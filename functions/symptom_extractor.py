import re 

def extract_symptoms(text : str):
    symptoms = re.findall(f"\b(headache|fever|nausea|fatigue|pain)\b")