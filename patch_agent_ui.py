--- frontend/src/components/AgentManagement.jsx
+++ frontend/src/components/AgentManagement.jsx
@@ -79,10 +79,18 @@
       if (field.key) {
           input_schema[field.key] = { type: field.type, required: field.required };
       }
     });
+
+    const output_schema = {};
+    outputSchemaFields.forEach(field => {
+        if (field.key) {
+            output_schema[field.key] = { type: field.type, required: field.required };
+        }
+    });

     const payload = {
         ...formData,
-        input_schema
+        input_schema,
+        output_schema
     };

     try {
@@ -107,6 +115,13 @@
     } else {
         setSchemaFields([{ key: '', type: 'string', required: false }]);
     }
+
+    if (agent.output_schema) {
+        const fields = Object.entries(agent.output_schema).map(([k, v]) => ({ key: k, type: v.type, required: v.required }));
+        setOutputSchemaFields(fields.length ? fields : [{ key: '', type: 'string', required: false }]);
+    } else {
+        setOutputSchemaFields([{ key: '', type: 'string', required: false }]);
+    }
   };

   const addSchemaField = () => setSchemaFields([...schemaFields, { key: '', type: 'string', required: false }]);
@@ -121,6 +136,13 @@
   const removeSchemaField = (index) => setSchemaFields(schemaFields.filter((_, i) => i !== index));
+
+  const addOutputSchemaField = () => setOutputSchemaFields([...outputSchemaFields, { key: '', type: 'string', required: false }]);
+  const updateOutputSchemaField = (index, field, value) => {
+      const newFields = [...outputSchemaFields];
+      newFields[index][field] = value;
+      setOutputSchemaFields(newFields);
+  };
+  const removeOutputSchemaField = (index) => setOutputSchemaFields(outputSchemaFields.filter((_, i) => i !== index));

   const runAgentTest = async () => {
@@ -262,6 +284,24 @@
                                 <button type="button" onClick={addSchemaField} className="text-sm text-indigo-600 font-medium flex items-center gap-1 hover:text-indigo-700"><Plus className="w-4 h-4" /> Add Field</button>
                             </div>
                         </div>
+
+                        <div>
+                            <label className="block text-sm font-medium text-gray-700 mb-2">Output Schema Builder</label>
+                            <div className="space-y-3 bg-gray-50 p-4 rounded-md border border-gray-200">
+                                {outputSchemaFields.map((field, index) => (
+                                    <div key={index} className="flex items-center gap-3">
+                                        <input type="text" placeholder="Key name" value={field.key} onChange={(e) => updateOutputSchemaField(index, 'key', e.target.value)} className="flex-1 border border-gray-300 rounded shadow-sm px-2 py-1.5 text-sm focus:ring-indigo-500 focus:border-indigo-500" />
+                                        <select value={field.type} onChange={(e) => updateOutputSchemaField(index, 'type', e.target.value)} className="w-28 border border-gray-300 rounded shadow-sm px-2 py-1.5 text-sm focus:ring-indigo-500 focus:border-indigo-500 bg-white">
+                                            <option value="string">String</option>
+                                            <option value="number">Number</option>
+                                            <option value="boolean">Boolean</option>
+                                        </select>
+                                        <button type="button" onClick={() => removeOutputSchemaField(index)} className="text-gray-400 hover:text-red-500 p-1"><Trash2 className="w-4 h-4" /></button>
+                                    </div>
+                                ))}
+                                <button type="button" onClick={addOutputSchemaField} className="text-sm text-indigo-600 font-medium flex items-center gap-1 hover:text-indigo-700"><Plus className="w-4 h-4" /> Add Field</button>
+                            </div>
+                        </div>
+
                         <div>
                             <div className="flex justify-between items-center mb-1">
                                 <label className="block text-sm font-medium text-gray-700">Agent Handler</label>
