from datetime import datetime
from os.path import dirname, join

import pytest  # noqa
from city_scrapers_core.constants import BOARD, PASSED
from city_scrapers_core.utils import file_response
from freezegun import freeze_time

from city_scrapers.spiders.gra_public_school_board import GraPublicSchoolBoardSpider

test_response = file_response(
    join(dirname(__file__), "files", "gra_public_school_board.json"),
    url="https://grps.org/our-district/board-of-education/",
)
test_response_detail = file_response(
    join(dirname(__file__), "files", "gra_public_school_board_detail.html"),
    url="https://grps.org/our-district/board-of-education/",
)
spider = GraPublicSchoolBoardSpider()

freezer = freeze_time("2024-05-29")
freezer.start()

# parse_detail expects a response object with a meta attribute
# containing the start date and meeting id
test_response_detail.meta["start_date"] = datetime(2024, 5, 22, 0, 0)
test_response_detail.meta["meeting_id"] = "gra_public_school_board/202405220000/x/special_board_meeting_board_retreat_9_30_a_m_12_00_p_m_"
parsed_items = [item for item in spider.parse(test_response)]
parsed_item = next(spider._parse_detail(test_response_detail))
freezer.stop()

def test_count():
    assert len(parsed_items) == 4  # Adjust based on your expected count

def test_title():
    assert parsed_item["title"] == "Special Board Meeting/Board Retreat @ 9:30 a.m. - 12:00 p.m."

def test_description():
    assert parsed_item["description"] == "GRAND RAPIDS PUBLIC SCHOOLS BOARD OF EDUCATION 1400 Fuller Ave. NE Multipurpose Room Grand Rapids, MI 49505 9:30 a.m. - 12:00 p.m. MINUTES STATEMENT Minutes of all Grand Rapids Board of Education meetings are kept on file and are available for inspection at the Board of Education Office of the Grand Rapids Public Schools, 1331 Franklin St. SE, during regular business hours and recent minutes are also accessible via GRPS website at www.grps.org through the BoardDocs link: https://www.boarddocs.com/mi/grand/Board.nsf/vpublic?open"

def test_start():
    assert parsed_item["start"] == test_response_detail.meta["start_date"]

def test_end():
    assert parsed_item["end"] is None

def test_time_notes():
    assert parsed_item["time_notes"] == ""

def test_id():
    assert parsed_item["id"] == "gra_public_school_board/202405220000/x/special_board_meeting_board_retreat_9_30_a_m_12_00_p_m_"

def test_status():
    assert parsed_item["status"] == PASSED

def test_location():
    assert parsed_item["location"] == {
  "name": "",
  "address": "BOARD OF EDUCATION, 1400 Fuller Ave. NE, Multipurpose Room, Grand Rapids, MI 49505"
}

def test_source():
    assert parsed_item["source"] == "https://go.boarddocs.com/mi/grand/Board.nsf/Public"

def test_links():
    assert parsed_item["links"] == []

def test_classification():
    assert parsed_item["classification"] == BOARD

def test_all_day():
    assert parsed_item["all_day"] is False
