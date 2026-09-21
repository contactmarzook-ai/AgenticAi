--- frontend/src/components/management/WorkflowBuilder.jsx
+++ frontend/src/components/management/WorkflowBuilder.jsx
@@ -375,13 +375,16 @@

         <div className="mt-auto p-4 border-t border-gray-200 bg-gray-50">
-            <div className="flex flex-col gap-2">
-               <div className="flex gap-2">
-                <button onClick={handleTest} disabled={isTesting} className="flex-1 bg-white border border-gray-300 text-gray-700 px-3 py-2 rounded-md text-sm font-medium hover:bg-gray-50 flex justify-center items-center gap-1">
-                    <Play className="w-4 h-4" /> Test
-                </button>
-                <button onClick={handleSave} className="flex-1 bg-indigo-600 text-white px-3 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 flex justify-center items-center gap-1">
-                    <Save className="w-4 h-4" /> Save Draft
-                </button>
-               </div>
-                <button onClick={handleActivate} className="w-full bg-green-600 text-white px-3 py-2 rounded-md text-sm font-medium hover:bg-green-700 flex justify-center items-center gap-1 mt-1">
-                    <Zap className="w-4 h-4" /> Activate
-                </button>
-            </div>
+            <div className="flex flex-col gap-2">
+               <div className="flex gap-2">
+                <button onClick={handleTest} disabled={isTesting} className="flex-1 bg-white border border-gray-300 text-gray-700 px-3 py-2 rounded-md text-sm font-medium hover:bg-gray-50 flex justify-center items-center gap-1">
+                    <Play className="w-4 h-4" /> Test
+                </button>
+                <button onClick={handleSave} className="flex-1 bg-indigo-600 text-white px-3 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 flex justify-center items-center gap-1">
+                    <Save className="w-4 h-4" /> Save Draft
+                </button>
+               </div>
+                <button onClick={handleActivate} className="w-full bg-green-600 text-white px-3 py-2 rounded-md text-sm font-medium hover:bg-green-700 flex justify-center items-center gap-1 mt-1">
+                    <Zap className="w-4 h-4" /> Activate
+                </button>
+            </div>
             {testResult && (
