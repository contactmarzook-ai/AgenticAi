--- backend/app/schemas.py
+++ backend/app/schemas.py
@@ -52,6 +52,7 @@
     trigger_keywords: Optional[str] = None
     handler: str
     input_schema: Optional[Dict[str, Any]] = None
+    output_schema: Optional[Dict[str, Any]] = None
     is_active: bool = True

 class AgentCreate(AgentBase):
