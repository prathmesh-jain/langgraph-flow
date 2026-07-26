import { useState, useCallback, useEffect } from 'react';
import ReactFlow, {
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  addEdge,
  MarkerType,
} from 'reactflow';
import type { Node, Edge, Connection } from 'reactflow';
import 'reactflow/dist/style.css';

interface GraphTopology {
  nodes: Array<{ id: string; type: string }>;
  edges: Array<{ id: string; source: string; target: string }>;
}

// Plug-and-play graph visualization component
function GraphVisualization({ 
  showGraph, 
  nodeStatus,
  shouldLoadTopology 
}: { 
  showGraph: boolean; 
  nodeStatus: Record<string, string>;
  shouldLoadTopology: boolean;
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [topologyLoaded, setTopologyLoaded] = useState(false);

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge(params, eds)),
    [setEdges]
  );

  // Load graph topology from backend only when flow starts
  useEffect(() => {
    if (!showGraph || !shouldLoadTopology || topologyLoaded) return;

    const loadTopology = async () => {
      try {
        const response = await fetch('http://localhost:8000/demo/graph');
        const topology: GraphTopology = await response.json();
        
        // Define hierarchical layout positions based on workflow structure
        const layoutPositions: Record<string, { x: number; y: number }> = {
          'input_processor': { x: 400, y: 50 },
          'planner': { x: 400, y: 150 },
          'research_subgraph': { x: 250, y: 250 },
          'direct_executor': { x: 550, y: 250 },
          'analyzer': { x: 400, y: 350 },
          'validator': { x: 400, y: 450 },
          'output_formatter': { x: 400, y: 550 },
        };
        
        // Add START and END nodes if they're in edges but not in nodes
        const nodeIds = new Set(topology.nodes.map(n => n.id));
        const allNodes = [...topology.nodes];
        
        // Check if START/END are in edges but not in nodes
        topology.edges.forEach(edge => {
          if (edge.source === 'START' && !nodeIds.has('START')) {
            allNodes.push({ id: 'START', type: 'special' });
          }
          if (edge.target === 'END' && !nodeIds.has('END')) {
            allNodes.push({ id: 'END', type: 'special' });
          }
        });
        
        // Convert backend nodes to React Flow nodes with hierarchical layout
        const flowNodes: Node[] = allNodes.map((node) => {
          let position = layoutPositions[node.id];
          
          // Special positions for START and END
          if (node.id === 'START') {
            position = { x: 400, y: 50 };
          } else if (node.id === 'END') {
            position = { x: 400, y: 650 };
          } else if (!position) {
            position = { x: 100 + Math.random() * 600, y: 100 + Math.random() * 500 };
          }
          
          const status = nodeStatus[node.id];
          
          let backgroundColor = '#f3f4f6';
          let borderColor = '#d1d5db';
          let boxShadow = 'none';
          
          if (status === 'running') {
            backgroundColor = '#fef3c7';
            borderColor = '#f59e0b';
            boxShadow = '0 0 20px rgba(245, 158, 11, 0.5)';
          } else if (status === 'completed') {
            backgroundColor = '#dcfce7';
            borderColor = '#22c55e';
          }
          
          return {
            id: node.id,
            type: 'default',
            data: { label: node.id },
            position,
            style: {
              background: backgroundColor,
              border: '2px solid',
              borderColor,
              width: 180,
              height: 50,
              boxShadow,
              transition: 'all 0.3s ease',
            },
          };
        });

        // Convert backend edges to React Flow edges (preserve backend connections)
        const flowEdges: Edge[] = topology.edges.map(edge => {
          const sourceStatus = nodeStatus[edge.source];
          const targetStatus = nodeStatus[edge.target];
          
          // Animate edge if source is running or both are completed
          const isAnimated = sourceStatus === 'running' || (sourceStatus === 'completed' && targetStatus === 'completed');
          
          // Color based on execution state
          let strokeColor = '#9ca3af';
          let strokeWidth = 2;
          
          if (sourceStatus === 'running') {
            strokeColor = '#f59e0b';
            strokeWidth = 3;
          } else if (sourceStatus === 'completed' && targetStatus === 'completed') {
            strokeColor = '#22c55e';
          }
          
          return {
            id: edge.id,
            source: edge.source,
            target: edge.target,
            markerEnd: { type: MarkerType.ArrowClosed },
            animated: isAnimated,
            style: {
              stroke: strokeColor,
              strokeWidth,
              transition: 'all 0.3s ease',
            },
          };
        });

        setNodes(flowNodes);
        setEdges(flowEdges);
        setTopologyLoaded(true);
      } catch (e) {
        console.error('Failed to load graph topology:', e);
      }
    };

    loadTopology();
  }, [showGraph, shouldLoadTopology, topologyLoaded, nodeStatus, setNodes, setEdges]);

  // Update node and edge styles when status changes
  useEffect(() => {
    if (!topologyLoaded) return;

    setNodes((nds) => 
      nds.map((node) => {
        const status = nodeStatus[node.id];
        let backgroundColor = '#f3f4f6';
        let borderColor = '#d1d5db';
        let boxShadow = 'none';
        
        if (status === 'running') {
          backgroundColor = '#fef3c7';
          borderColor = '#f59e0b';
          boxShadow = '0 0 20px rgba(245, 158, 11, 0.5)';
        } else if (status === 'completed') {
          backgroundColor = '#dcfce7';
          borderColor = '#22c55e';
        }
        
        return {
          ...node,
          style: {
            background: backgroundColor,
            border: '2px solid',
            borderColor,
            width: 180,
            height: 50,
            boxShadow,
            transition: 'all 0.3s ease',
          },
        };
      })
    );

    setEdges((eds) =>
      eds.map((edge) => {
        const sourceStatus = nodeStatus[edge.source];
        const targetStatus = nodeStatus[edge.target];
        
        const isAnimated = sourceStatus === 'running' || (sourceStatus === 'completed' && targetStatus === 'completed');
        let strokeColor = '#9ca3af';
        let strokeWidth = 2;
        
        if (sourceStatus === 'running') {
          strokeColor = '#f59e0b';
          strokeWidth = 3;
        } else if (sourceStatus === 'completed' && targetStatus === 'completed') {
          strokeColor = '#22c55e';
        }
        
        return {
          ...edge,
          animated: isAnimated,
          style: {
            stroke: strokeColor,
            strokeWidth,
            transition: 'all 0.3s ease',
          },
        };
      })
    );
  }, [nodeStatus, topologyLoaded, setNodes, setEdges]);

  if (!showGraph) return null;

  return (
    <div className="h-[600px] bg-white rounded-lg shadow-md border">
      {topologyLoaded ? (
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      ) : (
        <div className="h-full flex items-center justify-center">
          <p className="text-gray-500">Graph will load when execution starts...</p>
        </div>
      )}
    </div>
  );
}

