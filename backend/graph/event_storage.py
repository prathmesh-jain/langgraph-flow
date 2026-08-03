import sqlite3
import json
import uuid
import asyncio
from typing import AsyncGenerator, Optional, Any
from contextlib import contextmanager
from datetime import datetime
import sys


class _EventStorage:
    """Internal SQLite storage for FlowRecorder with in-memory caching."""
    
    def __init__(self, db_path: str = "langgraph_events.db", persist: bool = False):
        self.db_path = db_path
        self.persist = persist
        # In-memory event store for low-latency polling
        self._memory_events: dict[str, list[dict]] = {}
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
        # Store in memory for low-latency polling
        if run_id not in self._memory_events:
            self._memory_events[run_id] = []
        self._memory_events[run_id].append({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })
        
        # Store in persistent storage if persist flag is enabled
        if self.persist:
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
        # First check in-memory storage for low-latency access
        if run_id in self._memory_events:
            return self._memory_events[run_id]
        
        # Fall back to persistent storage if not in memory
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
        # Clear from memory
        if run_id in self._memory_events:
            del self._memory_events[run_id]
        
        # Clear from persistent storage
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
    
    def __init__(self, graph, persist: bool = False):
        self._graph = graph
        self._storage = _EventStorage(persist=persist)
        self._current_run_id = None
        self._subgraph_topology = self._extract_subgraph_topology()
    
    def _extract_subgraph_topology(self) -> dict:
        """Extract subgraph topology to map internal nodes to their parent subgraphs."""
        topology = {}
        try:
            if hasattr(self._graph, 'nodes'):
                print(f"[DEBUG FlowRecorder] Graph has nodes attribute", file=sys.stderr)
                for node_id, node_obj in self._graph.nodes.items():
                    print(f"[DEBUG FlowRecorder] Checking node {node_id}, has get_graph: {hasattr(node_obj, 'get_graph')}", file=sys.stderr)
                    if hasattr(node_obj, 'get_graph'):
                        subgraph_structure = node_obj.get_graph()
                        print(f"[DEBUG FlowRecorder] Subgraph {node_id} has nodes: {list(subgraph_structure.nodes)}", file=sys.stderr)
                        for sub_node_id in subgraph_structure.nodes:
                            if sub_node_id not in ["__start__", "__end__"]:
                                topology[sub_node_id] = node_id
                                print(f"[DEBUG FlowRecorder] Mapping {sub_node_id} -> {node_id}", file=sys.stderr)
        except Exception as e:
            print(f"[DEBUG FlowRecorder] Error extracting subgraph topology: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
        print(f"[DEBUG FlowRecorder] Final topology: {topology}", file=sys.stderr)
        return topology
    
    async def astream(self, inputs: dict, config: dict, thread_id: Optional[str] = None, **kwargs) -> AsyncGenerator:
        """Stream graph execution while recording events.
        
        This method streams graph execution while storing events internally for later retrieval via /stream endpoint.
        
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
        subgraph_stack = []  # Stack to handle nested subgraphs
        
        # Get list of subgraph nodes from the compiled graph
        subgraph_nodes = set()
        try:
            if hasattr(self._graph, 'nodes'):
                for node_id, node_obj in self._graph.nodes.items():
                    if hasattr(node_obj, 'get_graph'):
                        subgraph_nodes.add(node_id)
        except:
            pass
        
        print(f"[DEBUG FlowRecorder] Detected subgraph nodes: {subgraph_nodes}", file=sys.stderr)
        
        try:
            # Use astream_events with v2 for better compatibility with custom events
            # v3 requires transformers which adds complexity for our use case
            if "stream_mode" not in kwargs:
                kwargs["stream_mode"] = ["updates", "custom"]
            kwargs["version"] = "v2"
            # Enable subgraph streaming to capture internal subgraph node events
            kwargs["subgraphs"] = True
            
            async for event in self._graph.astream_events(inputs, config, **kwargs):
                event_type = event.get("event", "")
                metadata = event.get("metadata", {})
                data = event.get("data", {})
                
                print(f"[DEBUG FlowRecorder] Event type: {event_type}, metadata: {metadata}, data: {data}", file=sys.stderr)
                
                # Capture custom events from stream_writer (for parallel subgraphs)
                # In v2, custom events come through as on_chain_end with custom data
                if event_type == "on_chain_end":
                    output = data.get("output", {})
                    print(f"[DEBUG FlowRecorder] on_chain_end output: {output}", file=sys.stderr)
                    
                    if isinstance(output, dict):
                        # Check for custom event markers in output
                        if "__custom__" in output:
                            custom_events = output.get("__custom__", [])
                            print(f"[DEBUG FlowRecorder] Found {len(custom_events)} custom events in __custom__", file=sys.stderr)
                            for custom_event in custom_events:
                                custom_type = custom_event.get("type")
                                custom_data = custom_event.get("data", {})
                                
                                if custom_type == "node_started":
                                    node_id = custom_data.get("node_id")
                                    parent = custom_data.get("parent")
                                    event_payload = {"node_id": node_id}
                                    if parent:
                                        event_payload["parent"] = parent
                                    self._storage.store_event(run_id, "node_started", event_payload)
                                    print(f"[DEBUG FlowRecorder] Stored node_started for: {node_id} with parent: {parent}", file=sys.stderr)
                                    yield {"type": "event", "data": {"type": "node_started", "data": event_payload}}
                                
                                elif custom_type == "node_completed":
                                    node_id = custom_data.get("node_id")
                                    parent = custom_data.get("parent")
                                    event_payload = {"node_id": node_id}
                                    if parent:
                                        event_payload["parent"] = parent
                                    self._storage.store_event(run_id, "node_completed", event_payload)
                                    print(f"[DEBUG FlowRecorder] Stored node_completed for: {node_id} with parent: {parent}", file=sys.stderr)
                                    yield {"type": "event", "data": {"type": "node_completed", "data": event_payload}}
                
                # Track node start events
                if "on_chain_start" in event_type:
                    node_id = metadata.get("langgraph_node") or metadata.get("node_id") or metadata.get("name")
                    print(f"[DEBUG FlowRecorder] on_chain_start - node_id: {node_id}, current_subgraph: {current_subgraph}", file=sys.stderr)
                    
                    if node_id and node_id != "__start__" and node_id != "__end__":
                        # Extract parent from checkpoint_ns metadata
                        checkpoint_ns = metadata.get("checkpoint_ns", "")
                        parent_from_ns = None
                        if checkpoint_ns and "|" in checkpoint_ns:
                            # Format: subgraph_name:uuid|node_id:uuid
                            parent_from_ns = checkpoint_ns.split("|")[0].split(":")[0]
                        elif checkpoint_ns and ":" in checkpoint_ns:
                            # Format: subgraph_name:uuid
                            parent_from_ns = checkpoint_ns.split(":")[0]
                        
                        # Check if this node is a subgraph
                        if node_id in subgraph_nodes:
                            # Push to subgraph stack
                            subgraph_stack.append(node_id)
                            current_subgraph = node_id
                            print(f"[DEBUG FlowRecorder] Entering subgraph: {node_id}", file=sys.stderr)
                        
                        # Determine parent and format node_id for frontend
                        parent = None
                        formatted_node_id = node_id
                        
                        if parent_from_ns and parent_from_ns != node_id:
                            parent = parent_from_ns
                            formatted_node_id = f"{parent_from_ns}.{node_id}"
                            print(f"[DEBUG FlowRecorder] Formatting node_id as {formatted_node_id} from checkpoint_ns", file=sys.stderr)
                        elif node_id in self._subgraph_topology:
                            parent = self._subgraph_topology[node_id]
                            formatted_node_id = f"{parent}.{node_id}"
                            print(f"[DEBUG FlowRecorder] Formatting node_id as {formatted_node_id} from topology", file=sys.stderr)
                        elif current_subgraph and node_id != current_subgraph:
                            parent = current_subgraph
                            formatted_node_id = f"{current_subgraph}.{node_id}"
                            print(f"[DEBUG FlowRecorder] Formatting node_id as {formatted_node_id} from current_subgraph", file=sys.stderr)
                        
                        event_payload = {"node_id": formatted_node_id}
                        if parent:
                            event_payload["parent"] = parent
                        
                        self._storage.store_event(run_id, "node_started", event_payload)
                        yield {"type": "event", "data": {"type": "node_started", "data": event_payload}}
                
                # Track node end events
                elif "on_chain_end" in event_type:
                    node_id = metadata.get("langgraph_node") or metadata.get("node_id") or metadata.get("name")
                    print(f"[DEBUG FlowRecorder] on_chain_end - node_id: {node_id}, current_subgraph: {current_subgraph}", file=sys.stderr)
                    
                    if node_id and node_id != "__start__" and node_id != "__end__":
                        # Extract parent from checkpoint_ns metadata
                        checkpoint_ns = metadata.get("checkpoint_ns", "")
                        parent_from_ns = None
                        if checkpoint_ns and "|" in checkpoint_ns:
                            # Format: subgraph_name:uuid|node_id:uuid
                            parent_from_ns = checkpoint_ns.split("|")[0].split(":")[0]
                        elif checkpoint_ns and ":" in checkpoint_ns:
                            # Format: subgraph_name:uuid
                            parent_from_ns = checkpoint_ns.split(":")[0]
                        
                        # Determine parent and format node_id for frontend
                        parent = None
                        formatted_node_id = node_id
                        
                        if parent_from_ns and parent_from_ns != node_id:
                            parent = parent_from_ns
                            formatted_node_id = f"{parent_from_ns}.{node_id}"
                        elif node_id in self._subgraph_topology:
                            parent = self._subgraph_topology[node_id]
                            formatted_node_id = f"{parent}.{node_id}"
                        elif current_subgraph and node_id != current_subgraph:
                            parent = current_subgraph
                            formatted_node_id = f"{current_subgraph}.{node_id}"
                        
                        event_payload = {"node_id": formatted_node_id}
                        if parent:
                            event_payload["parent"] = parent
                        
                        self._storage.store_event(run_id, "node_completed", event_payload)
                        yield {"type": "event", "data": {"type": "node_completed", "data": event_payload}}
                        
                        # Check if we're exiting a subgraph
                        if node_id in subgraph_nodes and subgraph_stack:
                            exited_subgraph = subgraph_stack.pop()
                            print(f"[DEBUG FlowRecorder] Exiting subgraph: {exited_subgraph}", file=sys.stderr)
                            current_subgraph = subgraph_stack[-1] if subgraph_stack else None
                
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
            
            # Auto-cleanup if not persisting - delay to allow stream endpoint to finish
            if not self._storage.persist:
                print(f"[DEBUG FlowRecorder] Auto-cleanup enabled, delaying deletion to allow stream to finish", file=sys.stderr)
                # Wait 5 seconds to allow stream endpoint to finish sending all events
                await asyncio.sleep(5)
                print(f"[DEBUG FlowRecorder] Auto-cleanup deleting events after delay", file=sys.stderr)
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
                        event_payload = {"node_id": node_id}
                        # Use topology to infer parent
                        if node_id in self._subgraph_topology:
                            parent = self._subgraph_topology[node_id]
                            event_payload["parent"] = parent
                        self._storage.store_event(run_id, "node_started", event_payload)
                
                # Capture node end events
                elif "on_chain_end" in event_type:
                    node_id = metadata.get("langgraph_node") or metadata.get("node_id") or metadata.get("name")
                    if node_id and node_id != "__start__" and node_id != "__end__":
                        event_payload = {"node_id": node_id}
                        # Use topology to infer parent
                        if node_id in self._subgraph_topology:
                            parent = self._subgraph_topology[node_id]
                            event_payload["parent"] = parent
                        self._storage.store_event(run_id, "node_completed", event_payload)
                
                yield event
            
            # Mark run as completed
            self._storage.complete_run(run_id)
            self._storage.store_event(run_id, "graph_completed", {})
            
            # Auto-cleanup if not persisting - delay to allow stream endpoint to finish
            if not self._storage.persist:
                # Wait 5 seconds to allow stream endpoint to finish sending all events
                await asyncio.sleep(5)
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
