"""How much to rely on one Clinisight result.

Six rule-based checks, each rated High / Medium / Low, look at how specific the input is, whether the model
answers consistently and how well the retrieved PubMed papers back the answer. The overall score is their
weighted average. The checks cannot tell whether an answer is medically correct; only a clinician can.
"""
import datetime
import re
import statistics

from functions.diagnosis_symptoms import REFUSAL

HIGH, MEDIUM, LOW = "High", "Medium", "Low"
POINTS = {HIGH: 1.0, MEDIUM: 0.5, LOW: 0.0}

# Each check: weight in the overall score, why it matters, and the (High, Medium, Low) rules shown in the app
CHECKS = {
    "Symptom detail": {
        "weight": 0.15, "why": "More symptoms narrow down the possible causes.",
        "rules": ("3 or more symptoms", "2 symptoms", "1 symptom")},
    "Model agreement": {
        "weight": 0.25, "why": "Two separate model answers naming the same conditions means the result is stable, "
                               "not a one-off guess.",
        "rules": ("All top conditions also in the written assessment", "2 of them", "1 or none")},
    "Evidence coverage": {
        "weight": 0.20, "why": "Shows whether the papers found are about the suggested conditions.",
        "rules": ("Papers on 2 or more of the conditions", "Papers on 1", "Papers on none")},
    "Evidence strength": {
        "weight": 0.15, "why": "Guidelines and systematic reviews outweigh single studies and case reports.",
        "rules": ("Mostly guidelines, systematic reviews, meta-analyses or randomized trials",
                  "Mostly reviews, textbook chapters or other studies", "Mostly case reports, letters or editorials")},
    "Evidence recency": {
        "weight": 0.10, "why": "Newer papers reflect current practice.",
        "rules": ("Median age 5 years or less", "6 to 10 years", "Over 10 years")},
    "Summary grounding": {
        "weight": 0.15, "why": "Statements not found in the abstracts come from the model's own knowledge and "
                               "can't be checked against the sources.",
        "rules": ("75% or more of statements backed", "50 to 74%", "Under 50%")},
}

# PubMed publication types -> (label, evidence level); the first match wins, so retractions come first
STUDY_TYPES = [
    ("retracted paper", LOW, {"Retracted Publication"}),
    ("guideline", HIGH, {"Practice Guideline", "Guideline", "Consensus Development Conference",
                         "Consensus Development Conference, NIH"}),
    ("meta-analysis", HIGH, {"Meta-Analysis"}),
    ("systematic review", HIGH, {"Systematic Review"}),
    ("randomized trial", HIGH, {"Randomized Controlled Trial"}),
    ("review", MEDIUM, {"Review"}),
    ("textbook chapter", MEDIUM, {"Study Guide"}),  # StatPearls
    ("case report", LOW, {"Case Reports"}),
    ("letter or editorial", LOW, {"Letter", "Editorial", "Comment", "News"}),
]

# Words that don't identify a condition on their own ("viral gastroenteritis" is about "gastroenteritis")
GENERIC = {"acute", "chronic", "common", "disease", "disorder", "infection", "infections", "syndrome", "type",
           "viral", "bacterial", "condition", "related", "induced", "primary", "secondary", "mild", "severe"}
STOPWORDS = set("""about above after all also among and any are based been before below between both but can
could did does during each few for from had has have how however include includes including into its may might
more most much must not only other our over own per same should some such than that the their them then there
these they this those through under upon use used using very via was were what when where which while who whom
why will with within without would you your just like well""".split())
LLM_ERROR = "Error getting diagnosis:"  # prefix the LLM functions return when a Groq call fails


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3]


def _stem(word: str) -> str:
    # Crude stemming that keeps most of the word: "allergic" -> "aller", "poisoning" -> "poison"
    return word[:max(5, len(word) - 3)]


def _names(text: str, condition: str, symptoms: list[str], every: bool) -> bool:
    """Whether the text names the condition: all (every=True) or any of its identifying words appear."""
    symptom_words = set(_words(" ".join(symptoms)))
    keys = [w for w in _words(condition) if w not in GENERIC and w not in symptom_words and not w.isdigit()]
    keys = keys or _words(condition)
    text_words = _words(text)
    found = [any(t.startswith(_stem(k)) for t in text_words) for k in keys]
    return bool(found) and (all(found) if every else any(found))


def _failed(text: str | None) -> bool:
    return not text or text.startswith(LLM_ERROR) or (len(text) < 300 and bool(REFUSAL.match(text)))


def _plural(n: int, word: str) -> str:
    irregular = {"meta-analysis": "meta-analyses", "letter or editorial": "letters or editorials"}
    return f"{n} {word}" if n == 1 else f"{n} {irregular.get(word, word + 's')}"


def _study_type(article: dict) -> tuple[str, str]:
    types = set(article.get("publication_types") or [])
    for label, level, names in STUDY_TYPES:
        if types & names:
            return label, level
    return "research article", MEDIUM


