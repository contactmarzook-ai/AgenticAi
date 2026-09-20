import os
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from .database import get_db
from .models import User
from .schemas import UserSchema

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback-secret-for-local-dev-only")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 1 day

auth_router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)) -> User:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    return user

def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough privileges")
    return current_user

@auth_router.get("/sso/microsoft")
def mock_microsoft_sso(db: Session = Depends(get_db)):
    """
    Mock SSO endpoint that seeds default users and returns an admin token for testing.
    In a real app, this would receive a callback code from Entra ID and exchange it.
    """
    # Seed Admin
    admin_email = "admin@org.com"
    admin = db.query(User).filter(User.email == admin_email).first()
    if not admin:
        admin = User(email=admin_email, full_name="Admin User", role="admin", tenant_org_id="ORG-001")
        db.add(admin)

    # Seed User
    user_email = "user@org.com"
    normal_user = db.query(User).filter(User.email == user_email).first()
    if not normal_user:
        normal_user = User(email=user_email, full_name="Standard User", role="user", tenant_org_id="ORG-001")
        db.add(normal_user)

    db.commit()

    # Generate token for the admin for testing purposes
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": admin_email, "role": "admin"}, expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}
