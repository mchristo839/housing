"""
Find-a-Tender Service scraper.

The Find-a-Tender public API is a BULK OCDS feed, not a search endpoint:
  https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages

There's no `q=`/keyword filter on the public API — the web UI does its
search client-side after fetching pages. So this scraper:

  1. Cursor-paginates from --from date through all release packages
  2. Filters each release client-side by HOUSING_TITLE / CPV
  3. Yields normalised rows for the hits

API rate limit: 12 requests/minute. The base scraper's RATE_LIMIT_SEC = 6
keeps us inside that. A run from 2020-01-01 → today is in the high
thousands of pages → expect ~6-10 hours unattended.
"""
import datetime
from .base import (
    PortalScraper, empty_row, is_housing_title, is_housing_cpv,
    nuts_to_ons,
)


class FindATenderScraper(PortalScraper):
    PORTAL_NAME = "findatender"
    BASE_URL = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages"
    NOTICE_URL_TPL = "https://www.find-tender.service.gov.uk/Notice/{ocid}"
    # FTS public API rate limit is 12 req/min — 6 seconds between calls is safe
    RATE_LIMIT_SEC = 6.0

    def scrape(self):
        # cursor is an ISO 8601 datetime; we paginate forward through release packages
        cursor = f"{self.min_date}T00:00:00"
        seen_ocids = set()
        page = 0
        while True:
            page += 1
            params = {"cursor": cursor, "limit": 100}
            try:
                resp = self.get_json(self.BASE_URL, params=params)
            except Exception as e:
                print(f"  [findatender] page {page} error at cursor {cursor}: {e}")
                return
            releases = resp.get("releases", [])
            if not releases:
                return
            for release in releases:
                ocid = release.get("ocid")
                if not ocid or ocid in seen_ocids:
                    continue
                seen_ocids.add(ocid)
                for row in self._releases_to_rows(release):
                    yield row
            # advance cursor — FTS returns links.next OR we use the last release's date
            links = resp.get("links") or {}
            next_url = links.get("next")
            if next_url:
                # the next URL already has cursor baked in; pull the cursor out
                # the API also tells us we're at the end with empty `releases` next time
                # we override the base URL on next loop
                self.BASE_URL = next_url.split("?")[0]
                # extract cursor from next URL if possible
                import urllib.parse
                qs = urllib.parse.parse_qs(urllib.parse.urlsplit(next_url).query)
                cursor = qs.get("cursor", [cursor])[0]
            else:
                # advance manually using the last release's date
                last_date = None
                for r in releases:
                    d = r.get("date") or ""
                    if d and (last_date is None or d > last_date):
                        last_date = d
                if not last_date or last_date <= cursor:
                    return
                cursor = last_date
            # date guard
            if self.max_date and cursor[:10] > self.max_date:
                return
            if page % 10 == 0:
                print(f"  [findatender] cursor={cursor[:10]} (page {page})")

    # ── Release → normalised rows ──────────────────────────────────────────
    def _releases_to_rows(self, release):
        ocid = release.get("ocid", "")
        notice_url = self.NOTICE_URL_TPL.format(ocid=ocid)
        tender = release.get("tender", {}) or {}
        buyer = (release.get("buyer", {}) or {}).get("name", "")
        awards = release.get("awards", []) or []

        # only interested in award stage releases
        if not awards:
            return

        title = tender.get("title", "") or ""
        cpv_codes = []
        for item in tender.get("items", []) or []:
            classification = item.get("classification") or {}
            scheme = (classification.get("scheme") or "").upper()
            if scheme == "CPV" and classification.get("id"):
                cpv_codes.append(str(classification["id"]))

        # MUST look like housing — title OR CPV
        if not (is_housing_title(title) or is_housing_cpv(cpv_codes)):
            return

        # geography from delivery address or buyer NUTS
        ons_region = ""
        for addr in (tender.get("deliveryAddresses") or []):
            nuts = addr.get("region") or ""
            if nuts:
                ons_region = nuts_to_ons(nuts) or ons_region
                if ons_region:
                    break
        if not ons_region:
            buyer_id = (release.get("buyer", {}) or {}).get("id", "")
            for party in release.get("parties", []) or []:
                if party.get("id") == buyer_id:
                    nuts = ((party.get("address") or {}).get("region") or "")
                    if nuts:
                        ons_region = nuts_to_ons(nuts)
                        break

        for award in awards:
            if (award.get("status") or "").lower() not in ("active", "complete", ""):
                continue
            value_obj = award.get("value") or {}
            value_gbp = (value_obj.get("amount") if value_obj.get("currency") == "GBP" else None)
            award_date = award.get("date", "")[:10] if award.get("date") else ""

            for supplier in award.get("suppliers", []) or []:
                row = empty_row()
                row["Company"] = (supplier.get("name") or "").strip()
                if not row["Company"]:
                    continue
                row["Sector"] = "Housing"
                row["Council"] = (buyer or "").strip()
                row["Contracts (this council, this sector)"] = 1
                row["Categories"] = self._categorise(title, cpv_codes)
                row["Most Recent Award"] = self._fmt_date(award_date)
                row["Contract Titles"] = title.strip()
                row["ONS Region"] = ons_region
                row["Commissioner Type"] = self._classify_buyer(buyer)
                row["Geographic Scope"] = self._classify_scope(buyer, title, ons_region)
                row["source_portal"] = self.PORTAL_NAME
                row["source_url"] = notice_url
                row["source_id"] = ocid
                row["scraped_at"] = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                row["cpv_codes"] = ";".join(cpv_codes)
                row["contract_value_gbp"] = value_gbp or ""
                row["status"] = award.get("status", "")
                yield row

    @staticmethod
    def _fmt_date(iso):
        if not iso or len(iso) < 10:
            return ""
        try:
            d = datetime.date.fromisoformat(iso[:10])
            return d.strftime("%d/%m/%Y")
        except Exception:
            return ""

    @staticmethod
    def _categorise(title, cpv_codes):
        t = (title or "").lower()
        if "asylum" in t or "dispersal" in t:
            return "Asylum housing | Emergency accommodation"
        if "emergency accommodation" in t or "temporary accommodation" in t or "homeless" in t:
            return "Emergency accommodation | Emergency housing"
        if "cas-2" in t or "bail accommodation" in t or "approved premises" in t:
            return "Bail accommodation | Probation accommodation | Emergency accommodation"
        if "cas-3" in t or "probation accommodation" in t or "prison leaver" in t:
            return "Probation accommodation | Move-on accommodation | Supported accommodation"
        if "extra care" in t:
            return "Supported living | Extra care"
        if "supported living" in t or "supported accommodation" in t:
            return "Supported living | Supported accommodation"
        if "community accommodation" in t:
            return "Community accommodation | Supported accommodation"
        return "Supported accommodation"

    @staticmethod
    def _classify_buyer(buyer):
        b = (buyer or "").lower()
        if "county council" in b:
            return "County Council"
        if any(k in b for k in ["council", "borough", "city of london corporation"]):
            return "Local Council"
        if "nhs" in b or "icb" in b or "ccg" in b or "trust" in b:
            return "NHS"
        if any(k in b for k in ["ministry of", "department for", "home office",
                                 "hmpps", "national highways", "cabinet office"]):
            return "National Government"
        if any(k in b for k in ["espo", "ypo", "consortium", "framework",
                                 "procurement", "shared services"]):
            return "Regional Framework"
        if "housing" in b and ("association" in b or "trust" in b or "group" in b):
            return "Housing Association"
        return "Other"

    @staticmethod
    def _classify_scope(buyer, title, region):
        b = (buyer or "").lower()
        t = (title or "").lower()
        if "pan-london" in t or "all boroughs" in t or "region-wide" in t:
            return "Regional"
        if "ministry of" in b or "home office" in b or "hmpps" in b:
            return "National" if region == "National" else "Regional"
        if "county council" in b:
            return "County"
        if "ccg" in b or "icb" in b or "trust" in b:
            return "Local"
        return "Local"
