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

def test_validate_workflow_definition_schema_mismatch(db_session):
    from app.models import Agent
    import json

    # create test agents with strict inputs and outputs
    agent1 = Agent(
        name="A1",
        description="A1",
        trigger_keywords="a1",
        handler="default_handler",
        input_schema={"in1": {"type": "string", "required": True}},
        output_schema={"out1": {"type": "number", "required": True}},
        is_active=True
    )
    agent2 = Agent(
        name="A2",
        description="A2",
        trigger_keywords="a2",
        handler="default_handler",
        input_schema={"in2": {"type": "string", "required": True}},
        output_schema={"out2": {"type": "string", "required": True}},
        is_active=True
    )
    db_session.add(agent1)
    db_session.add(agent2)
    db_session.commit()

    definition = {
        "nodes": [
            {"id": "in", "type": "input"},
            {"id": "n1", "type": "agent", "data": {"agent_id": agent1.id, "mappings": {"in1": {"source": "context", "value": "input.in1"}}}},
            {"id": "n2", "type": "agent", "data": {"agent_id": agent2.id, "mappings": {"in2": {"source": "node", "node_id": "n1", "path": "out1"}}}},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"source": "in", "target": "n1"},
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "end"}
        ]
    }

    res = validate_workflow_definition(definition, db_session)
    assert res["is_valid"] is False
    assert any("schema mismatch" in str(e).lower() or "type mismatch" in str(e).lower() or "expected string" in str(e).lower() for e in res["errors"]), f"Errors: {res['errors']}"
