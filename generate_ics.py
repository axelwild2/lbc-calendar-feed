import re
import hashlib
from datetime import datetime, time
from zoneinfo import ZoneInfo
import os

import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event

BASE = "https://www.londonbuddhistcentre.com"
WHATS_ON = f"{BASE}/whats-on"
TZ = ZoneInfo("Europe/London")


def uid_for(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest() + "@lbc"


def parse_card_datetime(text: str):
    """
    Handles:
    1) Fri 2 Jan | 8:00 am - 9:00 am
    2) Sat 3 Jan - Sat 24 Jan (all-day range)
    """
    year = datetime.now(TZ).year

    # Case 1: date + time
    m = re.search(
        r"([A-Za-z]{3})\s+(\d{1,2})\s+([A-Za-z]{3})\s*\|\s*"
        r"(\d{1,2}:\d{2}\s*(?:am|pm))\s*[-–]\s*(\d{1,2}:\d{2}\s*(?:am|pm))",
        text,
        re.I,
    )
    if m:
        _, day, mon, start_t, end_t = m.groups()
        start = datetime.strptime(
            f"{day} {mon} {year} {start_t}", "%d %b %Y %I:%M %p"
        ).replace(tzinfo=TZ)
        end = datetime.strptime(
            f"{day} {mon} {year} {end_t}", "%d %b %Y %I:%M %p"
        ).replace(tzinfo=TZ)
        return start, end, False

    # Case 2: multi-day (no times → all-day)
    m = re.search(
        r"([A-Za-z]{3})\s+(\d{1,2})\s+([A-Za-z]{3})\s*[-–]\s*"
        r"([A-Za-z]{3})\s+(\d{1,2})\s+([A-Za-z]{3})",
        text,
        re.I,
    )
    if m:
        _, d1, m1, _, d2, m2 = m.groups()
        start = datetime.strptime(f"{d1} {m1} {year}", "%d %b %Y").replace(tzinfo=TZ)
        end = datetime.strptime(f"{d2} {m2} {year}", "%d %b %Y").replace(tzinfo=TZ)
        return start, end, True

    return None


def main():
    html = requests.get(WHATS_ON, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")

    cal = Calendar()
    cal.add("prodid", "-//London Buddhist Centre//Auto ICS//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "London Buddhist Centre")
    cal.add("x-wr-timezone", "Europe/London")

    cards = soup.select("a:contains('More info')")

    for a in cards:
        href = a.get("href")
        if not href:
            continue
        url = href if href.startswith("http") else BASE + href

        card = a.find_parent()
        text = card.get_text(" ", strip=True)

        parsed = parse_card_datetime(text)
        if not parsed:
            continue

        start, end, all_day = parsed

        # Title
        h = card.find(["h2", "h3", "strong"])
        title = h.get_text(strip=True) if h else "LBC Event"

        e = Event()
        e.add("uid", uid_for(url + title))
        e.add("summary", title)
        e.add("url", url)
        e.add("dtstamp", datetime.now(TZ))

        if all_day:
            e.add("dtstart", start.date())
            e.add("dtend", end.date())
        else:
            e.add("dtstart", start)
            e.add("dtend", end)

        cal.add_component(e)

    os.makedirs("docs", exist_ok=True)
    with open("docs/lbc.ics", "wb") as f:
        f.write(cal.to_ical())


if __name__ == "__main__":
    main()
