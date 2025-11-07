"use client";

import React, { memo, useState } from "react";
import { Handle, Position, NodeProps, useReactFlow } from "@xyflow/react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { 
  Mail, 
  Plus, 
  Trash2, 
  Send, 
  CheckCircle2, 
  XCircle, 
  Loader2,
  Eye,
  Settings,
  Users,
  MessageSquare
} from "lucide-react";
import { useCampaignStore } from "@/stores/campaignStore";
import { WorkflowExecutionService, ExecutionResult } from "@/lib/workflowExecution";
import { OutputViewer } from "@/components/workflow/OutputViewer";

interface EmailSenderNodeProps extends NodeProps {
  data: {
    id: string;
    isActive: boolean;
    module_name: string;
    inputs: Record<string, unknown>;
    executionStatus?: 'idle' | 'running' | 'success' | 'error';
    executionResult?: ExecutionResult;
  };
}

interface EmailRecipient {
  name: string;
  email: string;
  personal_description: string;
}

interface EmailFormData {
  company_name: string;
  campaign_description: string;
  recipients: EmailRecipient[];
  sender_name: string;
  email_subject: string;
}

const EmailSenderNodeComponent = ({ id, data }: EmailSenderNodeProps) => {
  const { selectedNodeId, updateModule, connectionPreview, executionResults, setExecutionResult } = useCampaignStore();
  const { setNodes } = useReactFlow();
  const [isExpanded, setIsExpanded] = useState(false);
  const [inputs, setInputs] = useState(data.inputs || {});
  const [isExecuting, setIsExecuting] = useState(false);
  const [showOutputViewer, setShowOutputViewer] = useState(false);

  const isSelected = selectedNodeId === id;

  // Initialize default values with proper typing
  const defaultInputs: EmailFormData = {
    company_name: (inputs.company_name as string) || "",
    campaign_description: (inputs.campaign_description as string) || "",
    recipients: (inputs.recipients as EmailRecipient[]) || [],
    sender_name: (inputs.sender_name as string) || "",
    email_subject: (inputs.email_subject as string) || ""
  };

  const [formData, setFormData] = useState<EmailFormData>(defaultInputs);

  const updateInput = (key: string, value: unknown) => {
    const newInputs = { ...inputs, [key]: value };
    setInputs(newInputs);
    
    // Update both the store AND the ReactFlow nodes
    updateModule(id, { ...data, inputs: newInputs });
    
    // Update the node in ReactFlow so it has the latest data
    setNodes((nds) =>
      nds.map((node) => {
        if (node.id === id) {
          return {
            ...node,
            data: {
              ...node.data,
              inputs: newInputs,
            },
          };
        }
        return node;
      })
    );
    
    console.log(`📝 Updated ${key} for node ${id}:`, value);
  };

  const updateFormData = (key: keyof EmailFormData, value: string | EmailRecipient[]) => {
    const newFormData = { ...formData, [key]: value } as EmailFormData;
    setFormData(newFormData);
    updateInput(key, value);
  };

  const addRecipient = () => {
    const newRecipient: EmailRecipient = {
      name: "",
      email: "",
      personal_description: ""
    };
    const newRecipients = [...formData.recipients, newRecipient];
    updateFormData("recipients", newRecipients);
  };

  const updateRecipient = (index: number, field: keyof EmailRecipient, value: string) => {
    const newRecipients = [...formData.recipients];
    newRecipients[index] = { ...newRecipients[index], [field]: value };
    updateFormData("recipients", newRecipients);
  };

  const removeRecipient = (index: number) => {
    const newRecipients = formData.recipients.filter((_: EmailRecipient, i: number) => i !== index);
    updateFormData("recipients", newRecipients);
  };

  // Get execution result from store
  const executionResult = executionResults[id] as ExecutionResult | undefined;
  const executionStatus = isExecuting ? 'running' : executionResult?.execution_status;

  const handleExecute = async () => {
    if (isExecuting) return;
    
    // Validate required fields
    if (!formData.company_name || !formData.campaign_description || formData.recipients.length === 0) {
      alert("Please fill in company name, campaign description, and add at least one recipient.");
      return;
    }

    // Validate recipient emails
    const invalidEmails = formData.recipients.filter((recipient: EmailRecipient) => 
      !recipient.email || !recipient.email.includes('@') || !recipient.name
    );
    
    if (invalidEmails.length > 0) {
      alert("Please ensure all recipients have valid names and email addresses.");
      return;
    }
    
    setIsExecuting(true);
    try {
      const result = await WorkflowExecutionService.executeModule(data.module_name, { ...formData } as unknown as Record<string, unknown>);
      setExecutionResult(id, result);
    } catch (error) {
      console.error('Email campaign execution failed:', error);
      setExecutionResult(id, {
        outputs: {},
        execution_status: 'error',
        error: error instanceof Error ? error.message : String(error)
      });
    } finally {
      setIsExecuting(false);
    }
  };

  const getExecutionStatusIcon = () => {
    switch (executionStatus) {
      case 'running':
        return <Loader2 className="w-4 h-4 animate-spin text-blue-500" />;
      case 'success':
        return <CheckCircle2 className="w-4 h-4 text-green-500" />;
      case 'error':
        return <XCircle className="w-4 h-4 text-red-500" />;
      default:
        return null;
    }
  };

  const hasOutput = executionResult && executionResult.execution_status === 'success' && executionResult.outputs;

  // Check if this node has compatible handles during connection preview
  const isConnectionSource = connectionPreview && connectionPreview.sourceNode === id;
  const isConnectionActive = connectionPreview !== null;
  
  const compatibleHandles = connectionPreview?.compatibleTargets
    .filter(target => target.nodeId === id)
    .map(target => target.handleId) || [];

  return (
    <div className="relative">
      <Card 
        className={`w-96 bg-slate-800/90 backdrop-blur-sm transition-all duration-200 ${
          isSelected 
            ? "ring-2 ring-violet-500 shadow-xl shadow-violet-500/20 border-violet-500" 
            : "border-slate-700 hover:border-slate-600"
        } ${data.isActive ? `border-2` : ""}`}
        style={{ borderColor: data.isActive && !isSelected ? "#8b5cf6" : undefined }}
      >
        {/* Input Handle */}
        <Handle
          type="target"
          position={Position.Left}
          id="campaign_description"
          className={`w-4 h-4 border-2 border-slate-900 shadow-md transition-all duration-200 ${
            compatibleHandles.includes('campaign_description') ? 'animate-pulse ring-2 ring-green-400' : ''
          }`}
          style={{ 
            top: 120,
            backgroundColor: compatibleHandles.includes('campaign_description') ? '#10b981' : '#8b5cf6',
            transform: compatibleHandles.includes('campaign_description') ? 'scale(1.2)' : 'scale(1)'
          }}
        />
        
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-purple-500" />
              <span className="font-medium text-sm text-white">ID: {data.id}</span>
              <Badge 
                variant={data.isActive ? "default" : "secondary"}
                className={data.isActive ? "bg-violet-600 text-white" : "bg-slate-700 text-slate-300"}
              >
                {data.isActive ? "Active" : "Inactive"}
              </Badge>
            </div>
            <div className="flex items-center ml-3 gap-1">
              {/* Execution Status Indicator */}
              {getExecutionStatusIcon()}
              
              {/* Execute Button */}
              {WorkflowExecutionService.isModuleExecutable(data.module_name) && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleExecute}
                  disabled={isExecuting}
                  title={isExecuting ? "Sending emails..." : "Send Email Campaign"}
                  className="text-green-400 hover:text-green-300 hover:bg-green-500/20"
                >
                  {isExecuting ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                </Button>
              )}
              
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsExpanded(!isExpanded)}
                className="text-slate-300 hover:text-violet-400 hover:bg-slate-700"
              >
                <Settings className="w-4 h-4" />
              </Button>
            </div>
          </div>
          <div>
            <h3 className="font-medium text-sm text-white flex items-center gap-2">
              <Mail className="w-4 h-4 text-purple-400" />
              Email Sender
            </h3>
            <p className="text-xs text-slate-400">Send personalized email campaigns using AI-generated content</p>
          </div>
        </CardHeader>

        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <Badge 
              variant="outline" 
              className="text-xs border-purple-600 text-purple-400"
            >
              Communication
            </Badge>
            
            {/* Output View Button */}
            {hasOutput && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowOutputViewer(true)}
                className="ml-auto bg-green-50 border-green-200 text-green-700 hover:bg-green-100"
                title="View Email Campaign Results"
              >
                <Eye className="w-3 h-3 mr-1" />
                Results
              </Button>
            )}
          </div>

          {isExpanded && (
            <div className="space-y-4 pt-3 border-t border-slate-700">
              {/* Company Name */}
              <div className="space-y-2">
                <Label className="text-xs text-slate-300 flex items-center gap-1">
                  Company Name
                  <span className="text-red-400">*</span>
                </Label>
                <Input
                  value={formData.company_name}
                  onChange={(e) => updateFormData("company_name", e.target.value)}
                  placeholder="Enter company name"
                  className="text-xs bg-slate-700/50 border-slate-600 text-white placeholder:text-slate-500 focus:border-violet-500"
                />
              </div>

              {/* Campaign Description */}
              <div className="space-y-2">
                <Label className="text-xs text-slate-300 flex items-center gap-1">
                  Campaign Description
                  <span className="text-red-400">*</span>
                </Label>
                <Textarea
                  value={formData.campaign_description}
                  onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => updateFormData("campaign_description", e.target.value)}
                  placeholder="Describe your email campaign..."
                  rows={3}
                  className="text-xs bg-slate-700/50 border-slate-600 text-white placeholder:text-slate-500 focus:border-violet-500 resize-none"
                />
              </div>

              {/* Sender Name */}
              <div className="space-y-2">
                <Label className="text-xs text-slate-300">Sender Name</Label>
                <Input
                  value={formData.sender_name}
                  onChange={(e) => updateFormData("sender_name", e.target.value)}
                  placeholder="Leave empty to use company name"
                  className="text-xs bg-slate-700/50 border-slate-600 text-white placeholder:text-slate-500 focus:border-violet-500"
                />
              </div>

              {/* Email Subject */}
              <div className="space-y-2">
                <Label className="text-xs text-slate-300">Email Subject</Label>
                <Input
                  value={formData.email_subject}
                  onChange={(e) => updateFormData("email_subject", e.target.value)}
                  placeholder="Leave empty for default subject"
                  className="text-xs bg-slate-700/50 border-slate-600 text-white placeholder:text-slate-500 focus:border-violet-500"
                />
              </div>

              {/* Recipients */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="text-xs text-slate-300 flex items-center gap-1">
                    <Users className="w-3 h-3" />
                    Recipients
                    <span className="text-red-400">*</span>
                  </Label>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={addRecipient}
                    className="text-violet-400 hover:text-violet-300 hover:bg-violet-500/20"
                  >
                    <Plus className="w-3 h-3 mr-1" />
                    Add
                  </Button>
                </div>

                <div className="space-y-3 max-h-48 overflow-y-auto custom-scrollbar">
                  {formData.recipients.map((recipient: EmailRecipient, index: number) => (
                    <div key={index} className="p-3 border border-slate-600 rounded bg-slate-700/30 space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-slate-400">Recipient {index + 1}</span>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => removeRecipient(index)}
                          className="text-red-400 hover:text-red-300 hover:bg-red-500/20 h-6 w-6 p-0"
                        >
                          <Trash2 className="w-3 h-3" />
                        </Button>
                      </div>
                      
                      <div className="space-y-2">
                        <Input
                          value={recipient.name}
                          onChange={(e) => updateRecipient(index, "name", e.target.value)}
                          placeholder="Recipient name"
                          className="text-xs bg-slate-600/50 border-slate-500 text-white placeholder:text-slate-400 focus:border-violet-500"
                        />
                        
                        <Input
                          type="email"
                          value={recipient.email}
                          onChange={(e) => updateRecipient(index, "email", e.target.value)}
                          placeholder="Recipient email"
                          className="text-xs bg-slate-600/50 border-slate-500 text-white placeholder:text-slate-400 focus:border-violet-500"
                        />
                        
                        <Textarea
                          value={recipient.personal_description}
                          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => updateRecipient(index, "personal_description", e.target.value)}
                          placeholder="Personal interests/preferences for AI personalization"
                          rows={2}
                          className="text-xs bg-slate-600/50 border-slate-500 text-white placeholder:text-slate-400 focus:border-violet-500 resize-none"
                        />
                      </div>
                    </div>
                  ))}
                </div>

                {formData.recipients.length === 0 && (
                  <div className="text-center py-6 text-slate-500 border border-slate-600 rounded bg-slate-700/30">
                    <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    <p className="text-xs">No recipients added yet</p>
                    <p className="text-xs">Click &quot;Add&quot; to add email recipients</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Empty space to maintain card height */}
          <div className="h-10"></div>
        </CardContent>

        {/* Output Handle */}
        <Handle
          type="source"
          position={Position.Right}
          id="campaign_results"
          className="w-4 h-4 border-2 border-slate-900 shadow-md"
          style={{ 
            top: 120,
            backgroundColor: "#8b5cf6"
          }}
        />
      </Card>
      
      {/* Handle Labels - Show when selected or during connection */}
      {(isSelected || isConnectionActive) && (
        <>
          {/* Input Label */}
          <div 
            className={`absolute text-xs px-2 py-1 rounded shadow-lg border text-right transition-all duration-200 whitespace-nowrap ${
              compatibleHandles.includes('campaign_description')
                ? 'bg-green-500 border-green-600 text-white font-semibold animate-pulse scale-110' 
                : isConnectionActive
                ? 'bg-slate-800/90 backdrop-blur-sm border-slate-700 text-slate-400'
                : 'bg-slate-800/90 backdrop-blur-sm text-slate-200 border-slate-700'
            }`}
            style={{ 
              top: '108px',
              right: 'calc(100% + 12px)',
            }}
          >
            campaign description
          </div>
          
          {/* Output Label */}
          <div 
            className={`absolute text-xs px-2 py-1 rounded shadow-lg border text-left transition-all duration-200 whitespace-nowrap ${
              isConnectionSource && connectionPreview?.sourceHandle === 'campaign_results'
                ? 'bg-violet-500 border-violet-600 text-white font-semibold ring-2 ring-violet-400'
                : isConnectionActive
                ? 'bg-slate-800/90 backdrop-blur-sm border-slate-700 text-slate-400'
                : 'bg-slate-800/90 backdrop-blur-sm text-slate-200 border-slate-700'
            }`}
            style={{ 
              top: '108px',
              left: 'calc(100% + 12px)',
            }}
          >
            campaign results
          </div>
        </>
      )}
      
      {/* Output Viewer Modal */}
      {showOutputViewer && executionResult && executionResult.execution_status === 'success' && (
        <OutputViewer
          moduleName={data.module_name}
          result={executionResult}
          onClose={() => setShowOutputViewer(false)}
        />
      )}

      <style jsx global>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: rgba(71, 85, 105, 0.1);
          border-radius: 3px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(139, 92, 246, 0.3);
          border-radius: 3px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(139, 92, 246, 0.5);
        }
      `}</style>
    </div>
  );
};

EmailSenderNodeComponent.displayName = 'EmailSenderNode';

export const EmailSenderNode = memo(EmailSenderNodeComponent);
