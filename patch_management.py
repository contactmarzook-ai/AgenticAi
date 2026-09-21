--- frontend/src/components/Management.jsx
+++ frontend/src/components/Management.jsx
@@ -1,7 +1,8 @@
 import React, { useState } from 'react';
-import { ShieldCog, LayoutDashboard, Activity } from 'lucide-react';
+import { ShieldCog, LayoutDashboard, Activity, GitMerge } from 'lucide-react';
 import Monitoring from './Monitoring';
-import AgentManagement from './AgentManagement'; // We will create this next
+import AgentManagement from './AgentManagement';
+import WorkflowBuilder from './management/WorkflowBuilder';

 export default function Management() {
   const [activeSubTab, setActiveSubTab] = useState('agents');
@@ -32,6 +33,16 @@
           >
             <LayoutDashboard className="w-4 h-4" /> Agent Management
           </button>
+          <button
+            onClick={() => setActiveSubTab('workflows')}
+            className={`flex items-center gap-2 px-6 py-3 font-medium text-sm transition-colors border-b-2 ${
+              activeSubTab === 'workflows'
+                ? 'border-indigo-600 text-indigo-600'
+                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
+            }`}
+          >
+            <GitMerge className="w-4 h-4" /> Workflow Builder
+          </button>
           <button
             onClick={() => setActiveSubTab('monitoring')}
             className={`flex items-center gap-2 px-6 py-3 font-medium text-sm transition-colors border-b-2 ${
@@ -48,6 +59,7 @@
       <div className="flex-1 overflow-hidden relative">
         {activeSubTab === 'agents' && <AgentManagement />}
+        {activeSubTab === 'workflows' && <WorkflowBuilder />}
         {activeSubTab === 'monitoring' && <Monitoring embedded={true} />}
       </div>
     </div>
