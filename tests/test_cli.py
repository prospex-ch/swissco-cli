"""The parser tree, the exit codes, and the flags every command shares."""

from __future__ import annotations

from datetime import date

import pytest

import importlib
import sys

from swissco import aramis, cli, finma, simap


class TestParser:
    def test_every_command_is_registered(self, capsys):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["--help"])
        out = capsys.readouterr().out
        for command in (
            "lookup",
            "search",
            "publications",
            "events",
            "watch",
            "tenders",
            "vendor",
            "finma",
            "lei",
            "research",
        ):
            assert command in out

    @pytest.mark.parametrize(
        "argv",
        [
            ["lookup", "CHE-444.420.929"],
            ["search", "term"],
            ["publications"],
            ["events", "CHE-444.420.929"],
            ["watch", "uids.txt"],
            ["tenders"],
            ["vendor", "CHE-444.420.929"],
            ["finma"],
            ["lei", "CHE-444.420.929"],
            ["research", "CHE-444.420.929"],
        ],
    )
    def test_every_command_takes_the_shared_flags(self, argv):
        args = cli.build_parser().parse_args([*argv, "--format", "json", "--quiet"])
        assert args.fmt == "json"
        assert args.quiet
        assert args.limit == 20
        assert args.interval is None

    def test_the_default_format_is_table(self):
        assert cli.build_parser().parse_args(["search", "x"]).fmt == "table"

    def test_an_unknown_format_is_rejected(self):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["search", "x", "--format", "yaml"])

    def test_dates_are_parsed(self):
        args = cli.build_parser().parse_args(["publications", "--since", "2026-08-01"])
        assert args.since == date(2026, 8, 1)

    def test_a_malformed_date_is_rejected(self):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["publications", "--since", "01.08.2026"])

    def test_canton_and_type_are_repeatable(self):
        args = cli.build_parser().parse_args(
            ["publications", "--canton", "ZH", "--canton", "BE", "--type", "MERGER"]
        )
        assert args.canton == ["ZH", "BE"]
        assert args.type == ["MERGER"]

    def test_only_real_event_types_are_accepted(self):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["publications", "--type", "NOT_AN_EVENT"])

    def test_all_eleven_event_types_are_offered(self):
        assert len(cli.EVENT_TYPES) == 11
        assert "OFFICERS_CHANGED" in cli.EVENT_TYPES


class TestMain:
    def test_no_command_prints_help_and_fails(self, capsys):
        assert cli.main([]) == cli.EXIT_ERROR
        assert "usage: swissco" in capsys.readouterr().out

    def test_an_invalid_uid_fails_before_any_request(self, capsys):
        assert cli.main(["lookup", "not-a-uid"]) == cli.EXIT_ERROR
        assert "invalid_uid" in capsys.readouterr().err

    def test_rest_search_without_credentials_says_so(self, capsys, monkeypatch):
        monkeypatch.delenv("ZEFIX_USER", raising=False)
        monkeypatch.delenv("ZEFIX_PASSWORD", raising=False)
        assert cli.main(["search", "x", "--via", "rest"]) == cli.EXIT_ERROR
        assert "credentials_required" in capsys.readouterr().err

    def test_a_missing_uid_file_fails(self, capsys, tmp_path):
        missing = tmp_path / "nope.txt"
        assert cli.main(["watch", str(missing), "--state", str(tmp_path)]) == cli.EXIT_ERROR
        assert "not_found" in capsys.readouterr().err

    def test_an_empty_uid_file_fails(self, capsys, tmp_path):
        path = tmp_path / "uids.txt"
        path.write_text("# nothing but a comment\n")
        assert cli.main(["watch", str(path), "--state", str(tmp_path)]) == cli.EXIT_ERROR
        assert "empty_input" in capsys.readouterr().err

    def test_a_file_of_bad_uids_fails(self, capsys, tmp_path):
        path = tmp_path / "uids.txt"
        path.write_text("nonsense\nCHE-123.456.789\n")
        assert cli.main(["watch", str(path), "--state", str(tmp_path)]) == cli.EXIT_ERROR
        assert "invalid_uid" in capsys.readouterr().err


class TestExitCodes:
    def test_watch_splits_zero_and_ten(self):
        """cron and shell scripts branch on this without parsing the output."""
        assert cli.EXIT_OK == 0
        assert cli.EXIT_ERROR == 1
        assert cli.EXIT_CHANGED == 10


