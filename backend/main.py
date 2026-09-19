from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from orchestrator import process_agent_interaction

app = FastAPI(title="AgentOS Backend")

class ChatRequest(BaseModel):
    message: str

# Allow requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
