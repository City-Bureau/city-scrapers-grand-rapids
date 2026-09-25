from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import COMMISSION
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.gra_city import GraCityCommissionSpider

html_response = file_response(
    join(dirname(__file__), "files", "gra_mobile_gr.html"),
    url="https://events.grandrapidsmi.gov/meetings/Index?action=search&StartDate=09/24/24&EndDate=03/24/27&Keywords=Mobile-GR-Commission",  # noqa
)

attachments_response = file_response(
    join(dirname(__file__), "files", "gra_mobile_gr.json"),
    url="https://grandrapidscity.primegov.com/api/v2/PublicPortal/ListArchivedMeetingsByCommitteeId?year=2026&committeeId=15",  # noqa
)


@pytest.fixture
def commission_items():
    spider = GraCityCommissionSpider()
    spider.attachments = attachments_response.json()
    with freeze_time("2026-09-24"):
        return [item for item in spider._parse_events(html_response)]


def test_count(commission_items):
    assert len(commission_items) == 12


def test_title(commission_items):
    assert commission_items[0]["title"] == "Mobile GR Commission Meeting"


def test_description(commission_items):
    assert commission_items[0]["description"] == ""


def test_start(commission_items):
    assert commission_items[0]["start"] == datetime(2025, 2, 6, 12, 0)


def test_end(commission_items):
    assert commission_items[0]["end"] is None


def test_time_notes(commission_items):
    assert commission_items[0]["time_notes"] == ""


def test_id(commission_items):
    assert (
        commission_items[0]["id"]
        == "gra_city_commission/202502061200/x/mobile_gr_commission_meeting"
    )


def test_status(commission_items):
    assert commission_items[0]["status"] == "passed"


def test_location(commission_items):
    assert commission_items[0]["location"] == {
        "name": "City of Grand Rapids - City Hall",
        "address": "300 Monroe Ave NW, Grand Rapids, MI 49503",
    }


def test_source(commission_items):
    assert (
        commission_items[0]["source"]
        == "https://events.grandrapidsmi.gov/meetings/Detail/2025-02-06-1200-Mobile-GR-Commission-Meeting"  # noqa
    )


def test_links(commission_items):
    assert commission_items[0]["links"] == [
        {
            "href": "https://www.grandrapidsmi.gov/government/public-notices/",
            "title": "Meeting cancellations and other public notices can be found on this page",  # noqa
        },
        {
            "href": "https://www.youtube.com/@TheCityofGrandRapids",
            "title": "YouTube channel",
        },
    ]


def test_classification(commission_items):
    assert commission_items[0]["classification"] == COMMISSION
