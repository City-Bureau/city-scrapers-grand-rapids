from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import COMMITTEE
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.gra_appointments import (
    GrandRapidsAppointmentsSpider,
)

test_response = file_response(
    join(dirname(__file__), "files", "grand_rapids_appointments.html"),
    url="http://grandrapidscitymi.iqm2.com/Citizens/calendar.aspx",
)
spider = GrandRapidsAppointmentsSpider()

freezer = freeze_time("2023-07-26")
freezer.start()

parsed_items = [item for item in spider.parse(test_response)]

freezer.stop()


"""
def test_tests():
    print("Please write some tests for this spider or at least disable this one.")
    assert False
Uncomment below
"""


def test_title():
    assert parsed_items[0]["title"] == "Committee on Appointments"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2023, 1, 10, 8, 0)


# def test_end():
#     assert parsed_items[0]["end"] == datetime(2019, 1, 1, 0, 0)


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert (
        parsed_items[0]["id"]
        == "gra_appointments/202301100800/x/committee_on_appointments"
    )


def test_status():
    assert parsed_items[0]["status"] == "passed"


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "",
        "address": "City Commission Chambers City Hall, 300 Monroe Ave NW, 9th Floor, Grand Rapids, MI  49503",  # noqa
    }


def test_source():
    assert (
        parsed_items[0]["source"]
        == "http://grandrapidscitymi.iqm2.com/Citizens/calendar.aspx"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "href": "http://grandrapidscitymi.iqm2.com//Citizens/Detail_Meeting.aspx?ID=6986",  # noqa
            "title": "Meeting Page",
        },
        {"href": None, "title": "Agenda"},
        {
            "href": "http://grandrapidscitymi.iqm2.com/Citizens/FileOpen.aspx?Type=1&ID=5134&Inline=True",  # noqa
            "title": "Agenda Packet",
        },
        {"href": None, "title": "Summary"},
        {"href": None, "title": "Minutes"},
    ]


def test_classification():
    assert parsed_items[0]["classification"] == COMMITTEE


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False
