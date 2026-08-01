import sqlite3
import json
import uuid
from typing import AsyncGenerator, Optional, Any
from contextlib import contextmanager
from datetime import datetime


class _EventStorage:
    """Internal SQLite storage for FlowRecorder."""
    
    def __init__(self, db_path: str = "langgraph_events.db", persist: bool = False):
        self.db_path = db_path
        self.persist = persist
        self._init_db()
    
    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    status TEXT DEFAULT 'running'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    event_type TEXT,
                    data TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_events_run_id ON events(run_id)")
    
    def create_run(self, run_id: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO runs (id, started_at, status) VALUES (?, ?, ?)",
                (run_id, datetime.now(), 'running')
            )
    
    def store_event(self, run_id: str, event_type: str, data: dict) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO events (run_id, event_type, data, timestamp) VALUES (?, ?, ?, ?)",
                (run_id, event_type, json.dumps(data), datetime.now())
            )
    
    def complete_run(self, run_id: str) -> None:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE runs SET completed_at = ?, status = ? WHERE id = ?",
                (datetime.now(), 'completed', run_id)
            )
    
    def get_events(self, run_id: str) -> list[dict]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT event_type, data, timestamp FROM events WHERE run_id = ? ORDER BY timestamp",
                (run_id,)
            )
            return [
                {
                    "type": row["event_type"],
                    "data": json.loads(row["data"]),
                    "timestamp": row["timestamp"]
                }
                for row in cursor.fetchall()
            ]
    
    def cleanup_run(self, run_id: str) -> None:
        with self._get_connection() as conn:
            conn.execute("DELETE FROM events WHERE run_id = ?", [run_id])
            conn.execute("DELETE FROM runs WHERE id = ?", [run_id])
    
    def get_active_run_id(self) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id FROM runs WHERE status = 'running' ORDER BY started_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            return row["id"] if row else None


