from city_scrapers_core.constants import BOARD
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import parser


class GrandRapidsPublicSchoolBoardSpider(CityScrapersSpider):
    name = "grand_rapids_public_school_board"
    agency = "Grand Rapids Public School Board"
    timezone = "America/Chicago"
    start_urls = ["https://grps.org/our-district/board-of-education/"]

    def parse(self, response):
        """
        `parse` should always `yield` Meeting items.

        Change the `_parse_title`, `_parse_start`, etc methods to fit your scraping
        needs.
        """
        for item in response.css(".fbcms_upcoming_event_item .fbcms_upcoming_event"):
            meeting = Meeting(
                title=self._parse_title(item),
                description=self._parse_description(item),
                classification=self._parse_classification(item),
                start=self._parse_start(item),
                end=self._parse_end(item),
                all_day=self._parse_all_day(item),
                time_notes=self._parse_time_notes(item),
                location=self._parse_location(item),
                links=self._parse_links(item),
                source=self._parse_source(response),
            )

            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)

            yield meeting

    def _parse_title(self, item):
        """Parse or generate meeting title."""
        title = item.css(".name span::text").get().strip()
        return title

    def _parse_description(self, item):
        """Parse or generate meeting description."""
        return ""

    def _parse_classification(self, item):
        """Parse or generate classification from allowed options."""
        return BOARD

    def _parse_start(self, item):
        """Parse start datetime as a naive datetime object."""
        date = item.css(".day .detail_value::text").get() + " 2023"
        time = item.css(".time .detail_value::text").get()
        start_time = time.split("to")[0]

        start = date + " " + start_time

        return parser().parse(start)

    def _parse_end(self, item):
        """Parse end datetime as a naive datetime object. Added by pipeline if None"""
        date = item.css(".day .detail_value::text").get() + " 2023"
        time = item.css(".time .detail_value::text").get()
        end_time = time.split("to")[1]

        end = date + " " + end_time

        return parser().parse(end)

    def _parse_time_notes(self, item):
        """Parse any additional notes on the timing of the meeting"""
        return ""

    def _parse_all_day(self, item):
        """Parse or generate all-day status. Defaults to False."""
        return False

    def _parse_location(self, item):
        """Parse or generate location."""
        location = item.css(".location .detail_value::text").get()
        return {
            "address": location,
            "name": location,
        }

    def _parse_links(self, item):
        """Parse or generate links."""
        return [
            {
                "href": "https://go.boarddocs.com/mi/grand/Board.nsf/Public",
                "title": "Meeting Agendas",
            }
        ]

    def _parse_source(self, response):
        """Parse or generate source."""
        return response.url
