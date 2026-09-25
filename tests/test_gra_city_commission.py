from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import COMMISSION
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.gra_city import GraCityCommissionSpider

html_response = file_response(
    join(dirname(__file__), "files", "gra_city_commission.html"),
    url="https://events.grandrapidsmi.gov/meetings/Index?action=search&StartDate=01/01/26&EndDate=03/23/27&Keywords=City-Commission-Meeting",  # noqa
)

attachments_response = file_response(
    join(dirname(__file__), "files", "gra_city_commission.json"),
    url="https://grandrapidscity.primegov.com/api/v2/PublicPortal/ListArchivedMeetingsByCommitteeId?year=2026&committeeId=1",  # noqa
)


@pytest.fixture
def commission_items():
    spider = GraCityCommissionSpider()
    spider.attachments = attachments_response.json()
    with freeze_time("2026-09-24"):
        return [item for item in spider._parse_events(html_response)]


def test_count(commission_items):
    assert len(commission_items) == 25


def test_title(commission_items):
    assert commission_items[0]["title"] == "City Commission Meeting"


def test_description(commission_items):
    assert commission_items[0]["description"] == ""


def test_start(commission_items):
    assert commission_items[0]["start"] == datetime(2026, 1, 13, 14, 0)


def test_end(commission_items):
    assert commission_items[0]["end"] is None


def test_time_notes(commission_items):
    assert commission_items[0]["time_notes"] == ""


def test_id(commission_items):
    assert (
        commission_items[0]["id"]
        == "gra_city_commission/202601131400/x/city_commission_meeting"
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
        == "https://events.grandrapidsmi.gov/meetings/Detail/2026-01-13-1400-City-Commission-Meeting"  # noqa
    )


def test_links(commission_items):
    assert commission_items[0]["links"] == [
        {
            "href": "https://www.grandrapidsmi.gov/government/public-notices/",
            "title": "Meeting cancellations and other public notices can be found on this page",  # noqa
        },
        {
            "href": "https://grandrapidsmi.new.swagit.com/videos/371916",
            "title": "Video",
        },
        {
            "href": "https://grandrapidscity.primegov.com/Public/CompiledDocument?meetingTemplateId=30218&compileOutputType=1",  # noqa
            "title": "Agenda",
        },
        {
            "href": "https://grandrapidscity.primegov.com/Public/CompiledDocument?meetingTemplateId=30220&compileOutputType=1",  # noqa
            "title": "Packet",
        },
        {
            "href": "https://grandrapidscity.primegov.com/Public/CompiledDocument?meetingTemplateId=30219&compileOutputType=1",  # noqa
            "title": "Official Proceedings",
        },
    ]


def test_classification(commission_items):
    assert commission_items[0]["classification"] == COMMISSION
