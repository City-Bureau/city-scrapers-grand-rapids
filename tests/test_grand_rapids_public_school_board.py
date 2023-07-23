from datetime import datetime
from os.path import dirname, join

import pytest
from city_scrapers_core.constants import BOARD
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.grand_rapids_public_school_board import (
    GrandRapidsPublicSchoolBoardSpider,
)

test_response = file_response(
    join(dirname(__file__), "files", "grand_rapids_public_school_board.html"),
    url="https://grps.org/our-district/board-of-education/",
)
spider = GrandRapidsPublicSchoolBoardSpider()

freezer = freeze_time("2023-07-22")
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
    assert parsed_items[0]["title"] == "Board of Education Finance Committee"


def test_description():
    assert parsed_items[0]["description"] == ""


def test_start():
    assert parsed_items[0]["start"] == datetime(2023, 7, 24, 16, 30)


def test_end():
    assert parsed_items[0]["end"] == datetime(2023, 7, 24, 17, 30)


def test_time_notes():
    assert parsed_items[0]["time_notes"] == ""


def test_id():
    assert (
        parsed_items[0]["id"]
        == "grand_rapids_public_school_board/202307241630/x/board_of_education_finance_committee"  # noqa
    )


def test_status():
    assert parsed_items[0]["status"] == "tentative"


def test_location():
    assert parsed_items[0]["location"] == {
        "name": "GRPS Administration Building, 1331 MLK Jr Street SE, Grand Rapids, MI 49506",  # noqa
        "address": "GRPS Administration Building, 1331 MLK Jr Street SE, Grand Rapids, MI 49506",  # noqa
    }


def test_source():
    assert (
        parsed_items[0]["source"] == "https://grps.org/our-district/board-of-education/"
    )


def test_links():
    assert parsed_items[0]["links"] == [
        {
            "href": "https://go.boarddocs.com/mi/grand/Board.nsf/Public",
            "title": "Meeting Agendas",
        }
    ]


def test_classification():
    assert parsed_items[0]["classification"] == BOARD


@pytest.mark.parametrize("item", parsed_items)
def test_all_day(item):
    assert item["all_day"] is False
