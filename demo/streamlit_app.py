"""
Clinisight — Streamlit demo
===========================
Runs the same pipeline as the FastAPI / MCP server, in-process:
symptom extraction -> possible conditions -> PubMed articles -> research summary.

Run locally (from the repo root):
    pip install -r demo/requirements.txt
    streamlit run demo/streamlit_app.py

Deploy on Streamlit Community Cloud:
    Main file path: demo/streamlit_app.py
    Settings -> Secrets:  GROQ_API_KEY = "gsk_..."   (optional: GROQ_MODEL = "...")

This folder has its own requirements.txt on purpose: Community Cloud reads the
dependency file next to the entrypoint first, so it skips the repo's uv.lock
(which pins torch/transformers the app never imports).
"""
import asyncio
import os
import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # lets `functions` import from the repo root

# Streamlit only hot-reloads modules inside demo/. When Community Cloud pulls a new commit,
# the old functions.* modules would stay cached and miss new code (e.g. "cannot import name
# 'symptoms_query'"), so drop them and let every run import the current version.
for _name in [m for m in sys.modules if m == "functions" or m.startswith("functions.")]:
    del sys.modules[_name]

# Copy the key from Streamlit secrets into the environment the functions read from.
# Only touch st.secrets when a secrets.toml exists; otherwise Streamlit shows its own
# "No secrets found" banner in the page.
if any(p.exists() for p in (Path.home() / ".streamlit" / "secrets.toml", ROOT / ".streamlit" / "secrets.toml")):
    try:
        for _key in ("GROQ_API_KEY", "GROQ_MODEL"):
            if _key in st.secrets and not os.getenv(_key):
                os.environ[_key] = st.secrets[_key]
    except Exception:
        pass

from functions.config import MODEL
from functions.symptom_extractor import extract_symptoms
from functions.diagnosis_symptoms import get_conditions, get_diagnosis
from functions.pubmed_articles import conditions_query, fetch_pubmed_articles_with_metadata, symptoms_query
from functions.summarize_pubmed import summarize_text

st.set_page_config(page_title="Clinisight — Symptom Analysis & Research Assistant", layout="wide")

EXAMPLES = {
    "Flu-like": "I've had a fever, a headache and a dry cough for three days.",
    "Stomach bug": "Since yesterday I have nausea, vomiting and diarrhoea, and I feel very tired.",
    "Allergy": "My nose keeps running, my eyes are itchy and I have a rash on my arms.",
}
LLM_ERROR = "Error getting diagnosis:"  # prefix the functions return when a Groq call fails


def _use_example(text: str) -> None:
    st.session_state.description = text


async def _diagnose(symptoms: list[str]):
    """Free-text diagnosis and the top 3 conditions (used for the PubMed search), requested in parallel."""
    return await asyncio.gather(get_diagnosis(symptoms), get_conditions(symptoms))


def _pubmed(query: str) -> list[dict]:
    """Real PubMed articles only (no mock fallback in the public demo)."""
    return [a for a in fetch_pubmed_articles_with_metadata(query, use_mock_if_empty=False) if "title" in a]


def _show_llm_text(text: str) -> None:
    if text.startswith(LLM_ERROR):
        st.error("The LLM request failed. " + text[len(LLM_ERROR):].strip())
    else:
        st.markdown(text)


st.session_state.setdefault("description", EXAMPLES["Flu-like"])
st.session_state.setdefault("result", None)
result = st.session_state.result

# ── Header ───────────────────────────────────────────────────────────────────
st.title("Clinisight — Symptom Analysis & Research Assistant")
st.caption(f"Plain-language symptoms → possible conditions → PubMed evidence → research summary · "
           f"Python, Groq ({MODEL}), PubMed E-utilities, MCP, Streamlit")

if not os.getenv("GROQ_API_KEY"):
    st.error("GROQ_API_KEY is not set. Add it under Settings → Secrets on Streamlit Cloud, or to a .env file locally.")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Pipeline stages", "4")
