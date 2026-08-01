import asyncio
import json
import random
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from fastapi import Query
from pydantic import BaseModel
from .workflow import create_workflow
from .event_storage import FlowRecorder


# Compile the graph once at startup
graph = create_workflow()

# Wrap with FlowRecorder for event recording
# Set persist=True to keep events for /stream endpoint to retrieve
flow = FlowRecorder(graph, persist=True)


class RunRequest(BaseModel):
    thread_id: str


router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/run")
async def run_graph(request: RunRequest):
    """Execute the LangGraph workflow with streaming output.
    
    This endpoint runs the configured workflow with all its nodes and edges.
    Events are automatically recorded by FlowRecorder for visualization.
    
    Args:
        request: Contains thread_id for this execution
    """
    # Generate random subgraph count (2-10)
    subgraph_count = random.randint(3, 10)
    
    inputs = {
        "status": "pending",
        "plan": [],
        "current_step": "",
        "results": [],
        "execution_path": "",
        "subgraph_count": subgraph_count
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
    
    This endpoint continuously polls FlowRecorder's storage for new events
    and streams them as they arrive during graph execution.
    
    Args:
        thread_id: The thread_id passed during /run execution
    """
    import sys
    import asyncio
    print(f"[DEBUG] /stream called with thread_id: {thread_id}", file=sys.stderr)
    
    sent_event_ids = set()
    
    async def generate():
        """Continuously poll for new events and stream them."""
        while True:
            events = flow.get_events(run_id=thread_id)
            
            print(f"[DEBUG] Polling events for {thread_id}: {len(events)} total", file=sys.stderr)
            
            # Send new events that haven't been sent yet
            for event in events:
                event_id = f"{event['type']}_{event.get('timestamp', '')}"
                if event_id not in sent_event_ids:
                    print(f"[DEBUG] Streaming new event: {event}", file=sys.stderr)
                    yield f"data: {json.dumps(event)}\n\n"
                    sent_event_ids.add(event_id)
            
            # Check if graph is completed
            if events and any(e["type"] == "graph_completed" for e in events):
                print(f"[DEBUG] Graph completed, ending stream", file=sys.stderr)
                break
            
            # Wait before polling again
            await asyncio.sleep(0.1)
    
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
    
    This endpoint extracts the graph structure from the compiled LangGraph
    including subgraph internal nodes and edges.
    """
    # Get the underlying graph from FlowRecorder
    compiled_graph = flow._graph
    
    nodes = []
    edges = []
    subgraph_nodes = set()
    
    # Method 1: Try to get graph structure directly
    try:
        graph_structure = compiled_graph.get_graph()
        
        # Extract nodes, skip __start__ and __end__ (they don't participate in visualization)
        for node_id in graph_structure.nodes:
            if node_id not in ["__start__", "__end__"]:
                nodes.append({
                    "id": node_id,
                    "type": "default"
                })
        
        # Try to extract edges using the graph's internal structure
        # LangGraph stores edges in different ways depending on version
        if hasattr(graph_structure, 'edges'):
            # Try to iterate as a collection
            try:
                edge_list = list(graph_structure.edges)
                for edge in edge_list:
                    if isinstance(edge, tuple) and len(edge) >= 2:
                        source = str(edge[0])
                        target = str(edge[1])
                        # Skip edges from/to __start__/__end__ since we don't show START/END nodes
                        if "__start__" not in source and "__end__" not in target:
                            if source != target:
                                edges.append({"id": f"{source}-{target}", "source": source, "target": target})
            except:
                pass
        
        # If no edges, try all_edges
        if not edges and hasattr(graph_structure, 'all_edges'):
            try:
                for edge in graph_structure.all_edges():
                    source = str(edge[0])
                    target = str(edge[1])
                    if "__start__" not in source and "__end__" not in target:
                        if source != target:
                            edges.append({"id": f"{source}-{target}", "source": source, "target": target})
            except:
                pass
        
        # Try to extract subgraph internal structure
        # Check if any node is a subgraph by checking if it has a get_graph method
        import sys
        print(f"[DEBUG] Checking {len(nodes)} nodes for subgraphs", file=sys.stderr)
        for node in nodes:
            node_id = node["id"]
            print(f"[DEBUG] Checking node: {node_id}", file=sys.stderr)
            try:
                # Try to get the node from the compiled graph
                if hasattr(compiled_graph, 'nodes') and node_id in compiled_graph.nodes:
                    node_obj = compiled_graph.nodes[node_id]
                    print(f"[DEBUG] Node object type: {type(node_obj)}", file=sys.stderr)
                    print(f"[DEBUG] Node object has get_graph: {hasattr(node_obj, 'get_graph')}", file=sys.stderr)
                    # Check if this node is a subgraph (has get_graph method)
                    if hasattr(node_obj, 'get_graph'):
                        subgraph_structure = node_obj.get_graph()
                        print(f"[DEBUG] Found subgraph in node: {node_id}", file=sys.stderr)
                        
                        # Extract subgraph internal nodes
                        for sub_node_id in subgraph_structure.nodes:
                            if sub_node_id not in ["__start__", "__end__"]:
                                # Mark as subgraph node with parent reference
                                subgraph_internal_id = f"{node_id}.{sub_node_id}"
                                subgraph_nodes.add(subgraph_internal_id)
                                nodes.append({
                                    "id": subgraph_internal_id,
                                    "type": "subgraph",
                                    "parent": node_id
                                })
                        
                        # Extract subgraph internal edges
                        if hasattr(subgraph_structure, 'edges'):
                            try:
                                sub_edge_list = list(subgraph_structure.edges)
                                for sub_edge in sub_edge_list:
                                    if isinstance(sub_edge, tuple) and len(sub_edge) >= 2:
                                        sub_source = str(sub_edge[0])
                                        sub_target = str(sub_edge[1])
                                        # Skip __start__/__end__ edges
                                        if "__start__" not in sub_source and "__end__" not in sub_target:
                                            if sub_source != sub_target:
                                                sub_source_id = f"{node_id}.{sub_source}"
                                                sub_target_id = f"{node_id}.{sub_target}"
                                                edges.append({
                                                    "id": f"{sub_source_id}-{sub_target_id}",
                                                    "source": sub_source_id,
                                                    "target": sub_target_id,
                                                    "subgraph": node_id
                                                })
                            except:
                                pass
            except Exception as e:
                print(f"[DEBUG] Error checking subgraph for {node_id}: {e}", file=sys.stderr)
                pass
                
    except Exception as e:
        import sys
        print(f"Error getting graph structure: {e}", file=sys.stderr)
    
    # Method 2: Fallback to mermaid parsing if direct extraction failed
    if not edges:
        try:
            mermaid_str = compiled_graph.get_graph().draw_mermaid()
            lines = mermaid_str.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('graph') or line.startswith('%%') or line.startswith('classDef') or line.startswith('style'):
                    continue
                
                if '-->' in line:
                    parts = line.split('-->')
                    if len(parts) == 2:
                        source = parts[0].strip()
                        target_part = parts[1].strip()
                        
                        if '|' in target_part:
                            target = target_part.split('|')[-1].strip().rstrip(';')
                        else:
                            target = target_part.rstrip(';')
                        
                        # Clean up
                        source = source.replace('([', '').replace('])', '').replace('[[', '').replace(']]', '')
                        target = target.replace('([', '').replace('])', '').replace('[[', '').replace(']]', '')
                        
                        # Skip __start__ and __end__ edges
                        if "__start__" not in source and "__end__" not in target:
                            if source != target and source and target:
                                edges.append({"id": f"{source}-{target}", "source": source, "target": target})
                                
                                if source not in [n["id"] for n in nodes]:
                                    nodes.append({"id": source, "type": "default"})
                                if target not in [n["id"] for n in nodes]:
                                    nodes.append({"id": target, "type": "default"})
        except Exception as e:
            import sys
            print(f"Error parsing mermaid: {e}", file=sys.stderr)
    
    import sys
    print(f"Final nodes: {nodes}", file=sys.stderr)
    print(f"Final edges: {edges}", file=sys.stderr)
    print(f"Subgraph nodes: {subgraph_nodes}", file=sys.stderr)
    
    return {
        "nodes": nodes,
        "edges": edges,
        "subgraph_nodes": list(subgraph_nodes)
    }


async def _error_stream(message: str):
    """Helper to stream error messages."""
    yield f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"
