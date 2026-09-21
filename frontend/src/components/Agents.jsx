import React, { useState, useEffect } from 'react';
import { Bot, Plus, X, Search, Code, CheckCircle, Clock, Trash2 } from 'lucide-react';
import api from '../store/api';
import { useAuthStore } from '../store/authStore';

export default function Agents() {
  const [agents, setAgents] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const user = useAuthStore((state) => state.user);

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

  return (
    <div className="flex flex-col h-full bg-gray-50 overflow-hidden">

      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-8 py-6 flex-shrink-0 flex justify-between items-center">
        <div className="flex items-center gap-3">
          <div className="bg-indigo-100 p-2 rounded-lg">
            <Bot className="w-6 h-6 text-indigo-600" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Agents Discoverability</h1>
            <p className="text-sm text-gray-500 mt-1">Discover available AI agents on the platform.</p>
          </div>
        </div>
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

    </div>
  );
}
