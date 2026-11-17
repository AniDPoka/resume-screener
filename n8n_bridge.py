"""Hands recruiter-approved candidates to n8n, which then sends the interview invites.

No AI here, and no Streamlit, so tests.py can check it directly.

What leaves the screener is kept to the minimum n8n needs: each candidate's name and email, and the
job title. Scores, flags and the AI's reasons are never sent.

The request is signed with a secret shared only by this app and n8n (N8N_SECRET in
.streamlit/secrets.toml), so n8n can refuse anything that did not come from the recruiter's click.
"""

import hashlib
import hmac
import json
import re
import urllib.request
import uuid
from datetime import datetime, timezone

import variants

INVITE_PATH = "/webhook/interview/invite"


def sign(secret, text):
    """A signature only someone with the secret can make: HMAC-SHA256, written as hex."""
    return hmac.new(secret.encode(), text.encode(), hashlib.sha256).hexdigest()


def contact(resume):
    """The name and email of one resume (a dict from ingest.read_resume), for the invite.
    The id is the file name without its ending, e.g. '01_priya_raman'."""
    match = re.search(r"^Email:\s*(\S+@\S+)\s*$", resume["text"], re.MULTILINE)
    who = variants.person(resume["text"])
    return {"id": resume["name"].rsplit(".", 1)[0], "name": who["full"], "email": match.group(1) if match else None}


def build_invite_request(approved, resumes, role, secret, now=None):
    """The signed request for n8n.

    approved: file names the recruiter ticked, e.g. ["01_priya_raman.txt"]
    resumes:  all resumes (dicts from ingest.read_resume), to look up name and email
    role:     the job title
    Returns {"body": text, "signature": hex}. body is the JSON text that was signed, sent as it is,
    so n8n checks exactly the text that was signed."""
    by_name = {r["name"]: r for r in resumes}
    candidates = []
    for name in approved:
        if name not in by_name:
            raise ValueError(f"{name} is not one of the resumes")
        person = contact(by_name[name])
        if not person["email"] or not person["name"]:
            raise ValueError(f"{name} has no name or email, so no invite can be sent")
        candidates.append(person)
    if not candidates:
        raise ValueError("No candidates were approved")
    body = json.dumps({
        "request_id": str(uuid.uuid4()),  # n8n refuses the same request twice
        "sent_at": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "role": role,
        "candidates": candidates,
    }, ensure_ascii=False)
    return {"body": body, "signature": sign(secret, body)}


def send_invites(n8n_url, request, timeout=30):
    """Posts the signed request to n8n's invite workflow and returns n8n's answer (a dict).
    Raises an error if n8n cannot be reached or refuses the request."""
    req = urllib.request.Request(n8n_url.rstrip("/") + INVITE_PATH, data=json.dumps(request).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode())
