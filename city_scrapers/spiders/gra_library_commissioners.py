import re
from collections import Counter

from city_scrapers_core.constants import BOARD
from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import parse as dateutil_parser


class GraLibraryCommissionersSpider(CityScrapersSpider):
    name = "gra_library_commissioners"
    agency = "Grand Rapids Public Library"
    timezone = "America/Detroit"
    start_urls = ["https://www.grpl.org/about/board-of-library-commissioners/"]
    location = {
        "name": "Main Library, Board Room (Level 5)",
        "address": "111 Library St NE, Grand Rapids, MI 49503",
    }

    # Dates flagged with an asterisk don't follow the regular start time described
    # under "Board Meetings", so the attachment has to be checked instead.
    ASTERISK_NOTE = "Please check the meeting attachment for start time details"

    # The regular start time is stated once in prose rather than per meeting, so
    # `parse` reads it off the response before walking the listing.
    regular_time = None
    regular_time_notes = ""

    def parse(self, response):
        """
        `parse` should always `yield` Meeting items.

        Meeting dates are listed under "Meeting Minutes and Packets", one paragraph
        per meeting, while the regular start time is only given in prose under
        "Board Meetings".
        """
        self.regular_time, self.regular_time_notes = self._parse_meeting_time(response)

        parsed = []
        for item in response.xpath(
            '//h3[contains(text(),"Meeting Minutes and Packets")]'
            '/ancestor::div[contains(@class,"fl-module-rich-text")][1]'
            '/following::div[contains(@class,"fl-accordion-content")]//p'
        ):
            start = self._parse_start(item)
            if start is None:
                # Not every paragraph in the accordion is a meeting listing
                continue

            meeting = Meeting(
                title="Board of Library Commissioners",
                description="",
                classification=BOARD,
                start=start,
                end=None,
                all_day=False,
                time_notes=self._parse_time_notes(item),
                location=self.location,
                links=self._parse_links(item),
                source=response.url,
            )

            item_text = self._parse_item_text(item)
            meeting["status"] = self._get_status(meeting, text=item_text)
            parsed.append((meeting, item_text))

        if not parsed:
            self.logger.warning(
                "No meetings found under 'Meeting Minutes and Packets' at %s. "
                "The listing markup has most likely changed.",
                response.url,
            )

        # Four dates list a regular and a special meeting as separate rows. Both
        # rows share a date, and the regular start time is applied to each, so
        # they would otherwise collapse onto a single ID. Only the starred row of
        # such a pair is the special meeting -- an asterisk on a date with no
        # twin just marks a meeting held off the usual last-Tuesday schedule.
        date_counts = Counter(meeting["start"] for meeting, _ in parsed)
        for meeting, item_text in parsed:
            identifier = None
            if date_counts[meeting["start"]] > 1 and "*" in item_text:
                identifier = "special"
            meeting["id"] = self._get_id(meeting, identifier)

            yield meeting

    def _parse_meeting_time(self, response):
        """Pull the regular start time, and the sentence it came from, out of the
        prose under the "Board Meetings" heading."""
        description = " ".join(
            response.xpath(
                '//h3[contains(text(),"Board Meetings")]'
                '/ancestor::div[contains(@class,"fl-module-rich-text")][1]'
                "/following::p[1]//text()"
            ).getall()
        )
        description = re.sub(r"\s+", " ", description).strip()

        time_match = re.search(r"\d{1,2}:\d{2}\s*[apAP]\.?[mM]\.?", description)
        if not time_match:
            self.logger.warning(
                "No start time found in the prose under 'Board Meetings' at %s. "
                "Meetings will be dated without a time.",
                response.url,
            )
            return None, ""

        time_str = re.sub(r"[\s.]", "", time_match.group()).upper()
        # Keep the sentence the time was found in as the time note
        sentences = re.split(r"(?<=\.)\s+", description)
        time_notes = next(
            (s for s in sentences if time_match.group() in s), description
        )
        return time_str, time_notes

    def _parse_item_text(self, item):
        """Flatten a meeting paragraph into a single line of text."""
        text = " ".join(item.xpath(".//text()").getall())
        # Link text includes screen reader hints that aren't part of the listing
        text = text.replace(", opens a new window", "")
        return re.sub(r"\s+", " ", text).strip()

    def _parse_start(self, item):
        """Parse start datetime as a naive datetime object."""
        date_match = re.search(
            r"[A-Z][a-z]+ \d{1,2}, \d{4}", self._parse_item_text(item)
        )
        if not date_match:
            return None

        date_str = date_match.group()
        if self.regular_time:
            return dateutil_parser(f"{date_str} {self.regular_time}")
        return dateutil_parser(date_str)

    def _parse_time_notes(self, item):
        """Parse any additional notes on the timing of the meeting"""
        notes = [self.regular_time_notes]
        if "*" in self._parse_item_text(item):
            notes.append(self.ASTERISK_NOTE)
        return " ".join([n for n in notes if n])

    def _parse_links(self, item):
        """Parse or generate links.

        The "Packet" link is labelled on the page, but the meeting date links
        straight to its attachment, so the file name decides the label.
        """
        links = []
        for link in item.xpath(".//a"):
            href = link.xpath("@href").get()
            if not href:
                continue
            text = " ".join(link.xpath(".//text()").getall())
            if "packet" in text.lower():
                title = "Packet"
            elif "agenda" in href.lower():
                title = "Agenda"
            elif "minutes" in href.lower():
                title = "Minutes"
            else:
                title = "Meeting Document"
            links.append({"href": href, "title": title})
        return links
