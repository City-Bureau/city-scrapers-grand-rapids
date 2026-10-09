import json
import random
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from city_scrapers_core.constants import BOARD, COMMITTEE, TENTATIVE
from city_scrapers_core.items import Meeting
from dateutil.relativedelta import relativedelta
from scrapy import Request
from w3lib.url import add_or_replace_parameters

from city_scrapers.mixins.boarddocs import BoardDocsMixin


class GraPublicSchoolBoardSpider(BoardDocsMixin):
    name = "gra_public_school_board"
    agency = "GRPS Board of Education"
    start_urls = [
        "https://grps.org/our-district/board-of-education/board-meeting-schedule/"
    ]
    boarddocs_slug = "grand"
    boarddocs_committee_id = "A4EP6J588C05"

    foxbright_url = "https://grps.org/Core/FoxbrightCalendars/Agenda/144574/"
    foxbright_calendar_id = "1002"
    youtube_playlist_id = "PL-TX6krcrZxZuKvEyOxDXB_Jy1CriraLl"
    youtube_playlist_url = (
        f"https://www.youtube.com/playlist?list={youtube_playlist_id}"
    )
    youtube_api_url = "https://www.googleapis.com/youtube/v3/playlistItems"
    BOARDDOCS_HEADERS = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",  # noqa
        "X-Requested-With": "XMLHttpRequest",
    }

    @property
    def cutoff_date(self):
        today = datetime.now(ZoneInfo(self.timezone)).date()
        return today - relativedelta(months=3, days=1)

    def _boarddocs_post(
        self, endpoint, body, referer, callback, cb_kwargs=None, errback=None
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
            cb_kwargs=cb_kwargs or {},
            errback=errback,
            dont_filter=True,
        )

    def _extract_all_times(self, text):
        if not text:
            return []
        candidates = re.findall(r"(\d{1,2}:\d{2}\s*[APap]\.?[Mm]\.?)", text)
        times = []
        for candidate in candidates:
            # Normalize "6:30PM" / "6:30 p.m." to "6:30 PM" for strptime
            cleaned = re.sub(
                r"\s*([AP])M$", r" \1M", candidate.replace(".", "").upper()
            )  # noqa
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
        self._video_map = {}

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
                location_name = self._parse_location_name(item)

                location = (
                    {"name": location_name, "address": location_address}
                    if location_address
                    else {"name": location_name or "TBD", "address": ""}
                )

                if date_str:
                    try:
                        full_date_str = f"{date_str} {base_year}"
                        parsed_date = datetime.strptime(full_date_str, "%b %d %Y")
                        if parsed_date.date() >= self.cutoff_date:
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

        yield from self._request_youtube_videos()

    def _request_youtube_videos(self, page_token=None):
        """Video titles look like "BOE Meeting 9/14/2026" or "Board of Education
        Meeting 7-13-26", so the playlist is read through the YouTube Data API
        to link each meeting to its own recording instead of the playlist.
        Without an API key, meetings are yielded without video links."""
        api_key = self.settings.get("YOUTUBE_API_KEY")
        if not api_key:
            self.logger.warning("YOUTUBE_API_KEY not set, skipping video links")
            yield from self._request_boarddocs_public_page()
            return

        params = {
            "part": "snippet",
            "playlistId": self.youtube_playlist_id,
            "maxResults": "50",
            "fields": "nextPageToken,items(snippet(title,resourceId/videoId))",
        }
        if page_token:
            params["pageToken"] = page_token
        yield Request(
            add_or_replace_parameters(self.youtube_api_url, params),
            # Sent as a header so the key stays out of logged request URLs
            headers={"X-Goog-Api-Key": api_key},
            callback=self._parse_youtube_videos,
            errback=self._handle_youtube_error,
            dont_filter=True,
        )

    def _handle_youtube_error(self, failure):
        self.logger.warning(
            "YouTube API request failed, continuing anyway: %r", failure
        )
        yield from self._request_boarddocs_public_page()

    def _parse_youtube_videos(self, response):
        try:
            data = json.loads(response.text)
        except ValueError as e:
            self.logger.warning("Failed to parse YouTube API response: %s", e)
            data = {}

        reached_cutoff = False
        for item in data.get("items", []):
            snippet = item.get("snippet", {})
            title = snippet.get("title", "")
            video_id = snippet.get("resourceId", {}).get("videoId")
            if not video_id or title in ("Private video", "Deleted video"):
                continue
            video_date = self._parse_video_date(title)
            if not video_date:
                self.logger.warning("No date found in YouTube video title: '%s'", title)
                continue
            if video_date < self.cutoff_date:
                reached_cutoff = True
                continue
            lang = "es" if re.search(r"espa[ñn]ol|spanish", title, re.I) else "en"
            key = (video_date, self._meeting_kind(title))
            self._video_map.setdefault(key, {})[
                lang
            ] = f"https://www.youtube.com/watch?v={video_id}"

        # The playlist is newest first, so once a video older than the cutoff
        # shows up, later pages are older too and would only spend API quota
        next_token = data.get("nextPageToken")
        if next_token and not reached_cutoff:
            yield from self._request_youtube_videos(next_token)
        else:
            yield from self._request_boarddocs_public_page()

    def _parse_video_date(self, title):
        """Titles have used "9/14/2026", "7-13-26", "03 24 25", "Dec 8, 2025",
        "November, 26 2024" and "January 8. 2024" over the years."""
        for match in re.finditer(
            r"\b(\d{1,2})([/\- ])(\d{1,2})\2(\d{4}|\d{2})\b", title
        ):
            month, _, day, year = match.groups()
            video_date = self._build_date(year, month, day)
            if video_date:
                return video_date
        for match in re.finditer(
            r"\b([A-Za-z]{3,9})[.,]?\s+(\d{1,2})[.,]?\s+(\d{4})\b", title
        ):
            month_name, day, year = match.groups()
            try:
                month = datetime.strptime(month_name[:3], "%b").month
            except ValueError:
                continue
            video_date = self._build_date(year, month, day)
            if video_date:
                return video_date
        return None

    def _build_date(self, year, month, day):
        year = int(year)
        if year < 100:
            year += 2000
        try:
            return date(year, int(month), int(day))
        except ValueError:
            return None

    def _meeting_kind(self, title):
        """Shared by video and Foxbright titles so a video only matches the
        meeting of the same kind on its date (e.g. the 6:30 Regular Meeting
        rather than the 5:00 committee meeting held the same evening).
        Committees are told apart by the word before "Committee", since two
        can meet on the same date and titles vary ("GRPS Finance Committe
        Meeting" vs "Board of Education Finance Committee Meeting")."""
        title = title.lower()
        committee = re.search(r"(\w+)\s+committe", title)
        if committee:
            return f"committee:{committee.group(1)}"
        if "committe" in title:
            return "committee"
        for kind in ("work session", "special"):
            if kind in title:
                return kind
        return "regular"

    def _request_boarddocs_public_page(self):
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

    def _parse_location_name(self, item):
        """Room details (e.g. "Library Building, Room 112" or "Located in the
        Auditorium.") live in the event description. Only the description's
        own text nodes are used so link text like "Agenda will be posted on
        BoardDocs." or "Watch Live" is ignored."""
        parts = [
            re.sub(r"\s+", " ", text).strip()
            for text in item.css(".details .description::text").getall()
        ]
        name = next((part for part in parts if part), "")
        name = re.sub(r"^Located in\s+(the\s+)?", "", name, flags=re.IGNORECASE)
        return name.rstrip(".").strip()

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

        cutoff_int = int(self.cutoff_date.strftime("%Y%m%d"))
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
                cb_kwargs={"numberdate": numberdate},
                errback=self._handle_boarddocs_detail_error,
            )

    def _handle_boarddocs_detail_error(self, failure):
        self.logger.warning("BoardDocs detail request failed: %r", failure)
        self._pending_boarddocs -= 1
        if self._pending_boarddocs <= 0:
            for meeting in self._parse_all_meetings():
                yield meeting

    def _parse_boarddocs_detail(self, response, numberdate=None):
        self._pending_boarddocs -= 1

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

            # _get_id and _get_status need a start datetime; skip rather than
            # let one bad event raise and drop every meeting after it
            if start_dt is None:
                self.logger.warning(
                    "Skipping Foxbright event without a parseable time: %s", ev
                )
                continue

            links = []
            dt_key = start_dt.strftime("%Y-%m-%d %H:%M:%S")
            if dt_key in self._boarddocs_links_map:
                links.append(
                    {
                        "href": self._boarddocs_links_map[dt_key],
                        "title": "Meeting Attachments",
                    }
                )

            videos = self._video_map.get(
                (start_dt.date(), self._meeting_kind(ev["title"])), {}
            )
            if "en" in videos:
                links.append({"href": videos["en"], "title": "Video"})
            if "es" in videos:
                links.append({"href": videos["es"], "title": "Video (Español)"})

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
            )
            meeting["id"] = self._get_id(meeting)
            meeting["status"] = self._get_status(meeting)
            # Upcoming meetings point to the playlist until their own recording
            # is posted; past meetings without a recording get no video link
            if not videos and meeting["status"] == TENTATIVE:
                meeting["links"].append(
                    {"href": self.youtube_playlist_url, "title": "YouTube channel"}
                )
            yield meeting

    def _parse_classification(self, title):
        if "committee" in title.lower():
            return COMMITTEE
        return BOARD
