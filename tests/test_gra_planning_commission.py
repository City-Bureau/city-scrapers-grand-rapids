from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import NOT_CLASSIFIED
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.gra_planning_commission import GraPlanningCommissionSpider

test_response = file_response(
    join(dirname(__file__), "files", "gra_planning_commission.html"),
    url="http://grandrapidscitymi.iqm2.com/Citizens/calendar.aspx?View=List",
)
spider = GraPlanningCommissionSpider()

freezer = freeze_time("2023-08-11")
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
    assert parsed_items[0]["title"] == "City Planning Commission"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2023, 1, 12, 12, 30)


# def test_end():
#     assert parsed_items[0]["end"] == datetime(2019, 1, 1, 0, 0)


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert (
        parsed_items[0]["id"]
        == "gra_planning_commission/202301121230/x/city_planning_commission"
    )


def test_status():
    assert parsed_items[0]["status"] == "passed"


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "",
        "address": "THURSDAY, JANUARY 12, 2023  12:30 PM\r\rBoard:\tCity Planning Commission\rType:\tRegular Meeting\rStatus:\tClosed\r\r\tCity Commission Chambers\r\tCity Hall, 300 Monroe Ave NW, 9th Floor, Grand Rapids, MI  49503",  # noqa
    }


def test_source():
    assert (
        parsed_items[0]["source"]
        == "http://grandrapidscitymi.iqm2.com/Citizens/calendar.aspx?View=List"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "href": "http://grandrapidscitymi.iqm2.com//Citizens/Detail_Meeting.aspx?ID=6903",  # noqa
            "title": "Meeting Page",
        },
        {
            "href": "http://grandrapidscitymi.iqm2.com//Citizens/Detail_Meeting.aspx?ID=6903",  # noqa
            "title": "Agenda",
        },
        {
            "href": "http://grandrapidscitymi.iqm2.com/Citizens/FileOpen.aspx?Type=1&ID=5133&Inline=True",  # noqa
            "title": "Agenda Packet",
        },
        {
            "href": "http://grandrapidscitymi.iqm2.com/Citizens/FileView.aspx?Type=15&ID=5205",  # noqa
            "title": "Summary",
        },
        {
            "href": "http://grandrapidscitymi.iqm2.com/Citizens/FileView.aspx?Type=12&ID=5205",  # noqa
            "title": "Minutes",
        },
    ]


def test_classification():
    assert parsed_items[0]["classification"] == NOT_CLASSIFIED


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False
