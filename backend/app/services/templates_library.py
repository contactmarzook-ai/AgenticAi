"""Ready-made automation templates. Each is a blueprint (see blueprint.py)."""

TEMPLATES = [
    {
        "key": "support-ticket-router",
        "name": "Route support tickets",
        "category": "Customer service",
        "description": "AI reads an incoming ticket, decides if it is billing, technical or other, and drafts the right reply.",
        "needs": [],
        "steps": [
            {
                "id": "start",
                "type": "start",
                "label": "New ticket",
                "fields": [
                    {"key": "customer", "label": "Customer name", "type": "text", "required": True},
                    {"key": "message", "label": "Ticket text", "type": "textarea", "required": True},
                ],
            },
            {
                "id": "classify",
                "type": "action",
                "action": "ai_classify",
                "label": "What is it about?",
                "config": {"text": "{{input.message}}", "categories": ["billing", "technical", "other"]},
            },
            {
                "id": "route",
                "type": "switch",
                "label": "Route by topic",
                "value": "{{classify.category}}",
                "cases": ["billing", "technical"],
            },
            {
                "id": "billing",
                "type": "action",
                "action": "ai_prompt",
                "label": "Billing reply",
                "config": {
                    "instruction": "Write a short, friendly reply to {{input.customer}} about this billing question. "
                    "Say the finance team will confirm within 1 business day.\n\n{{input.message}}"
                },
            },
            {
                "id": "technical",
                "type": "action",
                "action": "ai_prompt",
                "label": "Technical reply",
                "config": {
                    "instruction": "Write a short reply to {{input.customer}} with first troubleshooting steps for:\n\n{{input.message}}"
                },
            },
            {
                "id": "other",
                "type": "action",
                "action": "ai_prompt",
                "label": "General reply",
                "config": {
                    "instruction": "Write a short, polite acknowledgement to {{input.customer}} for:\n\n{{input.message}}"
                },
            },
            {"id": "finish", "type": "finish", "label": "Reply ready"},
        ],
        "links": [
            {"from": "start", "to": "classify"},
            {"from": "classify", "to": "route"},
            {"from": "route", "to": "billing", "branch": "billing"},
            {"from": "route", "to": "technical", "branch": "technical"},
            {"from": "route", "to": "other", "branch": "default"},
            {"from": "billing", "to": "finish"},
            {"from": "technical", "to": "finish"},
            {"from": "other", "to": "finish"},
        ],
    },
    {
        "key": "invoice-approval",
        "name": "Invoice check & approval",
        "category": "Finance",
        "description": "Extracts invoice details from pasted text; invoices over a limit get an approval request, others are auto-approved.",
        "needs": [],
        "steps": [
            {
                "id": "start",
                "type": "start",
                "label": "Invoice received",
                "fields": [
                    {"key": "invoice_text", "label": "Invoice text", "type": "textarea", "required": True},
                    {"key": "limit", "label": "Approval limit", "type": "number", "required": False},
                ],
            },
            {
                "id": "extract",
                "type": "action",
                "action": "ai_extract",
                "label": "Read the invoice",
                "config": {
                    "text": "{{input.invoice_text}}",
                    "fields": ["vendor", "invoice_number", "total_amount", "due_date"],
                },
            },
            {
                "id": "big",
                "type": "if",
                "label": "Above the limit?",
                "left": "{{extract.total_amount}}",
                "operator": ">",
                "right": "{{input.limit}}",
            },
            {
                "id": "ask",
                "type": "action",
                "action": "ai_prompt",
                "label": "Draft approval request",
                "config": {
                    "instruction": "Write a 3-line approval request to the finance manager for invoice "
                    "{{extract.invoice_number}} from {{extract.vendor}} for {{extract.total_amount}}, due {{extract.due_date}}."
                },
            },
            {
                "id": "auto",
                "type": "action",
                "action": "set_fields",
                "label": "Auto-approve",
                "config": {
                    "fields": {
                        "status": "auto-approved",
                        "invoice": "{{extract.invoice_number}}",
                        "amount": "{{extract.total_amount}}",
                    }
                },
            },
            {"id": "finish", "type": "finish", "label": "Done"},
        ],
        "links": [
            {"from": "start", "to": "extract"},
            {"from": "extract", "to": "big"},
            {"from": "big", "to": "ask", "branch": "true"},
            {"from": "big", "to": "auto", "branch": "false"},
            {"from": "ask", "to": "finish"},
            {"from": "auto", "to": "finish"},
        ],
    },
    {
        "key": "meeting-notes",
        "name": "Meeting notes → summary & actions",
        "category": "Productivity",
        "description": "Turns raw meeting notes into a summary and a clear list of action items with owners.",
        "needs": [],
        "steps": [
            {
                "id": "start",
                "type": "start",
                "label": "Notes",
                "fields": [{"key": "notes", "label": "Meeting notes", "type": "textarea", "required": True}],
            },
            {
                "id": "summary",
                "type": "action",
                "action": "ai_summarize",
                "label": "Summarize",
                "config": {"text": "{{input.notes}}", "length": "short"},
            },
            {
                "id": "actions",
                "type": "action",
                "action": "ai_prompt",
                "label": "List action items",
                "config": {
                    "instruction": "From these meeting notes, list every action item as '- <owner>: <task> (due <date if any>)'. "
                    "Only the list.\n\n{{input.notes}}"
                },
            },
            {
                "id": "compose",
                "type": "action",
                "action": "compose_text",
                "label": "Write the recap",
                "config": {"template": "Summary\n{{summary.summary}}\n\nAction items\n{{actions.text}}"},
            },
            {"id": "finish", "type": "finish", "label": "Recap ready", "output": "{{compose.text}}"},
        ],
        "links": [
            {"from": "start", "to": "summary"},
            {"from": "summary", "to": "actions"},
            {"from": "actions", "to": "compose"},
            {"from": "compose", "to": "finish"},
        ],
    },
    {
        "key": "translate-reply",
        "name": "Reply in the customer's language",
        "category": "Customer service",
        "description": "Translates a customer message to English, drafts a reply, and translates the reply back.",
        "needs": [],
        "steps": [
            {
                "id": "start",
                "type": "start",
                "label": "Customer message",
                "fields": [
                    {"key": "message", "label": "Message", "type": "textarea", "required": True},
                    {"key": "language", "label": "Customer's language", "type": "text", "required": True},
                ],
            },
            {
                "id": "to_en",
                "type": "action",
                "action": "ai_translate",
                "label": "Translate to English",
                "config": {"text": "{{input.message}}", "language": "English"},
            },
            {
                "id": "draft",
                "type": "action",
                "action": "ai_prompt",
                "label": "Draft reply",
                "config": {"instruction": "Write a helpful, polite reply to this customer message:\n\n{{to_en.text}}"},
            },
            {
                "id": "back",
                "type": "action",
                "action": "ai_translate",
                "label": "Translate reply back",
                "config": {"text": "{{draft.text}}", "language": "{{input.language}}"},
            },
            {"id": "finish", "type": "finish", "label": "Reply ready", "output": "{{back.text}}"},
        ],
        "links": [
            {"from": "start", "to": "to_en"},
            {"from": "to_en", "to": "draft"},
            {"from": "draft", "to": "back"},
            {"from": "back", "to": "finish"},
        ],
    },
    {
        "key": "lead-qualification",
        "name": "Qualify new leads",
        "category": "Sales",
        "description": "Extracts budget and timeline from a lead's message, scores it hot/warm/cold, and alerts Slack for hot leads.",
        "needs": ["slack_webhook"],
        "steps": [
            {
                "id": "start",
                "type": "start",
                "label": "New lead",
                "fields": [
                    {"key": "name", "label": "Name", "type": "text", "required": True},
                    {"key": "company", "label": "Company", "type": "text"},
                    {"key": "message", "label": "Their message", "type": "textarea", "required": True},
                ],
            },
            {
                "id": "details",
                "type": "action",
                "action": "ai_extract",
                "label": "Pick out the details",
                "config": {"text": "{{input.message}}", "fields": ["budget", "timeline", "need"]},
            },
            {
                "id": "score",
                "type": "action",
                "action": "ai_classify",
                "label": "Score the lead",
                "config": {
                    "text": "Lead: {{input.name}} ({{input.company}}). Need: {{details.need}}. Budget: {{details.budget}}. "
                    "Timeline: {{details.timeline}}.",
                    "categories": ["hot", "warm", "cold"],
                    "guidance": "hot = clear need, budget and timeline within 3 months.",
                },
            },
            {
                "id": "is_hot",
                "type": "if",
                "label": "Hot lead?",
                "left": "{{score.category}}",
                "operator": "==",
                "right": "hot",
            },
            {
                "id": "slack",
                "type": "action",
                "action": "slack_message",
                "label": "Alert sales on Slack",
                "config": {
                    "credential_id": "",
                    "text": ":fire: Hot lead: {{input.name}} ({{input.company}}) - {{details.need}}, "
                    "budget {{details.budget}}, timeline {{details.timeline}}",
                },
            },
            {"id": "finish", "type": "finish", "label": "Scored"},
        ],
        "links": [
            {"from": "start", "to": "details"},
            {"from": "details", "to": "score"},
            {"from": "score", "to": "is_hot"},
            {"from": "is_hot", "to": "slack", "branch": "true"},
            {"from": "is_hot", "to": "finish", "branch": "false"},
            {"from": "slack", "to": "finish"},
        ],
    },
    {
        "key": "uptime-check",
        "name": "Website / API health check",
        "category": "IT operations",
        "description": "Calls a URL on a schedule and emails the team if it does not answer with HTTP 200.",
        "needs": ["smtp"],
        "steps": [
            {"id": "start", "type": "start", "label": "Every 15 minutes (add a schedule)"},
            {
                "id": "call",
                "type": "action",
                "action": "http_request",
                "label": "Call the site",
                "config": {"method": "GET", "url": "https://example.com/health", "fail_on_error_status": False},
                "settings": {"retries": 2, "retry_delay_seconds": 5, "continue_on_error": True},
            },
            {
                "id": "down",
                "type": "if",
                "label": "Not OK?",
                "left": "{{call.status}}",
                "operator": "!=",
                "right": "200",
            },
            {
                "id": "mail",
                "type": "action",
                "action": "send_email",
                "label": "Email the on-call team",
                "config": {
                    "credential_id": "",
                    "to": "oncall@yourcompany.com",
                    "subject": "Health check failed",
                    "body": "The health check failed.\nStatus: {{call.status}}\nError: {{call.error}}",
                },
            },
            {"id": "finish", "type": "finish", "label": "Checked"},
        ],
        "links": [
            {"from": "start", "to": "call"},
            {"from": "call", "to": "down"},
            {"from": "down", "to": "mail", "branch": "true"},
            {"from": "down", "to": "finish", "branch": "false"},
            {"from": "mail", "to": "finish"},
        ],
    },
    {
        "key": "daily-briefing",
        "name": "Daily team briefing to Teams",
        "category": "Productivity",
        "description": "Every morning, writes a short briefing for the day and posts it to a Microsoft Teams channel.",
        "needs": ["teams_webhook"],
        "steps": [
            {"id": "start", "type": "start", "label": "Every weekday at 9:00 (add a schedule)"},
            {
                "id": "today",
                "type": "action",
                "action": "date_time",
                "label": "Today's date",
                "config": {"timezone": "UTC", "format": "human"},
            },
            {
                "id": "write",
                "type": "action",
                "action": "ai_prompt",
                "label": "Write the briefing",
                "config": {
                    "instruction": "Write a 4-line upbeat team briefing for {{today.value}}. Include one focus tip."
                },
            },
            {
                "id": "post",
                "type": "action",
                "action": "teams_message",
                "label": "Post to Teams",
                "config": {"credential_id": "", "title": "Briefing for {{today.weekday}}", "text": "{{write.text}}"},
            },
            {"id": "finish", "type": "finish", "label": "Posted"},
        ],
        "links": [
            {"from": "start", "to": "today"},
            {"from": "today", "to": "write"},
            {"from": "write", "to": "post"},
            {"from": "post", "to": "finish"},
        ],
    },
    {
        "key": "document-summary-email",
        "name": "Summarize a document and email it",
        "category": "Productivity",
        "description": "Paste any long text; get a bullet-point summary emailed to whoever you choose.",
        "needs": ["smtp"],
        "steps": [
            {
                "id": "start",
                "type": "start",
                "label": "Document",
                "fields": [
                    {"key": "title", "label": "Title", "type": "text", "required": True},
                    {"key": "text", "label": "Text", "type": "textarea", "required": True},
                    {"key": "email", "label": "Send to", "type": "email", "required": True},
                ],
            },
            {
                "id": "sum",
                "type": "action",
                "action": "ai_summarize",
                "label": "Summarize",
                "config": {"text": "{{input.text}}", "length": "detailed bullet points"},
            },
            {
                "id": "mail",
                "type": "action",
                "action": "send_email",
                "label": "Email the summary",
                "config": {
                    "credential_id": "",
                    "to": "{{input.email}}",
                    "subject": "Summary: {{input.title}}",
                    "body": "{{sum.summary}}",
                },
            },
            {"id": "finish", "type": "finish", "label": "Sent"},
        ],
        "links": [{"from": "start", "to": "sum"}, {"from": "sum", "to": "mail"}, {"from": "mail", "to": "finish"}],
    },
]

BY_KEY = {t["key"]: t for t in TEMPLATES}
