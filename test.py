import json
import pandas as pd
import requests


def get_all_sec_companies():
    # 1. Define the official SEC endpoint
    url = "https://www.sec.gov/files/company_tickers.json"

    # 2. Set your custom User-Agent (REQUIRED by the SEC)
    # The format should be: "YourName/YourVersion (YourEmail@domain.com)"
    headers = {"User-Agent": "DataCollector/1.0 (myprojectemail@example.com)"}

    print("Fetching data from the SEC database...")

    try:
        # 3. Request the data from the SEC
        response = requests.get(url, headers=headers)

        # Raise an exception if the request failed (e.g., 403 Forbidden)
        response.raise_for_status()

        # 4. Parse the JSON response
        sec_data = response.json()

        # 5. Extract every company entry into a clean list
        all_companies = []
        for index_key, company_info in sec_data.items():
            # Pad the CIK with leading zeros to make it a standard 10-digit string
            padded_cik = str(company_info["cik_str"]).zfill(10)

            all_companies.append(
                {
                    "ticker": company_info["ticker"],
                    "cik": padded_cik,
                    "company": company_info["title"],
                }
            )

        # 6. Convert the list into a structured Pandas DataFrame
        df = pd.DataFrame(all_companies)

        print(f"Successfully retrieved {len(df)} companies!\n")
        return df

    except requests.exceptions.HTTPError as e:
        print(f"\nHTTP Error occurred: {e}")
        print(
            "Double-check that you updated the 'User-Agent' header with a valid email address structure."
        )
        return None
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        return None


# --- Run the Program ---
if __name__ == "__main__":
    # Fetch the data
    df_companies = get_all_sec_companies()

    if df_companies is not None:
        # Print the first 15 companies to verify the output structure
        print("First 15 records:")
        print(df_companies.head(15).to_string(index=False))

        # Optional: Save the entire index to a CSV file on your computer
        df_companies.to_csv("all_sec_companies.csv", index=False)
        print("\nSaved all records to 'all_sec_companies.csv'")