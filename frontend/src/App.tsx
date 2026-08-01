import { useState, useCallback, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  useNodesState,
  useEdgesState,
  addEdge,
  MarkerType,
} from '@xyflow/react';
import type { Node, Edge, Connection } from '@xyflow/react';
import '@xyflow/react/dist/style.css';

interface GraphTopology {
  nodes: Array<{ id: string; type: string; parent?: string }>;
  edges: Array<{ id: string; source: string; target: string; subgraph?: string }>;
  subgraph_nodes?: Array<{ id: string; parent?: string }>;
}

// Automatic layout algorithm for hierarchical graph
function computeLayout(
  nodes: Array<{ id: string; parent?: string; type?: string }>,
  edges: Array<{ source: string; target: string }>,
  expandedSubgraphs: Set<string> = new Set()
): Record<string, { x: number; y: number }> {


  // Separate main graph nodes from subgraph nodes
  const mainNodes = nodes.filter(n => !n.parent);
  const subgraphNodes = nodes.filter(n => n.parent);

  console.log("========== NEW LAYOUT ==========");
  console.log("Expanded:", [...expandedSubgraphs]);

  console.log(
    "Subgraph node count:",
    subgraphNodes.length
  );

  console.log(
    "Nodes:",
    nodes.map(n => ({
      id: n.id,
      parent: n.parent
    }))
  );


  // Build adjacency list for main graph only
  const adjacency: Record<string, string[]> = {};
  const inDegree: Record<string, number> = {};

  mainNodes.forEach(node => {
    adjacency[node.id] = [];
    inDegree[node.id] = 0;
  });

  edges.forEach(edge => {
    // Only process main graph edges (skip subgraph internal edges)
    if (!edge.source.includes('.') && !edge.target.includes('.')) {
      if (adjacency[edge.source]) {
        adjacency[edge.source].push(edge.target);
      }
      if (inDegree[edge.target] !== undefined) {
        inDegree[edge.target]++;
      }
    }
  });

  // Topological sort with layering
  const layers: string[][] = [];
  const visited = new Set<string>();
  const queue: string[] = [];

  // Start with nodes that have no incoming edges (or START)
  mainNodes.forEach(node => {
    if (inDegree[node.id] === 0 || node.id === 'START') {
      queue.push(node.id);
      visited.add(node.id);
    }
  });

  while (queue.length > 0) {
    const currentLayer: string[] = [];
    const layerSize = queue.length;

    for (let i = 0; i < layerSize; i++) {
      const node = queue.shift()!;
      currentLayer.push(node);

      // Add neighbors to next layer
      if (adjacency[node]) {
        adjacency[node].forEach(neighbor => {
          if (!visited.has(neighbor)) {
            visited.add(neighbor);
            queue.push(neighbor);
          }
        });
      }
    }

    if (currentLayer.length > 0) {
      layers.push(currentLayer);
    }
  }

  // Add any remaining nodes (for disconnected graphs or cycles)
  mainNodes.forEach(node => {
    if (!visited.has(node.id)) {
      layers.push([node.id]);
    }
  });


  // Calculate positions based on layers
  const positions: Record<string, { x: number; y: number }> = {};
  const layerHeight = 100;
  const baseNodeWidth = 180;
  const nodeGap = 50;
  const canvasWidth = 1200; // Increased canvas width
  const parentGap = 60;
  const nodeSpacing = 60;
  const bottomPadding = 30;

  // Calculate dynamic node widths based on label length
  const nodeWidths: Record<string, number> = {};
  nodes.forEach(node => {
    const label = node.type === 'subgraph' ? node.id.split('.')[1] || node.id : node.id;
    const labelLength = label.length;
    nodeWidths[node.id] = Math.max(baseNodeWidth, Math.min(labelLength * 8 + 40, 300));
  });


  // Find which layer contains expanded subgraphs and calculate required spacing
  const expandedSubgraphLayers = new Set<number>();
  const subgraphNodeCounts: Record<number, number> = {};
  console.log("Layers:", layers);
  layers.forEach((layer, layerIndex) => {
    layer.forEach(nodeId => {
      if (expandedSubgraphs.has(nodeId)) {
        expandedSubgraphLayers.add(layerIndex);
        // Count subgraph internal nodes for this parent
        const count = subgraphNodes.filter(n => n.parent === nodeId).length;
        subgraphNodeCounts[layerIndex] = (subgraphNodeCounts[layerIndex] || 0) + count;
      }
    });
  });

  layers.forEach((layer, layerIndex) => {
    // Calculate layer width using dynamic node widths
    let layerWidth = 0;
    layer.forEach((nodeId, index) => {
      layerWidth += nodeWidths[nodeId] || baseNodeWidth;
      if (index < layer.length - 1) layerWidth += nodeGap;
    });
    const startX = (canvasWidth - layerWidth) / 2 + (nodeWidths[layer[0]] || baseNodeWidth) / 2; // Center horizontally

    // Calculate Y position with dynamic spacing
    let y = 50;
    for (let i = 0; i < layerIndex; i++) {
      if (expandedSubgraphLayers.has(i)) {
        // Add extra space after expanded subgraph layer based on total node count
        const nodeCount = subgraphNodeCounts[i] || 0;

        const extraSpace =
          parentGap +
          Math.max(0, nodeCount - 1) * nodeSpacing +
          bottomPadding; // Space for linear subgraph layout
        y += layerHeight + extraSpace;
      } else {
        y += layerHeight;
      }
    }

    layer.forEach((nodeId, nodeIndex) => {
      // Calculate X position using dynamic node widths
      let currentX = startX;
      for (let i = 0; i < nodeIndex; i++) {
        currentX += (nodeWidths[layer[i]] || baseNodeWidth) + nodeGap;
      }
      positions[nodeId] = {
        x: currentX,
        y: y
      };
    });
  });

  // Position subgraph nodes in a linear layout below their parent
  // Handle multiple parallel subgraphs by offsetting them horizontally
  const parallelSubgraphParents = new Set<string>();
  subgraphNodes.forEach(subNode => {
    if (subNode.parent) parallelSubgraphParents.add(subNode.parent);
  });

  const parentXOffsets: Record<string, number> = {};
  let xOffset = 0;
  // Sort parent IDs to ensure consistent ordering
  const sortedParentIds = Array.from(parallelSubgraphParents).sort();
  sortedParentIds.forEach(parentId => {
    parentXOffsets[parentId] = xOffset;
    xOffset += 200; // Offset each parallel subgraph by 200px for better spacing
  });

  // First, ensure parent nodes have positions (for dynamically created parents)
  sortedParentIds.forEach(parentId => {
    if (!positions[parentId]) {
      console.log('[computeLayout] Parent node not in positions:', parentId);

      // For parallel_subgraphs_X nodes, position them in the layer after planner
      // This is based on the workflow structure: planner -> parallel_subgraphs -> analyzer
      if (parentId.startsWith('parallel_subgraphs_')) {
        const plannerLayerIndex = layers.findIndex(layer => layer.includes('planner'));
        if (plannerLayerIndex >= 0) {
          const layerIndex = plannerLayerIndex + 1;
          const layerWidth = baseNodeWidth + nodeGap;
          const startX = (canvasWidth - layerWidth) / 2 + baseNodeWidth / 2;

          let y = 50;
          for (let i = 0; i < layerIndex; i++) {
            y += layerHeight;
          }

          positions[parentId] = {
            x: startX + (parentXOffsets[parentId] || 0),
            y: y
          };
          console.log('[computeLayout] Positioned parallel_subgraphs parent at layer:', layerIndex, parentId, positions[parentId]);
        } else {
          // Fallback if planner not found
          positions[parentId] = {
            x: canvasWidth / 2 + (parentXOffsets[parentId] || 0),
            y: 150
          };
          console.log('[computeLayout] Positioned parallel_subgraphs parent at fallback:', parentId, positions[parentId]);
        }
      } else {
        // For other dynamic parent nodes, try edge-based positioning
        const connectedEdge = edges.find(e => e.target === parentId || e.source === parentId);
        if (connectedEdge) {
          const connectedNodeId = connectedEdge.source === parentId ? connectedEdge.target : connectedEdge.source;
          const targetLayerIndex = layers.findIndex(layer => layer.includes(connectedNodeId));

          if (targetLayerIndex >= 0) {
            const layerIndex = targetLayerIndex;
            const layerWidth = baseNodeWidth + nodeGap;
            const startX = (canvasWidth - layerWidth) / 2 + baseNodeWidth / 2;

            let y = 50;
            for (let i = 0; i < layerIndex; i++) {
              y += layerHeight;
            }

            positions[parentId] = {
              x: startX + (parentXOffsets[parentId] || 0),
              y: y
            };
            console.log('[computeLayout] Positioned parent at layer:', layerIndex, parentId, positions[parentId]);
          } else {
            // Fallback: position at the end of the graph
            const lastLayerY = layers.length * layerHeight + 50;
            positions[parentId] = {
              x: canvasWidth / 2 + (parentXOffsets[parentId] || 0),
              y: lastLayerY
            };
            console.log('[computeLayout] Positioned parent at fallback:', parentId, positions[parentId]);
          }
        } else {
          // Fallback: position at the end of the graph
          const lastLayerY = layers.length * layerHeight + 50;
          positions[parentId] = {
            x: canvasWidth / 2 + (parentXOffsets[parentId] || 0),
            y: lastLayerY
          };
          console.log('[computeLayout] Positioned parent at fallback:', parentId, positions[parentId]);
        }
      }
    }
  });

  // Position subgraph nodes directly below their parent
  sortedParentIds.forEach(parentId => {
    const parentPos = positions[parentId];
    if (!parentPos) {
      console.log('[computeLayout] Parent has no position, skipping subgraph nodes:', parentId);
      return;
    }

    const parentSubgraphNodes = subgraphNodes.filter(n => n.parent === parentId);
    console.log('[computeLayout] Positioning subgraph nodes for parent:', parentId, 'count:', parentSubgraphNodes.length);
    console.log(
      "Parent layout position:",
      parentPos
    );
    parentSubgraphNodes.forEach((subNode, index) => {
      if (expandedSubgraphs.has(parentId)) {
        // Position directly below parent with vertical spacing
        const offsetY = (index + 1) * nodeSpacing; // 60px spacing between subgraph nodes
        console.log('[computeLayout] Expanded index:', index, 'offsetY:', offsetY);
        positions[subNode.id] = {
          x: parentPos.x, // Same X position as parent
          y: parentPos.y + offsetY
        };
        console.log('[computeLayout] Positioned subgraph node:', subNode.id, positions[subNode.id]);
      }
    });
  });

  console.log('[computeLayout] Final positions:', positions);
  console.log(
    "RETURNING",
    JSON.stringify(positions, null, 2)
  );
  return positions;
}

