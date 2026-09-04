"""UID normalisation, the SPARQL builder, and the row shapes."""

from __future__ import annotations

import re

import pytest
from zefix_parser.lindas import parse_entity_page

from swissco import companies
from swissco._sparql import escape_literal


class TestResolveUid:
    @pytest.mark.parametrize(
        "value",
        [
            "CHE-444.420.929",
            "CHE444420929",
            "che-444.420.929",
            "  CHE-444.420.929  ",
            "VAT: CHE-444.420.929 MWST",
        ],
    )
    def test_accepts_every_punctuation(self, value):
        assert companies.resolve_uid(value) == "CHE444420929"

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "not a uid",
            "CHE-123.456.789",  # the placeholder: correct shape, bad check digit
            "CHE-444.420.928",  # one digit off the real one
            "CHE44442092",  # too short
        ],
    )
    def test_rejects_everything_else(self, value):
        with pytest.raises(companies.NotAUid):
            companies.resolve_uid(value)

    def test_the_message_names_the_value(self):
        with pytest.raises(companies.NotAUid, match="nope"):
            companies.resolve_uid("nope")


class TestSearchQuery:
    def test_matches_name_and_purpose(self):
        query = companies.build_search_query("machining")
        assert 'CONTAINS(LCASE(STR(?searchName)), "machining")' in query
        assert 'CONTAINS(LCASE(STR(?searchPurpose)), "machining")' in query

    def test_lowercases_the_term(self):
        assert '"machining"' in companies.build_search_query("MaChiNing")

    def test_canton_is_uppercased_and_filtered(self):
        query = companies.build_search_query("x", canton="vd")
        assert 'UCASE(STR(?searchCanton)) = "VD"' in query

    def test_canton_is_absent_when_not_asked_for(self):
        assert "?searchCanton" not in companies.build_search_query("x")

    def test_legal_form_becomes_a_uri(self):
        query = companies.build_search_query("x", legal_form="0106")
        assert f"<{companies.LEGAL_FORM_BASE}0106>" in query

    def test_limit_reaches_the_query(self):
        assert "LIMIT 7" in companies.build_search_query("x", limit=7)

    def test_limit_must_be_positive(self):
        with pytest.raises(ValueError):
            companies.build_search_query("x", limit=0)

    def test_a_quote_cannot_close_the_literal(self):
        """A term ending the literal early would let the rest be read as syntax."""
        query = companies.build_search_query('bad" } INSERT { ?s ?p ?o } #')
        assert re.search(r'(?<!\\)" \}', query) is None
        assert 'bad\\" } insert' in query.lower()

    def test_a_backslash_cannot_smuggle_a_quote_back_in(self):
        query = companies.build_search_query('back\\slash')
        assert "back\\\\slash" in query

    def test_a_canton_is_escaped_too(self):
        query = companies.build_search_query("x", canton='V"')
        assert '\\"' in query


class TestEscapeLiteral:
    @pytest.mark.parametrize(
        ("raw", "escaped"),
        [
            ("plain", "plain"),
            ('a"b', 'a\\"b'),
            ("a\\b", "a\\\\b"),
            ("a\nb", "a\\nb"),
            ("a\rb", "a\\rb"),
            ('\\"', '\\\\\\"'),
        ],
    )
    def test_escapes(self, raw, escaped):
        assert escape_literal(raw) == escaped


class TestRows:
    def test_lookup_row_punctuates_the_uid(self, lindas_lookup):
        entity = parse_entity_page(lindas_lookup)[0]
        row = companies.entity_row(entity)
        assert entity.uid == "CHE444420929"
        assert row["uid"] == "CHE-444.420.929"
        assert row["legal_name"] == "Baumberger Bau AG"
        assert row["canton"] == "BE"
        assert row["municipality"] == "Koppigen"
        assert row["address"] == "Hauptstrasse 6, 3425 Koppigen"

    def test_lookup_row_punctuates_the_chid(self, lindas_lookup):
        entity = parse_entity_page(lindas_lookup)[0]
        assert companies.entity_row(entity)["chid"] == "CH-036.9.103.786-9"

    def test_search_row_is_narrower_than_lookup(self, lindas_lookup):
        entity = parse_entity_page(lindas_lookup)[0]
        search = set(companies.search_row(entity))
        lookup = set(companies.entity_row(entity))
        assert search < lookup
        assert "zefix_uri" not in search

    def test_search_results_are_all_in_the_asked_canton(self, lindas_search):
        entities = parse_entity_page(lindas_search)
        assert entities
        assert {e.canton for e in entities} == {"VD"}

    def test_search_results_match_the_term(self, lindas_search):
        for entity in parse_entity_page(lindas_search):
            haystack = f"{entity.legal_name} {entity.purpose}".lower()
            assert "usinage" in haystack
