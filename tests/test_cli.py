"""The parser tree, the exit codes, and the flags every command shares."""

from __future__ import annotations

from datetime import date

import pytest

from swissco import cli


class TestParser:
    def test_every_command_is_registered(self, capsys):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["--help"])
        out = capsys.readouterr().out
        for command in ("lookup", "search", "publications", "events", "watch"):
            assert command in out

    @pytest.mark.parametrize(
        "argv",
        [
            ["lookup", "CHE-444.420.929"],
            ["search", "term"],
            ["publications"],
            ["events", "CHE-444.420.929"],
            ["watch", "uids.txt"],
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


class TestPageEstimate:
    def test_a_short_range_says_so(self):
        assert "One or two" in cli._page_estimate(date(2026, 9, 3), date(2026, 9, 4))

    def test_a_long_range_counts_windows_and_both_states(self):
        note = cli._page_estimate(date(2026, 1, 1), date(2026, 12, 31))
        assert "windows" in note
        assert "both" in note
