import time
import pandas as pd
import requests

# 1. Define the SEC SIC Code Ranges for your target groups
def map_sic_to_sector(sic_code):
    if not sic_code:
        return "Unknown"
    
    try:
        sic = int(sic_code)
    except ValueError:
        return "Unknown"
    
    # Mapping based on official SEC Industrial Taxonomy guidelines
    if (7370 <= sic <= 7379) or (3570 <= sic <= 3577):
        return "Technology"
    elif (2833 <= sic <= 2836) or (3840 <= sic <= 3849) or (8000 <= sic <= 8999 and sic != 8742):
        return "Healthcare"
    elif (1311 <= sic <= 1389) or (2911 <= sic <= 2999) or (4911 <= sic <= 4939):
        return "Energy"
    elif (5200 <= sic <= 5999):
        return "Retail"
    elif (3500 <= sic <= 3599) or (3600 <= sic <= 3699) or (3711 <= sic <= 3799):
        # Heavy engineering/machinery/electronics production
        return "Industrials"
    elif (2000 <= sic <= 2399) or (2500 <= sic <= 2599) or (3940 <= sic <= 3949):
        return "Consumer Goods"
    elif (2000 <= sic <= 3999):
        # Catch-all for other general manufacturing processes
        return "Manufacturing"
    else:
        return "Other / Financial / Services"

# 2. Load your generated data
df = pd.read_csv("all_sec_companies.csv")

# NOTE: The SEC enforces strict rate limits (max 10 requests per second).
# We will test this on a smaller slice (e.g., first 30 entries). 
# Remove the `.head(30)` restriction to run the full dataset.
df_subset = df.head(30).copy()

headers = {
    "User-Agent": "DataCollector/1.0 (myprojectemail@example.com)" # <-- CHANGE THIS
}

sic_codes = []
sic_descriptions = []
mapped_sectors = []

print("Extracting live SIC mappings natively from SEC EDGAR...")

for index, row in df_subset.iterrows():
    # Make sure CIK is padded to 10 digits as required by the SEC data endpoint
    cik_padded = str(row['cik']).zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            company_profile = response.json()
            
            # Fetch numeric SIC code and description string
            sic = company_profile.get("sic", "")
            sic_desc = company_profile.get("sicDescription", "Unknown")
            
            sic_codes.append(sic)
            sic_descriptions.append(sic_desc)
            mapped_sectors.append(map_sic_to_sector(sic))
        else:
            sic_codes.append("")
            sic_descriptions.append("Request Blocked/Error")
            mapped_sectors.append("Unknown")
            
    except Exception as e:
        sic_codes.append("")
        sic_descriptions.append(f"Error: {str(e)}")
        mapped_sectors.append("Unknown")
        
    # Crucial step: Sleep for 0.15 seconds to respect the SEC's 10-requests-per-second rate limit
    time.sleep(0.15)

# 3. Add data columns back to the DataFrame
df_subset['sic_code'] = sic_codes
df_subset['sic_description'] = sic_descriptions
df_subset['target_sector'] = mapped_sectors

# 4. Save to a new structured CSV file
df_subset.to_csv("sec_sector_classified.csv", index=False)
print("\nSuccess! Results written to 'sec_sector_classified.csv'")