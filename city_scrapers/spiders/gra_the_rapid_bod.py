"""
The Rapid (Interurban Transit Partnership) board and committee meetings.

Everything comes from https://www.ridetherapid.org/about-the-rapid/board-of-directors

1. "FY <year> Board Meeting Packets" accordions list packet PDFs per body:
   board packets first, then one heading per committee. Link text is only
   month + year ("March 2026", "July 2025 Board Budget Workshop"), so the
   day, time and location come from the first page of each packet:

       FINANCE COMMITTEE MEETING
       Wednesday, November 5, 2025 – 4:00 p.m.
       Rapid Central Station Conference Room (250 Cesar Chavez Avenue, SW)

   Canceled meetings are plain text without a link ("June 2026 - CANCELED").
2. Packets end with "Next meeting: January 21, 2026", which gives the next
   meeting (with the time and location of that packet) and the day of a
   meeting the page later marks as canceled.
3. A "<year> Meeting Dates" list gives the board meeting dates of that year,
   for board meetings without a packet (upcoming or canceled ones).

The annual schedule PDF is not read because its layout changes between
versions. The Consumer Advisory Committee has no packets on the page, so no
meetings are produced for it.

Major breakages (failed requests, sections not found, no meetings) are
reported once on close through the `spider_error` signal, which forwards them
to Sentry. Problems with single packets or entries are only logged.
"""

import re
from collections import defaultdict
from datetime import date, datetime, time
from io import BytesIO
from zoneinfo import ZoneInfo

import scrapy
from city_scrapers_core.constants import (
    ADVISORY_COMMITTEE,
    BOARD,
    CANCELLED,
    COMMITTEE,
    PASSED,
    TENTATIVE,
)
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.relativedelta import relativedelta
from pypdf import PdfReader
from scrapy import signals
from twisted.python.failure import Failure

BOARD_BODY = "board"
FINANCE_BODY = "finance"
PLANNING_BODY = "planning"
PERFORMANCE_BODY = "performance"
CONSUMER_ADVISORY_BODY = "consumer_advisory"

BODIES = {
    BOARD_BODY: ("Board of Directors", BOARD),
    FINANCE_BODY: ("Finance Committee", COMMITTEE),
    # Was "Planning & Technology Committee"; now "Future Planning & Innovation"
    # on the page and "Future Planning & Innovations" in packets
    PLANNING_BODY: ("Future Planning & Innovation Committee", COMMITTEE),
    PERFORMANCE_BODY: ("Present Performance & Service Committee", COMMITTEE),
    CONSUMER_ADVISORY_BODY: (
        "Consumer Advisory Committee for Seniors & Persons with Disabilities",
        ADVISORY_COMMITTEE,
    ),
}
BOARD_SPECIAL_TITLE = "Board Special Meeting"

# Section headings on the page, matched in order
_BODY_HEADING_RES = [
    (re.compile(r"finance", re.I), FINANCE_BODY),
    (re.compile(r"planning", re.I), PLANNING_BODY),
    (re.compile(r"present\s+performance", re.I), PERFORMANCE_BODY),
    (re.compile(r"consumer\s+advisory", re.I), CONSUMER_ADVISORY_BODY),
]
_SPECIAL_RE = re.compile(r"retreat|workshop|special", re.I)

_FY_HEADER_RE = re.compile(r"FY\s*\d{4}\s+Board\s+Meeting\s+Packets", re.I)
# "March 2026", "February 2026 Board Retreat"
_LINK_MONTH_RE = re.compile(
    r"^(?P<month>[A-Za-z]+)\.?\s+(?P<year>\d{4})\b(?P<label>.*)$"
)
# "June 2026 - CANCELED", "January 2025 CANCELED", "November 2023 *Canceled*"
_CANCELED_RE = re.compile(
    r"(?P<month>[A-Za-z]+)\.?\s+(?P<year>\d{4})[\s\-–—:*]*CANCEL", re.I
)
# "2026 Meeting Dates"
_DATES_HEADING_RE = re.compile(r"(?P<year>\d{4})\s+Meeting\s+Dates", re.I)
# "January 28", "July 22 (Board Budget Workshop)"
_LIST_DATE_RE = re.compile(
    r"^(?P<month>[A-Za-z]+)\.?\s+(?P<day>\d{1,2})\b\s*(?:\((?P<label>[^)]*)\))?"
)
# "November 18, 2026 - 4:00 p.m." above the current board packet link
_HTML_DATE_RE = re.compile(r"[A-Za-z]+\s+\d{1,2},\s*(?P<year>\d{4})")

