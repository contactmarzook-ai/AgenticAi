import React, { useState, useEffect } from 'react';
import { Send, Terminal, Loader2, FileText, ChevronDown, ChevronRight, User, Bot, Route, AlertCircle, X } from 'lucide-react';

const mockMessages = [
  {
    id: 1,
    role: 'user',
    content: 'Generate an NOC for John Doe to travel to Dubai next week.',
  },
  {
    id: 2,
    role: 'system',
    type: 'reasoning',
    content: `1. Analyze user request: "Generate NOC for John Doe to travel to Dubai next week."
2. Intent identified: Document Generation (NOC).
3. Entities extracted:
   - Name: John Doe
   - Destination: Dubai
   - Timeframe: Next week
4. Required action: Route to Document Generation Agent.`,
    isExpanded: false
  },
  {
    id: 3,
    role: 'system',
    type: 'routing',
    agent: 'Document Generation Agent',
  },
  {
    id: 4,
    role: 'system',
    type: 'execution',
    script: 'generate_noc.py',
    logs: [
      '[INFO] Initializing Document Generation Agent...',
      '[INFO] Loading NOC template (standard_travel_noc.docx)...',
      '[INFO] Populating template with context: {name: "John Doe", destination: "Dubai"}',
      '[INFO] Generating PDF...',
      '[SUCCESS] NOC generated successfully: john_doe_noc_dubai.pdf'
    ],
    status: 'completed' // 'running', 'completed'
  },
  {
    id: 5,
    role: 'assistant',
    content: "I've generated the No Objection Certificate (NOC) for John Doe's travel to Dubai.",
    attachment: {
      name: 'john_doe_noc_dubai.pdf',
      size: '124 KB',
      type: 'pdf'
    }
  }
];

