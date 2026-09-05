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

One fixture is deliberately altered rather than captured whole. ARAMIS publishes
researchers' names, e-mail addresses and telephone numbers on a project detail,
and ``swissco`` reads none of them. Republishing a real researcher's contact
details in a public repository to prove that would be a strange way to keep the
promise, so ``aramis/project_detail_no_uid.json`` carries invented people in
those fields. Everything the parser actually reads is as captured.
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


@pytest.fixture
def gleif_record_squashed() -> bytes:
    """A search hit filed under the squashed UID: Aargauische Kantonalbank."""
    return load("gleif", "record_squashed_uid.json")


@pytest.fixture
def gleif_record_dotted() -> bytes:
    """A search hit filed under the dotted UID: UBS Switzerland AG."""
    return load("gleif", "record_dotted_uid.json")


@pytest.fixture
def gleif_search_empty() -> bytes:
    """A search that found no LEI at all, which is the common Swiss outcome."""
    return load("gleif", "search_empty.json")


@pytest.fixture
def gleif_direct_parent() -> bytes:
    """UBS Switzerland AG's direct parent: UBS AG."""
    return load("gleif", "direct_parent.json")


@pytest.fixture
def gleif_ultimate_parent() -> bytes:
    """The entity at the top of that chain: UBS Group AG."""
    return load("gleif", "ultimate_parent.json")


@pytest.fixture
def gleif_direct_children() -> bytes:
    """One page of UBS AG's 38 direct children, with the total in the meta."""
    return load("gleif", "direct_children.json")


@pytest.fixture
def gleif_children_empty() -> bytes:
    """A children response for an entity that consolidates nothing."""
    return load("gleif", "children_empty.json")


@pytest.fixture
def gleif_relation_404() -> bytes:
    """The body GLEIF returns when an entity reports no parent."""
    return load("gleif", "relation_not_found.json")


@pytest.fixture
def aramis_search() -> bytes:
    """A contractor search page: five projects, and the matched total."""
    return load("aramis", "projectlist_search.json")


@pytest.fixture
def aramis_search_confirmed() -> bytes:
    """The search page whose single hit carries the UID under test."""
    return load("aramis", "projectlist_confirmed.json")


@pytest.fixture
def aramis_detail_confirmed() -> bytes:
    """That hit hydrated: MPAssist AG as an Innosuisse implementation partner."""
    return load("aramis", "project_detail_confirmed.json")


@pytest.fixture
def aramis_detail_uid() -> bytes:
    """A detail carrying a participant UID: Storz Medical AG on project 60596."""
    return load("aramis", "project_detail_uid.json")


@pytest.fixture
def aramis_detail_no_uid() -> bytes:
    """A detail with no participant UID, and invented people in the PII fields."""
    return load("aramis", "project_detail_no_uid.json")


@pytest.fixture
def aramis_fault() -> bytes:
    """An A2AFault body, which the service sends with HTTP 200 as well as 500."""
    return load("aramis", "fault_count.json")
