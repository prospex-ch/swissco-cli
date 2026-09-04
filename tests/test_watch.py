"""State I/O and the fingerprint diff, across three generations."""

from __future__ import annotations

import json

import pytest
from zefix_parser.lindas import parse_entity_page

from swissco import watch


def record(fingerprint: str, **fields) -> dict:
    base = {name: "" for name in watch.WATCHED_FIELDS}
    base.update(fields)
    base["fingerprint"] = fingerprint
    return base


class TestReadUids:
    def test_one_per_line(self, tmp_path):
        path = tmp_path / "uids.txt"
        path.write_text("CHE-444.420.929\nCHE-105.943.826\n")
        assert watch.read_uids(path) == ["CHE-444.420.929", "CHE-105.943.826"]

    def test_blank_lines_and_comments_are_skipped(self, tmp_path):
        path = tmp_path / "uids.txt"
        path.write_text("# my watchlist\n\nCHE-444.420.929  # the branch\n\n")
        assert watch.read_uids(path) == ["CHE-444.420.929"]

    def test_duplicates_collapse_keeping_first_seen_order(self, tmp_path):
        path = tmp_path / "uids.txt"
        path.write_text("CHE-444.420.929\nCHE444420929\nCHE-105.943.826\n")
        assert watch.read_uids(path) == ["CHE-444.420.929", "CHE-105.943.826"]

    def test_an_empty_file_yields_nothing(self, tmp_path):
        path = tmp_path / "uids.txt"
        path.write_text("")
        assert watch.read_uids(path) == []


class TestState:
    def test_a_missing_file_is_a_first_run(self, tmp_path):
        assert watch.load_state(tmp_path) == {}

    def test_round_trip(self, tmp_path):
        companies = {"CHE444420929": record("abc", legal_name="Baumberger Bau AG")}
        watch.save_state(tmp_path, companies)
        assert watch.load_state(tmp_path) == companies

    def test_the_file_carries_a_version_and_a_timestamp(self, tmp_path):
        watch.save_state(tmp_path, {})
        data = json.loads(watch.state_path(tmp_path).read_text())
        assert data["version"] == watch.STATE_VERSION
        assert data["updated_at"]

    def test_a_corrupt_file_reads_as_a_first_run(self, tmp_path):
        watch.state_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        watch.state_path(tmp_path).write_text("{ not json")
        assert watch.load_state(tmp_path) == {}

    def test_a_file_without_companies_reads_as_a_first_run(self, tmp_path):
        watch.state_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
        watch.state_path(tmp_path).write_text('{"version": 1}')
        assert watch.load_state(tmp_path) == {}

    def test_no_temporary_file_is_left_behind(self, tmp_path):
        watch.save_state(tmp_path, {})
        assert not list(tmp_path.glob("*.tmp"))

    def test_creates_the_directory(self, tmp_path):
        nested = tmp_path / "a" / "b"
        watch.save_state(nested, {})
        assert watch.state_path(nested).exists()


class TestSnapshot:
    def test_carries_the_fingerprint_and_the_watched_fields(self, lindas_lookup):
        entity = parse_entity_page(lindas_lookup)[0]
        snap = watch.snapshot(entity)
        assert snap["fingerprint"] == entity.fingerprint
        assert snap["legal_name"] == "Baumberger Bau AG"
        assert set(snap) == {"fingerprint", *watch.WATCHED_FIELDS}


