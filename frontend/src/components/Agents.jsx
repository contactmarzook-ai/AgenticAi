import React, { useState, useEffect } from 'react';
import { Bot, Plus, X, Search, Code, CheckCircle, Clock, Trash2 } from 'lucide-react';
import api from '../store/api';
import { useAuthStore } from '../store/authStore';

export default function Agents() {
  const [agents, setAgents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const user = useAuthStore((state) => state.user);

  // Form State
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    trigger_keywords: '',
    python_code: 'output["status"] = "success"\noutput["message"] = "Hello from Agent!"\n',
  });
  const [schemaFields, setSchemaFields] = useState([{ key: '', type: 'string', required: false }]);

  useEffect(() => {
    fetchAgents();
  }, []);

  const fetchAgents = async () => {
    try {
      const res = await api.get('/agents');
      setAgents(res.data);
    } catch (err) {
      console.error("Failed to load agents", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCreateAgent = async (e) => {
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

      await api.post('/agents', {
          ...formData,
          input_schema: schemaObj,
          is_active: true
      });
      setIsModalOpen(false);
      fetchAgents();
    } catch (err) {
      console.error(err);
      alert("Failed to create agent");
    }
  };

  const addSchemaField = () => {
    setSchemaFields([...schemaFields, { key: '', type: 'string', required: false }]);
  };

  const updateSchemaField = (index, field, value) => {
    const newFields = [...schemaFields];
    newFields[index][field] = value;
    setSchemaFields(newFields);
  };

  const removeSchemaField = (index) => {
    const newFields = schemaFields.filter((_, i) => i !== index);
    setSchemaFields(newFields);
  };

  return (
    <div className="flex flex-col h-full bg-gray-50 overflow-hidden">

      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-8 py-6 flex-shrink-0 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="bg-indigo-100 p-2 rounded-lg">
            <Bot className="w-6 h-6 text-indigo-600" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Agents</h1>
            <p className="text-sm text-gray-500 mt-1">Manage AI agents and their execution scripts</p>
          </div>
        </div>
        {user?.role === 'admin' && (
            <button
                onClick={() => setIsModalOpen(true)}
                className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg shadow-sm transition-colors text-sm font-medium"
            >
                <Plus className="w-4 h-4" /> Create Agent
            </button>
        )}
      </div>

      {/* Main Content (Grid) */}
      <div className="flex-1 overflow-y-auto p-8">
         <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {agents.map(agent => (
                <div key={agent.id} className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow p-6 flex flex-col h-full">
                    <div className="flex justify-between items-start mb-4">
                        <div className="flex items-center gap-3">
                            <div className="bg-gray-100 p-2.5 rounded-lg border border-gray-200">
                                <Code className="w-5 h-5 text-gray-600" />
                            </div>
                            <h3 className="font-semibold text-gray-900 text-lg">{agent.name}</h3>
                        </div>
                        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${agent.is_active ? 'bg-green-50 text-green-700 border-green-200' : 'bg-gray-50 text-gray-600 border-gray-200'}`}>
                            <CheckCircle className="w-3 h-3" />
                            {agent.is_active ? 'Active' : 'Inactive'}
                        </span>
                    </div>

                    <p className="text-sm text-gray-600 flex-1 mb-6 leading-relaxed">
                        {agent.description || 'No description provided.'}
                    </p>

                    <div className="mt-auto space-y-4">
                        {agent.trigger_keywords && (
                            <div>
                                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Triggers</p>
                                <div className="flex flex-wrap gap-2">
                                    {agent.trigger_keywords.split(',').map((kw, i) => (
                                        <span key={i} className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-100">
                                            {kw.trim()}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}
                        <div className="pt-4 border-t border-gray-100 flex items-center justify-between text-xs text-gray-500">
                            <div className="flex items-center gap-1.5">
                                <Clock className="w-3.5 h-3.5" />
                                {new Date(agent.created_at).toLocaleDateString()}
                            </div>
                            <span>ID: {agent.id}</span>
                        </div>
                    </div>
                </div>
            ))}
         </div>
      </div>

      {/* Creation Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-gray-900/50 flex justify-end z-50">
            <div className="w-full max-w-2xl bg-white h-full shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50">
                    <h2 className="text-lg font-semibold text-gray-900">Create New Agent</h2>
                    <button onClick={() => setIsModalOpen(false)} className="text-gray-400 hover:text-gray-600 transition-colors p-2 rounded-full hover:bg-gray-200">
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <div className="flex-1 overflow-y-auto p-6">
                    <form id="agent-form" onSubmit={handleCreateAgent} className="space-y-6">
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
                                        <input
                                            type="text"
                                            placeholder="Key name"
                                            value={field.key}
                                            onChange={(e) => updateSchemaField(index, 'key', e.target.value)}
                                            className="flex-1 border border-gray-300 rounded shadow-sm px-2 py-1.5 text-sm focus:ring-indigo-500 focus:border-indigo-500"
                                        />
                                        <select
                                            value={field.type}
                                            onChange={(e) => updateSchemaField(index, 'type', e.target.value)}
                                            className="w-28 border border-gray-300 rounded shadow-sm px-2 py-1.5 text-sm focus:ring-indigo-500 focus:border-indigo-500 bg-white"
                                        >
                                            <option value="string">String</option>
                                            <option value="number">Number</option>
                                            <option value="boolean">Boolean</option>
                                        </select>
                                        <label className="flex items-center gap-1.5 text-sm text-gray-600">
                                            <input
                                                type="checkbox"
                                                checked={field.required}
                                                onChange={(e) => updateSchemaField(index, 'required', e.target.checked)}
                                                className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                                            />
                                            Req
                                        </label>
                                        <button
                                            type="button"
                                            onClick={() => removeSchemaField(index)}
                                            className="text-gray-400 hover:text-red-500 p-1"
                                        >
                                            <Trash2 className="w-4 h-4" />
                                        </button>
                                    </div>
                                ))}
                                <button
                                    type="button"
                                    onClick={addSchemaField}
                                    className="text-sm text-indigo-600 font-medium flex items-center gap-1 hover:text-indigo-700"
                                >
                                    <Plus className="w-4 h-4" /> Add Field
                                </button>
                            </div>
                        </div>
                        <div>
                            <div className="flex justify-between items-center mb-1">
                                <label className="block text-sm font-medium text-gray-700">Python Script</label>
                                <span className="text-[10px] uppercase font-bold text-gray-400">Execution Context</span>
                            </div>
                            <p className="text-xs text-gray-500 mb-2">Write standard Python. Variables <code className="bg-gray-100 px-1 rounded">params</code> (input dict) and <code className="bg-gray-100 px-1 rounded">output</code> (output dict) are pre-injected.</p>
                            <textarea
                                required
                                value={formData.python_code}
                                onChange={e => setFormData({...formData, python_code: e.target.value})}
                                rows={12}
                                className="w-full font-mono text-sm border border-gray-800 rounded-md shadow-inner px-4 py-3 bg-[#0D1117] text-gray-300 focus:ring-indigo-500 focus:border-indigo-500"
                                spellCheck="false"
                            />
                        </div>
                    </form>
                </div>

                <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 flex justify-end gap-3">
                    <button type="button" onClick={() => setIsModalOpen(false)} className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 bg-white hover:bg-gray-50 transition-colors shadow-sm">
                        Cancel
                    </button>
                    <button type="submit" form="agent-form" className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 transition-colors">
                        Save Agent
                    </button>
                </div>
            </div>
        </div>
      )}

    </div>
  );
}