export default function Chat() {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState(mockMessages);
  const [isLoading, setIsLoading] = useState(false);
  const [toastError, setToastError] = useState(null);

  useEffect(() => {
    if (toastError) {
      const timer = setTimeout(() => setToastError(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [toastError]);

  const toggleReasoning = (id) => {
    setMessages(messages.map(msg =>
      msg.id === id ? { ...msg, isExpanded: !msg.isExpanded } : msg
    ));
  };

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessageContent = input;
    const newUserMsg = {
      id: Date.now(),
      role: 'user',
      content: userMessageContent
    };

    setMessages(prev => [...prev, newUserMsg]);
    setInput('');
    setIsLoading(true);

    // Show thinking indicator
    const reasoningId = Date.now() + 1;
    setMessages(prev => [...prev, {
      id: reasoningId,
      role: 'system',
      type: 'reasoning',
      content: "Analyzing request with LLM...",
      isExpanded: true,
      status: 'thinking'
    }]);

    try {
      const response = await fetch('http://localhost:8000/api/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: userMessageContent }),
      });

      const data = await response.json();

      // Remove thinking indicator
      setMessages(prev => prev.filter(msg => msg.id !== reasoningId));

      if (data.status === 'error') {
          // Explicit error block
          setMessages(prev => [...prev, {
              id: Date.now() + 2,
              role: 'system',
              type: 'error',
              content: data.message || "An unknown error occurred during orchestration."
          }]);
      } else if (data.status === 'success') {
          // Show routing and execution
          setMessages(prev => [...prev,
              {
                id: Date.now() + 2,
                role: 'system',
                type: 'routing',
                agent: data.action_executed
              },
              {
                id: Date.now() + 3,
                role: 'system',
                type: 'execution',
                script: `${data.action_executed}.py`,
                logs: [`[INFO] Executing ${data.action_executed}...`, `[SUCCESS] ${JSON.stringify(data.result)}`],
                status: 'completed'
              },
              {
                  id: Date.now() + 4,
                  role: 'assistant',
                  content: data.result.message || "Action completed successfully."
              }
          ]);
      } else {
          // Clarification or Error
          setMessages(prev => [...prev, {
              id: Date.now() + 2,
              role: 'assistant',
              content: data.message || "I'm not sure how to handle that."
          }]);
      }

    } catch (error) {
      console.error("Failed to connect to backend:", error);
      setMessages(prev => prev.filter(msg => msg.id !== reasoningId));
      setToastError("Network Error: Could not connect to the orchestrator backend.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 relative">
        <h2 className="text-xl font-semibold text-gray-800">Chat Orchestrator</h2>
        <p className="text-sm text-gray-500">Interact with the agent system to perform tasks</p>

        {/* Toast Notification */}
        {toastError && (
          <div className="absolute top-4 right-6 bg-red-50 text-red-600 border border-red-200 px-4 py-3 rounded-lg shadow-sm flex items-center gap-3 animate-in fade-in slide-in-from-top-2">
             <AlertCircle className="w-5 h-5" />
             <span className="text-sm font-medium">{toastError}</span>
             <button onClick={() => setToastError(null)} className="p-1 hover:bg-red-100 rounded-md transition-colors ml-2">
               <X className="w-4 h-4" />
             </button>
          </div>
        )}
      </div>

      {/* Message Timeline */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {messages.map((msg) => (
          <div key={msg.id} className="flex flex-col">
            {/* User Message */}
            {msg.role === 'user' && (
              <div className="flex items-start gap-4 justify-end">
                <div className="bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-5 py-3 max-w-[80%] shadow-sm">
                  <p className="leading-relaxed">{msg.content}</p>
                </div>
                <div className="bg-indigo-100 p-2 rounded-full mt-1 flex-shrink-0">
                  <User className="w-5 h-5 text-indigo-700" />
                </div>
              </div>
            )}

            {/* Assistant / Final Output Message */}
            {msg.role === 'assistant' && (
              <div className="flex items-start gap-4">
                <div className="bg-white p-2 rounded-full border border-gray-200 mt-1 flex-shrink-0 shadow-sm">
                  <Bot className="w-5 h-5 text-gray-600" />
                </div>
                <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 max-w-[80%] shadow-sm">
                  <p className="text-gray-800 mb-3">{msg.content}</p>
                  {msg.attachment && (
                    <div className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg border border-gray-100 hover:bg-gray-100 transition-colors cursor-pointer">
                      <div className="bg-red-100 p-2 rounded-md">
                        <FileText className="w-5 h-5 text-red-600" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-gray-800">{msg.attachment.name}</p>
                        <p className="text-xs text-gray-500">{msg.attachment.size}</p>
                      </div>
                      <button className="ml-auto text-sm text-indigo-600 font-medium px-3 py-1 rounded bg-indigo-50 hover:bg-indigo-100 transition-colors">
                        Download
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* System / Orchestration Blocks */}
            {msg.role === 'system' && (
              <div className="pl-14 pr-4">

                {/* Reasoning Accordion */}
                {msg.type === 'reasoning' && (
                  <div className="bg-white border border-gray-200 rounded-lg shadow-sm overflow-hidden max-w-2xl">
                    <button
                      onClick={() => toggleReasoning(msg.id)}
                      className="w-full flex items-center justify-between px-4 py-3 bg-gray-50/50 hover:bg-gray-50 transition-colors border-b border-transparent data-[expanded=true]:border-gray-200"
                      data-expanded={msg.isExpanded}
                    >
                      <div className="flex items-center gap-2">
                        {msg.status === 'thinking' ? (
                           <Loader2 className="w-4 h-4 text-indigo-500 animate-spin" />
                        ) : (
                           <Bot className="w-4 h-4 text-indigo-500" />
                        )}
                        <span className="text-sm font-medium text-gray-700">
                          {msg.status === 'thinking' ? 'Reasoning...' : 'Reasoning process'}
                        </span>
                      </div>
                      {msg.isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-gray-400" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-gray-400" />
                      )}
                    </button>
                    {msg.isExpanded && (
                      <div className="px-4 py-3 bg-white">
                        <pre className="text-xs text-gray-600 whitespace-pre-wrap font-mono leading-relaxed">
                          {msg.content}
                        </pre>
                      </div>
                    )}
                  </div>
                )}

                {/* Routing Badge */}
                {msg.type === 'routing' && (
                  <div className="flex items-center gap-2 mt-4 mb-2">
                    <div className="flex items-center gap-2 px-3 py-1.5 bg-blue-50 text-blue-700 rounded-full text-xs font-medium border border-blue-100 shadow-sm">
                      <Route className="w-3.5 h-3.5" />
                      Routing to: {msg.agent}
                    </div>
                  </div>
                )}

                {/* Error State Block */}
                {msg.type === 'error' && (
                  <div className="bg-red-50 border border-red-200 rounded-lg shadow-sm overflow-hidden max-w-2xl mt-4">
                     <div className="px-4 py-3 border-b border-red-200 flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 text-red-500" />
                        <span className="text-sm font-medium text-red-700">Orchestration Error</span>
                     </div>
                     <div className="px-4 py-3">
                         <p className="text-sm text-red-600">{msg.content}</p>
                     </div>
                  </div>
                )}

                {/* Execution State */}
                {msg.type === 'execution' && (
                  <div className="bg-[#0D1117] rounded-lg shadow-lg overflow-hidden max-w-3xl mt-4 border border-[#30363D]">
                    <div className="flex items-center justify-between px-4 py-2 bg-[#161B22] border-b border-[#30363D]">
                      <div className="flex items-center gap-2 text-gray-400">
                        <Terminal className="w-4 h-4" />
                        <span className="text-xs font-mono text-gray-300">{msg.script}</span>
                      </div>
                      <div className="flex gap-1.5">
                        <div className="w-3 h-3 rounded-full bg-[#FF5F56]"></div>
                        <div className="w-3 h-3 rounded-full bg-[#FFBD2E]"></div>
                        <div className="w-3 h-3 rounded-full bg-[#27C93F]"></div>
                      </div>
                    </div>
                    <div className="p-4 font-mono text-xs text-gray-300 space-y-1.5 overflow-x-auto">
                      {msg.logs.map((log, idx) => (
                        <div key={idx} className="flex">
                          <span className="text-gray-500 mr-3 select-none">{idx + 1}</span>
                          <span className={`${
                            log.includes('[SUCCESS]') ? 'text-green-400' :
                            log.includes('[ERROR]') ? 'text-red-400' :
                            log.includes('[INFO]') ? 'text-blue-300' : 'text-gray-300'
                          }`}>
                            {log}
                          </span>
                        </div>
                      ))}
                      {msg.status === 'running' && (
                        <div className="flex items-center text-gray-500 mt-2">
                          <span className="animate-pulse">_</span>
                        </div>
                      )}
                    </div>
                  </div>
                )}

              </div>
            )}
          </div>
        ))}
      </div>

      {/* Input Area */}
      <div className="p-4 bg-white border-t border-gray-200">
        <div className="max-w-4xl mx-auto relative flex items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSend()}
            placeholder="Type your request (e.g., 'Generate an NOC for John Doe...')"
            className="w-full pl-4 pr-12 py-4 bg-gray-50 border border-gray-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-all shadow-sm disabled:opacity-50"
            disabled={isLoading}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="absolute right-2 p-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
        <div className="text-center mt-2">
           <span className="text-xs text-gray-400">AgentOS can make mistakes. Verify important information.</span>
        </div>
      </div>
    </div>
  );
}
