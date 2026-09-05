"""The GLEIF record parsers, the two UID spellings, and the absent parent.

Three things carry weight here. GLEIF stores a Swiss register number in either
spelling, so both have to resolve and the cheaper one has to be tried first. A
404 on a relationship is an answer rather than a failure, and reading it as a
failure would turn "this company reports no parent" into an error the user has
to interpret. And a parent is an accounting relationship, which the row copy
has to keep saying.
"""

from __future__ import annotations

import pytest

from swissco import gleif


class _Responses:
    """A client stand-in serving recorded bodies, keyed on what was asked for.

    No mocking library, matching the house rule: the fixtures are captured
    responses and this hands them back while recording the calls.
    """

    def __init__(self, *, by_spelling=None, relations=None) -> None:
        self.by_spelling = by_spelling or {}
        self.relations = relations or {}
        self.spellings: list[str] = []
        self.relation_calls: list[str] = []

    def fetch_records_by_registered_as(self, value: str) -> bytes:
        self.spellings.append(value)
        return self.by_spelling.get(value, b'{"data": []}')

    def fetch_relation(self, lei: str, relation: str, *, page_size: int = 0) -> bytes | None:
        self.relation_calls.append(relation)
        return self.relations.get(relation)


class TestParsingARecord:
    def test_a_search_hit_carries_the_lei_and_the_register_number(self, gleif_record_dotted):
        records = gleif.parse_records(gleif_record_dotted)
        assert len(records) == 1
        assert records[0].lei == "549300WOIFUSNYH0FL22"
        assert records[0].legal_name == "UBS Switzerland AG"
        assert records[0].registered_as == "CHE-412.669.376"
        assert records[0].jurisdiction == "CH"
        assert records[0].status == "ACTIVE"

    def test_a_search_that_found_nothing_is_an_empty_tuple(self, gleif_search_empty):
        assert gleif.parse_records(gleif_search_empty) == ()

    def test_registration_dates_and_former_names_survive(self, gleif_record_squashed):
        record = gleif.parse_records(gleif_record_squashed)[0]
        assert record.initial_registration_date.year == 2012
        assert record.registration_status == "ISSUED"
        assert "Banque Cantonale d'Argovie" in record.other_names

    def test_a_response_without_a_data_array_is_a_contract_error(self):
        with pytest.raises(gleif.ContractError, match="no data array"):
            gleif.parse_records(b'{"meta": {}}')

    def test_an_entry_without_an_lei_is_a_contract_error(self):
        with pytest.raises(gleif.ContractError, match="no LEI"):
            gleif.parse_records(b'{"data": [{"attributes": {"entity": {}}}]}')

    def test_an_unparseable_date_is_a_contract_error(self):
        body = (
            b'{"data": [{"id": "X", "attributes": {"lei": "X", '
            b'"registration": {"initialRegistrationDate": "soon"}}}]}'
        )
        with pytest.raises(gleif.ContractError, match="unparseable"):
            gleif.parse_records(body)

    def test_invalid_json_is_a_gleif_error_rather_than_a_crash(self):
        with pytest.raises(gleif.GleifError, match="invalid JSON"):
            gleif.parse_records(b"<html>maintenance</html>")


class TestTheTwoUidSpellings:
    """GLEIF stores whichever spelling the entity filed, and both are real."""

    def test_the_squashed_form_resolves(self, gleif_record_squashed):
        client = _Responses(by_spelling={"CHE105845287": gleif_record_squashed})
        record = gleif.find_by_uid(client, "CHE-105.845.287")
        assert record.legal_name == "Aargauische Kantonalbank"

    def test_the_dotted_form_resolves_too(self, gleif_record_dotted):
        client = _Responses(by_spelling={"CHE-412.669.376": gleif_record_dotted})
        record = gleif.find_by_uid(client, "CHE412669376")
        assert record.legal_name == "UBS Switzerland AG"

    def test_the_dotted_form_is_only_tried_after_the_squashed_one(
        self, gleif_record_squashed, gleif_record_dotted
    ):
        both = {
            "CHE105845287": gleif_record_squashed,
            "CHE-105.845.287": gleif_record_dotted,
        }
        client = _Responses(by_spelling=both)
        record = gleif.find_by_uid(client, "CHE-105.845.287")
        assert client.spellings == ["CHE105845287"]
        assert record.legal_name == "Aargauische Kantonalbank"

    def test_a_company_with_no_lei_costs_both_spellings_and_returns_none(self):
        client = _Responses()
        assert gleif.find_by_uid(client, "CHE-444.420.929") is None
        assert client.spellings == ["CHE444420929", "CHE-444.420.929"]

    def test_the_dotted_formatter_leaves_a_malformed_value_alone(self):
        assert gleif.dotted("CHE105845287") == "CHE-105.845.287"
        assert gleif.dotted("CHE-105.845.287") == "CHE-105.845.287"
        assert gleif.dotted("not a uid") == "not a uid"


