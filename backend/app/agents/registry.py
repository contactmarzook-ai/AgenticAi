from typing import Callable, Dict, Any
from .handlers import mock_noc_generator, mock_data_analyzer, default_handler

# Define the signature of an agent handler
AgentHandler = Callable[[Dict[str, Any]], Dict[str, Any]]

# The central registry mapping string names to python functions
AGENT_REGISTRY: Dict[str, AgentHandler] = {
    "mock_noc_generator": mock_noc_generator,
    "mock_data_analyzer": mock_data_analyzer,
    "default_handler": default_handler
}

def get_handler(handler_name: str) -> AgentHandler:
    return AGENT_REGISTRY.get(handler_name)
