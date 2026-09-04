"""The two-stage join: the title prefilter, then the body-UID confirmation."""

from __future__ import annotations

from datetime import date

import pytest
from shab_parser import PublicationRef, parse_xml

from swissco import events
from swissco.publications import ListEntry, parse_list_page


def entry(titles: dict[str, str]) -> ListEntry:
    return ListEntry(
        ref=PublicationRef(
            external_id="x",
            publication_date=date(2026, 9, 3),
            language="de",
            url="https://example.invalid/x",
        ),
        titles=titles,
    )


class TestNameKeys:
    def test_the_full_key_is_the_whole_name(self):
        full, _core = events.name_keys("Baumberger Bau AG")
        assert full == "baumberger bau ag"

    def test_the_core_key_drops_the_legal_form(self):
        _full, core = events.name_keys("Baumberger Bau AG")
        assert core == "baumberger bau"

    def test_punctuation_is_normalised_away(self):
        full, _core = events.name_keys("Dany & Fils S.A., décolletage")
        assert "&" not in full
        assert "," not in full

    def test_an_empty_name_yields_empty_keys(self):
        assert events.name_keys("") == ("", "")


class TestTitleMatches:
    def test_the_register_title_wraps_the_name(self):
        full, core = events.name_keys("Baumberger Bau AG")
        assert events.title_matches(
            {"de": "Mutation Baumberger Bau AG, Koppigen"}, full, core
        )

    def test_a_different_legal_form_still_matches_on_the_core(self):
        """Bilingual cantons print SA where the register stores AG."""
        full, core = events.name_keys("Baumberger Bau AG")
        assert events.title_matches({"fr": "Mutation Baumberger Bau SA, Koppigen"}, full, core)

    def test_any_language_counts(self):
        full, core = events.name_keys("Baumberger Bau AG")
        assert events.title_matches(
            {"de": "Etwas anderes", "it": "Cambiamenti Baumberger Bau AG"}, full, core
        )

    def test_another_company_does_not_match(self):
        full, core = events.name_keys("Baumberger Bau AG")
        assert not events.title_matches({"de": "Mutation Muster Handel AG, Zug"}, full, core)

    def test_a_short_core_key_is_ignored(self):
        """A two-letter core would otherwise match most of the register."""
        full, core = events.name_keys("XY AG")
        assert core == "xy"
        assert not events.title_matches({"de": "Mutation Oxygen Systems AG"}, full, core)

    def test_no_titles_never_matches(self):
        full, core = events.name_keys("Baumberger Bau AG")
        assert not events.title_matches({}, full, core)


class TestPrefilter:
    def test_keeps_only_plausible_titles(self):
        entries = [
            entry({"de": "Mutation Baumberger Bau AG, Koppigen"}),
            entry({"de": "Mutation Muster Handel AG, Zug"}),
        ]
        kept = events.prefilter(entries, "Baumberger Bau AG")
        assert len(kept) == 1

    def test_an_empty_name_keeps_nothing(self):
        assert events.prefilter([entry({"de": "anything"})], "") == []

    def test_it_runs_over_a_real_list_page(self, shab_list_page):
        entries, _total = parse_list_page(shab_list_page)
        names = [e.title.split()[1] for e in entries if len(e.title.split()) > 1]
        assert names
        # Every entry's own title must survive its own name as the needle.
        for candidate in entries[:3]:
            words = candidate.title.split()
            if len(words) < 3:
                continue
            needle = " ".join(words[1:3])
            assert events.prefilter([candidate], needle)


class TestConfirm:
    def test_the_body_uid_is_the_authority(self, shab_body_hr02):
        publication = parse_xml(shab_body_hr02)
        assert publication.uid
        assert events.confirm(publication, publication.uid)

    def test_any_punctuation_of_the_same_uid_confirms(self, shab_body_hr02):
        publication = parse_xml(shab_body_hr02)
        bare = publication.uid.replace("-", "").replace(".", "")
        assert events.confirm(publication, bare)

    def test_another_uid_is_rejected(self, shab_body_hr02):
        publication = parse_xml(shab_body_hr02)
        assert not events.confirm(publication, "CHE-444.420.929")

    def test_a_body_with_no_uid_is_rejected(self, shab_body_hr02):
        """An unattributable event under a specific UID is worse than none."""
        from dataclasses import replace

        publication = replace(parse_xml(shab_body_hr02), uid=None)
        assert not events.confirm(publication, "CHE-444.420.929")


class TestEventRow:
    def test_row_shape(self):
        event = events.CompanyEvent(
            uid="CHE-444.420.929",
            company_name="Baumberger Bau AG",
            event_type="ADDRESS_CHANGED",
            effective_date=date(2026, 9, 1),
            publication_date=date(2026, 9, 3),
            sub_rubric="HR02",
            canton="BE",
            external_id="x",
            url="https://example.invalid/x",
            payload={"trigger": "addressChanged"},
        )
        row = events.event_row(event)
        assert row["effective_date"] == "2026-09-01"
        assert row["event_type"] == "ADDRESS_CHANGED"
        assert "payload" not in row

    def test_a_missing_effective_date_renders_empty(self):
        event = events.CompanyEvent(
            uid="CHE-444.420.929",
            company_name="x",
            event_type="MERGER",
            effective_date=None,
            publication_date=date(2026, 9, 3),
            sub_rubric="HR02",
            canton="BE",
            external_id="x",
            url="",
            payload={},
        )
        assert events.event_row(event)["effective_date"] == ""


class TestBodyCache:
    def test_a_cached_body_is_read_instead_of_fetched(self, tmp_path, shab_body_hr02):
        listing = entry({"de": "x"})
        (tmp_path / f"{listing.ref.external_id}.xml").write_bytes(shab_body_hr02)

        class Exploding:
            def fetch(self, ref):
                raise AssertionError("should not have been fetched")

        assert events.body(Exploding(), listing, tmp_path) == shab_body_hr02

    def test_a_fetched_body_is_written_to_the_cache(self, tmp_path, shab_body_hr02):
        listing = entry({"de": "x"})

        class Stub:
            def fetch(self, ref):
                class Raw:
                    content = shab_body_hr02

                return Raw()

        assert events.body(Stub(), listing, tmp_path) == shab_body_hr02
        assert (tmp_path / "x.xml").read_bytes() == shab_body_hr02

    def test_a_failed_fetch_yields_none_rather_than_raising(self, tmp_path):
        class Failing:
            def fetch(self, ref):
                raise OSError("network down")

        assert events.body(Failing(), entry({"de": "x"}), tmp_path) is None
