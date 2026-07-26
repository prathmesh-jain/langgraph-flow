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
        run_id = thread_id or str(uuid.uuid4())
        self._current_run_id = run_id
        self._storage.create_run(run_id)
        self._storage.store_event(run_id, "graph_started", {})
        
        try:
            # Use astream_events internally to capture node start events for storage
            async for event in self._graph.astream_events(inputs, config, **kwargs):
                event_type = event.get("event", "")
                metadata = event.get("metadata", {})
                
                # Capture node start events for storage only
                if "on_chain_start" in event_type:
                    node_id = metadata.get("langgraph_node") or metadata.get("node_id") or metadata.get("name")
                    if node_id and node_id != "__start__" and node_id != "__end__":
                        self._storage.store_event(run_id, "node_started", {"node_id": node_id})
                
                # Capture node end events for storage only
                elif "on_chain_end" in event_type:
                    node_id = metadata.get("langgraph_node") or metadata.get("node_id") or metadata.get("name")
                    if node_id and node_id != "__start__" and node_id != "__end__":
                        self._storage.store_event(run_id, "node_completed", {"node_id": node_id})
                
                # Pass through custom chunks from output_formatter
                if event.get("event") == "on_chain_end" and "output_formatter" in str(metadata):
                    output = event.get("data", {}).get("output", {})
                    if output and isinstance(output, dict) and "content" in output:
                        yield {"type": "custom", "data": output}
            
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
