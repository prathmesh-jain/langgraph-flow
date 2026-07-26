import { useEffect, useCallback, useRef, useState } from 'react';
import ReactFlow, {
  type Node,
  type Edge,
  Background,
  Controls,
  useReactFlow,
  ReactFlowProvider,
  type NodeTypes,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { useGraphStore } from '../store';
import CustomNode from './CustomNode';
import type { GraphTopology, VisualizationEvent } from '../types';

const nodeTypes: NodeTypes = {
  custom: CustomNode,
};

interface LangGraphFlowProps {
  graphEndpoint: string;
  streamEndpoint: string;
  threadId?: string;
}

function LangGraphFlowInner({ graphEndpoint, streamEndpoint, threadId }: LangGraphFlowProps) {
  const { fitView, setCenter } = useReactFlow();
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const eventSourceRef = useRef<EventSource | null>(null);
  
  const { nodeStates, edgeStates, activeNodes, isRunning, handleEvent, reset } = useGraphStore();

  // Load graph topology
  useEffect(() => {
    fetch(graphEndpoint)
      .then((res) => res.json())
      .then((data: GraphTopology) => {
        
        // Auto-layout nodes in a simple vertical flow
        const layoutNodes = data.nodes.map((node, index) => ({
          ...node,
          type: 'custom',
          data: {
            ...node,
            status: 'idle' as const,
          },
          position: { x: 250, y: index * 150 },
        }));
        
        setNodes(layoutNodes);
        
        const layoutEdges = data.edges.map((edge) => ({
          ...edge,
          type: 'smoothstep',
          animated: false,
          style: { stroke: '#cbd5e1', strokeWidth: 2 },
        }));
        
        setEdges(layoutEdges);
        
        // Fit view after layout
        setTimeout(() => fitView({ padding: 0.2 }), 100);
      })
      .catch(console.error);
  }, [graphEndpoint, fitView]);

  // Connect to SSE stream
  useEffect(() => {
    if (!threadId || !streamEndpoint) return;

    reset();
    
    const url = `${streamEndpoint}/${threadId}`;
    const eventSource = new EventSource(url);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      try {
        const data: VisualizationEvent = JSON.parse(event.data);
        handleEvent(data);
      } catch (e) {
        console.error('Failed to parse event:', e);
      }
    };

    eventSource.onerror = (error) => {
      console.error('SSE error:', error);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [threadId, streamEndpoint, handleEvent, reset]);

  // Update node visual states based on store
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

  // Update edge visual states based on store
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

  // Camera control - focus on active nodes
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
    try {
      const response = await fetch('http://localhost:8000/demo/run', {
        method: 'POST',
      });
      const data = await response.json();
      window.location.href = `?thread_id=${data.thread_id}`;
    } catch (e) {
      console.error('Failed to start graph:', e);
    }
  }, []);

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
