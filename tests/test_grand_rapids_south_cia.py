from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import NOT_CLASSIFIED
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.grand_rapids_south_cia import GrandRapidsSouthCiaSpider

test_response = file_response(
    join(dirname(__file__), "files", "grand_rapids_south_cia.html"),
    url="http://grandrapidscitymi.iqm2.com/Citizens/calendar.aspx?View=List",
)
spider = GrandRapidsSouthCiaSpider()

freezer = freeze_time("2023-07-27")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


"""
Uncomment below
def test_tests():
    print("Please write some tests for this spider or at least disable this one.")
    assert False
"""


def test_title():
    assert parsed_items[0]["title"] == "South Division-Grandville CIA"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2023, 2, 9, 9, 0)


# def test_end():
#     assert parsed_items[0]["end"] == datetime(2019, 1, 1, 0, 0)


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert (
        parsed_items[0]["id"]
        == "grand_rapids_south_cia/202302090900/x/south_division_grandville_cia"
    )


def test_status():
    assert parsed_items[0]["status"] == "passed"


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "",
        "address": "Grand Rapids Fire Department 1823 Division Avenue S, Grand Rapids, MI  49507",  # noqa
    }


def test_source():
    assert (
        parsed_items[0]["source"]
        == "http://grandrapidscitymi.iqm2.com/Citizens/calendar.aspx?View=List"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "href": "http://grandrapidscitymi.iqm2.com//Citizens/Detail_Meeting.aspx?ID=7145",  # noqa
            "title": "Meeting Page",
        },
        {
            "href": "http://grandrapidscitymi.iqm2.com//Citizens/Detail_Meeting.aspx?ID=7145",  # noqa
            "title": "Agenda",
        },
        {
            "href": "http://grandrapidscitymi.iqm2.com/Citizens/FileOpen.aspx?Type=1&ID=5174&Inline=True",  # noqa
            "title": "Agenda Packet",
        },
        {"href": None, "title": "Summary"},
        {
            "href": "http://grandrapidscitymi.iqm2.com/Citizens/FileOpen.aspx?Type=12&ID=5229&Inline=True",  # noqa
            "title": "Minutes",
        },
    ]


def test_classification():
    assert parsed_items[0]["classification"] == NOT_CLASSIFIED


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False
