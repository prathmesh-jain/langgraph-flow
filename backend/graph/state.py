from typing import TypedDict, Annotated, List
from operator import add


class GraphState(TypedDict):
    """State for the main workflow."""
    status: str
    plan: List[str]
    current_step: str
    results: List[str]
    execution_path: str


class SubgraphState(TypedDict):
    """State for the subgraph."""
    status: str
    task_results: List[str]
    current_task: str
