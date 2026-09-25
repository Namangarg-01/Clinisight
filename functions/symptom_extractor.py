import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

model = "llama-3.3-70b-versatile"

# Keyword fallback, used only when the LLM call fails (e.g. no API key or network error)
COMMON_SYMPTOMS = (r"\b(headache|fever|nausea|vomiting|fatigue|pain|cough|sore throat|dizziness|rash|"
                   r"diarrh(?:o)?ea|chills|shortness of breath|runny nose|body ache|loss of appetite)\b")


def extract_symptoms(text: str) -> list[str]:
    # Ask the LLM for the symptoms as JSON, e.g. {"symptoms": ["fever", "dry cough"]}
    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Extract every medical symptom the patient describes. Reply with JSON only: "
                                              '{"symptoms": ["..."]}, using short lowercase phrases. '
                                              "Use an empty list if there are none."},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        symptoms = json.loads(response.choices[0].message.content).get("symptoms", [])
        return sorted({s.strip().lower() for s in symptoms if isinstance(s, str) and s.strip()})
    except Exception:
        return sorted(set(re.findall(COMMON_SYMPTOMS, text.lower())))
