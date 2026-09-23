import logging
from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD, CANCELLED, PASSED, TENTATIVE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.gra_library_commissioners import (
    GraLibraryCommissionersSpider,
)

SOURCE_URL = "https://www.grpl.org/about/board-of-library-commissioners/"
FIXTURE_PATH = join(dirname(__file__), "files", "gra_library_commissioners.html")

REGULAR_TIME_NOTES = (
    "The BoLC meet on the last Tuesday of each month at 5:15 pm at the Main Library "
    "(111 Library St NE), in the Board Room on Level 5, unless otherwise specified (*)."
)
ASTERISK_NOTE = "Please check the meeting attachment for start time details"


@pytest.fixture(scope="module")
def parsed_items():
    test_response = file_response(FIXTURE_PATH, url=SOURCE_URL)
    spider = GraLibraryCommissionersSpider()
    with freeze_time("2026-09-21"):
        return [item for item in spider.parse(test_response)]


@pytest.fixture(scope="module")
def fixture_html():
    with open(FIXTURE_PATH, encoding="utf-8") as fixture:
        return fixture.read()


def meeting_on(parsed_items, start, starred=None):
    """The meeting listed on `start`. Four dates carry two meetings, so `starred`
    picks the special one from the regular one."""
    matches = [item for item in parsed_items if item["start"] == start]
    if starred is not None:
        matches = [
            item
            for item in matches
            if item["time_notes"].endswith(ASTERISK_NOTE) is starred
        ]
    assert len(matches) == 1
    return matches[0]


@pytest.fixture(scope="module")
def first_meeting(parsed_items):
    # earliest listed meeting, carrying both minutes and a packet
    return parsed_items[0]


@pytest.fixture(scope="module")
def cancelled_meeting(parsed_items):
    return meeting_on(parsed_items, datetime(2026, 5, 26, 17, 15))


@pytest.fixture(scope="module")
def upcoming_meeting(parsed_items):
    # the only future meeting whose agenda has been posted
    return meeting_on(parsed_items, datetime(2026, 9, 29, 17, 15))


def test_count(parsed_items):
    assert len(parsed_items) == 53


def test_title(first_meeting):
    assert first_meeting["title"] == "Board of Library Commissioners"


def test_description(first_meeting):
    assert first_meeting["description"] == ""


def test_classification(first_meeting):
    assert first_meeting["classification"] == BOARD


def test_start(first_meeting):
    """Date comes from the listing, time from the "Board Meetings" prose."""
    assert first_meeting["start"] == datetime(2026, 2, 3, 17, 15)


def test_start_time_applied(parsed_items):
    """The one time stated in the prose is applied to every meeting."""
    assert all(
        item["start"].hour == 17 and item["start"].minute == 15 for item in parsed_items
    )


def test_end(first_meeting):
    assert first_meeting["end"] is None


def test_all_day(parsed_items):
    assert all(item["all_day"] is False for item in parsed_items)


def test_time_notes(first_meeting):
    assert first_meeting["time_notes"] == REGULAR_TIME_NOTES


def test_time_notes_asterisk(parsed_items):
    """Dates marked with an asterisk get an extra note appended."""
    starred = meeting_on(parsed_items, datetime(2026, 4, 28, 17, 15), starred=True)
    assert starred["time_notes"] == f"{REGULAR_TIME_NOTES} {ASTERISK_NOTE}"


def test_time_notes_asterisk_outside_link(parsed_items):
    """The asterisk is sometimes outside the date hyperlink."""
    starred = meeting_on(parsed_items, datetime(2023, 4, 25, 17, 15), starred=True)
    assert starred["time_notes"].endswith(ASTERISK_NOTE)


def test_location(first_meeting):
    assert first_meeting["location"] == {
        "name": "Main Library, Board Room (Level 5)",
        "address": "111 Library St NE, Grand Rapids, MI 49503",
    }


def test_source(first_meeting):
    assert first_meeting["source"] == SOURCE_URL


def test_id(first_meeting):
    assert (
        first_meeting["id"]
        == "gra_library_commissioners/202602031715/x/board_of_library_commissioners"
    )


def test_ids_unique(parsed_items):
    """Meetings sharing a date must not collapse onto one ID."""
    ids = [item["id"] for item in parsed_items]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "start", [datetime(2023, 4, 25, 17, 15), datetime(2024, 4, 30, 17, 15)]
)
def test_id_special_meeting(parsed_items, start):
    """A regular and a special meeting are listed on the same date four times
    over. The starred row of the pair is the special meeting."""
    stamp = start.strftime("%Y%m%d%H%M")
    special = meeting_on(parsed_items, start, starred=True)
    regular = meeting_on(parsed_items, start, starred=False)

    assert special["id"] == (
        f"gra_library_commissioners/{stamp}/special/board_of_library_commissioners"
    )
    assert regular["id"] == (
        f"gra_library_commissioners/{stamp}/x/board_of_library_commissioners"
    )


def test_id_lone_asterisk_not_special(parsed_items):
    """An asterisk on a date with no twin marks a meeting held off the usual
    last-Tuesday schedule, not a special meeting, so the ID stays unqualified."""
    lone = meeting_on(parsed_items, datetime(2025, 10, 21, 17, 15))
    assert lone["time_notes"].endswith(ASTERISK_NOTE)
    assert lone["id"] == (
        "gra_library_commissioners/202510211715/x/board_of_library_commissioners"
    )


def test_status(first_meeting):
    assert first_meeting["status"] == PASSED


def test_status_cancelled(cancelled_meeting):
    assert cancelled_meeting["status"] == CANCELLED


def test_status_tentative(upcoming_meeting):
    assert upcoming_meeting["status"] == TENTATIVE


def test_links(first_meeting):
    """The date links to its attachment, labelled from the file name."""
    assert first_meeting["links"] == [
        {
            "href": "https://cdn-web-main.bibliocms.com/wp-content/uploads/sites/124/2026/04/02-2026-02-03-bolc-minutes-approved-compliant-1.pdf",  # noqa
            "title": "Minutes",
        },
        {
            "href": "https://drive.google.com/file/d/121uSFn8-w5hJg_TNQ0wm6mQfEq36LHhe/view?usp=drive_link",  # noqa
            "title": "Packet",
        },
    ]


def test_links_agenda(upcoming_meeting):
    """A date pointing at an agenda file is labelled "Agenda", not "Minutes"."""
    assert upcoming_meeting["links"] == [
        {
            "href": "https://cdn-web-main.bibliocms.com/wp-content/uploads/sites/124/2026/09/2026-09-29_bolc-agenda_compliant.pdf",  # noqa
            "title": "Agenda",
        },
    ]


def test_links_empty(parsed_items, cancelled_meeting):
    """Cancelled meetings and unlinked "Packet" labels have no attachments."""
    unlinked = meeting_on(parsed_items, datetime(2026, 10, 20, 17, 15))
    assert cancelled_meeting["links"] == []
    assert unlinked["links"] == []


@pytest.mark.parametrize("degradation", ["empty", "truncated"])
def test_warns_when_listing_yields_nothing(degradation, fixture_html, tmp_path, caplog):
    """A page the spider can't read must not be indistinguishable from a page
    with no meetings on it, so it has to say something."""
    body = "" if degradation == "empty" else fixture_html[:10000]
    degraded = tmp_path / "degraded.html"
    degraded.write_text(body)
    response = file_response(str(degraded), url=SOURCE_URL)

    with caplog.at_level(logging.WARNING):
        items = list(GraLibraryCommissionersSpider().parse(response))

    assert items == []
    assert caplog.records, "parsed nothing and reported nothing"
