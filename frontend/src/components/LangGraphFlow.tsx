import { useEffect, useCallback, useRef, useState } from 'react';
import {
  ReactFlow,
  type Node,
  type Edge,
  Background,
  Controls,
  useReactFlow,
  ReactFlowProvider,
  type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import CustomNode from './CustomNode';
import type { GraphTopology, VisualizationEvent, NodeStatus, EdgeStatus } from '../types';

const nodeTypes: NodeTypes = {
  custom: CustomNode,
};

interface LangGraphFlowProps {
  graphEndpoint: string;
  streamEndpoint: string;
  threadId?: string;
  runEndpoint?: string;
}

function LangGraphFlowInner({ graphEndpoint, streamEndpoint, threadId, runEndpoint }: LangGraphFlowProps) {
  const { fitView, setCenter } = useReactFlow();
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [localThreadId, setLocalThreadId] = useState<string | undefined>(threadId);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Replace Zustand store with local state
  const [nodeStates, setNodeStates] = useState<Map<string, NodeStatus>>(new Map());
  const [edgeStates, setEdgeStates] = useState<Map<string, EdgeStatus>>(new Map());
  const [activeNodes, setActiveNodes] = useState<Set<string>>(new Set());
  const [isRunning, setIsRunning] = useState(false);

  const updateNodeStatus = useCallback((nodeId: string, status: NodeStatus) => {
    setNodeStates(prev => new Map(prev).set(nodeId, status));
  }, []);

  const setActiveNode = useCallback((nodeId: string) => {
    setActiveNodes(prev => new Set(prev).add(nodeId));
  }, []);

  const removeActiveNode = useCallback((nodeId: string) => {
    setActiveNodes(prev => {
      const newSet = new Set(prev);
      newSet.delete(nodeId);
      return newSet;
    });
  }, []);

  const reset = useCallback(() => {
    setNodeStates(new Map());
    setEdgeStates(new Map());
    setActiveNodes(new Set());
    setIsRunning(false);
  }, []);

  const handleEvent = useCallback((event: VisualizationEvent) => {
    const typeLower = String(event.type).toLowerCase();

    switch (typeLower) {
      case 'graphstarted':
      case 'graph_started':
        setIsRunning(true);
        break;

      case 'graphcompleted':
      case 'graph_completed':
        setIsRunning(false);
        setActiveNodes(new Set());
        break;

      case 'nodestarted':
      case 'node_started':
      case 'subgraphstarted':
      case 'subgraph_started': {
        const nodeId = event.node_id || event.data?.node_id;
        if (nodeId) {
          updateNodeStatus(nodeId, 'running');
          setActiveNode(nodeId);
        }
        break;
      }

      case 'nodecompleted':
      case 'node_completed':
      case 'subgraphcompleted':
      case 'subgraph_completed': {
        const nodeId = event.node_id || event.data?.node_id;
        if (nodeId) {
          updateNodeStatus(nodeId, 'completed');
          removeActiveNode(nodeId);
        }
        break;
      }

      case 'error': {
        const nodeId = event.node_id || event.data?.node_id;
        if (nodeId) {
          updateNodeStatus(nodeId, 'failed');
          removeActiveNode(nodeId);
        }
        break;
      }
    }
  }, [updateNodeStatus, setActiveNode, removeActiveNode]);

  useEffect(() => {
    fetch(graphEndpoint)
      .then((res) => res.json())
      .then((data: GraphTopology) => {
        const layoutNodes: Node[] = data.nodes.map((node, index) => ({
          ...node,
          id: node.id,
          type: 'custom',
          data: {
            ...node,
            label: node.label ?? node.id,
            status: 'idle' as const,
          },
          position: node.position ?? { x: 250, y: index * 150 },
        }));

        setNodes(layoutNodes);

        const layoutEdges: Edge[] = data.edges.map((edge) => ({
          ...edge,
          type: 'smoothstep',
          animated: false,
          style: { stroke: '#cbd5e1', strokeWidth: 2 },
        }));

        setEdges(layoutEdges);

        setTimeout(() => fitView({ padding: 0.2 }), 100);
      })
      .catch(console.error);
  }, [graphEndpoint, fitView]);

  useEffect(() => {
    const effectiveThreadId = threadId || localThreadId;
    if (!effectiveThreadId || !streamEndpoint) return;

    reset();
    setIsRunning(true);

    const separator = streamEndpoint.includes('?') ? '&' : '?';
    const url = `${streamEndpoint}${separator}thread_id=${encodeURIComponent(effectiveThreadId)}`;
    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      try {
        const data: VisualizationEvent = JSON.parse(event.data);
        handleEvent(data);

        if (data.type === 'graph_completed' || data.type === 'GraphCompleted') {
          setIsRunning(false);
          eventSource.close();
        }
      } catch (e) {
        console.error('Failed to parse event:', e);
      }
    };

    eventSource.onerror = (error) => {
      console.error('SSE error:', error);
      eventSource.close();
      setIsRunning(false);
    };

    return () => {
      eventSource.close();
    };
  }, [threadId, localThreadId, streamEndpoint, handleEvent, reset]);

  useEffect(() => {
    setNodes((prevNodes) =>
      prevNodes.map((node) => {
        const status = nodeStates.get(node.id) || 'idle';
        return {
          ...node,
          data: {
            ...node.data,
            status,
          },
        };
      })
    );
  }, [nodeStates]);

  useEffect(() => {
    setEdges((prevEdges) =>
      prevEdges.map((edge) => {
        const status = edgeStates.get(edge.id) || 'idle';
        const isActive = status === 'active';
        const isCompleted = status === 'completed';

        return {
          ...edge,
          animated: isActive,
          style: {
            stroke: isCompleted ? '#22c55e' : isActive ? '#3b82f6' : '#cbd5e1',
            strokeWidth: 2,
          },
        };
      })
    );
  }, [edgeStates]);

  useEffect(() => {
    if (!isRunning || activeNodes.size === 0) return;

    const activeNodeIds = Array.from(activeNodes);
    const activeNodesData = nodes.filter((n) => activeNodeIds.includes(n.id));

    if (activeNodesData.length === 1) {
      const node = activeNodesData[0];
      setCenter(node.position.x, node.position.y, { zoom: 1.2, duration: 800 });
    } else if (activeNodesData.length > 1) {
      fitView({ padding: 0.2, duration: 800 });
    }
  }, [activeNodes, isRunning, nodes, fitView, setCenter]);

  const handleRun = useCallback(async () => {
    const newThreadId = `thread_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    setLocalThreadId(newThreadId);
    reset();

    try {
      const runUrl = runEndpoint || 'http://localhost:8000/demo/run';
      await fetch(runUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ thread_id: newThreadId }),
      });
    } catch (e) {
      console.error('Failed to start graph:', e);
    }
  }, [runEndpoint, reset]);

  return (
    <div className="w-full h-screen bg-gray-50">
      <div className="absolute top-4 left-4 z-10">
        <button
          onClick={handleRun}
          disabled={isRunning}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
        >
          {isRunning ? 'Running...' : 'Run Graph'}
        </button>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        zoomOnScroll={false}
        panOnScroll={false}
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}

export default function LangGraphFlow(props: LangGraphFlowProps) {
  return (
    <ReactFlowProvider>
      <LangGraphFlowInner {...props} />
    </ReactFlowProvider>
  );
}
