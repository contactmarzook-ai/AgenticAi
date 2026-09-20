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
    """Test executing a registered python handler."""
    params = {"employee_name": "John Doe"}
    result = execute_agent_script("mock_noc_generator", params)

    assert result.get("status") == "success"
    assert "John Doe" in result.get("message")

def test_execute_agent_script_failure():
    """Test handler execution with unknown handler."""
    result = execute_agent_script("unknown_handler", {})
    assert result.get("status") == "error"
    assert "not found in registry" in result.get("error").lower()

def test_run_workflow_pipeline(db_session):
    """Test chaining two mock agents together."""

    # Agent 1: Data Analyzer
    agent1 = Agent(name="DataAnalyzer", handler="mock_data_analyzer", is_active=True)
    db_session.add(agent1)

    # Agent 2: NOC Generator
    agent2 = Agent(name="NOCGenerator", handler="mock_noc_generator", is_active=True)
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
    assert "NOC" in final_out.get("message")

    # Check history
    history = result.get("history")
    assert len(history) == 2

    # Agent 1 history checks
    assert history[0]["agent_name"] == "DataAnalyzer"
    assert history[0]["input_used"] == initial_input
    assert history[0]["output_produced"]["status"] == "success"

    # Agent 2 history checks
    assert history[1]["agent_name"] == "NOCGenerator"
    assert history[1]["output_produced"]["status"] == "success"
