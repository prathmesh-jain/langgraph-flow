import { create } from 'zustand';
import type { NodeStatus, EdgeStatus, VisualizationEvent } from './types';

interface GraphStore {
  nodeStates: Map<string, NodeStatus>;
  edgeStates: Map<string, EdgeStatus>;
  activeNodes: Set<string>;
  isRunning: boolean;

  updateNodeStatus: (nodeId: string, status: NodeStatus) => void;
  updateEdgeStatus: (edgeId: string, status: EdgeStatus) => void;
  setActiveNode: (nodeId: string) => void;
  removeActiveNode: (nodeId: string) => void;
  setRunning: (running: boolean) => void;
  reset: () => void;
  handleEvent: (event: VisualizationEvent) => void;
}

function extractNodeId(event: VisualizationEvent): string | undefined {
  if (event.node_id) return event.node_id;
  if (event.data?.node_id) return event.data.node_id;
  return undefined;
}

export const useGraphStore = create<GraphStore>((set) => ({
  nodeStates: new Map(),
  edgeStates: new Map(),
  activeNodes: new Set(),
  isRunning: false,

  updateNodeStatus: (nodeId, status) =>
    set((state) => {
      const newMap = new Map(state.nodeStates);
      newMap.set(nodeId, status);
      return { nodeStates: newMap };
    }),

  updateEdgeStatus: (edgeId, status) =>
    set((state) => {
      const newMap = new Map(state.edgeStates);
      newMap.set(edgeId, status);
      return { edgeStates: newMap };
    }),

  setActiveNode: (nodeId) =>
    set((state) => {
      const newSet = new Set(state.activeNodes);
      newSet.add(nodeId);
      return { activeNodes: newSet };
    }),

  removeActiveNode: (nodeId) =>
    set((state) => {
      const newSet = new Set(state.activeNodes);
      newSet.delete(nodeId);
      return { activeNodes: newSet };
    }),

  setRunning: (running) => set({ isRunning: running }),

  reset: () =>
    set({
      nodeStates: new Map(),
      edgeStates: new Map(),
      activeNodes: new Set(),
      isRunning: false,
    }),

  handleEvent: (event) =>
    set((state) => {
      const newNodes = new Map(state.nodeStates);
      const newActive = new Set(state.activeNodes);
      const typeLower = String(event.type).toLowerCase();

      switch (typeLower) {
        case 'graphstarted':
        case 'graph_started':
          return { isRunning: true };

        case 'graphcompleted':
        case 'graph_completed':
          return { isRunning: false, activeNodes: new Set() };

        case 'nodestarted':
        case 'node_started':
        case 'subgraphstarted':
        case 'subgraph_started': {
          const nodeId = extractNodeId(event);
          if (nodeId) {
            newNodes.set(nodeId, 'running');
            newActive.add(nodeId);
          }
          return { nodeStates: newNodes, activeNodes: newActive };
        }

        case 'nodecompleted':
        case 'node_completed':
        case 'subgraphcompleted':
        case 'subgraph_completed': {
          const nodeId = extractNodeId(event);
          if (nodeId) {
            newNodes.set(nodeId, 'completed');
            newActive.delete(nodeId);
          }
          return { nodeStates: newNodes, activeNodes: newActive };
        }

        case 'error': {
          const nodeId = extractNodeId(event);
          if (nodeId) {
            newNodes.set(nodeId, 'failed');
            newActive.delete(nodeId);
          }
          return { nodeStates: newNodes, activeNodes: newActive };
        }

        default:
          return state;
      }
    }),
}));
