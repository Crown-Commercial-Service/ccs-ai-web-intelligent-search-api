import requests
import pandas as pd
import time
from bs4 import BeautifulSoup



def clean_html_from_text(html_text):
    """Parses HTML and returns only the clean text."""
    if html_text is None or pd.isna(html_text):
        return None

    # Use BeautifulSoup for robust HTML cleaning
    soup = BeautifulSoup(str(html_text), 'html.parser')
    return soup.get_text(separator=' ', strip=True)



def fetch_all_ccs_frameworks(status='Live,Expired'):
    """
    Fetches all CCS Frameworks from the public API, cleans HTML, and returns a DataFrame.
    """
    base_url = "https://www.crowncommercial.gov.uk/api/frameworks"
    page_number = 1
    all_frameworks = []


    COLUMNS_TO_CLEAN = ['description', 'summary', 'benefits', 'how_to_buy', 'keywords']

    print(f"Starting to fetch and clean frameworks (Status: {status})...")

    while True:
        params = {
            "status[]": status,
            "limit": 300,
            "page": page_number
        }

        try:
            response = requests.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()


            results = data.get('results', [])
            if not results:
                print(f"Finished. Reached end of data after page {page_number}.")
                break

            # clean the data from api
            cleaned_results = []
            for record in results:
                cleaned_record = record.copy()
                for col in COLUMNS_TO_CLEAN:
                    # Check if the column exists and has content before cleaning
                    if col in cleaned_record and cleaned_record[col] is not None:
                        cleaned_record[col] = clean_html_from_text(cleaned_record[col])

                cleaned_results.append(cleaned_record)


            all_frameworks.extend(cleaned_results)
            print(f"Fetched Page {page_number}. Total frameworks collected: {len(all_frameworks)}")

            # Check for  metadata
            meta = data.get('meta', {})
            total_pages = meta.get('last_page', page_number)

            if page_number >= total_pages:
                print(f"Finished. Reached the last page: {total_pages}.")
                break

            page_number += 1
            time.sleep(0.5)

        except requests.exceptions.RequestException as e:
            print(f"❌ An error occurred during the API call on page {page_number}: {e}")
            break

    if all_frameworks:
        # Convert the list of CLEANED dictionaries to a DataFrame
        df = pd.DataFrame(all_frameworks)
        print("\n✅ DataFrame created successfully!")
        # print(f"Total Frameworks: {len(df)}")
        # print("\n--- Sample Public Framework Data (Cleaned) ---")
        # # Show the cleaned columns to confirm the HTML is gone
        # print(df[df.columns.intersection(['id', 'title', 'description'])].head())
        # df.to_csv('all_ccs_frameworks.csv', index=False)
        return df
    else:
        return None



# df_public_frameworks = fetch_all_ccs_frameworks()