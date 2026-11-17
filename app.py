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
RUNS_PER_DAY = 5
VERSION_LABELS = {"name": "name", "gender": "gender", "age": "age", "gap": "career-break", "university": "university"}
EVIDENCE_WORDS = {"demonstrated": "shown in use", "claimed": "claimed only", "none": "no quote found"}  # about 15,000-35,000 tokens each; Groq's free tier allows 200,000 a day

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
        left, middle, right, ats = st.columns([2.2, 1, 1, 1])
        rank = f"#{entry['rank']}  " if "rank" in entry else ""
        left.markdown(f"**{rank}{safe(person_name(entry['resume']))}**")
        must = entry.get("must_haves")
        if must:
            left.caption(f"Must-haves fully met: {must['met']} of {must['of']}"
                         + ("" if must["all"] else " (still listed: nobody is removed)"))
        middle.metric("Final score", points(entry["final_score"]), help="From the anonymised resume (name, contact, gender and age signals removed)")
        right.metric("Original", points(entry["original_score"]), help="Middle of 3 scores of the resume as written")
        if entry.get("keyword"):
            ats.metric("Keyword ATS", points(entry["keyword"]["score"]),
                       help="What a simple keyword filter would score, for comparison only. It is not used for the ranking.")

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
        if entry.get("hidden_text"):
            with st.expander("Hidden text found in this file (not sent to the AI)"):
                st.text(entry["hidden_text"])  # plain text, exactly as found

        with st.expander("Evidence and how it was checked"):
            if entry["judgements"]:
                rows = []
                for part, label in (("must_have", "Must-have"), ("nice_to_have", "Nice-to-have")):
                    for item in entry["judgements"][part]:
                        verdict = item["verdict"]
                        if item.get("ai_verdict") and item["ai_verdict"] != verdict:
                            verdict += f" (AI said {item['ai_verdict']})"
                        rows.append({"Requirement": item["requirement"], "Type": label, "Verdict": verdict,
                                     "Evidence": EVIDENCE_WORDS.get(item.get("evidence"), "–"),
                                     "Quote from the resume": " | ".join(item["quotes"]) or "–",
                                     "Reason": item["reason"]})
                # st.table wraps long text and shows it as plain text (never as HTML).
                st.table(pd.DataFrame(rows).set_index("Requirement"))
                if any(i.get("evidence") for i in entry["judgements"]["must_have"]):
                    st.caption("A skill counts as met only if it is shown being used (Experience or Education). "
                               "If it is only claimed (Summary or Skills), code marks it partly, whatever the AI said.")
            if entry.get("keyword"):
                st.markdown("**What a keyword ATS would have done** (for comparison, not used for ranking):")
                st.table(pd.DataFrame([
                    {"Requirement": i["requirement"], "Keyword filter": i["verdict"],
                     "Looked for": ", ".join(i["keywords"]), "Found": ", ".join(i["keywords_found"]) or "–"}
                    for part in ("must_have", "nice_to_have") for i in entry["keyword"]["judgements"][part]
                ]).set_index("Requirement"))
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
        versions = {s["version"]: s["score"] for s in scores if s["version"] in VERSION_LABELS}
        low, high = bias.get("range", [None, None])
        parts = [f"{VERSION_LABELS[kind]} version {points(v)}" for kind, v in versions.items()]
        verdict = "outside" if bias["flagged"] else "all within 5 points of"
        lines.append(f"**Bias check:** {', '.join(parts)}; {verdict} the original's range ({points(low)}–{points(high)}).")
        for s in steps:
            if s["step"] == "version_made" and s["version"] != "anonymised":
                label = VERSION_LABELS.get(s["version"], s["version"])
                lines.append(f"  - {label} version changed: " + "; ".join(safe(c) for c in s["changes"]))
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