class FlowRecorder:
    """Wrapper for LangGraph compiled graph that records execution events.
    
    Usage:
        graph = builder.compile()
        flow = FlowRecorder(graph, persist=False)
        
        # Use like the original graph - transparent pass-through
        async for chunk in flow.astream(inputs, config, stream_mode=["updates"]):
            # Process chunks normally
            print(chunk)
        
        # Get recorded events for visualization
        events = flow.get_events()
    """
    
    def __init__(self, graph: Any, persist: bool = False, db_path: str = "langgraph_events.db"):
        """Initialize FlowRecorder.
        
        Args:
            graph: Compiled LangGraph graph
            persist: If False, auto-deletes events after completion. If True, keeps them.
            db_path: Path to SQLite database (internal, user doesn't need to know)
        """
        self._graph = graph
        self._storage = _EventStorage(db_path, persist)
        self._current_run_id: Optional[str] = None
    
    async def astream(self, inputs: dict, config: dict, thread_id: Optional[str] = None, **kwargs) -> AsyncGenerator:
        """Stream graph execution while recording events.
        
        This method transparently passes through all chunks from the original graph
        while storing events internally for later retrieval via /stream endpoint.
        
        Args:
            thread_id: Optional thread_id to use as run_id
        """
        import sys
        run_id = thread_id or str(uuid.uuid4())
        self._current_run_id = run_id
        print(f"[DEBUG FlowRecorder] astream called with thread_id: {thread_id}, run_id: {run_id}", file=sys.stderr)
        
        self._storage.create_run(run_id)
        self._storage.store_event(run_id, "graph_started", {})
        print(f"[DEBUG FlowRecorder] Created run and stored graph_started event", file=sys.stderr)
        
        # Track current subgraph context
        current_subgraph = None
        
        try:
            # Use astream_events internally to capture node start events for storage
            async for event in self._graph.astream_events(inputs, config, **kwargs):
                event_type = event.get("event", "")
                metadata = event.get("metadata", {})
                
                print(f"[DEBUG FlowRecorder] Event type: {event_type}", file=sys.stderr)
                
                # Capture custom events from stream_writer (for parallel subgraphs)
                # These are emitted via get_stream_writer() in workflow nodes
                if event_type == "on_chain_end":
                    output = event.get("data", {}).get("output", {})
                    print(f"[DEBUG FlowRecorder] on_chain_end output: {output}", file=sys.stderr)
                    if isinstance(output, dict):
                        # Check for custom event markers
                        if "__custom__" in output:
                            custom_events = output.get("__custom__", [])
                            print(f"[DEBUG FlowRecorder] Found {len(custom_events)} custom events", file=sys.stderr)
                            for custom_event in custom_events:
                                custom_type = custom_event.get("type")
                                custom_data = custom_event.get("data", {})
                                
                                if custom_type == "subgraph_started":
                                    node_id = custom_data.get("node_id")
                                    self._storage.store_event(run_id, "subgraph_started", {"node_id": node_id})
                                    self._storage.store_event(run_id, "node_started", {"node_id": node_id})
                                    print(f"[DEBUG FlowRecorder] Stored custom subgraph_started for: {node_id}", file=sys.stderr)
                                    # Stream immediately for real-time updates
                                    yield {"type": "event", "data": {"type": "subgraph_started", "data": {"node_id": node_id}}}
                                    yield {"type": "event", "data": {"type": "node_started", "data": {"node_id": node_id}}}
                                
                                elif custom_type == "subgraph_completed":
                                    node_id = custom_data.get("node_id")
                                    self._storage.store_event(run_id, "subgraph_completed", {"node_id": node_id})
                                    self._storage.store_event(run_id, "node_completed", {"node_id": node_id})
                                    print(f"[DEBUG FlowRecorder] Stored custom subgraph_completed for: {node_id}", file=sys.stderr)
                                    yield {"type": "event", "data": {"type": "subgraph_completed", "data": {"node_id": node_id}}}
                                    yield {"type": "event", "data": {"type": "node_completed", "data": {"node_id": node_id}}}
                                
                                elif custom_type == "node_started":
                                    node_id = custom_data.get("node_id")
                                    parent = custom_data.get("parent")
                                    event_payload = {"node_id": node_id}
                                    if parent:
                                        event_payload["parent"] = parent
                                    self._storage.store_event(run_id, "node_started", event_payload)
                                    print(f"[DEBUG FlowRecorder] Stored custom node_started for: {node_id}", file=sys.stderr)
                                    yield {"type": "event", "data": {"type": "node_started", "data": event_payload}}
                                
                                elif custom_type == "node_completed":
                                    node_id = custom_data.get("node_id")
                                    parent = custom_data.get("parent")
                                    event_payload = {"node_id": node_id}
                                    if parent:
                                        event_payload["parent"] = parent
                                    self._storage.store_event(run_id, "node_completed", event_payload)
                                    print(f"[DEBUG FlowRecorder] Stored custom node_completed for: {node_id}", file=sys.stderr)
                                    yield {"type": "event", "data": {"type": "node_completed", "data": event_payload}}
                
                # Track subgraph entry/exit
                if "on_chain_start" in event_type:
                    node_id = metadata.get("langgraph_node") or metadata.get("node_id") or metadata.get("name")
                    print(f"[DEBUG FlowRecorder] on_chain_start - node_id: {node_id}, current_subgraph: {current_subgraph}", file=sys.stderr)
                    
                    if node_id and node_id != "__start__" and node_id != "__end__":
                        # Check if this node is a known subgraph (hardcoded for now)
                        known_subgraphs = ["research_subgraph", "direct_executor"]
                        
                        if node_id in known_subgraphs:
                            # This is a subgraph node entering
                            current_subgraph = node_id
                            print(f"[DEBUG FlowRecorder] Entering subgraph: {current_subgraph}", file=sys.stderr)
                            self._storage.store_event(run_id, "subgraph_started", {"node_id": node_id})
                            self._storage.store_event(run_id, "node_started", {"node_id": node_id})
                            # Stream immediately for real-time updates
                            yield {"type": "event", "data": {"type": "subgraph_started", "data": {"node_id": node_id}}}
                            yield {"type": "event", "data": {"type": "node_started", "data": {"node_id": node_id}}}
                        elif current_subgraph:
                            # We're inside a subgraph, prefix the node ID
                            full_node_id = f"{current_subgraph}.{node_id}"
                            self._storage.store_event(run_id, "node_started", {"node_id": full_node_id, "parent": current_subgraph})
                            print(f"[DEBUG FlowRecorder] Stored subgraph node_started for: {full_node_id}", file=sys.stderr)
                            yield {"type": "event", "data": {"type": "node_started", "data": {"node_id": full_node_id, "parent": current_subgraph}}}
                        else:
                            # Regular node in main graph
                            self._storage.store_event(run_id, "node_started", {"node_id": node_id})
                            print(f"[DEBUG FlowRecorder] Stored node_started for: {node_id}", file=sys.stderr)
                            # Stream immediately for real-time updates
                            yield {"type": "event", "data": {"type": "node_started", "data": {"node_id": node_id}}}
                
                # Capture node end events for storage only
                elif "on_chain_end" in event_type:
                    node_id = metadata.get("langgraph_node") or metadata.get("node_id") or metadata.get("name")
                    print(f"[DEBUG FlowRecorder] on_chain_end - node_id: {node_id}, current_subgraph: {current_subgraph}", file=sys.stderr)
                    
                    if node_id and node_id != "__start__" and node_id != "__end__":
                        known_subgraphs = ["research_subgraph", "direct_executor"]
                        
                        if current_subgraph and node_id == current_subgraph:
                            # Exiting subgraph
                            print(f"[DEBUG FlowRecorder] Exiting subgraph: {current_subgraph}", file=sys.stderr)
                            self._storage.store_event(run_id, "subgraph_completed", {"node_id": current_subgraph})
                            self._storage.store_event(run_id, "node_completed", {"node_id": current_subgraph})
                            current_subgraph = None
                            # Stream immediately for real-time updates
                            yield {"type": "event", "data": {"type": "subgraph_completed", "data": {"node_id": node_id}}}
                            yield {"type": "event", "data": {"type": "node_completed", "data": {"node_id": node_id}}}
                        elif current_subgraph and node_id not in known_subgraphs:
                            # This is an internal node of the current subgraph
                            full_node_id = f"{current_subgraph}.{node_id}"
                            self._storage.store_event(run_id, "node_completed", {"node_id": full_node_id, "parent": current_subgraph})
                            print(f"[DEBUG FlowRecorder] Stored subgraph node_completed for: {full_node_id}", file=sys.stderr)
                            yield {"type": "event", "data": {"type": "node_completed", "data": {"node_id": full_node_id, "parent": current_subgraph}}}
                        else:
                            self._storage.store_event(run_id, "node_completed", {"node_id": node_id})
                            print(f"[DEBUG FlowRecorder] Stored node_completed for: {node_id}", file=sys.stderr)
                            # Stream immediately for real-time updates
                            yield {"type": "event", "data": {"type": "node_completed", "data": {"node_id": node_id}}}
                
                # Pass through custom chunks from output_formatter
                if event.get("event") == "on_chain_end" and "output_formatter" in str(metadata):
                    output = event.get("data", {}).get("output", {})
                    if output and isinstance(output, dict) and "content" in output:
                        yield {"type": "custom", "data": output}
            
            # Mark run as completed
            self._storage.complete_run(run_id)
            self._storage.store_event(run_id, "graph_completed", {})
            print(f"[DEBUG FlowRecorder] Graph completed, events stored", file=sys.stderr)
            print(f"[DEBUG FlowRecorder] Total events for run_id {run_id}: {len(self._storage.get_events(run_id))}", file=sys.stderr)
            
            # Auto-cleanup if not persisting
            if not self._storage.persist:
                print(f"[DEBUG FlowRecorder] Auto-cleanup enabled, deleting events", file=sys.stderr)
                self._storage.cleanup_run(run_id)
                self._current_run_id = None
            else:
                print(f"[DEBUG FlowRecorder] Persist enabled, keeping events", file=sys.stderr)
        except Exception as e:
            print(f"[DEBUG FlowRecorder] Error: {e}", file=sys.stderr)
            self._storage.store_event(run_id, "error", {"error": str(e)})
            raise
    
    async def astream_events(self, inputs: dict, config: dict, thread_id: Optional[str] = None, **kwargs) -> AsyncGenerator:
        """Stream graph execution events while recording node start/completion.
        
        This method uses LangGraph's astream_events to capture node start events
        for dynamic visualization.
        
        Args:
            thread_id: Optional thread_id to use as run_id. If not provided, generates a UUID.
        """
        run_id = thread_id or str(uuid.uuid4())
        self._current_run_id = run_id
        self._storage.create_run(run_id)
        self._storage.store_event(run_id, "graph_started", {})
        
        try:
            # Use astream_events to capture node start events
            async for event in self._graph.astream_events(inputs, config, **kwargs):
                event_type = event.get("event", "")
                metadata = event.get("metadata", {})
                
                # Capture node start events - try multiple metadata keys
                if "on_chain_start" in event_type:
                    node_id = metadata.get("langgraph_node") or metadata.get("node_id") or metadata.get("name")
                    if node_id and node_id != "__start__" and node_id != "__end__":
                        self._storage.store_event(run_id, "node_started", {"node_id": node_id})
                
                # Capture node end events
                elif "on_chain_end" in event_type:
                    node_id = metadata.get("langgraph_node") or metadata.get("node_id") or metadata.get("name")
                    if node_id and node_id != "__start__" and node_id != "__end__":
                        self._storage.store_event(run_id, "node_completed", {"node_id": node_id})
                
                yield event
            
            # Mark run as completed
            self._storage.complete_run(run_id)
            self._storage.store_event(run_id, "graph_completed", {})
            
            # Auto-cleanup if not persisting
            if not self._storage.persist:
                self._storage.cleanup_run(run_id)
                self._current_run_id = None
        except Exception as e:
            self._storage.store_event(run_id, "error", {"error": str(e)})
            raise
    
    async def ainvoke(self, inputs: dict, config: dict, **kwargs) -> dict:
        """Invoke graph while recording events."""
        result = await self._graph.ainvoke(inputs, config, **kwargs)
        return result
    
    def get_events(self, run_id: Optional[str] = None) -> list[dict]:
        """Get recorded events for a run.
        
        Args:
            run_id: Specific run ID, or None to get current run's events
        
        Returns:
            List of recorded events
        """
        target_run_id = run_id or self._current_run_id or self._storage.get_active_run_id()
        if target_run_id:
            return self._storage.get_events(target_run_id)
        return []
    
    @property
    def current_run_id(self) -> Optional[str]:
        """Get the current run ID."""
        return self._current_run_id or self._storage.get_active_run_id()
