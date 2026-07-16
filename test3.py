import io
import json
import zipfile
import pandas as pd
import requests

# 1. Official SEC SIC Code sector mapping logic
def map_sic_to_sector(sic_code):
    if not sic_code: 
        return "Unknown"
    try: 
        sic = int(sic_code)
    except ValueError: 
        return "Unknown"
    
    if (7370 <= sic <= 7379) or (3570 <= sic <= 3577): 
        return "Technology"
    elif (2833 <= sic <= 2836) or (3840 <= sic <= 3849) or (8000 <= sic <= 8999 and sic != 8742): 
        return "Healthcare"
    elif (1311 <= sic <= 1389) or (2911 <= sic <= 2999) or (4911 <= sic <= 4939): 
        return "Energy"
    elif (5200 <= sic <= 5999): 
        return "Retail"
    elif (3500 <= sic <= 3599) or (3600 <= sic <= 3699) or (3711 <= sic <= 3799): 
        return "Industrials"
    elif (2000 <= sic <= 2399) or (2500 <= sic <= 2599) or (3940 <= sic <= 3949): 
        return "Consumer Goods"
    elif (2000 <= sic <= 3999): 
        return "Manufacturing"
    return "Other / Financial / Services"

# 2. Load your original list of 10,408 companies
print("Loading 'all_sec_companies.csv'...")
try:
    df_original = pd.read_csv("all_sec_companies.csv")
    
    # Strip leading zeros so we can do a clean, absolute match with the filenames
    df_original['cik_clean'] = df_original['cik'].astype(str).str.lstrip('0')
    ciks_to_find = set(df_original['cik_clean'])
    print(f"Loaded {len(df_original)} CIKs to map.")
except FileNotFoundError:
    print("Error: Could not find 'all_sec_companies.csv' in your directory.")
    exit()

# 3. Download the CORRECT official SEC Bulk Submissions ZIP
# Correct URL: https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip
bulk_zip_url = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
headers = {
    # The SEC strictly requires a User-Agent containing a name and a contact email address
    "User-Agent": "DataCollector/1.0 (myprojectemail@example.com)", 
    "Accept-Encoding": "gzip, deflate"
}

print("\nDownloading the SEC bulk submissions archive directly (approx. 100MB)...")
print("This may take a minute depending on your internet speed.")

try:
    response = requests.get(bulk_zip_url, headers=headers, stream=True)
    if response.status_code != 200:
        print(f"Error downloading bulk file from SEC. HTTP Status: {response.status_code}")
        print("Please make sure you have modified the User-Agent header with your real email address.")
        exit()
except Exception as e:
    print(f"Network error occurred: {e}")
    exit()

print("Download complete! Unzipping and processing files in memory...")

categorized_data = []
processed_count = 0

# 4. Open the ZIP archive from RAM and extract company details
try:
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        # Filter files that look like 'CIK000xxxxxx.json' (ignoring folders inside zip if any)
        cik_files = [
            f for f in z.namelist() 
            if f.split("/")[-1].startswith("CIK") and f.endswith(".json")
        ]
        
        for filename in cik_files:
            # Extract only the base file name to parse out the CIK
            base_filename = filename.split("/")[-1]
            cik_from_file = base_filename.replace("CIK", "").replace(".json", "").lstrip('0')
            
            # Only process files that belong to our target CSV companies list
            if cik_from_file in ciks_to_find:
                try:
                    with z.open(filename) as f:
                        # Decode JSON safely
                        profile = json.loads(f.read().decode('utf-8'))
                        
                        sic = profile.get("sic", "")
                        sic_desc = profile.get("sicDescription", "Unknown")
                        
                        # Handle cases where the "tickers" list might be empty or missing
                        tickers_list = profile.get("tickers", [])
                        ticker = tickers_list[0] if isinstance(tickers_list, list) and len(tickers_list) > 0 else ""
                        name = profile.get("name", "")
                        
                        # Standardize both codes: CIK is the unique ID, SIC is the industry sector code
                        categorized_data.append({
                            "ticker": ticker,
                            "cik": cik_from_file.zfill(10),  # Save your 10-digit CIK (e.g. 0000320193)
                            "company": name,
                            "sic_code": sic,                 # Standard Industrial Classification Code
                            "sic_description": sic_desc,
                            "target_sector": map_sic_to_sector(sic)
                        })
                        processed_count += 1
                except Exception:
                    # Skip any single corrupt or empty JSON files inside the ZIP
                    continue
except zipfile.BadZipFile:
    print("Error: The downloaded file from the SEC is corrupted. Please try running the script again.")
    exit()

# 5. Merge and export the final dataset to your workspace folder
if len(categorized_data) > 0:
    full_df = pd.DataFrame(categorized_data)
    
    # Save the file in your working directory
    output_filename = "all_sec_companies_categorized.csv"
    full_df.to_csv(output_filename, index=False)
    
    print("\n" + "="*50)
    print(f"SUCCESS! Successfully mapped {processed_count} out of {len(df_original)} companies.")
    print(f"Both CIK codes and mapped sectors have been saved!")
    print(f"Results saved to: {output_filename}")
    print("="*50)
else:
    print("\nMapped 0 companies. Please verify your 'all_sec_companies.csv' file has valid CIK values.")