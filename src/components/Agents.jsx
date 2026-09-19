import React, { useState } from 'react';
import { Bot, FileText, Database, Activity, Code, Settings2, Play, Search, X } from 'lucide-react';

const mockAgents = [
  {
    id: 1,
    name: 'NOC Generator',
    description: 'Generates No Objection Certificates for employee travel or external requests based on context.',
    status: 'active',
    keywords: ['noc', 'certificate', 'objection', 'travel letter'],
    icon: FileText,
    script: 'generate_noc.py'
  },
  {
    id: 2,
    name: 'Data Analyzer',
    description: 'Processes CSV/Excel files and provides statistical summaries and insights.',
    status: 'active',
    keywords: ['analyze', 'data', 'stats', 'csv', 'excel'],
    icon: Database,
    script: 'analyze_data.py'
  },
  {
    id: 3,
    name: 'System Monitor',
    description: 'Checks health of internal services and generates incident reports.',
    status: 'inactive',
    keywords: ['health', 'status', 'monitor', 'incident'],
    icon: Activity,
    script: 'check_health.py'
  }
];

export default function Agents() {
  const [selectedAgent, setSelectedAgent] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  const filteredAgents = mockAgents.filter(agent =>
    agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    agent.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">

      {/* Main Content Area */}
      <div className={`flex-1 flex flex-col transition-all duration-300 ${selectedAgent ? 'mr-96' : ''}`}>

        {/* Header */}
        <div className="bg-white border-b border-gray-200 px-8 py-6">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-2xl font-semibold text-gray-800">Agents & Workflows</h2>
              <p className="text-sm text-gray-500 mt-1">Manage agent configurations and underlying scripts</p>
            </div>
            <button className="bg-indigo-600 text-white px-4 py-2 rounded-lg hover:bg-indigo-700 transition-colors font-medium text-sm flex items-center gap-2">
              <Bot className="w-4 h-4" />
              New Agent
            </button>
          </div>

          {/* Search */}
          <div className="mt-6 relative max-w-md">
            <Search className="w-5 h-5 absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="Search agents..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-all text-sm"
            />
          </div>
        </div>

        {/* Agents Grid */}
        <div className="flex-1 overflow-y-auto p-8">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredAgents.map(agent => (
              <div
                key={agent.id}
                onClick={() => setSelectedAgent(agent)}
                className={`bg-white rounded-xl border ${selectedAgent?.id === agent.id ? 'border-indigo-500 ring-1 ring-indigo-500' : 'border-gray-200'} p-6 cursor-pointer hover:shadow-md transition-all group`}
              >
                <div className="flex justify-between items-start mb-4">
                  <div className={`p-3 rounded-lg ${selectedAgent?.id === agent.id ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-50 text-gray-600 group-hover:bg-indigo-50 group-hover:text-indigo-600'} transition-colors`}>
                    <agent.icon className="w-6 h-6" />
                  </div>
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    agent.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'
                  }`}>
                    {agent.status}
                  </span>
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-2">{agent.name}</h3>
                <p className="text-sm text-gray-500 line-clamp-2 mb-4">{agent.description}</p>

                <div className="flex flex-wrap gap-1.5 mt-auto">
                  {agent.keywords.slice(0, 3).map(kw => (
                    <span key={kw} className="px-2 py-1 bg-gray-50 text-gray-500 rounded text-xs border border-gray-100">
                      {kw}
                    </span>
                  ))}
                  {agent.keywords.length > 3 && (
                    <span className="px-2 py-1 bg-gray-50 text-gray-500 rounded text-xs border border-gray-100">
                      +{agent.keywords.length - 3}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Slide-over Editor Panel */}
      <div
        className={`fixed inset-y-0 right-0 w-[500px] bg-white border-l border-gray-200 shadow-2xl transform transition-transform duration-300 ease-in-out z-20 flex flex-col ${
          selectedAgent ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {selectedAgent && (
          <>
            {/* Panel Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-white">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
                  <selectedAgent.icon className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-semibold text-gray-900">{selectedAgent.name}</h3>
                  <p className="text-xs text-gray-500">Configuration & Script</p>
                </div>
              </div>
              <button
                onClick={() => setSelectedAgent(null)}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Panel Content */}
            <div className="flex-1 overflow-y-auto">

              {/* Configuration Section */}
              <div className="p-6 border-b border-gray-100">
                <h4 className="text-sm font-semibold text-gray-900 flex items-center gap-2 mb-4">
                  <Settings2 className="w-4 h-4 text-gray-500" />
                  Agent Settings
                </h4>
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Description</label>
                    <textarea
                      className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      rows="2"
                      defaultValue={selectedAgent.description}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">LLM System Instructions</label>
                    <textarea
                      className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:outline-none"
                      rows="3"
                      defaultValue={`Extract necessary entities (name, destination, dates) for NOC generation. Return JSON format.`}
                    />
                  </div>
                </div>
              </div>

              {/* I/O Mapping Section */}
              <div className="p-6 border-b border-gray-100 bg-gray-50/50">
                <h4 className="text-sm font-semibold text-gray-900 flex items-center gap-2 mb-4">
                  <Activity className="w-4 h-4 text-gray-500" />
                  I/O Parameters
                </h4>
                <div className="bg-white border border-gray-200 rounded-lg p-4 space-y-3">
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-mono bg-gray-100 px-2 py-1 rounded text-gray-600">context.name</span>
                    <span className="text-gray-400 text-xs">→</span>
                    <span className="text-xs font-mono bg-indigo-50 text-indigo-700 px-2 py-1 rounded">args.employee_name</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs font-mono bg-gray-100 px-2 py-1 rounded text-gray-600">context.destination</span>
                    <span className="text-gray-400 text-xs">→</span>
                    <span className="text-xs font-mono bg-indigo-50 text-indigo-700 px-2 py-1 rounded">args.travel_dest</span>
                  </div>
                </div>
              </div>

              {/* Code Editor Section */}
              <div className="p-6 flex-1 flex flex-col min-h-[300px]">
                <div className="flex items-center justify-between mb-4">
                  <h4 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
                    <Code className="w-4 h-4 text-gray-500" />
                    Execution Script
                  </h4>
                  <span className="text-xs font-mono text-gray-500">{selectedAgent.script}</span>
                </div>

                <div className="flex-1 bg-[#1e1e1e] rounded-lg border border-gray-800 overflow-hidden flex flex-col">
                  <div className="flex items-center justify-between px-4 py-2 bg-[#2d2d2d] border-b border-gray-800">
                    <div className="flex gap-1.5">
                       <div className="w-2.5 h-2.5 rounded-full bg-gray-600"></div>
                       <div className="w-2.5 h-2.5 rounded-full bg-gray-600"></div>
                       <div className="w-2.5 h-2.5 rounded-full bg-gray-600"></div>
                    </div>
                    <button className="text-xs text-gray-400 hover:text-white flex items-center gap-1 transition-colors">
                      <Play className="w-3 h-3" /> Run Test
                    </button>
                  </div>
                  <div className="p-4 overflow-auto">
                    <pre className="text-xs font-mono text-gray-300 leading-relaxed">
<span className="text-pink-400">import</span> sys{'\n'}
<span className="text-pink-400">import</span> json{'\n'}
<span className="text-pink-400">from</span> document_gen <span className="text-pink-400">import</span> PDFGenerator{'\n\n'}
<span className="text-blue-400">def</span> <span className="text-yellow-200">generate_noc</span>(args):{'\n'}
{'    '}data = json.loads(args){'\n'}
{'    '}name = data.get(<span className="text-green-300">'employee_name'</span>){'\n'}
{'    '}dest = data.get(<span className="text-green-300">'travel_dest'</span>){'\n\n'}
{'    '}print(<span className="text-green-300">f"[INFO] Generating NOC for {'{name}'}"</span>){'\n'}
{'    '}generator = PDFGenerator(template=<span className="text-green-300">'noc_std'</span>){'\n'}
{'    '}output = generator.build(name=name, dest=dest){'\n\n'}
{'    '}<span className="text-pink-400">return</span> output{'\n\n'}
<span className="text-pink-400">if</span> __name__ == <span className="text-green-300">"__main__"</span>:{'\n'}
{'    '}res = generate_noc(sys.argv[<span className="text-purple-300">1</span>]){'\n'}
{'    '}print(<span className="text-green-300">f"[SUCCESS] Saved to {'{res}'}"</span>)
                    </pre>
                  </div>
                </div>
              </div>

            </div>

            {/* Panel Footer */}
            <div className="p-4 border-t border-gray-200 bg-gray-50 flex justify-end gap-3">
              <button
                onClick={() => setSelectedAgent(null)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors">
                Save Changes
              </button>
            </div>
          </>
        )}
      </div>

      {/* Overlay for mobile/smaller screens when panel is open */}
      {selectedAgent && (
        <div
          className="fixed inset-0 bg-gray-900/20 backdrop-blur-sm z-10 lg:hidden"
          onClick={() => setSelectedAgent(null)}
        />
      )}
    </div>
  );
}
