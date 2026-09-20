import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch
from app.database import Base
from app.models import Agent, User, ChatSession
from app.services.orchestrator import fast_path_route, route_and_execute

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

@pytest.fixture()
def mock_user(db_session):
    user = User(email="test@test.com", full_name="Test User", role="user")
    db_session.add(user)
    db_session.commit()
    return user

@pytest.fixture()
def mock_session(db_session, mock_user):
    session = ChatSession(user_id=mock_user.id)
    db_session.add(session)
    db_session.commit()
    return session

def test_fast_path_route_match_name(db_session):
    agent = Agent(name="DataAnalyzer", trigger_keywords="analyze,data", handler="mock_data_analyzer", is_active=True)
    db_session.add(agent)
    db_session.commit()

    result = fast_path_route("run the dataanalyzer", db_session)
    assert result is not None
    assert result["action"] == "agent"
    assert result["target_id"] == agent.id
    assert result["routing_method"] == "fast_path"

def test_fast_path_route_match_keyword(db_session):
    agent = Agent(name="NOCGenerator", trigger_keywords="noc,generate document", handler="mock_noc_generator", is_active=True)
    db_session.add(agent)
    db_session.commit()

    result = fast_path_route("please generate document for me", db_session)
    assert result is not None
    assert result["action"] == "agent"
    assert result["target_id"] == agent.id
    assert result["routing_method"] == "fast_path"

def test_fast_path_route_no_match(db_session):
    agent = Agent(name="SpecificAgent", trigger_keywords="specific", handler="default_handler", is_active=True)
    db_session.add(agent)
    db_session.commit()

    result = fast_path_route("I just want to chat", db_session)
    assert result is None

@patch("app.services.orchestrator.call_llama")
def test_route_and_execute_fallback_to_llm(mock_call_llama, db_session, mock_user, mock_session):
    # Setup LLM mock to return a low confidence clarify action
    mock_call_llama.return_value = {
        "action": "clarify",
        "message": "I need more info.",
        "confidence_score": 0.5
    }

    # Fast path should fail on this input
    user_input = "Something vague"
    result = route_and_execute(user_input, mock_session.id, mock_user, db_session)

    # Assert LLM was called because fast path failed
    mock_call_llama.assert_called_once()
    assert result["action"] == "clarify"
    assert result["llm_reasoning"]["routing_method"] == "llm"

@patch("app.services.orchestrator.call_llama")
def test_route_and_execute_low_confidence_override(mock_call_llama, db_session, mock_user, mock_session):
    # Setup LLM mock to return a tool but with low confidence
    mock_call_llama.return_value = {
        "action": "agent",
        "target_id": 1,
        "parameters": {},
        "confidence_score": 0.4
    }

    user_input = "Do something maybe?"
    result = route_and_execute(user_input, mock_session.id, mock_user, db_session)

    # Even though LLM returned 'agent', the low confidence should override it to 'clarify'
    assert result["action"] == "clarify"
    assert "not confident" in result["message"]
