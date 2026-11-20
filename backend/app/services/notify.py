"""'Tell me when it fails': an automation can name a Slack, Teams or email connection that is
notified whenever a real (non-test) run fails. Best effort: notification errors are only logged."""

import logging

from sqlalchemy.orm import Session

from ..crypto import decrypt_json
from ..models import Credential, Run, User, Workflow
from ..nodes import NodeContext, NodeError, get_node_type
from ..rbac import can_view
from .platform_settings import get_settings

logger = logging.getLogger("agentos.notify")


def failure_settings(definition: dict) -> dict:
    s = ((definition or {}).get("settings") or {}).get("notify_on_failure") or {}
    return s if isinstance(s, dict) else {}


def notify_failure(db: Session, run: Run) -> None:
    if run.target_type != "workflow" or run.source == "test":
        return
    wf = db.get(Workflow, run.target_id)
    if wf is None:
        return
    cfg = failure_settings(wf.definition)
    if not cfg.get("credential_id"):
        return
    owner = db.get(User, wf.owner_id) if wf.owner_id else None
    try:
        cred = db.get(Credential, int(cfg["credential_id"]))
    except (TypeError, ValueError):
        cred = None
    if cred is None or owner is None or not can_view(owner, cred):
        logger.warning("Failure notification for workflow %s skipped: connection unavailable", wf.id)
        return

    text = (
        f"Workflow '{wf.name}' failed (run #{run.id}, started by {run.source}).\n"
        f"Reason: {run.error or 'unknown'}\n"
        "Open Star Dust > History for details."
    )

    def get_credential(cred_id, expected_type):
        if cred.type != expected_type:
            raise NodeError("wrong connection type")
        return decrypt_json(cred.data_encrypted)

    ctx = NodeContext(
        role=owner.role,
        get_credential=get_credential,
        ask_llm=lambda *a, **k: (_ for _ in ()).throw(NodeError("not available")),
        run_agent=lambda *a, **k: (_ for _ in ()).throw(NodeError("not available")),
        settings=get_settings(db),
    )
    try:
        if cred.type == "slack_webhook":
            get_node_type("slack_message").handler({"credential_id": cred.id, "text": text}, ctx)
        elif cred.type == "teams_webhook":
            get_node_type("teams_message").handler(
                {"credential_id": cred.id, "title": "Workflow failed", "text": text}, ctx
            )
        elif cred.type == "smtp" and cfg.get("email_to"):
            get_node_type("send_email").handler(
                {
                    "credential_id": cred.id,
                    "to": cfg["email_to"],
                    "subject": f"Workflow failed: {wf.name}",
                    "body": text,
                },
                ctx,
            )
        else:
            return
        logger.info("Sent failure notification for run %s", run.id)
    except Exception as exc:  # noqa: BLE001 - never let a notification break run bookkeeping
        logger.warning("Failure notification for run %s could not be sent: %s", run.id, exc)
