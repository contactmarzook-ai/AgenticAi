1.  *Update Database Models & Schemas*
    -   Update `Agent` model in `backend/app/models.py` to include `output_schema` (JSON).
    -   Update `AgentBase` schema in `backend/app/schemas.py` to include `output_schema`.

2.  *Update Agent Validation Logic*
    -   Create `backend/app/services/agent_validator.py` to validate inputs against `input_schema` and outputs against `output_schema` during execution.
    -   Integrate this validation into `backend/app/services/executor.py` before and after handler execution.

3.  *Update Workflow Validation Logic*
    -   Update `backend/app/services/workflow_validator.py` to check that connected nodes have compatible schemas. If Node A outputs `loan_id: string`, and Node B takes `loan_id: string`, mapping A to B is valid. If types mismatch or fields are missing, add to `errors`.

4.  *Update Frontend Agent UI*
    -   Update `AgentManagement.jsx` to include a builder for `output_schema` similar to the existing `input_schema`.

5.  *Update Frontend Workflow Builder UI*
    -   Update `WorkflowBuilder.jsx` to display validation errors if incompatible mappings are made (e.g., in the properties sidebar or when clicking "Test").

6.  *Write Tests*
    -   Write tests for input/output schema validation in `agent_validator.py`.
    -   Write tests for mapping type compatibility in `workflow_validator.py`.

7.  *Pre-commit & Submit*
    -   Run tests, verify frontend visually, and submit.
