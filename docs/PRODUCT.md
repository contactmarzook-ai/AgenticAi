# Star Dust - product assessment and release scope

Owner's review of Star Dust against the automation tools our users already know, what overlaps or
over-complicates the product, and what this release therefore contains.

## Who it is for

People who are not developers and want to automate routine work with AI, inside the company,
on models the company controls. Administrators need control over what automations can reach
and who can do what.

## Market comparison

Compared with the tools non-coders most often meet: **n8n**, **Zapier**, **Make** and
**Microsoft Power Automate**. Columns describe the capability class, not exact parity.

| Capability users expect | n8n | Zapier | Make | Power Automate | Star Dust (this release) |
|---|---|---|---|---|---|
| Describe-in-words → draft automation | AI builder | Copilot | AI assistant | Copilot | **Yes** (local model, validated + auto-repaired) |
| Visual step builder, no code | Yes | Linear editor | Yes | Yes | **Yes** |
| Ready-made templates | Large library | Large library | Large library | Large library | **8 curated** |
| AI steps (summarize, classify, extract, translate) | Yes | AI by Zapier | Yes | AI Builder | **Yes**, on own models |
| AI agents with tools | AI Agent node | Agents | Agents | Copilot Studio | **Yes** (tools = same steps as automations) |
| Branching (If / Switch) | Yes | Paths/Filters | Routers/Filters | Conditions/Switch | **Yes** |
| Loop over a list | Yes | Looping | Iterators | Apply to each | **Yes - "Repeat for each"** |
| Triggers: manual form, schedule, webhook | Yes | Yes | Yes | Yes | **Yes** |
| Shareable form anyone can fill in | Form trigger | Interfaces | - | Forms | **Yes - public form link** |
| App-event triggers (new email, new row...) | Yes | Yes | Yes | Yes | No (webhook covers apps that can call out) |
| Large app catalogue with OAuth | Hundreds | Thousands | Thousands | Hundreds+ | **No**: HTTP, email, Slack, Teams + any API via HTTP |
| Saved, encrypted connections | Yes | Yes | Yes | Yes | **Yes** |
| Retries / continue on error | Yes | Autoreplay | Error handlers | Retry policy | **Yes** |
| Alert when an automation fails | Error workflow | Email alerts | Notifications | Notifications | **Yes** (Slack/Teams/email) |
| Run history with per-step data, re-run | Yes | Yes | Yes | Yes | **Yes** |
| Versions: draft / publish / roll back | Enterprise | Versions | Versions | Solutions | **Yes** |
| Admin control of steps, outbound hosts | Enterprise | Admin | Admin | DLP policies | **Yes** (step on/off, host allowlist, private-network block) |
| RBAC, departments, audit log | Enterprise | Enterprise | Enterprise | Yes | **Yes** |
| Runs fully on-premise / own models | Yes (self-host) | No | No | No | **Yes** |

### Conclusion

Star Dust matches the market on the **core loop** non-coders need: describe → review → test →
publish → run from a form / schedule / webhook / chat → see history → get alerted on failure,
with stronger governance and data control than the SaaS tools (self-hosted, own models, admin
allowlists, audit). Its deliberate gap is **breadth of app integrations**: it does not compete on
connector count. Any system with an API is reachable through the HTTP step (with saved API-key
connections), and Slack, Teams and email are built in. App-event triggers and OAuth connectors
are the top items for the next release.

## Overlaps and over-complication found, and what was done

| Finding | Why it hurts | Decision |
|---|---|---|
| Two tool systems: agent "tools" (calculator, get_current_time, http_get, render_template) **and** workflow steps (Calculate, Date & time, HTTP request, Fill template) doing the same jobs | Two names and two behaviours for one thing; admins could switch off a step but agents still had its twin | **One set of building blocks.** Agent tools are now generated from the step catalogue, obey the same admin switches and allowlist; old tool names still work as aliases |
| Agent editor exposes temperature, max steps, trigger keywords up front | Jargon for non-coders | Moved under *Advanced* |
| Automation "chat keywords" shown as a main setting | Chat already routes by AI | Moved under *Advanced* |
| Raw cron expressions for schedules | Not usable by non-coders | Plain picker ("every weekday at 09:00"); cron only under *Custom* |
| Webhook-only way for outsiders to start an automation | Needs a developer | Public form link |
| Older node types (agent/tool/transform) | Duplicates of action steps | Hidden from the builder; still run for old automations |
| Turned-off automations disappeared | Looked like data loss | Stay listed as *Off* with *Turn on* |

Kept on purpose: **Chat** (the conversational entry point to agents and automations, as with
Copilot), **Agents** (for open-ended tasks; automations for repeatable ones), **History**
(everyone) vs **Monitoring** (admin aggregates).

## Release scope (v1.0)

In: everything in the Star Dust column above, the QA fixes from exploratory testing, and the
deployment package (Docker, Kubernetes, CI).

Next release candidates, in priority order: app-event triggers (email inbox, new file, new
row), OAuth connectors (Microsoft 365, Google Workspace), human approval step, SSO (OIDC/SAML),
sub-automations, document knowledge base for agents.
