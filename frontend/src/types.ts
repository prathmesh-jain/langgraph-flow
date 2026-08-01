export type NodeStatus = 'idle' | 'queued' | 'running' | 'completed' | 'failed';
export type EdgeStatus = 'idle' | 'active' | 'completed';

export type EventType =
  | 'GraphStarted'
  | 'GraphCompleted'
  | 'NodeStarted'
  | 'NodeCompleted'
  | 'graph_started'
  | 'graph_completed'
  | 'node_started'
  | 'node_completed'
  | 'subgraph_started'
  | 'subgraph_completed'
  | 'error';

export interface VisualizationEvent {
  type: EventType;
  timestamp?: number | string;
  thread_id?: string;
  run_id?: string;
  node_id?: string;
  data?: {
    node_id?: string;
    parent?: string;
    [key: string]: any;
  };
  [key: string]: any;
}

export interface GraphNode {
  id: string;
  type: string;
  parent?: string;
  label?: string;
  position?: { x: number; y: number };
  [key: string]: any;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  subgraph?: string;
  condition?: string | null;
  [key: string]: any;
}

export interface GraphTopology {
  nodes: GraphNode[];
  edges: GraphEdge[];
  subgraph_nodes?: GraphNode[];
  subgraphs?: any[];
  subgraph_templates?: Record<string, any>;
  parallel_execution_nodes?: string[];
  [key: string]: any;
}

export interface NodeData extends GraphNode {
  status: NodeStatus;
}

export interface EdgeData extends GraphEdge {
  status: EdgeStatus;
}
