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
    time.sleep(3)
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
    time.sleep(3)
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


def create_analysis_subgraph() -> StateGraph:
    """Create the analysis subgraph."""
    subgraph = StateGraph(SubgraphState)
    
    subgraph.add_node("analysis_task_1", task_1_node)
    subgraph.add_node("analysis_task_2", task_2_node)
    subgraph.add_node("analysis_task_3", task_3_node)
    subgraph.add_node("analysis_aggregator", subgraph_aggregator)
    
    subgraph.add_edge(START, "analysis_task_1")
    subgraph.add_edge("analysis_task_1", "analysis_task_2")
    subgraph.add_edge("analysis_task_2", "analysis_task_3")
    subgraph.add_edge("analysis_task_3", "analysis_aggregator")
    subgraph.add_edge("analysis_aggregator", END)
    
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
    time.sleep(3)
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
    
    
    return {
        "status": "planned",
        "plan": plan,
        "current_step": "research",
        "execution_path": "planned",
        "subgraph_count": subgraph_count
    }


def route_decision(state: GraphState) -> list[str]:
    """Route to parallel subgraphs or direct execution based on plan."""
    if "research" in state.get("plan", []):
        # Return both subgraph nodes for parallel execution
        return ["research_subgraph", "analysis_subgraph"]
    return ["direct_executor"]


def direct_executor(state: GraphState) -> GraphState:
    """Direct execution path without subgraph."""
    time.sleep(3)
    return {
        "status": "direct_executed",
        "results": ["Direct execution result"],
        "current_step": "validation",
        "execution_path": "direct"
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
    time.sleep(3)
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
    # workflow.add_node("direct_executor", direct_executor)
    workflow.add_node("analyzer", analyzer_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("output_formatter", output_formatter)
    
    # Add compiled subgraphs as nodes for parallel execution
    # Note: These are actual compiled StateGraph objects that will be executed as subgraphs
    research_subgraph = create_subgraph()
    analysis_subgraph = create_analysis_subgraph()
    
    workflow.add_node("research_subgraph", research_subgraph)
    workflow.add_node("analysis_subgraph", analysis_subgraph)
    
    # Add edges
    workflow.add_edge(START, "input_processor")
    workflow.add_edge("input_processor", "planner")
    
    # Conditional routing from planner to parallel subgraphs
    workflow.add_conditional_edges(
        "planner",
        route_decision,
        {
            "research_subgraph": "research_subgraph",
            "analysis_subgraph": "analysis_subgraph",
            # "direct_executor": "direct_executor"
        }
    )
    
    # Both subgraph paths converge at analyzer
    workflow.add_edge("research_subgraph", "analyzer")
    workflow.add_edge("analysis_subgraph", "analyzer")
    # workflow.add_edge("direct_executor", "analyzer")
    
    # Continue through validation and output
    workflow.add_edge("analyzer", "validator")
    workflow.add_edge("validator", "output_formatter")
    workflow.add_edge("output_formatter", END)
    
    return workflow.compile()
