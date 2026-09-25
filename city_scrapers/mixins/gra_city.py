import re
from datetime import datetime, timezone
from urllib.parse import urljoin

from city_scrapers_core.items import Meeting
from city_scrapers_core.spiders import CityScrapersSpider
from dateutil.parser import parse as dateutil_parser
from dateutil.relativedelta import relativedelta
from scrapy import Request
from w3lib.url import add_or_replace_parameter


class GrandRapidsCityMixinMeta(type):
    def __init__(cls, name, bases, dct):
        required_static_vars = ["keyword", "committee_id", "classification"]
        missing_vars = [var for var in required_static_vars if var not in dct]

        if missing_vars:
            missing_vars_str = ", ".join(missing_vars)
            raise NotImplementedError(
                f"{name} must define the following static variable(s): {missing_vars_str}."  # noqa
            )

        super().__init__(name, bases, dct)


class GrandRapidsCityMixin(CityScrapersSpider, metaclass=GrandRapidsCityMixinMeta):
    custom_settings = {
        "ROBOTSTXT_OBEY": False,
    }
    timezone = "America/Detroit"

    source_url = "https://events.grandrapidsmi.gov/meetings/"
    events_url = "https://events.grandrapidsmi.gov/meetings/index?action=search&StartDate={start_date}&EndDate={end_date}&Keywords={keyword}"  # noqa
    upcoming_attachments_url = "https://grandrapidscity.primegov.com/api/v2/PublicPortal/ListUpcomingMeetingsByCommitteeId?committeeId={committee_id}"  # noqa
    archived_attachments_url = "https://grandrapidscity.primegov.com/api/v2/PublicPortal/ListArchivedMeetingsByCommitteeId?year={year}&committeeId={committee_id}"  # noqa
    template_url = "https://grandrapidscity.primegov.com/Public/CompiledDocument?meetingTemplateId={template_id}&compileOutputType=1"  # noqa

    keyword = None
    committee_id = None
    classification = None
    attachments = None

    UA_HEADER = "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Mobile Safari/537.36"  # noqa

    location = {
        "name": "City of Grand Rapids - City Hall",
        "address": "300 Monroe Ave NW, Grand Rapids, MI 49503",
    }

    def start_requests(self):
        self.now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.past_date = self.now - relativedelta(years=2)
        self.future_date = self.now + relativedelta(months=6)

        yield Request(
            url=self.upcoming_attachments_url.format(committee_id=self.committee_id),
            callback=self._parse_upcoming,
        )

    def _parse_upcoming(self, response):
        years = list(range(self.past_date.year, self.now.year + 1))
        yield self._archived_request(years, list(response.json()))

    def _archived_request(self, years, docs):
        year, *remaining = years
        return Request(
            url=self.archived_attachments_url.format(
                year=year, committee_id=self.committee_id
            ),
            callback=self._parse_archived,
            errback=self._archived_failed,
            cb_kwargs={
                "remaining_years": remaining,
                "docs": docs,
            },
        )

    def _parse_archived(self, response, remaining_years, docs):
        yield self._next_step(remaining_years, docs + response.json())

    def _archived_failed(self, failure):
        kw = failure.request.cb_kwargs
        self.logger.warning(f"Archived request failed: {failure.request.url}")
        yield self._next_step(kw["remaining_years"], kw["docs"])

    def _next_step(self, remaining_years, docs):
        if remaining_years:
            return self._archived_request(remaining_years, docs)

        self.attachments = docs
        return Request(
            url=self.events_url.format(
                start_date=self.past_date.strftime("%m/%d/%y"),
                end_date=self.future_date.strftime("%m/%d/%y"),
                keyword=self.keyword,
            ),
            headers={"User-Agent": self.UA_HEADER},
            callback=self._parse_events,
        )

    def _total_pages(self, response):
        script = " ".join(response.css("script::text").getall())
        match = re.search(r"bootpag\(\s*\{[^}]*total\s*:\s*(\d+)", script)
        return int(match.group(1)) if match else 1

    def _parse_events(self, response, rows=None, page=0, total_pages=None):
        if total_pages is None:
            total_pages = self._total_pages(response)

        rows = (rows or []) + response.css(".EVN_table tbody tr")

        next_page = page + 1
        if next_page < total_pages:
            yield Request(
                url=add_or_replace_parameter(response.url, "Page", str(next_page)),
                callback=self._parse_events,
                headers={"User-Agent": self.UA_HEADER},
                cb_kwargs={"rows": rows, "page": page + 1, "total_pages": total_pages},
            )
        else:
            yield from self.parse(rows)

    def parse(self, rows):
        meetings = {}
        for row in rows:
            start = self._parse_start(row)
            if start is None:
                self.logger.warning("Skipping, no meeting date found.")
                continue

            meeting = Meeting(
                title=self._parse_title(row),
                description="",
                classification=self.classification,
                start=start,
                end=None,
                all_day=False,
                time_notes="",
                location=self.location,
                links=[],
                source=self._parse_source(row),
            )

            meeting["links"] = self._parse_links(meeting)
            meeting["status"] = self._get_status(meeting)
            meeting["id"] = self._get_id(meeting)

            if start in meetings:
                self.logger.info(f"Replacing duplicate meeting at {start}")
            meetings[start] = meeting

        yield from meetings.values()

    def _parse_title(self, row):
        title_txt = (row.css('td[headers="c2"] a::text').get() or "").strip()
        if not title_txt:
            return self.keyword.replace("-", " ").strip()
        return title_txt

    def _parse_start(self, row):
        dt_txt = (row.css('td[headers="c1"]::text').get() or "").strip()
        if not dt_txt:
            return None
        return dateutil_parser(dt_txt)

    def _parse_links(self, meeting):
        """
        The following two links apply universally to all
        Grand Rapids city spiders.
        """
        links = [
            {
                "title": "Meeting cancellations and other public notices can be found on this page",  # noqa
                "href": "https://www.grandrapidsmi.gov/government/public-notices/",
            },
            {
                "title": "YouTube channel",
                "href": "https://www.youtube.com/@TheCityofGrandRapids",
            },
        ]

        meeting_dt = meeting["start"]

        for item in self.attachments or []:
            item_dt = item.get("dateTime")
            if item_dt and dateutil_parser(item_dt) == meeting_dt:
                links.extend(self._parse_doc_item(item))
        return links

    def _parse_doc_item(self, item):
        links = []

        if video_url := item.get("videoUrl", ""):
            links.append({"title": "Video", "href": video_url})

        seen = set()
        for doc in item.get("documentList") or []:
            t_id = doc.get("templateId")
            t_name = doc.get("templateName") or "Document"
            if not t_id or t_id in seen:
                continue
            if "html" in t_name.lower():
                continue
            seen.add(t_id)
            links.append(
                {"title": t_name, "href": self.template_url.format(template_id=t_id)}
            )
        return links

    def _parse_source(self, row):
        relative_url = (row.css('td[headers="c2"] a::attr(href)').get() or "").strip()
        if not relative_url:
            return self.source_url
        return urljoin(self.source_url, relative_url)
