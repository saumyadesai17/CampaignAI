"use client";

import React, { useCallback, useEffect } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  addEdge,
  Node,
  Edge,
  Connection,
  ConnectionMode,
  ReactFlowInstance,
  OnConnectStart,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { GenericModuleNode } from "./nodes/GenericModuleNode";
import { OutputNode } from "./nodes/OutputNode";
import { InputNode } from "./nodes/InputNode";
import { EmailSenderNode } from "./nodes/EmailSenderNode";
import { useCampaignStore } from "@/stores/campaignStore";
import { Sidebar } from "./Sidebar";
import { CampaignCalendar } from "./CampaignCalendar";
import { StrategyPanel } from "./StrategyPanel";
import { MODULE_DEFINITIONS, CONNECTION_MATRIX } from "@/lib/moduleDefinitions";
import { Eye, EyeOff } from "lucide-react";
import { WorkflowExecutionService } from "@/lib/workflowExecution";

// Helper function to convert ReactFlow edges to workflow connections format
const convertEdgesToConnections = (nodes: Node[], edges: Edge[]) => {
  const connectionsBySource: Record<string, Array<{target_module: string, source_output: string, target_input: string}>> = {};
  
  console.log('🔄 Converting edges to connections...');
  console.log('📋 Available edges:', edges);
  
  edges.forEach(edge => {
    const sourceNode = nodes.find(n => n.id === edge.source);
    const targetNode = nodes.find(n => n.id === edge.target);
    
    if (sourceNode && targetNode) {
      const sourceModuleName = sourceNode.data.module_name as string;
      const targetModuleName = targetNode.data.module_name as string;
      
      // Extract output and input names from handles (these should be the actual field names)
      const sourceOutput = edge.sourceHandle || 'output';
      const targetInput = edge.targetHandle || 'input';
      
      if (!connectionsBySource[sourceModuleName]) {
        connectionsBySource[sourceModuleName] = [];
      }
      
      connectionsBySource[sourceModuleName].push({
        target_module: targetModuleName,
        source_output: sourceOutput,
        target_input: targetInput
      });
      
      console.log(`🔗 Edge connection: ${sourceModuleName}.${sourceOutput} → ${targetModuleName}.${targetInput}`);
      console.log(`   Source node: ${sourceNode.id} (${sourceModuleName})`);
      console.log(`   Target node: ${targetNode.id} (${targetModuleName})`);
    } else {
      console.warn('⚠️ Could not find source or target node for edge:', edge);
    }
  });
  
  // Convert to the format expected by workflow execution
  const result = Object.entries(connectionsBySource).map(([module_name, connections]) => ({
    module_name,
    connections
  }));
  
  console.log('🎯 Final connections structure:', result);
  return result;
};

const nodeTypes = {
  module: GenericModuleNode,
  output: OutputNode,
  input: InputNode,
  email_sender: EmailSenderNode,
};

interface CampaignCanvasProps {
  initialNodes?: Node[];
  initialEdges?: Edge[];
}

// Default edge options for better interaction and visual feedback
const defaultEdgeOptions = {
  animated: false, // Disable animation for clearer visual state
  style: { 
    stroke: '#8b5cf6', 
    strokeWidth: 2,
  },
  type: 'smoothstep',
};

