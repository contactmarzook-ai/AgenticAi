def create_support_ticket(user_id: str, issue_description: str) -> dict:
    """Mocks creating a support ticket."""
    return {
        "status": "success",
        "ticket_id": "TKT-12345",
        "user_id": user_id,
        "message": f"Support ticket created for issue: '{issue_description}'"
    }

def get_account_status(account_number: str) -> dict:
    """Mocks retrieving an account status."""
    return {
        "status": "success",
        "account_number": account_number,
        "account_status": "Active",
        "message": f"Account {account_number} is in good standing."
    }

WORKFLOW_REGISTRY = {
    "create_support_ticket": {
        "function": create_support_ticket,
        "description": "Creates a support ticket for a given user with an issue description.",
        "parameters": [
            {"name": "user_id", "type": "str", "description": "The ID of the user."},
            {"name": "issue_description", "type": "str", "description": "Description of the issue."}
        ]
    },
    "get_account_status": {
        "function": get_account_status,
        "description": "Retrieves the status of an account given the account number.",
        "parameters": [
            {"name": "account_number", "type": "str", "description": "The account number to look up."}
        ]
    }
}
