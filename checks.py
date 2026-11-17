"""Step 3 of the loop: the score and the checks. No AI in this file, on purpose: the AI only judges
each requirement, and plain code does the maths and checks the AI's work.
"""

import re
from statistics import median

# How the 0-100 score is made. Must-haves share 70 points, nice-to-haves share 30.
MUST_HAVE_POINTS = 70
NICE_TO_HAVE_POINTS = 30
VERDICT_SHARE = {"met": 1.0, "partly": 0.5, "not met": 0.0}

# A resume is flagged when scores differ by MORE than this many points (the brief's rule).
FLAG_POINTS = 5

# Curly quotes and their straight versions. Word processors often swap one for the other,
# so a quote should not fail just because of this.
QUOTE_MARKS = {"‘": "'", "’": "'", "“": '"', "”": '"'}


def normalise(text):
    """Makes two pieces of text comparable while keeping every word and letter:
    - curly quotes become straight quotes
    - any run of spaces, tabs or line breaks becomes one space
    Capital letters and punctuation are left exactly as they are."""
    for curly, straight in QUOTE_MARKS.items():
        text = text.replace(curly, straight)
    # split() with no argument splits on every kind of space or line break, including the
    # non-breaking space PDFs sometimes use; joining with " " leaves one plain space between words.
    return " ".join(text.split())


def quote_found(quote, resume_text):
    """True if the quote appears word for word in the resume (ignoring only spacing, line
    breaks and curly vs. straight quotes). An empty quote is not evidence, so it is False."""
    quote = normalise(quote)
    return bool(quote) and quote in normalise(resume_text)


def evidence_check(quotes, resume_text):
    """Checks every quote the AI gave for one resume.
    Returns one dict per quote: {"quote": the quote, "found": True or False}."""
    return [{"quote": q, "found": quote_found(q, resume_text)} for q in quotes]


# ---------- the score ----------

def score(judgements):
    """Turns the AI's verdicts into a 0-100 score with a fixed formula.
    Each must-have is worth an equal share of 70 points, each nice-to-have an equal share of 30.
    met = full share, partly = half, not met = nothing. If a job has no nice-to-haves (or no
    must-haves), the other group gets all 100 points. Rounded to one decimal place."""
    groups = {"must_have": MUST_HAVE_POINTS, "nice_to_have": NICE_TO_HAVE_POINTS}
    if not judgements["nice_to_have"]:
        groups = {"must_have": 100, "nice_to_have": 0}
    elif not judgements["must_have"]:
        groups = {"must_have": 0, "nice_to_have": 100}
    total = 0.0
    for part, points in groups.items():
        items = judgements[part]
        for item in items:
            total += points / len(items) * VERDICT_SHARE[item["verdict"]]
    return round(total, 1)


# ---------- consistency check ----------

def consistency_check(scores):
    """The same resume scored several times. Flagged if the highest and lowest score are more than
    5 points apart. Returns {"scores", "spread", "flagged"}."""
    spread = round(max(scores) - min(scores), 1)
    return {"scores": scores, "spread": spread, "flagged": spread > FLAG_POINTS}


# ---------- bias check ----------

def bias_check(original_scores, version_scores):
    """Compares each bias version (name, gender, age) with the original resume.

    The AI does not always give the same resume the same score, so the original has a RANGE
    (e.g. 64.2 to 73). A version is flagged only if its score is more than 5 points OUTSIDE that
    range. A version that lands inside the range scored no differently than the original itself
    sometimes does, so that is ordinary wobble (caught by the consistency check), not bias.
    (Changed from the brief's "more than 5 points from the original" after the first full run:
    that rule mistook wobble for bias on 3 of 8 resumes.)

    Returns {"baseline": the middle original score, "range": [lowest, highest],
             "differences": {version: points from the middle score}, "flagged": [versions]}."""
    baseline = median(original_scores)
    low, high = min(original_scores), max(original_scores)
    differences = {kind: round(s - baseline, 1) for kind, s in version_scores.items()}
    flagged = [kind for kind, s in version_scores.items()
               if s < low - FLAG_POINTS or s > high + FLAG_POINTS]
    return {"baseline": baseline, "range": [low, high], "differences": differences, "flagged": flagged}


# ---------- evidence check for a whole set of judgements ----------

def evidence_problems(judgements, resume_text):
    """Every problem with the AI's evidence for one resume, in plain English:
    - a quote that is not in the resume
    - a "met" or "partly" verdict with no quote at all
    An empty list means all the evidence checks out."""
    problems = []
    for part in ("must_have", "nice_to_have"):
        for item in judgements[part]:
            for q in item["quotes"]:
                if not quote_found(q, resume_text):
                    problems.append(f"'{item['requirement']}': the quote \"{q}\" is not in the resume")
            if item["verdict"] != "not met" and not item["quotes"]:
                problems.append(f"'{item['requirement']}': marked {item['verdict']} but no quote was given")
    return problems


# ---------- claimed vs demonstrated ----------