// Plug-and-play graph visualization component
function GraphVisualization({
  showGraph,
  nodeStatus,
  shouldLoadTopology,
  autoExpandSubgraphs
}: {
  showGraph: boolean;
  nodeStatus: Record<string, string>;
  shouldLoadTopology: boolean;
  autoExpandSubgraphs: boolean;
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [topologyLoaded, setTopologyLoaded] = useState(false);
  const [expandedSubgraphs, setExpandedSubgraphs] = useState<Set<string>>(new Set());
  const [topology, setTopology] = useState<GraphTopology | null>(null);
  const [dynamicNodes, setDynamicNodes] = useState<any[]>([]);
  const [dynamicEdges, setDynamicEdges] = useState<any[]>([]);

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

        console.log('Received topology:', topology);
        console.log('Subgraph nodes:', topology.subgraph_nodes);

        // Store topology for dynamic node creation
        setTopology(topology);

        // Use automatic layout algorithm based on backend topology
        const layoutPositions = computeLayout(topology.nodes, topology.edges, expandedSubgraphs);

        // Filter nodes based on expanded subgraphs
        const visibleNodes = topology.nodes.filter(node => {
          if (node.type === 'subgraph') {
            // Show subgraph internal nodes only if parent is expanded
            const parentId = node.parent;
            return parentId && expandedSubgraphs.has(parentId);
          }
          return true;
        });

        // Filter edges based on expanded subgraphs
        const visibleEdges = topology.edges.filter(edge => {
          if (edge.subgraph) {
            // Show subgraph internal edges only if parent is expanded
            return expandedSubgraphs.has(edge.subgraph);
          }
          return true;
        });

        // Convert backend nodes to React Flow nodes with automatic layout
        const flowNodes: Node[] = visibleNodes.map((node) => {
          const position = layoutPositions[node.id] || { x: 100, y: 100 };
          const status = nodeStatus[node.id];

          let backgroundColor = '#f3f4f6';
          let borderColor = '#d1d5db';
          let boxShadow = 'none';
          let nodeWidth = 180;

          if (status === 'running') {
            backgroundColor = '#fef3c7';
            borderColor = '#f59e0b';
            boxShadow = '0 0 20px rgba(245, 158, 11, 0.5)';
          } else if (status === 'completed') {
            backgroundColor = '#dcfce7';
            borderColor = '#22c55e';
          }

          // Style subgraph nodes differently
          if (node.type === 'subgraph') {
            backgroundColor = '#ede9fe';
            borderColor = '#8b5cf6';
            nodeWidth = 120; // Even smaller for subgraph internal nodes
          }

          return {
            id: node.id,
            type: 'default',
            data: {
              label: node.type === 'subgraph' ? node.id.split('.')[1] || node.id : node.id
            },
            position,
            style: {
              background: backgroundColor,
              border: '2px solid',
              borderColor,
              width: nodeWidth,
              height: node.type === 'subgraph' ? 40 : 50,
              boxShadow,
              transition: 'all 0.3s ease',
              fontSize: node.type === 'subgraph' ? '11px' : '14px',
            },
          };
        });

        // Convert backend edges to React Flow edges (preserve backend connections)
        const flowEdges: Edge[] = visibleEdges.map(edge => {
          const sourceStatus = nodeStatus[edge.source];
          const targetStatus = nodeStatus[edge.target];

          // Animate edge if source is running or both are completed
          const isAnimated = sourceStatus === 'running' || (sourceStatus === 'completed' && targetStatus === 'completed');

          // Color based on execution state
          let strokeColor = '#9ca3af';
          let strokeWidth = 2;

          // Style subgraph edges differently
          if (edge.subgraph) {
            strokeColor = '#c4b5fd';
            strokeWidth = 1;
          }

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
  }, [showGraph, shouldLoadTopology, topologyLoaded, setNodes, setEdges]);

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
  }, [nodeStatus, topologyLoaded, setNodes]);

  // Auto-expand subgraphs when they start executing and dynamically create nodes
  useEffect(() => {
    if (!autoExpandSubgraphs) return;

    const newExpanded = new Set(expandedSubgraphs);
    const newDynamicNodes = [...dynamicNodes];
    const newDynamicEdges = [...dynamicEdges];

    Object.entries(nodeStatus).forEach(([nodeId, status]) => {
      // Dynamically detect if this node is a subgraph parent
      // Check for child nodes from events or topology, or parallel_subgraphs_X naming pattern
      const hasChildNodes = topology?.subgraph_nodes?.some(n => n.parent === nodeId) ||
        newDynamicNodes.some(n => n.parent === nodeId);
      const isParallelSubgraphInstance = nodeId.startsWith('parallel_subgraphs_') && nodeId !== 'parallel_subgraphs';
      const isSubgraphParent = hasChildNodes || isParallelSubgraphInstance;

      if (isSubgraphParent && status === 'running' && !newExpanded.has(nodeId)) {
        console.log(`Auto-expanding subgraph: ${nodeId}`);
        newExpanded.add(nodeId);

        // Dynamically create internal nodes for subgraph instances
        if (!newDynamicNodes.find(n => n.id === nodeId)) {
          // First, create the parent node if it doesn't exist in topology
          if (!topology?.nodes.find(n => n.id === nodeId)) {
            newDynamicNodes.push({
              id: nodeId,
              type: 'default'
            });
          }

          // Dynamically extract subgraph internal nodes from topology or events
          // Check if topology has subgraph nodes for this parent
          const subgraphInternalNodes = topology?.subgraph_nodes
            ?.filter(n => n.parent === nodeId)
            .map(n => n.id.split('.').pop()) || [];

          // If no topology info, extract from existing dynamic nodes or use a default pattern
          const existingInternalNodes = newDynamicNodes
            .filter(n => n.parent === nodeId)
            .map(n => n.id.split('.').pop());

          const internalNodesToCreate = subgraphInternalNodes.length > 0
            ? subgraphInternalNodes
            : (existingInternalNodes.length > 0 ? existingInternalNodes : []);

          internalNodesToCreate.forEach((internalNode, index) => {
            const fullId = `${nodeId}.${internalNode}`;

            const alreadyExists =
              topology?.nodes.some(n => n.id === fullId) ||
              newDynamicNodes.some(n => n.id === fullId);

            if (!alreadyExists) {
              newDynamicNodes.push({
                id: fullId,
                type: 'subgraph',
                parent: nodeId
              });
              // Add internal edges
              if (index < internalNodesToCreate.length - 1) {
                const nextFullId = `${nodeId}.${internalNodesToCreate[index + 1]}`;
                newDynamicEdges.push({
                  id: `${fullId}-${nextFullId}`,
                  source: fullId,
                  target: nextFullId,
                  subgraph: nodeId
                });
              }
            }
          });
        }
      }

      // Auto-collapse when subgraph completes
      if (isSubgraphParent && status === 'completed' && newExpanded.has(nodeId)) {
        console.log(`Auto-collapsing subgraph: ${nodeId}`);
        newExpanded.delete(nodeId);

        // Remove dynamic subgraph internal nodes when collapsing
        const nodesToRemove = newDynamicNodes.filter(n => n.parent === nodeId);
        const edgesToRemove = newDynamicEdges.filter(e => e.subgraph === nodeId);

        nodesToRemove.forEach(node => {
          const index = newDynamicNodes.findIndex(n => n.id === node.id);
          if (index !== -1) newDynamicNodes.splice(index, 1);
        });

        edgesToRemove.forEach(edge => {
          const index = newDynamicEdges.findIndex(e => e.id === edge.id);
          if (index !== -1) newDynamicEdges.splice(index, 1);
        });

        console.log(`Removed ${nodesToRemove.length} subgraph nodes and ${edgesToRemove.length} edges for ${nodeId}`);
      }
    });

    if (newExpanded.size !== expandedSubgraphs.size) {
      setExpandedSubgraphs(newExpanded);
    }

    if (newDynamicNodes.length !== dynamicNodes.length || newDynamicEdges.length !== dynamicEdges.length) {
      setDynamicNodes(newDynamicNodes);
      setDynamicEdges(newDynamicEdges);
    }
  }, [nodeStatus, autoExpandSubgraphs, expandedSubgraphs, dynamicNodes, dynamicEdges, topology]);

  // Update graph when subgraphs expand/collapse (without full reload)
  useEffect(() => {
    if (!topology || !topologyLoaded) return;

    console.log('[GraphUpdate] Updating graph with topology:', topology);
    console.log('[GraphUpdate] Dynamic nodes:', dynamicNodes);
    console.log('[GraphUpdate] Dynamic edges:', dynamicEdges);
    console.log('[GraphUpdate] Expanded subgraphs:', Array.from(expandedSubgraphs));

    // Combine static topology with dynamic nodes
    const allNodes = [...topology.nodes, ...dynamicNodes];
    const allEdges = [...topology.edges, ...dynamicEdges];

    console.log('[GraphUpdate] All nodes:', allNodes.length);
    console.log('[GraphUpdate] All edges:', allEdges.length);

    // Use automatic layout algorithm based on combined topology
    const layoutPositions = computeLayout(allNodes, allEdges, expandedSubgraphs);
    console.log(
      "AFTER COMPUTELAYOUT",
      layoutPositions["parallel_subgraphs.task_1"]
    );

    // Filter nodes based on expanded subgraphs
    const visibleNodes = allNodes.filter(node => {
      if (node.type === 'subgraph') {
        // Show subgraph internal nodes only if parent is expanded
        const parentId = node.parent;
        return parentId && expandedSubgraphs.has(parentId);
      }
      return true;
    });

    // Filter edges based on expanded subgraphs
    const visibleEdges = allEdges.filter(edge => {
      if (edge.subgraph) {
        return expandedSubgraphs.has(edge.subgraph);
      }
      return true;
    });

    console.log('[GraphUpdate] Visible nodes:', visibleNodes.length);
    console.log('[GraphUpdate] Visible edges:', visibleEdges.length);

    // Convert backend nodes to React Flow nodes
    const flowNodes: Node[] = visibleNodes.map(node => {
      const position = layoutPositions[node.id] || { x: 0, y: 0 };
      console.log(node.id, position, node.type, 222222);
      const status = nodeStatus[node.id];

      let backgroundColor = '#f3f4f6';
      let borderColor = '#d1d5db';
      let boxShadow = 'none';
      let nodeWidth = 180;

      if (status === 'running') {
        backgroundColor = '#fef3c7';
        borderColor = '#f59e0b';
        boxShadow = '0 0 20px rgba(245, 158, 11, 0.5)';
      } else if (status === 'completed') {
        backgroundColor = '#dcfce7';
        borderColor = '#22c55e';
      }

      // Style subgraph nodes differently
      if (node.type === 'subgraph') {
        backgroundColor = '#ede9fe';
        borderColor = '#8b5cf6';
        nodeWidth = 120; // Even smaller for subgraph internal nodes
      }

      // Calculate node width based on label length
      const label = node.type === 'subgraph' ? node.id.split('.')[1] || node.id : node.id;
      const labelLength = label.length;
      const calculatedWidth = Math.max(nodeWidth, Math.min(labelLength * 8 + 40, 300)); // Dynamic width with max limit

      return {
        id: node.id,
        type: 'default',
        data: {
          label: label
        },
        position,
        style: {
          background: backgroundColor,
          border: '2px solid',
          borderColor,
          width: calculatedWidth,
          height: node.type === 'subgraph' ? 40 : 50,
          boxShadow,
          transition: 'all 0.3s ease',
          fontSize: node.type === 'subgraph' ? '11px' : '14px',
          whiteSpace: 'normal',
          wordWrap: 'break-word',
          overflow: 'hidden',
          padding: '8px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
        },
      };
    });

    // Convert backend edges to React Flow edges (preserve backend connections)
    const flowEdges: Edge[] = visibleEdges.map(edge => {
      const sourceStatus = nodeStatus[edge.source];
      const targetStatus = nodeStatus[edge.target];

      // Animate edge if source is running or both are completed
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

    console.log('[GraphUpdate] Setting flow nodes:', flowNodes.length);
    console.log('[GraphUpdate] Setting flow edges:', flowEdges.length);

    setNodes(flowNodes);
    setEdges(flowEdges);
  }, [topology, topologyLoaded, expandedSubgraphs, dynamicNodes, dynamicEdges, nodeStatus, setNodes, setEdges]);

  // Update edge styles and active edge separately to avoid infinite loop
  useEffect(() => {
    if (!topologyLoaded) return;

    setEdges((eds) => {
      return eds.map((edge) => {
        const sourceStatus = nodeStatus[edge.source];
        const targetStatus = nodeStatus[edge.target];

        // Edge is active if:
        // 1. The target node is currently running (flow is arriving at this node)
        // 2. The source node is running and target is not yet started (flow is leaving this node)
        const isFlowArriving = targetStatus === 'running';
        const isFlowLeaving = sourceStatus === 'running' && targetStatus === undefined;

        // Edge is completed if both source and target are completed
        const isCompletedPath = sourceStatus === 'completed' && targetStatus === 'completed';

        let strokeColor = '#9ca3af';
        let strokeWidth = 2;
        let animated = false;

        if (isFlowArriving || isFlowLeaving) {
          // Active flow - bright blue animation
          strokeColor = '#3b82f6';
          strokeWidth = 4;
          animated = true;
        } else if (isCompletedPath) {
          // Completed path - green
          strokeColor = '#22c55e';
          strokeWidth = 2;
          animated = false;
        } else if (sourceStatus === 'running') {
          // Source is running but flow hasn't reached target yet
          strokeColor = '#f59e0b';
          strokeWidth = 3;
          animated = true;
        }

        return {
          ...edge,
          animated,
          style: {
            stroke: strokeColor,
            strokeWidth,
            transition: 'all 0.3s ease',
          },
        };
      });
    });
  }, [nodeStatus, topologyLoaded, setEdges]);

  if (!showGraph) return null;

  console.log('[GraphVisualization] Rendering with nodes:', nodes.length, 'edges:', edges.length);
  console.log('[GraphVisualization] Topology loaded:', topologyLoaded);

  return (
    <div className="h-[600px] bg-white rounded-lg shadow-md border">
      {topologyLoaded ? (
        <>
          {nodes.length === 0 ? (
            <div className="h-full flex items-center justify-center">
              <p className="text-red-500">No nodes to display. Check console for errors.</p>
            </div>
          ) : (
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              fitView
              defaultViewport={{ x: 0, y: 0, zoom: 0.8 }}
            >
              <Background />
              <Controls />
            </ReactFlow>
          )}
        </>
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
  const [autoExpandSubgraphs, setAutoExpandSubgraphs] = useState(true);

  const handleRun = async () => {
    // Generate unique thread_id for this execution
    const newThreadId = `thread_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    setThreadId(newThreadId);

    setLoading(true);
    setNodeStatus({});
    setStreamedText('');
    setShouldLoadTopology(true); // Trigger graph topology load when flow starts

    try {
      // Start the graph execution and stream text output
      const runResponse = await fetch('http://localhost:8000/demo/run', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          thread_id: newThreadId
        }),
      });

      const runReader = runResponse.body?.getReader();
      const runDecoder = new TextDecoder();

      // Stream text output from /run endpoint
      if (runReader) {
        const runStream = async () => {
          while (true) {
            const { done, value } = await runReader.read();
            if (done) break;

            const chunk = runDecoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const data = line.slice(6);
                try {
                  const parsed = JSON.parse(data);
                  // Handle output text chunks
                  if (parsed.content) {
                    setStreamedText(prev => prev + parsed.content + '\n');
                  }
                } catch (e) {
                  console.error('Failed to parse SSE data:', e);
                }
              }
            }
          }
        };
        runStream();
      }

      // Start streaming node status updates from /stream endpoint
      const streamResponse = await fetch(`http://localhost:8000/demo/stream?thread_id=${newThreadId}`);
      const reader = streamResponse.body?.getReader();
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
                  const nodeId = parsed.data?.node_id;
                  if (nodeId) {
                    setNodeStatus(prev => ({
                      ...prev,
                      [nodeId]: 'running'
                    }));
                  }
                }
                // Handle subgraph started events
                else if (parsed.type === 'subgraph_started') {
                  const nodeId = parsed.data?.node_id;
                  if (nodeId) {
                    setNodeStatus(prev => ({
                      ...prev,
                      [nodeId]: 'running'
                    }));
                  }
                }
                // Handle node completed events
                else if (parsed.type === 'node_completed') {
                  const nodeId = parsed.data?.node_id;
                  if (nodeId) {
                    setNodeStatus(prev => ({
                      ...prev,
                      [nodeId]: 'completed'
                    }));
                  }
                }
                // Handle subgraph completed events
                else if (parsed.type === 'subgraph_completed') {
                  const nodeId = parsed.data?.node_id;
                  if (nodeId) {
                    setNodeStatus(prev => ({
                      ...prev,
                      [nodeId]: 'completed'
                    }));
                  }
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
          <div className="flex items-center gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={autoExpandSubgraphs}
                onChange={(e) => setAutoExpandSubgraphs(e.target.checked)}
                className="w-4 h-4"
              />
              Auto-expand subgraphs
            </label>
            <button
              onClick={handleRun}
              disabled={loading}
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
            >
              {loading ? 'Running...' : 'Run Graph'}
            </button>
          </div>
        </div>
      </div>

      <div className="flex-1 p-4 overflow-hidden">
        <div className="max-w-full mx-auto h-full" style={{ width: '100%' }}>
          <GraphVisualization
            showGraph={showGraph}
            nodeStatus={nodeStatus}
            shouldLoadTopology={shouldLoadTopology}
            autoExpandSubgraphs={autoExpandSubgraphs}
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
