"""
eTendersNI scraper (STUB).

https://etendersni.gov.uk/ — NI procurement portal.
"""
from .base import PortalScraper


class ETendersNIScraper(PortalScraper):
    PORTAL_NAME = "etendersni"

    def scrape(self):
        print(f"  [{self.PORTAL_NAME}] not yet implemented")
        return
        yield
