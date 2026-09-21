--- backend/tests/test_workflow_validator.py
+++ backend/tests/test_workflow_validator.py
@@ -1,5 +1,19 @@
 import pytest
+from sqlalchemy import create_engine
+from sqlalchemy.orm import sessionmaker
+from app.database import Base
 from app.services.workflow_validator import validate_workflow_definition

+SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
+engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
+TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
+
+@pytest.fixture()
+def db_session():
+    Base.metadata.create_all(bind=engine)
+    db = TestingSessionLocal()
+    try:
+        yield db
+    finally:
+        db.close()
+        Base.metadata.drop_all(bind=engine)
+
 def test_validate_workflow_definition_empty():
     res = validate_workflow_definition({"nodes": [], "edges": []}, None)
@@ -7,14 +21,13 @@
     assert "Workflow must have at least one node." in res["errors"]

-def test_validate_workflow_definition_missing_endpoints():
+def test_validate_workflow_definition_missing_endpoints(db_session):
     definition = {
         "nodes": [{"id": "n1", "type": "agent", "data": {"agent_id": 1}}],
         "edges": []
     }
-    # Create mock DB session if needed, but here missing input/end will fail first
-    res = validate_workflow_definition(definition, None)
+    res = validate_workflow_definition(definition, db_session)
     assert res["is_valid"] is False
     assert "Workflow must have an Input Node." in res["errors"]
     assert "Workflow must have an End Node." in res["errors"]
