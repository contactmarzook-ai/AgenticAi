# AgentOS

AgentOS is an enterprise AI Workflow Orchestrator designed to map user requests to a set of registered AI agents and execute chained workflows.

## Architecture & Security Model
The system uses a **trusted handler architecture**.

### The Agent Registry
Agents are defined as standard Python functions in `backend/app/agents/handlers.py` and are registered in `backend/app/agents/registry.py`.

The database model (`Agent`) stores metadata, descriptions, trigger keywords, and the name of the `handler` function to use, but **never raw Python code**. This prevents Remote Code Execution (RCE) vulnerabilities and ensures that the LLM orchestrator only selects from a pre-vetted list of operations.

### Fast-Path & Lightweight Routing Orchestrator
The Orchestrator (`backend/app/services/orchestrator.py`) handles incoming user requests using a dual-path routing model to keep inference times and CPU/GPU usage low:
1. **Fast-Path:** The system first attempts to route requests directly by matching keywords and agent names without calling the LLM. If a confident match is found, it proceeds immediately to execution.
2. **LLM Fallback:** If the fast-path fails, it queries the local LLM model (via Ollama/Llama) with a dynamic prompt containing available agents and workflows.
3. The LLM acts strictly as a **router**, identifying the best tool to use, extracting required parameters, and calculating a `confidence_score`. It explicitly avoids deep reasoning or generating multi-step plans.
4. If the LLM `confidence_score` is below `0.7`, the system falls back to asking the user for clarification.
5. If a tool is confidently identified (via fast-path or LLM), the Orchestrator calls the Execution Engine (`backend/app/services/executor.py`) or Workflow Runner, which looks up the registered handler function by name and executes it with the provided parameters.

This architecture ensures extremely fast routing for common tasks, smart fallback for complex requests, and preserves the ability to plug in a separate Dynamic Planner layer in the future without rewriting the core router.

## Local Development
1. **Frontend:** React + Vite + Tailwind CSS. `cd frontend && npm install && npm run dev`
2. **Backend:** FastAPI + SQLAlchemy. `cd backend && pip install -r requirements.txt && uvicorn main:app --reload`
3. **Database:** SQLite (in-memory for tests, file-based for local dev).
