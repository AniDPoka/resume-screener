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

print("All checks passed.")
