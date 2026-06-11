"""
Contracts Finder scraper — GET /Published/Notices/OCDS/Search.

Per the official API docs:
  https://www.contractsfinder.service.gov.uk/apidocumentation/Notices/1/GET-Published-Notice-OCDS-Search

  GET  https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search
  Query params:
    publishedFrom  ISO 8601, lower bound
    publishedTo    ISO 8601, upper bound (optional)
    stages         award (we restrict to award stage)
    limit          1-100, default 100
    cursor         opaque pagination token (alphanumeric, ≤300 chars)

  On rate-limit: HTTP 403, wait 5 minutes before retrying (we wait 130s
  and let it retry up to 3 times — covers the lockout).

We cursor-paginate ONCE through all awards since min_date (no per-keyword
loop), then filter client-side using HOUSING_TITLE / HOUSING_CPV. Each page
saves cursor to disk so the run is resumable.
"""
import datetime
import json
import os
import urllib.parse

from .base import (
    PortalScraper, empty_row, is_housing_title, is_housing_cpv,
    nuts_to_ons,
)
from .findatender import FindATenderScraper


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHECKPOINT = os.path.join(ROOT, "data", "scraped", "raw", "contractsfinder_cursor.txt")


class ContractsFinderScraper(PortalScraper):
    PORTAL_NAME = "contractsfinder"
    SEARCH_URL = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search"
    NOTICE_URL_TPL = "https://www.contractsfinder.service.gov.uk/Notice/{notice_id}"
    RATE_LIMIT_SEC = 6.0    # 12 req/min ceiling
    LOCKOUT_RETRY_SEC = 305  # docs say wait 5 minutes; 305s is a hair over

    def scrape(self):
        builder = FindATenderScraper(self.min_date, self.max_date)
        cursor = self._load_checkpoint()
        seen_ocids = set()
        page = 0
        published_from = f"{self.min_date}T00:00:00"
        published_to = (f"{self.max_date}T23:59:59" if self.max_date
                        else f"{datetime.date.today().isoformat()}T23:59:59")
        if cursor:
            print(f"  [contractsfinder] resuming from checkpoint cursor")
        else:
            print(f"  [contractsfinder] starting from {published_from}")

        while True:
            page += 1
            params = {
                "publishedFrom": published_from,
                "publishedTo": published_to,
                "stages": "award",
                "limit": 100,
            }
            if cursor:
                params["cursor"] = cursor
            try:
                resp = self.get_json(self.SEARCH_URL, params=params)
            except Exception as e:
                print(f"  [contractsfinder] page {page} failed: {e}")
                if cursor:
                    self._save_checkpoint(cursor)
                return
            releases = resp.get("releases") or []
            if not releases:
                print(f"  [contractsfinder] no more releases at cursor {cursor!r}, done")
                if os.path.exists(CHECKPOINT):
                    os.remove(CHECKPOINT)
                return
            yielded_this_page = 0
            for release in releases:
                ocid = release.get("ocid")
                if not ocid or ocid in seen_ocids:
                    continue
                seen_ocids.add(ocid)
                for row in builder._releases_to_rows(release):
                    row["source_portal"] = self.PORTAL_NAME
                    notice_id = release.get("id") or ocid
                    row["source_url"] = self.NOTICE_URL_TPL.format(notice_id=notice_id)
                    yielded_this_page += 1
                    yield row

            # advance cursor
            next_cursor = self._extract_next_cursor(resp)
            if next_cursor:
                cursor = next_cursor
                self._save_checkpoint(cursor)
            else:
                print(f"  [contractsfinder] no next cursor — end of feed")
                if os.path.exists(CHECKPOINT):
                    os.remove(CHECKPOINT)
                return

            if page % 5 == 0:
                print(f"  [contractsfinder] page {page} — {len(seen_ocids)} unique OCIDs seen, "
                      f"{yielded_this_page} housing rows from this page", flush=True)

    @staticmethod
    def _extract_next_cursor(resp):
        """Find the next cursor from the response. Contracts Finder puts it
        in links.next as a fully-formed URL; we extract the cursor param."""
        links = resp.get("links") or {}
        next_url = links.get("next")
        if not next_url:
            return None
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(next_url).query)
        return qs.get("cursor", [None])[0]

    @staticmethod
    def _load_checkpoint():
        try:
            with open(CHECKPOINT) as f:
                v = f.read().strip()
                return v or None
        except Exception:
            return None

    @staticmethod
    def _save_checkpoint(cursor):
        os.makedirs(os.path.dirname(CHECKPOINT), exist_ok=True)
        with open(CHECKPOINT, "w") as f:
            f.write(cursor)
