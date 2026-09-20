import traceback
from typing import Dict, Any

def execute_agent_script(python_code: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Dynamically executes a Python script.

    The script must define a variable `output` which will be returned as the result.
    The script will have access to the `params` dictionary in its execution context.

    Args:
        python_code: The raw python string to execute.
        params: A dictionary of parameters to feed into the script context.

    Returns:
        A dictionary containing the state of the `output` variable after execution.
        If an error occurs, it returns an error dictionary with the traceback.
    """
    # Restrict builtins to prevent highly dangerous operations (optional hardening)
    # However, for full flexibility, we might need __builtins__.
    # For now, we supply a clean context but allow standard builtins.
    exec_globals = {
        "__builtins__": __builtins__
    }

    # We pass the input params directly into the local namespace,
    # and we expect the script to populate 'output'.
    exec_locals = {
        "params": params,
        "output": {}
    }

    try:
        # Execute the code dynamically
        exec(python_code, exec_globals, exec_locals)

        # Extract the resulting output
        result = exec_locals.get("output", {})

        if not isinstance(result, dict):
            return {"status": "error", "error": "Script did not produce a dictionary in the 'output' variable."}

        return result

    except Exception as e:
        error_traceback = traceback.format_exc()
        return {
            "status": "error",
            "error": str(e),
            "traceback": error_traceback
        }
