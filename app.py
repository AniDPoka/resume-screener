"""The web page (Streamlit). Run with:  .venv/bin/streamlit run app.py

Four tabs:
  Shortlist             the saved real run (data/demo_run.json): opens instantly, no AI
  Try one live          one sample resume through the whole loop with the real AI (limited)
  How flags are handled the SIMULATED example (data/simulated_example.json), always labelled
  How it works          the loop, the rules and the limits, in plain words

Safety: everything from a resume or the AI is shown through safe() or in a table, never as HTML.
The key comes from Streamlit's Secrets and is never shown. No uploads: visitors use the samples.
"""

import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

import ingest
import loop
import scorer
from audit import Audit
from safety import DailyAllowance, safe

HERE = Path(__file__).parent
DATA = HERE / "data"
RUNS_PER_VISIT = 2
RUNS_PER_DAY = 5  # about 15,000-35,000 tokens each; Groq's free tier allows 200,000 a day

st.set_page_config(page_title="Resume Screening Loop", page_icon="🔎", layout="wide")
state = st.session_state


# ---------- loading our own files (shared, because they hold only made-up sample data) ----------

@st.cache_data
def load_json(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


@st.cache_data
def load_samples():
    return ingest.read_job(DATA / "job_description.txt"), ingest.read_folder(DATA / "resumes")


@st.cache_resource
def daily_allowance():
    """One counter for the whole app (numbers only, no visitor data)."""
    return DailyAllowance(RUNS_PER_DAY)


def groq_key():
    try:
        return st.secrets.get("GROQ_API_KEY")
    except Exception:  # no secrets file at all
        return None


# ---------- small helpers ----------

def person_name(file_name):
    """'01_priya_raman.txt' -> 'Priya Raman' (all sample names are made up)."""
    stem = Path(file_name).stem
    parts = stem.split("_")[1:] if stem.split("_")[0].isdigit() else stem.split("_")
    return " ".join(p.capitalize() for p in parts)


def points(value):
    return "–" if value is None else f"{value:g}"


def steps_for(steps, resume):
    return [s for s in steps if s.get("resume") == resume]


# ---------- showing one candidate ----------

def show_candidate(entry, steps, key):
    """One candidate: score, status line, and (opened on click) the evidence and how it was checked."""
    with st.container(border=True):
        left, middle, right = st.columns([3, 1, 1])
        rank = f"#{entry['rank']}  " if "rank" in entry else ""
        left.markdown(f"**{rank}{safe(person_name(entry['resume']))}**")
        middle.metric("Final score", points(entry["final_score"]), help="From the anonymised resume (name, contact, gender and age signals removed)")
        right.metric("Original score", points(entry["original_score"]), help="Middle of 3 scores of the resume as written")

        if entry["needs_human_review"]:
            st.warning("Needs human review: " + "; ".join(safe(f) for f in entry["flags"]))
        elif entry["resolved"]:
            rounds = entry["revise_rounds"]
            st.info(f"Settled in {rounds} revise round{'s' if rounds != 1 else ''}: "
                    + "; ".join(safe(f) for f in entry["resolved"]))
        else:
            st.success("No problems found.")
        for note in entry.get("notes", []):
            st.caption(safe(note))

        with st.expander("Evidence and how it was checked"):
            if entry["judgements"]:
                rows = []
                for part, label in (("must_have", "Must-have"), ("nice_to_have", "Nice-to-have")):
                    for item in entry["judgements"][part]:
                        rows.append({"Requirement": item["requirement"], "Type": label, "Verdict": item["verdict"],
                                     "Evidence from the resume": " | ".join(item["quotes"]) or "–",
                                     "Reason": item["reason"]})
                # st.table wraps long text and shows it as plain text (never as HTML).
                st.table(pd.DataFrame(rows).set_index("Requirement"))
            show_checks(steps_for(steps, entry["resume"]))


def show_checks(steps):
    """The checks for one candidate, from the audit steps."""
    scores = [s for s in steps if s["step"] == "score"]
    originals = [points(s["score"]) for s in scores if s["version"] == "original"]
    lines = []
    if originals:
        lines.append(f"**Consistency:** the resume was scored {len(originals)} times: {', '.join(originals)}.")
    bias = next((s for s in steps if s["step"] == "bias_check"), None)
    if bias:
        versions = {s["version"]: s["score"] for s in scores if s["version"] in ("name", "gender", "age")}
        low, high = bias.get("range", [None, None])
        parts = [f"{kind} version {points(v)}" for kind, v in versions.items()]
        verdict = "outside" if bias["flagged"] else "all within 5 points of"
        lines.append(f"**Bias check:** {', '.join(parts)}; {verdict} the original's range ({points(low)}–{points(high)}).")
        for s in steps:
            if s["step"] == "version_made" and s["version"] != "anonymised":
                lines.append(f"  - {s['version']} version changed: " + "; ".join(safe(c) for c in s["changes"]))
    evidence = next((s for s in steps if s["step"] == "evidence_check"), None)
    if evidence:
        lines.append("**Evidence check:** every quote was found in the resume." if not evidence["problems"] else
                     "**Evidence check:** " + "; ".join(safe(p) for p in evidence["problems"]))
    anon = next((s for s in scores if s["version"] == "anonymised" and s.get("run") is None), None)
    if anon:
        lines.append(f"**Anonymised score:** {points(anon['score'])}.")
    for r in (s for s in steps if s["step"] == "revise_round"):
        told = "; ".join(safe(f) for f in r["feedback"])
        outcome = "clean, so the loop stopped" if r["resolved"] else "still unsettled"
        lines.append(f"**Revise round {r['round']}:** the AI was told: {told} → scores "
                     f"{', '.join(points(x) for x in r['scores'])}, {outcome}.")
    st.markdown("\n\n".join(lines) if lines else "No checks were run.")


def download_audit(record, name, key):
    st.download_button("Download the audit file (every step and score)", json.dumps(record, indent=2, ensure_ascii=False),
                       file_name=name, mime="application/json", key=key)


# ---------- the page ----------

st.title("Resume screening loop with bias and fairness checks")
st.info("Demo on made-up resumes. It suggests a reading order for a recruiter; a person makes every "
        "decision. Nobody is rejected automatically.")

job, resumes = load_samples()
demo, demo_audit, example = load_json("demo_run.json"), load_json("demo_audit.json"), load_json("simulated_example.json")

shortlist_tab, live_tab, example_tab, how_tab = st.tabs(["Shortlist", "Try one live", "How flags are handled", "How it works"])

with shortlist_tab:
    st.subheader(f"{safe(job['text'].splitlines()[0].replace('Job title: ', ''))}: {len(demo['shortlist'])} candidates")
    st.caption(f"A real run with {demo['settings']['model']} on {demo['created'][:10]}: "
               f"{demo['totals']['ai_calls']} AI calls. Ranked by the anonymised score. Everyone is listed.")
    with st.expander("The job's requirements"):
        st.markdown("**Must-have:**\n" + "\n".join(f"- {safe(r)}" for r in job["must_have"]))
        st.markdown("**Nice-to-have:**\n" + "\n".join(f"- {safe(r)}" for r in job["nice_to_have"]))
    for entry in demo["shortlist"]:
        show_candidate(entry, demo_audit["steps"], key=f"demo_{entry['resume']}")
    download_audit(demo_audit, "demo_audit.json", key="demo_audit")

with live_tab:
    st.subheader("Run one resume through the whole loop")
    st.caption("Uses the real AI: 7 calls, more if something is flagged. Takes 1–3 minutes.")
    names = [r["name"] for r in resumes]
    chosen = st.selectbox("Sample resume", names, format_func=person_name)
    resume = resumes[names.index(chosen)]
    with st.expander("Read this resume"):
        st.text(resume["text"])  # plain text, exactly as the AI sees it

    key = groq_key()
    used = state.get("live_runs", 0)
    if not key:
        st.warning("Live runs are switched off here (no AI key). The Shortlist tab shows a real saved run.")
    elif used >= RUNS_PER_VISIT:
        st.warning(f"This visit has used its {RUNS_PER_VISIT} live runs. The Shortlist tab shows a full saved run.")
    elif st.button("Run the loop on this resume", type="primary"):
        if not daily_allowance().take():
            st.warning("Today's live runs are used up (they share a small free AI allowance). "
                       "The Shortlist tab shows a full saved run. Please try again tomorrow.")
        else:
            state["live_runs"] = used + 1
            with tempfile.TemporaryDirectory() as folder, st.status("Running the loop…", expanded=True) as status:
                # The audit file goes to a temporary folder: it is offered as a download, not kept.
                audit = Audit(loop.settings(), folder=folder)
                try:
                    call = scorer.groq_call(scorer.connect(key))
                    entry = loop.screen_resume(call, job, resume, audit, on_step=lambda m: status.write(safe(m)))
                    state["live"] = {"entry": entry, "record": audit.record}
                    status.update(label="Done", state="complete", expanded=False)
                except Exception as error:
                    audit.log("stopped", reason=f"AI service error: {type(error).__name__}")
                    state["live"] = {"error": type(error).__name__, "record": audit.record}
                    status.update(label="The AI service stopped the run", state="error")
            # Redraw the page now, so the run count (and the limit message, if reached) is up to date.
            # Kept outside the try/except above, because st.rerun works by raising a special signal.
            st.rerun()
    live = state.get("live")
    if live and "error" in live:
        st.error(f"The AI service stopped the run ({safe(live['error'])}), often because the free allowance "
                 "is busy. Nothing was saved. Try again later, or see the Shortlist tab.")
    elif live:
        show_candidate(live["entry"], live["record"]["steps"], key="live")
        download_audit(live["record"], "live_audit.json", key="live_audit")

with example_tab:
    st.error("**Simulated: not a real AI result.** The real loop code ran, but the AI was a scripted "
             "stand-in, so that every step can be seen.")
    st.markdown("In the saved real run, each problem was settled in one or two rounds. This example shows a "
                "harder case: the stand-in AI invents a quote and disagrees with itself. The evidence check "
                "catches the invented quote, revise round 1 is told exactly what to fix but is still unsettled, "
                "and round 2 is clean.")
    show_candidate(example["entry"], example["steps"], key="example")

with how_tab:
    st.markdown("""
**The loop, for every resume**

1. **Read.** Text only. A photo in a PDF is never read, so it never reaches the AI.
2. **Score.** For each requirement the AI says *met*, *partly* or *not met* and quotes the resume.
   Plain code turns that into 0–100: must-haves share 70 points, nice-to-haves 30; *partly* is half.
3. **Check** (plain code, no AI):
   - *Evidence*: every quote must appear word for word in the resume.
   - *Consistency*: the resume is scored 3 times; more than 5 points apart is flagged.
   - *Bias*: the same resume with a different name, the other gender, or a graduation year 20 years
     away. Flagged if a version scores more than 5 points outside the original's own range.
4. **Revise.** Every resume is also scored with its name, contact details, he/she words and
   graduation year removed: that is the final score. Flagged resumes get up to 3 more rounds, and each
   round tells the AI exactly which quote or requirement to fix.
5. **Hand off.** Everyone is ranked; nobody is removed. Anything unsettled, and any sign of bias, is
   marked *needs human review*.

**Why the bias rule compares with a range.** Even at its steadiest setting the AI sometimes gives the
same resume different scores. The first full run flagged 3 of 8 candidates for "bias" by exactly that
amount. A version that scores what the original itself sometimes scores is not evidence of bias.

**Limits**
- Rules find names and he/she words from a fixed list; unusual layouts may slip through.
- Phrases such as "recent graduate" still hint at age after anonymising.
- A clean bias check on 8 resumes is not proof the AI is unbiased in general.
- Screening tools are regulated (New York City Local Law 144; the EU AI Act treats hiring tools as
  high-risk). This is a demo on made-up data, not a hiring tool.
""")
