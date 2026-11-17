"""Runs the whole loop on ONE resume with the real AI, from Terminal. Uses 7 AI calls
(more if it is flagged and goes through revise rounds).

Run with:  .venv/bin/python try_one.py 01_priya_raman.txt
(any file name from data/resumes; the first one if you give none)

The Groq key is read from .streamlit/secrets.toml (GROQ_API_KEY = "...") or from the
GROQ_API_KEY environment variable. It is never printed or saved.
"""

import os
import sys
import tomllib
from pathlib import Path

import ingest
import loop
import scorer
from audit import Audit

HERE = Path(__file__).parent


def read_key():
    secrets = HERE / ".streamlit" / "secrets.toml"
    if secrets.exists():
        key = tomllib.loads(secrets.read_text()).get("GROQ_API_KEY")
        if key:
            return key
    return os.environ.get("GROQ_API_KEY")


def main():
    key = read_key()
    if not key:
        sys.exit("No Groq key found. Put GROQ_API_KEY = \"...\" in .streamlit/secrets.toml")

    file_name = sys.argv[1] if len(sys.argv) > 1 else "01_priya_raman.txt"
    path = HERE / "data" / "resumes" / file_name
    resume = ingest.read_resume(path.read_bytes(), path.name)
    job = ingest.read_job(HERE / "data" / "job_description.txt")

    audit = Audit(loop.settings(), folder=HERE / "audit_logs")
    call = scorer.groq_call(scorer.connect(key))
    try:
        entry = loop.screen_resume(call, job, resume, audit, on_step=print)
    except Exception as error:
        # Say what kind of error it was, never its full text (which could include request details).
        audit.log("stopped", reason=f"AI service error: {type(error).__name__}")
        sys.exit(f"The AI service stopped the run ({type(error).__name__}). See {audit.path}")

    print()
    print(f"Final score: {entry['final_score']} ({entry['score_source']})   original: {entry['original_score']}")
    for item in (entry["judgements"] or {}).get("must_have", []) + (entry["judgements"] or {}).get("nice_to_have", []):
        print(f"  {item['verdict']:8} {item['requirement']}")
    print("Revise rounds:", entry["revise_rounds"], "  Resolved:", entry["resolved"] or "nothing to resolve")
    print("Flags:", entry["flags"] or "none", "  Needs human review:", "YES" if entry["needs_human_review"] else "no")

    calls = [u for s in audit.record["steps"] if s["step"] == "score" for u in s["usage"]]
    print(f"\nAI calls: {len(calls)}, tokens: {sum(c['prompt_tokens'] + c['reply_tokens'] for c in calls)}, "
          f"time: {sum(c['seconds'] for c in calls):.0f}s")
    print(f"Audit file: {audit.path}")


if __name__ == "__main__":
    main()