def show_impact(report):
    """The NYC-style impact ratios for the whole run, with the small-sample warning."""
    if not report:
        return
    with st.expander("Bias audit across all candidates (impact ratio)"):
        st.markdown("Each resume was also scored with a name from another background and with the other "
                    "gender. As in a New York City bias audit, a group's *scoring rate* is the share of its "
                    "scores above the middle score, and its *impact ratio* is that rate divided by the best "
                    "group's. Below 0.8 is the usual warning sign (the four-fifths rule).")
        for attribute, result in report.items():
            st.markdown(f"**By {safe(attribute)}**")
            st.table(pd.DataFrame([{"Group": g, "Scores": r["count"], "Average score": r["average"],
                                    "Scoring rate": r["rate"], "Impact ratio": r["ratio"]}
                                   for g, r in result["groups"].items()]).set_index("Group"))
            st.caption(safe(result["warning"]))


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
    show_impact(demo.get("impact"))
    for entry in demo["shortlist"]:
        show_candidate(entry, demo_audit["steps"], key=f"demo_{entry['resume']}")
    download_audit(demo_audit, "demo_audit.json", key="demo_audit")

with live_tab:
    st.subheader("Run one resume through the whole loop")
    st.caption("Uses the real AI: 9 calls, more if something is flagged. Takes 2–4 minutes.")
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

1. **Read.** Text only. A photo in a PDF is never read. Hidden text (white, tiny or invisible
   letters) is split off and never sent to the AI, and any text giving orders to an AI ("ignore all
   previous instructions...") sends the resume to a person.
2. **Score.** For each requirement the AI says *met*, *partly* or *not met* and quotes the resume,
   following a written marking guide (what counts as met, what counts as partly).
   Code then checks where each quote comes from: a skill shown in use (Experience, Education) can be
   *met*; a skill only claimed (Summary, Skills) is *partly*, whatever the AI said.
   Plain code turns that into 0–100: must-haves share 70 points, nice-to-haves 30; *partly* is half.
3. **Check** (plain code, no AI):
   - *Evidence*: every quote must appear word for word in the resume.
   - *Consistency*: the resume is scored 3 times; more than 5 points apart is flagged.
   - *Bias*: the same resume with a different name, the other gender, a graduation year 20 years
     away, a one-year career break for caring, or a non-UK university. Flagged if a version scores
     more than 5 points outside the original's own range.
4. **Revise.** Every resume is also scored with its name, contact details, he/she words and
   graduation year removed: that is the final score. Flagged resumes get up to 3 more rounds, and each
   round tells the AI exactly which quote or requirement to fix.
5. **Hand off.** Everyone is ranked; nobody is removed. Each candidate shows how many must-haves are
   fully met (like an ATS knockout question, but nobody is filtered out). Anything unsettled, any sign
   of bias, and any hidden instructions are marked *needs human review*.

**Compared with a keyword ATS.** Each candidate also shows what a simple keyword filter would score.
Keyword filters miss evidence written differently ("INDEX MATCH" is a lookup, "XLOOKUP" is not the
word "lookup") and reward words without substance (an intern can "match" *2 years of HR data*). It is
shown for comparison only.

**Bias audit across all candidates.** The Shortlist tab reports impact ratios, the measure used in
New York City bias audits: does one group's share of above-middle scores fall below 0.8 of the best
group's? With a handful of resumes this demonstrates the method; it is not a finding.

**Why the bias rule compares with a range.** Even at its steadiest setting the AI sometimes gives the
same resume different scores. The first full run flagged 3 of 8 candidates for "bias" by exactly that
amount. A version that scores what the original itself sometimes scores is not evidence of bias.

**Limits**
- Rules find names, he/she words, headings and universities from fixed lists; unusual layouts may slip through.
- Phrases such as "recent graduate" still hint at age after anonymising.
- A clean bias check on a few resumes is not proof the AI is unbiased in general.
- Screening tools are regulated (New York City Local Law 144; the EU AI Act treats hiring tools as
  high-risk). This is a demo on made-up data, not a hiring tool.
""")
