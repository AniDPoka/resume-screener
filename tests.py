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

print("All checks passed.")
