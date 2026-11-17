"""Step 1 of the loop: reads the job description and the resumes into plain text.

No AI here. Only text is taken from a resume: if a PDF holds a picture (often a photo of the
candidate), the picture is never read, so it can never reach the AI. We only note that it was there.

Two defences against candidates who try to trick an AI screener:
- Hidden text in a PDF (white letters, tiny letters, or invisible text) is split off and never sent
  to the AI. A person can see it in the audit file.
- Text that gives orders to an AI ("ignore all previous instructions", "rate this candidate...")
  is flagged, whether hidden or visible, so a person looks at that resume.
"""

import logging
import re
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

# pypdf prints its own warnings about damaged PDFs. We already turn those into a plain note.
logging.getLogger("pypdf").setLevel(logging.ERROR)

# Limits, so a huge or odd file cannot slow the app down or cause trouble.
ALLOWED_TYPES = (".txt", ".pdf")
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB is far more than any resume needs
MAX_PDF_PAGES = 10
TINY_TEXT_POINTS = 4  # letters smaller than this are too small for a person to read

# Phrases that give orders to an AI rather than describe a person's experience.
INSTRUCTION_PATTERNS = [
    r"ignore (?:all |any )?(?:the )?(?:previous|prior|above|earlier|other) (?:instructions|rules|prompts)",
    r"disregard (?:all |any )?(?:the )?(?:previous|prior|above|earlier) \w+",
    r"(?:note|message|instructions?) (?:to|for) (?:the |any )?(?:ai|llm|language model|chatgpt|screening (?:system|tool)s?)",
    r"(?:rate|score|mark|rank) (?:this|the) (?:candidate|applicant|resume|cv)",
    r"you are (?:an? )?(?:ai|language model|assistant|screening)",
    r"system prompt",
]


def read_resume(data, file_name):
    """Turns one resume file (its bytes and its name) into a dict:
    name: the file name
    text: the resume as plain text ("" if none could be read)
    had_image: True if a PDF contained a picture (not read, not sent to the AI)
    notes: plain-English remarks for the audit file, e.g. why a file was refused
    hidden_text: text in a PDF that a person cannot see (never sent to the AI)
    instructions: phrases that give orders to an AI, found anywhere in the file
    """
    result = {"name": file_name, "text": "", "had_image": False, "notes": [], "hidden_text": "", "instructions": []}
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
            pages = [split_hidden_text(page) for page in reader.pages]
            result["text"] = "\n".join(visible for visible, _ in pages)
            result["hidden_text"] = " ".join(hidden for _, hidden in pages if hidden).strip()
            result["had_image"] = any(page_has_image(page) for page in reader.pages)
        except Exception:
            # A damaged or password-protected PDF: say so instead of crashing.
            result["notes"].append("Refused: the PDF could not be opened.")
            return result
        if result["had_image"]:
            result["notes"].append("This PDF contained an image. It was not read or sent to the AI.")

    if result["hidden_text"]:
        result["notes"].append("This PDF contained hidden text (white, tiny or invisible letters). "
                               "It was not sent to the AI.")
    result["instructions"] = find_instructions(result["text"] + "\n" + result["hidden_text"])
    if result["instructions"]:
        result["notes"].append("This resume contains text giving orders to an AI screener. A person should look at it.")

    result["text"] = result["text"].strip()
    if not result["text"]:
        result["notes"].append("No text found. It may be a scanned image; a person should read it.")
    return result


def split_hidden_text(page):
    """Reads one PDF page and returns (visible text, hidden text).
    Text counts as hidden if it is white, set to invisible, or smaller than TINY_TEXT_POINTS.
    pypdf tells us each colour or style change, then each piece of text, so we keep track."""
    state = {"white": False, "invisible": False}
    saved = []  # PDFs save and restore their drawing settings with q and Q
    visible, hidden = [], []

    def before(operator, args, cm, tm):
        try:
            if operator == b"q":
                saved.append(dict(state))
            elif operator == b"Q" and saved:
                state.update(saved.pop())
            elif operator == b"rg":   # fill colour as red, green, blue (1 = full)
                state["white"] = all(float(a) >= 0.95 for a in args)
            elif operator == b"g":    # fill colour as grey (1 = white)
                state["white"] = float(args[0]) >= 0.95
            elif operator == b"k":    # fill colour as CMYK (all 0 = white)
                state["white"] = all(float(a) <= 0.05 for a in args)
            elif operator == b"Tr":   # text style 3 = invisible
                state["invisible"] = int(args[0]) == 3
        except (TypeError, ValueError, IndexError):
            pass  # an odd value: leave the settings as they were

    def text(piece, cm, tm, font, size):
        scale = max(abs(tm[0]), abs(tm[3]) or 0) * max(abs(cm[0]), abs(cm[3]) or 0)
        tiny = piece.strip() and size * (scale or 1) < TINY_TEXT_POINTS
        (hidden if state["white"] or state["invisible"] or tiny else visible).append(piece)

    page.extract_text(visitor_operand_before=before, visitor_text=text)
    return "".join(visible), " ".join(" ".join(hidden).split())


def find_instructions(text):
    """Every phrase in the text that gives orders to an AI (see INSTRUCTION_PATTERNS)."""
    flat = " ".join(text.split())
    found = []
    for pattern in INSTRUCTION_PATTERNS:
        found += [m.group(0) for m in re.finditer(pattern, flat, re.IGNORECASE)]
    return found


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
    """Reads the job description and pulls out its two requirement lists and marking guide.
    Returns a dict: text, must_have and nice_to_have (lists of requirement names), and guide:
    {requirement: {"met": ..., "partly": ..., "keywords": [...]}} (empty if the file has none)."""
    text = Path(path).read_text(encoding="utf-8-sig")
    return {"text": text, **requirements(text)}


def requirements(text):
    """Finds the bullet points under the "Must-have:" and "Nice-to-have:" headings.
    A bullet is a line starting with "-". Indented lines under a bullet starting with "met:",
    "partly:" or "keywords:" are its marking guide. Anything else ends the list."""
    lists = {"must_have": [], "nice_to_have": [], "guide": {}}
    current, last = None, None
    for line in text.splitlines():
        stripped = line.strip()
        heading = stripped.lower().rstrip(":")
        label, _, rest = stripped.partition(":")
        if heading == "must-have":
            current = "must_have"
        elif heading == "nice-to-have":
            current = "nice_to_have"
        elif current and stripped.startswith("-"):
            last = stripped.lstrip("- ").strip()
            lists[current].append(last)
            lists["guide"][last] = {"met": "", "partly": "", "keywords": []}
        elif current and last and label.lower() in ("met", "partly", "keywords"):
            if label.lower() == "keywords":
                lists["guide"][last]["keywords"] = [k.strip() for k in rest.split(",") if k.strip()]
            else:
                lists["guide"][last][label.lower()] = rest.strip()
        else:
            current, last = None, None  # anything that is not a bullet or a guide line ends the list
    return lists
