"""The loop: Score -> Check (and, in Phase 4, Revise -> Hand off).

check_resume runs steps 2 and 3 for one resume:
  - score the original resume 3 times (consistency check)
  - score the name, gender and age versions once each (bias check)
  - check every quote against the text the AI was shown (evidence check)
Every AI answer, score and check result is written to the audit file.
"""

import checks
import scorer
import variants

CONSISTENCY_RUNS = 3


def score_once(call, job, text, audit, resume_name, version, run=None):
    """One AI judgement, turned into a score by code and checked for evidence. Logged in full.
    Returns {"score", "judgements", "evidence_problems"}, or {"score": None, "problem"} if the
    AI's reply could not be used twice in a row."""
    result = scorer.judge(call, job, text)
    usage = [a["usage"] for a in result["attempts"]]
    if result["judgements"] is None:
        audit.log("score", resume=resume_name, version=version, run=run, score=None,
                  problem=result["problem"], replies=[a["reply"] for a in result["attempts"]], usage=usage)
        return {"score": None, "problem": result["problem"]}

    points = checks.score(result["judgements"])
    problems = checks.evidence_problems(result["judgements"], text)
    audit.log("score", resume=resume_name, version=version, run=run, score=points,
              judgements=result["judgements"], evidence_problems=problems, usage=usage)
    return {"score": points, "judgements": result["judgements"], "evidence_problems": problems}


def check_resume(call, job, resume, audit, on_step=None):
    """Scores and checks one resume (a dict from ingest.read_resume). Returns a summary dict.
    on_step(text), if given, is told what is happening, so a page can show progress."""
    name, text = resume["name"], resume["text"]
    tell = on_step or (lambda message: None)
    audit.log("resume_read", resume=name, had_image=resume["had_image"], notes=resume["notes"])

    # Consistency: the same resume, scored 3 times.
    originals = []
    for run in range(1, CONSISTENCY_RUNS + 1):
        tell(f"{name}: scoring the original, run {run} of {CONSISTENCY_RUNS}")
        originals.append(score_once(call, job, text, audit, name, "original", run))
    scores = [r["score"] for r in originals if r["score"] is not None]
    if len(scores) < 2:
        audit.log("stopped", resume=name, reason="the AI's answers could not be used")
        return {"resume": name, "error": "The AI's answers could not be used. A person should review this resume."}
    consistency = checks.consistency_check(scores)
    audit.log("consistency_check", resume=name, **consistency)

    # Bias: each version changes one thing (name, gender or age).
    versions = variants.bias_versions(text)
    version_results = {}
    for kind, version in versions.items():
        tell(f"{name}: scoring the {kind} version")
        audit.log("version_made", resume=name, version=kind, changes=version["changes"])
        version_results[kind] = score_once(call, job, version["text"], audit, name, kind)
    version_scores = {k: r["score"] for k, r in version_results.items() if r["score"] is not None}
    bias = checks.bias_check(scores, version_scores)
    audit.log("bias_check", resume=name, **bias)

    # Evidence: every problem found in any of the answers above.
    evidence = sorted({p for r in list(originals) + list(version_results.values()) for p in r.get("evidence_problems", [])})
    audit.log("evidence_check", resume=name, problems=evidence)

    flags = []
    if consistency["flagged"]:
        flags.append(f"Inconsistent: scores ranged {min(scores)}-{max(scores)}")
    for kind in bias["flagged"]:
        flags.append(f"Possible {kind} bias: the {kind} version scored {bias['differences'][kind]:+} points")
    if len(version_scores) < len(versions):
        flags.append("Some versions could not be scored")
    if evidence:
        flags.append(f"{len(evidence)} evidence problem(s)")

    summary = {
        "resume": name,
        "score": bias["baseline"],  # the middle of the 3 original scores
        "scores": scores,
        "consistency": consistency,
        "bias": bias,
        "evidence_problems": evidence,
        "flags": flags,
        # The rationale shown to the recruiter: the run whose score is the middle one, if there is one.
        "judgements": next((r["judgements"] for r in originals if r["score"] == bias["baseline"]),
                           next(r["judgements"] for r in originals if r["score"] is not None)),
    }
    audit.log("resume_summary", **{k: v for k, v in summary.items() if k != "judgements"})
    return summary
