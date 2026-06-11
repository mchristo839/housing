"""
Sell2Wales scraper (STUB — to implement when Welsh coverage is in scope).

Welsh Government's procurement portal: https://www.sell2wales.gov.wales/

It exposes search but no documented JSON API. Likely needs HTML scraping
of the search results pages with BeautifulSoup, then OCDS-format fetches
for each notice.
"""
from .base import PortalScraper


class Sell2WalesScraper(PortalScraper):
    PORTAL_NAME = "sell2wales"

    def scrape(self):
        # TODO: implement
        # 1. POST to https://www.sell2wales.gov.wales/search/search.aspx with
        #    keywords + noticeType=Awarded
        # 2. Parse results table, follow each notice link
        # 3. Scrape notice details (supplier, value, region)
        print(f"  [{self.PORTAL_NAME}] not yet implemented")
        return
        yield  # pragma: no cover