# "Wednesday, November 5, 2025 – 4:00 p.m.". The weekday and its comma are
# optional ("November 6, 2024 – 4:00 p.m.", "Wednesday November 18, 2026"),
# and so are the minutes ("4 p.m."). The "– <time>" part is required, so
# lines like "MINUTES REVIEW – September 24, 2025" don't match.
_PACKET_DATE_RE = re.compile(
    r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?"
    r"(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})\s*[–—-]\s*"
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>[ap])\.?\s*m\b\.?",
    re.I,
)
# "Next meeting: January 21, 2026"; "Next meeting: TBD, 2027" doesn't match
_NEXT_MEETING_RE = re.compile(
    r"Next\s+meeting:\s*(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2}),\s*(?P<year>\d{4})",
    re.I,
)

_LOCATION_CHANGE_RE = re.compile(r"^location\s+change\s*[,:–-]?\s*", re.I)
# "Name (250 Cesar Chavez Avenue, SW)", "Name | 250 Cesar E Chavez, SW",
# "Rapid Operations Center, 301 Bartlett Street SW"
_LOCATION_RES = [
    re.compile(r"^(?P<name>.+?)\s*\((?P<address>[^)]+)\)\s*$"),
    re.compile(r"^(?P<name>.+?)\s*\|\s*(?P<address>.+)$"),
    re.compile(r"^(?P<name>[^,]+?)\s*,\s*(?P<address>\d.+)$"),
]
# Spellings of the same room used in packets; the address is kept as printed
_KNOWN_LOCATIONS = {
    "rapid central station conference room": "Rapid Central Station Conference Room",
    "rapid central station": "Rapid Central Station Conference Room",
    "rapid operations center": "Rapid Operations Center",
    "rapid operations center training room": "Rapid Operations Center Training Room",
    "rapid board room": "Ellsworth Board Room",
    "ellsworth board room": "Ellsworth Board Room",
}
_CITY = "Grand Rapids, MI"

# Priority of the sources of a meeting; the highest one wins for a date
_FROM_NEXT_MEETING = 1
_FROM_DATE_LIST = 2
_FROM_PACKET = 3


class GraTheRapidBodError(Exception):
    """The Rapid's board page could not be read as expected."""