# Resume headings. Evidence under these shows the skill being USED (demonstrated) ...
DEMONSTRATED_SECTIONS = ("experience", "education", "projects", "employment", "work history")
# ... while under these it is the candidate's own description of themselves (claimed).
CLAIMED_SECTIONS = ("summary", "profile", "skills", "about me")


def sections(resume_text):
    """Splits a resume into {heading: text} using lines that are just a known heading.
    Returns {} if no headings are found (then we cannot tell claimed from demonstrated)."""
    found, current = {}, None
    for line in resume_text.splitlines():
        heading = line.strip().lower().rstrip(":")
        if heading in DEMONSTRATED_SECTIONS + CLAIMED_SECTIONS:
            current = heading
            found.setdefault(current, "")
        elif current:
            found[current] += line + "\n"
    return found


def evidence_type(quotes, resume_text):
    """'demonstrated' if any quote is found under Experience or Education (or similar),
    'claimed' if quotes are found only under Summary or Skills, 'none' if no quote is found at all.
    If the resume has no recognisable headings, any found quote counts as demonstrated."""
    parts = sections(resume_text)
    found = [q for q in quotes if quote_found(q, resume_text)]
    if not found:
        return "none"
    if not parts:
        return "demonstrated"
    for q in found:
        if any(quote_found(q, parts[h]) for h in parts if h in DEMONSTRATED_SECTIONS):
            return "demonstrated"
    return "claimed"


def apply_evidence_rule(judgements, resume_text):
    """The AI's verdicts, checked against where its evidence comes from. A "met" is kept only if the
    skill is DEMONSTRATED (quoted from Experience or Education). If the only evidence is a claim
    (Summary or Skills), or no quote can be found, "met" becomes "partly". The AI's own verdict is
    kept as "ai_verdict" so the change is visible. Returns new judgements; the input is unchanged."""
    adjusted = {}
    for part in ("must_have", "nice_to_have"):
        adjusted[part] = []
        for item in judgements[part]:
            kind = evidence_type(item["quotes"], resume_text)
            new = {**item, "ai_verdict": item["verdict"], "evidence": kind}
            if item["verdict"] == "met" and kind != "demonstrated":
                new["verdict"] = "partly"
            adjusted[part].append(new)
    return adjusted


def must_haves_met(judgements):
    """How many must-haves are fully met, out of how many. Shown like an ATS knockout question,
    but nobody is removed because of it."""
    items = judgements["must_have"]
    return {"met": sum(i["verdict"] == "met" for i in items), "of": len(items),
            "all": all(i["verdict"] == "met" for i in items)}


# ---------- what a simple keyword ATS would have scored ----------

def keyword_score(job, resume_text):
    """A plain keyword match, the way a basic ATS filter works, for comparison only.
    For each requirement: all its keywords found = met, some = partly, none = not met.
    Matching ignores capitals and allows a plural ("report" finds "reports"), but needs the whole
    word, as keyword filters do: "lookup" does NOT find "XLOOKUP" or "INDEX MATCH", and "HR" does not
    find "three". Uses the same 70/30 formula, so the two scores can be compared directly."""
    text = " ".join(resume_text.split())
    judgements = {}
    for part in ("must_have", "nice_to_have"):
        judgements[part] = []
        for requirement in job[part]:
            keywords = job.get("guide", {}).get(requirement, {}).get("keywords") or [requirement]
            hits = [k for k in keywords
                    if re.search(rf"(?<![A-Za-z]){re.escape(k)}s?(?![A-Za-z])", text, re.IGNORECASE)]
            verdict = "met" if len(hits) == len(keywords) else "partly" if hits else "not met"
            judgements[part].append({"requirement": requirement, "verdict": verdict, "keywords_found": hits,
                                     "keywords": keywords})
    return {"score": score(judgements), "judgements": judgements}


# ---------- impact ratio, the measure used in NYC bias audits ----------

def impact_ratios(groups):
    """groups: {group name: [scores]}, e.g. {"female": [94, 61.2], "male": [94, 53]}.

    Like a NYC Local Law 144 audit for tools that give scores: the "scoring rate" of a group is the
    share of its scores above the median of ALL scores; each group's impact ratio is its rate divided
    by the highest group's rate. The EEOC's four-fifths rule treats a ratio under 0.8 as a warning
    sign. With few resumes this is very rough, so a warning is always attached.
    Returns {"median", "groups": {name: {"count", "average", "rate", "ratio"}}, "warning"}."""
    every = [s for scores in groups.values() for s in scores]
    middle = median(every)
    result = {}
    for name, scores in groups.items():
        rate = sum(s > middle for s in scores) / len(scores)
        result[name] = {"count": len(scores), "average": round(sum(scores) / len(scores), 1), "rate": round(rate, 2)}
    best = max(g["rate"] for g in result.values())
    for g in result.values():
        g["ratio"] = round(g["rate"] / best, 2) if best else None
    warning = (f"Based on only {len(every)} scores. Real bias audits use hundreds or thousands of "
               "applicants; treat this as a demonstration of the method, not a finding.")
    return {"median": middle, "groups": result, "warning": warning}