export function CampaignCanvas({ initialNodes = [], initialEdges = [] }: CampaignCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const [reactFlowInstance, setReactFlowInstance] = React.useState<ReactFlowInstance | null>(null);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = React.useState(false);
  const [isMinimapCollapsed, setIsMinimapCollapsed] = React.useState(false);
  const [showCalendar, setShowCalendar] = React.useState(false);
  const [isExecutingWorkflow, setIsExecutingWorkflow] = React.useState(false);
  const [executionProgress, setExecutionProgress] = React.useState<{completed: number, total: number}>({completed: 0, total: 0});
  const { setSelectedNodeId, setConnectionPreview, setExecutionResult, strategyPlan, setStrategyPlan } = useCampaignStore();

  // Update nodes and edges when props change
  useEffect(() => {
    if (initialNodes.length > 0) {
      setNodes(initialNodes);
    }
  }, [initialNodes, setNodes]);

  useEffect(() => {
    if (initialEdges.length > 0) {
      setEdges(initialEdges);
    }
  }, [initialEdges, setEdges]);

  const onConnect = useCallback(
    (params: Connection) => {
      const sourceNode = nodes.find(n => n.id === params.source);
      const targetNode = nodes.find(n => n.id === params.target);
      
      // Check connection compatibility
      if (sourceNode && targetNode) {
        const isCompatible = checkConnectionCompatibility(
          sourceNode, 
          params.sourceHandle!,
          targetNode, 
          params.targetHandle!
        );
        
        if (isCompatible) {
          setEdges((eds) => addEdge(params, eds));
        }
      }
    },
    [nodes, setEdges]
  );

  const checkConnectionCompatibility = (
    sourceNode: Node,
    sourceHandle: string,
    targetNode: Node, 
    targetHandle: string
  ): boolean => {
    // Check using the connection matrix
    if (sourceNode.type === "module" && targetNode.type === "module") {
      const sourceKey = `${sourceNode.data.module_name}.${sourceHandle}`;
      const targetKey = `${targetNode.data.module_name}.${targetHandle}`;
      
      const compatibleTargets = CONNECTION_MATRIX[sourceKey as keyof typeof CONNECTION_MATRIX];
      
      if (compatibleTargets) {
        return compatibleTargets.includes(targetKey) || compatibleTargets.includes("*");
      }
    }
    
    // Allow connections from input nodes to any module input
    if (sourceNode.type === "input" && targetNode.type === "module") {
      return true;
    }
    
    // Allow connections from any module output to output nodes
    if (sourceNode.type === "module" && targetNode.type === "output") {
      return true;
    }
    
    return false;
  };



  const onNodeClick = useCallback((event: React.MouseEvent, node: Node) => {
    setSelectedNodeId(node.id);
  }, [setSelectedNodeId]);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
  }, [setSelectedNodeId]);

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
  }, []);

  const onDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();

    const reactFlowBounds = (event.target as Element).closest('.react-flow')?.getBoundingClientRect();
    const data = event.dataTransfer.getData('application/reactflow');

    if (typeof data === 'undefined' || !data || !reactFlowInstance || !reactFlowBounds) {
      return;
    }

    try {
      const dropData = JSON.parse(data);
      
      // Use cursor position or center of viewport if no cursor position
      let position;
      if (event.clientX && event.clientY) {
        position = reactFlowInstance.screenToFlowPosition({
          x: event.clientX - reactFlowBounds.left,
          y: event.clientY - reactFlowBounds.top,
        });
      } else {
        // Center of viewport as fallback
        const viewport = reactFlowInstance.getViewport();
        position = {
          x: (reactFlowBounds.width / 2 - viewport.x) / viewport.zoom,
          y: (reactFlowBounds.height / 2 - viewport.y) / viewport.zoom,
        };
      }

      // Initialize inputs with default values from module definition
      const moduleDefinition = MODULE_DEFINITIONS[dropData.module_name as keyof typeof MODULE_DEFINITIONS];
      const initialInputs: Record<string, unknown> = {};
      
      if (moduleDefinition) {
        Object.entries(moduleDefinition.inputs).forEach(([key, inputDef]) => {
          const def = inputDef as { type?: string; properties?: Record<string, unknown>; default?: unknown };
          if (def.type === 'array') {
            initialInputs[key] = [];
          } else if (def.type === 'object') {
            // Initialize object with proper structure based on properties definition
            const objectValue: Record<string, unknown> = {};
            if (def.properties) {
              Object.entries(def.properties).forEach(([propKey, propType]) => {
                if (Array.isArray(propType)) {
                  objectValue[propKey] = [];
                } else if (propType === 'object') {
                  objectValue[propKey] = {};
                } else {
                  objectValue[propKey] = "";
                }
              });
            }
            initialInputs[key] = objectValue;
          } else {
            initialInputs[key] = inputDef.default || (inputDef.type === 'integer' ? 0 : inputDef.type === 'boolean' ? false : '');
          }
        });
        
        // HARDCODE OVERRIDE: Force campaign_duration to 2025 October-December
        if (initialInputs.campaign_duration) {
          initialInputs.campaign_duration = {
            start_date: "2025-10-01",
            end_date: "2025-12-31"
          };
        }
      }

      const newNode = {
        id: `${dropData.module_name}-${Date.now()}`,
        type: dropData.module_name === 'email_sender' ? 'email_sender' : 'module',
        position,
        data: {
          id: `${Math.random().toString(36).substr(2, 9).toUpperCase()}`,
          isActive: true,
          module_name: dropData.module_name,
          inputs: initialInputs
        },
      };

      setNodes((nds) => nds.concat(newNode));
    } catch (error) {
      console.error('Error parsing drop data:', error);
    }
  }, [reactFlowInstance, setNodes]);

  const getCompatibleTargets = useCallback((sourceNodeId: string, sourceHandle: string) => {
    const sourceNode = nodes.find(n => n.id === sourceNodeId);
    if (!sourceNode) return [];

    const compatibleTargets: Array<{nodeId: string, handleId: string}> = [];
    
    nodes.forEach(targetNode => {
      if (targetNode.id === sourceNodeId) return; // Skip same node
      
      if (targetNode.type === "module") {
        const moduleDefinition = MODULE_DEFINITIONS[targetNode.data.module_name as keyof typeof MODULE_DEFINITIONS];
        if (moduleDefinition) {
          Object.keys(moduleDefinition.inputs).forEach(inputKey => {
            if (checkConnectionCompatibility(sourceNode, sourceHandle, targetNode, inputKey)) {
              compatibleTargets.push({ nodeId: targetNode.id, handleId: inputKey });
            }
          });
        }
      } else if (targetNode.type === "output") {
        compatibleTargets.push({ nodeId: targetNode.id, handleId: "input" });
      }
    });

    return compatibleTargets;
  }, [nodes]);

  const onConnectStart = useCallback<OnConnectStart>((event, params) => {
    if (!params) return;
    const compatibleTargets = getCompatibleTargets(params.nodeId!, params.handleId!);
    setConnectionPreview({
      sourceNode: params.nodeId!,
      sourceHandle: params.handleId!,
      compatibleTargets,
    });
  }, [getCompatibleTargets, setConnectionPreview]);

  const onConnectEnd = useCallback(() => {
    setConnectionPreview(null);
  }, [setConnectionPreview]);

  const handleAddModule = useCallback((moduleId: string) => {
    // Get viewport center for new node placement
    let position = { x: 300, y: 200 }; // Default position
    
    if (reactFlowInstance) {
      const bounds = document.querySelector('.react-flow')?.getBoundingClientRect();
      
      if (bounds) {
        position = reactFlowInstance.screenToFlowPosition({
          x: bounds.width / 2,
          y: bounds.height / 2,
        });
      }
    }

    // Initialize inputs with default values from module definition
    const moduleDefinition = MODULE_DEFINITIONS[moduleId as keyof typeof MODULE_DEFINITIONS];
    const initialInputs: Record<string, unknown> = {};
    
    if (moduleDefinition) {
      Object.entries(moduleDefinition.inputs).forEach(([key, inputDef]: [string, unknown]) => {
        const def = inputDef as Record<string, unknown>;
        if (def.type === 'array') {
          initialInputs[key] = [];
        } else if (def.type === 'object') {
          // Initialize object with proper structure based on properties definition
          const objectValue: Record<string, unknown> = {};
          if (def.properties) {
            Object.entries(def.properties as Record<string, unknown>).forEach(([propKey, propType]) => {
              if (Array.isArray(propType)) {
                objectValue[propKey] = [];
              } else if (propType === 'object') {
                objectValue[propKey] = {};
              } else {
                objectValue[propKey] = "";
              }
            });
          }
          initialInputs[key] = objectValue;
        } else {
          initialInputs[key] = def.default || (def.type === 'integer' ? 0 : def.type === 'boolean' ? false : '');
        }
      });
      
      // HARDCODE OVERRIDE: Force campaign_duration to 2025 October-December
      if (initialInputs.campaign_duration) {
        initialInputs.campaign_duration = {
          start_date: "2025-10-01",
          end_date: "2025-12-31"
        };
      }
    }

    const newNode = {
      id: `${moduleId}-${Date.now()}`,
      type: moduleId === 'email_sender' ? 'email_sender' : 'module' as const,
      position,
      data: {
        id: `${Math.random().toString(36).substr(2, 9).toUpperCase()}`,
        isActive: true,
        module_name: moduleId,
        inputs: initialInputs
      },
    };

    setNodes((nds) => nds.concat(newNode));
  }, [reactFlowInstance, setNodes]);

  const handleRunWorkflow = useCallback(async () => {
    if (isExecutingWorkflow) {
      // TODO: Add ability to cancel workflow execution
      setIsExecutingWorkflow(false);
      return;
    }

    setIsExecutingWorkflow(true);
    setExecutionProgress({ completed: 0, total: nodes.length });

    try {
      // Get the latest module data from the store before execution
      const modules = useCampaignStore.getState().modules;
      
      // Sync latest inputs from store to nodes
      const nodesWithLatestInputs = nodes.map(node => {
        const moduleData = modules[node.id];
        if (moduleData && typeof moduleData === 'object' && 'inputs' in moduleData) {
          console.log(`� Syncing latest inputs for node ${node.id}:`, (moduleData as {inputs: Record<string, unknown>}).inputs);
          return {
            id: node.id,
            data: {
              module_name: node.data.module_name as string,
              inputs: (moduleData as {inputs: Record<string, unknown>}).inputs
            }
          };
        }
        return {
          id: node.id,
          data: {
            module_name: node.data.module_name as string,
            inputs: node.data.inputs as Record<string, unknown>
          }
        };
      });
      
      console.log('📋 Nodes with latest inputs:', nodesWithLatestInputs.map(n => ({
        id: n.id,
        module: n.data.module_name,
        inputs: n.data.inputs
      })));
      
      // Convert ReactFlow edges to workflow connections format
      const connections = convertEdgesToConnections(nodes, edges);
      console.log('🔗 Converted connections:', connections);

      // Execute workflow with latest inputs
      const results = await WorkflowExecutionService.executeWorkflow(
        nodesWithLatestInputs,
        connections,
        (nodeId, result) => {
          // On node completion
          setExecutionResult(nodeId, result);
          setExecutionProgress(prev => ({ ...prev, completed: prev.completed + 1 }));
        },
        (nodeId) => {
          // On node start
          console.log(`Starting execution of node: ${nodeId}`);
        }
      );

      console.log('Workflow execution completed:', results);
    } catch (error) {
      console.error('Workflow execution failed:', error);
    } finally {
      setIsExecutingWorkflow(false);
      setExecutionProgress({ completed: 0, total: 0 });
    }
  }, [nodes, edges, isExecutingWorkflow, setExecutionResult]);

  return (
    <>
      <div className="h-full w-full flex overflow-hidden">
        <div className="flex-1 relative h-full">
          {/* Strategy Panel - AI Agent's Thought Process */}
          {strategyPlan && (
            <StrategyPanel 
              strategyPlan={strategyPlan} 
              onClose={() => setStrategyPlan(null)} 
            />
          )}
          
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={onNodeClick}
            onPaneClick={onPaneClick}
            onConnectStart={onConnectStart}
            onConnectEnd={onConnectEnd}
            onInit={setReactFlowInstance}
            onDragOver={onDragOver}
            onDrop={onDrop}
            nodeTypes={nodeTypes}
            connectionMode={ConnectionMode.Strict}
            defaultEdgeOptions={defaultEdgeOptions}
            elementsSelectable={true}
            deleteKeyCode="Delete"
            fitView
            className="bg-slate-900/50 h-full w-full backdrop-blur-sm"
            attributionPosition="bottom-left"
          >
            <Background 
              color="#475569" 
              gap={16}
              size={1}
              className="opacity-30"
            />
            <Controls 
              className="bg-slate-800/90 backdrop-blur-sm border border-slate-700 rounded-lg shadow-xl"
            />
            {!isMinimapCollapsed && (
              <MiniMap
                className="!bg-slate-800/90 backdrop-blur-sm border border-slate-700 rounded-lg shadow-xl"
                maskColor="rgb(15 23 42 / 0.6)"
                nodeColor={(node) => {
                  switch (node.type) {
                    case "input":
                      return "#3b82f6";
                    case "module":
                      if (node.data.module_name && MODULE_DEFINITIONS[node.data.module_name as keyof typeof MODULE_DEFINITIONS]) {
                        return MODULE_DEFINITIONS[node.data.module_name as keyof typeof MODULE_DEFINITIONS].color;
                      }
                      return "#6b7280"; 
                    case "output":
                      return "#f59e0b";
                    default:
                      return "#6b7280";
                  }
                }}
              />
            )}
          </ReactFlow>
          
          {/* Control Buttons */}
          <div className="absolute bottom-4 right-4 flex flex-col gap-2 z-10">
            {/* Minimap Toggle Button */}
            <button
              onClick={() => setIsMinimapCollapsed(!isMinimapCollapsed)}
              className="bg-white border border-gray-300 rounded-md p-2 text-xs shadow-sm hover:bg-gray-50 flex items-center justify-center"
              title={isMinimapCollapsed ? 'Show Minimap' : 'Hide Minimap'}
            >
              {isMinimapCollapsed ? (
                <Eye className="w-4 h-4" />
              ) : (
                <EyeOff className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>
        <Sidebar 
          onAddModule={handleAddModule}
          onRunWorkflow={handleRunWorkflow}
          isExecutingWorkflow={isExecutingWorkflow}
          executionProgress={executionProgress}
          nodesCount={nodes.length}
          isCollapsed={isSidebarCollapsed}
          onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
        />
      </div>

      {/* Calendar Modal */}
      {showCalendar && (
        <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl w-[95vw] h-[95vh] relative">
            <button
              onClick={() => setShowCalendar(false)}
              className="absolute top-4 right-4 z-10 bg-slate-800/90 backdrop-blur-sm border border-slate-700 rounded-full p-2.5 shadow-xl hover:bg-slate-700 transition-all duration-200 group"
            >
              <svg className="w-5 h-5 text-slate-300 group-hover:text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            <CampaignCalendar />
          </div>
        </div>
      )}
    </>
  );
}