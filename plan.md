1.  *Update Database Models & Schemas*
    -   Update `Workflow` model in `backend/app/models.py`. Currently `steps_json` is a simple list of integers. It needs to hold a complex JSON representing the graph (nodes, edges, node-specific configs like agent IDs and mappings). Alternatively, replace it with `nodes` and `edges` JSON columns or a single `definition` JSON column.
    -   Update `WorkflowBase` in `backend/app/schemas.py` to match the new structure.

2.  *Update Workflow Runner (`backend/app/services/workflow_runner.py`)*
    -   Rewrite `run_workflow_pipeline` to parse the graph execution flow.
    -   Support nodes: `input`, `agent`, `condition`, `transform`, `end`.
    -   Maintain a context (a dictionary) storing outputs of all executed nodes by their node ID.
    -   Implement mapping logic: when executing a node, build its inputs based on its mappings (either from workflow input, previous node output, another node output, or static values).
    -   Support conditional branching (evaluate basic conditions like `==`, `<`, `>`).
    -   Ensure deterministic execution (e.g., topological sort or iterative execution based on resolved dependencies).
    -   Return structured output and execution history.

3.  *Build React Flow UI for Workflow Builder*
    -   Create `WorkflowBuilder.jsx` in frontend.
    -   Use `@xyflow/react` to build a visual canvas.
    -   Create custom node components for `input`, `agent`, `condition`, `transform`, and `end`.
    -   Implement a sidebar/modal to edit node properties (select agent, define condition logic, map inputs).
    -   For `agent` nodes, fetch agent details from API to dynamically render input fields based on `input_schema` and allow mapping to previous node outputs or workflow inputs.
    -   Integrate it into the Admin UI (`Management.jsx` or similar). Add a list view for workflows and a builder view.

4.  *Update Orchestrator & Fast-Path Routing*
    -   Update `orchestrator.py` and `fast_path_route` to handle the new workflow execution inputs. Ensure that if an LLM extracts params for a workflow, they are mapped to the Workflow's `input` node.

5.  *Write Tests*
    -   Create tests for `workflow_runner.py` to verify correct graph execution, parameter mapping, conditional branching, and handling missing inputs or failing agents.
    -   Test the new schemas and models.

6.  *Pre-commit & Submit*
    -   Follow `pre_commit_instructions` to test, verify frontend (Playwright screenshots), and review code.
