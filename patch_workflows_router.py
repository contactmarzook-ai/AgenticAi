--- backend/app/routers/workflows.py
+++ backend/app/routers/workflows.py
@@ -19,10 +19,11 @@
 def create_workflow(workflow_data: WorkflowCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
     new_workflow = Workflow(
         name=workflow_data.name,
         description=workflow_data.description,
-        steps_json=workflow_data.steps_json,
-        user_id=user.id
+        definition=workflow_data.definition,
+        is_active=workflow_data.is_active,
+        user_id=user.id if user else None
     )
     db.add(new_workflow)
     db.commit()
     db.refresh(new_workflow)
