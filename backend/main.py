from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.database import Base, engine
from app.auth import auth_router
from app.routers.chat import chat_router
from app.routers.agents import agents_router
from app.routers.workflows import workflows_router
from app.routers.admin import admin_router

# Initialize database
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AgentOS Backend")

# Include routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(agents_router)
app.include_router(workflows_router)
app.include_router(admin_router)

# Allow requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health_check():
    return {"status": "ok", "message": "AgentOS Backend is running"}