k2.metric("Symptoms found", len(result["symptoms"]) if result else "—")
k3.metric("PubMed articles", len(result["articles"]) if result else "—")
k4.metric("Analysis time", f"{result['seconds']:.1f} s" if result else "—")
k5.metric("Evidence source", "PubMed")

st.divider()

# ── Input + how it works ─────────────────────────────────────────────────────
left, right = st.columns([3, 2], gap="large")
with left:
    st.subheader("Describe the symptoms")
    for col, (label, text) in zip(st.columns(len(EXAMPLES)), EXAMPLES.items()):
        col.button(label, on_click=_use_example, args=(text,))
    st.text_area("Symptoms in plain language", key="description", height=120, label_visibility="collapsed")
    analyze = st.button("Analyze symptoms", type="primary")

with right:
    st.subheader("How it works")
    with st.container(border=True):
        st.markdown(
            "1. **Symptom extraction:** the LLM reads your description and returns the symptoms as JSON "
            "(keyword matching is the fallback).\n"
            "2. **Possible conditions:** the LLM suggests likely conditions for those symptoms and names "
            "the top 3.\n"
            "3. **PubMed evidence:** the most relevant papers on those conditions that mention your symptoms "
            "are fetched live from NCBI PubMed.\n"
            "4. **Research summary:** the LLM summarizes the retrieved abstracts."
        )
    st.caption("Educational demo only, not medical advice. Always consult a healthcare professional.")

# ── Run the pipeline ─────────────────────────────────────────────────────────
if analyze:
    text = st.session_state.description.strip()
    if not text:
        st.warning("Describe the symptoms first.")
    else:
        start = time.perf_counter()
        diagnosis = summary = query = None
        conditions, articles = [], []
        with st.status("Analyzing...", expanded=False) as status:
            status.update(label="Extracting symptoms...")
            symptoms = extract_symptoms(text)
            if symptoms:
                status.update(label="Finding possible conditions...")
                diagnosis, conditions = asyncio.run(_diagnose(symptoms))
                status.update(label="Searching PubMed...")
                # Papers on the likely conditions first; symptom-only searches are the fallback
                searches = ([conditions_query(conditions, symptoms)] if conditions else []) + [
                    symptoms_query(symptoms), " OR ".join(symptoms)]
                for query in searches:
                    articles = _pubmed(query)
                    if articles:
                        break
                if articles:
                    status.update(label="Summarizing the research...")
                    research = "\n\n".join(f"{a['title']}\n{a['abstract']}" for a in articles)[:3000]
                    summary = asyncio.run(summarize_text(research))
            status.update(label="Done", state="complete")
        st.session_state.result = {"symptoms": symptoms, "diagnosis": diagnosis, "conditions": conditions,
                                   "articles": articles, "query": query if articles else None,
                                   "summary": summary, "seconds": time.perf_counter() - start}
        st.rerun()  # refresh the KPI row with this run's numbers

# ── Results ──────────────────────────────────────────────────────────────────
if result:
    st.divider()
    if not result["symptoms"]:
        st.info("No symptoms detected. Try describing how you feel in a bit more detail.")
    else:
        res_left, res_right = st.columns(2, gap="large")
        with res_left:
            st.subheader("Symptoms detected")
            st.markdown(" ".join(f":blue-background[{s}]" for s in result["symptoms"]))
            st.subheader("Possible conditions")
            if result.get("conditions"):  # .get: results saved before this field existed
                st.markdown("Most likely: " + " ".join(f":orange-background[{c}]" for c in result["conditions"]))
            with st.container(border=True):
                _show_llm_text(result["diagnosis"])
        with res_right:
            st.subheader("PubMed evidence")
            if not result["articles"]:
                st.info("No PubMed articles found for these symptoms.")
            elif result.get("query"):
                st.caption(f"PubMed search: `{result['query']}`")
            for a in result["articles"]:
                with st.container(border=True):
                    st.markdown(f"**[{a['title']}]({a['article_url']})**")
                    st.caption(f"{', '.join(a['authors'][:3])} · {a['publication_date']}")
            if result["summary"]:
                st.subheader("Research summary")
                with st.container(border=True):
                    _show_llm_text(result["summary"])