function App() {
  const [nodeStatus, setNodeStatus] = useState<Record<string, string>>({});
  const [streamedText, setStreamedText] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [showGraph] = useState(true); // Set to false to disable graph visualization
  const [shouldLoadTopology, setShouldLoadTopology] = useState(false);
  const [threadId, setThreadId] = useState<string>('');

  const handleRun = async () => {
    // Generate unique thread_id for this execution
    const newThreadId = `thread_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    setThreadId(newThreadId);
    
    setLoading(true);
    setNodeStatus({});
    setStreamedText('');
    setShouldLoadTopology(true); // Trigger graph topology load when flow starts
    try {
      // Run graph and stream both events and output in real-time
      const response = await fetch('http://localhost:8000/demo/run', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ thread_id: newThreadId }),
      });
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              try {
                const parsed = JSON.parse(data);
                
                // Handle node started events
                if (parsed.type === 'node_started') {
                  const nodeId = parsed.node_id;
                  if (nodeId) {
                    setNodeStatus(prev => ({
                      ...prev,
                      [nodeId]: 'running'
                    }));
                  }
                }
                // Handle node completed events
                else if (parsed.type === 'node_completed') {
                  const nodeId = parsed.node_id;
                  if (nodeId) {
                    setNodeStatus(prev => ({
                      ...prev,
                      [nodeId]: 'completed'
                    }));
                  }
                }
                // Handle output text chunks
                else if (parsed.content) {
                  setStreamedText(prev => prev + parsed.content + '\n');
                }
              } catch (e) {
                console.error('Failed to parse SSE data:', e);
              }
            }
          }
        }
      }
    } catch (e) {
      console.error('Failed to run graph:', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <div className="bg-white p-4 shadow-md">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <h1 className="text-2xl font-bold">LangGraph Demo</h1>
          <button
            onClick={handleRun}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
          >
            {loading ? 'Running...' : 'Run Graph'}
          </button>
        </div>
      </div>

      <div className="flex-1 p-4">
        <div className="max-w-7xl mx-auto h-full">
          <GraphVisualization 
            showGraph={showGraph} 
            nodeStatus={nodeStatus}
            shouldLoadTopology={shouldLoadTopology}
          />

          {streamedText && (
            <div className="mt-4 p-4 bg-white rounded-lg shadow-md border">
              <h2 className="text-lg font-semibold mb-2">Streaming Output:</h2>
              <pre className="whitespace-pre-wrap text-sm">{streamedText}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;
