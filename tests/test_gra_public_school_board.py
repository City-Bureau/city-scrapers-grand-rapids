import json
from datetime import date, datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD, PASSED, TENTATIVE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time
from scrapy.http import TextResponse
from scrapy.utils.test import get_crawler

from city_scrapers.spiders.gra_public_school_board import GraPublicSchoolBoardSpider

FILES_DIR = join(dirname(__file__), "files")
FREEZE_DATE = "2026-09-24"

PLAYLIST_LINK = {
    "href": "https://www.youtube.com/playlist?list=PL-TX6krcrZxZuKvEyOxDXB_Jy1CriraLl",  # noqa
    "title": "YouTube channel",
}

AUG_10_VIDEO_LINKS = [
    {"href": "https://www.youtube.com/watch?v=Uh-TjTCW3cU", "title": "Video"},
    {
        "href": "https://www.youtube.com/watch?v=YXGHXMpnx8c",
        "title": "Video (Español)",
    },
]


def _spider(api_key=None):
    crawler = get_crawler(GraPublicSchoolBoardSpider, {"YOUTUBE_API_KEY": api_key})
    return GraPublicSchoolBoardSpider.from_crawler(crawler)


@pytest.fixture
def spider():
    return _spider()


@pytest.fixture
def foxbright_response():
    return file_response(
        join(FILES_DIR, "gra_public_school_board_foxbright.html"),
        url="https://grps.org/Core/FoxbrightCalendars/Agenda/144574/",
    )


