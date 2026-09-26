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