class TestRange:
    def test_defaults_end_today(self):
        from argparse import Namespace

        start, end = cli._range(Namespace(since=None, until=None), default_days=7)
        assert end == date.today()
        assert (end - start).days == 7

    def test_an_inverted_range_is_rejected(self):
        from argparse import Namespace

        with pytest.raises(ValueError, match="is after"):
            cli._range(
                Namespace(since=date(2026, 9, 4), until=date(2026, 9, 1)),
                default_days=1,
            )


class TestTheNewSources:
    """Everything here fails before a request, so the suite stays offline."""

    def test_a_publication_type_simap_does_not_have_is_rejected(self):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["tenders", "--type", "not_a_type"])

    def test_every_documented_publication_type_is_offered(self):
        for pub_type in simap.KNOWN_PUB_TYPES:
            args = cli.build_parser().parse_args(["tenders", "--type", pub_type])
            assert args.type == [pub_type]

    def test_tender_cantons_and_types_are_repeatable(self):
        args = cli.build_parser().parse_args(
            ["tenders", "--canton", "ZH", "--canton", "ZG", "--type", "award"]
        )
        assert args.canton == ["ZH", "ZG"]

    def test_a_language_outside_the_four_is_rejected(self):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["tenders", "--lang", "rm"])

    def test_a_supervisory_category_outside_one_to_five_is_rejected(self):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["finma", "--category", "6"])

    def test_a_licence_type_finma_does_not_issue_is_rejected(self):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["finma", "--licence", "Crypto bank"])

    def test_every_licence_type_finma_does_issue_is_offered(self):
        for licence in finma.LICENCE_TYPES:
            args = cli.build_parser().parse_args(["finma", "--licence", licence])
            assert args.licence == licence

    def test_finma_takes_an_optional_query(self):
        assert cli.build_parser().parse_args(["finma"]).query == ""
        assert cli.build_parser().parse_args(["finma", "Raiffeisen"]).query == "Raiffeisen"

    def test_an_invalid_uid_fails_finma_before_any_download(self, capsys):
        assert cli.main(["finma", "--uid", "not-a-uid"]) == cli.EXIT_ERROR
        assert "invalid_uid" in capsys.readouterr().err

    def test_lookup_does_not_ask_for_finma_unless_told_to(self):
        assert cli.build_parser().parse_args(["lookup", "CHE-444.420.929"]).finma is False
        assert cli.build_parser().parse_args(["lookup", "CHE-444.420.929", "--finma"]).finma

    def test_lookup_does_not_ask_for_a_lei_unless_told_to(self):
        """Both extras cost requests a plain lookup does not, so both are opt-in."""
        assert cli.build_parser().parse_args(["lookup", "CHE-444.420.929"]).lei is False
        assert cli.build_parser().parse_args(["lookup", "CHE-444.420.929", "--lei"]).lei

    def test_lei_counts_children_unless_asked_to_list_them(self):
        assert cli.build_parser().parse_args(["lei", "CHE-444.420.929"]).children is False
        assert cli.build_parser().parse_args(["lei", "CHE-444.420.929", "--children"]).children

    def test_an_invalid_uid_fails_lei_before_any_request(self, capsys):
        assert cli.main(["lei", "not-a-uid"]) == cli.EXIT_ERROR
        assert "invalid_uid" in capsys.readouterr().err

    def test_research_defaults_to_the_language_the_service_answers_in(self):
        args = cli.build_parser().parse_args(["research", "hydrogen"])
        assert args.lang == aramis.DEFAULT_LANGUAGE == "EN"

    def test_every_service_language_is_offered(self):
        for language in aramis.LANGUAGES:
            args = cli.build_parser().parse_args(["research", "x", "--lang", language])
            assert args.lang == language

    def test_a_mis_cased_language_is_rejected_before_the_service_400s(self):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["research", "x", "--lang", "en"])

    def test_a_language_aramis_does_not_speak_is_rejected(self):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["research", "x", "--lang", "RM"])


class TestStartupCost:
    def test_a_spreadsheet_library_is_not_loaded_to_parse_a_flag(self):
        """``uvx swissco lookup`` must not pay for openpyxl it will not use.

        The import lives inside ``finma.parse_bank_workbook`` on purpose. This
        guards it, because it regresses the moment someone tidies the imports.
        """
        for module in ("swissco.cli", "swissco.finma", "swissco.sources", "openpyxl"):
            sys.modules.pop(module, None)
        importlib.import_module("swissco.cli").build_parser()
        assert "openpyxl" not in sys.modules
