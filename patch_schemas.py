--- backend/app/schemas.py
+++ backend/app/schemas.py
@@ -69,7 +69,8 @@
 class WorkflowBase(BaseModel):
     name: str
     description: Optional[str] = None
-    steps_json: List[int] = Field(default_factory=list) # List of Agent IDs
+    definition: Dict[str, Any] = Field(default_factory=dict)
+    is_active: bool = True

 class WorkflowCreate(WorkflowBase):
     pass
