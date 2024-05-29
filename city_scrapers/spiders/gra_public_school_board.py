import re

from city_scrapers.mixins.boarddocs import BoardDocsMixin


class GraPublicSchoolBoardSpider(BoardDocsMixin):
    name = "gra_public_school_board"
    agency = "Grand Rapids Public School Board"
    start_urls = ["https://grps.org/our-district/board-of-education/"]
    boarddocs_slug = "grand"
    boarddocs_committee_id = "A4EP6J588C05"

    def _parse_location(self, response):
        """
        Parse the description node for the location address.
        In this case, the location tends to be the first 4 lines
        are time information in the format "9:30 a.m."
        """
        location_node = response.css("div.meeting-description")

        if not location_node:
            return {"name": "TBD", "address": ""}

        # Extract and clean the HTML content
        location_text = location_node.get()
        location_text = re.sub(
            r"<br\s*/?>", "\n", location_text
        )  # Replace <br> with newlines
        location_text = re.sub(
            r"<.*?>", "", location_text
        )  # Remove any other HTML tags
        location_lines = location_text.split("\n")

        # Regex to match time pattern (e.g., "9:30 a.m.")
        time_pattern = re.compile(r"\d{1,2}:\d{2}\s*(a\.m\.|p\.m\.)", re.IGNORECASE)
        address_lines = []

        for i, line in enumerate(location_lines):
            if time_pattern.search(line.strip()):
                # Assume the previous 4 lines contain the address parts
                start_index = max(0, i - 4)
                address_lines = location_lines[start_index:i]
                break

        if not address_lines:
            return {"name": "TBD", "address": ""}

        # Combine address parts into a single string
        address = ", ".join([line.strip() for line in address_lines if line.strip()])

        return {"name": "", "address": address}
