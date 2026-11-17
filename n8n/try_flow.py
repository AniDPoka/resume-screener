"""Runs the whole interview flow against n8n on this Mac and checks every step. No AI is used.

Start n8n first (sh n8n/start_n8n.sh), then:   .venv/bin/python n8n/try_flow.py
It clears n8n's test data, invites 3 sample candidates, books a time for one of them, tries a few
tricks that must be refused, and runs the reminder and follow-up checks as if time had passed.
Each check prints PASS or FAIL. At the end, open http://localhost:5678/webhook/interview/outbox
"""

import json
import re
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

HERE = Path(__file__).parent.parent
sys.path.insert(0, str(HERE))
import ingest  # noqa: E402
import n8n_bridge  # noqa: E402

secrets = tomllib.loads((HERE / ".streamlit" / "secrets.toml").read_text())
SECRET, URL = secrets["N8N_SECRET"], secrets.get("N8N_URL", "http://localhost:5678")
BASE = URL + "/webhook/interview"
failures = []


def check(ok, what):
    print(("PASS  " if ok else "FAIL  ") + what)
    if not ok:
        failures.append(what)


def get(url):
    """(status, text) of a GET request, including refused ones."""
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def post(request):
    try:
        return 200, n8n_bridge.send_invites(URL, request)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def links():
    """Every time button in the outbox: {invite id: [booking links]} (newest email first)."""
    found = {}
    for href in re.findall(r'href="([^"]+/book\?[^"]+)"', get(BASE + "/outbox")[1]):
        href = unescape(href)
        invite = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)["invite"][0]
        found.setdefault(invite, []).append(href)
    return found


def state():
    return json.loads(get(BASE + "/log")[1])


# 0. A fresh start (reset needs a signed link).
at = datetime.now(timezone.utc).isoformat(timespec="seconds")
status, text = get(f"{BASE}/reset?at={urllib.parse.quote(at)}&sig={n8n_bridge.sign(SECRET, 'reset|' + at)}")
check(status == 200 and json.loads(text)["ok"], "the test data was cleared")

job = ingest.read_job(HERE / "data" / "job_description.txt")
resumes = ingest.read_folder(HERE / "data" / "resumes")
role = job["text"].splitlines()[0].replace("Job title: ", "")
approved = ["01_priya_raman.txt", "02_daniel_okafor.txt", "05_margaret_ellis.txt"]

# 1. Tricks that must be refused.
fake = n8n_bridge.build_invite_request(approved, resumes, role, "not-the-real-secret")
check(post(fake)[0] == 401, "a request signed with the wrong secret is refused")
old = n8n_bridge.build_invite_request(approved, resumes, role, SECRET, now=datetime.now(timezone.utc) - timedelta(hours=1))
check(post(old)[0] == 401, "a request older than 10 minutes is refused")

# 2. The recruiter sends invites for 3 approved candidates.
request = n8n_bridge.build_invite_request(approved, resumes, role, SECRET)
check("score" not in request["body"] and "flags" not in request["body"], "only names, emails and the role leave the screener")
status, answer = post(request)
check(status == 200 and answer["invited"] == ["Priya Raman", "Daniel Okafor", "Margaret Ellis"], f"3 invites written: {answer}")
check(post(request)[0] == 401, "the same request cannot be used twice")
status, again = post(n8n_bridge.build_invite_request(approved[:1], resumes, role, SECRET))
check(status == 200 and again["invited"] == [] and again["skipped"], "Priya is not invited twice")

s = state()
offered = [slot for i in s["invites"] for slot in i["offered"]]
check(len(offered) == 9 and len(set(offered)) == 9, "each candidate was offered 3 different times (9 in all, no overlap)")
check(all(datetime.fromisoformat(x).weekday() < 5 and 9 <= datetime.fromisoformat(x).hour <= 16 for x in offered),
      "every time is Monday to Friday, within working hours")
buttons = links()
check(len(buttons) == 3 and all(len(b) == 3 for b in buttons.values()), "each invite email has 3 time buttons")

# 3. Priya books her first time.
priya = next(i for i in s["invites"] if i["name"] == "Priya Raman")
priya_link = buttons[priya["id"]][0]
status, page = get(priya_link)
check(status == 200 and "booked" in page, "Priya's click books the time and shows 'You're booked'")
status, page = get(priya_link)
check(status == 200 and "already booked" in page, "clicking again is harmless")
check(get(priya_link.replace("sig=", "sig=0"))[0] == 403, "a changed link is refused")
daniel = next(i for i in s["invites"] if i["name"] == "Daniel Okafor")
forged = re.sub(r"slot=[^&]+", "slot=" + urllib.parse.quote(priya["offered"][0]), buttons[daniel["id"]][0])
check(get(forged)[0] == 403, "Daniel cannot take Priya's time by editing his link")
s = state()
check(list(s["calendar"].values()) == [priya["id"]], "the simulated calendar has exactly one booking")
check([m for m in s["log"] if m["event"] == "email_saved_to_outbox"][-1]["subject"].startswith("Interview confirmed"),
      "a confirmation email was written")

# 4. Time passes (test mode can pretend): reminder, follow-ups, then a note to the recruiter.
hours_to_interview = (datetime.fromisoformat(priya["offered"][0]) - datetime.now(timezone.utc)).total_seconds() / 3600
status, done = get(f"{BASE}/checks?hours_later={int(hours_to_interview) - 12}")
check("reminder to Priya Raman" in json.loads(done)["actions"], "a reminder is written 24 hours before Priya's interview")
done = json.loads(get(f"{BASE}/checks?hours_later=73")[1])["actions"]
check(sorted(done) == ["follow-up to Daniel Okafor", "follow-up to Margaret Ellis"], f"one follow-up after 3 days: {done}")
done = json.loads(get(f"{BASE}/checks?hours_later=73")[1])["actions"]
check(done == [], "the follow-up is not repeated")
done = json.loads(get(f"{BASE}/checks?hours_later=121")[1])["actions"]
check(sorted(done) == ["recruiter told about Daniel Okafor", "recruiter told about Margaret Ellis"],
      "after 5 days the recruiter is told (nobody is rejected automatically)")
kinds = [m["event"] for m in state()["log"]]
check(not any("reject" in k for k in kinds), "no rejection was sent at any point")

print(f"\n{'All checks passed.' if not failures else f'{len(failures)} check(s) failed.'}")
print(f"Open the outbox: {BASE}/outbox")
sys.exit(1 if failures else 0)
