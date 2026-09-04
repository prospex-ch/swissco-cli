"""Turning rows into the three output formats.

Two rules, both carried over from the prospex CLI and both worth stating:

The format never depends on whether stdout is a terminal. A command piped into
``jq`` and the same command watched by a person produce identical bytes.
``--format`` is the only thing that changes output, so a script that worked
interactively works in CI.

``table`` and ``csv`` are rendered from the same list of dicts that ``json``
serialises. There is one code path and one shape, so a column can never appear
in one format and be missing from another.

Progress notes go to stderr, where ``--quiet`` silences them. Errors go to
stderr as a single JSON object, so a caller reading stdout as JSON is never
handed a mixture.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from datetime import date

FORMATS = ("table", "json", "csv")

#: Cells wider than this are truncated in ``table`` output. JSON and CSV are
#: never truncated: they are read by programs, which do not care about width.
MAX_CELL = 60


def emit(rows: list[dict], *, fmt: str, stream=None) -> None:
    """Write *rows* to *stream* (default stdout) in *fmt*."""
    stream = sys.stdout if stream is None else stream
    if fmt == "json":
        stream.write(to_json(rows))
    elif fmt == "csv":
        stream.write(to_csv(rows))
    elif fmt == "table":
        stream.write(to_table(rows))
    else:
        raise ValueError(f"unknown format {fmt!r}; expected one of {', '.join(FORMATS)}")


def emit_object(payload: dict, *, fmt: str, stream=None) -> None:
    """Write a single record, which ``table`` prints as label/value pairs.

    ``lookup`` returns one company, and a one-row table of twelve columns is
    unreadable in a terminal. JSON and CSV keep the row shape a program
    expects.
    """
    stream = sys.stdout if stream is None else stream
    if fmt == "table":
        stream.write(to_fields(payload))
    else:
        emit([payload], fmt=fmt, stream=stream)


def to_json(rows: list[dict]) -> str:
    """*rows* as a pretty-printed JSON array with a trailing newline."""
    return json.dumps(rows, ensure_ascii=False, indent=2, default=_serialise) + "\n"


def to_csv(rows: list[dict]) -> str:
    """*rows* as CSV with a header, quoted per RFC 4180.

    The header comes from the union of every row's keys in first-seen order, so
    a row that omits an optional key still lines up under the right columns.
    Lists are joined with a semicolon and dicts are serialised as JSON, because
    a CSV cell holds one string.
    """
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=columns(rows), lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _cell(row.get(key)) for key in columns(rows)})
    return buffer.getvalue()


def to_table(rows: list[dict]) -> str:
    """*rows* as a plain-text table, columns padded to their widest cell."""
    if not rows:
        return ""
    headers = columns(rows)
    body = [[_truncate(_cell(row.get(header))) for header in headers] for row in rows]
    widths = [
        max(len(header), *(len(line[index]) for line in body))
        for index, header in enumerate(headers)
    ]

    out = [_line([h.upper() for h in headers], widths)]
    out.append("  ".join("-" * width for width in widths))
    out.extend(_line(line, widths) for line in body)
    return "\n".join(out) + "\n"


def to_fields(payload: dict) -> str:
    """One record as ``label  value`` lines, labels padded to a common width."""
    if not payload:
        return ""
    labels = {key: key.replace("_", " ") for key in payload}
    width = max(len(label) for label in labels.values())
    lines = []
    for key, value in payload.items():
        cell = _cell(value)
        if not cell:
            continue
        lines.append(f"{labels[key].ljust(width)}  {cell}")
    return "\n".join(lines) + "\n" if lines else ""


def columns(rows: list[dict]) -> list[str]:
    """Every key across *rows*, in the order first encountered."""
    ordered: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                ordered.append(key)
    return ordered


def note(message: str, *, quiet: bool = False) -> None:
    """Write a progress note to stderr, unless *quiet*."""
    if not quiet:
        print(message, file=sys.stderr)


def fail(message: str, *, code: str = "error") -> None:
    """Write one JSON error object to stderr.

    JSON in every format, so a caller that hit an error while asking for CSV
    still gets something it can parse instead of a bare English sentence.
    """
    print(
        json.dumps({"error": code, "message": message}, ensure_ascii=False),
        file=sys.stderr,
    )


def _line(cells: list[str], widths: list[int]) -> str:
    padded = [cell.ljust(width) for cell, width in zip(cells, widths)]
    return "  ".join(padded).rstrip()


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return "; ".join(_cell(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_serialise)
    return str(value)


def _truncate(cell: str) -> str:
    collapsed = " ".join(cell.split())
    if len(collapsed) <= MAX_CELL:
        return collapsed
    return collapsed[: MAX_CELL - 1] + "…"


def _serialise(value):
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"cannot serialise {type(value).__name__}")
