"""App steps: talk to other systems. Secrets come from encrypted connections."""

import json
import smtplib
import ssl
from email.message import EmailMessage

import httpx

from .. import safe_http
from .base import Field, NodeContext, NodeError, credential_type, node

# ---------------- connection types ----------------
credential_type(
    "smtp",
    "Email (SMTP)",
    [
        Field("host", "SMTP server", "text", required=True, placeholder="smtp.office365.com"),
        Field("port", "Port", "number", required=True, default=587),
        Field("username", "Username", "text"),
        Field("password", "Password", "password"),
        Field("from_address", "From address", "text", required=True, placeholder="automation@yourcompany.com"),
        Field("security", "Security", "select", default="starttls", options=("starttls", "ssl", "none")),
    ],
    help="Used by the Send email step.",
)
credential_type(
    "slack_webhook",
    "Slack (incoming webhook)",
    [Field("url", "Webhook URL", "password", required=True, placeholder="https://hooks.slack.com/services/...")],
    help="Create an incoming webhook in Slack and paste its URL.",
)
credential_type(
    "teams_webhook",
    "Microsoft Teams (incoming webhook)",
    [Field("url", "Webhook URL", "password", required=True)],
    help="Add an Incoming Webhook / Workflows webhook to a Teams channel and paste its URL.",
)
credential_type(
    "http_header",
    "API key (header)",
    [
        Field("header_name", "Header name", "text", required=True, default="Authorization"),
        Field("header_value", "Header value", "password", required=True, placeholder="Bearer sk-..."),
    ],
    help="Adds one secret header to HTTP requests.",
)
credential_type(
    "http_basic",
    "Username & password (HTTP basic)",
    [Field("username", "Username", "text", required=True), Field("password", "Password", "password", required=True)],
)


def _auth_from(ctx: NodeContext, credential_id) -> tuple[dict, tuple | None]:
    if not credential_id:
        return {}, None
    for ctype in ("http_header", "http_basic"):
        try:
            cred = ctx.get_credential(credential_id, ctype)
        except NodeError:
            continue
        if ctype == "http_header":
            return {cred["header_name"]: cred["header_value"]}, None
        return {}, (cred["username"], cred["password"])
    raise NodeError("The selected connection is not an API key or username/password connection")


# ---------------- steps ----------------
@node(
    "http_request",
    "HTTP request",
    "Apps",
    "Call any web API (GET, POST, ...). The response is available to later steps.",
    "globe",
    [
        Field("method", "Method", "select", default="GET", options=("GET", "POST", "PUT", "PATCH", "DELETE")),
        Field("url", "URL", "text", required=True, placeholder="https://api.example.com/orders/{{input.order_id}}"),
        Field("headers", "Headers", "keyvalue"),
        Field("body", "Body (JSON)", "json", help="For POST/PUT/PATCH. Variables are allowed inside strings."),
        Field(
            "credential_id",
            "Authentication",
            "credential",
            credential_type="http_header|http_basic",
            help="Optional saved API key.",
        ),
        Field("fail_on_error_status", "Fail if the server returns an error (4xx/5xx)", "boolean", default=True),
    ],
    output_hint="{ status, ok, body, json }",
)
def http_request(cfg: dict, ctx: NodeContext):
    headers = {str(k): str(v) for k, v in (cfg.get("headers") or {}).items()}
    auth_headers, basic = _auth_from(ctx, cfg.get("credential_id"))
    headers.update(auth_headers)
    body = cfg.get("body")
    if isinstance(body, str) and body.strip():
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            pass  # send as text
    method = (cfg.get("method") or "GET").upper()
    try:
        resp = safe_http.request(
            method,
            str(cfg["url"]),
            ctx.settings,
            headers=headers,
            json_body=body if method != "GET" and not isinstance(body, str) and body not in (None, "") else None,
            content=body if method != "GET" and isinstance(body, str) and body else None,
            auth=basic,
        )
    except safe_http.BlockedRequest as exc:
        raise NodeError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise NodeError(f"Request failed: {exc.__class__.__name__}") from exc
    text = resp.text
    try:
        parsed = resp.json()
    except ValueError:
        parsed = None
    if cfg.get("fail_on_error_status", True) and resp.status_code >= 400:
        raise NodeError(f"Server answered HTTP {resp.status_code}: {text[:300]}")
    return {"status": resp.status_code, "ok": resp.status_code < 400, "body": text[:50_000], "json": parsed}


