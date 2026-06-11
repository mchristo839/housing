"""
Public Contracts Scotland scraper (STUB).

https://www.publiccontractsscotland.gov.uk/
Provides RSS feeds + search; may have JSON API on the new platform.
"""
from .base import PortalScraper


class PublicContractsScotlandScraper(PortalScraper):
    PORTAL_NAME = "publiccontractsscotland"

    def scrape(self):
        print(f"  [{self.PORTAL_NAME}] not yet implemented")
        return
        yield
