import React, { useState, useEffect } from 'react';
import { GitMerge, Plus, Play, Tag } from 'lucide-react';
import api from '../../store/api';

export default function WorkflowList({ onOpenBuilder }) {
    const [workflows, setWorkflows] = useState([]);

    useEffect(() => {
        fetchWorkflows();
    }, []);

    const fetchWorkflows = async () => {
        try {
            const res = await api.get('/workflows');
            // Group by group_id
            const grouped = {};
            res.data.forEach(wf => {
                if (!grouped[wf.group_id]) grouped[wf.group_id] = [];
                grouped[wf.group_id].push(wf);
            });
            setWorkflows(Object.values(grouped));
        } catch (e) {
            console.error(e);
        }
    };

    return (
        <div className="p-8 h-full overflow-y-auto">
            <div className="flex justify-between items-center mb-6">
                <div>
                    <h2 className="text-xl font-bold text-gray-900">Workflows</h2>
                    <p className="text-sm text-gray-500">Manage workflow versions and drafts.</p>
                </div>
                <button onClick={onOpenBuilder} className="bg-indigo-600 text-white px-4 py-2 rounded flex items-center gap-2 hover:bg-indigo-700">
                    <Plus className="w-4 h-4"/> New Workflow
                </button>
            </div>

            <div className="space-y-6">
                {workflows.map((group, idx) => {
                    const active = group.find(w => w.status === 'active');
                    const drafts = group.filter(w => w.status === 'draft');
                    const latest = group[0];
                    return (
                        <div key={idx} className="bg-white border rounded-xl shadow-sm p-5">
                            <div className="flex justify-between items-start mb-4">
                                <div>
                                    <h3 className="font-bold text-lg text-gray-900 flex items-center gap-2">
                                        {latest.name}
                                        {active && <span className="bg-green-100 text-green-800 text-xs px-2 py-0.5 rounded-full font-medium">v{active.version} Active</span>}
                                    </h3>
                                    <p className="text-gray-500 text-sm mt-1">{latest.description}</p>
                                </div>
                                <button onClick={() => onOpenBuilder(latest.id)} className="text-indigo-600 hover:text-indigo-800 text-sm font-medium">
                                    Edit Latest
                                </button>
                            </div>

                            <div className="border-t pt-4 mt-4">
                                <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Version History</h4>
                                <div className="space-y-2">
                                    {group.map(w => (
                                        <div key={w.id} className="flex items-center justify-between bg-gray-50 p-2 rounded border">
                                            <div className="flex items-center gap-3">
                                                <span className="text-sm font-medium text-gray-700">v{w.version}</span>
                                                <span className={`text-xs px-2 py-0.5 rounded-full ${w.status === 'active' ? 'bg-green-100 text-green-700' : w.status === 'draft' ? 'bg-orange-100 text-orange-700' : 'bg-gray-200 text-gray-600'}`}>
                                                    {w.status}
                                                </span>
                                            </div>
                                            <button onClick={() => onOpenBuilder(w.id)} className="text-indigo-600 hover:text-indigo-800 text-xs font-medium">
                                                {w.status === 'draft' ? 'Edit Draft' : 'View / Rollback'}
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    );
                })}
                {workflows.length === 0 && (
                    <div className="text-center py-12 bg-white rounded-xl border">
                        <GitMerge className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                        <p className="text-gray-500">No workflows found. Create one to get started.</p>
                    </div>
                )}
            </div>
        </div>
    );
}
