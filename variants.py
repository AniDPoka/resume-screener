"""Builds the versions of a resume used by the bias check and the revise rounds. No AI here.

Bias versions (each changes ONE thing, by a fixed rule, so a change in score has a clear cause):
  1. name_version:   a name from a different background, same gender
  2. gender_version: he/she swapped, plus a first name of the other gender from the same background
  3. age_version:    the graduation year moved by 20 years (job dates are left alone)

anonymised: name, contact details, he/she and graduation years removed. Used in the revise rounds.

Each function returns {"text": the new resume, "changes": plain-English list of what was changed}.
The changes go into the audit file, so anyone can see exactly how a version differs.
"""

import re

# First names grouped by background, so a swap can stay within (or move between) backgrounds.
# The first name in each list is the one used as a replacement. Surnames are used by name_version.
# This is a short, fixed list on purpose: it is easy to read and to explain.
NAME_GROUPS = {
    "uk_majority": {"female": ["Emily", "Sophie", "Margaret"], "male": ["James", "Daniel", "Tom", "Liam"], "surname": "Walker"},
    "south_asian": {"female": ["Priya", "Anjali"], "male": ["Arjun", "Rahul"], "surname": "Sharma"},
    "west_african": {"female": ["Amara", "Aisha"], "male": ["Chidi", "Tunde"], "surname": "Okoye"},
    "arab": {"female": ["Fatima", "Layla"], "male": ["Mohammed", "Omar"], "surname": "Rahman"},
    "east_asian": {"female": ["Mei"], "male": ["Wei"], "surname": "Chen"},
}
MINORITY_GROUPS = ["south_asian", "west_african", "arab", "east_asian"]

# How much the age version moves a graduation year, and the year that counts as "recent".
AGE_SHIFT_YEARS = 20
RECENT_YEAR = 2005

# Lines that only hold personal details. The anonymised version drops them.
PERSONAL_LINES = ("Name:", "Email:", "Phone:", "Address:")

# "graduated 2019", "graduated in 2019", "completed 2018". \s+ also matches a PDF line break.
GRADUATION = re.compile(r"\b(graduated|completed)(\s+in)?\s+(\d{4})\b")

# he/she words, female <-> male. "her" is treated as "his" (the usual use in a resume).
TO_MALE = {"she": "he", "her": "his", "hers": "his", "herself": "himself"}
TO_FEMALE = {"he": "she", "his": "her", "him": "her", "himself": "herself"}
PRONOUN = re.compile(r"\b(she|he|her|his|him|hers|herself|himself)\b", re.IGNORECASE)


# ---------- reading who the resume is about ----------

def person(text):
    """Finds the name, background group and gender of the person in a resume.
    The name comes from the "Name:" line. Gender comes from he/she words in the text, or else
    from the first-name list. Background comes from the first-name list ("unknown" if not in it)."""
    match = re.search(r"^Name:\s*(.+)$", text, re.MULTILINE)
    full = match.group(1).strip() if match else ""
    first, _, last = full.partition(" ")

    words = [w.lower() for w in PRONOUN.findall(text)]
    female = sum(w in TO_MALE for w in words)
    male = sum(w in TO_FEMALE for w in words)
    group, listed_gender = "unknown", None
    for name, details in NAME_GROUPS.items():
        for g in ("female", "male"):
            if first in details[g]:
                group, listed_gender = name, g
    gender = "female" if female > male else "male" if male > female else listed_gender
    return {"full": full, "first": first, "last": last, "group": group, "gender": gender}


# ---------- small helpers ----------

def swap_name(text, old_first, old_last, new_first, new_last):
    """Replaces the first name and surname everywhere, including in the email address."""
    if old_last and new_last:
        text = re.sub(rf"\b{re.escape(old_last)}\b", new_last, text)
    text = re.sub(rf"\b{re.escape(old_first)}\b", new_first, text)
    old_email = f"{old_first}.{old_last}".lower()
    new_email = f"{new_first}.{new_last}".lower()
    return text.replace(old_email, new_email)


def keep_capital(original, replacement):
    """'She' -> 'He', 'she' -> 'he': the replacement starts with a capital if the original did."""
    return replacement[0].upper() + replacement[1:] if original[0].isupper() else replacement


# ---------- the three bias versions ----------

