"""
Debug script to inspect tournament page structure and extract dates
"""

import requests
from bs4 import BeautifulSoup
import json

# The URL from the database
url = "https://badmintonsweden.tournamentsoftware.com/tournament/77FEC02B-4489-4D4C-A71F-C6844BAEB2BA"

print("=" * 80)
print("DEBUGGING TOURNAMENT PAGE SCRAPING")
print("=" * 80)
print(f"\nURL: {url}\n")

try:
    # Set up session with cookiewall bypass
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0"})
    s.post("https://badmintonsweden.tournamentsoftware.com/cookiewall/Save", data={
        "ReturnUrl": "/",
        "SettingsOpen": "false",
        "CookieWallCategoryPreferences": "1,2,3"
    }, allow_redirects=True, timeout=5)

    # Fetch the tournament page
    print("Fetching tournament page...")
    resp = s.get(url, timeout=10)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Get tournament name
    print("\n" + "=" * 80)
    print("1. TOURNAMENT NAME EXTRACTION")
    print("=" * 80)
    
    name_el = soup.select_one(".media__title a")
    if name_el:
        name = name_el.get_text(strip=True)
        print(f"✅ Found via '.media__title a': {name}")
    else:
        name_el = soup.select_one(".media__title")
        if name_el:
            name = name_el.get_text(strip=True)
            print(f"✅ Found via '.media__title': {name}")
        else:
            print("❌ Tournament name not found")
            name = None
    
    # Get location
    print("\n" + "=" * 80)
    print("2. LOCATION EXTRACTION")
    print("=" * 80)
    
    location_el = soup.select_one(".media__subheading")
    if location_el:
        location = location_el.get_text(strip=True)
        print(f"✅ Found via '.media__subheading': {location}")
    else:
        print("❌ Location not found")
        location = None
    
    # Try to find timeline
    print("\n" + "=" * 80)
    print("3. TIMELINE DATES EXTRACTION")
    print("=" * 80)
    
    timeline = soup.select_one(".tournament-meta__timeline")
    if timeline:
        print("✅ Found '.tournament-meta__timeline'")
        
        dates = {}
        list_items = timeline.find_all("li")
        print(f"   Found {len(list_items)} list items in timeline")
        
        for i, li in enumerate(list_items):
            print(f"\n   Item {i+1}:")
            
            label_el = li.select_one(".list__value")
            time_el = li.find("time")
            
            if label_el:
                label = label_el.get_text(strip=True)
                print(f"     Label: {label}")
            else:
                print(f"     Label: NOT FOUND")
                label = None
            
            if time_el:
                datetime_val = time_el.get("datetime", "")
                print(f"     DateTime attribute: {datetime_val}")
                print(f"     DateTime[:10]: {datetime_val[:10]}")
            else:
                print(f"     Time element: NOT FOUND")
                time_el = None
            
            if label_el and time_el:
                label = label_el.get_text(strip=True)
                datetime_val = time_el.get("datetime", "")[:10]
                
                if "öppnar" in label.lower():
                    dates["registration_opens"] = datetime_val
                    print(f"     → registration_opens = {datetime_val}")
                elif "stänger" in label.lower():
                    dates["registration_closes"] = datetime_val
                    print(f"     → registration_closes = {datetime_val}")
                elif "återbud" in label.lower():
                    dates["cancellation_deadline"] = datetime_val
                    print(f"     → cancellation_deadline = {datetime_val}")
                elif "start" in label.lower():
                    dates["competition_start"] = datetime_val
                    print(f"     → competition_start = {datetime_val}")
                elif "slut" in label.lower():
                    dates["competition_end"] = datetime_val
                    print(f"     → competition_end = {datetime_val}")
        
        print(f"\n   Extracted dates: {json.dumps(dates, indent=2)}")
    else:
        print("❌ '.tournament-meta__timeline' NOT FOUND")
        print("   Looking for alternative selectors...")
        
        # Try to find any elements with "timeline" class
        timeline_elements = soup.find_all(class_=lambda x: x and "timeline" in x.lower())
        print(f"   Found {len(timeline_elements)} elements with 'timeline' in class name")
        
        for i, el in enumerate(timeline_elements[:3]):
            print(f"\n   Element {i+1}:")
            print(f"     Tag: {el.name}")
            print(f"     Classes: {el.get('class', [])}")
            print(f"     HTML snippet: {str(el)[:200]}...")
        
        # Try to find time elements
        print("\n   Looking for <time> elements...")
        time_elements = soup.find_all("time")
        print(f"   Found {len(time_elements)} <time> elements total")
        
        for i, time_el in enumerate(time_elements[:5]):
            print(f"\n   Time element {i+1}:")
            print(f"     datetime: {time_el.get('datetime', 'NOT SET')}")
            print(f"     text: {time_el.get_text(strip=True)}")
            parent = time_el.find_parent("li")
            if parent:
                print(f"     parent <li> found: yes")
                label_el = parent.select_one(".list__value")
                if label_el:
                    print(f"     label: {label_el.get_text(strip=True)}")
    
    # Look for any structured date/time data
    print("\n" + "=" * 80)
    print("4. ALTERNATIVE DATE EXTRACTION METHODS")
    print("=" * 80)
    
    # Method 1: Look for any element with text containing date patterns
    print("\nMethod 1: Text-based search")
    import re
    date_pattern = r'\d{4}-\d{2}-\d{2}'
    text_content = soup.get_text()
    dates_found = re.findall(date_pattern, text_content)
    if dates_found:
        print(f"  Found {len(set(dates_found))} unique dates in page text:")
        for date in set(dates_found):
            print(f"    - {date}")
    else:
        print("  No dates in YYYY-MM-DD format found")
    
    # Method 2: Look for data attributes
    print("\nMethod 2: Data attributes")
    data_elements = soup.find_all(attrs={"data-date": True})
    if data_elements:
        print(f"  Found {len(data_elements)} elements with data-date attribute:")
        for el in data_elements[:3]:
            print(f"    - {el.get('data-date')}: {el.get_text(strip=True)[:50]}")
    else:
        print("  No elements with data-date attribute found")
    
    # Method 3: Look for specific text patterns
    print("\nMethod 3: Text pattern search")
    for text in ["Anmälan öppnar", "Anmälan stänger", "Återbud senast", "Tävling börjar", "Tävling slutar"]:
        elements = soup.find_all(string=re.compile(text, re.IGNORECASE))
        if elements:
            print(f"  Found '{text}': {len(elements)} occurrences")
            for el in elements[:1]:
                parent = el.find_parent("li")
                if parent:
                    time_el = parent.find("time")
                    if time_el:
                        print(f"    → datetime: {time_el.get('datetime', 'NOT SET')}")
    
    print("\n" + "=" * 80)
    print("PAGE STRUCTURE SUMMARY")
    print("=" * 80)
    print(f"HTML length: {len(resp.text)} characters")
    print(f"Title: {soup.title.string if soup.title else 'NO TITLE'}")
    
except Exception as e:
    print(f"\n❌ Error: {e}")
    import traceback
    traceback.print_exc()
