import React, { useState, useEffect } from 'react';
import { Workflow, Plus, X, ArrowRight, Save, Trash2, CheckCircle } from 'lucide-react';
import api from '../store/api';
import { useAuthStore } from '../store/authStore';

export default function Workflows() {
  const [workflows, setWorkflows] = useState([]);
  const [agents, setAgents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isBuilderOpen, setIsBuilderOpen] = useState(false);
  const user = useAuthStore((state) => state.user);

  // Builder State
  const [workflowName, setWorkflowName] = useState('');
  const [workflowDesc, setWorkflowDesc] = useState('');
  const [steps, setSteps] = useState([null]); // Array of selected Agent IDs

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [wfRes, agRes] = await Promise.all([
        api.get('/workflows'),
        api.get('/agents')
      ]);
      setWorkflows(wfRes.data);
      setAgents(agRes.data);
    } catch (err) {
      console.error("Failed to load data", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAddStep = () => setSteps([...steps, null]);
  const handleRemoveStep = (idx) => setSteps(steps.filter((_, i) => i !== idx));

  const handleStepChange = (idx, agentId) => {
    const newSteps = [...steps];
    newSteps[idx] = parseInt(agentId, 10);
    setSteps(newSteps);
  };

  const handleSaveWorkflow = async () => {
    // Validate
    if (!workflowName) return alert("Workflow needs a name");
    if (steps.some(s => s === null || isNaN(s))) return alert("All steps must have an agent selected");

    try {
      await api.post('/workflows', {
        name: workflowName,
        description: workflowDesc,
        steps_json: steps
      });
      setIsBuilderOpen(false);

      // Reset builder
      setWorkflowName('');
      setWorkflowDesc('');
      setSteps([null]);

      fetchData();
    } catch (err) {
      console.error(err);
      alert("Failed to save workflow");
    }
  };

  const handleDelete = async (id) => {
      try {
          await api.delete(`/workflows/${id}`);
          fetchData();
      } catch (err) {
          console.error(err);
          alert("Failed to delete workflow");
      }
  };

  return (
    <div className="flex flex-col h-full bg-gray-50 overflow-hidden relative">

      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-8 py-6 flex-shrink-0 flex justify-between items-center z-10 relative">
        <div className="flex items-center gap-3">
          <div className="bg-indigo-100 p-2 rounded-lg">
            <Workflow className="w-6 h-6 text-indigo-600" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Workflows</h1>
            <p className="text-sm text-gray-500 mt-1">Design and manage multi-agent execution pipelines</p>
          </div>
        </div>
        <button
            onClick={() => setIsBuilderOpen(true)}
            className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg shadow-sm transition-colors text-sm font-medium"
        >
            <Plus className="w-4 h-4" /> Create Workflow
        </button>
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto p-8 z-0">
          {workflows.length === 0 && !isLoading && (
              <div className="text-center py-20 text-gray-500">
                  <Workflow className="w-12 h-12 mx-auto mb-4 text-gray-300" />
                  <p>No workflows created yet. Build your first pipeline!</p>
              </div>
          )}
         <div className="space-y-4">
            {workflows.map(wf => (
                <div key={wf.id} className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 flex items-center justify-between group">
                    <div>
                        <h3 className="font-semibold text-gray-900 text-lg mb-1">{wf.name}</h3>
                        <p className="text-sm text-gray-600 mb-4">{wf.description}</p>

                        {/* Visual Step Display */}
                        <div className="flex items-center flex-wrap gap-2">
                            {wf.steps_json.map((agentId, idx) => {
                                const agent = agents.find(a => a.id === agentId);
                                return (
                                    <React.Fragment key={idx}>
                                        <div className="bg-gray-100 border border-gray-200 px-3 py-1.5 rounded-md text-sm font-medium text-gray-700 flex items-center gap-2 shadow-sm">
                                            <span className="bg-white text-gray-500 text-xs w-5 h-5 flex items-center justify-center rounded-full border border-gray-200">{idx + 1}</span>
                                            {agent ? agent.name : `Unknown Agent (${agentId})`}
                                        </div>
                                        {idx < wf.steps_json.length - 1 && (
                                            <ArrowRight className="w-4 h-4 text-gray-400 mx-1" />
                                        )}
                                    </React.Fragment>
                                )
                            })}
                        </div>
                    </div>
                    <button
                        onClick={() => handleDelete(wf.id)}
                        className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                    >
                        <Trash2 className="w-5 h-5" />
                    </button>
                </div>
            ))}
         </div>
      </div>

      {/* Workflow Builder Full Screen Overlay */}
      {isBuilderOpen && (
        <div className="absolute inset-0 bg-gray-50 z-50 flex flex-col animate-in fade-in duration-200">
            {/* Builder Header */}
            <div className="bg-white border-b border-gray-200 px-8 py-4 flex justify-between items-center shadow-sm">
                <div className="flex items-center gap-3">
                    <button onClick={() => setIsBuilderOpen(false)} className="text-gray-400 hover:text-gray-600 transition-colors p-1.5 rounded-md hover:bg-gray-100 mr-2">
                        <X className="w-5 h-5" />
                    </button>
                    <h2 className="text-lg font-semibold text-gray-900">Pipeline Builder</h2>
                </div>
                <button
                    onClick={handleSaveWorkflow}
                    className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2 rounded-lg shadow-sm transition-colors text-sm font-medium"
                >
                    <Save className="w-4 h-4" /> Save Pipeline
                </button>
            </div>

            {/* Builder Canvas */}
            <div className="flex-1 overflow-y-auto p-8 max-w-5xl mx-auto w-full">

                {/* Meta Config */}
                <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm mb-8 space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Workflow Name</label>
                        <input type="text" value={workflowName} onChange={e => setWorkflowName(e.target.value)} className="w-full border border-gray-300 rounded-md shadow-sm px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500 text-lg font-medium" placeholder="e.g., Financial Report Generator" />
                    </div>
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                        <input type="text" value={workflowDesc} onChange={e => setWorkflowDesc(e.target.value)} className="w-full border border-gray-300 rounded-md shadow-sm px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm" placeholder="What does this pipeline accomplish?" />
                    </div>
                </div>

                {/* Steps Configurator */}
                <div className="space-y-6">
                    <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider pl-2">Execution Sequence</h3>

                    {steps.map((step, idx) => (
                        <div key={idx} className="relative flex items-start gap-4">
                            {/* Visual Connector Line */}
                            {idx !== steps.length - 1 && (
                                <div className="absolute left-6 top-14 bottom-[-24px] w-0.5 bg-indigo-200"></div>
                            )}

                            {/* Step Node */}
                            <div className="flex-shrink-0 w-12 h-12 bg-white border-2 border-indigo-200 rounded-full flex items-center justify-center shadow-sm z-10 text-indigo-700 font-bold">
                                {idx + 1}
                            </div>

                            {/* Step Content */}
                            <div className="flex-1 bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex items-center gap-4">
                                <div className="flex-1">
                                    <label className="block text-xs font-medium text-gray-500 mb-1 uppercase tracking-wide">
                                        {idx === 0 ? "Initial Input Agent" : idx === steps.length - 1 ? "Final Output Agent" : "Intermediate Processor"}
                                    </label>
                                    <select
                                        value={step || ''}
                                        onChange={(e) => handleStepChange(idx, e.target.value)}
                                        className="w-full border border-gray-300 rounded-md shadow-sm px-3 py-2.5 focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm bg-gray-50 font-medium text-gray-800"
                                    >
                                        <option value="" disabled>Select an Agent...</option>
                                        {agents.map(ag => (
                                            <option key={ag.id} value={ag.id}>{ag.name}</option>
                                        ))}
                                    </select>
                                </div>

                                {steps.length > 1 && (
                                    <button onClick={() => handleRemoveStep(idx)} className="p-2 text-gray-400 hover:text-red-600 transition-colors rounded-md hover:bg-red-50 mt-5">
                                        <X className="w-5 h-5" />
                                    </button>
                                )}
                            </div>
                        </div>
                    ))}

                    {/* Add Step Button */}
                    <div className="relative flex items-start gap-4 pt-2">
                        <div className="flex-shrink-0 w-12 flex justify-center z-10">
                            <button onClick={handleAddStep} className="w-8 h-8 bg-indigo-100 hover:bg-indigo-200 border border-indigo-200 rounded-full flex items-center justify-center transition-colors text-indigo-600 shadow-sm">
                                <Plus className="w-5 h-5" />
                            </button>
                        </div>
                        <div className="flex-1 pt-1">
                            <span className="text-sm font-medium text-gray-500">Add Next Step</span>
                        </div>
                    </div>

                </div>
            </div>
        </div>
      )}

    </div>
  );
}
