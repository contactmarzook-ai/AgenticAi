--- frontend/src/components/management/WorkflowBuilder.jsx
+++ frontend/src/components/management/WorkflowBuilder.jsx
@@ -82,8 +82,21 @@
         description: workflowDesc,
         definition: {
             nodes: nodes,
             edges: edges
         }
     };
-    console.log("Saving workflow:", payload);
-    // Add real API call here
+    try {
+        const res = await api.post('/workflows', payload);
+        setTestResult({status: 'success', message: 'Workflow saved.'});
+        setTimeout(() => setTestResult(null), 3000);
+    } catch (err) {
+        console.error(err);
+        setTestResult({status: 'error', message: 'Failed to save workflow.'});
+        setTimeout(() => setTestResult(null), 3000);
+    }
   };
