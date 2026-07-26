import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from .workflow import create_workflow


# Compile the graph once at startup
graph = create_workflow()


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
        # Stream using LangGraph's native streaming with custom mode
        async for chunk in graph.astream(
            inputs,
            config=config,
            stream_mode=["custom"],
            version="v2",
        ):
            if chunk["type"] == "custom":
                # Yield custom text chunks from output_formatter as JSON
                yield f"data: {json.dumps(chunk['data'])}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
