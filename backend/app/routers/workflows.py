from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user
from app.models import User, Workflow
from app.schemas import WorkflowSchema, WorkflowCreate

workflows_router = APIRouter(prefix="/api/workflows", tags=["workflows"])

@workflows_router.get("", response_model=List[WorkflowSchema])
def list_workflows(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    workflows = db.query(Workflow).filter(Workflow.user_id == user.id).all()
    return workflows

@workflows_router.post("", response_model=WorkflowSchema)
def create_workflow(workflow_data: WorkflowCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    new_workflow = Workflow(
        name=workflow_data.name,
        description=workflow_data.description,
        steps_json=workflow_data.steps_json,
        user_id=user.id
    )
    db.add(new_workflow)
    db.commit()
    db.refresh(new_workflow)
    return new_workflow

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
