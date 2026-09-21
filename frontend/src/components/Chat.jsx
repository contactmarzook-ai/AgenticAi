import React, { useState, useEffect } from 'react';
import { Send, FileText, User, Bot, AlertCircle, X } from 'lucide-react';
import api from '../store/api';
import { useAuthStore } from '../store/authStore';

export default function Chat({ sessionId, setSessionId }) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [toastError, setToastError] = useState(null);
  const token = useAuthStore((state) => state.token);

  useEffect(() => {
    const fetchMessages = async () => {
      if (!sessionId) {
          setMessages([]);
          return;
      }
      try {
        const res = await api.get(`/chat/sessions/${sessionId}/messages`);

        // Map backend schema to frontend UI schema
        const mapped = [];
        res.data.forEach(msg => {
            if (msg.role === 'user') {
                mapped.push({ id: msg.id, role: 'user', content: msg.content });
            } else if (msg.role === 'assistant') {
                mapped.push({ id: msg.id, role: 'assistant', content: msg.content });
            }
        });
        setMessages(mapped);

      } catch (err) {
        console.error("Failed to fetch messages", err);
        setToastError("Failed to load chat history.");
      }
    };

    fetchMessages();
  }, [sessionId]);

  useEffect(() => {
    if (toastError) {
      const timer = setTimeout(() => setToastError(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [toastError]);

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

    try {
      if (!token) {
        setToastError("Authentication failed. Cannot send message.");
        setIsLoading(false);
        return;
      }

      let currentSessionId = sessionId;

      // Create session if it doesn't exist
      if (!currentSessionId) {
          const sessionRes = await api.post(`/chat/sessions?title=${encodeURIComponent(userMessageContent.substring(0, 20) + "...")}`);
          currentSessionId = sessionRes.data.id;
          setSessionId(currentSessionId);
      }

      const response = await api.post(`/chat/sessions/${currentSessionId}/send`, {
        message: userMessageContent
      });

      const data = response.data;

      if (data.status === 'error') {
          setMessages(prev => [...prev, {
              id: Date.now() + 2,
              role: 'assistant',
              isError: true,
              content: data.message || "An unknown error occurred during orchestration."
          }]);
      } else if (data.status === 'success' && data.execution_trace) {
          setMessages(prev => [...prev, {
              id: Date.now() + 4,
              role: 'assistant',
              content: data.message || "Action completed successfully."
          }]);
      } else {
          setMessages(prev => [...prev, {
              id: Date.now() + 2,
              role: 'assistant',
              content: data.message || "I'm not sure how to handle that."
          }]);
      }

    } catch (error) {
      console.error("Failed to connect to backend:", error);
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
        {messages.filter(msg => msg.role === 'user' || msg.role === 'assistant').map((msg) => (
          <div key={msg.id} className="flex flex-col w-full">
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
                <div className={`border rounded-2xl rounded-tl-sm px-5 py-4 max-w-[80%] shadow-sm ${msg.isError ? 'bg-red-50 border-red-200 text-red-800' : 'bg-white border-gray-200 text-gray-800'}`}>
                  <p className="mb-3">{msg.content}</p>
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

          </div>
        ))}

        {isLoading && (
          <div className="flex items-start gap-4">
            <div className="bg-white p-2 rounded-full border border-gray-200 mt-1 flex-shrink-0 shadow-sm">
              <Bot className="w-5 h-5 text-gray-600" />
            </div>
            <div className="bg-white border border-gray-200 rounded-2xl rounded-tl-sm px-5 py-4 shadow-sm flex items-center gap-3">
               <div className="flex gap-1">
                 <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                 <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                 <div className="w-2 h-2 bg-indigo-400 rounded-full animate-bounce"></div>
               </div>
               <span className="text-sm text-gray-500 font-medium">AgentOS is thinking...</span>
            </div>
          </div>
        )}
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
