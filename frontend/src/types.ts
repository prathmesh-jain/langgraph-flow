export type NodeStatus = 'idle' | 'queued' | 'running' | 'completed' | 'failed';
export type EdgeStatus = 'idle' | 'active' | 'completed';

export type EventType =
  | 'GraphStarted'
  | 'GraphCompleted'
  | 'NodeStarted'
  | 'NodeCompleted';

export interface VisualizationEvent {
  type: EventType;
  timestamp: number;
  thread_id: string;
  run_id: string;
  node_id?: string;
}

export interface GraphNode {
  id: string;
  type: string;
  label: string;
  position: { x: number; y: number };
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  condition: string | null;
}

export interface GraphTopology {
  nodes: GraphNode[];
  edges: GraphEdge[];
  subgraphs: any[];
}

export interface NodeData extends GraphNode {
  status: NodeStatus;
}

export interface EdgeData extends GraphEdge {
  status: EdgeStatus;
}
