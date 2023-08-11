from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import NOT_CLASSIFIED
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.gra_city_commission import GraCityCommissionSpider

test_response = file_response(
    join(dirname(__file__), "files", "gra_city_commission.html"),
    url="http://grandrapidscitymi.iqm2.com/Citizens/calendar.aspx?View=List",
)
spider = GraCityCommissionSpider()

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
    assert parsed_items[0]["title"] == "City Commission"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2023, 1, 10, 14, 0)


# def test_end():
#     assert parsed_items[0]["end"] == datetime(2019, 1, 1, 0, 0)


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert parsed_items[0]["id"] == "gra_city_commission/202301101400/x/city_commission"


def test_status():
    assert parsed_items[0]["status"] == "passed"


"""
def test_location():
    assert parsed_items[0]["location"] == {
        "name": "",
        "address": "TUESDAY, JANUARY 10, 2023  2:00 PM\r\rBoard:\tCity Commission\rType:\tRegular Session\rStatus:\tClosed\r\r\tCity Commission Chambers\r\tCity Hall, 300 Monroe Ave NW, 9th Floor, GrandRapids, MI  49503",  # noqa
    }
"""


def test_source():
    assert (
        parsed_items[0]["source"]
        == "http://grandrapidscitymi.iqm2.com/Citizens/calendar.aspx?View=List"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "href": "http://grandrapidscitymi.iqm2.com//Citizens/Detail_Meeting.aspx?ID=7034",  # noqa
            "title": "Meeting Page",
        },
        {
            "href": "http://grandrapidscitymi.iqm2.com//Citizens/Detail_Meeting.aspx?ID=7034",  # noqa
            "title": "Agenda",
        },
        {
            "href": "http://grandrapidscitymi.iqm2.com/Citizens/FileOpen.aspx?Type=1&ID=5138&Inline=True",  # noqa
            "title": "Agenda Packet",
        },
        {"href": None, "title": "Summary"},
        {
            "href": "http://grandrapidscitymi.iqm2.com/Citizens/FileOpen.aspx?Type=12&ID=5203&Inline=True",  # noqa
            "title": "Minutes",
        },
    ]


def test_classification():
    assert parsed_items[0]["classification"] == NOT_CLASSIFIED


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False
