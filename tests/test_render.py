"""The three formats, all rendered from the same rows."""

from __future__ import annotations

import csv
import io
import json
from datetime import date

import pytest

from swissco import render

ROWS = [
    {"name": "Alpha AG", "canton": "ZH", "count": 3},
    {"name": "Beta SA", "canton": "VD", "count": 11},
]


def emitted(rows, fmt) -> str:
    stream = io.StringIO()
    render.emit(rows, fmt=fmt, stream=stream)
    return stream.getvalue()


class TestJson:
    def test_is_a_parseable_array(self):
        assert json.loads(emitted(ROWS, "json")) == ROWS

    def test_keeps_non_ascii_as_itself(self):
        out = emitted([{"name": "Sàrl à Genève"}], "json")
        assert "Sàrl à Genève" in out
        assert "\\u" not in out

    def test_dates_become_iso_strings(self):
        out = json.loads(emitted([{"day": date(2026, 9, 3)}], "json"))
        assert out == [{"day": "2026-09-03"}]

    def test_an_empty_result_is_an_empty_array(self):
        assert json.loads(emitted([], "json")) == []


class TestCsv:
    def test_header_then_rows(self):
        parsed = list(csv.DictReader(io.StringIO(emitted(ROWS, "csv"))))
        assert parsed == [
            {"name": "Alpha AG", "canton": "ZH", "count": "3"},
            {"name": "Beta SA", "canton": "VD", "count": "11"},
        ]

    def test_a_comma_in_a_value_is_quoted(self):
        out = emitted([{"name": "Dany & Fils S.A., décolletage"}], "csv")
        assert '"Dany & Fils S.A., décolletage"' in out
        assert list(csv.reader(io.StringIO(out)))[1] == ["Dany & Fils S.A., décolletage"]

    def test_a_quote_in_a_value_is_doubled(self):
        out = emitted([{"name": 'the "Muster" AG'}], "csv")
        assert list(csv.reader(io.StringIO(out)))[1] == ['the "Muster" AG']

    def test_a_newline_in_a_value_survives_the_round_trip(self):
        out = emitted([{"purpose": "first line\nsecond line"}], "csv")
        assert list(csv.reader(io.StringIO(out)))[1] == ["first line\nsecond line"]

    def test_a_missing_key_leaves_its_column_empty(self):
        out = emitted([{"a": 1, "b": 2}, {"a": 3}], "csv")
        assert list(csv.DictReader(io.StringIO(out))) == [
            {"a": "1", "b": "2"},
            {"a": "3", "b": ""},
        ]

    def test_a_list_becomes_one_cell(self):
        out = emitted([{"events": ["INCORPORATION", "MERGER"]}], "csv")
        assert list(csv.reader(io.StringIO(out)))[1] == ["INCORPORATION; MERGER"]

    def test_an_empty_result_writes_nothing(self):
        assert emitted([], "csv") == ""


class TestTable:
    def test_has_a_header_a_rule_and_the_rows(self):
        lines = emitted(ROWS, "table").splitlines()
        assert lines[0].startswith("NAME")
        assert set(lines[1]) <= {"-", " "}
        assert len(lines) == 4

    def test_columns_align(self):
        lines = emitted(ROWS, "table").splitlines()
        assert lines[2].index("ZH") == lines[3].index("VD")

    def test_long_cells_are_truncated(self):
        out = emitted([{"purpose": "x" * 200}], "table")
        assert "…" in out
        assert len(out.splitlines()[2]) <= render.MAX_CELL

    def test_newlines_inside_a_cell_are_collapsed(self):
        out = emitted([{"purpose": "first\nsecond"}], "table")
        assert len(out.splitlines()) == 3
        assert "first second" in out

    def test_an_empty_result_writes_nothing(self):
        assert emitted([], "table") == ""


class TestFields:
    def test_label_and_value_per_line(self):
        out = render.to_fields({"legal_name": "Alpha AG", "canton": "ZH"})
        assert out.splitlines() == ["legal name  Alpha AG", "canton      ZH"]

    def test_empty_values_are_left_out(self):
        out = render.to_fields({"legal_name": "Alpha AG", "chid": ""})
        assert "chid" not in out

    def test_an_empty_record_writes_nothing(self):
        assert render.to_fields({}) == ""


class TestOneShape:
    def test_every_format_carries_the_same_columns(self):
        """table and csv are rendered from the rows json serialises."""
        columns = set(render.columns(ROWS))
        header = emitted(ROWS, "table").splitlines()[0].lower().split()
        assert set(header) == columns
        assert set(next(csv.reader(io.StringIO(emitted(ROWS, "csv"))))) == columns
        assert set(json.loads(emitted(ROWS, "json"))[0]) == columns

    def test_output_does_not_depend_on_the_stream_being_a_terminal(self):
        """No isatty check anywhere: same command, same bytes, terminal or pipe."""
        import inspect

        assert "isatty" not in inspect.getsource(render)


class TestErrors:
    def test_an_unknown_format_raises(self):
        with pytest.raises(ValueError, match="unknown format"):
            emitted(ROWS, "yaml")

    def test_fail_writes_one_json_object_to_stderr(self, capsys):
        render.fail("no such company", code="not_found")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert json.loads(captured.err) == {
            "error": "not_found",
            "message": "no such company",
        }

    def test_note_goes_to_stderr(self, capsys):
        render.note("listing 1027 publications")
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "1027" in captured.err

    def test_quiet_silences_a_note(self, capsys):
        render.note("listing", quiet=True)
        assert capsys.readouterr().err == ""


class TestEmitObject:
    def test_table_renders_a_record_as_fields(self):
        stream = io.StringIO()
        render.emit_object({"legal_name": "Alpha AG"}, fmt="table", stream=stream)
        assert stream.getvalue() == "legal name  Alpha AG\n"

    def test_json_keeps_the_row_shape_a_program_expects(self):
        stream = io.StringIO()
        render.emit_object({"legal_name": "Alpha AG"}, fmt="json", stream=stream)
        assert json.loads(stream.getvalue()) == [{"legal_name": "Alpha AG"}]
