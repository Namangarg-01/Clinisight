"""
Clinisight — Streamlit demo
===========================
Runs the same pipeline as the FastAPI / MCP server, in-process:
symptom extraction -> possible diagnoses -> PubMed articles -> research summary.

Run locally (from the repo root):
    pip install -r demo/requirements.txt
    streamlit run demo/streamlit_app.py

Deploy on Streamlit Community Cloud:
    Main file path: demo/streamlit_app.py
    Settings -> Secrets:  GROQ_API_KEY = "gsk_..."

This folder has its own requirements.txt on purpose: Community Cloud reads the
dependency file next to the entrypoint first, so it skips the repo's uv.lock
(which pins torch/transformers the app never imports).
"""
import asyncio
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # lets `functions` import from the repo root

# Copy the key from Streamlit secrets into the environment the functions read from.
# Only touch st.secrets when a secrets.toml exists; otherwise Streamlit shows its own
# "No secrets found" banner in the page.
if any(p.exists() for p in (Path.home() / ".streamlit" / "secrets.toml", ROOT / ".streamlit" / "secrets.toml")):
    try:
        if "GROQ_API_KEY" in st.secrets and not os.getenv("GROQ_API_KEY"):
            os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
    except Exception:
        pass

from functions.symptom_extractor import extract_symptoms
from functions.diagnosis_symptoms import get_diagnosis
from functions.pubmed_articles import fetch_pubmed_articles_with_metadata
from functions.summarize_pubmed import summarize_text

st.set_page_config(page_title="Clinisight — Medical Diagnosis Demo", page_icon="🩺")

st.title("🩺 Clinisight")
st.caption("Describe symptoms in plain language → symptom extraction → possible conditions → "
           "PubMed evidence → research summary")
st.warning("Educational demo only — not medical advice. Always consult a healthcare professional.")

if not os.getenv("GROQ_API_KEY"):
    st.error("GROQ_API_KEY is not set. Add it under Settings → Secrets on Streamlit Cloud, or to a .env file locally.")

description = st.text_area("Describe your symptoms",
                           value="I've had a fever, a headache and a dry cough for three days.", height=110)

if st.button("Analyze", type="primary"):
    if not description.strip():
        st.error("Describe your symptoms first.")
        st.stop()

    with st.spinner("Extracting symptoms..."):
        symptoms = extract_symptoms(description)
    if not symptoms:
        st.info("No symptoms detected. Try describing how you feel in a bit more detail.")
        st.stop()
    st.subheader("1. Symptoms detected")
    st.write(", ".join(symptoms))

    with st.spinner("Generating possible diagnoses..."):
        diagnosis = asyncio.run(get_diagnosis(symptoms))
    st.subheader("2. Possible conditions")
    st.markdown(diagnosis)

    with st.spinner("Searching PubMed..."):
        # No mock fallback in the public demo — show real articles or say none were found
        articles = [a for a in fetch_pubmed_articles_with_metadata(" ".join(symptoms), use_mock_if_empty=False)
                    if "title" in a]
    st.subheader("3. PubMed articles")
    if not articles:
        st.info("No PubMed articles found for these symptoms.")
    else:
        for a in articles:
            st.markdown(f"**[{a['title']}]({a['article_url']})**  \n"
                        f"{', '.join(a['authors'][:3])} · {a['publication_date']}")
        with st.spinner("Summarizing the research..."):
            research = "\n\n".join(f"{a['title']}\n{a['abstract']}" for a in articles)[:3000]
            summary = asyncio.run(summarize_text(research))
        st.subheader("4. Research summary")
        st.markdown(summary)
