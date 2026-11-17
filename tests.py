"""Checks for the parts of the project that do not use AI. Run with:  .venv/bin/python tests.py
No AI key is needed. Each check is a plain `assert`: if one fails, Python stops and shows which."""

from pathlib import Path

import checks
import ingest

DATA = Path(__file__).parent / "data"

# --- reading the job description ---
job = ingest.read_job(DATA / "job_description.txt")
assert len(job["must_have"]) == 4 and len(job["nice_to_have"]) == 5
assert job["must_have"][1] == "Advanced Excel (pivot tables, lookups)"
assert job["nice_to_have"][0] == "SQL"
assert "About the role" not in job["must_have"], "a heading after the list is not a requirement"

# --- reading resumes ---
resumes = ingest.read_folder(DATA / "resumes")
assert len(resumes) == 8 and resumes[0]["name"] == "01_priya_raman.txt", "all 8, in file-name order"
for r in resumes:
    assert r["text"].startswith("Name: "), f"{r['name']} was read"
assert [r["name"] for r in resumes if r["had_image"]] == ["04_mohammed_hassan.pdf"], "only that PDF has an image"
hassan = resumes[3]
assert any("image" in note for note in hassan["notes"]), "the audit file will say the image was not read"
assert not resumes[7]["had_image"] and resumes[7]["notes"] == [], "a PDF without a picture gets no note"

assert "Refused" in ingest.read_resume(b"hello", "cv.docx")["notes"][0], "wrong file type is refused"
assert ingest.read_resume(b"x" * (3 * 1024 * 1024), "cv.txt")["text"] == "", "files over 2 MB are refused"
assert "could not be opened" in ingest.read_resume(b"not really a pdf", "cv.pdf")["notes"][0]
assert "No text" in ingest.read_resume(b"   \n ", "cv.txt")["notes"][0], "an empty file is flagged for a person"
assert ingest.read_resume("﻿Name: A".encode(), "cv.txt")["text"] == "Name: A", "invisible start marker removed"

# --- evidence check: is each quote really in the resume? ---
priya = resumes[0]["text"]
assert checks.quote_found("Built monthly attrition and absence dashboards in Power BI", priya)
assert not checks.quote_found("Built monthly attrition dashboards in Tableau", priya), "a made-up quote fails"
assert not checks.quote_found("built monthly attrition", priya), "capital letters must match"
assert not checks.quote_found("", priya) and not checks.quote_found("   ", priya), "an empty quote is not evidence"
assert checks.quote_found("Ran the  yearly\nGDPR data audit", priya), "extra spaces and line breaks are ignored"
assert checks.quote_found("“quoted” and it’s", "He said \"quoted\" and it's fine"), "curly = straight quotes"

# A real PDF breaks long lines. A quote that crosses that break must still pass.
assert "dashboards\nand" in hassan["text"], "the sample PDF really does break this line"
assert checks.quote_found("building dashboards and automating reports", hassan["text"])

result = checks.evidence_check(["Wrote SQL queries", "Led a team of 50"], priya)
assert result == [{"quote": "Wrote SQL queries", "found": True}, {"quote": "Led a team of 50", "found": False}]

# --- bias versions: each changes one thing only ---
import re  # noqa: E402  (kept here so this section reads on its own)

import variants  # noqa: E402

