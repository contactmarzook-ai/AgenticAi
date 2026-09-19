import React, { useState } from 'react';
import Sidebar from './components/Sidebar';
import Chat from './components/Chat';
import Agents from './components/Agents';

function App() {
  const [activeTab, setActiveTab] = useState('chat');

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden font-sans">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />

      <main className="flex-1 relative h-full overflow-hidden">
        {activeTab === 'chat' && <Chat />}
        {activeTab === 'agents' && <Agents />}
      </main>
    </div>
  );
}

export default App;
