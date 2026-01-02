import os
import re
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event

BASE = "https://www.londonbuddhistcentre.com"
URL = "https://www.londonbuddhistcentre.com/whats-on"
TZ = ZoneInfo("Europe/London")


def uid(text):
    return hashlib.md5(text.encode()).hexdigest() + "@lbc"


headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-GB,en;q=0.9",
}


def main():
    r = requests.get(URL, headers=headers, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    cal = Calendar()
    cal.add("prodid", "-//London Buddhist Centre//ICS//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "London Buddhist Centre")
    cal.add("x-wr-timezone", "Europe/London")

    events = soup.select("div[role='listitem']")

    for ev in events:
        title_el = ev.find("h4")
        link_el = ev.find("a", href=True)
        time_el = ev.find(string=re.compile(r"\d{1,2}:\d{2}"))

        if not title_el or not link_el or not time_el:
            continue

        title = title_el.get_text(strip=True)
        url = BASE + link_el["href"]

        m = re.search(r"(\d{1,2}:\d{2}\s*(?:am|pm))\s*-\s*(\d{1,2}:\d{2}\s*(?:am|pm))", time_el)
        if not m:
            continue

        start_t, end_t = m.groups()

        today = datetime.now(TZ)
        start = datetime.strptime(start_t, "%I:%M %p").replace(
            year=today.year, month=today.month, day=today.day, tzinfo=TZ
        )
        end = datetime.strptime(end_t, "%I:%M %p").replace(
            year=today.year, month=today.month, day=today.day, tzinfo=TZ
        )

        e = Event()
        e.add("uid", uid(url + title))
        e.add("summary", title)
        e.add("dtstart", start)
        e.add("dtend", end)
        e.add("url", url)

        cal.add_component(e)

    os.makedirs("docs", exist_ok=True)
    with open("docs/lbc.ics", "wb") as f:
        f.write(cal.to_ical())


if __name__ == "__main__":
    main()
