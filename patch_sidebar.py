--- frontend/src/components/Sidebar.jsx
+++ frontend/src/components/Sidebar.jsx
@@ -38,7 +38,6 @@
   const tabs = [
     { id: 'chat', label: 'Chat', icon: MessageSquare },
     { id: 'agents', label: 'Agents', icon: Bot, badge: 'Read Only' },
-    { id: 'workflows', label: 'Workflows', icon: Workflow },
     ...(user?.role === 'admin' ? [
         { id: 'management', label: 'Management', icon: ShieldCog },
         { id: 'users', label: 'User Management', icon: Users }
