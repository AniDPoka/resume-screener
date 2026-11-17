"""The loop: Score -> Check -> Revise -> Hand off.

screen_resume runs the whole loop for one resume:
  1. check_resume: score the original 3 times (consistency check) and the name, gender and age
     versions once each (bias check); every quote is checked against the text the AI was shown.
  2. Score the anonymised version once. This is the final score the shortlist is ranked by.
  3. If anything was flagged: up to 3 revise rounds on the anonymised version, each telling the
     AI exactly which problems to fix. Still unsettled after round 3 -> "needs human review".
shortlist then ranks everyone. Nobody is removed or rejected: it is a reading order for a person.
Every AI answer, score and check result is written to the audit file.
"""

from statistics import median

import checks
import scorer
import variants

CONSISTENCY_RUNS = 3
MAX_REVISE_ROUNDS = 3


def score_once(call, job, text, audit, resume_name, version, run=None, feedback=None):
    """One AI judgement, turned into a score by code and checked for evidence. Logged in full.
    Returns {"score", "judgements", "evidence_problems"}, or {"score": None, "problem"} if the
    AI's reply could not be used twice in a row."""
    result = scorer.judge(call, job, text, feedback)
    usage = [a["usage"] for a in result["attempts"]]
    if result["judgements"] is None:
        audit.log("score", resume=resume_name, version=version, run=run, score=None,
                  problem=result["problem"], replies=[a["reply"] for a in result["attempts"]], usage=usage)
        return {"score": None, "problem": result["problem"]}

    points = checks.score(result["judgements"])
    problems = checks.evidence_problems(result["judgements"], text)
    audit.log("score", resume=resume_name, version=version, run=run, score=points, feedback=feedback,
              judgements=result["judgements"], evidence_problems=problems, usage=usage)
    return {"score": points, "judgements": result["judgements"], "evidence_problems": problems}


def disagreements(answers):
    """Requirements that got different verdicts in different answers, in plain English.
    answers: a list of judgements (all for the same job)."""
    notes = []
    for part in ("must_have", "nice_to_have"):
        for position, item in enumerate(answers[0][part]):
            verdicts = sorted({a[part][position]["verdict"] for a in answers})
            if len(verdicts) > 1:
                notes.append(f"'{item['requirement']}' was judged {' / '.join(verdicts)} in different answers. "
                             "Decide from the quotes alone.")
    return notes


def middle_answer(results, middle):
    """The judgements whose score is the middle one, so the reasons shown match the score shown."""
    usable = [r for r in results if r["score"] is not None]
    return next((r["judgements"] for r in usable if r["score"] == middle), usable[0]["judgements"])


# ---------- steps 2 and 3: score and check ----------

def check_resume(call, job, resume, audit, on_step=None):
    """Scores and checks one resume (a dict from ingest.read_resume). Returns a summary dict.
    on_step(text), if given, is told what is happening, so a page can show progress."""
    name, text = resume["name"], resume["text"]
    tell = on_step or (lambda message: None)

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
    every = originals + list(version_results.values())
    evidence = sorted({p for r in every for p in r.get("evidence_problems", [])})
    audit.log("evidence_check", resume=name, problems=evidence)

    flags = []
    if consistency["flagged"]:
        flags.append(f"Inconsistent: scores ranged {min(scores)}-{max(scores)}")
    for kind in bias["flagged"]:
        low, high = bias["range"]
        flags.append(f"Possible {kind} bias: the {kind} version scored {version_scores[kind]}, "
                     f"outside the original's range of {low}-{high}")
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
        "disagreements": disagreements([r["judgements"] for r in every if r["score"] is not None]),
        "flags": flags,
        "judgements": middle_answer(originals, bias["baseline"]),
    }
    audit.log("resume_summary", **{k: v for k, v in summary.items() if k != "judgements"})
    return summary


# ---------- step 4: revise ----------

def revise(call, job, resume_name, anon_text, feedback, audit, tell):
    """Up to 3 rounds on the anonymised resume. Each round scores it 3 times with the feedback,
    then checks consistency and evidence again. Stops as soon as a round is clean.
    Returns {"rounds", "resolved", "score", "judgements", "remaining"}."""
    last = {"rounds": 0, "resolved": False, "score": None, "judgements": None, "remaining": feedback}
    for round_number in range(1, MAX_REVISE_ROUNDS + 1):
        results = []
        for run in range(1, CONSISTENCY_RUNS + 1):
            tell(f"{resume_name}: revise round {round_number}, run {run} of {CONSISTENCY_RUNS}")
            results.append(score_once(call, job, anon_text, audit, resume_name, "anonymised",
                                      run=f"revise {round_number}.{run}", feedback=feedback))
        usable = [r for r in results if r["score"] is not None]
        if len(usable) < 2:
            remaining = ["The AI's answers could not be used"]
        else:
            consistency = checks.consistency_check([r["score"] for r in usable])
            evidence = sorted({p for r in usable for p in r["evidence_problems"]})
            remaining = evidence + (disagreements([r["judgements"] for r in usable]) if consistency["flagged"] else [])
            last.update(score=median([r["score"] for r in usable]))
            last.update(judgements=middle_answer(usable, last["score"]))
        last.update(rounds=round_number, resolved=not remaining, remaining=remaining)
        audit.log("revise_round", resume=resume_name, round=round_number, feedback=feedback,
                  scores=[r["score"] for r in results], resolved=last["resolved"], remaining=remaining)
        if last["resolved"]:
            break
        feedback = remaining  # the next round is told exactly what is still wrong
    return last


