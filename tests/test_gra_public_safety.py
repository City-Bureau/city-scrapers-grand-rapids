from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import COMMITTEE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.gra_city import GraPublicSafetySpider

html_response = file_response(
    join(dirname(__file__), "files", "gra_public_safety.html"),
    url="https://events.grandrapidsmi.gov/meetings/Index?action=search&StartDate=09/24/24&EndDate=03/24/27&Keywords=Public-Safety-Committee",  # noqa
)

attachments_response = file_response(
    join(dirname(__file__), "files", "gra_public_safety.json"),
    url="https://grandrapidscity.primegov.com/api/v2/PublicPortal/ListArchivedMeetingsByCommitteeId?year=2026&committeeId=1",  # noqa
)


@pytest.fixture
def committee_items():
    spider = GraPublicSafetySpider()
    spider.attachments = attachments_response.json()
    with freeze_time("2026-09-24"):
        return [item for item in spider._parse_events(html_response)]


def test_count(committee_items):
    assert len(committee_items) == 11


def test_title(committee_items):
    assert committee_items[0]["title"] == "Public Safety Committee"


def test_description(committee_items):
    assert committee_items[0]["description"] == ""


def test_start(committee_items):
    assert committee_items[0]["start"] == datetime(2026, 1, 27, 12, 30)


def test_end(committee_items):
    assert committee_items[0]["end"] is None


def test_time_notes(committee_items):
    assert committee_items[0]["time_notes"] == ""


def test_id(committee_items):
    assert (
        committee_items[0]["id"]
        == "gra_public_safety/202601271230/x/public_safety_committee"
    )


def test_status(committee_items):
    assert committee_items[0]["status"] == "passed"


def test_location(committee_items):
    assert committee_items[0]["location"] == {
        "name": "City of Grand Rapids - City Hall",
        "address": "300 Monroe Ave NW, Grand Rapids, MI 49503",
    }


def test_source(committee_items):
    assert (
        committee_items[0]["source"]
        == "https://events.grandrapidsmi.gov/meetings/Detail/2026-01-27-1230-Public-Safety-Committee"  # noqa
    )


def test_links(committee_items):
    assert committee_items[0]["links"] == [
        {
            "href": "https://www.grandrapidsmi.gov/government/public-notices/",
            "title": "Meeting cancellations and other public notices can be found on this page",  # noqa
        },
        {
            "title": "YouTube channel",
            "href": "https://www.youtube.com/@TheCityofGrandRapids",
        },
        {
            "href": "https://grandrapidsmi.new.swagit.com/videos/373285",
            "title": "Video",
        },
        {
            "href": "https://grandrapidscity.primegov.com/Public/CompiledDocument?meetingTemplateId=31096&compileOutputType=1",  # noqa
            "title": "Agenda",
        },
        {
            "href": "https://grandrapidscity.primegov.com/Public/CompiledDocument?meetingTemplateId=31098&compileOutputType=1",  # noqa
            "title": "Packet",
        },
    ]


def test_classification(committee_items):
    assert committee_items[0]["classification"] == COMMITTEE
