import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Workflow
from app.services.workflow_runner import resolve_mapping, evaluate_condition, run_workflow_pipeline

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

def test_resolve_mapping():
    context = {"node1": {"a": 1, "b": 2}}
    initial_input = {"start": 99}

    assert resolve_mapping({"source": "static", "value": 42}, context, initial_input) == 42
    assert resolve_mapping({"source": "workflow", "path": "start"}, context, initial_input) == 99
    assert resolve_mapping({"source": "node", "node_id": "node1", "path": "a"}, context, initial_input) == 1
    assert resolve_mapping({"source": "node", "node_id": "node1"}, context, initial_input) == {"a": 1, "b": 2}

def test_evaluate_condition():
    context = {}
    initial_input = {}

    # 5 > 3
    cond1 = {"left": {"source": "static", "value": 5}, "operator": ">", "right": {"source": "static", "value": 3}}
    assert evaluate_condition(cond1, context, initial_input) is True

    # 5 == 5
    cond2 = {"left": {"source": "static", "value": 5}, "operator": "==", "right": {"source": "static", "value": 5}}
    assert evaluate_condition(cond2, context, initial_input) is True

def test_run_workflow_pipeline_missing_wf(db_session):
    res = run_workflow_pipeline(999, {}, db_session)
    assert res["status"] == "error"
