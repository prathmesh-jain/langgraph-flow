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
      
      switch (event.type) {
        case 'GraphStarted':
          return { isRunning: true };
        
        case 'GraphCompleted':
          return { isRunning: false, activeNodes: new Set() };
        
        case 'NodeStarted':
          if (event.node_id) {
            newNodes.set(event.node_id, 'running');
            newActive.add(event.node_id);
          }
          return { nodeStates: newNodes, activeNodes: newActive };
        
        case 'NodeCompleted':
          if (event.node_id) {
            newNodes.set(event.node_id, 'completed');
            newActive.delete(event.node_id);
          }
          return { nodeStates: newNodes, activeNodes: newActive };
        
        default:
          return state;
      }
    }),
}));
