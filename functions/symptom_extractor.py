import re 

def extract_symptoms(text : str) -> list[str]:
    symptoms = re.findall(r"\b(headache|fever|nausea|fatigue|pain)\b", text.lower()) #Looking for these problems in the user text and get the list of the diseases
    return list(set(symptoms)) # Getting unique entry for symptoms
    #/b for word boundary, | or operator, (...) Capture group(returns matched words)
    # With r backslash is not trated as escape character


