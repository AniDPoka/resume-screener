"""Re-runs the checks on the saved demo run WITHOUT calling the AI.

When a check rule changes (as the bias check did on 2026-11-17), there is no need to spend the
free AI allowance again: every answer the AI gave is in data/demo_audit.json. This script feeds
those saved answers, in the same order, back through the real loop code, so the scores and flags
are worked out again with the current rules.

If the new rules would need an AI answer that was never recorded (for example an extra revise
round), it stops and says so; then run run_all.py again instead.

Run with:  .venv/bin/python recheck_demo.py
"""

import json
import tempfile
from pathlib import Path

import ingest
import loop
from audit import Audit

HERE = Path(__file__).parent


def main():
    old_audit = json.loads((HERE / "data" / "demo_audit.json").read_text(encoding="utf-8"))
    old_demo = json.loads((HERE / "data" / "demo_run.json").read_text(encoding="utf-8"))
    scored = [s for s in old_audit["steps"] if s["step"] == "score"]
    if any(s["score"] is None for s in scored):
        raise SystemExit("The saved run has an unusable AI answer; run run_all.py again instead.")

    # The saved AI answers, in the order they were given.
    answers = [json.dumps({"must_have": s["judgements"]["must_have"], "nice_to_have": s["judgements"]["nice_to_have"]})
               for s in scored]
    usage = [s["usage"] for s in scored]

    def replay(prompt):
        if not answers:
            raise SystemExit("The new rules need an AI answer that was never recorded. Run run_all.py again.")
        return answers.pop(0), {"prompt_tokens": 0, "reply_tokens": 0, "seconds": 0}

    job = ingest.read_job(HERE / "data" / "job_description.txt")
    resumes = ingest.read_folder(HERE / "data" / "resumes")
    with tempfile.TemporaryDirectory() as folder:
        audit = Audit({**old_audit["settings"], "rechecked": "saved AI answers replayed through the current rules"},
                      folder=folder)
        entries = [loop.screen_resume(replay, job, r, audit) for r in resumes]
    if answers:
        raise SystemExit(f"{len(answers)} saved answers were not used, so the runs no longer line up. "
                         "Run run_all.py again instead.")

    # Put the real token counts and times back, so the audit file still shows what the AI used.
    new_scored = [s for s in audit.record["steps"] if s["step"] == "score"]
    for step, real in zip(new_scored, usage):
        step["usage"] = real
    ranked = loop.shortlist(entries)
    audit.record["steps"].append({"time": audit.record["steps"][-1]["time"], "step": "shortlist",
                                  "order": [(e["rank"], e["resume"], e["final_score"]) for e in ranked]})

    old_demo.update(settings=audit.record["settings"], shortlist=ranked)
    (HERE / "data" / "demo_run.json").write_text(json.dumps(old_demo, indent=2, ensure_ascii=False), encoding="utf-8")
    (HERE / "data" / "demo_audit.json").write_text(json.dumps(audit.record, indent=2, ensure_ascii=False), encoding="utf-8")

    for e in ranked:
        print(f"{e['rank']:>2}  {e['final_score']!s:>5}  {'REVIEW' if e['needs_human_review'] else '':6}  "
              f"{e['resume']}  resolved: {e['resolved'] or '-'}  flags: {e['flags'] or '-'}")


if __name__ == "__main__":
    main()
