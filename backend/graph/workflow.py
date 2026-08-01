import time
import asyncio
from typing import Literal
from langgraph.graph import StateGraph, START, END
from langgraph.config import get_stream_writer
from .state import GraphState, SubgraphState
import sys


# ============ SUBGRAPH NODES ============

def task_1_node(state: SubgraphState) -> SubgraphState:
    """First task in subgraph."""
    time.sleep(1)
    return {
        "task_results": state.get("task_results", []) + ["Task 1 completed"],
        "current_task": "task_2"
    }


def task_2_node(state: SubgraphState) -> SubgraphState:
    """Second task in subgraph."""
    time.sleep(1.5)
    return {
        "task_results": state.get("task_results", []) + ["Task 2 completed"],
        "current_task": "task_3"
    }


def task_3_node(state: SubgraphState) -> SubgraphState:
    """Third task in subgraph."""
    time.sleep(1)
    return {
        "task_results": state.get("task_results", []) + ["Task 3 completed"],
        "current_task": "aggregator"
    }


def subgraph_aggregator(state: SubgraphState) -> SubgraphState:
    """Aggregate results from subgraph tasks."""
    time.sleep(0.5)
    return {
        "status": "subgraph_completed",
        "task_results": state.get("task_results", []) + ["Subgraph aggregation complete"]
    }


def create_subgraph() -> StateGraph:
    """Create the research subgraph."""
    subgraph = StateGraph(SubgraphState)
    
    subgraph.add_node("task_1", task_1_node)
    subgraph.add_node("task_2", task_2_node)
    subgraph.add_node("task_3", task_3_node)
    subgraph.add_node("subgraph_aggregator", subgraph_aggregator)
    
    subgraph.add_edge(START, "task_1")
    subgraph.add_edge("task_1", "task_2")
    subgraph.add_edge("task_2", "task_3")
    subgraph.add_edge("task_3", "subgraph_aggregator")
    subgraph.add_edge("subgraph_aggregator", END)
    
    return subgraph.compile()


# ============ MAIN GRAPH NODES ============

def input_processor(state: GraphState) -> GraphState:
    """Process initial input."""
    time.sleep(0.5)
    return {
        "status": "input_processed",
        "execution_path": "processing"
    }


def planner_node(state: GraphState) -> GraphState:
    """Planner node - creates execution plan and determines subgraph count based on state."""
    time.sleep(2)
    plan = ["research", "analysis", "validation", "output"]
    
    # Determine subgraph count from state (e.g., alert count from input)
    # In real scenario, this would come from alert details in state
    # For demo, use a default if not set
    subgraph_count = state.get("subgraph_count", 1)
    
    # If subgraph_count is 1, generate random for demo purposes
    # In production, this would be based on actual alert count
    if subgraph_count == 1:
        import random
        subgraph_count = random.randint(2, 5)  # Simulate alert count
    
    print(f"[DEBUG planner] Determined subgraph_count: {subgraph_count}", file=sys.stderr)
    
    return {
        "status": "planned",
        "plan": plan,
        "current_step": "research",
        "execution_path": "planned",
        "subgraph_count": subgraph_count
    }


def route_decision(state: GraphState) -> Literal["parallel_subgraphs", "direct_executor"]:
    """Route to parallel subgraphs or direct execution based on plan."""
    if "research" in state.get("plan", []):
        return "parallel_subgraphs"
    return "direct_executor"


def direct_executor(state: GraphState) -> GraphState:
    """Direct execution path without subgraph."""
    time.sleep(2)
    return {
        "status": "direct_executed",
        "results": ["Direct execution result"],
        "current_step": "validation",
        "execution_path": "direct"
    }


