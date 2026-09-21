import React, { useEffect, useState } from 'react';
import { MessageSquare, Bot, Settings, Hexagon, Plus, Users, Workflow, LogOut, Trash2, ShieldCog } from 'lucide-react';
import { useAuthStore } from '../store/authStore';
import api from '../store/api';

export default function Sidebar({ activeTab, setActiveTab, activeSessionId, setActiveSessionId }) {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const [sessions, setSessions] = useState([]);

  const fetchSessions = async () => {
    try {
      const res = await api.get('/chat/sessions');
      setSessions(res.data);
    } catch (err) {
      console.error("Failed to fetch sessions", err);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, [activeSessionId]); // Refetch when a new session is created

  const handleDeleteSession = async (e, id) => {
    e.stopPropagation();
    try {
      await api.delete(`/chat/sessions/${id}`);
      if (activeSessionId === id) {
        setActiveSessionId(null);
        setActiveTab('chat');
      }
      fetchSessions();
    } catch (err) {
      console.error("Failed to delete session", err);
    }
  };

  const tabs = [
    { id: 'chat', label: 'Chat', icon: MessageSquare },
    { id: 'agents', label: 'Agents', icon: Bot, badge: 'Read Only' },
    ...(user?.role === 'admin' ? [
        { id: 'management', label: 'Management', icon: ShieldCog },
        { id: 'users', label: 'User Management', icon: Users }
    ] : []),
  ];

  const handleNewChat = () => {
    setActiveSessionId(null);
    setActiveTab('chat');
  };

  return (
    <aside className="w-64 bg-white border-r border-gray-200 h-screen flex flex-col flex-shrink-0">
      {/* Header */}
      <div className="p-5 border-b border-gray-100">
        <div className="flex items-center gap-3 mb-4">
          <div className="bg-indigo-600 p-1.5 rounded-lg">
            <Hexagon className="w-6 h-6 text-white" />
          </div>
          <span className="font-bold text-xl text-gray-900 tracking-tight">AgentOS</span>
        </div>

        <div className="bg-gray-50 rounded-lg p-3 border border-gray-100 flex items-center justify-between">
           <div>
               <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Tenant</p>
               <p className="text-sm font-medium text-gray-900 truncate">ORG-001</p>
           </div>
           <div className="text-right">
               <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Role</p>
               <p className="text-sm font-medium text-indigo-600 capitalize truncate">{user?.role}</p>
           </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        <div className="p-4">
            <button
                onClick={handleNewChat}
                className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors shadow-sm mb-4"
            >
                <Plus className="w-4 h-4" /> New Chat
            </button>

            {/* Navigation */}
            <nav className="space-y-1 mb-6">
            {tabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className={`w-full flex items-center justify-between px-3 py-2.5 rounded-md transition-colors duration-150 ease-in-out ${
                    isActive
                        ? 'bg-indigo-50 text-indigo-700 font-medium'
                        : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                    }`}
                >
                    <div className="flex items-center gap-3">
                        <Icon className={`w-5 h-5 ${isActive ? 'text-indigo-600' : 'text-gray-400'}`} />
                        {tab.label}
                    </div>
                    {tab.badge && (
                        <span className="text-[10px] uppercase font-bold bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded border border-gray-200">
                            {tab.badge}
                        </span>
                    )}
                </button>
                );
            })}
            </nav>

            {/* Recent Sessions */}
            <div className="space-y-1">
                <p className="px-3 text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Recent Sessions</p>
                {sessions.map(session => (
                    <div
                        key={session.id}
                        onClick={() => {
                            setActiveSessionId(session.id);
                            setActiveTab('chat');
                        }}
                        className={`w-full group flex items-center justify-between cursor-pointer px-3 py-2 text-sm rounded-md transition-colors ${activeSessionId === session.id && activeTab === 'chat' ? 'bg-gray-100 text-gray-900 font-medium' : 'text-gray-600 hover:bg-gray-50'}`}
                    >
                        <span className="truncate flex-1">{session.title}</span>
                        <button
                            onClick={(e) => handleDeleteSession(e, session.id)}
                            className="opacity-0 group-hover:opacity-100 p-1 text-gray-400 hover:text-red-500 transition-opacity"
                            title="Delete session"
                        >
                            <Trash2 className="w-4 h-4" />
                        </button>
                    </div>
                ))}
            </div>
        </div>
      </div>

      {/* Footer Settings */}
      <div className="p-4 border-t border-gray-100 space-y-1">
        <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors duration-150 ease-in-out">
          <Settings className="w-5 h-5 text-gray-400" />
          Settings
        </button>
        <button
          onClick={logout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-red-600 hover:bg-red-50 transition-colors duration-150 ease-in-out"
        >
          <LogOut className="w-5 h-5" />
          Sign Out
        </button>
      </div>
    </aside>
  );
}
