"""The ARAMIS parsers, the guards in front of the service, and the redaction.

The load-bearing test in this file is the last class. ARAMIS publishes named
researchers with their direct lines, and the promise ``swissco`` makes is that
none of it reaches an output format. That promise is asserted over the raw
fixture bytes, so it fails the moment a field is added to
:class:`~swissco.aramis.Participant` rather than the moment somebody notices.

The two guards in front of the service matter for a different reason: both
failures are ones we would otherwise cause ourselves. ``Count`` above 100 is an
HTTP 500 that the retry loop would hammer three times, and a lower-case language
is an HTTP 400.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from swissco import aramis


class _Service:
    """A client stand-in: one search page, then one detail per hydration."""

    def __init__(self, search: bytes, details: dict[int, bytes]) -> None:
        self.search = search
        self.details = details
        self.searches: list[dict] = []
        self.hydrated: list[int] = []

    def fetch_project_list(self, **kwargs) -> bytes:
        self.searches.append(kwargs)
        return self.search

    def fetch_project(self, aramis_id: int, *, language: str = "EN") -> bytes:
        self.hydrated.append(aramis_id)
        return self.details[aramis_id]


class TestTheGuardsBeforeTheRequest:
    def test_a_count_of_101_is_refused_rather_than_sent(self):
        client = aramis.AramisClient(client=object())
        with pytest.raises(ValueError, match="answers HTTP 500"):
            client.fetch_project_list(count=101)

    def test_a_count_of_zero_is_refused_too(self):
        client = aramis.AramisClient(client=object())
        with pytest.raises(ValueError, match="Count must be"):
            client.fetch_project_list(count=0)

    def test_a_lower_case_language_is_refused(self):
        """``EN`` answers and ``en`` is an HTTP 400. The match is case-sensitive."""
        with pytest.raises(ValueError, match="case-sensitive"):
            aramis.check_language("en")

    def test_the_four_service_languages_are_accepted(self):
        for language in aramis.LANGUAGES:
            assert aramis.check_language(language) == language

    def test_the_bulk_export_host_is_not_reachable(self):
        """The 43 MB export is off the allowlist, so no command can pull it."""
        client = aramis.AramisClient(client=object())
        with pytest.raises(ValueError, match="refusing host"):
            client.check_url("https://datenausgabe.aramis.admin.ch/full_export.json")


class TestFaults:
    def test_a_fault_body_raises_even_though_the_status_was_200(self, aramis_fault):
        with pytest.raises(aramis.ServiceFault, match="Serverfehler"):
            aramis._checked(aramis_fault)

    def test_an_ordinary_response_passes_through_untouched(self, aramis_search):
        assert aramis._checked(aramis_search) == aramis_search

    def test_a_fault_is_never_handed_to_the_parser_as_a_project(self, aramis_fault):
        with pytest.raises(aramis.ContractError, match="no Projects array"):
            aramis.parse_project_list(aramis_fault)


class TestWcfDates:
    def test_the_calendar_day_is_read_in_the_offset_the_payload_states(self):
        """2026-12-31 23:00 UTC is 2027-01-01 in +0100, and ARAMIS shows the latter.

        Taking the UTC day instead would move a third of winter dates back by
        one, and this project's start would be published in the wrong year.
        """
        assert aramis.parse_wcf_date("/Date(1798758000000+0100)/") == date(2027, 1, 1)

    def test_a_1901_outlier_parses_rather_than_failing(self):
        assert aramis.parse_wcf_date("/Date(-2153872800000+0100)/").year == 1901

    def test_the_9999_open_end_sentinel_does_not_crash(self):
        assert aramis.parse_wcf_date("/Date(253402210800000+0100)/").year == 9999

    def test_a_value_past_the_end_of_datetime_is_clamped(self):
        assert aramis.parse_wcf_date("/Date(99999999999999999)/") == date.max

    def test_an_absent_date_is_none_rather_than_a_sentinel(self):
        assert aramis.parse_wcf_date(None) is None
        assert aramis.parse_wcf_date("") is None

    def test_the_iso_dialect_on_the_same_surface_is_accepted(self):
        assert aramis.parse_wcf_date("2028-12-31T00:00:00") == date(2028, 12, 31)

    def test_an_unrecognised_date_is_a_contract_error(self):
        with pytest.raises(aramis.ContractError, match="unrecognised"):
            aramis.parse_wcf_date("next Tuesday")


class TestTheUpstreamMisspellings:
    def test_titel_is_read_under_its_wire_spelling(self, aramis_search):
        page = aramis.parse_project_list(aramis_search)
        assert page.projects[0].title
        assert "Titel" in json.loads(aramis_search)["Projects"][0]

    def test_title_still_works_as_a_fallback(self):
        """Built in memory: upstream publishes only the misspelling today."""
        body = b'{"Projects": [{"Id": 1, "Title": {"Text": "Corrected upstream"}}]}'
        assert aramis.parse_project_list(body).projects[0].title == "Corrected upstream"

    def test_categroies_is_read_inside_a_category_group(self):
        body = json.dumps(
            {
                "ProjectId": 1,
                "Categories": [{"Id": 143, "Categroies": [{"Name": {"Text": "IEA 8"}}]}],
            }
        ).encode()
        assert aramis.parse_project(body).categories == ("IEA 8",)


class TestSearchAndConfirmation:
    def test_a_search_page_parses_into_rows_and_a_matched_total(self, aramis_search):
        page = aramis.parse_project_list(aramis_search)
        assert page.matched == 41
        assert len(page.projects) == 5
        assert page.projects[0].aramis_id > 0

    def test_a_row_without_an_id_is_a_contract_error(self):
        with pytest.raises(aramis.ContractError, match="no Id"):
            aramis.parse_project_list(b'{"Projects": [{"ProjectNumber": "1"}]}')

    def test_a_matching_participant_uid_confirms_the_project(
        self, aramis_search_confirmed, aramis_detail_confirmed
    ):
        detail = json.loads(aramis_detail_confirmed)
        client = _Service(aramis_search_confirmed, {detail["ProjectId"]: aramis_detail_confirmed})
        confirmed = aramis.confirmed_projects(client, "CHE-337.958.399", "MPAssist")
        assert len(confirmed) == 1
        project, participant = confirmed[0]
        assert participant.uid == "CHE-337.958.399"
        assert participant.role == "Implementation Partner"
        assert project.office == "INNOSUISSE"

    def test_a_project_whose_participant_uid_differs_is_dropped(
        self, aramis_search_confirmed, aramis_detail_confirmed
    ):
        """The name found the candidate and the UID is what decides."""
        detail = json.loads(aramis_detail_confirmed)
        client = _Service(aramis_search_confirmed, {detail["ProjectId"]: aramis_detail_confirmed})
        assert aramis.confirmed_projects(client, "CHE-444.420.929", "MPAssist") == []

    def test_a_project_with_no_participant_uid_cannot_confirm_anything(
        self, aramis_search_confirmed, aramis_detail_no_uid
    ):
        detail = json.loads(aramis_detail_no_uid)
        client = _Service(aramis_search_confirmed, {detail["ProjectId"]: aramis_detail_no_uid})
        client.search = json.dumps(
            {"CountOfMatchedProjects": 1, "Projects": [{"Id": detail["ProjectId"]}]}
        ).encode()
        assert aramis.confirmed_projects(client, "CHE-337.958.399", "Bernet") == []

    def test_both_search_keys_are_tried_and_the_candidates_merged(
        self, aramis_search_confirmed, aramis_detail_confirmed
    ):
        detail = json.loads(aramis_detail_confirmed)
        client = _Service(aramis_search_confirmed, {detail["ProjectId"]: aramis_detail_confirmed})
        aramis.confirmed_projects(client, "CHE-337.958.399", "MPAssist")
        asked = [
            {key for key in ("contractor", "keywords") if call.get(key)}
            for call in client.searches
        ]
        assert asked == [{"contractor"}, {"keywords"}]
        # The same project came back from both keys and is hydrated once.
        assert client.hydrated == [detail["ProjectId"]]


class TestRows:
    def test_a_confirmed_row_names_the_role_the_uid_was_found_on(
        self, aramis_detail_confirmed
    ):
        detail = aramis.parse_project(aramis_detail_confirmed)
        partner = next(
            person for person in detail.participants if person.uid == "CHE-337.958.399"
        )
        row = aramis.confirmed_row(detail, partner)
        assert row["role"] == "Implementation Partner"
        assert row["uid"] == "CHE-337.958.399"
        assert row["office"] == "INNOSUISSE"

    def test_a_participant_with_no_organisation_leaves_no_gap_in_the_list(self):
        """ARAMIS files a few blocks naming a person and no organisation."""
        body = json.dumps(
            {
                "ProjectId": 1,
                "Participants": [
                    {"Company1": None, "Prename": "Alex", "FamilyName": "Muster"},
                    {"Company1": "Grensol AG"},
                ],
            }
        ).encode()
        assert aramis.project_row(aramis.parse_project(body))["participants"] == ["Grensol AG"]


class TestTheSearchTerm:
    def test_a_legal_form_suffix_is_stripped(self):
        assert aramis.search_term("Storz Medical AG") == "Storz Medical"
        assert aramis.search_term("Bobst Mex SA") == "Bobst Mex"

    def test_a_long_name_is_capped_where_upstream_truncates(self):
        """``Company1`` is truncated at 35 characters, so a longer term cannot match."""
        term = aramis.search_term("inspire AG für mechatronische Produktionssysteme")
        assert len(term) <= aramis.MAX_TERM_CHARS

    def test_a_name_without_a_suffix_is_left_alone(self):
        assert aramis.search_term("Empa") == "Empa"


class TestTheUidInsideAUrl:
    def test_the_uid_is_read_out_of_the_participant_link(self):
        found = aramis.uid_from_url("www.uid.admin.ch/Detail.aspx?uid_id=CHE106209800", None)
        assert found == "CHE-106.209.800"

    def test_url2_is_scanned_as_well_as_url1(self):
        assert aramis.uid_from_url(None, "?uid_id=CHE106209800") == "CHE-106.209.800"

    def test_a_participant_without_a_link_has_no_uid(self):
        assert aramis.uid_from_url(None, None) == ""
        assert aramis.uid_from_url("https://www.example.ch") == ""


class TestPersonalDataStopsAtTheParser:
    """ARAMIS publishes researchers. ``swissco`` reads the organisation only."""

    PERSON_FIELDS = (
        "Prename",
        "FamilyName",
        "EMail",
        "FormOfAddress",
        "Title",
        "Phone1",
        "Phone2",
        "Phone3",
        "Telefax",
        "ShortViewName",
    )

    def test_the_fixture_really_carries_the_fields_being_guarded_against(
        self, aramis_detail_no_uid
    ):
        """Otherwise the assertion below would pass against an empty payload."""
        wire = json.loads(aramis_detail_no_uid)["Participants"][0]
        assert wire["EMail"] and wire["FamilyName"] and wire["Phone1"]

    def test_no_person_field_exists_on_the_dataclass(self):
        fields = set(aramis.Participant.__dataclass_fields__)
        assert not fields & {field.lower() for field in self.PERSON_FIELDS}
        assert fields == {"organisation", "role", "uid", "canton", "country", "city"}

    def test_no_person_value_survives_into_the_parsed_project(self, aramis_detail_no_uid):
        wire = json.loads(aramis_detail_no_uid)
        published = {
            str(person.get(field))
            for person in wire["Participants"]
            for field in self.PERSON_FIELDS
            if person.get(field)
        }
        parsed = json.dumps(
            [aramis.project_row(aramis.parse_project(aramis_detail_no_uid))],
            ensure_ascii=False,
            default=str,
        )
        for value in published:
            assert value not in parsed, value

    def test_the_organisation_and_the_role_do_survive(self, aramis_detail_no_uid):
        detail = aramis.parse_project(aramis_detail_no_uid)
        assert detail.participants[1].organisation == "Bernet Engineering"
        assert detail.participants[1].role == "Implementation Partner"
