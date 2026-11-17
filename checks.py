"""Step 3 of the loop: the checks. No AI in this file, on purpose: the AI is checked by plain code.

Phase 1 has the evidence check. The bias and consistency checks are added in later phases.
"""

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
