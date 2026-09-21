from typing import Dict, Any

def validate_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> list[str]:
    """
    Validates a dictionary of data against a simplified schema dictionary.
    Schema format example: {"loan_id": {"type": "string", "required": True}}
    Returns a list of error strings. Empty list means valid.
    """
    if not schema:
        return [] # No schema means no constraints

    errors = []

    # Check for required fields and types
    for key, rules in schema.items():
        if not isinstance(rules, dict):
            continue

        is_required = rules.get("required", False)
        expected_type = rules.get("type", "string")

        if key not in data:
            if is_required:
                errors.append(f"Missing required field: '{key}'")
            continue

        value = data[key]

        # Simple type checking
        if expected_type == "string" and not isinstance(value, str):
            errors.append(f"Field '{key}' must be a string, got {type(value).__name__}.")
        elif expected_type == "number" and not isinstance(value, (int, float)):
            errors.append(f"Field '{key}' must be a number, got {type(value).__name__}.")
        elif expected_type == "boolean" and not isinstance(value, bool):
            errors.append(f"Field '{key}' must be a boolean, got {type(value).__name__}.")

    return errors
