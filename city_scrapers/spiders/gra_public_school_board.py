import json
import random
import re
from datetime import date, datetime

from city_scrapers_core.items import Meeting
from scrapy import Request

from city_scrapers.mixins.boarddocs import BoardDocsMixin


class GraPublicSchoolBoardSpider(BoardDocsMixin):
    name = "gra_public_school_board"
    agency = "GRPS Board of Education"
    start_urls = [
        "https://grps.org/our-district/board-of-education/board-meeting-schedule/"
    ]
    boarddocs_slug = "grand"
    boarddocs_state = "mi"
    boarddocs_committee_id = "A4EP6J588C05"

    foxbright_url = "https://grps.org/Core/FoxbrightCalendars/Agenda/144574/"
    foxbright_calendar_id = "1002"
    VIDEO_PLAYLIST_URL = (
        "http://youtube.com/playlist?list=PL-TX6krcrZxZuKvEyOxDXB_Jy1CriraLl"
    )
    BOARDDOCS_HEADERS = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",  # noqa
        "X-Requested-With": "XMLHttpRequest",
    }

    CUTOFF_DATE = date(2026, 7, 1)

    custom_settings = {
        **BoardDocsMixin.custom_settings,
        "COOKIES_ENABLED": True,
    }

    def _boarddocs_post(
        self, endpoint, body, referer, callback, meta=None, errback=None
    ):
        return Request(
            f"{self.base_url}/{self.boarddocs_state}/{self.boarddocs_slug}/Board.nsf/"
            f"{endpoint}?open&0.{self.gen_random_int()}",
            method="POST",
            body=body,
            headers={
                **self.BOARDDOCS_HEADERS,
                "Origin": self.base_url,
                "Referer": referer,
            },
            callback=callback,
            meta=meta or {},
            errback=errback,
            dont_filter=True,
        )

    def _extract_all_times(self, text):
        if not text:
            return []
        candidates = re.findall(r"(\d{1,2}:\d{2}\s*[APap]\.?[Mm]\.?)", text)
        times = []
        for candidate in candidates:
            cleaned = candidate.replace(".", "").upper()
            try:
                times.append(datetime.strptime(cleaned, "%I:%M %p").time())
            except ValueError:
                self.logger.warning("Failed to parse time from text: '%s'", text)
                continue
        return times

    def start_requests(self):
        self._foxbright_events = []
        self._boarddocs_links_map = {}
        self._pending_boarddocs = 0

        body = (
            "Month=AllFromStart"
            f"&rndm={random.random()}"
            f"&Calendars={self.foxbright_calendar_id}"
            "&DisplayType=List&HideNavigation=true"
        )
        yield Request(
            self.foxbright_url,
            method="POST",
            body=body,
            headers={
                **self.BOARDDOCS_HEADERS,
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            },
            callback=self._parse_foxbright_all,
            dont_filter=True,
        )

    def _parse_foxbright_all(self, response):
        self._foxbright_events = []

        for month_block in response.css(".agenda_block.month_table"):
            header_text = month_block.css(".agenda_header.month_header::text").get(
                default=""
            )
            header_match = re.search(r"([A-Za-z]+)\s+(\d{4})", header_text)
            if not header_match:
                continue
            year_str = header_match.group(2)
            try:
                base_year = int(year_str)
            except ValueError:
                self.logger.warning(
                    "Failed to parse year from Foxbright header: '%s'", header_text
                )
                continue

            for item in month_block.css(".agenda_row.event_row"):
                title = (
                    item.css(".event_title::text, .agenda_data .name::text")
                    .get(default="")
                    .strip()
                )
                date_str = item.css(".event_date::text").get(default="").strip()
                time_str = item.css(".event_time::text").get(default="").strip()
                location_address = (
                    item.css(".event_detail.location .detail_value::text")
                    .get(default="")
                    .strip()
                )

                location = (
                    {"name": "", "address": location_address}
                    if location_address
                    else {"name": "TBD", "address": ""}
                )

                if date_str:
                    try:
                        full_date_str = f"{date_str} {base_year}"
                        parsed_date = datetime.strptime(full_date_str, "%b %d %Y")
                        if parsed_date.date() >= self.CUTOFF_DATE:
                            self._foxbright_events.append(
                                {
                                    "title": title,
                                    "date": parsed_date.date(),
                                    "time_str": time_str,
                                    "location": location,
                                }
                            )
                    except ValueError:
                        self.logger.warning(
                            "Failed to parse date from Foxbright: '%s'", date_str
                        )

        yield Request(
            self._parse_source(),
            callback=self._request_boarddocs_meetings_list,
            errback=self._handle_public_source_error,
            headers={
                **self.BOARDDOCS_HEADERS,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",  # noqa
                "Referer": "https://grps.org/",
            },
            dont_filter=True,
        )

    def _handle_public_source_error(self, failure):
        self.logger.warning(
            "BoardDocs public page request failed, continuing anyway: %s", failure
        )
        yield from self._request_boarddocs_meetings_list(None)

    def _request_boarddocs_meetings_list(self, response):
        yield self._boarddocs_post(
            "BD-GetMeetingsList",
            body=f"current_committee_id={self.boarddocs_committee_id}",
            referer=self._parse_source(),
            callback=self._parse_boarddocs_list,
            errback=self._handle_boarddocs_list_error,
        )

    def _handle_boarddocs_list_error(self, failure):
        self.logger.warning("BoardDocs list request failed: %r", failure)
        self._pending_boarddocs = 0
        self._boarddocs_links_map = {}
        yield from self._parse_all_meetings()

    def _parse_boarddocs_list(self, response):
        try:
            data = json.loads(response.text)
        except Exception as e:
            self.logger.warning(
                "Failed to parse JSON response from BoardDocs meetings list: %s", e
            )
            data = []

        cutoff_int = int(self.CUTOFF_DATE.strftime("%Y%m%d"))
        valid_items = []
        for item in data:
            if not item or not item.get("unique") or not item.get("numberdate"):
                continue
            try:
                numberdate_int = int(item["numberdate"])
            except (TypeError, ValueError):
                self.logger.warning(
                    "Invalid BoardDocs numberdate: %r", item.get("numberdate")
                )
                continue
            if numberdate_int >= cutoff_int:
                valid_items.append(item)

        self._pending_boarddocs = len(valid_items)
        self._boarddocs_links_map = {}

        if self._pending_boarddocs == 0:
            for meeting in self._parse_all_meetings():
                yield meeting
            return

        for item in valid_items:
            meeting_id = item.get("unique")
            numberdate = item.get("numberdate")
            yield self._boarddocs_post(
                "BD-GetMeeting",
                body=f"id={meeting_id}&current_committee_id={self.boarddocs_committee_id}",  # noqa
                referer=response.url,
                callback=self._parse_boarddocs_detail,
                meta={"numberdate": numberdate},
                errback=self._handle_boarddocs_detail_error,
            )

    def _handle_boarddocs_detail_error(self, failure):
        self.logger.warning("BoardDocs detail request failed: %r", failure)
        self._pending_boarddocs -= 1
        if self._pending_boarddocs <= 0:
            for meeting in self._parse_all_meetings():
                yield meeting

    def _parse_boarddocs_detail(self, response):
        self._pending_boarddocs -= 1
        numberdate = response.meta.get("numberdate")

        if numberdate:
            try:
                d_obj = datetime.strptime(str(numberdate), "%Y%m%d").date()
                detail_text = response.css("dd.col.rightcol::text").get(default="")
                if not detail_text:
                    detail_text = response.text

                times = self._extract_all_times(detail_text)
                t_obj = times[0] if times else None
                if t_obj:
                    dt_key = datetime.combine(d_obj, t_obj).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

                    clipboard_url = response.css(
                        "button.url::attr(data-clipboard-text)"
                    ).get()
                    if clipboard_url:
                        self._boarddocs_links_map[dt_key] = clipboard_url
                else:
                    self.logger.warning(
                        "Failed to parse time from BoardDocs detail for numberdate: '%s'",  # noqa
                        numberdate,
                    )
            except ValueError:
                self.logger.warning(
                    "Failed to parse date from BoardDocs detail for numberdate: '%s'",
                    numberdate,
                )

        if self._pending_boarddocs <= 0:
            for meeting in self._parse_all_meetings():
                yield meeting

    def _parse_all_meetings(self):
        for ev in self._foxbright_events:
            start_dt = None
            end_dt = None

            if ev.get("time_str"):
                times = self._extract_all_times(ev["time_str"])
                if not times:
                    self.logger.warning(
                        "Failed to parse start time from Foxbright: '%s'",
                        ev["time_str"],
                    )
                else:
                    start_dt = datetime.combine(ev["date"], times[0])
                    if len(times) >= 2:
                        end_dt = datetime.combine(ev["date"], times[1])

            links = []
            if start_dt is not None:
                dt_key = start_dt.strftime("%Y-%m-%d %H:%M:%S")
                if dt_key in self._boarddocs_links_map:
                    links.append(
                        {
                            "href": self._boarddocs_links_map[dt_key],
                            "title": "Meeting Attachments",
                        }
                    )

            links.append({"href": self.VIDEO_PLAYLIST_URL, "title": "Video"})

            meeting = Meeting(
                title=ev["title"] or "Board of Education Meeting",
                description="",
                classification=self._parse_classification(ev["title"]),
                start=start_dt,
                end=end_dt,
                all_day=False,
                time_notes="",
                location=ev["location"],
                links=links,
                source=self.start_urls[0],
                status="",
            )
            meeting["id"] = self._get_id(meeting)
            meeting["status"] = self._get_status(meeting)
            yield meeting

    def _parse_classification(self, title):
        if "committee" in title.lower():
            return "Committee"
        return "Board"