@pytest.fixture
def youtube_response():
    return file_response(
        join(FILES_DIR, "gra_public_school_board_youtube.json"),
        url="https://www.googleapis.com/youtube/v3/playlistItems",
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
        return file_response(
            path,
            url="https://go.boarddocs.com/mi/grand/Board.nsf/BD-GetMeeting?open",
        )
    except FileNotFoundError:
        return None


@pytest.fixture
def parsed_items(spider, foxbright_response, youtube_response, boarddocs_list_response):
    """
    Drives the spider's callback chain directly against fixture files. Detail
    fixtures are optional here: any BoardDocs meeting whose detail page hasn't
    been captured yet simply won't have its attachment link matched, but every
    Foxbright event still becomes a Meeting (see test_links_placeholder below
    for why link-matching assertions are separated out).
    """
    spider._video_map = {}
    with freeze_time(FREEZE_DATE):
        list(spider._parse_foxbright_all(foxbright_response))
        list(spider._parse_youtube_videos(youtube_response))
        detail_requests = list(spider._parse_boarddocs_list(boarddocs_list_response))

        for req in detail_requests:
            numberdate = req.cb_kwargs["numberdate"]
            detail_response = _detail_response_for(numberdate)
            if detail_response is not None:
                list(spider._parse_boarddocs_detail(detail_response, **req.cb_kwargs))
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


def test_links_attachment_without_video(parsed_item):
    # Jul 1 Work Session matches BoardDocs meeting DVDHLR490E4B (numberdate
    # 20260701) but has no recording in the YouTube playlist.
    assert parsed_item["links"] == [
        {
            "href": "https://go.boarddocs.com/mi/grand/Board.nsf/goto?open&id=DVDHLR490E4B",  # noqa
            "title": "Meeting Attachments",
        },
    ]


def _meeting_at(parsed_items, start):
    return next(m for m in parsed_items if m["start"] == start)


def test_links_video_english_and_spanish(parsed_items):
    meeting = _meeting_at(parsed_items, datetime(2026, 8, 10, 18, 30))
    assert meeting["title"] == "Board of Education Regular Meeting"
    assert meeting["links"] == AUG_10_VIDEO_LINKS


def test_links_video_two_digit_year_title(parsed_items):
    # Video is titled "Board of Education Meeting 7-13-26"
    meeting = _meeting_at(parsed_items, datetime(2026, 7, 13, 18, 30))
    assert meeting["links"] == [
        {"href": "https://www.youtube.com/watch?v=I90hU8wFrl8", "title": "Video"}
    ]


def test_links_no_video_for_committee_on_same_date(parsed_items):
    # The Ad Hoc Facilities Committee meets earlier the same evening as the
    # Regular Meeting, but the recording belongs to the Regular Meeting.
    meeting = _meeting_at(parsed_items, datetime(2026, 8, 10, 17, 0))
    assert "Committee" in meeting["title"]
    assert meeting["links"] == []


def test_links_playlist_for_upcoming_meeting(parsed_items):
    # No recording yet, so the tentative meeting points to the playlist
    meeting = _meeting_at(parsed_items, datetime(2026, 10, 12, 18, 30))
    assert meeting["status"] == TENTATIVE
    assert meeting["links"] == [PLAYLIST_LINK]


def test_links_playlist_for_upcoming_committee_meeting(parsed_items):
    meeting = _meeting_at(parsed_items, datetime(2026, 10, 13, 17, 0))
    assert "Committee" in meeting["title"]
    assert meeting["status"] == TENTATIVE
    assert meeting["links"] == [PLAYLIST_LINK]


def test_links_tentative_meeting_prefers_own_video(parsed_items, spider):
    # A recording posted for a still-upcoming meeting replaces the playlist link
    spider._video_map[(date(2026, 10, 12), "regular")] = {
        "en": "https://www.youtube.com/watch?v=upcoming"
    }
    with freeze_time(FREEZE_DATE):
        meetings = list(spider._parse_all_meetings())
    meeting = _meeting_at(meetings, datetime(2026, 10, 12, 18, 30))
    assert meeting["status"] == TENTATIVE
    assert meeting["links"] == [
        {"href": "https://www.youtube.com/watch?v=upcoming", "title": "Video"}
    ]


def test_video_map_skips_old_and_undated_videos(spider, youtube_response):
    spider._video_map = {}
    with freeze_time(FREEZE_DATE):
        list(spider._parse_youtube_videos(youtube_response))
    # Cutoff is 2026-06-23: Jun 8 and earlier are dropped, as is "Private video"
    assert sorted(d.isoformat() for d, _ in spider._video_map) == [
        "2026-07-13",
        "2026-08-10",
        "2026-09-14",
    ]


def test_youtube_skipped_without_api_key(spider):
    requests = list(spider._request_youtube_videos())
    assert len(requests) == 1
    assert "boarddocs.com" in requests[0].url


def test_cancelled_meeting(parsed_items):
    from city_scrapers_core.constants import CANCELLED

    meeting = next(m for m in parsed_items if "Policy Committee Meeting" in m["title"])
    assert meeting["status"] == CANCELLED
    # Foxbright's title text keeps the "Canceled --" prefix; the
    assert (
        meeting["title"] == "Canceled -- Board of Education Policy Committee Meeting"
    )  # noqa
    assert meeting["classification"] == "Committee"
    assert meeting["links"] == []
    assert meeting["start"] == datetime(2026, 9, 23, 16, 30)


def test_classification_board(parsed_item):
    assert parsed_item["classification"] == BOARD


def test_classification_committee(parsed_items):
    committee_items = [m for m in parsed_items if "committee" in m["title"].lower()]
    assert len(committee_items) == 14
    assert all(m["classification"] == "Committee" for m in committee_items)


def test_all_day(parsed_item):
    assert parsed_item["all_day"] is False


# Add test for location_name_from_description
@pytest.mark.parametrize(
    "title,start,expected_name",
    [
        (
            "Board of Education Regular Meeting",
            datetime(2026, 7, 13, 18, 30),
            "Auditorium",
        ),
        (
            "Canceled -- Board of Education Policy Committee Meeting",
            datetime(2026, 9, 23, 16, 30),
            "Library Building, Room 112",
        ),
    ],
    ids=["auditorium_with_links", "room_no_links"],
)
def test_location_name_from_description(parsed_items, title, start, expected_name):
    meeting = next(
        m for m in parsed_items if m["title"] == title and m["start"] == start
    )
    assert meeting["location"] == {
        "name": expected_name,
        "address": "1331 M.L.K. Jr St SE, Grand Rapids, MI 49506, USA",
    }


@pytest.mark.parametrize(
    "titles,expects_next_page",
    [
        (["BOE Meeting 9/14/2026", "BOE Meeting 8/10/2026"], True),
        (["BOE Meeting 9/14/2026", "BOE Meeting 1/12/2026"], False),
        (["BOE Meeting 1/12/2026"], False),
    ],
    ids=["all_recent_keeps_paging", "reaches_cutoff_stops", "all_old_stops"],
)
def test_youtube_paging(titles, expects_next_page):
    spider = _spider("test-key")
    body = json.dumps(
        {
            "nextPageToken": "PAGE2",
            "items": [
                {"snippet": {"title": title, "resourceId": {"videoId": "x"}}}
                for title in titles
            ],
        }
    )
    response = TextResponse(
        url="https://www.googleapis.com/youtube/v3/playlistItems",
        body=body,
        encoding="utf-8",
    )
    spider._video_map = {}
    with freeze_time(FREEZE_DATE):
        requests = list(spider._parse_youtube_videos(response))
    assert len(requests) == 1
    assert ("pageToken=PAGE2" in requests[0].url) is expects_next_page


def test_links_committee_video_matches_committee_name(parsed_items, spider):
    # Two committees meet on Oct 13; a Facilities recording belongs only to
    # the Facilities committee
    spider._video_map[(date(2026, 10, 13), "committee:facilities")] = {
        "en": "https://www.youtube.com/watch?v=facilities"
    }
    with freeze_time(FREEZE_DATE):
        meetings = list(spider._parse_all_meetings())
    facilities = _meeting_at(meetings, datetime(2026, 10, 13, 17, 0))
    liaison = _meeting_at(meetings, datetime(2026, 10, 13, 16, 0))
    assert "Facilities" in facilities["title"]
    assert facilities["links"] == [
        {"href": "https://www.youtube.com/watch?v=facilities", "title": "Video"}
    ]
    assert "Liaison" in liaison["title"]
    assert liaison["links"] == [PLAYLIST_LINK]


@pytest.mark.parametrize(
    "title,expected",
    [
        ("BOE Meeting 9/14/2026 Español", date(2026, 9, 14)),
        ("Board of Education Meeting 7-13-26", date(2026, 7, 13)),
        ("GRPS Finance Committee Meeting 03 24 25", date(2025, 3, 24)),
        ("GRPS Board Meeting Dec 8, 2025 Spanish", date(2025, 12, 8)),
        ("GRPS Board Meeting October 13 2025 Spanish", date(2025, 10, 13)),
        ("GRPS Finance Committee Meeting November, 26 2024", date(2024, 11, 26)),
        (
            "GRPS Board of Education Meeting -- January 8. 2024 (en español)",
            date(2024, 1, 8),
        ),
        ("July 23, 2024 Finance Committee Meeting", date(2024, 7, 23)),
        ("Private video", None),
        ("BOE Meeting 13/45/2026", None),
    ],
)
def test_parse_video_date(spider, title, expected):
    assert spider._parse_video_date(title) == expected


@pytest.mark.parametrize(
    "title,expected",
    [
        ("BOE Meeting 9/14/2026", "regular"),
        ("Board of Education Regular Meeting", "regular"),
        ("Board of Education Work Session", "work session"),
        ("Board of Education Special Work Session", "work session"),
        ("Board of Education Special Meeting", "special"),
        ("Board of Education Finance Committee Meeting", "committee:finance"),
        ("GRPS Finance Committe Meeting Feb 24, 2025", "committee:finance"),
        (
            "Board of Education Ad Hoc Facilities Committee Meeting",
            "committee:facilities",
        ),
        (
            "Canceled -- Board of Education Policy Committee Meeting",
            "committee:policy",
        ),
    ],
)
def test_meeting_kind(spider, title, expected):
    assert spider._meeting_kind(title) == expected
