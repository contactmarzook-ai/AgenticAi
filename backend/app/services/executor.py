import traceback
from typing import Dict, Any, Optional
from app.agents.registry import get_handler
from app.services.agent_validator import validate_schema

def execute_agent_script(handler_name: str, params: Dict[str, Any], input_schema: Optional[Dict[str, Any]] = None, output_schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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

    if input_schema:
        in_errors = validate_schema(params, input_schema)
        if in_errors:
            return {
                "status": "error",
                "error": f"Input validation failed: {', '.join(in_errors)}"
            }

    try:
        result = handler(params)

        if not isinstance(result, dict):
            return {"status": "error", "error": "Handler did not produce a dictionary."}

        if output_schema:
            out_errors = validate_schema(result, output_schema)
            if out_errors:
                return {
                    "status": "error",
                    "error": f"Output validation failed: {', '.join(out_errors)}"
                }

        return result

    except Exception as e:
        error_traceback = traceback.format_exc()
        return {
            "status": "error",
            "error": str(e),
            "traceback": error_traceback
        }