@node(
    "send_email",
    "Send email",
    "Apps",
    "Send an email through your SMTP server.",
    "mail",
    [
        Field("credential_id", "Email account", "credential", required=True, credential_type="smtp"),
        Field("to", "To", "text", required=True, placeholder="ops@yourcompany.com, {{input.email}}"),
        Field("subject", "Subject", "text", required=True),
        Field("body", "Message", "textarea", required=True),
        Field("cc", "Cc", "text"),
    ],
    output_hint="{ sent, to }",
)
def send_email(cfg: dict, ctx: NodeContext):
    cred = ctx.get_credential(cfg["credential_id"], "smtp")
    recipients = [a.strip() for a in str(cfg["to"]).replace(";", ",").split(",") if a.strip()]
    cc = [a.strip() for a in str(cfg.get("cc") or "").replace(";", ",").split(",") if a.strip()]
    if not recipients or any("@" not in a for a in recipients + cc):
        raise NodeError("Enter valid email addresses")
    msg = EmailMessage()
    msg["From"] = cred["from_address"]
    msg["To"] = ", ".join(recipients)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = str(cfg["subject"])[:300]
    msg.set_content(str(cfg["body"]))
    host, port, security = cred["host"], int(cred.get("port") or 587), cred.get("security") or "starttls"
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=30, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=30)
        with server:
            if security == "starttls":
                server.starttls(context=ssl.create_default_context())
            if cred.get("username"):
                server.login(cred["username"], cred.get("password") or "")
            server.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise NodeError("Email could not be sent: the email server rejected the username or password") from exc
    except smtplib.SMTPRecipientsRefused as exc:
        raise NodeError("Email could not be sent: the server refused the recipient address") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise NodeError(
            f"Email could not be sent: could not reach the email server '{host}:{port}' ({exc.__class__.__name__}). "
            "Check the server name and port in the connection."
        ) from exc
    return {"sent": True, "to": recipients + cc}


def _post_webhook(url: str, payload: dict, ctx: NodeContext) -> dict:
    try:
        resp = safe_http.request("POST", url, ctx.settings, json_body=payload, trusted_host=True)
    except safe_http.BlockedRequest as exc:
        raise NodeError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise NodeError(f"Request failed: {exc.__class__.__name__}") from exc
    if resp.status_code >= 400:
        raise NodeError(f"Webhook answered HTTP {resp.status_code}: {resp.text[:200]}")
    return {"sent": True, "status": resp.status_code}


@node(
    "slack_message",
    "Slack message",
    "Apps",
    "Post a message to a Slack channel.",
    "message-square",
    [
        Field("credential_id", "Slack connection", "credential", required=True, credential_type="slack_webhook"),
        Field("text", "Message", "textarea", required=True),
    ],
    output_hint="{ sent }",
)
def slack_message(cfg: dict, ctx: NodeContext):
    cred = ctx.get_credential(cfg["credential_id"], "slack_webhook")
    return _post_webhook(cred["url"], {"text": str(cfg["text"])}, ctx)


@node(
    "teams_message",
    "Teams message",
    "Apps",
    "Post a message to a Microsoft Teams channel.",
    "message-circle",
    [
        Field("credential_id", "Teams connection", "credential", required=True, credential_type="teams_webhook"),
        Field("title", "Title", "text"),
        Field("text", "Message", "textarea", required=True),
    ],
    output_hint="{ sent }",
)
def teams_message(cfg: dict, ctx: NodeContext):
    cred = ctx.get_credential(cfg["credential_id"], "teams_webhook")
    text = f"**{cfg['title']}**\n\n{cfg['text']}" if cfg.get("title") else str(cfg["text"])
    return _post_webhook(cred["url"], {"text": text}, ctx)
