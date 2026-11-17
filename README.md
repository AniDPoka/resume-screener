# Resume screening loop with bias and fairness checks

An AI loop that scores resumes against a job description, **checks its own work** for made-up
evidence, inconsistency and bias, fixes what it can, and hands a ranked shortlist to a human
recruiter. **It never rejects anyone.** Every candidate stays on the list, and anything the loop
cannot settle is marked *needs human review*.

Built as an HR analytics portfolio project. All resumes are made up.

## Why this matters for HR

AI screening tools can give the same CV different scores on different days, or a different score
when only the name changes. A recruiter usually cannot see either. This project makes both visible
and testable, and keeps a full audit trail of every score.

## How it works

| Step | What happens | Who does it |
|---|---|---|
| 1. Read | The job description and resumes (.txt or .pdf) become plain text. Photos in PDFs are never read. | Code |
| 2. Score | For each requirement: *met*, *partly* or *not met*, with quotes from the resume. | AI |
| | The 0–100 score: must-haves share 70 points, nice-to-haves 30, *partly* = half. | Code |
| 3. Check | **Evidence:** every quote must appear word for word in the resume. | Code |
| | **Consistency:** the resume is scored 3 times; more than 5 points apart is flagged. | Code |
| | **Bias:** the same resume with a different name, the other gender, or a graduation year 20 years away. Flagged if a version scores more than 5 points outside the original's own range. | Code (versions made by fixed rules) |
| 4. Revise | Every resume is scored once more with name, contact details, he/she words and graduation year removed: that is the final score. Flagged resumes get up to 3 rounds, each telling the AI exactly which quote or requirement to fix. | AI + code |
| 5. Hand off | Everyone ranked by the anonymised score, with evidence, reasons, flags and a *needs human review* marker. | Code |

Every AI answer, score and check is written to a JSON audit file.

## Results from a real run (8 resumes, 71 AI calls)

| Rank | Candidate | Final score | What the loop handled |
|---|---|---|---|
| 1 | Priya Raman | 94 | nothing to fix |
| 2 | Daniel Okafor | 94 | nothing to fix |
| 3 | Margaret Ellis | 82 | nothing to fix |
| 4 | Sophie Clarke | 61.2 | inconsistent (64.2–73), settled in revise round 1 |
| 5 | Mohammed Hassan | 53 | the AI reworded a quote; caught by the evidence check, fixed in round 1 |
| 6 | Liam Murphy | 26.2 | nothing to fix |
| 7 | Tom Becker | 17.5 | inconsistent (0–26.2), settled in round 1 |
| 8 | Aisha Bello | 0 | inconsistent (0–8.8), settled in round 2 |

No name, gender or age version scored outside the original's own range.

## Design decisions

- **The AI judges, code does the maths.** The AI never writes the score, so every point can be
  traced to a requirement and a sentence in the resume.
- **Quotes are checked by code, not by the AI.** Only spacing, line breaks and curly quotes are
  ignored; every word must match.
- **The bias rule was changed after the first full run.** The brief's rule ("more than 5 points
  from the original") flagged 3 of 8 candidates. Each gap was exactly the size of the AI's own
  randomness on that resume. The rule now asks whether a version scored outside the range the
  original already got. `recheck_demo.py` replayed the 71 saved AI answers through the new rule
  without calling the AI: the scores were identical and only the false alarms went away.
- **Temperature 0** (as steady as possible), because that is how a real screening tool should be
  set. The run shows it is still not perfectly repeatable on borderline resumes.
- **A free AI service (Groq, `openai/gpt-oss-120b`).** All AI calls are in one file (`scorer.py`),
  so another provider can be swapped in. The public app opens on a saved run and limits live runs,
  so visitors cannot use up the free allowance.

## Try it

The live app has four tabs: the saved shortlist, one resume run live, a clearly labelled
**simulated** example of a resume that needs several revise rounds, and a plain-English explanation.

To run it on your own computer (Python 3.11+):

```bash
pip install -r requirements.txt
python tests.py                 # all checks; no AI key needed (it uses a stand-in AI)
streamlit run app.py
```

For live runs, get a free key at console.groq.com/keys and put it in `.streamlit/secrets.toml`:
`GROQ_API_KEY = "..."`. That file is never committed.

Other scripts: `try_one.py` (one resume, real AI), `run_all.py` (all resumes, saves the demo run),
`recheck_demo.py` (replays the saved answers through the current rules), `make_example.py`
(rebuilds the simulated example), `data/make_resumes.py` (rebuilds the sample resumes).

## Files

| File | What it does |
|---|---|
| `ingest.py` | Reads resumes and the job description; notes but never reads PDF images |
| `scorer.py` | The only file that talks to the AI |
| `checks.py` | Score formula, evidence, consistency and bias checks (no AI) |
| `variants.py` | Builds the name, gender, age and anonymised versions by fixed rules (no AI) |
| `loop.py` | Score → Check → Revise → Hand off |
| `audit.py` | The JSON audit file |
| `app.py` | The web page |
| `tests.py` | Plain checks with a stand-in AI, including the whole app run headless |

## Limits and law

- **Made-up data only.** This is a demonstration, not a hiring tool. A person makes every decision.
- Automated screening is regulated: **New York City Local Law 144** requires bias audits of
  automated employment decision tools, and the **EU AI Act** treats AI used in hiring as
  high-risk. A real deployment would need far more than this.
- A clean bias check on 8 resumes is not proof the AI is unbiased in general.
- Names and he/she words are found by fixed rules and a short name list; unusual layouts or names
  may slip through.
- After anonymising, phrases such as "recent graduate" still hint at age.
- The age version moves only the graduation year, so some versions look odd (e.g. graduated 1999,
  first job 2019); job dates are left alone because they are real qualifications.
- Text sent to the AI leaves the app (Groq states it does not keep API data by default).
  Never use real candidates' resumes with the public app.
