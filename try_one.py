"""Scores and checks ONE resume with the real AI, from Terminal. Uses 6 AI calls.

Run with:  .venv/bin/python try_one.py 01_priya_raman.txt
(any file name from data/resumes; the first one if you give none)

The Groq key is read from .streamlit/secrets.toml (GROQ_API_KEY = "...") or from the
GROQ_API_KEY environment variable. It is never printed or saved.
"""

import os
import sys
import tomllib
from pathlib import Path

import checks
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

    audit = Audit({"model": scorer.MODEL, "temperature": scorer.TEMPERATURE,
                   "consistency_runs": loop.CONSISTENCY_RUNS, "flag_points": checks.FLAG_POINTS,
                   "points": {"must_have": checks.MUST_HAVE_POINTS, "nice_to_have": checks.NICE_TO_HAVE_POINTS}},
                  folder=HERE / "audit_logs")
    call = scorer.groq_call(scorer.connect(key))
    try:
        result = loop.check_resume(call, job, resume, audit, on_step=print)
    except Exception as error:
        # Say what kind of error it was, never its full text (which could include request details).
        audit.log("stopped", reason=f"AI service error: {type(error).__name__}")
        sys.exit(f"The AI service stopped the run ({type(error).__name__}). See {audit.path}")

    print()
    if "error" in result:
        print(result["error"])
    else:
        print(f"Score: {result['score']}   (3 runs: {result['scores']})")
        print(f"Bias versions vs original: {result['bias']['differences']}")
        for item in result["judgements"]["must_have"] + result["judgements"]["nice_to_have"]:
            print(f"  {item['verdict']:8} {item['requirement']}")
        print("Flags:", result["flags"] or "none")

    calls = [u for s in audit.record["steps"] if s["step"] == "score" for u in s["usage"]]
    print(f"\nAI calls: {len(calls)}, tokens: {sum(c['prompt_tokens'] + c['reply_tokens'] for c in calls)}, "
          f"time: {sum(c['seconds'] for c in calls):.0f}s")
    print(f"Audit file: {audit.path}")


if __name__ == "__main__":
    main()