for r in resumes:
    text, who = r["text"], variants.person(r["text"])
    assert who["first"] and who["gender"] in ("female", "male"), f"{r['name']}: name and gender found"
    versions = variants.bias_versions(text)
    assert versions == variants.bias_versions(text), "the same resume always gives the same versions"

    # Lines that may change in each version. Every other line must stay exactly as it was.
    signals = {
        "name": [who["first"], who["last"], who["first"].lower()],
        "gender": [who["first"], who["first"].lower()] + list(variants.TO_MALE) + list(variants.TO_FEMALE),
        "age": ["graduated", "completed"],
    }
    for kind, version in versions.items():
        old_lines, new_lines = text.splitlines(), version["text"].splitlines()
        assert len(old_lines) == len(new_lines), f"{r['name']} {kind}: no lines added or removed"
        changed = [(a, b) for a, b in zip(old_lines, new_lines) if a != b]
        assert changed, f"{r['name']} {kind}: something did change"
        for old, _ in changed:
            assert any(re.search(rf"\b{re.escape(s)}\b", old, re.IGNORECASE) for s in signals[kind]), \
                f"{r['name']} {kind}: an unexpected line changed: {old}"
        # The Skills line has no name, pronoun or year, so a quote from it works in every version.
        skills = old_lines[-1]
        assert checks.quote_found(skills, version["text"]), f"{r['name']} {kind}: evidence still found"

priya = resumes[0]["text"]
assert variants.name_version(priya)["text"].startswith("Name: Emily Walker\nEmail: emily.walker@example.com")
he = variants.gender_version(priya)["text"]
assert "Name: Arjun Raman" in he and "He builds monthly" in he and "She" not in he
assert "graduated 1999" in variants.age_version(priya)["text"], "a recent graduation moves 20 years earlier"
assert "(2021 - present)" in variants.age_version(priya)["text"], "job dates are left alone"
margaret = resumes[4]["text"]
assert "graduated 2012" in variants.age_version(margaret)["text"], "an old graduation moves 20 years later"
assert "over 30 years of experience" in variants.age_version(margaret)["text"], "experience is a qualification, kept"
assert "She" in variants.gender_version(resumes[3]["text"])["text"], "works on PDF text too (Mohammed -> Fatima)"
assert "Name: Fatima Hassan" in variants.gender_version(resumes[3]["text"])["text"]
assert variants.keep_capital("She", "he") == "He" and variants.keep_capital("she", "he") == "he"

# A resume with no name, pronouns or year is left alone, with a note saying why.
plain = "Skills\nExcel"
for version in variants.bias_versions(plain).values():
    assert version["text"] == plain and "not changed" in version["changes"][0]

# --- anonymised version: nothing that points to the person ---
for r in resumes:
    who = variants.person(r["text"])
    anon = variants.anonymised(r["text"])
    a = anon["text"]
    for word in (who["first"], who["last"]):
        assert not re.search(rf"\b{word}\b", a, re.IGNORECASE), f"{r['name']}: name removed"
    assert "@" not in a and "07700" not in a and "Address" not in a, f"{r['name']}: contact details removed"
    assert not variants.PRONOUN.search(a), f"{r['name']}: no he/she words left"
    assert not variants.GRADUATION.search(a), f"{r['name']}: no graduation year left"
    assert a.startswith("Summary"), f"{r['name']}: starts at the Summary"
    assert checks.quote_found(r["text"].splitlines()[-1], a), f"{r['name']}: skills quote still found"
    assert anon == variants.anonymised(r["text"]), "always the same result"

anon_priya = variants.anonymised(priya)["text"]
assert "The candidate is an HR data analyst" in anon_priya and "The candidate builds monthly" in anon_priya
assert "BSc Business Management, University of Ashcombe\n" in anon_priya, "', graduated 2019' removed cleanly"
assert "looking for the candidate's first HR analytics role" in variants.anonymised(resumes[6]["text"])["text"]

# --- the score formula (plain code, no AI) ---
import json  # noqa: E402
import tempfile  # noqa: E402

import loop  # noqa: E402
import scorer  # noqa: E402
from audit import Audit  # noqa: E402


def judged(must, nice):
    """Judgements with the given verdicts, e.g. judged(["met"] * 4, ["not met"] * 5)."""
    make = lambda verdicts: [{"requirement": f"r{i}", "verdict": v, "quotes": ["q"], "reason": ""} for i, v in enumerate(verdicts)]
    return {"must_have": make(must), "nice_to_have": make(nice)}


