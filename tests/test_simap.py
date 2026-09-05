"""The simap read-API parsers, the cursor walk, and the UID confirmation.

The point of most of these is the last one. simap publishes no UID-indexed
endpoint, so the only honest per-company answer comes from the vendor
directory, where a row carries its own ``uidNo``. These tests pin that the name
is only ever used to *find* candidates and never to decide between them.
"""

from __future__ import annotations

import json

import pytest

from swissco import simap


class _Pages:
    """A client stand-in that hands back recorded pages in order.

    No mocking library, matching the house rule: the fixtures are real captured
    responses and this just serves them.
    """

    def __init__(self, *pages: bytes) -> None:
        self.pages = list(pages)
        self.calls: list[str] = []

    def fetch_project_search_page(self, **kwargs) -> bytes:
        self.calls.append(kwargs.get("last_item", ""))
        return self.pages[min(len(self.calls) - 1, len(self.pages) - 1)]

    def fetch_vendor_search_page(self, **kwargs) -> bytes:
        self.calls.append(kwargs.get("last_item", ""))
        return self.pages[min(len(self.calls) - 1, len(self.pages) - 1)]


class TestProjectSearch:
    def test_a_page_parses_into_projects_and_a_cursor(self, simap_project_page_1):
        page = simap.parse_project_search_page(simap_project_page_1)
        assert len(page.projects) == 20
        assert page.last_item == "20260815|41760"
        assert page.items_per_page == 20

    def test_a_translated_title_is_kept_whole(self, simap_project_page_1):
        page = simap.parse_project_search_page(simap_project_page_1)
        title = page.projects[0].title
        assert title["de"] == "Umbettungstücher und Einwegdecken"
        # The nulls simap sends for untranslated languages are dropped, so an
        # empty mapping means "published in no language", not "field missing".
        assert "en" not in title

    def test_a_lots_project_has_one_head_per_lot(self, simap_project_page_1):
        page = simap.parse_project_search_page(simap_project_page_1)
        lotted = [p for p in page.projects if p.lots_type and len(p.heads) > 1]
        assert lotted, "expected at least one lots project in the fixture"
        assert all(head.publication_id for head in lotted[0].heads)

    def test_a_lots_project_borrows_its_canton_from_the_first_lot(
        self, simap_project_page_1
    ):
        page = simap.parse_project_search_page(simap_project_page_1)
        first = page.projects[0]
        assert json.loads(simap_project_page_1)["projects"][0]["orderAddress"] is None
        assert first.order_address is not None

    def test_a_response_without_a_projects_array_is_a_contract_error(self):
        with pytest.raises(simap.ContractError, match="no projects array"):
            simap.parse_project_search_page(b'{"pagination": {}}')

    def test_a_row_without_an_id_is_a_contract_error(self):
        with pytest.raises(simap.ContractError, match="no id"):
            simap.parse_project_search_page(b'{"projects": [{"projectNumber": "1"}]}')

    def test_an_unparseable_date_is_a_contract_error(self):
        body = b'{"projects": [{"id": "a", "publicationId": "b", "publicationDate": "soon"}]}'
        with pytest.raises(simap.ContractError, match="unparseable date"):
            simap.parse_project_search_page(body)

    def test_invalid_json_is_a_simap_error_not_a_crash(self):
        with pytest.raises(simap.SimapError, match="invalid JSON"):
            simap.parse_project_search_page(b"{not json")

    def test_a_json_array_is_a_contract_error(self):
        with pytest.raises(simap.ContractError, match="expected a JSON object"):
            simap.parse_project_search_page(b"[]")


class TestTheCursorWalk:
    def test_it_follows_the_cursor_to_the_next_page(
        self, simap_project_page_1, simap_project_page_2
    ):
        client = _Pages(simap_project_page_1, simap_project_page_2)
        rows = list(simap.iter_projects(client, limit=25))
        assert len(rows) == 25
        assert client.calls == ["", "20260815|41760"]

    def test_it_stops_at_the_limit_without_fetching_another_page(
        self, simap_project_page_1
    ):
        client = _Pages(simap_project_page_1)
        assert len(list(simap.iter_projects(client, limit=5))) == 5
        assert client.calls == [""]

    def test_a_repeated_cursor_ends_the_walk_rather_than_looping(
        self, simap_project_page_1
    ):
        # The same page for ever: without the guard this would never return.
        client = _Pages(simap_project_page_1)
        rows = list(simap.iter_projects(client, limit=10_000))
        assert len(rows) == 40
        assert client.calls == ["", "20260815|41760"]

    def test_a_page_with_no_cursor_ends_the_walk(self):
        client = _Pages(b'{"projects": [{"id": "a", "publicationId": "b"}], "pagination": {}}')
        assert len(list(simap.iter_projects(client, limit=100))) == 1

    def test_each_page_is_reported_as_it_lands(self, simap_project_page_1):
        seen = []
        client = _Pages(simap_project_page_1)
        list(simap.iter_projects(client, limit=5, on_page=lambda n, so_far: seen.append(n)))
        assert seen == [20]


