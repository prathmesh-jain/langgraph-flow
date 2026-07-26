import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from fastapi import Query
from pydantic import BaseModel
from .workflow import create_workflow
from .event_storage import FlowRecorder


# Compile the graph once at startup
graph = create_workflow()

# Wrap with FlowRecorder for event recording
flow = FlowRecorder(graph, persist=False)


class RunRequest(BaseModel):
    thread_id: str


router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/run")
async def run_graph(request: RunRequest):
    """Execute the complex LangGraph workflow with streaming output.
    
    This endpoint runs a multi-node workflow with:
    - Input processor
    - Planner
    - Router with conditional branching
    - Subgraph (research path) with 4 nodes
    - Direct executor (alternative path)
    - Analyzer
    - Validator
    - Output formatter (streams text chunks)
    
    Events are automatically recorded by FlowRecorder for visualization.
    
    Args:
        request: Contains thread_id for this execution
    """
    inputs = {
        "status": "pending",
        "plan": [],
        "current_step": "",
        "results": [],
        "execution_path": ""
    }
    config = {"configurable": {"thread_id": request.thread_id}}
    
    async def generate():
        """Stream execution results including custom text chunks."""
        # Use FlowRecorder's astream - transparent wrapper that records events
        async for chunk in flow.astream(
            inputs,
            config=config,
            stream_mode=["updates", "custom"],
            version="v2",
            thread_id=request.thread_id,
        ):
            # Pass through custom text chunks from output_formatter only
            if chunk["type"] == "custom":
                yield f"data: {json.dumps(chunk['data'])}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get("/stream")
async def stream_graph(thread_id: str = Query(..., description="Thread ID to fetch events for")):
    """Stream node execution events for visualization.
    
    This endpoint reads events from FlowRecorder's storage for a specific thread_id.
    Events are automatically recorded during /run execution.
    
    Args:
        thread_id: The thread_id passed during /run execution
    """
    events = flow.get_events(run_id=thread_id)
    
    if not events:
        return StreamingResponse(
            _error_stream("No events found for this thread_id. Please run the graph first."),
            media_type="text/event-stream"
        )
    
    async def generate():
        """Stream events from FlowRecorder."""
        for event in events:
            yield f"data: {json.dumps(event)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.get("/graph")
async def get_graph_topology():
    """Get the graph topology (nodes and edges) for visualization.
    
    This endpoint extracts the graph structure from the compiled LangGraph.
    """
    # Get the underlying graph from FlowRecorder
    compiled_graph = flow._graph
    
    nodes = []
    edges = []
    
    # Extract nodes
    for node_id in compiled_graph.nodes:
        nodes.append({
            "id": node_id,
            "type": "default"
        })
    
    # Extract edges from the graph's internal structure
    # LangGraph stores edges in the StateGraph builder
    if hasattr(compiled_graph, 'graph'):
        graph_dict = compiled_graph.graph
        if 'edges' in graph_dict:
            for edge in graph_dict['edges']:
                # Handle different edge formats
                if isinstance(edge, tuple) and len(edge) == 2:
                    source = edge[0]
                    target = edge[1]
                    # Normalize special nodes
                    if source == "__start__":
                        source = "START"
                    if target == "__end__":
                        target = "END"
                    edges.append({
                        "id": f"{source}-{target}",
                        "source": source,
                        "target": target
                    })
    
    # Also try to get edges from the compiled graph's adjacency
    if not edges and hasattr(compiled_graph, 'all_edges'):
        for edge in compiled_graph.all_edges():
            source = edge[0]
            target = edge[1]
            if source == "__start__":
                source = "START"
            if target == "__end__":
                target = "END"
            edges.append({
                "id": f"{source}-{target}",
                "source": source,
                "target": target
            })
    
    # Fallback: manually construct edges based on workflow structure
    if not edges:
        # This is based on our known workflow structure
        workflow_edges = [
            ("START", "input_processor"),
            ("input_processor", "planner"),
            ("planner", "research_subgraph"),
            ("planner", "direct_executor"),
            ("research_subgraph", "analyzer"),
            ("direct_executor", "analyzer"),
            ("analyzer", "validator"),
            ("validator", "output_formatter"),
            ("output_formatter", "END"),
        ]
        for source, target in workflow_edges:
            edges.append({
                "id": f"{source}-{target}",
                "source": source,
                "target": target
            })
    
    return {
        "nodes": nodes,
        "edges": edges
    }


async def _error_stream(message: str):
    """Helper to stream error messages."""
    yield f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"
