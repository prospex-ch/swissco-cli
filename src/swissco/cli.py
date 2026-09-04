"""The ``swissco`` command: argument parsing and dispatch.

``argparse`` and a small table renderer, with no CLI framework. ``uvx swissco``
pays the import cost on every invocation, and the two libraries this wraps are
already the interesting part of the startup time.

Exit codes:

==  ===========================================================
0   success, and for ``watch`` also "nothing changed"
1   the request failed: bad input, no such company, upstream error
10  ``watch`` found at least one change
==  ===========================================================

``watch`` splitting 0 and 10 is what lets cron and a shell script branch on the
result without parsing the output.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from shab_parser import EventType, ShabError, parse_xml
from zefix_parser import AuthenticationError, ZefixError

from . import __version__, companies, config, events, publications, render, sources, watch
from .companies import NotAUid

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CHANGED = 10

EVENT_TYPES = [e.value for e in EventType]

#: Commercial-register publications the gazette issues on an average day, used
#: only to tell a user how long a wide range will take before it starts.
PUBLICATIONS_PER_DAY = 1000

EPILOG = """\
credentials:
  Every command works without them. Supplying Zefix PublicREST credentials,
  which zefix@bj.admin.ch issues on request, adds capital, status, former names
  and corporate relations to `lookup`, and a name-prefix search to `search`.
  Read from --user/--password or from ZEFIX_USER/ZEFIX_PASSWORD.

examples:
  swissco lookup CHE-444.420.929
  swissco search "precision machining" --canton VD --limit 5
  swissco publications --canton ZH --since 2026-08-01 --type CAPITAL_INCREASED
  swissco events CHE-444.420.929 --since 2024-01-01
  swissco watch uids.txt --state ~/.swissco/
"""


def build_parser() -> argparse.ArgumentParser:
    """The full parser tree."""
    parser = argparse.ArgumentParser(
        prog="swissco",
        description="Swiss company data from the shell: Zefix and SHAB in one command.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"swissco {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    lookup = subparsers.add_parser(
        "lookup",
        help="one company by UID, CH-ID or EHRA id",
        description="Print everything the register publishes about one company.",
    )
    lookup.add_argument("uid", help="CHE-444.420.929, CHE444420929, or a CH-ID")
    _common(lookup)
    lookup.set_defaults(handler=_lookup)

    search = subparsers.add_parser(
        "search",
        help="companies by name or statutory purpose",
        description=(
            "Search legal names and statutory purposes. The purpose is what "
            "makes this useful: it is how a company describes what it does, in "
            "its own words, in the register."
        ),
    )
    search.add_argument("term", help="text to look for in the name or the purpose")
    search.add_argument("--canton", default="", help="two-letter canton code, e.g. VD")
    search.add_argument(
        "--legal-form", default="", help="eCH-0097 legal-form code, e.g. 0106 for an AG"
    )
    search.add_argument(
        "--via",
        choices=("lindas", "rest"),
        default="lindas",
        help="lindas (default) matches a substring; rest matches a name prefix "
        "and needs credentials",
    )
    _common(search)
    search.set_defaults(handler=_search)

    pubs = subparsers.add_parser(
        "publications",
        help="SHAB commercial-register publications in a date range",
        description=(
            "List publications from the Swiss Official Gazette of Commerce. "
            "Filters are applied here, because the API accepts and ignores them."
        ),
    )
    pubs.add_argument("--since", type=_day, help="first publication date (YYYY-MM-DD)")
    pubs.add_argument("--until", type=_day, help="last publication date (YYYY-MM-DD)")
    pubs.add_argument(
        "--canton", action="append", default=[], help="canton code, repeatable"
    )
    pubs.add_argument(
        "--sub-rubric",
        action="append",
        default=[],
        choices=("HR01", "HR02", "HR03"),
        help="HR01 registrations, HR02 mutations, HR03 deletions; repeatable",
    )
    pubs.add_argument(
        "--type",
        action="append",
        default=[],
        choices=EVENT_TYPES,
        metavar="EVENT",
        help="keep only publications carrying this event; repeatable. "
        f"One of: {', '.join(EVENT_TYPES)}",
    )
    pubs.add_argument("--query", default="", help="text to look for in the title")
    _common(pubs)
    pubs.set_defaults(handler=_publications)

    evts = subparsers.add_parser(
        "events",
        help="one company's registry events over a date range",
        description=(
            "Resolve a UID to its legal name, scan the gazette for "
            "publications about it, and confirm each against the body's own UID."
        ),
    )
    evts.add_argument("uid", help="the company's UID")
    evts.add_argument("--since", type=_day, help="first publication date (YYYY-MM-DD)")
    evts.add_argument("--until", type=_day, help="last publication date (YYYY-MM-DD)")
    evts.add_argument(
        "--no-cache", action="store_true", help="fetch every body, ignoring the cache"
    )
    _common(evts)
    evts.set_defaults(handler=_events)

    wtch = subparsers.add_parser(
        "watch",
        help="report what changed since the last run",
        description=(
            "Compare each company against the state written last time. "
            f"Exits {EXIT_CHANGED} when something changed, {EXIT_OK} when nothing did."
        ),
    )
    wtch.add_argument("uids", help="file of UIDs, one per line")
    _common(wtch)
    wtch.set_defaults(handler=_watch)

    return parser


def _common(parser: argparse.ArgumentParser) -> None:
    """The flags every command takes."""
    parser.add_argument(
        "--format",
        dest="fmt",
        choices=render.FORMATS,
        default="table",
        help="output format (default: table). Identical in a terminal and in a pipe.",
    )
    parser.add_argument("--limit", type=int, default=20, help="maximum rows (default: 20)")
    parser.add_argument("--user", default="", help="Zefix PublicREST username")
    parser.add_argument("--password", default="", help="Zefix PublicREST password")
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help=f"minimum seconds between requests (floor: {config.MIN_INTERVAL})",
    )
    parser.add_argument(
        "--state", default="", help=f"state directory (default: {config.DEFAULT_STATE_DIR})"
    )
    parser.add_argument("--quiet", action="store_true", help="silence progress notes")


def main(argv: list[str] | None = None) -> int:
    """Parse *argv*, run the command, and return the exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return EXIT_ERROR

    settings = config.resolve(args)
    try:
        return args.handler(args, settings)
    except NotAUid as exc:
        render.fail(str(exc), code="invalid_uid")
    except ValueError as exc:
        render.fail(str(exc), code="invalid_argument")
    except AuthenticationError as exc:
        render.fail(str(exc), code="authentication_failed")
    except (ZefixError, ShabError) as exc:
        render.fail(str(exc), code="upstream_error")
    except OSError as exc:
        render.fail(str(exc), code="io_error")
    except KeyboardInterrupt:
        render.fail("interrupted", code="interrupted")
    return EXIT_ERROR


