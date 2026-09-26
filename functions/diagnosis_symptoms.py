import json
import os
import re
from groq import AsyncGroq
from dotenv import load_dotenv
from functions.config import MODEL as model

load_dotenv()

# Framed as general information: asked to diagnose a patient and suggest a cure, the model sometimes refuses outright
DIAGNOSIS_PROMPT = (
    "You are the medical information assistant of an educational app. Given a list of symptoms, explain which "
    "conditions commonly cause them and how those conditions are usually managed. This is general information, "
    "not a diagnosis of a real patient. Answer in Markdown, under 250 words, with three short sections:\n"
    "**Likely causes:** 3 to 5 conditions, most likely first, each with one line on why it fits.\n"
    "**Usual care:** the self-care and treatments commonly used for the most likely ones.\n"
    "**See a doctor if:** the key warning signs.\n"
    "End with one line saying this is not medical advice."
)
REFUSAL = re.compile(r"^\W*(i['’]?m sorry|i am sorry|sorry|i can(?:not|['’]?t))", re.IGNORECASE)


async def get_diagnosis(keywords: list[str]) -> str:
    try:
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        for _ in range(2):  # a short refusal ("I'm sorry, but I can't help with that.") gets one retry
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": DIAGNOSIS_PROMPT},
                          {"role": "user", "content": f"Symptoms: {', '.join(keywords)}"}],
            )
            text = response.choices[0].message.content or ""
            if not (len(text) < 300 and REFUSAL.match(text)):
                break
        return text
    except Exception as e:
        return f"Error getting diagnosis: {str(e)}"


async def get_conditions(keywords: list[str]) -> list[str]:
    # The 3 most likely conditions as short medical names, e.g. ["influenza", "COVID-19", "common cold"].
    # They drive the PubMed search, so the evidence is about the conditions, not just the symptom words.
    try:
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "List the 3 most likely medical conditions for the patient's symptoms, "
                                              "most likely first, using standard medical names as they would appear "
                                              'in a PubMed article title (e.g. "migraine", "iron deficiency anemia"). '
                                              'Reply with JSON only: {"conditions": ["..."]}'},
                {"role": "user", "content": f"Symptoms: {', '.join(keywords)}"},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        conditions = json.loads(response.choices[0].message.content).get("conditions", [])
        return [c.strip() for c in conditions if isinstance(c, str) and c.strip()][:3]
    except Exception:
        return []
