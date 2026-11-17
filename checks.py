"""Step 3 of the loop: the score and the checks. No AI in this file, on purpose: the AI only judges
each requirement, and plain code does the maths and checks the AI's work.
"""

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
    The original's score is the middle (median) of its repeat scores, so one odd run does not
    decide it. A version is flagged if its score is more than 5 points away.
    Returns {"baseline", "differences": {version: points}, "flagged": [versions]}."""
    baseline = median(original_scores)
    differences = {kind: round(s - baseline, 1) for kind, s in version_scores.items()}
    flagged = [kind for kind, d in differences.items() if abs(d) > FLAG_POINTS]
    return {"baseline": baseline, "differences": differences, "flagged": flagged}


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