# ---------- the whole loop for one resume ----------

def screen_resume(call, job, resume, audit, on_step=None):
    """Runs the full loop for one resume and returns its entry for the shortlist."""
    name = resume["name"]
    tell = on_step or (lambda message: None)
    audit.log("resume_read", resume=name, had_image=resume["had_image"], notes=resume["notes"])
    entry = {"resume": name, "final_score": None, "original_score": None, "score_source": None,
             "judgements": None, "flags": [], "resolved": [], "revise_rounds": 0,
             "notes": list(resume["notes"]), "needs_human_review": False}

    if not resume["text"]:
        entry["flags"].append("Could not be read, so it was not scored")
        entry["needs_human_review"] = True
        audit.log("handoff_entry", **entry)
        return entry

    summary = check_resume(call, job, resume, audit, on_step)
    if "error" in summary:
        entry["flags"].append(summary["error"])
        entry["needs_human_review"] = True
        audit.log("handoff_entry", **entry)
        return entry
    entry.update(original_score=summary["score"], judgements=summary["judgements"], score_source="original")

    # The anonymised version, scored once for every resume: this is the score the shortlist uses.
    anon = variants.anonymised(resume["text"])
    audit.log("version_made", resume=name, version="anonymised", changes=anon["changes"])
    tell(f"{name}: scoring the anonymised version")
    anon_result = score_once(call, job, anon["text"], audit, name, "anonymised")
    flags = list(summary["flags"])
    if anon_result["score"] is not None:
        entry.update(final_score=anon_result["score"], judgements=anon_result["judgements"], score_source="anonymised")
        if anon_result["evidence_problems"]:
            flags.append(f"{len(anon_result['evidence_problems'])} evidence problem(s) in the anonymised answer")
    else:
        entry["final_score"] = summary["score"]
        flags.append("The anonymised version could not be scored, so the original score is used")

    if flags:
        # Tell the AI exactly what went wrong, then let it try again on the anonymised resume.
        feedback = sorted(set(summary["evidence_problems"] + anon_result.get("evidence_problems", []))) + summary["disagreements"]
        feedback = feedback or ["Judge each requirement carefully from the quotes alone."]
        result = revise(call, job, name, anon["text"], feedback, audit, tell)
        entry["revise_rounds"] = result["rounds"]
        if result["score"] is not None:
            entry.update(final_score=result["score"], judgements=result["judgements"], score_source="anonymised, revised")
        bias_flags = [f for f in flags if f.startswith("Possible")]
        if result["resolved"]:
            entry["resolved"] = [f for f in flags if f not in bias_flags]
            entry["flags"] = bias_flags
        else:
            entry["flags"] = flags + [f"Still unsettled after {result['rounds']} revise round(s)"]
        # Bias found in the original scoring always goes to a person, even though the final
        # score comes from the anonymised version.
        entry["needs_human_review"] = bool(entry["flags"])

    audit.log("handoff_entry", **{k: v for k, v in entry.items() if k != "judgements"})
    return entry


# ---------- step 5: hand off ----------

def shortlist(entries):
    """Ranks everyone by final score, highest first. Resumes without a score go last.
    Nobody is removed: this is a suggested reading order for a person, not a decision."""
    ordered = sorted(entries, key=lambda e: (e["final_score"] is None, -(e["final_score"] or 0), e["resume"]))
    return [{"rank": i, **e} for i, e in enumerate(ordered, 1)]


def settings():
    """What a run used, for the top of the audit file. Never includes the key."""
    return {"model": scorer.MODEL, "temperature": scorer.TEMPERATURE,
            "consistency_runs": CONSISTENCY_RUNS, "max_revise_rounds": MAX_REVISE_ROUNDS,
            "flag_points": checks.FLAG_POINTS,
            "points": {"must_have": checks.MUST_HAVE_POINTS, "nice_to_have": checks.NICE_TO_HAVE_POINTS}}
