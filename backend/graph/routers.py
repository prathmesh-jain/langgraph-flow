import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from .workflow import create_workflow
from .event_storage import FlowRecorder


# Compile the graph once at startup
graph = create_workflow()

# Wrap with FlowRecorder for event recording
flow = FlowRecorder(graph, persist=False)


router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/run")
async def run_graph():
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
    """
    inputs = {
        "status": "pending",
        "plan": [],
        "current_step": "",
        "results": [],
        "execution_path": ""
    }
    config = {"configurable": {"thread_id": "default"}}
    
    async def generate():
        """Stream execution results including custom text chunks."""
        # Use FlowRecorder's astream - it transparently records events
        async for chunk in flow.astream(
            inputs,
            config=config,
            stream_mode=["updates", "custom"],
            version="v2",
        ):
            # Pass through custom text chunks from output_formatter
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
async def stream_graph():
    """Stream node execution events for visualization.
    
    This endpoint reads events from FlowRecorder's storage.
    Events are automatically recorded during /run execution.
    """
    events = flow.get_events()
    
    if not events:
        return StreamingResponse(
            _error_stream("No active run found. Please run the graph first."),
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


async def _error_stream(message: str):
    """Helper to stream error messages."""
    yield f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"
