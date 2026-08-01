import asyncio
import json
import random
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from fastapi import Query
from pydantic import BaseModel
from .workflow import create_workflow, create_subgraph
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
    compiled_graph = flow._graph
    
    nodes = []
    edges = []
    subgraph_nodes = []
    subgraph_node_keys = set()
    subgraph_templates = {}
    parallel_execution_nodes = []
    
    try:
        graph_structure = compiled_graph.get_graph()
        
        for node_id in graph_structure.nodes:
            if node_id not in ["__start__", "__end__"]:
                node_entry = {"id": node_id, "type": "default"}
                nodes.append(node_entry)
        
        def extract_edges(gs, source_prefix="", target_prefix="", subgraph_label=None):
            extracted = []
            if hasattr(gs, 'edges'):
                try:
                    edge_list = list(gs.edges)
                    for edge in edge_list:
                        if isinstance(edge, tuple) and len(edge) >= 2:
                            source = source_prefix + str(edge[0]) if str(edge[0]) not in ["__start__", "__end__"] else None
                            target = target_prefix + str(edge[1]) if str(edge[1]) not in ["__start__", "__end__"] else None
                            if source and target:
                                edge_entry = {
                                    "id": f"{source}-{target}",
                                    "source": source,
                                    "target": target
                                }
                                if subgraph_label:
                                    edge_entry["subgraph"] = subgraph_label
                                extracted.append(edge_entry)
                except:
                    pass
            if not extracted and hasattr(gs, 'all_edges'):
                try:
                    for edge in gs.all_edges():
                        source = source_prefix + str(edge[0]) if str(edge[0]) not in ["__start__", "__end__"] else None
                        target = target_prefix + str(edge[1]) if str(edge[1]) not in ["__start__", "__end__"] else None
                        if source and target:
                            edge_entry = {"id": f"{source}-{target}", "source": source, "target": target}
                            if subgraph_label:
                                edge_entry["subgraph"] = subgraph_label
                            extracted.append(edge_entry)
                except:
                    pass
            return extracted
        
        edges = extract_edges(graph_structure)
        
        import sys
        print(f"[DEBUG] Checking {len(nodes)} nodes for subgraphs", file=sys.stderr)
        
        subgraph_template_instance = create_subgraph()
        subgraph_template_structure = subgraph_template_instance.get_graph()
        template_internal_nodes = []
        template_internal_edges = []
        
        for sub_node_id in subgraph_template_structure.nodes:
            if sub_node_id not in ["__start__", "__end__"]:
                template_internal_nodes.append(sub_node_id)
        
        for t_edge in extract_edges(subgraph_template_structure):
            template_internal_edges.append({
                "source": t_edge["source"],
                "target": t_edge["target"]
            })
        
        print(f"[DEBUG] Subgraph template internal nodes: {template_internal_nodes}", file=sys.stderr)
        
        for node in nodes:
            node_id = node["id"]
            is_subgraph_node = False
            
            try:
                if hasattr(compiled_graph, 'nodes') and node_id in compiled_graph.nodes:
                    node_obj = compiled_graph.nodes[node_id]
                    if hasattr(node_obj, 'get_graph'):
                        subgraph_structure = node_obj.get_graph()
                        print(f"[DEBUG] Found compiled subgraph in node: {node_id}", file=sys.stderr)
                        is_subgraph_node = True
                        
                        for sub_node_id in subgraph_structure.nodes:
                            if sub_node_id not in ["__start__", "__end__"]:
                                subgraph_internal_id = f"{node_id}.{sub_node_id}"
                                key = (subgraph_internal_id, node_id)
                                if key not in subgraph_node_keys:
                                    subgraph_node_keys.add(key)
                                    subgraph_nodes.append({"id": subgraph_internal_id, "parent": node_id})
                                nodes.append({
                                    "id": subgraph_internal_id,
                                    "type": "subgraph",
                                    "parent": node_id
                                })
                        
                        sub_edges = extract_edges(
                            subgraph_structure,
                            source_prefix=f"{node_id}.",
                            target_prefix=f"{node_id}.",
                            subgraph_label=node_id
                        )
                        edges.extend(sub_edges)
            except Exception as e:
                print(f"[DEBUG] Error checking compiled subgraph for {node_id}: {e}", file=sys.stderr)
            
            if node_id == "parallel_subgraphs":
                is_subgraph_node = True
                parallel_execution_nodes.append(node_id)
                print(f"[DEBUG] Marking parallel_subgraphs as parallel execution node with template", file=sys.stderr)
                
                subgraph_templates[node_id] = {
                    "pattern": r"^parallel_subgraphs_\d+$",
                    "internal_nodes": template_internal_nodes,
                    "internal_edges": template_internal_edges,
                    "parallel": True,
                    "upstream_node": "planner",
                    "downstream_node": "analyzer"
                }
                
                for sub_node_id in template_internal_nodes:
                    subgraph_internal_id = f"{node_id}.{sub_node_id}"
                    key = (subgraph_internal_id, node_id)
                    if key not in subgraph_node_keys:
                        subgraph_node_keys.add(key)
                        subgraph_nodes.append({"id": subgraph_internal_id, "parent": node_id})
                    nodes.append({
                        "id": subgraph_internal_id,
                        "type": "subgraph",
                        "parent": node_id
                    })
                
                for t_edge in template_internal_edges:
                    sub_source_id = f"{node_id}.{t_edge['source']}"
                    sub_target_id = f"{node_id}.{t_edge['target']}"
                    edges.append({
                        "id": f"{sub_source_id}-{sub_target_id}",
                        "source": sub_source_id,
                        "target": sub_target_id,
                        "subgraph": node_id
                    })
            
            if is_subgraph_node and not node.get("subgraph_info"):
                node["type"] = "subgraph_parent"
                
    except Exception as e:
        import sys
        print(f"Error getting graph structure: {e}", file=sys.stderr)
    
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
                        
                        source = source.replace('([', '').replace('])', '').replace('[[', '').replace(']]', '')
                        target = target.replace('([', '').replace('])', '').replace('[[', '').replace(']]', '')
                        
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
    print(f"Final nodes: {len(nodes)} - {[n['id'] for n in nodes]}", file=sys.stderr)
    print(f"Final edges: {len(edges)} - {[e['id'] for e in edges]}", file=sys.stderr)
    print(f"Subgraph nodes: {subgraph_nodes}", file=sys.stderr)
    print(f"Subgraph templates: {list(subgraph_templates.keys())}", file=sys.stderr)
    print(f"Parallel execution nodes: {parallel_execution_nodes}", file=sys.stderr)
    
    return {
        "nodes": nodes,
        "edges": edges,
        "subgraph_nodes": subgraph_nodes,
        "subgraph_templates": subgraph_templates,
        "parallel_execution_nodes": parallel_execution_nodes
    }


async def _error_stream(message: str):
    """Helper to stream error messages."""
    yield f"data: {json.dumps({'type': 'error', 'message': message})}\n\n"
