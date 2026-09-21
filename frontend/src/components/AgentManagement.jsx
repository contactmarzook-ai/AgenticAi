import React, { useState, useEffect } from 'react';
import { Bot, Plus, X, Trash2, Edit2, Play, Code } from 'lucide-react';
import api from '../store/api';

export default function AgentManagement() {
  const [agents, setAgents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);
  const [testAgentId, setTestAgentId] = useState(null);
  const [testInput, setTestInput] = useState('{}');
  const [testResult, setTestResult] = useState(null);

  // Form State
  const [formData, setFormData] = useState({
    id: null,
    name: '',
    description: '',
    trigger_keywords: '',
    handler: 'default_handler',
    is_active: true
  });
  const [schemaFields, setSchemaFields] = useState([{ key: '', type: 'string', required: false }]);

  useEffect(() => {
    fetchAgents();
  }, []);

  const fetchAgents = async () => {
    try {
      const res = await api.get('/agents'); // assuming admins see all active via this endpoint, or you might need a dedicated admin endpoint to see inactive ones too
      setAgents(res.data);
    } catch (err) {
      console.error("Failed to load agents", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleOpenCreate = () => {
    setFormData({ id: null, name: '', description: '', trigger_keywords: '', handler: 'default_handler', is_active: true });
    setSchemaFields([{ key: '', type: 'string', required: false }]);
    setIsModalOpen(true);
  };

  const handleOpenEdit = (agent) => {
    setFormData({
        id: agent.id,
        name: agent.name,
        description: agent.description,
        trigger_keywords: agent.trigger_keywords,
        handler: agent.handler,
        is_active: agent.is_active
    });

    // Parse schema back into fields
    const fields = [];
    if (agent.input_schema && agent.input_schema.properties) {
        for (const [key, val] of Object.entries(agent.input_schema.properties)) {
            fields.push({
                key: key,
                type: val.type,
                required: (agent.input_schema.required || []).includes(key)
            });
        }
    }
    if (fields.length === 0) fields.push({ key: '', type: 'string', required: false });
    setSchemaFields(fields);
    setIsModalOpen(true);
  };

  const handleSaveAgent = async (e) => {
    e.preventDefault();
    try {
      const schemaObj = {
        type: "object",
        properties: {},
        required: []
      };

      schemaFields.forEach(field => {
        if (field.key) {
          schemaObj.properties[field.key] = { type: field.type };
          if (field.required) {
            schemaObj.required.push(field.key);
          }
        }
      });

      const payload = {
          ...formData,
          input_schema: schemaObj
      };

      if (formData.id) {
          await api.put(`/agents/${formData.id}`, payload);
      } else {
          await api.post('/agents', payload);
      }

      setIsModalOpen(false);
      fetchAgents();
    } catch (err) {
      console.error(err);
      alert("Failed to save agent");
    }
  };

  const toggleAgentStatus = async (agent) => {
      try {
          await api.put(`/agents/${agent.id}`, { ...agent, is_active: !agent.is_active });
          fetchAgents();
      } catch(err) {
          console.error("Failed to toggle status", err);
      }
  };

  const addSchemaField = () => setSchemaFields([...schemaFields, { key: '', type: 'string', required: false }]);
  const updateSchemaField = (index, field, value) => {
    const newFields = [...schemaFields];
    newFields[index][field] = value;
    setSchemaFields(newFields);
  };
  const removeSchemaField = (index) => setSchemaFields(schemaFields.filter((_, i) => i !== index));

  const handleOpenTest = (id) => {
      setTestAgentId(id);
      setTestInput('{}');
      setTestResult(null);
      setIsTestModalOpen(true);
  };

  const runAgentTest = async () => {
      try {
          let payload = {};
          try {
              payload = JSON.parse(testInput);
          } catch(e) {
              setTestResult({ status: 'error', message: 'Invalid JSON input' });
              return;
          }

          const res = await api.post(`/agents/${testAgentId}/test`, payload);
          setTestResult(res.data);
      } catch (err) {
          setTestResult({ status: 'error', message: err.response?.data?.detail || err.toString() });
      }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden p-8">
        <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-semibold text-gray-800">Registered Agents</h2>
            <button
                onClick={handleOpenCreate}
                className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg shadow-sm transition-colors text-sm font-medium"
            >
                <Plus className="w-4 h-4" /> Register New Agent
            </button>
        </div>

        <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden flex-1 overflow-y-auto">
            <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                    <tr>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Agent</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Handler</th>
                        <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                        <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
                    </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                    {agents.map(agent => (
                        <tr key={agent.id} className="hover:bg-gray-50">
                            <td className="px-6 py-4">
                                <div className="flex items-center gap-3">
                                    <div className="bg-indigo-50 p-2 rounded border border-indigo-100">
                                        <Bot className="w-4 h-4 text-indigo-600" />
                                    </div>
                                    <div>
                                        <p className="text-sm font-medium text-gray-900">{agent.name}</p>
                                        <p className="text-xs text-gray-500 truncate max-w-[200px]">{agent.description}</p>
                                    </div>
                                </div>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                                <span className="px-2.5 py-1 rounded bg-gray-100 text-gray-700 text-xs font-mono border border-gray-200">
                                    {agent.handler}
                                </span>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap">
                                <button
                                    onClick={() => toggleAgentStatus(agent)}
                                    className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${agent.is_active ? 'bg-green-50 text-green-700 border-green-200 hover:bg-green-100' : 'bg-gray-50 text-gray-600 border-gray-200 hover:bg-gray-100'}`}
                                >
                                    {agent.is_active ? 'Active' : 'Inactive'}
                                </button>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium space-x-2">
                                <button onClick={() => handleOpenTest(agent.id)} className="text-indigo-600 hover:text-indigo-900 bg-indigo-50 p-1.5 rounded" title="Test Agent">
                                    <Play className="w-4 h-4" />
                                </button>
                                <button onClick={() => handleOpenEdit(agent)} className="text-gray-600 hover:text-gray-900 bg-gray-100 p-1.5 rounded" title="Edit Agent">
                                    <Edit2 className="w-4 h-4" />
                                </button>
                            </td>
                        </tr>
                    ))}
                    {agents.length === 0 && !isLoading && (
                        <tr><td colSpan="4" className="px-6 py-8 text-center text-gray-500 text-sm">No agents registered.</td></tr>
                    )}
                </tbody>
            </table>
        </div>

        {/* Edit/Create Modal */}
        {isModalOpen && (
        <div className="fixed inset-0 bg-gray-900/50 flex justify-end z-[60]">
            <div className="w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
                    <h2 className="text-lg font-semibold text-gray-900">{formData.id ? 'Edit Agent' : 'Register Agent'}</h2>
                    <button onClick={() => setIsModalOpen(false)} className="text-gray-400 hover:text-gray-600 transition-colors p-2 rounded-full hover:bg-gray-200">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-6">
                    <form id="agent-form" onSubmit={handleSaveAgent} className="space-y-6">
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Agent Name</label>
                            <input required type="text" value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} className="w-full border border-gray-300 rounded-md shadow-sm px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm" placeholder="e.g., DataAnalyzer" />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                            <textarea value={formData.description} onChange={e => setFormData({...formData, description: e.target.value})} rows={3} className="w-full border border-gray-300 rounded-md shadow-sm px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm" placeholder="What does this agent do?" />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Trigger Keywords (Comma separated)</label>
                            <input type="text" value={formData.trigger_keywords} onChange={e => setFormData({...formData, trigger_keywords: e.target.value})} className="w-full border border-gray-300 rounded-md shadow-sm px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm" placeholder="e.g., analyze, parse, report" />
                        </div>
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-2">Input Schema Builder</label>
                            <div className="space-y-3 bg-gray-50 p-4 rounded-md border border-gray-200">
                                {schemaFields.map((field, index) => (
                                    <div key={index} className="flex items-center gap-3">
                                        <input type="text" placeholder="Key name" value={field.key} onChange={(e) => updateSchemaField(index, 'key', e.target.value)} className="flex-1 border border-gray-300 rounded shadow-sm px-2 py-1.5 text-sm focus:ring-indigo-500 focus:border-indigo-500" />
                                        <select value={field.type} onChange={(e) => updateSchemaField(index, 'type', e.target.value)} className="w-28 border border-gray-300 rounded shadow-sm px-2 py-1.5 text-sm focus:ring-indigo-500 focus:border-indigo-500 bg-white">
                                            <option value="string">String</option>
                                            <option value="number">Number</option>
                                            <option value="boolean">Boolean</option>
                                        </select>
                                        <label className="flex items-center gap-1.5 text-sm text-gray-600">
                                            <input type="checkbox" checked={field.required} onChange={(e) => updateSchemaField(index, 'required', e.target.checked)} className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500" />
                                            Req
                                        </label>
                                        <button type="button" onClick={() => removeSchemaField(index)} className="text-gray-400 hover:text-red-500 p-1"><Trash2 className="w-4 h-4" /></button>
                                    </div>
                                ))}
                                <button type="button" onClick={addSchemaField} className="text-sm text-indigo-600 font-medium flex items-center gap-1 hover:text-indigo-700"><Plus className="w-4 h-4" /> Add Field</button>
                            </div>
                        </div>
                        <div>
                            <div className="flex justify-between items-center mb-1">
                                <label className="block text-sm font-medium text-gray-700">Agent Handler</label>
                                <span className="text-[10px] uppercase font-bold text-gray-400">Registry Binding</span>
                            </div>
                            <p className="text-xs text-gray-500 mb-2">Select the registered python function that powers this agent.</p>
                            <select
                                required
                                value={formData.handler}
                                onChange={e => setFormData({...formData, handler: e.target.value})}
                                className="w-full border border-gray-300 rounded-md shadow-sm px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm bg-white"
                            >
                                <option value="mock_noc_generator">mock_noc_generator</option>
                                <option value="mock_data_analyzer">mock_data_analyzer</option>
                                <option value="default_handler">default_handler</option>
                            </select>
                        </div>
                    </form>
                </div>

                <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 flex justify-end gap-3">
                    <button type="button" onClick={() => setIsModalOpen(false)} className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 transition-colors shadow-sm">Cancel</button>
                    <button type="submit" form="agent-form" className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 transition-colors">Save Agent</button>
                </div>
            </div>
        </div>
      )}

      {/* Test Modal */}
      {isTestModalOpen && (
         <div className="fixed inset-0 bg-gray-900/50 flex justify-center items-center z-[70] p-4">
            <div className="bg-white rounded-xl shadow-xl w-full max-w-lg overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-200">
                <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center bg-gray-50">
                    <h3 className="font-semibold text-gray-900 flex items-center gap-2"><Play className="w-4 h-4 text-indigo-600"/> Test Agent Execution</h3>
                    <button onClick={() => setIsTestModalOpen(false)} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5"/></button>
                </div>
                <div className="p-6 space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Input Parameters (JSON)</label>
                        <textarea
                            value={testInput}
                            onChange={e => setTestInput(e.target.value)}
                            rows={4}
                            className="w-full font-mono text-sm border border-gray-300 rounded-md shadow-sm px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500"
                        />
                    </div>
                    <button onClick={runAgentTest} className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-2 rounded-md transition-colors">
                        Execute
                    </button>

                    {testResult && (
                        <div className={`p-4 rounded-md border text-sm overflow-x-auto ${testResult.status === 'error' ? 'bg-red-50 border-red-200 text-red-800' : 'bg-gray-50 border-gray-200 text-gray-800'}`}>
                            <pre className="whitespace-pre-wrap font-mono text-xs">{JSON.stringify(testResult, null, 2)}</pre>
                        </div>
                    )}
                </div>
            </div>
         </div>
      )}

    </div>
  );
}
