import json
from datetime import datetime, time
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD, CANCELLED, COMMITTEE, PASSED, TENTATIVE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time
from scrapy import signals
from scrapy.http import HtmlResponse, Response
from scrapy.utils.test import get_crawler

from city_scrapers.spiders.gra_the_rapid_bod import GraTheRapidBodSpider

FILES_DIR = join(dirname(__file__), "files")
FREEZE_DATE = "2026-11-17"
SOURCE = "https://www.ridetherapid.org/about-the-rapid/board-of-directors"
FILES_URL = "https://www.ridetherapid.org/sites/default/files/"

# First-page text of each packet, as extracted by pypdf from the real PDFs.
# Stored as text because the spider only reads page one and the full packets
# are up to 30 MB each; gra_the_rapid_bod_packet.pdf covers the PDF reading itself.
with open(join(FILES_DIR, "gra_the_rapid_bod_packets.json"), encoding="utf-8") as f:
    PACKET_TEXTS = json.load(f)


def _spider():
    crawler = get_crawler(GraTheRapidBodSpider)
    return GraTheRapidBodSpider.from_crawler(crawler)


def _page_response(html=None):
    if html is None:
        return file_response(join(FILES_DIR, "gra_the_rapid_bod.html"), url=SOURCE)
    return HtmlResponse(url=SOURCE, body=html.encode("utf-8"), encoding="utf-8")


def _crawl(spider, page=None, texts=PACKET_TEXTS):
    """Run the page and every packet request through the spider's callbacks."""
    spider._pdf_first_page_text = lambda body: texts[body.decode()]
    results = list(spider.parse(page or _page_response()))
    requests = [r for r in results if not isinstance(r, dict)]
    meetings = [r for r in results if isinstance(r, dict)]
    for request in requests:
        response = Response(url=request.url, body=request.url.encode())
        meetings.extend(request.callback(response, **request.cb_kwargs))
    return requests, meetings


def _find(meetings, start):
    start = datetime.strptime(start, "%Y-%m-%d %H:%M")
    found = [m for m in meetings if m["start"] == start]
    assert len(found) == 1, f"{len(found)} meetings at {start}"
    return found[0]


@pytest.fixture(scope="module")
def crawl():
    with freeze_time(FREEZE_DATE):
        spider = _spider()
        requests, meetings = _crawl(spider)
    return spider, requests, meetings


@pytest.fixture(scope="module")
def meetings(crawl):
    return crawl[2]


def test_requests(crawl):
    spider, requests, _ = crawl
    urls = [r.url for r in requests]
    assert len(urls) == len(set(urls)) == 43
    # Current packet linked above the member list
    assert FILES_URL + "2026-11/BOD%20Meeting%20Packet%2011-18-2026.pdf" in urls
    # Links before the 2-year lookback window aren't downloaded
    assert FILES_URL + "2025-07/bod-oct-23-final-packet-rev1%20%282%29.pdf" not in urls
    assert FILES_URL + "2025-07/bod-sep-25-final-packet.pdf" not in urls
    # November 2024 packets are listed under FY 2024 and FY 2025 but requested once
    assert urls.count(FILES_URL + "2025-07/nov-6-finance-final-packet.pdf") == 1


def test_count(meetings):
    assert len(meetings) == 49


def test_lookback(meetings):
    assert min(m["start"] for m in meetings) == datetime(2024, 12, 4, 16, 0)


def test_no_problems(crawl):
    assert crawl[0]._problems == []


def test_titles_and_classification(meetings):
    assert {(m["title"], m["classification"]) for m in meetings} == {
        ("Board of Directors", BOARD),
        ("Board Special Meeting", BOARD),
        ("Finance Committee", COMMITTEE),
        ("Future Planning & Innovation Committee", COMMITTEE),
        ("Present Performance & Service Committee", COMMITTEE),
    }


def test_board_meeting(meetings):
    item = _find(meetings, "2026-09-23 16:00")
    assert item["title"] == "Board of Directors"
    assert item["description"] == ""
    assert item["end"] is None
    assert item["all_day"] is False
    assert item["time_notes"] == ""
    assert item["status"] == PASSED
    assert item["source"] == SOURCE
    assert item["location"] == {
        "name": "Rapid Central Station Conference Room",
        "address": "250 Cesar E Chavez, SW, Grand Rapids, MI",
    }
    assert item["links"] == [
        {
            "href": FILES_URL + "2026-09/BOD%20Meeting%20Packet%209-23-2026.pdf",
            "title": "Meeting Packet",
        }
    ]
    assert item["id"] == "gra_the_rapid_bod/202609231600/x/board_of_directors"


def test_location_change(meetings):
    item = _find(meetings, "2025-10-22 16:00")
    assert item["location"] == {
        "name": "Rapid Operations Center",
        "address": "301 Bartlett Street SW, Grand Rapids, MI",
    }


