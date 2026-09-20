from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.auth import require_admin
from app.models import User
from app.schemas import UserSchema

admin_router = APIRouter(prefix="/api/admin", tags=["admin"])

class RoleUpdate(BaseModel):
    role: str

@admin_router.get("/users", response_model=List[UserSchema])
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    users = db.query(User).all()
    return users

@admin_router.put("/users/{user_id}/role", response_model=UserSchema)
def update_user_role(user_id: int, role_update: RoleUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if role_update.role not in ["admin", "user"]:
        raise HTTPException(status_code=400, detail="Invalid role specified")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.role = role_update.role
    db.commit()
    db.refresh(user)
    return user
