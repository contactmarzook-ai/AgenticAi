import React from 'react';
import { MessageSquare, Bot, Settings, Hexagon } from 'lucide-react';

export default function Sidebar({ activeTab, setActiveTab }) {
  const tabs = [
    { id: 'chat', label: 'Chat', icon: MessageSquare },
    { id: 'agents', label: 'Agents', icon: Bot },
  ];

  return (
    <aside className="w-64 bg-white border-r border-gray-200 h-screen flex flex-col">
      {/* Header */}
      <div className="p-6 flex items-center gap-3 border-b border-gray-100">
        <div className="bg-indigo-600 p-1.5 rounded-lg">
          <Hexagon className="w-6 h-6 text-white" />
        </div>
        <span className="font-bold text-xl text-gray-900 tracking-tight">AgentOS</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-md transition-colors duration-150 ease-in-out ${
                isActive
                  ? 'bg-indigo-50 text-indigo-700 font-medium'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              }`}
            >
              <Icon className={`w-5 h-5 ${isActive ? 'text-indigo-600' : 'text-gray-400'}`} />
              {tab.label}
            </button>
          );
        })}
      </nav>

      {/* Footer Settings */}
      <div className="p-4 border-t border-gray-100">
        <button className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-gray-600 hover:bg-gray-50 hover:text-gray-900 transition-colors duration-150 ease-in-out">
          <Settings className="w-5 h-5 text-gray-400" />
          Settings
        </button>
      </div>
    </aside>
  );
}
