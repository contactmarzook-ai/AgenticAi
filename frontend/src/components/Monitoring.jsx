import React, { useEffect, useState } from 'react';
import { Activity, Clock, Cpu, CheckCircle, XCircle } from 'lucide-react';
import api from '../store/api';

export default function Monitoring({ embedded = false }) {
  const [logs, setLogs] = useState([]);
  const [metrics, setMetrics] = useState({
      fastPathPercent: 0,
      avgLlmLatency: 0,
      avgAgentTime: 0,
      successRate: 0,
      totalRequests: 0
  });
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchLogs();
  }, []);

  const fetchLogs = async () => {
    try {
      const res = await api.get('/admin/monitoring/logs');
      setLogs(res.data.logs);
      setMetrics(res.data.metrics);
    } catch (err) {
      console.error("Failed to load monitoring logs", err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-gray-50 overflow-hidden">
      {!embedded && (
        <div className="bg-white border-b border-gray-200 px-8 py-6 flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="bg-indigo-100 p-2 rounded-lg">
              <Activity className="w-6 h-6 text-indigo-600" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold text-gray-900">Execution Monitoring</h1>
              <p className="text-sm text-gray-500 mt-1">Admin-only view of routing and execution performance.</p>
            </div>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-8">
          {/* Summary Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
              <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex flex-col">
                  <div className="flex items-center gap-2 mb-2 text-gray-500">
                      <Cpu className="w-4 h-4" />
                      <span className="text-sm font-medium uppercase tracking-wider">Routing</span>
                  </div>
                  <span className="text-2xl font-bold text-gray-900">{metrics.fastPathPercent.toFixed(1)}%</span>
                  <span className="text-xs text-gray-500 mt-1">Fast-path usage</span>
              </div>
              <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex flex-col">
                  <div className="flex items-center gap-2 mb-2 text-gray-500">
                      <Clock className="w-4 h-4" />
                      <span className="text-sm font-medium uppercase tracking-wider">Avg Latency (LLM)</span>
                  </div>
                  <span className="text-2xl font-bold text-gray-900">{metrics.avgLlmLatency.toFixed(2)}s</span>
                  <span className="text-xs text-gray-500 mt-1">Model inference time</span>
              </div>
              <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex flex-col">
                  <div className="flex items-center gap-2 mb-2 text-gray-500">
                      <Clock className="w-4 h-4 text-indigo-500" />
                      <span className="text-sm font-medium uppercase tracking-wider">Avg Execution Time</span>
                  </div>
                  <span className="text-2xl font-bold text-gray-900">{metrics.avgAgentTime.toFixed(2)}s</span>
                  <span className="text-xs text-gray-500 mt-1">Agent processing time</span>
              </div>
              <div className="bg-white p-5 rounded-xl border border-gray-200 shadow-sm flex flex-col">
                  <div className="flex items-center gap-2 mb-2 text-gray-500">
                      <Activity className="w-4 h-4" />
                      <span className="text-sm font-medium uppercase tracking-wider">Success Rate</span>
                  </div>
                  <span className="text-2xl font-bold text-gray-900">{metrics.successRate.toFixed(1)}%</span>
                  <span className="text-xs text-gray-500 mt-1">From {metrics.totalRequests} total requests</span>
              </div>
          </div>

          {/* Logs Table */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-gray-200">
                      <thead className="bg-gray-50">
                          <tr>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Time</th>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User</th>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Request ID</th>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">User Request</th>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Routing Method</th>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Target</th>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Model Used</th>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Duration</th>
                              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                          </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-gray-200">
                          {logs.map((log) => (
                              <tr key={log.id} className="hover:bg-gray-50">
                                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                      {new Date(log.created_at).toLocaleString()}
                                  </td>
                                  <td className="px-6 py-4 text-sm text-gray-900 max-w-xs truncate" title={log.user_request}>
                                      {log.user_request}
                                  </td>
                                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                                      <span className={`px-2 inline-flex text-xs leading-5 font-semibold rounded-full ${log.routing_method === 'fast_path' ? 'bg-green-100 text-green-800' : 'bg-purple-100 text-purple-800'}`}>
                                          {log.routing_method}
                                      </span>
                                  </td>
                                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                      {log.target || 'N/A'}
                                  </td>
                                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                      {log.total_duration ? `${log.total_duration.toFixed(2)}s` : 'N/A'}
                                      {log.llm_duration && <span className="text-xs text-gray-400 block">LLM: {log.llm_duration.toFixed(2)}s</span>}
                                  </td>
                                  <td className="px-6 py-4 whitespace-nowrap">
                                      {log.status === 'success' ? (
                                          <div className="flex items-center gap-1.5 text-green-600">
                                              <CheckCircle className="w-4 h-4" />
                                              <span className="text-sm font-medium">Success</span>
                                          </div>
                                      ) : (
                                          <div className="flex items-center gap-1.5 text-red-600" title={log.error_details}>
                                              <XCircle className="w-4 h-4" />
                                              <span className="text-sm font-medium">Error</span>
                                          </div>
                                      )}
                                  </td>
                              </tr>
                          ))}
                          {logs.length === 0 && !isLoading && (
                              <tr>
                                  <td colSpan="6" className="px-6 py-8 text-center text-gray-500 text-sm">
                                      No execution logs available.
                                  </td>
                              </tr>
                          )}
                      </tbody>
                  </table>
              </div>
          </div>
      </div>
    </div>
  );
}
