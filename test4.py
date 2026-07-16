import io
import json
import zipfile
import pandas as pd
import requests

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

print("Loading 'all_sec_companies.csv'...")
try:
    df_original = pd.read_csv("all_sec_companies.csv", dtype={"cik": str})
    df_original['cik_clean'] = df_original['cik'].astype(str).str.lstrip('0')
    unique_ciks_to_find = set(df_original['cik_clean'])
    print(f"Loaded {len(df_original)} entries.")
except FileNotFoundError:
    print("Error: Could not find 'all_sec_companies.csv' in your directory.")
    exit()

bulk_zip_url = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
headers = {
    "User-Agent": "DataCollector/1.0 (myprojectemail@example.com)",
    "Accept-Encoding": "gzip, deflate"
}

print("\nDownloading SEC bulk submissions...")
response = requests.get(bulk_zip_url, headers=headers, stream=True)
if response.status_code != 200:
    print(f"Download failed. HTTP Status: {response.status_code}")
    exit()

print("Processing files in memory...")
sec_metadata_lookup = {}

try:
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        cik_files = [
            f for f in z.namelist() 
            if f.split("/")[-1].startswith("CIK") and f.endswith(".json")
        ]
        
        for filename in cik_files:
            base_filename = filename.split("/")[-1]
            cik_from_file = base_filename.replace("CIK", "").replace(".json", "").lstrip('0')
            
            if cik_from_file in unique_ciks_to_find:
                try:
                    with z.open(filename) as f:
                        profile = json.loads(f.read().decode('utf-8'))
                        sic = profile.get("sic", "")
                        sic_desc = profile.get("sicDescription", "Unknown")
                        
                        sec_metadata_lookup[cik_from_file] = {
                            "sic_code": sic,
                            "sic_description": sic_desc,
                            "target_sector": map_sic_to_sector(sic)
                        }
                except Exception:
                    continue
except zipfile.BadZipFile:
    print("Error: Zip file corrupted.")
    exit()

print("Applying accurate sector mapping...")
df_original['sic_code'] = df_original['cik_clean'].map(lambda x: sec_metadata_lookup.get(x, {}).get('sic_code', ''))
df_original['sic_description'] = df_original['cik_clean'].map(lambda x: sec_metadata_lookup.get(x, {}).get('sic_description', 'Unknown'))
df_original['target_sector'] = df_original['cik_clean'].map(lambda x: sec_metadata_lookup.get(x, {}).get('target_sector', 'Unknown'))

# Format CIK as text so Excel won't drop leading zeros
df_original['cik'] = df_original['cik'].apply(lambda x: f'="{str(x).zfill(10)}"')
df_original.drop(columns=['cik_clean'], inplace=True)

output_filename = "all_sec_companies_categorized.csv"
df_original.to_csv(output_filename, index=False)
print(f"SUCCESS! Exact mappings saved to: {output_filename}")