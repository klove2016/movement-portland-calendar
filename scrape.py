from playwright.sync_api import sync_playwright
from ics import Calendar, Event
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, parse_qs
import hashlib
import re

URL = "https://movementgyms.com/portland/calendar/#activity=yoga&location=portland"
LOCATION = "Movement Portland"
DAYS_AHEAD = 90

SKIP_CATEGORIES = {"Youth Programs", "First Visit"}

def clean_html(text):
    if not text:
        return ""
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)

def slugify(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")

def get_date_from_link(item):
    link = item.get("link", "")
    try:
        query = parse_qs(urlparse(link).query)
        date_value = query.get("date", [None])[0]
        if date_value:
            return datetime.fromisoformat(date_value).date()
    except Exception:
        pass
    return None

def stable_uid(item, category, feed_slug, begin, end):
    raw = f"{feed_slug}|{category}|{item.get('title')}|{begin}|{end}|{item.get('link')}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest() + f"@movement-portland-{feed_slug}"

def is_multiday_event(item):
    start = datetime.fromisoformat(item["startLocal"])
    end = datetime.fromisoformat(item["endLocal"])
    return end.date() != start.date()

def is_series_parent(item):
    text = " ".join([
        item.get("title", ""),
        clean_html(item.get("description", "")),
    ]).lower()

    return (
        "series" in text
        or "over the course" in text
        or re.search(r"\b\d+\s+classes\b", text) is not None
    )

def same_time(a, b):
    return a.hour == b.hour and a.minute == b.minute

def get_actual_start(item):
    start = datetime.fromisoformat(item["startLocal"])
    link_date = get_date_from_link(item)

    if link_date:
        start = start.replace(
            year=link_date.year,
            month=link_date.month,
            day=link_date.day,
        )

    return start

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

            start = get_actual_start(item)
            end = datetime.fromisoformat(end_raw)

            if end.date() == datetime.fromisoformat(start_raw).date():
                normal_starts[category].append(start)

    return normal_starts

def has_individual_sessions_in_range(item, category, normal_starts):
    start = get_actual_start(item)
    end = datetime.fromisoformat(item["endLocal"])

    matches = [
        dt for dt in normal_starts.get(category, [])
        if start <= dt <= end and same_time(dt, start)
    ]

    return len(matches) >= 1

def get_event_time_pairs(item):
    start = get_actual_start(item)
    raw_end = datetime.fromisoformat(item["endLocal"])

    end = start.replace(
        hour=raw_end.hour,
        minute=raw_end.minute,
        second=raw_end.second,
        microsecond=raw_end.microsecond,
    )

    if end <= start:
        end = start + timedelta(hours=1)

    return [(start.isoformat(), end.isoformat())]

def build_event(item, category, feed_slug, begin, end, include_category_in_title=True):
    title = item.get("title", "Untitled")
    instructor = item.get("instructor", "")
    description = clean_html(item.get("description", ""))
    link = item.get("link", "")

    event = Event()
    event.name = f"{category}: {title}" if include_category_in_title else title
    event.begin = begin
    event.end = end
    event.location = LOCATION
    event.uid = stable_uid(item, category, feed_slug, begin, end)
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
            if item.get("isAvailable") is False:
                continue

            start_raw = item.get("startLocal")
            end_raw = item.get("endLocal")

            if not start_raw or not end_raw:
                continue

            actual_start = get_actual_start(item)

            if actual_start < now or actual_start > max_date:
                continue

            if (
                is_multiday_event(item)
                and is_series_parent(item)
                and has_individual_sessions_in_range(item, category, normal_starts)
            ):
                continue

            for begin, end in get_event_time_pairs(item):
                calendars["all"].events.add(
                    build_event(item, category, "all", begin, end, include_category_in_title=True)
                )

                calendars[slug].events.add(
                    build_event(item, category, slug, begin, end, include_category_in_title=False)
                )

    for slug, cal in calendars.items():
        output_file = f"movement_portland_{slug}.ics"

        with open(output_file, "w", encoding="utf-8") as f:
            f.writelines(cal)

        print(f"Wrote {len(cal.events)} events to {output_file}")

if __name__ == "__main__":
    main()