def test_location_variants(meetings):
    # "Rapid Board Room (300 Ellsworth, SW)"
    assert _find(meetings, "2026-06-08 08:30")["location"] == {
        "name": "Ellsworth Board Room",
        "address": "300 Ellsworth, SW, Grand Rapids, MI",
    }
    # "Ellsworth Board Room | 300 Ellsworth, SW"
    assert _find(meetings, "2026-03-17 16:00")["location"] == {
        "name": "Ellsworth Board Room",
        "address": "300 Ellsworth, SW, Grand Rapids, MI",
    }


def test_special_meetings(meetings):
    special = sorted(
        m["start"] for m in meetings if m["title"] == "Board Special Meeting"
    )
    assert special == [
        # "BOARD RETREAT" in the packet title
        datetime(2025, 2, 26, 15, 0),
        # Packet title is the regular one; link text is "July 2025 Board
        # Budget Workshop"
        datetime(2025, 7, 23, 15, 0),
        datetime(2026, 2, 25, 15, 0),
        # "BOARD BUDGET WORKSHOP MEETING AGENDA"
        datetime(2026, 7, 22, 15, 0),
    ]


def test_committee_meeting(meetings):
    item = _find(meetings, "2026-02-09 08:30")
    assert item["title"] == "Future Planning & Innovation Committee"
    assert item["location"] == {
        "name": "Rapid Operations Center",
        "address": "335 Bartlett, SW, Grand Rapids, MI",
    }
    # "Planning & Technology Committee" in the November 2024 packet; its next
    # meeting (canceled) is in the same committee
    assert _find(meetings, "2025-01-06 08:30")["title"] == (
        "Future Planning & Innovation Committee"
    )


def test_packet_year_typo(meetings):
    # Packets say "Tuesday, January 14, 2024" and "Tuesday, May 20, 2024";
    # the links say "January 2025" and "May 2025"
    for start in ("2025-01-14 16:00", "2025-05-20 16:00"):
        item = _find(meetings, start)
        assert item["title"] == "Present Performance & Service Committee"
        assert item["links"]


def test_time_without_minutes(meetings):
    # "Tuesday, March 18, 2025 – 4 p.m."
    assert _find(meetings, "2025-03-18 16:00")["status"] == PASSED


def test_cancellations_dated_from_next_meeting(meetings):
    canceled = {(m["start"], m["title"]) for m in meetings if m["status"] == CANCELLED}
    assert canceled == {
        (datetime(2025, 1, 6, 8, 30), "Future Planning & Innovation Committee"),
        (datetime(2025, 7, 14, 8, 30), "Future Planning & Innovation Committee"),
        (datetime(2025, 7, 22, 16, 0), "Present Performance & Service Committee"),
        (datetime(2025, 11, 11, 16, 0), "Present Performance & Service Committee"),
        (datetime(2026, 6, 10, 16, 0), "Finance Committee"),
        (datetime(2026, 7, 21, 16, 0), "Present Performance & Service Committee"),
    }
    item = _find(meetings, "2026-06-10 16:00")
    assert item["links"] == []
    assert item["location"]["name"] == "Rapid Central Station Conference Room"


def test_undatable_cancellations_skipped(meetings):
    def months(title):
        return {
            (m["start"].year, m["start"].month) for m in meetings if m["title"] == title
        }

    # August 2026 follows the canceled June meeting, so no packet gives its day
    assert (2026, 8) not in months("Finance Committee")
    assert (2025, 9) not in months("Future Planning & Innovation Committee")
    assert (2025, 11) not in months("Future Planning & Innovation Committee")


def test_next_meeting_from_packet(meetings):
    # From "Next meeting: November 10, 2026" in the September 2026 packet
    item = _find(meetings, "2026-11-10 16:00")
    assert item["title"] == "Present Performance & Service Committee"
    assert item["status"] == PASSED
    assert item["links"] == []
    assert item["time_notes"] == ""


def test_next_meeting_tbd_skipped(meetings):
    planning = [
        m["start"]
        for m in meetings
        if m["title"] == "Future Planning & Innovation Committee"
    ]
    assert max(planning) == datetime(2026, 10, 12, 8, 30)


def test_current_board_packet(meetings):
    item = _find(meetings, "2026-11-18 16:00")
    assert item["status"] == TENTATIVE
    assert item["time_notes"] == ""
    assert item["links"] == [
        {
            "href": FILES_URL + "2026-11/BOD%20Meeting%20Packet%2011-18-2026.pdf",
            "title": "Meeting Packet",
        }
    ]


def test_board_date_list(meetings):
    # "December 16 (Election of Officers)": upcoming, no packet yet
    item = _find(meetings, "2026-12-16 16:00")
    assert item["title"] == "Board of Directors"
    assert item["status"] == TENTATIVE
    assert item["links"] == []
    assert item["time_notes"] == ""
    assert item["location"]["name"] == "Rapid Central Station Conference Room"
    # "October 28": past, no packet posted and not marked canceled
    item = _find(meetings, "2026-10-28 16:00")
    assert item["status"] == PASSED
    assert item["links"] == []


def test_packet_wins_over_date_list(meetings):
    # "February 25 (Board Meeting/Retreat)" is in the list at the default
    # 4:00 p.m.; the packet says 3:00 p.m.
    feb = [m for m in meetings if m["start"].date() == datetime(2026, 2, 25).date()]
    assert len(feb) == 1
    assert feb[0]["start"].time() == time(15, 0)
    assert feb[0]["links"]


