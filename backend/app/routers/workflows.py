from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import uuid

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Workflow
from app.schemas import WorkflowSchema, WorkflowCreate
from app.services.workflow_validator import validate_workflow_definition
from app.services.workflow_runner import run_workflow_pipeline

workflows_router = APIRouter(prefix="/api/workflows", tags=["workflows"])

@workflows_router.get("", response_model=List[WorkflowSchema])
def list_workflows(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    workflows = db.query(Workflow).filter(Workflow.user_id == user.id, Workflow.status != "archived").order_by(Workflow.group_id, Workflow.version.desc()).all()
    return workflows

@workflows_router.post("", response_model=WorkflowSchema)
def create_workflow(workflow_data: WorkflowCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    group_id = workflow_data.group_id
    version = 1

    if group_id:
        latest = db.query(Workflow).filter(Workflow.group_id == group_id).order_by(Workflow.version.desc()).first()
        if latest:
            version = latest.version + 1
    else:
        group_id = uuid.uuid4().hex

    new_workflow = Workflow(
        name=workflow_data.name,
        description=workflow_data.description,
        definition=workflow_data.definition,
        is_active=workflow_data.is_active,
        user_id=user.id if user else None
    )
    db.add(new_workflow)
    db.commit()
    db.refresh(new_workflow)
    return new_workflow

@workflows_router.post("/{workflow_id}/activate", response_model=WorkflowSchema)
def activate_workflow(workflow_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    val_res = validate_workflow_definition(workflow.definition, db)
    if not val_res["is_valid"]:
        raise HTTPException(status_code=400, detail={"message": "Validation failed", "errors": val_res["errors"]})

    # Archive other active versions in this group
    old_actives = db.query(Workflow).filter(Workflow.group_id == workflow.group_id, Workflow.is_active == True).all()
    for old in old_actives:
        old.is_active = False
        old.status = "archived"

    workflow.is_active = True
    workflow.status = "active"
    db.commit()
    db.refresh(workflow)
    return workflow

@workflows_router.post("/{workflow_id}/test")
def test_workflow(workflow_id: int, input_data: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    val_res = validate_workflow_definition(workflow.definition, db)
    if not val_res["is_valid"]:
        return {"status": "error", "message": "Validation failed", "errors": val_res["errors"]}

    result = run_workflow_pipeline(workflow_id, input_data, db, is_test=True)
    return result

@workflows_router.put("/{workflow_id}", response_model=WorkflowSchema)
def update_workflow(workflow_id: int, workflow_data: WorkflowCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.user_id == user.id).first()
    if not workflow:
         raise HTTPException(status_code=404, detail="Workflow not found")

    for key, value in workflow_data.model_dump().items():
        setattr(workflow, key, value)

    db.commit()
    db.refresh(workflow)
    return workflow

@workflows_router.delete("/{workflow_id}")
def delete_workflow(workflow_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.user_id == user.id).first()
    if not workflow:
         raise HTTPException(status_code=404, detail="Workflow not found")

    db.delete(workflow)
    db.commit()
    return {"message": "Workflow deleted successfully"}
