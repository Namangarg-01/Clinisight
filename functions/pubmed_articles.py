import calendar
import re

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# NCBI allows 3 requests/s without an API key and sometimes answers 429 or 5xx, so retry those with a backoff
# (read timeouts are not retried, so a hanging NCBI doesn't multiply the wait)
session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=3, read=0, backoff_factor=1,
                                                        status_forcelist=[429, 500, 502, 503, 504])))


def symptoms_query(symptoms: list[str]) -> str:
    # Every symptom must appear in the title or abstract, e.g. "fever"[tiab] AND "cough"[tiab]
    return " AND ".join(f'"{s}"[tiab]' for s in symptoms)


def conditions_query(conditions: list[str], symptoms: list[str]) -> str:
    # Papers about a likely condition that mention any of the symptoms and have an abstract, e.g.
    # ("influenza"[ti] OR "COVID-19"[ti]) AND ("fever"[tiab] OR "dry cough"[tiab]) AND hasabstract
    # Searching symptoms alone mostly finds drug trials that list them as side effects.
    names = [re.sub(r"\(.*?\)|[\"\[\]]", "", c).strip() for c in conditions]  # keep each name a valid phrase
    title = " OR ".join(f'"{c}"[ti]' for c in names if c)
    mention = " OR ".join(f'"{s}"[tiab]' for s in symptoms)
    return f"({title}) AND ({mention}) AND hasabstract"


def fetch_pubmed_articles_with_metadata(query: str, max_results=3, use_mock_if_empty=True):
    headers = {"User-Agent": "Mozilla/5.0"} #Tp authenticate with the URL Header is needed 

    # Step 1: Search PubMed
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    search_params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance"
    }
    try:
        search_response = session.get(search_url, params=search_params, headers=headers, timeout=10).json()
        id_list = search_response["esearchresult"]["idlist"]
        print("Found PubMed IDs:", id_list)
        if not id_list:
            raise ValueError("No IDs found for this query.")

        ids = ",".join(id_list)

        # Step 2: Fetch article summaries
        fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        fetch_params = {
            "db": "pubmed",
            "id": ids,
            "retmode": "xml"
        }
        fetch_response = session.get(fetch_url, params=fetch_params, headers=headers, timeout=10)
        soup = BeautifulSoup(fetch_response.text, "lxml")
        # Book records (e.g. StatPearls chapters) come back as <PubmedBookArticle>, not <PubmedArticle>
        articles_xml = soup.find_all(["pubmedarticle", "pubmedbookarticle"])
        print("Articles found in XML:", len(articles_xml))

        articles_info = []
        for article in articles_xml:
            pmid = article.find("pmid").get_text(strip=True)  # from the record itself, so links always match
            title_tag = article.find("articletitle") or article.find("booktitle")
            abstract_tag = article.find("abstract")
            date_tag = article.find("pubdate")
            author_tags = article.find_all("author")

            # Title
            title = " ".join(title_tag.get_text().split()) if title_tag else "No title"  # keeps spaces around <i> tags

            # Abstract
            abstract = abstract_tag.get_text(separator=" ", strip=True) if abstract_tag else "No abstract available"

            # Authors
            authors = []
            for author in author_tags:
                last = author.find("lastname")
                fore = author.find("forename")
                if last and fore:
                    authors.append(f"{fore.get_text()} {last.get_text()}")
                elif last:
                    authors.append(last.get_text())
            authors = authors if authors else ["No authors listed"]

            # Publication Date
            pub_date, pub_year = "No date", None
            if date_tag:
                year = date_tag.find("year")
                month = date_tag.find("month")
                month = month.get_text() if month else None
                if month and month.isdigit() and 1 <= int(month) <= 12:  # book records use "01", articles "Jan"
                    month = calendar.month_abbr[int(month)]
                pub_date = f"{month} {year.get_text()}" if year and month else year.get_text() if year else "No date"
                pub_year = int(year.get_text()) if year and year.get_text().isdigit() else None

            # Study types, e.g. ["Journal Article", "Review"] or ["Study Guide"] for StatPearls chapters
            publication_types = [t.get_text(strip=True) for t in article.find_all("publicationtype")]

            # PubMed Article URL
            url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

            print(f"Article: {title}\n   - Authors: {authors}\n   - Date: {pub_date}\n   - URL: {url}\n")
            articles_info.append({
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "publication_date": pub_date,
                "year": pub_year,
                "publication_types": publication_types,
                "article_url": url
            })

        if not articles_info and use_mock_if_empty:
            print("No valid articles found, returning mock data.")
            return [{
                "title": "Simulated Study on Fever",
                "abstract": "This is a simulated abstract on the treatment of fever in adults.",
                "authors": ["John Doe", "Jane Smith"],
                "publication_date": "March 2024",
                "article_url": "https://pubmed.ncbi.nlm.nih.gov/12345678/"
            }]
        return articles_info

    except Exception as e:
        print(f"Error during PubMed fetch: {e}")
        if use_mock_if_empty:
            return [{
                "title": "Simulated Study on Fever",
                "abstract": "This is a simulated abstract on the treatment of fever in adults.",
                "authors": ["John Doe", "Jane Smith"],
                "publication_date": "March 2024",
                "article_url": "https://pubmed.ncbi.nlm.nih.gov/12345678/"
            }]
        else:
            return [{"message": f"Error: {e}"}]