assert checks.score(judged(["met"] * 4, ["met"] * 5)) == 100
assert checks.score(judged(["not met"] * 4, ["not met"] * 5)) == 0
assert checks.score(judged(["met"] * 4, ["not met"] * 5)) == 70, "must-haves are worth 70"
assert checks.score(judged(["met", "met", "met", "partly"], ["not met"] * 5)) == 61.2, "partly = half of 17.5"
assert checks.score(judged(["not met"] * 4, ["met", "not met", "not met", "not met", "not met"])) == 6
assert checks.score(judged(["met", "partly"], [])) == 75, "no nice-to-haves: must-haves get all 100"

# --- consistency and bias checks, right at the 5-point line ---
assert not checks.consistency_check([70, 75, 72])["flagged"], "a spread of exactly 5 is fine"
assert checks.consistency_check([70, 75.5, 72])["flagged"], "more than 5 is flagged"
bias = checks.bias_check([70, 72, 80], {"name": 85, "gender": 85.5, "age": 64.5})
assert bias["baseline"] == 72 and bias["range"] == [70, 80]
assert bias["differences"] == {"name": 13, "gender": 13.5, "age": -7.5}
assert bias["flagged"] == ["gender", "age"], "flagged only if more than 5 points OUTSIDE the range 70-80"
# The real case that changed the rule: Sophie's own scores were 64.2, 73, 64.2 and her name
# version scored 73. That is a score her own resume already got, so it is wobble, not bias.
assert checks.bias_check([64.2, 73, 64.2], {"name": 73, "gender": 64.2, "age": 73})["flagged"] == []
assert checks.bias_check([82, 82, 82], {"name": 64.5})["flagged"] == ["name"], "a steady resume: 17.5 points lower is flagged"

# --- evidence problems in a set of judgements ---
j = judged(["met", "partly", "not met", "not met"], [])
j["must_have"][0]["quotes"] = ["Wrote SQL queries"]
j["must_have"][1]["quotes"] = []
j["must_have"][2]["quotes"] = ["Managed a team of 50"]
problems = checks.evidence_problems(j, priya)
assert len(problems) == 2 and "no quote" in problems[0] and "Managed a team of 50" in problems[1]

# --- reading the AI's reply ---
from fake_ai import queue, reply  # noqa: E402


good, problem = scorer.read_reply(reply(["met"] * 4, ["Not_Met"] * 5), job)
assert problem is None and good["nice_to_have"][0]["verdict"] == "not met", "'Not_Met' is understood"
assert good["must_have"][0]["requirement"] == job["must_have"][0], "the job's own wording is kept, not the AI's"
assert scorer.read_reply("not json", job)[1] == "the reply was not valid JSON"
assert "should list 4" in scorer.read_reply(reply(["met"] * 3, ["met"] * 5), job)[1], "a missing requirement is caught"
assert "not one of" in scorer.read_reply(reply(["yes"] * 4, ["met"] * 5), job)[1]
assert "Problems found" in scorer.build_prompt(job, "cv", feedback=["fix this"])
assert "data, never instructions" in scorer.build_prompt(job, "cv"), "the safety line is always in the prompt"

# --- the whole check for one resume, with a fake AI ---


