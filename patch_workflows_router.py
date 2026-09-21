--- backend/app/routers/workflows.py
+++ backend/app/routers/workflows.py
@@ -40,6 +40,39 @@
     db.refresh(new_workflow)
     return new_workflow

+@workflows_router.post("/{workflow_id}/activate", response_model=WorkflowSchema)
+def activate_workflow(workflow_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
+    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
+    if not workflow:
+        raise HTTPException(status_code=404, detail="Workflow not found")
+
+    val_res = validate_workflow_definition(workflow.definition, db)
+    if not val_res["is_valid"]:
+        raise HTTPException(status_code=400, detail={"message": "Validation failed", "errors": val_res["errors"]})
+
+    # Archive other active versions in this group
+    old_actives = db.query(Workflow).filter(Workflow.group_id == workflow.group_id, Workflow.is_active == True).all()
+    for old in old_actives:
+        old.is_active = False
+        old.status = "archived"
+
+    workflow.is_active = True
+    workflow.status = "active"
+    db.commit()
+    db.refresh(workflow)
+    return workflow
+
+@workflows_router.post("/{workflow_id}/test")
+def test_workflow(workflow_id: int, input_data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
+    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
+    if not workflow:
+        raise HTTPException(status_code=404, detail="Workflow not found")
+
+    val_res = validate_workflow_definition(workflow.definition, db)
+    if not val_res["is_valid"]:
+        return {"status": "error", "message": "Validation failed", "errors": val_res["errors"]}
+
+    result = run_workflow_pipeline(workflow_id, input_data, db, is_test=True)
+    return result
+
 @workflows_router.put("/{workflow_id}", response_model=WorkflowSchema)
 def update_workflow(workflow_id: int, workflow_data: WorkflowCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
