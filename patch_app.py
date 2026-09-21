--- frontend/src/App.jsx
+++ frontend/src/App.jsx
@@ -4,7 +4,6 @@
 import Sidebar from './components/Sidebar';
 import Chat from './components/Chat';
 import Agents from './components/Agents';
-import Workflows from './components/Workflows';
 import Users from './components/Users';
 import Management from './components/Management';
 import Login from './components/Login';
@@ -27,7 +26,6 @@
       <main className="flex-1 relative h-full overflow-hidden">
         {activeTab === 'chat' && <Chat sessionId={activeSessionId} setSessionId={setActiveSessionId} />}
         {activeTab === 'agents' && <Agents />}
-        {activeTab === 'workflows' && <Workflows />}
         {activeTab === 'users' && <Users />}
         {activeTab === 'management' && <Management />}
       </main>