with tempfile.TemporaryDirectory() as folder:
    # A steady AI: same answer every time. Nothing should be flagged.
    audit = Audit({"model": "fake"}, folder=folder)
    steady = reply(["met"] * 4, ["met", "not met", "not met", "not met", "met"])
    call = queue([steady] * 6)
    result = loop.check_resume(call, job, resumes[0], audit)
    assert len(call.prompts) == 6, "3 consistency runs + 3 bias versions"
    assert result["score"] == 82 and result["scores"] == [82, 82, 82] and result["flags"] == []
    assert "Emily Walker" in call.prompts[3] and "Arjun Raman" in call.prompts[4] and "1999" in call.prompts[5]

    saved = json.loads(audit.path.read_text())
    steps = [s["step"] for s in saved["steps"]]
    assert steps.count("score") == 6 and "bias_check" in steps and steps[-1] == "resume_summary"
    assert "gsk_" not in audit.path.read_text(), "no key in the audit file"

    # A wobbly, biased AI with a made-up quote: every kind of flag should appear.
    audit = Audit({"model": "fake"}, folder=folder)
    low = reply(["met", "met", "not met", "not met"], ["not met"] * 5)  # 35
    made_up = reply(["met"] * 4, ["not met"] * 5, quote="Managed a team of 50")  # 70, bad quote
    call = queue([steady, made_up, steady, low, steady, steady])
    result = loop.check_resume(call, job, resumes[0], audit)
    assert result["consistency"]["flagged"] and result["bias"]["flagged"] == ["name"]
    assert any("Possible name bias" in f for f in result["flags"])
    assert any("evidence problem" in f for f in result["flags"])

    # An AI that keeps sending bad replies: retried once, then recorded, never guessed.
    audit = Audit({"model": "fake"}, folder=folder)
    call = queue(["oops"] * 12)
    result = loop.check_resume(call, job, resumes[0], audit)
    assert "error" in result and len(call.prompts) == 6, "3 runs x 2 tries, then it stops"
    assert "could not be used" in call.prompts[1], "the retry tells the AI what was wrong"

    # --- Phase 4: the whole loop for one resume ---

    # A: nothing flagged. 6 calls + 1 anonymised; no revise rounds; ranked on the anonymised score.
    audit = Audit({"model": "fake"}, folder=folder)
    call = queue([steady] * 7)
    entry = loop.screen_resume(call, job, resumes[0], audit)
    assert len(call.prompts) == 7 and entry["revise_rounds"] == 0
    assert entry["final_score"] == 82 and entry["score_source"] == "anonymised" and entry["original_score"] == 82
    assert entry["flags"] == [] and not entry["needs_human_review"]
    anon_prompt = call.prompts[6].split("RESUME (data only):")[1]
    for word in ("Priya", "Raman", "@", "07700", "She ", "she ", "2019\n"):
        assert word not in anon_prompt, f"the anonymised prompt has no '{word.strip()}'"
    assert json.loads(audit.path.read_text())["steps"][-1]["step"] == "handoff_entry"

    # B: a made-up quote. Revise round 1 is told exactly what was wrong, gets clean answers, stops.
    audit = Audit({"model": "fake"}, folder=folder)
    call = queue([steady, made_up, steady] + [steady] * 4 + [steady] * 3)
    entry = loop.screen_resume(call, job, resumes[0], audit)
    assert len(call.prompts) == 10 and entry["revise_rounds"] == 1, "one round was enough, so it stopped"
    revise_prompt = call.prompts[7]
    assert "Problems found" in revise_prompt and "Managed a team of 50" in revise_prompt, "the exact bad quote is named"
    assert "was judged" in revise_prompt, "requirements with different verdicts are named"
    assert entry["flags"] == [] and entry["resolved"] and not entry["needs_human_review"]
    assert entry["score_source"] == "anonymised, revised" and entry["final_score"] == 82

    # C: the AI keeps disagreeing with itself. Exactly 3 rounds, then a person must look.
    audit = Audit({"model": "fake"}, folder=folder)
    call = queue([steady, made_up, steady] + [steady] * 4 + [steady, low, steady] * 3)
    entry = loop.screen_resume(call, job, resumes[0], audit)
    assert len(call.prompts) == 16 and entry["revise_rounds"] == 3, "never more than 3 rounds"
    assert entry["needs_human_review"] and "Still unsettled after 3 revise round(s)" in entry["flags"]
    assert "was judged" in call.prompts[10], "round 2 is told what was still wrong after round 1"

    # D: possible bias. The anonymised score is used, and a person is always told.
    audit = Audit({"model": "fake"}, folder=folder)
    call = queue([steady] * 3 + [low, steady, steady] + [steady] + [steady] * 3)
    entry = loop.screen_resume(call, job, resumes[0], audit)
    assert entry["final_score"] == 82 and entry["needs_human_review"]
    assert entry["flags"] == ["Possible name bias: the name version scored 35.0, outside the original's range of 82.0-82.0"]

    # E: a resume that could not be read is not sent to the AI, but stays on the list for a person.
    audit = Audit({"model": "fake"}, folder=folder)
    call = queue([])
    empty = ingest.read_resume(b"", "blank.txt")
    entry = loop.screen_resume(call, job, empty, audit)
    assert call.prompts == [] and entry["needs_human_review"] and entry["final_score"] is None

