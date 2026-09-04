"""Fixtures for the offline suite.

Every response was captured once from the live endpoints and lives under
``tests/fixtures``. Nothing here opens a network connection, so the suite runs
in a sandbox and cannot start failing because a company changed its address.
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
