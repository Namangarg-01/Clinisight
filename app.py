from fastapi import FastAPI
from pydantic import BaseModel
from functions.symptom_extractor import extract_symptoms
from functions.diagnosis_symptoms import get_diagnosis
from functions.pubmed_articles import fetch_pubmed_articles_with_metadata
from functions.summarize_pubmed import summarize_text

app = FastAPI()

class SymptomInput(BaseModel):
    description: str

@app.get("/")
def run():
    return {"Success":"API Running"}

@app.post("/diagnosis")
async def Diagnosis(data:SymptomInput):
    symptoms = extract_symptoms(data.description)
    if not symptoms:
        return {
            "error" : "No symptoms detected",
            "symptoms": [],
            "diagnosis" : None,
            "pubmed_summary": None
        }
    
    Diagnosis_results = await get_diagnosis(symptoms)

    query = " ".join(symptoms)
    pubmeds_article = fetch_pubmed_articles_with_metadata(query) #getting list of dictionary
    summary = await summarize_text(pubmeds_article[:3000])

    return {
        "symptoms" : symptoms,
        "diagosis" : Diagnosis_results,
        "pubmed_summary" : summary
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port = 8080, reload=True)