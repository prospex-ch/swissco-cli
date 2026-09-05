"""Fixtures for the offline suite.

Every response was captured once from the live endpoints and lives under
``tests/fixtures``. Nothing here opens a network connection, so the suite runs
in a sandbox and cannot start failing because a company changed its address.

The two FINMA files are whole, not trimmed. Their parser checks itself against
the footer total FINMA publishes, and a hand-shortened workbook would mean
hand-editing that total -- which would test the fiction rather than the
contract. The tests that need input FINMA does not publish, such as a workbook
with a missing column, build it in memory and say so; you cannot capture a
response that does not exist upstream.
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load(*parts: str) -> bytes:
    """The bytes of one recorded response."""
    return (FIXTURES.joinpath(*parts)).read_bytes()


@pytest.fixture
def lindas_lookup() -> bytes:
    """A detail-by-UID response for CHE-444.420.929 (Baumberger Bau AG)."""
    return load("lindas", "lookup.json")


@pytest.fixture
def lindas_search() -> bytes:
    """A search response: "usinage" in canton VD, five hits."""
    return load("lindas", "search.json")


@pytest.fixture
def shab_list_page() -> bytes:
    """One bulk-export page: twelve publications from 2026-09-03."""
    return load("shab", "list-page.xml")


@pytest.fixture
def shab_body_hr02() -> bytes:
    """One HR02 mutation body."""
    return load("shab", "body-HR02.xml")


@pytest.fixture
def shab_body_hr03() -> bytes:
    """One HR03 deletion body."""
    return load("shab", "body-HR03.xml")


@pytest.fixture
def simap_project_page_1() -> bytes:
    """A project-search page, with a cursor pointing at the next one."""
    return load("simap", "project_search_page_1.json")


@pytest.fixture
def simap_project_page_2() -> bytes:
    """The continuation of that search."""
    return load("simap", "project_search_page_2.json")


@pytest.fixture
def simap_vendor_search() -> bytes:
    """A vendor-directory search page. The rows carry uidNo themselves."""
    return load("simap", "vendor_search_page_1.json")


@pytest.fixture
def simap_vendor_public() -> bytes:
    """One vendor profile: Egli Gartenbau AG Sursee, CHE-409.633.691."""
    return load("simap", "vendor_public.json")


@pytest.fixture
def simap_vendor_consortium() -> bytes:
    """A bidding consortium: no uidNo at all, because it is not a legal entity."""
    return load("simap", "vendor_public_consortium.json")


@pytest.fixture
def finma_workbook() -> bytes:
    """FINMA's authorised banks and securities firms workbook, as published."""
    return load("finma", "beh.xlsx")


@pytest.fixture
def finma_crosswalk() -> bytes:
    """FINMA's (name, city, authorisation type) -> UID crosswalk, as published."""
    return load("finma", "uid.csv")
