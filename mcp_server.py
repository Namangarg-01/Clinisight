from mcp.server.fastmcp import FastMCP
from functions.symptom_extractor import extract_symptoms
from functions.diagnosis_symptoms import get_diagnosis
from functions.pubmed_articles import fetch_pubmed_articles_with_metadata
from functions.summarize_pubmed import summarize_text


mcp = FastMCP()

@mcp.tool()
async def Clinisight_ai(symptom_text):
    symptoms = extract_symptoms(symptom_text)
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
    mcp.run(transport="stdio")