def _lookup(args, settings: config.Config) -> int:
    uid = companies.resolve_uid(args.uid)
    with sources.lindas(settings) as client:
        entity = companies.lookup(client, uid)
    if entity is None:
        render.fail(f"no company with UID {args.uid} in the LINDAS dataset", code="not_found")
        return EXIT_ERROR

    row = companies.entity_row(entity)
    if settings.has_credentials:
        with sources.zefix_rest(settings) as rest:
            company = rest.get_by_uid(uid)
        if company is not None:
            row.update(companies.rest_row(company))
    else:
        render.note(
            "LINDAS only. Zefix PublicREST credentials add capital, status, "
            "former names and corporate relations.",
            quiet=settings.quiet,
        )

    render.emit_object(row, fmt=args.fmt)
    return EXIT_OK


def _search(args, settings: config.Config) -> int:
    if args.via == "rest":
        if not settings.has_credentials:
            render.fail(
                "--via rest needs Zefix PublicREST credentials "
                "(--user/--password or ZEFIX_USER/ZEFIX_PASSWORD)",
                code="credentials_required",
            )
            return EXIT_ERROR
        with sources.zefix_rest(settings) as client:
            hits = companies.search_rest(client, args.term, limit=args.limit)
        rows = [companies.rest_search_row(hit) for hit in hits]
    else:
        with sources.lindas(settings) as client:
            found = companies.search(
                client,
                args.term,
                canton=args.canton,
                legal_form=args.legal_form,
                limit=args.limit,
            )
        rows = [companies.search_row(entity) for entity in found]

    if not rows:
        render.note(f"no companies matching {args.term!r}", quiet=settings.quiet)
    render.emit(rows, fmt=args.fmt)
    return EXIT_OK


def _publications(args, settings: config.Config) -> int:
    start, end = _range(args, default_days=1)
    entries = _discover(settings, start, end)
    entries = publications.filter_entries(
        entries,
        cantons=args.canton,
        sub_rubrics=args.sub_rubric,
        since=start,
        until=end,
        query=args.query,
    )

    if not args.type:
        rows = [publications.entry_row(entry) for entry in entries[: args.limit]]
        render.emit(rows, fmt=args.fmt)
        return EXIT_OK

    wanted = set(args.type)
    render.note(
        f"{len(entries)} publications match the filters; fetching each body to "
        f"classify it, at {settings.interval}s per request",
        quiet=settings.quiet,
    )
    rows = []
    with sources.shab(settings) as client:
        for entry in entries:
            if len(rows) >= args.limit:
                break
            content = events.body(client, entry)
            if content is None:
                continue
            try:
                publication = parse_xml(
                    content,
                    source_url=entry.ref.url,
                    ref_state=entry.ref.publication_state,
                )
            except Exception:
                continue
            found = [e.event_type.value for e in publication.events]
            if not wanted.intersection(found):
                continue
            rows.append(publications.publication_row(entry, publication, found))

    render.emit(rows, fmt=args.fmt)
    return EXIT_OK


