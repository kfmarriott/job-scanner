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
    # Small niche lines
    "Lindblad Expeditions jobs",
    "American Cruise Lines coordinator",
    "American Cruise Lines marine",
    "UnCruise Adventures jobs",
    "Windstar Cruises jobs",
    "Viking River Cruises jobs",
    "Viking Ocean Cruises jobs",

    # Big cruise corporations
    "Carnival Corporation coordinator",
    "Carnival Corporation associate",
    "Royal Caribbean coordinator",
    "Royal Caribbean associate",
    "Norwegian Cruise Line coordinator",
    "Norwegian Cruise Line associate",
    "MSC Cruises coordinator",
    "Disney Cruise Line coordinator",
    "Disney Cruise Line associate",

    # Broad cruise sweeps
    "cruise line coordinator entry level",
    "cruise line rotational program",
    "expedition cruise associate hiring",
    "small ship cruise coordinator hiring",

    # Marine and conservation
    "marine operations coordinator hiring",
    "marine conservation coordinator East Coast",
    "aquarium coordinator Northeast",
    "coastal conservation associate Florida",
    "marine naturalist coordinator",
    "voyage coordinator entry level",

    # Sustainability and environmental consulting
    "marine environmental consulting associate",
    "coastal sustainability coordinator Northeast",
    "blue economy coordinator associate",

    # Port and marina development
    "marina operations coordinator East Coast",
    "waterfront development coordinator",
    "port operations associate coordinator",
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

def is_wrong_level(job):
    """Filter out jobs that are clearly too senior, irrelevant, or shipboard crew."""
    title = job.get("title", "").lower()
    
    hard_excludes = [
        # Too senior
        "uscg master", "chief mate", "chief engineer",
        "senior engineer", "staff engineer",
        "vp ", "vice president", "cto", "cfo", "coo", "ceo",
        # Officer titles
        "deck officer", "chief officer", "safety officer",
        "security officer", "medical officer", "engineering officer",
        "third officer", "second officer", "first officer",
        "staff captain", "port officer", "flag officer",
        # Irrelevant specialisms
        "firefight", "medical", "historian",
        # Shipboard hospitality crew
        "chef", "waiter", "waitress", "food server", "server",
        "housekeeper", "housekeeping", "public room attendant",
        "concierge", "bartender", "barista", "sommelier",
        "steward", "stewardess", "cabin crew", "cabin steward",
        "dishwasher", "cook ", "sous chef", "pastry", "MBA"
        "laundry", "room attendant", "galley", "casino"
        "boatswain", "electrician", "welder", "plumber", 
	"pipefitter", "oiler", "wiper", "engineer cadet",
        "security officer", "safety officer",
    ]
    
    return any(term in title for term in hard_excludes)

def requires_too_much_experience(job):
    """Filter out jobs explicitly requiring more than 5 years experience."""
    
    # Check title and description snippet
    title = job.get("title", "").lower()
    description = job.get("description", "").lower()
    text = title + " " + description
    
    experience_patterns = [
        "6+ years", "6 or more years", "6 years",
        "7+ years", "7 or more years", "7 years",
        "8+ years", "8 or more years", "8 years",
        "9+ years", "9 or more years", "9 years",
        "10+ years", "10 or more years", "10 years",
        "minimum 6 years", "minimum 7 years",
        "minimum 8 years", "minimum 10 years",
        "at least 6 years", "at least 7 years",
        "at least 8 years", "at least 10 years",
    ]
    
    return any(pattern in text for pattern in experience_patterns)

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

            # Skip clearly wrong level or irrelevant roles
            if is_wrong_level(parsed):
                print(f"  Skipping wrong level: {parsed['title']} at {parsed['company']}")
                continue

            # Skip jobs requiring more than 5 years experience
            if requires_too_much_experience(parsed):
                print(f"  Skipping overqualified: {parsed['title']} at {parsed['company']}")
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