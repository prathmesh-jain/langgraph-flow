from typing import TypedDict, Annotated, List
from operator import add


def replace_left(x, y):
    """Reducer that takes the left (first) value - for concurrent updates."""
    return x


def replace_right(x, y):
    """Reducer that takes the right (second) value - for concurrent updates."""
    return y


class GraphState(TypedDict):
    """State for the main workflow."""
    status: Annotated[str, replace_right]
    plan: List[str]
    current_step: Annotated[str, replace_right]
    results: Annotated[List[str], add]
    execution_path: Annotated[str, replace_right]
    subgraph_count: int


class SubgraphState(TypedDict):
    """State for the subgraph."""
    status: str
    task_results: List[str]
    current_task: str