class TestTheVendorDirectory:
    def test_search_rows_carry_their_own_uid(self, simap_vendor_search):
        page = simap.parse_vendor_search_page(simap_vendor_search)
        assert len(page.vendors) == 20
        assert any(vendor.uid_no.startswith("CHE") for vendor in page.vendors)

    def test_the_vendor_cursor_is_a_name_not_a_date(self, simap_vendor_search):
        assert simap.parse_vendor_search_page(simap_vendor_search).last_item == "ABRAG AG"

    def test_a_profile_parses_with_its_address_and_codes(self, simap_vendor_public):
        profile = simap.parse_vendor_public(simap_vendor_public)
        assert profile.uid_no == "CHE-409.633.691"
        assert profile.name == "Egli Gartenbau AG Sursee"
        assert profile.address.canton_id == "LU"
        assert profile.address.city == "Sursee"

    def test_a_consortium_carries_no_uid_at_all(self, simap_vendor_consortium):
        profile = simap.parse_vendor_public(simap_vendor_consortium)
        assert profile.is_bidding_consortium is True
        assert profile.uid_no == ""
        assert profile.leading_vendor_name

    def test_a_profile_without_an_id_is_a_contract_error(self):
        with pytest.raises(simap.ContractError, match="no id"):
            simap.parse_vendor_public(b'{"name": "x"}')

    def test_a_search_response_without_a_vendors_array_is_a_contract_error(self):
        with pytest.raises(simap.ContractError, match="no vendors array"):
            simap.parse_vendor_search_page(b"{}")


class TestConfirmingOnTheUid:
    def _row(self, name: str, uid: str) -> simap.VendorRow:
        return simap.VendorRow(vendor_id=name.lower(), name=name, uid_no=uid)

    def test_the_matching_uid_is_kept(self):
        rows = [self._row("Egli Gartenbau AG Sursee", "CHE-409.633.691")]
        assert simap.confirmed_by_uid(rows, "CHE-409.633.691") == rows

    def test_punctuation_does_not_decide_it(self):
        rows = [self._row("A", "CHE-409.633.691")]
        assert simap.confirmed_by_uid(rows, "CHE409633691") == rows

    def test_a_near_identical_name_with_another_uid_is_dropped(self):
        # Both of these are real: two unrelated companies, near-identical
        # names, different cantons. A name matcher would return both.
        sursee = self._row("Egli Gartenbau AG Sursee", "CHE-409.633.691")
        uster = self._row("Egli Gartenbau AG Uster", "CHE-428.118.900")
        assert simap.confirmed_by_uid([sursee, uster], "CHE-409.633.691") == [sursee]

    def test_a_row_with_no_uid_is_never_confirmed(self):
        assert simap.confirmed_by_uid([self._row("A consortium", "")], "CHE-1") == []


class TestRows:
    def test_a_tender_row_keeps_its_keys_in_column_order(self, simap_project_page_1):
        project = simap.parse_project_search_page(simap_project_page_1).projects[0]
        assert list(simap.tender_row(project))[:4] == [
            "title",
            "project_number",
            "buyer",
            "canton",
        ]

    def test_a_row_never_carries_a_translation_dict(self, simap_project_page_1):
        page = simap.parse_project_search_page(simap_project_page_1)
        for project in page.projects:
            row = simap.tender_row(project)
            assert isinstance(row["title"], str)
            assert isinstance(row["buyer"], str)

    def test_the_requested_language_wins_when_the_field_has_it(self):
        assert simap.preferred({"de": "Deutsch", "fr": "Français"}, "fr") == "Français"

    def test_a_missing_language_falls_back_rather_than_emptying_the_cell(self):
        assert simap.preferred({"de": "Deutsch"}, "it") == "Deutsch"

    def test_the_default_order_prefers_german_then_french(self):
        assert simap.preferred({"en": "English", "fr": "Français"}) == "Français"

    def test_an_untranslated_field_is_an_empty_string(self):
        assert simap.preferred({}) == ""

    def test_the_newest_publication_is_the_one_reported(self, simap_project_page_1):
        project = simap.parse_project_search_page(simap_project_page_1).projects[0]
        row = simap.tender_row(project)
        assert row["publication_date"] == project.newest_publication_date


class TestPoliteness:
    def test_the_client_refuses_a_host_it_was_not_given(self):
        client = simap.SimapClient(client=object())
        with pytest.raises(ValueError, match="refusing host"):
            client.check_url("https://example.com/api/vendors/v1")

    def test_the_client_refuses_plain_http(self):
        client = simap.SimapClient(client=object())
        with pytest.raises(ValueError, match="non-https"):
            client.check_url("http://www.simap.ch/api/vendors/v1")

    def test_the_client_refuses_the_routes_robots_txt_disallows(self):
        client = simap.SimapClient(client=object())
        with pytest.raises(ValueError, match="robots.txt"):
            client.check_url("https://www.simap.ch/de/project-detail/1")

    def test_the_documented_api_surface_is_allowed(self):
        client = simap.SimapClient(client=object())
        assert client.check_url("https://www.simap.ch/api/vendors/v1")
