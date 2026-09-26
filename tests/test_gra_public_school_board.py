from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD, PASSED
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.gra_public_school_board import GraPublicSchoolBoardSpider

FILES_DIR = join(dirname(__file__), "files")
FREEZE_DATE = "2026-09-24"

VIDEO_LINK = {
    "href": "http://youtube.com/playlist?list=PL-TX6krcrZxZuKvEyOxDXB_Jy1CriraLl",
    "title": "Video",
}


@pytest.fixture
def spider():
    return GraPublicSchoolBoardSpider()


@pytest.fixture
def foxbright_response():
    return file_response(
        join(FILES_DIR, "gra_public_school_board_foxbright.html"),
        url="https://grps.org/Core/FoxbrightCalendars/Agenda/144574/",
    )


@pytest.fixture
def boarddocs_list_response():
    return file_response(
        join(FILES_DIR, "gra_public_school_board_boarddocs_list.json"),
        url="https://go.boarddocs.com/mi/grand/Board.nsf/BD-GetMeetingsList?open",
    )


def _detail_response_for(numberdate):
    """
    Loads a captured BoardDocs detail fixture matching `numberdate`, if present.
    Detail fixtures are named by numberdate (see capture_fixtures.py) and are
    what let a meeting pick up its "Meeting Attachments" link.
    """
    path = join(FILES_DIR, f"gra_public_school_board_detail_{numberdate}.html")
    try:
        response = file_response(
            path,
            url="https://go.boarddocs.com/mi/grand/Board.nsf/BD-GetMeeting?open",
        )
        response.meta["numberdate"] = numberdate
        return response
    except FileNotFoundError:
        return None


@pytest.fixture
def parsed_items(spider, foxbright_response, boarddocs_list_response):
    """
    Drives the spider's callback chain directly against fixture files. Detail
    fixtures are optional here: any BoardDocs meeting whose detail page hasn't
    been captured yet simply won't have its attachment link matched, but every
    Foxbright event still becomes a Meeting (see test_links_placeholder below
    for why link-matching assertions are separated out).
    """
    with freeze_time(FREEZE_DATE):
        list(spider._parse_foxbright_all(foxbright_response))
        detail_requests = list(spider._parse_boarddocs_list(boarddocs_list_response))

        for req in detail_requests:
            numberdate = req.meta["numberdate"]
            detail_response = _detail_response_for(numberdate)
            if detail_response is not None:
                list(spider._parse_boarddocs_detail(detail_response))
            else:
                spider._pending_boarddocs -= 1

        if spider._pending_boarddocs <= 0:
            return list(spider._parse_all_meetings())
        return []


@pytest.fixture
def parsed_item(parsed_items):
    # First Foxbright event: Jul 1, 2026 Board of Education Work Session
    return parsed_items[0]


def test_count(parsed_items):
    # Verified by running the spider against the real captured Foxbright fixture:
    # July 2026 - Dec 2026 contains 32 events on/after the CUTOFF_DATE.
    assert len(parsed_items) == 32


def test_title(parsed_item):
    assert parsed_item["title"] == "Board of Education Work Session"


def test_description(parsed_item):
    assert parsed_item["description"] == ""


def test_start(parsed_item):
    assert parsed_item["start"] == datetime(2026, 7, 1, 18, 30)


def test_end(parsed_item):
    assert parsed_item["end"] == datetime(2026, 7, 1, 19, 30)


def test_time_notes(parsed_item):
    assert parsed_item["time_notes"] == ""


def test_id(parsed_item):
    assert (
        parsed_item["id"]
        == "gra_public_school_board/202607011830/x/board_of_education_work_session"
    )


def test_status(parsed_item):
    # Frozen "today" is 2026-09-24, so the Jul 1 meeting is in the past
    assert parsed_item["status"] == PASSED


def test_location(parsed_item):
    assert parsed_item["location"] == {
        "name": "",
        "address": "1331 M.L.K. Jr St SE, Grand Rapids, MI 49506, USA",
    }


def test_source(parsed_item):
    assert (
        parsed_item["source"]
        == "https://grps.org/our-district/board-of-education/board-meeting-schedule/"
    )


def test_links_both_attachment_and_video(parsed_item):
    # Jul 1 Work Session matches BoardDocs meeting DVDHLR490E4B (numberdate
    # 20260701), so it should carry both the attachment link and the video link.
    assert parsed_item["links"] == [
        {
            "href": "https://go.boarddocs.com/mi/grand/Board.nsf/goto?open&id=DVDHLR490E4B",  # noqa
            "title": "Meeting Attachments",
        },
        VIDEO_LINK,
    ]


def test_links_video_only_when_no_boarddocs_match(parsed_items):
    # Committee meetings (Ad Hoc Facilities, Finance, etc.) have no matching
    # BoardDocs entry, so they should only carry the video link.
    meeting = next(
        m
        for m in parsed_items
        if m["title"] == "Board of Education Ad Hoc Facilities Committee Meeting"
        and m["start"] == datetime(2026, 7, 13, 17, 0)
    )
    assert meeting["links"] == [VIDEO_LINK]


def test_cancelled_meeting(parsed_items):
    from city_scrapers_core.constants import CANCELLED

    meeting = next(m for m in parsed_items if "Policy Committee Meeting" in m["title"])
    assert meeting["status"] == CANCELLED
    # Foxbright's title text keeps the "Canceled --" prefix; the
    assert (
        meeting["title"] == "Canceled -- Board of Education Policy Committee Meeting"
    )  # noqa
    assert meeting["classification"] == "Committee"
    assert meeting["links"] == [VIDEO_LINK]
    assert meeting["start"] == datetime(2026, 9, 23, 16, 30)


def test_classification_board(parsed_item):
    assert parsed_item["classification"] == BOARD


def test_classification_committee(parsed_items):
    committee_items = [m for m in parsed_items if "committee" in m["title"].lower()]
    assert len(committee_items) == 14
    assert all(m["classification"] == "Committee" for m in committee_items)


def test_all_day(parsed_item):
    assert parsed_item["all_day"] is False
