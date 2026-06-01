import os
import json
import requests
import time
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ─────────────────────────────────────────
# CUSTOMIZE THESE — update as your search evolves
# ─────────────────────────────────────────

SEARCH_QUERIES = [
    # Small niche lines — pull everything recent
    "Lindblad Expeditions jobs",
    "American Cruise Lines jobs",
    "UnCruise Adventures jobs",
    "Windstar Cruises jobs",
    "Viking River Cruises jobs",
    "Viking Ocean Cruises jobs",

    # Big cruise corporations — filtered to relevant roles
    "Carnival Corporation coordinator",
    "Carnival Corporation associate",
    "Carnival Corporation operations",
    "Royal Caribbean coordinator",
    "Royal Caribbean associate",
    "Royal Caribbean rotational program",
    "Norwegian Cruise Line coordinator",
    "Norwegian Cruise Line associate",
    "MSC Cruises coordinator",
    "Disney Cruise Line coordinator",
    "Disney Cruise Line associate",

    # Broad cruise industry sweeps — catches anyone
    "cruise line coordinator entry level",
    "cruise line operations associate",
    "cruise line rotational program",
    "cruise operations coordinator East Coast",
    "expedition cruise associate hiring",

    # Marine and conservation broad sweeps
    "marine conservation coordinator East Coast",
    "ocean sustainability associate Northeast",
    "marine educator coordinator",
    "coastal conservation associate Florida",
    "marine affairs associate entry level",
    "aquarium coordinator Northeast",
    "aquarium operations associate Florida",
    "marine science program coordinator",
]

SHEET_NAME = "Job Scanner"  # Must match your Google Sheet name exactly

# ─────────────────────────────────────────
# Setup — reads secrets from environment variables
# ─────────────────────────────────────────

SERPAPI_KEY = os.environ.get("SERPAPI_KEY")

def get_sheet():
    """Connect to Google Sheets using service account credentials."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS environment variable not set")
    
    creds_dict = json.loads(creds_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open(SHEET_NAME).sheet1

def get_existing_links(sheet):
    """Get all job links already in the sheet to avoid duplicates."""
    try:
        # Link column is column 7 (index 6)
        links = sheet.col_values(7)
        return set(links[1:])  # Skip header row
    except Exception:
        return set()

def search_jobs(query):
    """Call SerpAPI's Google Jobs endpoint for a given search query."""
    params = {
       	"engine": "google_jobs",
        "q": query,
        "api_key": SERPAPI_KEY,
        "chips": "date_posted:week",
        "hl": "en",
        "gl": "us",
    }
    
    try:
        response = requests.get("https://serpapi.com/search", params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        return data.get("jobs_results", [])
    except requests.exceptions.RequestException as e:
        print(f"Error fetching jobs for '{query}': {e}")
        return []

def parse_job(job, query):
    """Extract the fields we care about from a SerpAPI job result."""
    # SerpAPI returns detected_extensions with schedule/work type info
    extensions = job.get("detected_extensions", {})
    
    return {
        "date_found": datetime.today().strftime("%Y-%m-%d"),
        "title": job.get("title", ""),
        "company": job.get("company_name", ""),
        "location": job.get("location", ""),
        "job_type": extensions.get("schedule_type", ""),
        "posted": extensions.get("posted_at", ""),
        "link": job.get("share_link", job.get("related_links", [{}])[0].get("link", "")),
        "search_term": query,
    }

def is_remote_only(job):
    """Filter out fully remote jobs — you want hybrid or in-person."""
    location = job.get("location", "").lower()
    title = job.get("title", "").lower()
    job_type = job.get("job_type", "").lower()
    
    remote_signals = ["remote", "work from home", "wfh", "anywhere"]
    hybrid_signals = ["hybrid"]
    
    # Keep if hybrid is mentioned
    if any(h in location or h in title for h in hybrid_signals):
        return False
    
    # Exclude if fully remote signals appear
    if any(r in location or r in title or r in job_type for r in remote_signals):
        return True
    
    return False

def run_scanner():
    """Main function — runs all searches and writes new jobs to the sheet."""
    print(f"Starting job scan at {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    sheet = get_sheet()
    existing_links = get_existing_links(sheet)
    
    new_jobs_count = 0
    
    for query in SEARCH_QUERIES:
        print(f"Searching: {query}")
        results = search_jobs(query)
        
        for job in results:
            parsed = parse_job(job, query)
            
            # Skip if already in sheet
            if parsed["link"] in existing_links:
                continue
            
            # Skip fully remote jobs
            if is_remote_only(parsed):
                print(f"  Skipping remote: {parsed['title']} at {parsed['company']}")
                continue
            
            # Write to sheet
            row = [
                parsed["date_found"],
                parsed["title"],
                parsed["company"],
                parsed["location"],
                parsed["job_type"],
                parsed["posted"],
                parsed["link"],
                parsed["search_term"],
            ]
            sheet.append_row(row)
            existing_links.add(parsed["link"])
            new_jobs_count += 1
            print(f"  Added: {parsed['title']} at {parsed['company']} ({parsed['location']})")
            time.sleep(1.5)
    
    print(f"\nDone. {new_jobs_count} new jobs added to sheet.")

if __name__ == "__main__":
    run_scanner()