def _events(args, settings: config.Config) -> int:
    uid = companies.resolve_uid(args.uid)
    with sources.lindas(settings) as client:
        entity = companies.lookup(client, uid)
    if entity is None:
        render.fail(f"no company with UID {args.uid} in the LINDAS dataset", code="not_found")
        return EXIT_ERROR

    start, end = _range(args, default_days=365)
    render.note(
        f"{entity.legal_name}: scanning the gazette from {start} to {end}. "
        f"{_page_estimate(start, end)}",
        quiet=settings.quiet,
    )

    entries = _discover(settings, start, end)
    candidates = events.prefilter(entries, entity.legal_name)
    render.note(
        f"{len(entries)} publications listed, {len(candidates)} match the name; "
        "fetching those bodies to confirm the UID",
        quiet=settings.quiet,
    )

    cache = None if args.no_cache else settings.state_dir / "cache"
    with sources.shab(settings) as client:
        found = events.collect(client, candidates, uid, cache_dir=cache)

    rows = [events.event_row(event) for event in found[: args.limit]]
    if not rows:
        render.note("no confirmed events in this range", quiet=settings.quiet)
    render.emit(rows, fmt=args.fmt)
    return EXIT_OK


def _watch(args, settings: config.Config) -> int:
    path = Path(args.uids).expanduser()
    if not path.exists():
        render.fail(f"no such file: {path}", code="not_found")
        return EXIT_ERROR

    raw_uids = watch.read_uids(path)
    if not raw_uids:
        render.fail(f"{path} lists no UIDs", code="empty_input")
        return EXIT_ERROR

    resolved, rejected = [], []
    for value in raw_uids:
        try:
            resolved.append(companies.resolve_uid(value))
        except NotAUid:
            rejected.append(value)
    for value in rejected:
        render.note(f"skipping {value!r}: not a valid UID", quiet=settings.quiet)
    if not resolved:
        render.fail(f"{path} lists no valid UIDs", code="invalid_uid")
        return EXIT_ERROR

    previous = watch.load_state(settings.state_dir)
    current: dict[str, dict] = {}
    with sources.lindas(settings) as client:
        for batch in _batched(resolved, 200):
            for entity in client.fetch_by_uids(batch):
                if entity.uid:
                    current[entity.uid] = watch.snapshot(entity)

    report = watch.diff(previous, current, requested=resolved)
    saved = watch.save_state(settings.state_dir, current)
    render.note(
        f"{len(current)} of {len(resolved)} companies found; "
        f"{report.unchanged} unchanged. State written to {saved}",
        quiet=settings.quiet,
    )

    render.emit(report.rows(), fmt=args.fmt)
    return EXIT_CHANGED if report.has_changes else EXIT_OK


def _discover(
    settings: config.Config, start: date, end: date
) -> list[publications.ListEntry]:
    """List every publication in the range, reporting each window as it lands."""
    seen = 0

    def progress(window_start: date, window_end: date, total: int) -> None:
        nonlocal seen
        seen += total
        render.note(
            f"  {window_start} to {window_end}: {total} publications",
            quiet=settings.quiet,
        )

    with sources.shab(settings) as client:
        return publications.discover(client, start, end, on_window=progress)


def _range(args, *, default_days: int) -> tuple[date, date]:
    """The date window, defaulting to the *default_days* ending today."""
    end = args.until or date.today()
    start = args.since or end - timedelta(days=default_days)
    if start > end:
        raise ValueError(f"--since {start} is after --until {end}")
    return start, end


def _page_estimate(start: date, end: date) -> str:
    """How long listing this range will take, before any body is fetched.

    The gazette publishes roughly a thousand commercial-register entries a day.
    Each list page holds 2,000, and a range past ten days is split into several
    windows, so both numbers grow with the range.
    """
    days = (end - start).days + 1
    listed = days * PUBLICATIONS_PER_DAY
    windows = max(1, -(-listed // publications.OFFSET_WINDOW))
    # Per state: one probe request per window plus the pages it takes to read
    # it. Doubled, because PUBLISHED and CANCELLED are listed separately.
    requests = 2 * (windows + max(1, -(-listed // events.PAGE_SIZE)))
    if requests <= 4:
        return "One or two list pages per publication state."
    return (
        f"About {requests} list requests across {windows} windows and both "
        f"publication states, so at least {round(requests * 0.5)}s before any "
        "body is fetched."
    )


def _batched(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a date (expected YYYY-MM-DD)")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
