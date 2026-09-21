import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.services.workflow_validator import validate_workflow_definition

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

def test_validate_workflow_definition_empty():
    res = validate_workflow_definition({"nodes": [], "edges": []}, None)
    assert res["is_valid"] is False
    assert "Workflow must have at least one node." in res["errors"]

def test_validate_workflow_definition_missing_endpoints(db_session):
    definition = {
        "nodes": [{"id": "n1", "type": "agent", "data": {"agent_id": 1}}],
        "edges": []
    }
    res = validate_workflow_definition(definition, db_session)
    assert res["is_valid"] is False
    assert "Workflow must have an Input Node." in res["errors"]
    assert "Workflow must have an End Node." in res["errors"]

def test_validate_workflow_definition_disconnected(db_session):
    definition = {
        "nodes": [
            {"id": "in", "type": "input"},
            {"id": "end", "type": "end"},
            {"id": "n1", "type": "agent"}
        ],
        "edges": [{"source": "in", "target": "end"}]
    }
    res = validate_workflow_definition(definition, db_session)
    assert res["is_valid"] is False
    assert "Node n1 (agent) is disconnected." in res["errors"]
