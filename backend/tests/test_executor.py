import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Agent, Workflow
from app.services.executor import execute_agent_script
from app.services.workflow_runner import run_workflow_pipeline

# Setup in-memory SQLite DB for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture()
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

def test_execute_agent_script_success():
    """Test dynamically executing a python script for NOC generation."""
    script = """
account_id = params.get('account_id')
if not account_id:
    raise ValueError("account_id is required")

noc_text = f"This is an official NOC for account: {account_id}. Approved."

output['status'] = 'success'
output['noc_content'] = noc_text
output['document_id'] = f"DOC-{account_id}"
"""
    params = {"account_id": "ACC123"}
    result = execute_agent_script(script, params)

    assert result.get("status") == "success"
    assert result.get("noc_content") == "This is an official NOC for account: ACC123. Approved."
    assert result.get("document_id") == "DOC-ACC123"

def test_execute_agent_script_failure():
    """Test dynamic execution handling errors and traceback."""
    script = """
x = 1 / 0  # This will throw ZeroDivisionError
"""
    result = execute_agent_script(script, {})
    assert result.get("status") == "error"
    assert "division by zero" in result.get("error").lower()
    assert "Traceback" in result.get("traceback")

def test_run_workflow_pipeline(db_session):
    """Test chaining two mock agents together."""

    # Agent 1: Extracts data
    agent1_script = """
user_query = params.get('query')
# Mock logic extracting an account ID
extracted_id = "ACC-999"

output['account_id'] = extracted_id
output['original_query'] = user_query
"""
    agent1 = Agent(name="DataExtractor", python_code=agent1_script, is_active=True)
    db_session.add(agent1)

    # Agent 2: Generates Document based on extracted data
    agent2_script = """
acc_id = params.get('account_id')
doc_type = "NOC"

output['final_message'] = f"Generated {doc_type} for {acc_id}"
"""
    agent2 = Agent(name="DocGenerator", python_code=agent2_script, is_active=True)
    db_session.add(agent2)
    db_session.commit()

    # Create workflow
    workflow = Workflow(name="NOC Pipeline", steps_json=[agent1.id, agent2.id])
    db_session.add(workflow)
    db_session.commit()

    # Run pipeline
    initial_input = {"query": "I need an NOC for my account"}
    result = run_workflow_pipeline(workflow.id, initial_input, db_session)

    # Assertions
    assert result.get("status") == "success"

    # Check final output (from Agent 2)
    final_out = result.get("final_output")
    assert final_out.get("final_message") == "Generated NOC for ACC-999"

    # Check history
    history = result.get("history")
    assert len(history) == 2

    # Agent 1 history checks
    assert history[0]["agent_name"] == "DataExtractor"
    assert history[0]["input_used"] == initial_input
    assert history[0]["output_produced"]["account_id"] == "ACC-999"

    # Agent 2 history checks
    assert history[1]["agent_name"] == "DocGenerator"
    assert history[1]["input_used"]["account_id"] == "ACC-999" # Input of 2 was output of 1
    assert history[1]["output_produced"]["final_message"] == "Generated NOC for ACC-999"