class TestDiff:
    def test_a_first_run_reports_everything_as_added(self):
        current = {"CHE444420929": record("a", legal_name="Baumberger Bau AG")}
        report = watch.diff({}, current)
        assert [row["uid"] for row in report.added] == ["CHE-444.420.929"]
        assert report.has_changes

    def test_an_unchanged_fingerprint_reports_nothing(self):
        state = {"CHE444420929": record("a", legal_name="Baumberger Bau AG")}
        report = watch.diff(state, state)
        assert not report.has_changes
        assert report.unchanged == 1

    def test_a_moved_fingerprint_names_the_changed_fields(self):
        before = {"CHE444420929": record("a", legal_name="Alt AG", canton="BE")}
        after = {"CHE444420929": record("b", legal_name="Neu AG", canton="BE")}
        report = watch.diff(before, after)
        assert report.changed[0]["changes"] == "legal_name"
        assert report.changed[0]["legal_name"] == "Neu AG"

    def test_several_changed_fields_are_listed_in_a_stable_order(self):
        before = {"x": record("a", legal_name="Alt", locality="Bern", purpose="Alt")}
        after = {"x": record("b", legal_name="Neu", locality="Zug", purpose="Neu")}
        assert watch.diff(before, after).changed[0]["changes"] == (
            "legal_name, locality, purpose"
        )

    def test_a_fingerprint_moving_on_an_unnamed_field_is_still_a_change(self):
        """The digest covers more than the named fields, and it is the authority."""
        before = {"x": record("a", legal_name="Same")}
        after = {"x": record("b", legal_name="Same")}
        report = watch.diff(before, after)
        assert len(report.changed) == 1
        assert report.changed[0]["changes"] == ""

    def test_absence_is_reported_as_absence_and_never_as_deletion(self):
        before = {"CHE444420929": record("a", legal_name="Baumberger Bau AG")}
        report = watch.diff(before, {}, requested=["CHE-444.420.929"])
        assert report.vanished[0]["status"] == "no longer in the dataset"
        assert "delet" not in report.vanished[0]["status"].lower()

    def test_a_uid_taken_off_the_list_has_not_vanished(self):
        before = {
            "CHE444420929": record("a", legal_name="Watched"),
            "CHE105943826": record("b", legal_name="Dropped from the list"),
        }
        current = {"CHE444420929": record("a", legal_name="Watched")}
        report = watch.diff(before, current, requested=["CHE-444.420.929"])
        assert report.vanished == []
        assert report.unchanged == 1

    def test_without_a_request_list_every_absence_counts(self):
        before = {"CHE444420929": record("a")}
        assert len(watch.diff(before, {}).vanished) == 1

    def test_the_request_list_is_matched_on_normalised_uids(self):
        """State keys arrive bare from LINDAS; the request list may be punctuated."""
        before = {"CHE444420929": record("a", legal_name="Gone")}
        report = watch.diff(before, {}, requested=["CHE-444.420.929"])
        assert len(report.vanished) == 1

    def test_three_generations(self):
        """Added, then changed, then gone."""
        uid = "CHE444420929"
        first = watch.diff({}, {uid: record("a", legal_name="Muster AG")})
        assert len(first.added) == 1

        second = watch.diff(
            {uid: record("a", legal_name="Muster AG")},
            {uid: record("b", legal_name="Muster Holding AG")},
        )
        assert len(second.changed) == 1
        assert second.changed[0]["changes"] == "legal_name"

        third = watch.diff(
            {uid: record("b", legal_name="Muster Holding AG")}, {}, requested=[uid]
        )
        assert len(third.vanished) == 1

    def test_rows_are_added_then_changed_then_vanished(self):
        a, b, c = "CHE105943826", "CHE166712190", "CHE444420929"
        before = {b: record("1", legal_name="B"), c: record("1", legal_name="C")}
        current = {a: record("1", legal_name="A"), b: record("2", legal_name="B")}
        rows = watch.diff(before, current, requested=[a, b, c]).rows()
        assert [row["status"] for row in rows] == [
            "added",
            "changed",
            "no longer in the dataset",
        ]

    def test_rows_are_uid_sorted_within_each_group(self):
        current = {
            "CHE105943826": record("1", legal_name="Second"),
            "CHE444420929": record("1", legal_name="First"),
        }
        report = watch.diff({}, current)
        assert [row["uid"] for row in report.added] == [
            "CHE-105.943.826",
            "CHE-444.420.929",
        ]


class TestChangedFields:
    def test_reports_only_what_differs(self):
        before = record("a", legal_name="Alt", canton="BE")
        after = record("b", legal_name="Neu", canton="BE")
        assert watch.changed_fields(before, after) == ["legal_name"]

    def test_a_missing_key_compares_as_empty(self):
        assert watch.changed_fields({}, record("a", legal_name="Neu")) == ["legal_name"]

    def test_identical_records_differ_in_nothing(self):
        assert watch.changed_fields(record("a"), record("a")) == []
