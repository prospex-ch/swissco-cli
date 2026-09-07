"""List-page parsing, the client-side filters, and deduplication."""

from __future__ import annotations

from datetime import date

import pytest
from shab_parser import PublicationRef, PublicationState

from swissco import publications
from swissco.publications import ListEntry


def entry(
    external_id: str,
    *,
    canton: str = "ZH",
    sub_rubric: str = "HR02",
    day: date = date(2026, 9, 3),
    state: str = "PUBLISHED",
    titles: dict | None = None,
) -> ListEntry:
    return ListEntry(
        ref=PublicationRef(
            external_id=external_id,
            publication_date=day,
            language="de",
            url=f"https://example.invalid/{external_id}",
            publication_state=state,
        ),
        sub_rubric=sub_rubric,
        canton=canton,
        titles=titles or {"de": f"Mutation {external_id} AG"},
    )


class TestParseListPage:
    def test_reads_the_total(self, shab_list_page):
        _entries, total = publications.parse_list_page(shab_list_page)
        assert total == 1027

    def test_reads_every_publication(self, shab_list_page):
        entries, _total = publications.parse_list_page(shab_list_page)
        assert len(entries) == 12

    def test_keeps_the_meta_the_library_drops(self, shab_list_page):
        """cantons, subRubric and the four titles are why this parser exists."""
        entries, _total = publications.parse_list_page(shab_list_page)
        first = entries[0]
        assert first.canton
        assert first.sub_rubric in ("HR01", "HR02", "HR03")
        assert set(first.titles) <= {"de", "fr", "it", "en"}
        assert first.titles

    def test_builds_a_usable_ref(self, shab_list_page):
        entries, _total = publications.parse_list_page(shab_list_page)
        ref = entries[0].ref
        assert ref.url.startswith("https://amtsblattportal.ch/api/v1/publications/")
        assert ref.publication_date == date(2026, 9, 3)
        assert ref.publication_state == "PUBLISHED"
        assert ref.language in ("de", "fr", "it")

    def test_an_empty_page_yields_nothing(self):
        xml = b'<bulk:bulk-export xmlns:bulk="https://shab.ch/bulk-export"><total>0</total></bulk:bulk-export>'
        assert publications.parse_list_page(xml) == ([], 0)


class TestTitle:
    def test_prefers_the_publications_own_language(self):
        e = entry("x", titles={"de": "Deutsch", "fr": "Français"})
        assert e.title == "Deutsch"

    def test_falls_back_to_any_language(self):
        e = entry("x", titles={"fr": "Français"})
        assert e.title == "Français"

    def test_no_titles_is_an_empty_string(self):
        blank = ListEntry(ref=entry("x").ref, titles={})
        assert blank.title == ""

    def test_titles_default_to_a_dict_not_none(self):
        assert ListEntry(ref=entry("x").ref).titles == {}


