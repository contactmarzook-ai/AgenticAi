import traceback
from typing import Dict, Any
from app.agents.registry import get_handler

def execute_agent_script(handler_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executes an agent by finding its registered handler function.

    Args:
        handler_name: The name of the registered python function.
        params: A dictionary of parameters to feed into the handler.

    Returns:
        A dictionary containing the output of the handler.
        If an error occurs, it returns an error dictionary with the traceback.
    """
    handler = get_handler(handler_name)

    if not handler:
        return {
            "status": "error",
            "error": f"Handler '{handler_name}' not found in registry."
        }

    try:
        result = handler(params)

        if not isinstance(result, dict):
            return {"status": "error", "error": "Handler did not produce a dictionary."}

        return result

    except Exception as e:
        error_traceback = traceback.format_exc()
        return {
            "status": "error",
            "error": str(e),
            "traceback": error_traceback
        }
