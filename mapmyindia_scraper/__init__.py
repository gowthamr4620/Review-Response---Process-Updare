"""
Mappls (MapmyIndia) business-listing scraper and cross-verifier.

Given a Mappls listing link it extracts business name, address, PIN code,
latitude/longitude and phone number - preferring the official Mappls REST API
and falling back to parsing the page - then compares each field against the
values shared in a spreadsheet and writes a colour-coded verification report.

Entry point: python -m mapmyindia_scraper.cli --help
"""

__version__ = "0.1.0"