def name_version(text):
    """Version 1: same resume, a name from a different background, same gender.
    A UK-majority name becomes a minority-group name, and the other way round (as in classic CV
    studies). Which minority group is fixed by the letters of the name, so it never changes."""
    who = person(text)
    if not who["first"]:
        return {"text": text, "changes": ["No 'Name:' line found, so the name was not changed."]}
    gender = who["gender"] or "female"
    if who["group"] in ("uk_majority", "unknown"):
        new_group = MINORITY_GROUPS[sum(map(ord, who["full"])) % len(MINORITY_GROUPS)]
    else:
        new_group = "uk_majority"
    new_first = NAME_GROUPS[new_group][gender][0]
    new_last = NAME_GROUPS[new_group]["surname"]
    new_text = swap_name(text, who["first"], who["last"], new_first, new_last)
    return {"text": new_text, "changes": [f"Name: {who['full']} -> {new_first} {new_last}"]}


def gender_version(text):
    """Version 2: same resume, other gender. he/she words are swapped and the first name becomes
    one of the other gender from the same background. The surname stays."""
    who = person(text)
    if not who["gender"]:
        return {"text": text, "changes": ["No he/she words or known first name, so gender was not changed."]}
    swap = TO_MALE if who["gender"] == "female" else TO_FEMALE
    other = "male" if who["gender"] == "female" else "female"
    new_text = PRONOUN.sub(lambda m: keep_capital(m.group(0), swap.get(m.group(0).lower(), m.group(0))), text)
    changes = [f"he/she words: {who['gender']} -> {other}"]
    if who["first"]:
        group = who["group"] if who["group"] != "unknown" else "uk_majority"
        new_first = NAME_GROUPS[group][other][0]
        new_text = swap_name(new_text, who["first"], who["last"], new_first, who["last"])
        changes.append(f"First name: {who['first']} -> {new_first}")
    return {"text": new_text, "changes": changes}


def age_version(text):
    """Version 3: same resume, a different age signal. Each graduation year moves 20 years:
    earlier if it is recent, later if it is old. Job dates and years of experience stay the same,
    because those are real qualifications, not just age."""
    changes = []

    def shift(m):
        year = int(m.group(3))
        new_year = year - AGE_SHIFT_YEARS if year >= RECENT_YEAR else year + AGE_SHIFT_YEARS
        changes.append(f"Graduation year: {year} -> {new_year}")
        return m.group(0)[: -4] + str(new_year)

    new_text = GRADUATION.sub(shift, text)
    if not changes:
        changes.append("No graduation year found, so the age signal was not changed.")
    return {"text": new_text, "changes": changes}


# ---------- the anonymised version ----------

def anonymised(text):
    """The resume with personal details removed, for the revise rounds:
    - the Name, Email, Phone and Address lines are dropped
    - the person's name and he/she words become "the candidate"
    - graduation years are removed (they hint at age)
    Photos never get this far: they are not read from PDFs at all (see ingest.py)."""
    who = person(text)
    changes = []

    lines = text.splitlines()
    kept = [line for line in lines if not line.strip().startswith(PERSONAL_LINES)]
    if len(kept) < len(lines):
        changes.append("Removed the Name, Email, Phone and Address lines")
    text = "\n".join(kept)

    for name in (who["full"], who["first"], who["last"]):
        if name and re.search(rf"\b{re.escape(name)}\b", text):
            text = re.sub(rf"\b{re.escape(name)}\b", lambda m: candidate(m, text), text)
            changes.append("Replaced the name with 'the candidate'")

    def neutral(m):
        word = m.group(0).lower()
        if word in ("her", "his", "hers"):
            new = "the candidate's"
        elif word in ("herself", "himself"):
            new = "themselves"
        else:
            new = "the candidate"
        return keep_capital(m.group(0), new)

    if PRONOUN.search(text):
        text = PRONOUN.sub(neutral, text)
        changes.append("Replaced he/she words with 'the candidate'")

    # ", graduated 2019" disappears completely, leaving "BSc Business Management, University of Ashcombe".
    text, removed = re.subn(r",?\s*" + GRADUATION.pattern, "", text)
    if removed:
        changes.append("Removed graduation years")

    return {"text": text.strip(), "changes": list(dict.fromkeys(changes))}  # no repeated notes


def candidate(match, text):
    """'The candidate' at the start of a sentence or line, 'the candidate' in the middle."""
    before = text[: match.start()].rstrip(" ")
    starts_sentence = before == "" or before.endswith(("\n", ".", "!", "?"))
    return "The candidate" if starts_sentence else "the candidate"


def bias_versions(text):
    """The three bias versions of one resume, by name, ready for the bias check."""
    return {"name": name_version(text), "gender": gender_version(text), "age": age_version(text)}
