import time
import math

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.crowncommercial.gov.uk/api/frameworks"
COLUMNS_TO_CLEAN = ("description", "summary", "benefits", "how_to_buy", "keywords")



def clean_html_from_text(html_text):
    """Parses HTML and returns only the clean text."""
    if html_text is None:
        return None

    if isinstance(html_text, float) and math.isnan(html_text):
        return None

    text = str(html_text)
    # Fast path: avoid parser work when the text has no HTML tags.
    if "<" not in text and ">" not in text:
        return text.strip()

    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(separator=' ', strip=True)


def _clean_framework_record(record):
    cleaned_record = record.copy()
    for col in COLUMNS_TO_CLEAN:
        value = cleaned_record.get(col)
        if value is not None:
            cleaned_record[col] = clean_html_from_text(value)
    return cleaned_record


def fetch_all_ccs_frameworks(
    status="Live,Expired", *, sleep_seconds=0.5, page_limit=300, timeout=20
):
    """
    Fetches all CCS Frameworks from the public API, cleans HTML, and returns a DataFrame.
    """
    page_number = 1
    all_frameworks = []

    print(f"Starting to fetch and clean frameworks (Status: {status})...")
    with requests.Session() as session:
        while True:
            params = {"status[]": status, "limit": page_limit, "page": page_number}

            try:
                response = session.get(BASE_URL, params=params, timeout=timeout)
                response.raise_for_status()
                data = response.json()

                results = data.get("results", [])
                if not results:
                    print(f"Finished. Reached end of data after page {page_number}.")
                    break

                all_frameworks.extend(_clean_framework_record(record) for record in results)
                print(
                    f"Fetched Page {page_number}. Total frameworks collected: {len(all_frameworks)}"
                )

                meta = data.get("meta", {})
                total_pages = meta.get("last_page", page_number)
                if page_number >= total_pages:
                    print(f"Finished. Reached the last page: {total_pages}.")
                    break

                page_number += 1
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)

            except requests.exceptions.RequestException as e:
                print(f"An error occurred during the API call on page {page_number}: {e}")
                break

    if all_frameworks:
        import pandas as pd

        df = pd.DataFrame(all_frameworks)
        print("\nDataFrame created successfully!")
        return df
    return None
