import json
import os
from groq import AsyncGroq
from dotenv import load_dotenv
from functions.config import MODEL as model

load_dotenv()


async def get_diagnosis(keywords: list[str]) -> str:
    prompt = f"Patient has symptoms: {', '.join(keywords)}. Suggest possible medical diagnosis. Suggest me a possible cure for the same."
    try:
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        response = await client.chat.completions.create(messages=[{"role":"user", "content": prompt}], model=model)
        return response.choices[0].message.content #ollama gives output as dict
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
