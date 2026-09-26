import os

from dotenv import load_dotenv

load_dotenv()

# Groq model used by every LLM step. Override with the GROQ_MODEL env var / Streamlit secret.
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
