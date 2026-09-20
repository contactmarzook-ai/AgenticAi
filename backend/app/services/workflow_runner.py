from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.models import Workflow, Agent
from app.services.executor import execute_agent_script

def run_workflow_pipeline(workflow_id: int, initial_input: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """
    Executes a workflow by fetching it from the DB and chaining its agents sequentially.
    The output of Agent N becomes the input of Agent N+1.

    Args:
        workflow_id: The ID of the workflow to run.
        initial_input: The starting parameters for the first agent.
        db: SQLAlchemy session.

    Returns:
        A dictionary containing the final output and the history of execution steps.
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()

    if not workflow:
        return {
            "status": "error",
            "error": f"Workflow with ID {workflow_id} not found."
        }

    agent_ids = workflow.steps_json
    if not agent_ids or not isinstance(agent_ids, list):
        return {
             "status": "error",
             "error": "Workflow has no defined steps or steps_json is invalid."
        }

    execution_history = []
    current_input = initial_input

    for idx, agent_id in enumerate(agent_ids):
        agent = db.query(Agent).filter(Agent.id == agent_id).first()

        if not agent:
            error_msg = f"Agent with ID {agent_id} not found in database."
            execution_history.append({
                "step": idx + 1,
                "agent_id": agent_id,
                "status": "error",
                "error": error_msg
            })
            return {
                "status": "error",
                "error": "Pipeline failed.",
                "history": execution_history
            }

        if not agent.is_active:
             error_msg = f"Agent '{agent.name}' (ID: {agent_id}) is inactive."
             execution_history.append({
                "step": idx + 1,
                "agent_id": agent_id,
                "agent_name": agent.name,
                "status": "error",
                "error": error_msg
            })
             return {
                "status": "error",
                "error": "Pipeline failed.",
                "history": execution_history
            }

        # Execute the agent script
        step_result = execute_agent_script(agent.python_code, current_input)

        # Check for execution failure
        if step_result.get("status") == "error":
             execution_history.append({
                "step": idx + 1,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "status": "error",
                "error": step_result.get("error"),
                "traceback": step_result.get("traceback")
             })
             return {
                "status": "error",
                "error": f"Agent '{agent.name}' failed during execution.",
                "history": execution_history
             }

        # Record successful step execution
        execution_history.append({
            "step": idx + 1,
            "agent_id": agent.id,
            "agent_name": agent.name,
            "status": "success",
            "input_used": current_input,
            "output_produced": step_result
        })

        # Pipeline logic: current output becomes next step's input
        current_input = step_result

    return {
        "status": "success",
        "final_output": current_input,
        "history": execution_history
    }
