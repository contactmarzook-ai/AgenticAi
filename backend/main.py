from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from orchestrator import process_agent_interaction
from app.database import Base, engine
from app.auth import auth_router

# Initialize database
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AgentOS Backend")

# Include routers
app.include_router(auth_router)

class ChatRequest(BaseModel):
    message: str

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

@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    result = process_agent_interaction(request.message)
    return result