async def parallel_subgraphs(state: GraphState) -> GraphState:
    """Execute multiple subgraph instances in parallel with event streaming."""
    subgraph_count = state.get("subgraph_count", 1)
    subgraph_template = create_subgraph()
    
    # Collect custom events to return in output
    custom_events = []
    
    # Emit subgraph start events for each instance
    for i in range(subgraph_count):
        subgraph_id = f"parallel_subgraphs_{i+1}"
        custom_events.append({"type": "subgraph_started", "data": {"node_id": subgraph_id}})
        custom_events.append({"type": "node_started", "data": {"node_id": subgraph_id}})
    
    # Create and execute subgraph instances in parallel
    async def execute_subgraph_instance(index: int):
        """Execute a single subgraph instance with event streaming."""
        subgraph_id = f"parallel_subgraphs_{index+1}"
        subgraph_input = {
            "status": "started",
            "task_results": [],
            "current_task": "task_1"
        }
        
        # Manually emit events for subgraph internal nodes
        tasks_nodes = ["task_1", "task_2", "task_3", "subgraph_aggregator"]
        for task_node in tasks_nodes:
            full_node_id = f"{subgraph_id}.{task_node}"
            custom_events.append({"type": "node_started", "data": {"node_id": full_node_id, "parent": subgraph_id}})
            await asyncio.sleep(1)  # Simulate task execution
            custom_events.append({"type": "node_completed", "data": {"node_id": full_node_id, "parent": subgraph_id}})
        
        return {"task_results": [f"{subgraph_id} completed"]}
    
    # Execute all subgraph instances in parallel
    tasks = [execute_subgraph_instance(i) for i in range(subgraph_count)]
    results = await asyncio.gather(*tasks)
    
    # Emit subgraph completion events
    for i in range(subgraph_count):
        subgraph_id = f"parallel_subgraphs_{i+1}"
        custom_events.append({"type": "subgraph_completed", "data": {"node_id": subgraph_id}})
        custom_events.append({"type": "node_completed", "data": {"node_id": subgraph_id}})
    
    # Aggregate results from all subgraphs
    all_results = []
    for i, result in enumerate(results):
        all_results.extend(result.get("task_results", []))
    
    return {
        "status": "parallel_subgraphs_completed",
        "results": all_results,
        "current_step": "validation",
        "execution_path": "parallel",
        "__custom__": custom_events  # Embed custom events in output for FlowRecorder to capture
    }


def analyzer_node(state: GraphState) -> GraphState:
    """Analyze results from execution."""
    time.sleep(1.5)
    return {
        "status": "analyzed",
        "results": state.get("results", []) + ["Analysis complete"],
        "current_step": "validation",
        "execution_path": "analyzed"
    }


def validator_node(state: GraphState) -> GraphState:
    """Validate results."""
    time.sleep(1)
    return {
        "status": "validated",
        "results": state.get("results", []) + ["Validation passed"],
        "current_step": "output",
        "execution_path": "validated"
    }


def output_formatter(state: GraphState) -> GraphState:
    """Format final output with streaming text."""
    stream_writer = get_stream_writer()
    
    # Emit dummy text chunks
    dummy_text = [
        "Processing complete.",
        "The workflow executed successfully through all nodes.",
        "Research subgraph completed 4 tasks.",
        "Analysis and validation passed.",
        "Final output has been formatted and ready.",
        "Thank you for using the LangGraph Flow system."
    ]
    
    for chunk in dummy_text:
        time.sleep(0.3)
        stream_writer({"type": "text_chunk", "content": chunk})
    
    return {
        "status": "completed",
        "results": state.get("results", []) + ["Output formatted"],
        "current_step": "done",
        "execution_path": "finished"
    }


def create_workflow() -> StateGraph:
    """Create and compile the complex LangGraph workflow with parallel subgraphs."""
    workflow = StateGraph(GraphState)
    
    # Add main graph nodes
    workflow.add_node("input_processor", input_processor)
    workflow.add_node("planner", planner_node)
    workflow.add_node("parallel_subgraphs", parallel_subgraphs)
    workflow.add_node("direct_executor", direct_executor)
    workflow.add_node("analyzer", analyzer_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("output_formatter", output_formatter)
    
    # Add edges
    workflow.add_edge(START, "input_processor")
    workflow.add_edge("input_processor", "planner")
    
    # Conditional routing from planner
    workflow.add_conditional_edges(
        "planner",
        route_decision,
        {
            "parallel_subgraphs": "parallel_subgraphs",
            "direct_executor": "direct_executor"
        }
    )
    
    # Both paths converge at analyzer
    workflow.add_edge("parallel_subgraphs", "analyzer")
    workflow.add_edge("direct_executor", "analyzer")
    
    # Continue through validation and output
    workflow.add_edge("analyzer", "validator")
    workflow.add_edge("validator", "output_formatter")
    workflow.add_edge("output_formatter", END)
    
    return workflow.compile()
