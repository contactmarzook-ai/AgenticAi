from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, require_admin
from app.models import User, Agent
from app.schemas import AgentSchema, AgentCreate

agents_router = APIRouter(prefix="/api/agents", tags=["agents"])

@agents_router.get("", response_model=List[AgentSchema])
def list_agents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # All authenticated users can view active agents
    agents = db.query(Agent).filter(Agent.is_active == True).all()
    return agents

@agents_router.post("", response_model=AgentSchema)
def create_agent(agent_data: AgentCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    new_agent = Agent(
        name=agent_data.name,
        description=agent_data.description,
        trigger_keywords=agent_data.trigger_keywords,
        python_code=agent_data.python_code,
        input_schema=agent_data.input_schema,
        is_active=agent_data.is_active,
        created_by=admin.id
    )
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)
    return new_agent

@agents_router.put("/{agent_id}", response_model=AgentSchema)
def update_agent(agent_id: int, agent_data: AgentCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    for key, value in agent_data.model_dump().items():
        setattr(agent, key, value)

    db.commit()
    db.refresh(agent)
    return agent

@agents_router.delete("/{agent_id}")
def delete_agent(agent_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Soft delete
    agent.is_active = False
    db.commit()
    return {"message": "Agent deactivated successfully"}