class TestTheGroup:
    def test_both_parents_are_read_as_related_entities(
        self, gleif_direct_parent, gleif_ultimate_parent
    ):
        client = _Responses(
            relations={
                "direct-parent": gleif_direct_parent,
                "ultimate-parent": gleif_ultimate_parent,
            }
        )
        found = gleif.group(client, "549300WOIFUSNYH0FL22")
        assert found.direct_parent.legal_name == "UBS AG"
        assert found.ultimate_parent.legal_name == "UBS Group AG"
        assert found.direct_parent.label() == "UBS AG (BFM8T61CT2L1QCEMIK50, CH)"

    def test_an_entity_reporting_no_parent_is_an_absence_not_a_failure(self):
        """GLEIF answers 404 for "this entity reports no parent"."""
        client = _Responses()
        found = gleif.group(client, "HTQNUFL6OI5TZ7V7SI73")
        assert found.direct_parent is None
        assert gleif.lei_row(gleif.LeiRecord(lei="X"), found)["direct_parent"] == "none reported"

    def test_children_are_not_fetched_unless_they_are_asked_for(self, gleif_direct_parent):
        client = _Responses(relations={"direct-parent": gleif_direct_parent})
        gleif.group(client, "X")
        assert client.relation_calls == ["direct-parent", "ultimate-parent"]

    def test_a_children_page_carries_the_whole_sets_total(self, gleif_direct_children):
        page = gleif.parse_related_page(gleif_direct_children)
        assert page.total == 38
        assert len(page.entities) == 15
        assert page.entities[0].jurisdiction == "BR"

    def test_an_entity_that_consolidates_nothing_counts_zero(self, gleif_children_empty):
        page = gleif.parse_related_page(gleif_children_empty)
        assert page.total == 0
        assert page.entities == ()


class TestTheRelationStatusPolicy:
    class _Response:
        def __init__(self, status: int) -> None:
            self.status_code = status
            self.headers: dict[str, str] = {}

    def test_a_404_on_a_relation_is_raised_as_an_absence(self):
        client = gleif.GleifClient(client=object())
        url = f"{gleif.BASE}/lei-records/X/direct-parent"
        with pytest.raises(gleif.RelationAbsent):
            client.check_response(self._Response(404), url)

    def test_a_404_on_a_record_stays_a_permanent_failure(self):
        from swissco._http import HttpError

        client = gleif.GleifClient(client=object())
        with pytest.raises(HttpError) as caught:
            client.check_response(self._Response(404), f"{gleif.BASE}/lei-records/X")
        assert not isinstance(caught.value, gleif.RelationAbsent)

    def test_a_paged_children_url_is_still_recognised_as_a_relation(self):
        client = gleif.GleifClient(client=object())
        url = f"{gleif.BASE}/lei-records/X/direct-children?page%5Bsize%5D=20"
        with pytest.raises(gleif.RelationAbsent):
            client.check_response(self._Response(404), url)

    def test_a_relation_the_api_does_not_have_is_refused_before_the_request(self):
        client = gleif.GleifClient(client=object())
        with pytest.raises(ValueError, match="unknown GLEIF relation"):
            client.fetch_relation("X", "grandparent")


class TestRows:
    def test_a_parent_is_reported_as_the_entity_that_consolidates(
        self, gleif_record_dotted, gleif_direct_parent
    ):
        record = gleif.parse_records(gleif_record_dotted)[0]
        found = gleif.Group(direct_parent=gleif.parse_related(gleif_direct_parent))
        row = gleif.lei_row(record, found)
        assert row["legal_name"] == "UBS Switzerland AG"
        assert row["direct_parent"].startswith("UBS AG (")
        assert row["ultimate_parent"] == "none reported"

    def test_the_lookup_fields_are_the_four_a_company_row_can_use(
        self, gleif_record_dotted, gleif_direct_parent
    ):
        record = gleif.parse_records(gleif_record_dotted)[0]
        found = gleif.Group(direct_parent=gleif.parse_related(gleif_direct_parent))
        assert set(gleif.lookup_fields(record, found)) == {
            "lei",
            "lei_status",
            "direct_parent",
            "ultimate_parent",
        }

    def test_a_child_row_names_the_jurisdiction_it_sits_in(self, gleif_direct_children):
        page = gleif.parse_related_page(gleif_direct_children)
        row = gleif.child_row(page.entities[0])
        assert row["jurisdiction"] == "BR"
        assert row["lei"] == page.entities[0].lei
