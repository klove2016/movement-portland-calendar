from playwright.sync_api import sync_playwright
from ics import Calendar, Event
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
import hashlib
import re

URL = "https://movementgyms.com/portland/calendar/#activity=yoga&location=portland"
LOCATION = "Movement Portland"
DAYS_AHEAD = 60

SKIP_CATEGORIES = {"Youth Programs", "First Visit"}

def clean_html(text):
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)

def slugify(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")

def stable_uid(item, category, feed_slug):
    raw = f"{feed_slug}|{category}|{item.get('title')}|{item.get('startLocal')}|{item.get('endLocal')}|{item.get('link')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest() + f"@movement-portland-{feed_slug}"

def get_event_times(item):
    start = datetime.fromisoformat(item["startLocal"])
    end = datetime.fromisoformat(item["endLocal"])

    # Movement sometimes exposes multi-day endLocal values for courses.
    # Google Calendar renders those as multi-day blocks, so normalize them
    # to the start date while preserving the exposed end time.
    if end.date() != start.date():
        end = start.replace(
            hour=end.hour,
            minute=end.minute,
            second=end.second,
            microsecond=end.microsecond,
        )

        if end <= start:
            end = start + timedelta(hours=1)

    return start.isoformat(), end.isoformat()

def is_multiday_event(item):
    start = datetime.fromisoformat(item["startLocal"])
    end = datetime.fromisoformat(item["endLocal"])
    return end.date() != start.date()

def build_normal_event_starts(data, config):
    normal_starts = {}

    for index, calendar_group in enumerate(data):
        category = config[index]["label"]
        normal_starts.setdefault(category, [])

        for item in calendar_group.get("data", []):
            start_raw = item.get("startLocal")
            end_raw = item.get("endLocal")

            if not start_raw or not end_raw:
                continue

            start = datetime.fromisoformat(start_raw)
            end = datetime.fromisoformat(end_raw)

            if end.date() == start.date():
                normal_starts[category].append(start)

    return normal_starts

def has_individual_sessions_in_range(item, category, normal_starts):
    start = datetime.fromisoformat(item["startLocal"])
    end = datetime.fromisoformat(item["endLocal"])

    matches = [
        dt for dt in normal_starts.get(category, [])
        if start <= dt <= end
    ]

    return len(matches) >= 2

def build_event(item, category, feed_slug, include_category_in_title=True):
    title = item.get("title", "Untitled")
    instructor = item.get("instructor", "")
    description = clean_html(item.get("description", ""))
    link = item.get("link", "")

    event = Event()
    event.name = f"{category}: {title}" if include_category_in_title else title
    event.begin, event.end = get_event_times(item)
    event.location = LOCATION
    event.uid = stable_uid(item, category, feed_slug)
    event.transparent = True

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

    return event

def main():
    now = datetime.now(timezone.utc)
    max_date = now + timedelta(days=DAYS_AHEAD)

    calendars = {"all": Calendar()}
    calendars["all"].creator = "Movement Portland Calendar Sync"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle", timeout=60000)

        data = page.evaluate("window.elcap_calendar_data")
        config = page.evaluate("window.elcap_calendar_config")

        browser.close()

    normal_starts = build_normal_event_starts(data, config)

    for index, calendar_group in enumerate(data):
        category = config[index]["label"]

        if category in SKIP_CATEGORIES:
            continue

        slug = slugify(category)

        if slug not in calendars:
            calendars[slug] = Calendar()
            calendars[slug].creator = f"Movement Portland {category} Calendar Sync"

        for item in calendar_group.get("data", []):
            start_raw = item.get("startLocal")
            end_raw = item.get("endLocal")

            if not start_raw or not end_raw:
                continue

            start_dt = datetime.fromisoformat(start_raw)

            if start_dt < now or start_dt > max_date:
                continue

            # If a multi-day parent/course event already has individual
            # same-day sessions listed inside its range, skip the parent.
            if is_multiday_event(item) and has_individual_sessions_in_range(item, category, normal_starts):
                continue

            calendars["all"].events.add(
                build_event(item, category, "all", include_category_in_title=True)
            )

            calendars[slug].events.add(
                build_event(item, category, slug, include_category_in_title=False)
            )

    for slug, cal in calendars.items():
        output_file = f"movement_portland_{slug}.ics"

        with open(output_file, "w", encoding="utf-8") as f:
            f.writelines(cal)

        print(f"Wrote {len(cal.events)} events to {output_file}")

if __name__ == "__main__":
    main()