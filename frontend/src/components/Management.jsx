import React, { useState } from 'react';
import { ShieldCog, LayoutDashboard, Activity, GitMerge } from 'lucide-react';
import Monitoring from './Monitoring';
import AgentManagement from './AgentManagement';
import WorkflowBuilder from './management/WorkflowBuilder';
import WorkflowList from './management/WorkflowList';

export default function Management() {
  const [activeSubTab, setActiveSubTab] = useState('agents');
  const [editingWorkflowId, setEditingWorkflowId] = useState(null);

  return (
    <div className="flex flex-col h-full bg-gray-50 overflow-hidden">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-8 py-6 flex-shrink-0">
        <div className="flex items-center gap-3 mb-6">
          <div className="bg-indigo-100 p-2 rounded-lg">
            <ShieldCog className="w-6 h-6 text-indigo-600" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold text-gray-900">Platform Management</h1>
            <p className="text-sm text-gray-500 mt-1">Admin-only controls and observability.</p>
          </div>
        </div>

        {/* Sub-navigation */}
        <div className="flex border-b border-gray-200">
          <button
            onClick={() => setActiveSubTab('agents')}
            className={`flex items-center gap-2 px-6 py-3 font-medium text-sm transition-colors border-b-2 ${
              activeSubTab === 'agents'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <LayoutDashboard className="w-4 h-4" /> Agent Management
          </button>
          <button
            onClick={() => setActiveSubTab('workflows_list')}
            className={`flex items-center gap-2 px-6 py-3 font-medium text-sm transition-colors border-b-2 ${
              activeSubTab === 'workflows_list' || activeSubTab === 'workflows_builder'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <GitMerge className="w-4 h-4" /> Workflows
          </button>
          <button
            onClick={() => setActiveSubTab('monitoring')}
            className={`flex items-center gap-2 px-6 py-3 font-medium text-sm transition-colors border-b-2 ${
              activeSubTab === 'monitoring'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
          >
            <Activity className="w-4 h-4" /> Execution Monitoring
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-hidden relative">
        {activeSubTab === 'agents' && <AgentManagement />}
        {activeSubTab === 'workflows_list' && <WorkflowList onOpenBuilder={(id) => { setEditingWorkflowId(id || null); setActiveSubTab('workflows_builder'); }} />}
        {activeSubTab === 'workflows_builder' && <WorkflowBuilder workflowId={editingWorkflowId} onBack={() => setActiveSubTab('workflows_list')} />}
        {activeSubTab === 'monitoring' && <Monitoring embedded={true} />}
      </div>
    </div>
  );
}