class TestFilters:
    def test_no_filters_keeps_everything(self):
        entries = [entry("a"), entry("b", canton="BE")]
        assert publications.filter_entries(entries) == entries

    def test_canton(self):
        entries = [entry("a", canton="ZH"), entry("b", canton="BE")]
        kept = publications.filter_entries(entries, cantons=["BE"])
        assert [e.ref.external_id for e in kept] == ["b"]

    def test_canton_is_case_insensitive(self):
        kept = publications.filter_entries([entry("a", canton="ZH")], cantons=["zh"])
        assert len(kept) == 1

    def test_several_cantons(self):
        entries = [entry("a", canton="ZH"), entry("b", canton="BE"), entry("c", canton="VD")]
        kept = publications.filter_entries(entries, cantons=["ZH", "VD"])
        assert [e.ref.external_id for e in kept] == ["a", "c"]

    def test_sub_rubric(self):
        entries = [entry("a", sub_rubric="HR01"), entry("b", sub_rubric="HR03")]
        kept = publications.filter_entries(entries, sub_rubrics=["HR03"])
        assert [e.ref.external_id for e in kept] == ["b"]

    def test_since_and_until_are_inclusive(self):
        entries = [
            entry("a", day=date(2026, 9, 1)),
            entry("b", day=date(2026, 9, 2)),
            entry("c", day=date(2026, 9, 3)),
        ]
        kept = publications.filter_entries(
            entries, since=date(2026, 9, 2), until=date(2026, 9, 3)
        )
        assert [e.ref.external_id for e in kept] == ["b", "c"]

    def test_query_matches_any_language(self):
        """A French word finds a German publication whose French title has it."""
        entries = [entry("a", titles={"de": "Mutation Muster AG", "fr": "Radiation Muster AG"})]
        assert publications.filter_entries(entries, query="radiation")
        assert publications.filter_entries(entries, query="MUTATION")
        assert not publications.filter_entries(entries, query="fusion")

    def test_filters_compose(self):
        entries = [
            entry("a", canton="ZH", sub_rubric="HR01"),
            entry("b", canton="ZH", sub_rubric="HR02"),
            entry("c", canton="BE", sub_rubric="HR01"),
        ]
        kept = publications.filter_entries(entries, cantons=["ZH"], sub_rubrics=["HR01"])
        assert [e.ref.external_id for e in kept] == ["a"]

    def test_blank_filter_values_are_ignored(self):
        entries = [entry("a")]
        assert publications.filter_entries(entries, cantons=["", "  "]) == entries


class TestDedupe:
    def test_cancelled_supersedes_published(self):
        entries = [entry("a", state="PUBLISHED"), entry("a", state="CANCELLED")]
        kept = publications.dedupe(entries)
        assert len(kept) == 1
        assert kept[0].ref.publication_state == "CANCELLED"

    def test_order_of_arrival_does_not_matter(self):
        entries = [entry("a", state="CANCELLED"), entry("a", state="PUBLISHED")]
        assert publications.dedupe(entries)[0].ref.publication_state == "CANCELLED"

    def test_sorted_by_date_then_id(self):
        entries = [
            entry("b", day=date(2026, 9, 3)),
            entry("a", day=date(2026, 9, 3)),
            entry("c", day=date(2026, 9, 1)),
        ]
        assert [e.ref.external_id for e in publications.dedupe(entries)] == ["c", "a", "b"]


class TestListUrl:
    def test_carries_only_the_parameters_the_api_honours(self):
        url = publications.list_url(
            "https://example.invalid/api/v1", date(2026, 1, 1), date(2026, 1, 2),
            "PUBLISHED", 0, 2000,
        )
        assert "tenant=shab" in url
        assert "rubrics=HR" in url
        assert "publicationDate.start=2026-01-01" in url
        assert "publicationDate.end=2026-01-02" in url

    def test_omits_the_parameters_the_api_ignores(self):
        url = publications.list_url(
            "https://example.invalid/api/v1", date(2026, 1, 1), date(2026, 1, 2),
            "PUBLISHED", 0, 2000,
        )
        for ignored in ("cantons=", "subRubrics=", "q=", "keywords="):
            assert ignored not in url

    def test_the_state_is_a_string_not_an_enum_repr(self):
        """PublicationState is a str enum, and its repr is a 400 from the API."""
        url = publications.list_url(
            "https://example.invalid/api/v1", date(2026, 1, 1), date(2026, 1, 1),
            PublicationState.PUBLISHED.value, 0, 2000,
        )
        assert "publicationStates=PUBLISHED" in url
        assert "PublicationState." not in url


class TestRows:
    def test_entry_row(self, shab_list_page):
        entries, _total = publications.parse_list_page(shab_list_page)
        row = publications.entry_row(entries[0])
        assert row["publication_date"] == "2026-09-03"
        assert set(row) == {
            "publication_date", "canton", "sub_rubric", "title",
            "language", "state", "id", "url",
        }


class TestEstimate:
    def test_a_short_range_says_so(self):
        assert "One or two" in publications.estimate(date(2026, 9, 3), date(2026, 9, 4))

    def test_a_long_range_counts_windows_and_both_states(self):
        note = publications.estimate(date(2026, 1, 1), date(2026, 12, 31))
        assert "windows" in note
        assert "both" in note
