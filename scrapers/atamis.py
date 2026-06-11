"""
Atamis scraper (STUB).

Atamis (https://atamis.co.uk) is the NHS-favoured procurement platform that
replaced Bravo for many ICBs/Trusts since 2023. No public JSON API documented;
the public-facing search at https://atamis-1928.cloudforce.com/s/Welcome
is likely the only entry point.

Most NHS housing-related awards on Atamis are ALSO published on Find-a-Tender
(legal requirement above the threshold), so this is a secondary source for
catching anything that slips between. Implement later if there's a measurable
gap after running FTS + Contracts Finder.
"""
from .base import PortalScraper


class AtamisScraper(PortalScraper):
    PORTAL_NAME = "atamis"

    def scrape(self):
        print(f"  [{self.PORTAL_NAME}] not yet implemented")
        return
        yield
