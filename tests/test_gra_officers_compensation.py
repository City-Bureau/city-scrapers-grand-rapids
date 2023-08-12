from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import COMMISSION
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.gra_officers_compensation import (
    GraOfficersCompensationSpider,
)

test_response = file_response(
    join(dirname(__file__), "files", "gra_officers_compensation.html"),
    url="http://grandrapidscitymi.iqm2.com/Citizens/calendar.aspx",
)
spider = GraOfficersCompensationSpider()

freezer = freeze_time("2023-08-12")
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
    assert parsed_items[0]["title"] == "Local Officers Compensation Commission"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2023, 3, 13, 15, 0)


# def test_end():
#     assert parsed_items[0]["end"] == datetime(2019, 1, 1, 0, 0)


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert (
        parsed_items[0]["id"]
        == "gra_officers_compensation/202303131500/x/local_officers_compensation_commission"  # noqa
    )


def test_status():
    assert parsed_items[0]["status"] == "passed"


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "",
        "address": "Room 811, 8th Floor 300 Monroe Avenue NW, Room 811, 8th Floor, Grand Rapids, MI  49503",  # noqa
    }


def test_source():
    assert (
        parsed_items[0]["source"]
        == "http://grandrapidscitymi.iqm2.com/Citizens/calendar.aspx"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "href": "http://grandrapidscitymi.iqm2.com//Citizens/Detail_Meeting.aspx?ID=7299",  # noqa
            "title": "Meeting Page",
        },
        {"href": None, "title": "Agenda"},
        {"href": None, "title": "Agenda Packet"},
        {"href": None, "title": "Summary"},
        {"href": None, "title": "Minutes"},
    ]


def test_classification():
    assert parsed_items[0]["classification"] == COMMISSION


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False
