"""Step 1 of the loop: reads the job description and the resumes into plain text.

No AI here. Only text is taken from a resume: if a PDF holds a picture (often a photo of the
candidate), the picture is never read, so it can never reach the AI. We only note that it was there.
"""

import logging
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

# pypdf prints its own warnings about damaged PDFs. We already turn those into a plain note.
logging.getLogger("pypdf").setLevel(logging.ERROR)

# Limits, so a huge or odd file cannot slow the app down or cause trouble.
ALLOWED_TYPES = (".txt", ".pdf")
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB is far more than any resume needs
MAX_PDF_PAGES = 10


def read_resume(data, file_name):
    """Turns one resume file (its bytes and its name) into a dict:
    name: the file name
    text: the resume as plain text ("" if none could be read)
    had_image: True if a PDF contained a picture (not read, not sent to the AI)
    notes: plain-English remarks for the audit file, e.g. why a file was refused
    """
    result = {"name": file_name, "text": "", "had_image": False, "notes": []}
    kind = Path(file_name).suffix.lower()

    if kind not in ALLOWED_TYPES:
        result["notes"].append(f"Refused: only {' and '.join(ALLOWED_TYPES)} files are accepted.")
        return result
    if len(data) > MAX_FILE_BYTES:
        result["notes"].append("Refused: the file is larger than 2 MB.")
        return result

    if kind == ".txt":
        # utf-8-sig also removes the invisible marker some editors put at the start of a file.
        result["text"] = data.decode("utf-8-sig", errors="replace")
    else:
        try:
            reader = PdfReader(BytesIO(data))
            if len(reader.pages) > MAX_PDF_PAGES:
                result["notes"].append(f"Refused: the PDF has more than {MAX_PDF_PAGES} pages.")
                return result
            result["text"] = "\n".join(page.extract_text() or "" for page in reader.pages)
            result["had_image"] = any(page_has_image(page) for page in reader.pages)
        except Exception:
            # A damaged or password-protected PDF: say so instead of crashing.
            result["notes"].append("Refused: the PDF could not be opened.")
            return result
        if result["had_image"]:
            result["notes"].append("This PDF contained an image. It was not read or sent to the AI.")

    result["text"] = result["text"].strip()
    if not result["text"]:
        result["notes"].append("No text found. It may be a scanned image; a person should read it.")
    return result


def page_has_image(page):
    """True if a PDF page contains a picture. We look at the page's list of resources and never
    open the picture itself."""
    resources = page.get("/Resources")
    if resources is None:
        return False
    objects = resources.get_object().get("/XObject")
    if objects is None:
        return False
    return any(obj.get_object().get("/Subtype") == "/Image" for obj in objects.get_object().values())


def read_folder(folder):
    """Reads every resume in a folder, in file-name order, so runs are always in the same order."""
    paths = sorted(p for p in Path(folder).iterdir() if p.is_file() and not p.name.startswith("."))
    return [read_resume(p.read_bytes(), p.name) for p in paths]


def read_job(path):
    """Reads the job description and pulls out its two requirement lists.
    Returns a dict: text (the whole description), must_have and nice_to_have (lists of strings)."""
    text = Path(path).read_text(encoding="utf-8-sig")
    return {"text": text, **requirements(text)}


def requirements(text):
    """Finds the bullet points under the "Must-have:" and "Nice-to-have:" headings.
    A bullet is a line starting with "-". A blank line or a new heading ends the list."""
    lists = {"must_have": [], "nice_to_have": []}
    current = None
    for line in text.splitlines():
        stripped = line.strip()
        heading = stripped.lower().rstrip(":")
        if heading == "must-have":
            current = "must_have"
        elif heading == "nice-to-have":
            current = "nice_to_have"
        elif current and stripped.startswith("-"):
            lists[current].append(stripped.lstrip("- ").strip())
        else:
            current = None  # anything that is not a bullet ends the list
    return lists