class GraTheRapidBodSpider(CityScrapersSpider):
    name = "gra_the_rapid_bod"
    agency = "The Rapid Board of Directors"
    timezone = "America/Detroit"
    start_urls = ["https://www.ridetherapid.org/about-the-rapid/board-of-directors"]

    lookback_years = 2

    # Used for board meetings from the date list when no regular board packet
    # was read
    default_board_time = time(16, 0)
    default_location = {
        "name": "Rapid Central Station Conference Room",
        "address": f"250 Cesar E Chavez Ave SW, {_CITY}",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._problems = []
        self._failed_requests = 0
        self._packets = []
        self._canceled = []
        self._board_dates = []
        self._pending = 0
        self._packets_requested = 0
        self._meetings_parsed = 0

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider._on_spider_closed, signal=signals.spider_closed)
        return spider

    def _now(self):
        """
        Current time in Grand Rapids, naive like meeting start times. Scrapers
        run on UTC servers, where datetime.now() is 4-5 hours ahead.
        """
        return datetime.now(ZoneInfo(self.timezone)).replace(tzinfo=None)

    @property
    def cutoff_date(self):
        return self._now().date() - relativedelta(years=self.lookback_years)

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(url, callback=self.parse, errback=self._request_failed)

    def parse(self, response):
        self._board_dates = self._parse_board_dates(response)
        entries = self._parse_current_packet(response) + self._parse_fy_sections(
            response
        )

        seen = set()
        requests = []
        for entry in entries:
            if entry["canceled"]:
                if self._in_window(entry["year"], entry["month"]):
                    self._canceled.append(entry)
                continue
            if entry["url"] in seen or not self._in_window(
                entry["year"], entry["month"]
            ):
                continue
            seen.add(entry["url"])
            requests.append(
                scrapy.Request(
                    entry["url"],
                    callback=self._parse_packet,
                    errback=self._packet_failed,
                    cb_kwargs={"entry": entry},
                    dont_filter=True,
                )
            )

        self._pending = self._packets_requested = len(requests)
        if not requests:
            yield from self._parse_meetings()
            return
        yield from requests

    def _in_window(self, year, month):
        """Whether a month can hold meetings on or after the cutoff date."""
        cutoff = self.cutoff_date
        return (year, month) >= (cutoff.year, cutoff.month)

    def _parse_board_dates(self, response):
        """
        Dates from the "<year> Meeting Dates" list. The year is taken from the
        heading, whatever year it is.
        """
        headings = response.xpath(
            "//*[self::h1 or self::h2 or self::h3 or self::h4 or self::h5 or "
            "self::h6][contains(normalize-space(.), 'Meeting Dates')]"
        )
        for heading in headings:
            match = _DATES_HEADING_RE.search(self._node_text(heading))
            if not match:
                continue
            year = int(match.group("year"))
            dates = []
            for li in heading.xpath("following-sibling::ul[1]/li"):
                text = self._node_text(li)
                item = _LIST_DATE_RE.match(text)
                month = self._month_number(item.group("month")) if item else None
                meeting_date = (
                    self._safe_date(year, month, int(item.group("day")))
                    if month
                    else None
                )
                if not meeting_date:
                    self.logger.warning(f"Could not read board meeting date {text!r}")
                    continue
                dates.append(
                    {"date": meeting_date, "label": (item.group("label") or "").strip()}
                )
            if not dates:
                self._add_problem("'<year> Meeting Dates' list is empty")
            return dates
        self._add_problem(
            "'<year> Meeting Dates' heading not found on the board page; the page "
            "layout may have changed"
        )
        return []

    def _parse_current_packet(self, response):
        """
        The packet of the current board meeting is linked above the member
        list ("Board of Directors Meeting", "November 18, 2026 - 4:00 p.m.",
        "Meeting Packet") rather than in the FY sections.
        """
        entries = []
        for heading in response.xpath(
            "//h6[contains(normalize-space(.), 'Board of Directors Meeting')]"
        ):
            paragraphs = heading.xpath("following-sibling::p[position() <= 3]")
            year_match = _HTML_DATE_RE.search(
                " ".join(self._node_text(p) for p in paragraphs)
            )
            if not year_match:
                continue
            for link in paragraphs.xpath(".//a[contains(@href, '.pdf')]"):
                entries.append(
                    {
                        "body": BOARD_BODY,
                        "url": response.urljoin(link.attrib["href"]),
                        "year": int(year_match.group("year")),
                        # Only the year is used; the month is checked
                        # against the lookback window
                        "month": 12,
                        "label": "",
                        "canceled": False,
                    }
                )
        return entries

    def _parse_fy_sections(self, response):
        """
        Packet links and canceled months from each "FY <year> Board Meeting
        Packets" accordion. Board packets come first; each committee starts
        with its own heading (h6 in newer years, h3 in older ones).
        """
        sections = [
            article
            for article in response.css("article.accordion-item-faq")
            if _FY_HEADER_RE.search(self._node_text(article.css("h4")))
        ]
        if not sections:
            self._add_problem(
                "'FY <year> Board Meeting Packets' sections not found on the board "
                "page; the page layout may have changed"
            )
            return []

        entries = []
        for section in sections:
            body = BOARD_BODY
            for node in section.xpath(
                ".//div[contains(@class, 'accordion-body-content')]//*[self::h1 or "
                "self::h2 or self::h3 or self::h4 or self::h5 or self::h6 or self::p]"
            ):
                text = self._node_text(node)
                if node.root.tag != "p":
                    if text:
                        body = self._parse_body(text)
                    continue
                if body is None:
                    continue
                entries.extend(self._parse_paragraph(node, body, response))
        return entries

    def _parse_body(self, heading):
        for pattern, body in _BODY_HEADING_RES:
            if pattern.search(heading):
                return body
        self.logger.warning(f"Unknown section heading {heading!r}; skipping it")
        return None

    def _parse_paragraph(self, node, body, response):
        entries = []
        for link in node.xpath(".//a[@href]"):
            text = self._node_text(link)
            match = _LINK_MONTH_RE.match(text)
            month = self._month_number(match.group("month")) if match else None
            if not month:
                # Older sections have links like "Part 1" or "Audit Report"
                self.logger.debug(f"No month and year in packet link {text!r}")
                continue
            entries.append(
                {
                    "body": body,
                    "url": response.urljoin(link.attrib["href"]),
                    "year": int(match.group("year")),
                    "month": month,
                    "label": match.group("label").strip(),
                    "canceled": False,
                }
            )
        if not entries:
            text = self._node_text(node)
            for match in _CANCELED_RE.finditer(text):
                month = self._month_number(match.group("month"))
                if month:
                    entries.append(
                        {
                            "body": body,
                            "year": int(match.group("year")),
                            "month": month,
                            "canceled": True,
                        }
                    )
            if not entries and re.search(r"cancel", text, re.I):
                # e.g. "July 15 CANCELED", which has no year
                self.logger.debug(f"Could not read canceled meeting {text!r}")
        return entries

    def _parse_packet(self, response, entry):
        try:
            text = self._pdf_first_page_text(response.body)
        except Exception as e:
            self.logger.warning(f"Could not read packet PDF {response.url}: {e!r}")
            text = ""
        packet = self._parse_packet_text(text, entry)
        if packet:
            self._packets.append(packet)
        yield from self._packet_done()

    def _packet_failed(self, failure):
        self._request_failed(failure)
        yield from self._packet_done()

    def _packet_done(self):
        self._pending -= 1
        if self._pending == 0:
            yield from self._parse_meetings()

    def _pdf_first_page_text(self, body):
        return PdfReader(BytesIO(body)).pages[0].extract_text() or ""

    def _parse_packet_text(self, text, entry):
        """
        Title, date, time and location from the first page of a packet, plus
        the "Next meeting" date if there is one. The title is the line(s)
        before the date line and the location is the line after it.
        """
        lines = [self._clean_text(line) for line in text.splitlines()]
        lines = [line for line in lines if line]
        for index, line in enumerate(lines):
            match = _PACKET_DATE_RE.search(line)
            if match:
                break
        else:
            self.logger.warning(f"No meeting date found in packet {entry['url']}")
            return None

        # The year in packets has typos ("Tuesday, January 14, 2024" in the
        # January 2025 packet), so it comes from the link text
        month = self._month_number(match.group("month"))
        meeting_date = (
            self._safe_date(entry["year"], month, int(match.group("day")))
            if month
            else None
        )
        if not meeting_date:
            self.logger.warning(
                f"Invalid meeting date {line!r} in packet {entry['url']}"
            )
            return None
        if int(match.group("year")) != entry["year"]:
            self.logger.warning(
                f"Packet {entry['url']} says {match.group('year')}, using "
                f"{entry['year']} from the link text"
            )

        hour = int(match.group("hour")) % 12
        if match.group("ampm").lower() == "p":
            hour += 12
        start_time = time(hour, int(match.group("minute") or 0))

        title_lines = []
        for previous in reversed(lines[max(0, index - 3) : index]):
            if not self._is_caps(previous):
                break
            if previous.upper() != "AGENDA":
                title_lines.insert(0, previous)
        title = " ".join(title_lines)

        location_line = lines[index + 1] if index + 1 < len(lines) else ""
        location = self._parse_location(location_line, entry["url"])

        next_date = None
        next_match = _NEXT_MEETING_RE.search("\n".join(lines))
        if next_match:
            next_month = self._month_number(next_match.group("month"))
            next_date = next_month and self._safe_date(
                int(next_match.group("year")), next_month, int(next_match.group("day"))
            )
            if not next_date or next_date <= meeting_date:
                self.logger.warning(
                    f"Ignoring next meeting {next_match.group(0)!r} in packet "
                    f"{entry['url']} (meeting on {meeting_date})"
                )
                next_date = None
        elif re.search(r"Next\s+meeting:", text, re.I):
            # "Next meeting: TBD, 2027", or garbled text
            self.logger.info(f"No next meeting date in packet {entry['url']}")

        return {
            "body": entry["body"],
            "date": meeting_date,
            "time": start_time,
            "title": title,
            "special": bool(_SPECIAL_RE.search(f"{title} {entry['label']}")),
            "location": location,
            "url": entry["url"],
            "next_date": next_date,
        }

    def _parse_location(self, line, url):
        line = _LOCATION_CHANGE_RE.sub("", line).strip()
        if not line or line.upper() == "AGENDA":
            self.logger.warning(f"No location found in packet {url}")
            return dict(self.default_location)
        for pattern in _LOCATION_RES:
            match = pattern.match(line)
            if match:
                name = match.group("name").strip(" ,")
                address = match.group("address").strip(" ,")
                name = _KNOWN_LOCATIONS.get(name.lower(), name)
                return {"name": name, "address": f"{address}, {_CITY}"}
        self.logger.warning(f"Could not read location {line!r} in packet {url}")
        return {"name": line, "address": ""}

    def _parse_meetings(self):
        if self._packets_requested and not self._packets:
            self._add_problem(
                f"no meeting date read from any of {self._packets_requested} "
                "packets; the packet layout may have changed"
            )

        records = {}

        def add(record):
            key = (record["body"], record["date"])
            if key not in records or records[key]["priority"] < record["priority"]:
                records[key] = record

        for packet in self._packets:
            add({**packet, "priority": _FROM_PACKET, "canceled": False})
            if packet["next_date"]:
                add(
                    {
                        "body": packet["body"],
                        "date": packet["next_date"],
                        "time": packet["time"],
                        "special": False,
                        "location": packet["location"],
                        "url": None,
                        "priority": _FROM_NEXT_MEETING,
                        "canceled": False,
                    }
                )

        board_time, board_location = self._board_template()
        for item in self._board_dates:
            add(
                {
                    "body": BOARD_BODY,
                    "date": item["date"],
                    "time": board_time,
                    "special": bool(_SPECIAL_RE.search(item["label"])),
                    "location": board_location,
                    "url": None,
                    "priority": _FROM_DATE_LIST,
                    "canceled": False,
                }
            )

        self._apply_cancellations(records)

        for record in sorted(
            records.values(), key=lambda r: (r["date"], r["time"], r["body"])
        ):
            if record["date"] < self.cutoff_date:
                continue
            meeting = self._build_meeting(record)
            self._meetings_parsed += 1
            yield meeting

    def _board_template(self):
        """Time and location of the latest regular board packet."""
        regular = [
            p for p in self._packets if p["body"] == BOARD_BODY and not p["special"]
        ]
        if not regular:
            return self.default_board_time, dict(self.default_location)
        latest = max(regular, key=lambda p: p["date"])
        return latest["time"], latest["location"]

    def _apply_cancellations(self, records):
        """
        A canceled month gets the day of the meeting expected in that month:
        an earlier packet's "Next meeting" date (committees) or the date list
        (board). Months without one can't be dated and are skipped.
        """
        by_month = defaultdict(list)
        for record in records.values():
            by_month[
                (record["body"], record["date"].year, record["date"].month)
            ].append(record)

        for entry in self._canceled:
            key = (entry["body"], entry["year"], entry["month"])
            name = f"{BODIES[entry['body']][0]} {entry['year']}-{entry['month']:02d}"
            candidates = [r for r in by_month.get(key, []) if r["url"] is None]
            if any(r["url"] for r in by_month.get(key, [])):
                self.logger.warning(
                    f"{name} is marked canceled but has a packet; keeping the packet"
                )
            elif len(candidates) == 1:
                candidates[0]["canceled"] = True
            elif not candidates:
                self.logger.info(
                    f"Canceled meeting {name} can't be dated (no earlier packet "
                    "or list date gives its day); skipping it"
                )
            else:
                self.logger.warning(
                    f"Canceled meeting {name} matches several dates; skipping it"
                )

    def _build_meeting(self, record):
        title, classification = BODIES[record["body"]]
        if record["body"] == BOARD_BODY and record["special"]:
            title = BOARD_SPECIAL_TITLE
        links = []
        if record["url"]:
            links.append({"href": record["url"], "title": "Meeting Packet"})
        meeting = Meeting(
            title=title,
            description="",
            classification=classification,
            start=datetime.combine(record["date"], record["time"]),
            end=None,
            all_day=False,
            time_notes="",
            location=record["location"],
            links=links,
            source=self.start_urls[0],
        )
        meeting["status"] = self._get_status(
            meeting, text="canceled" if record["canceled"] else ""
        )
        meeting["id"] = self._get_id(meeting)
        return meeting

    def _request_failed(self, failure):
        """
        Without an errback, HTTP errors and network failures are only logged
        by Scrapy and never reach Sentry; reported on spider close.
        """
        self._failed_requests += 1
        request = getattr(failure, "request", None)
        url = request.url if request else self.start_urls[0]
        self._add_problem(f"request to {url} failed: {failure.value!r}")

    def _add_problem(self, problem):
        self.logger.warning(problem)
        self._problems.append(problem)

    def _on_spider_closed(self, spider, reason):
        """Report one error per run for major breakages only."""
        problems = list(self._problems)
        if reason == "finished" and self._meetings_parsed == 0:
            problems.append("0 meetings parsed")
        if not problems:
            return
        self._report_error(
            GraTheRapidBodError(
                f"{self.name}: {'; '.join(problems)} (finish_reason={reason}, "
                f"failed_requests={self._failed_requests}, "
                f"packets={len(self._packets)}/{self._packets_requested}, "
                f"meetings={self._meetings_parsed})"
            )
        )

    def _get_status(self, item, text=""):
        """
        Like the core version, but compares the start time with the time in
        Grand Rapids rather than the server's time, so a 4:00 p.m. meeting
        isn't marked passed at noon.
        """
        status = super()._get_status(item, text)
        if status == CANCELLED:
            return status
        return PASSED if item["start"] < self._now() else TENTATIVE

    def _report_error(self, exc):
        """Log and send spider_error (forwarded to Sentry)."""
        self.logger.error(str(exc))
        self.crawler.stats.inc_value(f"spider_exceptions/{exc.__class__.__name__}")
        self.crawler.signals.send_catch_log(
            signal=signals.spider_error,
            failure=Failure(exc),
            response=None,
            spider=self,
        )

    def _node_text(self, node):
        return self._clean_text(" ".join(node.xpath(".//text()").getall()))

    def _clean_text(self, text):
        return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()

    def _is_caps(self, line):
        letters = [c for c in line if c.isalpha()]
        return bool(letters) and all(c.isupper() for c in letters)

    def _month_number(self, name):
        for fmt in ("%B", "%b"):
            try:
                return datetime.strptime(name[:3] if fmt == "%b" else name, fmt).month
            except ValueError:
                continue
        return None

    def _safe_date(self, year, month, day):
        try:
            return date(year, month, day)
        except (TypeError, ValueError):
            return None
