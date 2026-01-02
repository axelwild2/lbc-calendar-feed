#!/usr/bin/env python3
"""
Generate an ICS feed from London Buddhist Centre "What's On" pages.

Writes to: docs/lbc.ics
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dtparser
from icalendar import Calendar, Event


TZ = ZoneInfo("Europe/London")
BASE = "https://www.londonbuddhistcentre.com"
OUTFILE = Path("docs/lbc.ics")

# These are the category pages you asked for
CATEGORY_PAGES = [
    f"{BASE}/whats-on?tags-event=Meditation",
    f"{BASE}/whats-on?tags-event=Buddhism",
    f"{BASE}/whats-on?tags-event=Retreats",
    f"{BASE}/whats-on?tags-event=Yoga",
    f"{BASE}/whats-on?tags-event=Courses",
    f"{BASE}/whats-on?tags-event=Online",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LBC-ICS/1.0; +https://github.com/axelwild2/lbc-calendar-feed)"
}

def stable_uid(text: str) -> str:
    h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
    return f"{h}@lbc-ics"

def fetch(url: str) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text

def absolute_url(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return BASE + href
    return BASE + "/" + href

def parse_time_range(times_text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Expect strings like: "8:00 am - 9:00 am" (sometimes with en dash).
    Returns (start_str, end_str) or (None, None)
    """
    t = times_text.strip().replace("–", "-")
    # common pattern: "8:00 am - 9:00 am"
    m = re.search(r"(\d{1,2}:\d{2}\s*(?:am|pm))\s*-\s*(\d{1,2}:\d{2}\s*(?:am|pm))", t, re.I)
    if not m:
        return None, None
    return m.group(1), m.group(2)

def iter_event_cards(html: str) -> Iterable[dict]:
    """
    Pull events from the server-rendered HTML.

    We look for each "whatson-events" card that contains:
    - an internal page link: a[fs-list-element="item-link"]
    - a title: h4[fs-list-field="keyword"]
    - date/time text inside the card
    """
    soup = BeautifulSoup(html, "html.parser")

    for card in soup.select("div.w-layout-grid.whatson-events"):
        link_tag = card.select_one('a[fs-list-element="item-link"]')
        title_tag = card.select_one('h4[fs-list-field="keyword"]')
        if not link_tag or not title_tag:
            continue

        href = link_tag.get("href", "").strip()
        if not href:
            continue
        url = absolute_url(href)

        title = " ".join(title_tag.get_text(" ", strip=True).split())

        # Find the visible date + time line, e.g. "2 Jan | 8:00 am - 9:00 am"
        # The markup typically has "2 Jan" then "|" then times.
        text = " ".join(card.get_text(" ", strip=True).split())

        # Try to detect a day+month like "2 Jan" or "20 Dec"
        dm = re.search(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", text)
        if not dm:
            continue

        day = int(dm.group(1))
        mon = dm.group(2)
        # If the page contains items spanning years, they include data-end-time on parent w-dyn-item.
        # Grab it if present; it’s the most reliable for year.
        parent_dyn = card.find_parent("div", class_="w-dyn-item")
        year = None
        if parent_dyn and parent_dyn.has_attr("data-end-time"):
            try:
                end_dt = dtparser.parse(parent_dyn["data-end-time"])
                year = end_dt.year
            except Exception:
                year = None
        if year is None:
            # fallback: assume current year (London time)
            year = datetime.now(TZ).year

        start_str, end_str = parse_time_range(text)
        if not start_str or not end_str:
            # If no time range, skip (multi-day blocks on the page can confuse parsing)
            continue

        # Build datetimes
        date_str = f"{day} {mon} {year}"
        dt_start = dtparser.parse(f"{date_str} {start_str}", dayfirst=True).replace(tzinfo=TZ)
        dt_end = dtparser.parse(f"{date_str} {end_str}", dayfirst=True).replace(tzinfo=TZ)

        # Description: first “text-size-small” paragraph inside the card is usually the blurb
        desc_tag = card.select_one(".whats-on-content .text-size-small")
        desc = desc_tag.get_text(" ", strip=True) if desc_tag else ""

        yield {
            "title": title,
            "start": dt_start,
            "end": dt_end,
            "url": url,
            "desc": desc,
        }

def build_calendar() -> Calendar:
    cal = Calendar()
    cal.add("prodid", "-//London Buddhist Centre//Auto ICS//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "London Buddhist Centre")
    cal.add("x-wr-timezone", "Europe/London")

    seen = set()

    for page in CATEGORY_PAGES:
        html = fetch(page)
        for item in iter_event_cards(html):
            key = (item["title"], item["start"].isoformat(), item["url"])
            if key in seen:
                continue
            seen.add(key)

            ev = Event()
            ev.add("uid", stable_uid(item["url"] + "|" + item["start"].isoformat()))
            ev.add("summary", item["title"])
            ev.add("dtstart", item["start"])
            ev.add("dtend", item["end"])
            ev.add("url", item["url"])
            if item["desc"]:
                ev.add("description", item["desc"])

            cal.add_component(ev)

    return cal

def main() -> None:
    OUTFILE.parent.mkdir(parents=True, exist_ok=True)
    cal = build_calendar()

    # If we somehow found zero events, still write the file (but this is your warning signal)
    OUTFILE.write_bytes(cal.to_ical())

    print(f"Wrote: {OUTFILE} ({OUTFILE.stat().st_size} bytes)")

if __name__ == "__main__":
    main()
