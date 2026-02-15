import os
from groq import AsyncGroq
from dotenv import load_dotenv

load_dotenv()

model = "llama-3.3-70b-versatile"


async def summarize_text(text: str) -> str:
    prompt = f"Summarize the given medical text data. \n\n : {text}"
    try:
        client = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
        response = await client.chat.completions.create(messages=[{"role":"user", "content": prompt}], model=model)
        return response.choices[0].message.content #ollama gives output as dict
    except Exception as e:
        return f"Error getting diagnosis: {str(e)}"

