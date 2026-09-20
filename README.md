# AgentOS

AgentOS is an enterprise AI Workflow Orchestrator designed to map user requests to a set of registered AI agents and execute chained workflows.

## Architecture & Security Model
The system uses a **trusted handler architecture**.

### The Agent Registry
Agents are defined as standard Python functions in `backend/app/agents/handlers.py` and are registered in `backend/app/agents/registry.py`.

The database model (`Agent`) stores metadata, descriptions, trigger keywords, and the name of the `handler` function to use, but **never raw Python code**. This prevents Remote Code Execution (RCE) vulnerabilities and ensures that the LLM orchestrator only selects from a pre-vetted list of operations.

### Orchestration
The Orchestrator (`backend/app/services/orchestrator.py`) handles incoming user requests:
1. It queries the local LLM model (via Ollama/Llama) with a dynamic prompt containing available agents and workflows.
2. The LLM determines the best tool to use and extracts required parameters into a structured JSON payload.
3. The Orchestrator calls the Execution Engine (`backend/app/services/executor.py`) or Workflow Runner, which looks up the registered handler function by name and executes it with the provided parameters.

## Local Development
1. **Frontend:** React + Vite + Tailwind CSS. `cd frontend && npm install && npm run dev`
2. **Backend:** FastAPI + SQLAlchemy. `cd backend && pip install -r requirements.txt && uvicorn main:app --reload`
3. **Database:** SQLite (in-memory for tests, file-based for local dev).
