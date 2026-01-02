import re
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event

BASE = "https://www.londonbuddhistcentre.com"
WHATS_ON = f"{BASE}/whats-on"
TZ = ZoneInfo("Europe/London")


def uid_for(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest() + "@lbc"


def parse_datetime_range(text: str):
    """
    Tries to parse patterns like:
    "Fri 2 Jan | 8:00 am - 9:00 am"
    Returns (start_dt, end_dt) or None.
    """
    m = re.search(
        r"([A-Za-z]{3,9})\s+(\d{1,2})\s+([A-Za-z]{3,9})\s*\|\s*"
        r"(\d{1,2}:\d{2}\s*(?:am|pm))\s*[-–]\s*(\d{1,2}:\d{2}\s*(?:am|pm))",
        text,
        re.IGNORECASE,
    )
    if not m:
        return None

    _dow, day, mon, start_t, end_t = m.groups()

    # If the page doesn't show year, assume current year in London time
    year = datetime.now(TZ).year

    start_dt = datetime.strptime(f"{day} {mon} {year} {start_t}", "%d %b %Y %I:%M %p").replace(tzinfo=TZ)
    end_dt = datetime.strptime(f"{day} {mon} {year} {end_t}", "%d %b %Y %I:%M %p").replace(tzinfo=TZ)
    return start_dt, end_dt


def main():
    html = requests.get(WHATS_ON, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")

    cal = Calendar()
    cal.add("prodid", "-//London Buddhist Centre//WhatsOn to ICS//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "London Buddhist Centre (Auto)")
    cal.add("x-wr-timezone", "Europe/London")

    # Grab all "More info" links (each should point to an event page)
    more_info_links = soup.find_all("a", string=re.compile(r"More info", re.I))

    for a in more_info_links:
        href = a.get("href")
        if not href:
            continue
        url = href if href.startswith("http") else BASE + href

        # Try to extract a date/time line from the event card area
        card_text = a.find_parent().get_text(" | ", strip=True)
        dt_range = parse_datetime_range(card_text)

        # If not found on the card, try the event page
        title = None
        if not dt_range:
            event_html = requests.get(url, timeout=30).text
            event_soup = BeautifulSoup(event_html, "html.parser")
            page_text = event_soup.get_text("\n", strip=True)
            dt_range = parse_datetime_range(page_text)

            # Title from the event page
            h = event_soup.find(["h1", "h2"])
            title = h.get_text(strip=True) if h else None
        else:
            # Title from the card: usually a bold heading nearby
            # Fallback: use first line-ish of the card text
            title = card_text.split("|")[-1].strip() if card_text else None

        if not dt_range:
            # Skip events we can't parse safely (better than wrong dates)
            continue

        start_dt, end_dt = dt_range
        if not title:
            title = "LBC Event"

        e = Event()
        e.add("uid", uid_for(url + title))
        e.add("summary", title)
        e.add("dtstart", start_dt)
        e.add("dtend", end_dt)
        e.add("dtstamp", datetime.now(TZ))
        e.add("url", url)

        cal.add_component(e)

    # Write to docs so GitHub Pages can host it
    import os
os.makedirs("docs", exist_ok=True)
    with open("docs/lbc.ics", "wb") as f:
        f.write(cal.to_ical())


if __name__ == "__main__":
    main()
