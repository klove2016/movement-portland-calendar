from playwright.sync_api import sync_playwright
from ics import Calendar, Event
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import hashlib

URL = "https://movementgyms.com/portland/calendar/#activity=yoga&location=portland"
OUTPUT_FILE = "movement_portland.ics"
LOCATION = "Movement Portland"
DAYS_AHEAD = 60

def clean_html(text):
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)

def stable_uid(item, category):
    raw = f"{category}|{item.get('title')}|{item.get('startLocal')}|{item.get('endLocal')}|{item.get('link')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest() + "@movement-portland"

def main():
    now = datetime.now(timezone.utc)
    max_date = now + timedelta(days=DAYS_AHEAD)

    cal = Calendar()
    cal.creator = "Movement Portland Calendar Sync"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)

        data = page.evaluate("window.elcap_calendar_data")
        config = page.evaluate("window.elcap_calendar_config")

        browser.close()

    for index, calendar_group in data.items():
        category = config[int(index)]["label"]

        # Optional skips:
        if category in ["Youth Programs", "First Visit"]:
            continue

        for item in calendar_group.get("data", []):
            start_raw = item.get("startLocal")
            end_raw = item.get("endLocal")

            if not start_raw or not end_raw:
                continue

            start_dt = datetime.fromisoformat(start_raw)
            if start_dt < now or start_dt > max_date:
                continue

            title = item.get("title", "Untitled")
            instructor = item.get("instructor", "")
            description = clean_html(item.get("description", ""))
            link = item.get("link", "")

            event = Event()
            event.name = f"{category}: {title}"
            event.begin = start_raw
            event.end = end_raw
            event.location = LOCATION
            event.uid = stable_uid(item, category)

            event.description = "\n".join(
                part for part in [
                    f"Category: {category}",
                    f"Instructor: {instructor}" if instructor else "",
                    description,
                    link,
                ]
                if part
            )

            if link:
                event.url = link

            cal.events.add(event)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.writelines(cal)

    print(f"Wrote {len(cal.events)} events to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()