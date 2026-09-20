import React, { useState } from 'react';
import { useAuthStore } from './store/authStore';
import Sidebar from './components/Sidebar';
import Chat from './components/Chat';
import Agents from './components/Agents';
import Workflows from './components/Workflows';
import Users from './components/Users';
import Login from './components/Login';

function App() {
  const token = useAuthStore((state) => state.token);
  const [activeTab, setActiveTab] = useState('chat');
  const [activeSessionId, setActiveSessionId] = useState(null);

  if (!token) {
    return <Login />;
  }

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden font-sans">
      <Sidebar
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          activeSessionId={activeSessionId}
          setActiveSessionId={setActiveSessionId}
      />

      <main className="flex-1 relative h-full overflow-hidden">
        {activeTab === 'chat' && <Chat sessionId={activeSessionId} setSessionId={setActiveSessionId} />}
        {activeTab === 'agents' && <Agents />}
        {activeTab === 'workflows' && <Workflows />}
        {activeTab === 'users' && <Users />}
      </main>
    </div>
  );
}

export default App;
