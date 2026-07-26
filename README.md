# LangGraph Flow Visualization

A proof-of-concept for a reusable LangGraph Flow Visualization library designed as an OSS package.

## Architecture

This project follows a **layered adapter pattern** with strict separation of concerns:

```
Application Layer (User's business logic - unchanged)
         ↓
LangGraph Runtime (Native LangGraph execution - no modifications)
         ↓
Visualization Adapter Layer (Transforms native LangGraph events)
         ↓
API Layer (FastAPI - exposes graph topology and event streams)
         ↓
React Flow Visualization Layer (Pure UI component - no business logic)
```

## Key Design Principle: Zero User Code Changes

**This system works with ANY existing LangGraph without requiring custom event schemas in user code.**

The backend uses LangGraph's native `astream()` API with `version="v2"` and `stream_mode="updates"`. This means:

- **No custom event schemas** in your LangGraph nodes
- **No modifications** to existing business logic
- **No special callbacks** or instrumentation needed
- Just add the visualization layer as an optional add-on

## Design Principles

1. **Non-Invasive** - Uses LangGraph's public APIs only, no modifications to LangGraph internals or user code
2. **Reusable** - Visualization layer is completely decoupled from agent implementation
3. **Extensible** - Easy to add new event types and visualizations
4. **Production-Ready** - Proper error handling, async execution, type safety

## Backend Structure

```
backend/
├── app.py              # FastAPI application entry
├── requirements.txt    # Python dependencies
└── graph/
    ├── workflow.py     # LangGraph definition with deterministic nodes
    ├── state.py        # TypedDict state definition
    └── routers.py      # API route handlers with event transformation
```

### LangGraph Native API Usage

- **Graph Definition**: `StateGraph`, `add_node`, `add_edge`
- **Graph Compilation**: `workflow.compile()`
- **Graph Topology**: `app.get_graph()` to extract nodes/edges
- **Event Streaming**: `astream(version="v2", stream_mode=["updates"])` - Native LangGraph streaming
- **Async Execution**: Background task execution

### Adapter Layer

The backend includes a **single transformation function** that converts LangGraph's native `StreamPart` events to visualization events:

```python
def transform_langgraph_event(part: StreamPart, thread_id: str, run_id: str) -> dict | None:
    """Transform LangGraph's native StreamPart to visualization event."""
    event_type = part["type"]
    data = part["data"]
    
    if event_type == "updates":
        for node_id, state_update in data.items():
            return {
                "type": "NodeCompleted",
                "node_id": node_id,
                "timestamp": asyncio.get_event_loop().time(),
                "thread_id": thread_id,
                "run_id": run_id,
            }
    return None
```

This is the **only** adapter needed. User code remains completely untouched.

### API Endpoints

- `POST /demo/run` - Start graph execution, returns `run_id` and `thread_id`
- `GET /demo/stream/{thread_id}` - SSE stream of execution events
- `GET /demo/graph` - Static graph topology (React Flow format)

## Frontend Structure

```
frontend/src/
├── components/
│   ├── LangGraphFlow.tsx   # Main visualization component
│   └── CustomNode.tsx       # Custom React Flow node
├── types.ts                 # TypeScript type definitions
├── store.ts                 # Zustand state management
├── utils.ts                 # Utility functions
└── App.tsx                  # Application entry
```

### Component Usage

```tsx
<LangGraphFlow
  graphEndpoint="http://localhost:8000/demo/graph"
  streamEndpoint="http://localhost:8000/demo/stream"
  threadId={threadId}
/>
```

### Visualization Features

- **Node States**: idle, queued, running, completed, failed
- **Animations**: Pulse for running nodes
- **Camera Controls**: Auto-fit graph, focus on running nodes

## Setup

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Running the Demo

1. Start the backend server: `uvicorn app:app --reload` (runs on port 8000)
2. Start the frontend dev server: `npm run dev` (runs on port 5173)
3. Open http://localhost:5173
4. Click "Run Graph" to start the workflow execution
5. Watch the real-time visualization of node execution

## Workflow

The demo workflow uses deterministic nodes with `time.sleep()`:

```
START → Planner (2s) → Executor (3s) → Validator (2s) → END
```

Each node returns `{"status": "done"}`.

## Event Schema

Visualization events are derived from LangGraph's native events:

- `GraphStarted` - Graph execution begins
- `GraphCompleted` - Graph execution finishes
- `NodeStarted` - Node begins execution (inferred from graph topology)
- `NodeCompleted` - Node finishes execution (from LangGraph's "updates" stream)

## Future Vision

This is designed to eventually become:

- `pip install langgraph-flow` - Backend package
- `npm install @langgraph-flow/react` - Frontend package

Users would only need:

```tsx
<LangGraphFlow
  graphEndpoint="/api/graph"
  streamEndpoint="/api/stream"
  threadId={threadId}
/>
```

And a couple of backend routes, with **zero changes to business logic**.
