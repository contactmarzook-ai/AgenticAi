from typing import Dict, Any

def mock_noc_generator(params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "success",
        "message": f"Generated NOC for {params.get('employee_name', 'Employee')}"
    }

def mock_data_analyzer(params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "success",
        "message": "Data analysis complete."
    }

def default_handler(params: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "success",
        "message": "Default agent executed."
    }