def _modified_page(old, new):
    with open(join(FILES_DIR, "gra_the_rapid_bod.html"), encoding="utf-8") as f:
        html = f.read()
    assert old in html
    return _page_response(html.replace(old, new))


@freeze_time(FREEZE_DATE)
def test_date_list_year_from_heading():
    spider = _spider()
    page = _modified_page("2026 Meeting Dates", "2027 Meeting Dates")
    _, meetings = _crawl(spider, page)
    item = _find(meetings, "2027-01-28 16:00")
    assert item["status"] == TENTATIVE
    assert _find(meetings, "2027-07-22 16:00")["title"] == "Board Special Meeting"


@freeze_time(FREEZE_DATE)
def test_canceled_board_month_dated_from_list():
    spider = _spider()
    page = _modified_page(
        ">September 2026</a></p>",
        ">September 2026</a></p><p>October 2026 - CANCELED</p>",
    )
    _, meetings = _crawl(spider, page)
    assert _find(meetings, "2026-10-28 16:00")["status"] == CANCELLED


@freeze_time(FREEZE_DATE)
def test_missing_sections_reported():
    spider = _spider()
    page = _page_response("<html><body><p>Nothing here</p></body></html>")
    errors = []

    # Signal receivers are weak references, so keep a named one alive
    def on_error(failure, **kwargs):
        errors.append(failure.value)

    spider.crawler.signals.connect(on_error, signal=signals.spider_error)
    requests, meetings = _crawl(spider, page)
    assert requests == [] and meetings == []
    spider._on_spider_closed(spider, "finished")
    assert len(errors) == 1
    message = str(errors[0])
    assert "Meeting Dates" in message
    assert "FY <year> Board Meeting Packets" in message
    assert "0 meetings parsed" in message


def test_pdf_first_page():
    spider = _spider()
    with open(join(FILES_DIR, "gra_the_rapid_bod_packet.pdf"), "rb") as f:
        text = spider._pdf_first_page_text(f.read())
    entry = {"body": "board", "url": "x", "year": 2025, "month": 10, "label": ""}
    packet = spider._parse_packet_text(text, entry)
    assert packet["date"] == datetime(2025, 10, 22).date()
    assert packet["time"] == time(16, 0)
    assert packet["title"] == "BOARD OF DIRECTORS MEETING AGENDA"
    assert packet["location"]["name"] == "Rapid Operations Center"


@pytest.mark.parametrize(
    "text,expected_date,expected_time",
    [
        (
            "MINUTES REVIEW – September 24, 2025\nFINANCE COMMITTEE MEETING\n"
            "Wednesday, November 5, 2025 – 4:00 p.m.\nRoom (1 Main St)",
            "2025-11-05",
            time(16, 0),
        ),
        (
            "FINANCE COMMITTEE MEETING\nNovember 6, 2025 – 4:00 p.m.\nRoom (1 Main St)",
            "2025-11-06",
            time(16, 0),
        ),
        (
            "BOARD OF DIRECTORS MEETING AGENDA\nWednesday November 18, 2025 – 4 pm\n"
            "Room (1 Main St)",
            "2025-11-18",
            time(16, 0),
        ),
        (
            "COMMITTEE MEETING\nMonday, March 10, 2025 — 8:30 a.m.\nRoom (1 Main St)",
            "2025-03-10",
            time(8, 30),
        ),
    ],
)
def test_packet_date_formats(text, expected_date, expected_time):
    spider = _spider()
    entry = {"body": "finance", "url": "x", "year": 2025, "month": 11, "label": ""}
    packet = spider._parse_packet_text(text, entry)
    assert packet["date"].isoformat() == expected_date
    assert packet["time"] == expected_time
    assert packet["location"] == {
        "name": "Room",
        "address": "1 Main St, Grand Rapids, MI",
    }


def test_packet_without_date():
    spider = _spider()
    entry = {"body": "finance", "url": "x", "year": 2025, "month": 11, "label": ""}
    assert (
        spider._parse_packet_text("MINUTES REVIEW – September 24, 2025", entry) is None
    )


@pytest.mark.parametrize(
    "utc_now,expected",
    [
        # 3:30 p.m. in Grand Rapids (EST, UTC-5): server's UTC clock is past 4:00
        ("2026-11-18 20:30", TENTATIVE),
        # 4:30 p.m. in Grand Rapids
        ("2026-11-18 21:30", PASSED),
    ],
)
def test_status_uses_local_time(utc_now, expected):
    with freeze_time(utc_now):
        spider = _spider()
        item = {"title": "Board of Directors", "start": datetime(2026, 11, 18, 16)}
        assert spider._get_status(item) == expected


def test_cutoff_uses_local_date():
    # 11:30 p.m. Nov 17 in Grand Rapids is already Nov 18 in UTC
    with freeze_time("2026-11-18 04:30"):
        assert _spider().cutoff_date == datetime(2024, 11, 17).date()