def _statements(summary: str) -> list[str]:
    """Summary sentences and bullets that make a claim (headings and fragments are skipped)."""
    out = []
    for line in summary.splitlines():
        for part in re.split(r"(?<=[.!?;])\s+(?=[A-Z])", line):
            text = part.strip(" *#>-•\t")
            is_heading = len(text.split()) <= 8 and not text.endswith((".", "!", "?", ";", ":"))
            if len([w for w in _words(text) if w not in STOPWORDS]) >= 4 and not is_heading:
                out.append(text)
    return out


def _check_symptoms(symptoms):
    n = len(symptoms)
    return _plural(n, "symptom"), HIGH if n >= 3 else MEDIUM if n == 2 else LOW


def _check_agreement(symptoms, conditions, diagnosis):
    if not conditions:
        return "No structured list of likely conditions was returned", LOW
    if _failed(diagnosis):
        return "No written assessment to compare with", LOW
    # Compare with the "Likely causes" part only; the care advice mentions unrelated words ("food", "cold")
    part = re.search(r"likely causes(.*?)(?:usual care|see a doctor|$)", diagnosis, re.IGNORECASE | re.DOTALL)
    named = [c for c in conditions if _names(part.group(1) if part else diagnosis, c, symptoms, every=False)]
    rating = HIGH if len(named) == len(conditions) else MEDIUM if len(named) >= 2 else LOW
    return f"{len(named)} of {len(conditions)} top conditions also appear in the written assessment", rating


def _check_coverage(symptoms, conditions, articles):
    if not conditions or not articles:
        return "No likely conditions or papers to compare", LOW
    covered = [c for c in conditions if any(_names(a["title"], c, symptoms, every=True) for a in articles)]
    missing = [c for c in conditions if c not in covered]
    text = f"Papers on {', '.join(covered)}" if covered else "No paper is about a likely condition"
    if covered and missing:
        text += f"; none on {', '.join(missing)}"
    return text, HIGH if len(covered) >= 2 else MEDIUM if covered else LOW


def _check_strength(articles):
    if not articles:
        return "No papers found", LOW
    kinds = [_study_type(a) for a in articles]
    labels = {}
    for label, _ in kinds:
        labels[label] = labels.get(label, 0) + 1
    score = statistics.mean(POINTS[level] for _, level in kinds)
    text = ", ".join(_plural(n, label) for label, n in labels.items())
    return text[0].upper() + text[1:], HIGH if score >= 0.75 else MEDIUM if score >= 0.4 else LOW


def _check_recency(articles):
    years = sorted(a["year"] for a in articles if a.get("year"))
    if not years:
        return "No papers found" if not articles else "Publication years unknown", LOW
    age = max(0, datetime.date.today().year - statistics.median_low(years))  # epub-ahead papers can be dated next year
    span = str(years[0]) if years[0] == years[-1] else f"{years[0]}–{years[-1]}"
    return f"Median {_plural(age, 'year')} old ({span})", HIGH if age <= 5 else MEDIUM if age <= 10 else LOW


def _check_grounding(summary, research):
    if _failed(summary) or not research:
        return "No research summary to check", LOW
    # A statement counts as backed when at least half of its content words (first 5 letters) are in the
    # abstracts it was written from. Calibrated on live runs: 79-84% of statements pass against their own
    # sources, 0-21% against unrelated abstracts.
    source = {w[:5] for w in _words(research)}
    statements = _statements(summary)
    if not statements:
        return "No research summary to check", LOW
    backed = 0
    for s in statements:
        words = [w for w in _words(s) if w not in STOPWORDS]
        backed += sum(w[:5] in source for w in words) / len(words) >= 0.5
    share = backed / len(statements)
    return (f"{backed} of {len(statements)} statements backed by the abstracts",
            HIGH if share >= 0.75 else MEDIUM if share >= 0.5 else LOW)


def assess(symptoms: list[str], conditions: list[str], diagnosis: str | None, articles: list[dict],
           summary: str | None, research: str) -> dict:
    """Rate one result. `research` is the text the summary was generated from."""
    results = {
        "Symptom detail": _check_symptoms(symptoms),
        "Model agreement": _check_agreement(symptoms, conditions, diagnosis),
        "Evidence coverage": _check_coverage(symptoms, conditions, articles),
        "Evidence strength": _check_strength(articles),
        "Evidence recency": _check_recency(articles),
        "Summary grounding": _check_grounding(summary, research),
    }
    score = round(100 * sum(CHECKS[name]["weight"] * POINTS[rating] for name, (_, rating) in results.items())
                  / sum(c["weight"] for c in CHECKS.values()))
    grade = "High" if score >= 75 else "Moderate" if score >= 50 else "Low"
    advice = {
        "High": "The answer is consistent and backed by relevant literature. It is still general information, "
                "not a diagnosis.",
        "Moderate": "The answer is only partly backed. Use it as background for a conversation with a clinician, "
                    "not as an answer.",
        "Low": "The answer is weakly backed. Treat it as a rough guess and rely on a clinician.",
    }[grade]
    checks = [{"check": name, "result": result, "rating": rating, "why": CHECKS[name]["why"]}
              for name, (result, rating) in results.items()]
    return {"score": score, "grade": grade, "advice": advice, "checks": checks}
