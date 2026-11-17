"""Makes the SIMULATED example of a flagged resume, for the app's "See how a flagged resume is
handled" button. With the real AI at temperature 0, real runs are rarely flagged, so this shows
the revise rounds working.

It runs the REAL loop code (loop.py) on a sample resume, but with the fake AI from fake_ai.py,
scripted to invent a quote and to disagree with itself once. No AI service is contacted.
The output is marked "simulated": true and must always be shown with that label.

Run with:  .venv/bin/python make_example.py
"""

import json
import tempfile
from pathlib import Path

import ingest
import loop
from audit import Audit
from fake_ai import by_prompt, reply

HERE = Path(__file__).parent
RESUME = "08_liam_murphy.pdf"

REAL_QUOTE = "Involved in reporting and analytics initiatives"   # really in Liam's resume
MADE_UP_QUOTE = "Built advanced Excel models for the HR team"     # not in Liam's resume

# Liam's usual answer: 1 must-have met, 1 partly, the rest not met.
usual = reply(["met", "not met", "partly", "not met"], ["not met"] * 5, quote=REAL_QUOTE)
# Call 2: the fake AI claims Advanced Excel with a quote that is not in the resume.
invented = reply(["met", "met", "partly", "not met"], ["not met"] * 5, quote=MADE_UP_QUOTE)
# Call 9 (revise round 1): it changes its mind on "reports or dashboards", from partly to met.
wobble = reply(["met", "not met", "met", "not met"], ["not met"] * 5, quote=REAL_QUOTE)


def scripted(prompt, number):
    """Which answer the fake AI gives on each call (calls 1-3 original, 4-6 bias versions,
    7 anonymised, 8-10 revise round 1, 11-13 revise round 2)."""
    return {2: invented, 9: wobble}.get(number, usual)


def main():
    resume = ingest.read_resume((HERE / "data" / "resumes" / RESUME).read_bytes(), RESUME)
    job = ingest.read_job(HERE / "data" / "job_description.txt")
    with tempfile.TemporaryDirectory() as folder:
        audit = Audit({**loop.settings(), "model": "simulated (fake AI, no AI service used)"}, folder=folder)
        entry = loop.screen_resume(by_prompt(scripted), job, resume, audit)
    example = {
        "simulated": True,
        "explanation": "A scripted example, not a real AI result. The real loop code ran, but the AI was a "
                       "stand-in that invented one quote and changed its mind once, to show how flags are handled.",
        "entry": entry,
        "steps": audit.record["steps"],
    }
    out = HERE / "data" / "simulated_example.json"
    out.write_text(json.dumps(example, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Revise rounds: {entry['revise_rounds']}, resolved: {entry['resolved']}, flags left: {entry['flags']}")
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
