"""Builds n8n/interview_workflow.json (the file n8n imports) from the readable steps in n8n/code/.

Each Code node gets helpers.js (settings and shared helpers) followed by its own step file.
Run after changing anything in n8n/code/:   .venv/bin/python n8n/build_workflow.py
The output is the same every time (fixed ids), so git only shows real changes.
"""

import json
import uuid
from pathlib import Path

HERE = Path(__file__).parent
CODE = HERE / "code"
OUT = HERE / "interview_workflow.json"
WORKFLOW_ID = "rsInterviewFlow1"  # fixed, so importing again updates the same workflow
NAMESPACE = uuid.UUID("6f1b3c2a-0d4e-4b7a-9a51-3c1f2e7d8b90")


def fixed_id(name):
    """The same id every build, made from the node's name."""
    return str(uuid.uuid5(NAMESPACE, name))


def code_node(name, step_file, x, y):
    js = (CODE / "helpers.js").read_text() + "\n" + (CODE / step_file).read_text()
    return {"name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [x, y],
            "parameters": {"mode": "runOnceForAllItems", "jsCode": js}}


def webhook(name, method, path, x, y):
    return {"name": name, "type": "n8n-nodes-base.webhook", "typeVersion": 2.2, "position": [x, y],
            "webhookId": fixed_id("webhook " + path),
            "parameters": {"httpMethod": method, "path": path, "responseMode": "responseNode", "options": {}}}


def respond_json(name, code, x, y):
    return {"name": name, "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1.5, "position": [x, y],
            "parameters": {"respondWith": "json", "responseBody": "={{ JSON.stringify($json) }}",
                           "options": {"responseCode": code}}}


def respond_page(name, code, x, y):
    return {"name": name, "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1.5, "position": [x, y],
            "parameters": {"respondWith": "text", "responseBody": "={{ $json.html }}",
                           "options": {"responseCode": code, "responseHeaders": {"entries": [
                               {"name": "Content-Type", "value": "text/html; charset=utf-8"}]}}}}


def if_ok(name, x, y):
    return {"name": name, "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": [x, y],
            "parameters": {"conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict", "version": 2},
                "conditions": [{"id": fixed_id(name), "leftValue": "={{ $json.ok }}", "rightValue": "",
                                "operator": {"type": "boolean", "operation": "true", "singleValue": True}}],
                "combinator": "and"}, "options": {}}}


def note(name, text, x, y, width, height):
    return {"name": name, "type": "n8n-nodes-base.stickyNote", "typeVersion": 1, "position": [x, y],
            "parameters": {"content": text, "width": width, "height": height}}


NODES = [
    note("Note: invites", "## 1. Invites\nThe recruiter approves candidates in the screener app and clicks **Send invites**. "
         "The request is signed, so only the app can start this. Each candidate is held 3 free times and gets an email "
         "(test mode: saved to the outbox, not sent).", -40, -140, 1180, 420),
    webhook("Recruiter sends invites", "POST", "interview/invite", 0, 100),
    code_node("Check it came from the screener", "check_request.js", 220, 100),
    if_ok("Genuine request?", 440, 100),
    code_node("Hold 3 free times per candidate", "offer_slots.js", 660, 0),
    code_node("Write and save invite emails", "write_invites.js", 880, 0),
    respond_json("Answer the screener", 200, 1100, 0),
    respond_json("Refuse the request", 401, 660, 200),

    note("Note: booking", "## 2. Booking\nThe candidate clicks a time in the email. The link is signed, so it cannot be "
         "made up or changed. The time is booked (test mode: a simulated calendar), a confirmation is written, and if "
         "someone took that time a moment earlier, 3 new times are offered.", -40, 320, 1180, 400),
    webhook("Candidate picks a time", "GET", "interview/book", 0, 540),
    code_node("Check the link is genuine", "check_link.js", 220, 540),
    if_ok("Genuine link?", 440, 540),
    code_node("Book it or offer new times", "book_slot.js", 660, 460),
    respond_page("Show the booking page", 200, 880, 460),
    respond_page("Show 'link not valid'", 403, 660, 640),

    note("Note: follow-ups", "## 3. Reminders and follow-ups\nEvery 15 minutes: a reminder 24 hours before each interview, "
         "one follow-up after 3 days without an answer, and a note to the recruiter after 5 days. "
         "Nobody is rejected automatically.", -40, 760, 1180, 380),
    {"name": "Every 15 minutes", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 920],
     "parameters": {"rule": {"interval": [{"field": "minutes", "minutesInterval": 15}]}}},
    code_node("Reminders and follow-ups", "reminders.js", 220, 920),
    webhook("Run the checks now (test mode)", "GET", "interview/checks", 0, 1060),
    code_node("Reminders and follow-ups (on request)", "reminders.js", 220, 1060),
    respond_json("Report what was done", 200, 440, 1060),

    note("Note: viewing", "## 4. See what happened\n**/outbox**: every email and the calendar. **/log**: the audit log. "
         "**/reset** (test mode, signed): start a fresh demo.", -40, 1180, 1180, 520),
    webhook("Open the outbox", "GET", "interview/outbox", 0, 1340),
    code_node("Show the outbox and calendar", "outbox.js", 220, 1340),
    respond_page("Outbox page", 200, 440, 1340),
    webhook("Open the audit log", "GET", "interview/log", 0, 1480),
    code_node("Show the audit log", "show_log.js", 220, 1480),
    respond_json("Audit log", 200, 440, 1480),
    webhook("Reset for a new demo", "GET", "interview/reset", 0, 1620),
    code_node("Clear everything (test mode)", "reset.js", 220, 1620),
    respond_json("Reset result", 200, 440, 1620),
]

LINKS = [
    ("Recruiter sends invites", "Check it came from the screener"),
    ("Check it came from the screener", "Genuine request?"),
    ("Genuine request?", "Hold 3 free times per candidate", 0),
    ("Genuine request?", "Refuse the request", 1),
    ("Hold 3 free times per candidate", "Write and save invite emails"),
    ("Write and save invite emails", "Answer the screener"),
    ("Candidate picks a time", "Check the link is genuine"),
    ("Check the link is genuine", "Genuine link?"),
    ("Genuine link?", "Book it or offer new times", 0),
    ("Genuine link?", "Show 'link not valid'", 1),
    ("Book it or offer new times", "Show the booking page"),
    ("Every 15 minutes", "Reminders and follow-ups"),
    ("Run the checks now (test mode)", "Reminders and follow-ups (on request)"),
    ("Reminders and follow-ups (on request)", "Report what was done"),
    ("Open the outbox", "Show the outbox and calendar"),
    ("Show the outbox and calendar", "Outbox page"),
    ("Open the audit log", "Show the audit log"),
    ("Show the audit log", "Audit log"),
    ("Reset for a new demo", "Clear everything (test mode)"),
    ("Clear everything (test mode)", "Reset result"),
]


def build():
    nodes = [{"id": fixed_id(n["name"]), **n} for n in NODES]
    connections = {}
    for link in LINKS:
        source, target, output = (link + (0,))[:3]
        outputs = connections.setdefault(source, {"main": []})["main"]
        while len(outputs) <= output:
            outputs.append([])
        outputs[output].append({"node": target, "type": "main", "index": 0})
    return {"id": WORKFLOW_ID, "name": "Interview scheduling (resume screener)", "active": False,
            "nodes": nodes, "connections": connections,
            "settings": {"executionOrder": "v1", "timezone": "Europe/London", "saveManualExecutions": True}}


if __name__ == "__main__":
    OUT.write_text(json.dumps(build(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}")