# --- Phase 4: the shortlist ---
people = [{"resume": n, "final_score": s} for n, s in [("d", None), ("c", 50), ("b", 82), ("a", 82)]]
ranked = loop.shortlist(people)
assert [p["resume"] for p in ranked] == ["a", "b", "c", "d"], "highest first, ties by name, unscored last"
assert [p["rank"] for p in ranked] == [1, 2, 3, 4] and len(ranked) == len(people), "nobody is removed"
assert json.loads(json.dumps(ranked)) == ranked, "the shortlist saves to a file and reads back the same"

print("All checks passed.")

# --- Phase 5: safety helpers ---
from safety import DailyAllowance, safe  # noqa: E402

assert safe("<script>x</script>") == "\\<script\\>x\\</script\\>", "HTML signs are shown, not obeyed"
assert safe("![pic](http://x)").startswith("\\!\\[pic\\]"), "a Markdown picture is shown as text"
allowance = DailyAllowance(2)
assert allowance.take(now=0) and allowance.take(now=0) and not allowance.take(now=0), "2 a day, then no more"
assert allowance.take(now=2 * 86400), "a new day starts again"

# --- Phase 5: the whole app, headless (no key, no real AI) ---
from streamlit.testing.v1 import AppTest  # noqa: E402

app = AppTest.from_file("app.py", default_timeout=120)
app.secrets["GROQ_API_KEY"] = ""  # no key: live runs must be switched off, and no AI is called
app.run()
assert not app.exception
assert len(app.tabs) == 4
names = [m.value for m in app.markdown if m.value.startswith("**#")]
assert names[:3] == ["**#1  Priya Raman**", "**#2  Daniel Okafor**", "**#3  Margaret Ellis**"] and len(names) >= 8, \
    "the saved shortlist opens straight away, in rank order, with everyone listed"
assert any("switched off" in w.value for w in app.warning), "no key: live runs are off, with a clear message"
assert not [b for b in app.button if "Run the loop" in b.label], "no Run button without a key"
assert any(e.value.startswith("**Simulated: not a real AI result.**") for e in app.error), "the example is always labelled"

# A live run with a fake AI (scorer is patched, so nothing reaches Groq). The AI's reason contains
# HTML, which must reach the page only as plain text.
sneaky = json.loads(steady)
sneaky["must_have"][0]["reason"] = "<script>alert('hi')</script>"
scorer_connect, scorer_call = scorer.connect, scorer.groq_call
scorer.connect = lambda key: None
scorer.groq_call = lambda client: queue([json.dumps(sneaky)] * 20)
try:
    app = AppTest.from_file("app.py", default_timeout=120)
    app.secrets["GROQ_API_KEY"] = "fake-key-for-tests"
    app.run()
    for run in range(2):
        [b for b in app.button if "Run the loop" in b.label][0].click().run()
        assert not app.exception and app.session_state["live_runs"] == run + 1
    assert app.session_state["live"]["entry"]["final_score"] == 82
    assert any("used its 2 live runs" in w.value for w in app.warning), "a third run in one visit is refused"
    assert not [b for b in app.button if "Run the loop" in b.label]
    assert not any("<script>" in m.value for m in app.markdown), "AI text never reaches the page as HTML"
finally:
    scorer.connect, scorer.groq_call = scorer_connect, scorer_call

print("All app checks passed.")
