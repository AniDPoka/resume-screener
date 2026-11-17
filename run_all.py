"""Runs the whole loop on every sample resume with the real AI and saves the ranked shortlist.

Run with:  .venv/bin/python run_all.py
About 9 AI calls per resume (more if one is flagged), so a full run of 9 takes about 20 minutes and
most of Groq's free daily allowance (about 190,000 of 200,000 tokens). Run it on a fresh day.

Saves:
  audit_logs/run_....json   the full audit file (kept on your computer, not in git)
  data/demo_run.json        the shortlist, which the public app shows without using any AI
  data/demo_audit.json      a copy of the audit file, so visitors can see every step
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import ingest
import loop
import scorer
from audit import Audit
from try_one import read_key

HERE = Path(__file__).parent


def main():
    key = read_key()
    if not key:
        sys.exit("No Groq key found. Put GROQ_API_KEY = \"...\" in .streamlit/secrets.toml")

    job = ingest.read_job(HERE / "data" / "job_description.txt")
    resumes = ingest.read_folder(HERE / "data" / "resumes")
    audit = Audit(loop.settings(), folder=HERE / "audit_logs")
    audit.log("job_read", must_have=job["must_have"], nice_to_have=job["nice_to_have"])
    call = scorer.groq_call(scorer.connect(key))

    entries = []
    for resume in resumes:
        try:
            entries.append(loop.screen_resume(call, job, resume, audit, on_step=print))
        except Exception as error:
            # The AI service stopped (e.g. the free daily limit). Keep what is done; list the rest.
            audit.log("stopped", resume=resume["name"], reason=f"AI service error: {type(error).__name__}")
            print(f"The AI service stopped the run ({type(error).__name__}).")
            done = {e["resume"] for e in entries}
            for r in resumes:
                if r["name"] not in done:
                    entries.append({"resume": r["name"], "final_score": None, "original_score": None,
                                    "score_source": None, "judgements": None, "revise_rounds": 0,
                                    "flags": ["Not scored: the AI service stopped the run"], "resolved": [],
                                    "notes": r["notes"], "needs_human_review": True})
            break

    ranked = loop.shortlist(entries)
    audit.log("shortlist", order=[(e["rank"], e["resume"], e["final_score"]) for e in ranked])

    calls = [u for s in audit.record["steps"] if s["step"] == "score" for u in s["usage"]]
    totals = {"ai_calls": len(calls), "tokens": sum(c["prompt_tokens"] + c["reply_tokens"] for c in calls),
              "seconds": round(sum(c["seconds"] for c in calls))}
    impact = loop.impact_report(ranked)
    audit.log("impact_report", **impact)
    demo = {"simulated": False, "created": datetime.now().isoformat(timespec="seconds"),
            "settings": loop.settings(), "job": job, "totals": totals, "shortlist": ranked, "impact": impact}
    (HERE / "data" / "demo_run.json").write_text(json.dumps(demo, indent=2, ensure_ascii=False), encoding="utf-8")
    (HERE / "data" / "demo_audit.json").write_text(json.dumps(audit.record, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nRank  Final  Original  Review  Resume")
    for e in ranked:
        review = "YES" if e["needs_human_review"] else ""
        print(f"{e['rank']:>4}  {e['final_score']!s:>5}  {e['original_score']!s:>8}  {review:>6}  {e['resume']}  {e['flags'] or ''}")
    print(f"\n{totals['ai_calls']} AI calls, {totals['tokens']} tokens, {totals['seconds']}s")
    print(f"Audit file: {audit.path}")


if __name__ == "__main__":
    main()
