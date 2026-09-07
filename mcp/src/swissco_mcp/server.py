"""The nine tools, and what each one carries back with its rows.

Each tool assembles the same calls ``swissco`` assembles, in the same order,
and returns the rows the same ``*_row()`` builders produce. A field in an MCP
result and the same field in ``swissco --format json`` carry the same name and
the same value.

**Every result carries its caveats in ``notes``.** The command line writes
those caveats to
stderr, where a person reads them next to the table: absence from LINDAS is not
deletion, FINMA's list covers banks and securities firms and no other licence
type, about 28,000 Swiss entities hold an LEI, ARAMIS indexes no participant
list. Here they come back next to the rows they qualify.

**The work is capped.** A tool result lands in a context window, and a wide
gazette range costs one request per 2,000 publications at a half-second floor.
``limit`` stops at :data:`MAX_LIMIT`, ``swissco_publications`` stops at
:data:`MAX_PUBLICATION_DAYS` and ``swissco_events`` at :data:`MAX_EVENT_DAYS`.
A trimmed request says so in ``notes`` and reports what it did instead.

**Settings come from the environment.** ``ZEFIX_USER`` and ``ZEFIX_PASSWORD``
extend ``swissco_lookup`` and ``swissco_search``; ``SWISSCO_STATE`` moves the
cache; ``SWISSCO_INTERVAL`` raises the pacing floor. It cannot lower it:
:mod:`swissco.sources` clamps every client with ``max(interval, MIN_INTERVAL)``
and the sources this reaches are small public services run by federal offices.
"""

from __future__ import annotations

import functools
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from shab_parser import EventType, ShabError, parse_xml
from swissco import (
    aramis,
    companies,
    config,
    events,
    finma,
    gleif,
    publications,
    render,
    simap,
    sources,
)
from swissco._http import HttpError
from swissco.companies import NotAUid
from zefix_parser import AuthenticationError, ZefixError

from . import __version__

#: The most rows any tool returns. A result is read by a model, and a hundred
#: rows of a nine-column table is already most of what it can weigh at once.
MAX_LIMIT = 100

#: The widest gazette range ``swissco_publications`` will list.
MAX_PUBLICATION_DAYS = 7

#: The widest gazette range ``swissco_events`` will scan. A year is what the
#: command line defaults to, and the name prefilter keeps the body fetches
#: proportional to the company rather than to the range.
MAX_EVENT_DAYS = 365

EVENT_TYPES = tuple(e.value for e in EventType)

GLEIF_CONSOLIDATION = (
    'direct_parent and ultimate_parent read as "consolidated by". GLEIF '
    "Level 2 records accounting consolidation, so a parent here is the entity "
    "that reports this one into its accounts."
)

LINDAS_ONLY = (
    "LINDAS only. Zefix PublicREST credentials in ZEFIX_USER and "
    "ZEFIX_PASSWORD add capital, status, former names and corporate relations."
)

INSTRUCTIONS = """\
Swiss company data from six federal and international open-data sources: the
commercial register (Zefix on LINDAS), the Swiss Official Gazette of Commerce
(SHAB), public procurement (simap), FINMA's authorised banks and securities
firms, the Legal Entity Identifier (GLEIF) and federally funded research
(ARAMIS).

Start from a UID, the Swiss company number, written CHE-123.456.789. Use
swissco_search to find one from a name or from what a company says it does.

Read the `notes` on every result. They carry what each source does and does not
cover, and a source's silence usually means the company sits outside that
source's scope.
"""

mcp = MCPServer(
    "swissco",
    title="Swiss company data",
    version=__version__,
    website_url="https://prospex.ch",
    instructions=INSTRUCTIONS,
)

#: Every tool reads a public register and writes nothing. ``open_world_hint``
#: because the answer comes from a live service; ``idempotent_hint`` because
#: asking twice costs two requests and returns the same rows.
READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    idempotent_hint=True,
    open_world_hint=True,
)


@dataclass(frozen=True)
class ToolResult:
    """What every tool returns.

    ``rows`` are the same dicts ``swissco --format json`` prints, ``count`` is
    how many there are, and ``notes`` carry the caveats and the trimming
    decisions.
    """

    rows: list[dict[str, Any]]
    count: int
    notes: list[str] = field(default_factory=list)


# -- plumbing ----------------------------------------------------------------


def _settings() -> config.Config:
    """The configuration, read from the environment.

    ``config.resolve`` takes an argparse namespace, so this builds the frozen
    dataclass itself. ``quiet`` is on: a stdio server writes the protocol to
    stdout and has no terminal to print progress to.
    """
    state = os.environ.get("SWISSCO_STATE", "")
    return config.Config(
        username=os.environ.get("ZEFIX_USER", ""),
        password=os.environ.get("ZEFIX_PASSWORD", ""),
        interval=_interval(),
        state_dir=Path(state).expanduser() if state else config.DEFAULT_STATE_DIR,
        quiet=True,
    )


def _interval() -> float:
    """``SWISSCO_INTERVAL`` clamped up to the floor, which it cannot go under."""
    raw = os.environ.get("SWISSCO_INTERVAL", "").strip()
    if not raw:
        return config.MIN_INTERVAL
    try:
        return max(config.MIN_INTERVAL, float(raw))
    except ValueError:
        raise ToolError(
            f"SWISSCO_INTERVAL is {raw!r}, which is not a number of seconds"
        ) from None


def _readable(fn):
    """Re-raise ``swissco``'s own exceptions so the model reads their message.

    The SDK turns a ``ToolError`` into a tool error carrying the text and
    everything else into ``Error executing tool <name>``, which withholds it.
    The messages this package raises are the ones a caller needs ("expected
    CHE-123.456.789 with a valid check digit"), so they are handed over as
    written.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except (
            NotAUid,
            ValueError,
            AuthenticationError,
            ZefixError,
            ShabError,
            simap.SimapError,
            finma.FinmaError,
            gleif.GleifError,
            aramis.AramisError,
            HttpError,
            OSError,
        ) as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


def _enumerating(**values):
    """Fill an enumeration into a docstring before the tool is registered.

    ``@mcp.tool`` reads the description at decoration time, so a list of every
    event type is formatted in here rather than typed out. A new one upstream
    reaches the tool description on its own.
    """

    def decorate(fn):
        fn.__doc__ = (fn.__doc__ or "").format(**values)
        return fn

    return decorate


def _result(rows: list[dict], notes: list[str]) -> ToolResult:
    """Rows and notes as one envelope, dates rendered the way JSON output is."""
    return ToolResult(rows=[_plain(row) for row in rows], count=len(rows), notes=notes)


def _plain(value):
    """*value* with every :class:`~datetime.date` in it turned into a day.

    Several row builders hand back a ``date`` object, and
    :func:`swissco.render.jsonable` is what ``--format json`` serialises it
    with, so both surfaces spell a day the same way.
    """
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, date):
        return render.jsonable(value)
    return value


def _capped(limit: int, notes: list[str]) -> int:
    """*limit* within 1 and :data:`MAX_LIMIT`, noting a trim."""
    if limit < 1:
        raise ToolError(f"limit must be at least 1, got {limit}")
    if limit > MAX_LIMIT:
        notes.append(f"limit lowered from {limit} to {MAX_LIMIT}, the per-call maximum.")
        return MAX_LIMIT
    return limit


def _day(value: str, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolError(
            f"{name} is {value!r}, which is not a date (expected YYYY-MM-DD)"
        ) from None


def _window(
    since: str,
    until: str,
    *,
    default_days: int,
    max_days: int = 0,
    notes: list[str],
) -> tuple[date, date]:
    """The date range to ask for, defaulted and clamped.

    *until* defaults to today and *since* to *default_days* before it. A range
    wider than *max_days* is moved forward to end on *until*, so the newest
    part of what was asked for is the part that gets read.
    """
    end = _day(until, "until") if until else date.today()
    start = _day(since, "since") if since else end - timedelta(days=default_days)
    if start > end:
        raise ToolError(f"since {start} is after until {end}")
    if max_days and (end - start).days > max_days:
        start = end - timedelta(days=max_days)
        notes.append(
            f"range trimmed to {start} .. {end}: one call reads at most "
            f"{max_days} days of the gazette."
        )
    return start, end


def _choices(values: list[str] | None, allowed, name: str) -> tuple[str, ...]:
    """*values* checked against *allowed*, so a typo fails before a request."""
    picked = tuple(v.strip() for v in (values or []) if v.strip())
    unknown = [v for v in picked if v not in allowed]
    if unknown:
        raise ToolError(
            f"{name} {', '.join(repr(v) for v in unknown)} is not one of: "
            f"{', '.join(sorted(allowed))}"
        )
    return picked


def _cantons(values: list[str] | None) -> tuple[str, ...]:
    return tuple(v.strip().upper() for v in (values or []) if v.strip())


def _listed(settings: config.Config, start: date, end: date, notes: list[str]):
    """List the gazette range, reporting the windows as one note rather than many.

    A year is around seventy windows, and seventy progress lines in a tool
    result would crowd out the rows.
    """
    windows = 0
    listed = 0

    def progress(_start: date, _end: date, total: int) -> None:
        nonlocal windows, listed
        windows += 1
        listed += total

    with sources.shab(settings) as client:
        entries = publications.discover(client, start, end, on_window=progress)

    notes.append(
        f"{listed} publications listed across {windows} window(s) "
        f"from {start} to {end}."
    )
    return entries


# -- the register ------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
@_readable
def swissco_lookup(
    uid: Annotated[
        str,
        Field(
            description="A Swiss UID in any punctuation: CHE-444.420.929, "
            "CHE444420929, or a CH-ID."
        ),
    ],
    finma_licence: Annotated[
        bool,
        Field(
            description="Add the FINMA licence type and supervisory category. "
            "Costs two downloads on a cold cache."
        ),
    ] = False,
    lei: Annotated[
        bool,
        Field(
            description="Add the LEI and the entities that consolidate this "
            "one. Costs three requests."
        ),
    ] = False,
) -> ToolResult:
    """Everything the commercial register publishes about one company.

    One row: ``legal_name``, ``uid``, ``chid``, ``ehra_id``,
    ``legal_form_code``, ``legal_form``, ``municipality``, ``canton``,
    ``address``, ``purpose`` and ``zefix_uri``. With Zefix PublicREST
    credentials in the environment it also carries ``status``,
    ``capital_nominal``, ``capital_currency``, ``deletion_date``,
    ``old_names``, ``branch_offices``, ``head_offices``, ``has_taken_over``,
    ``was_taken_over_by`` and ``cantonal_excerpt``.

    ``finma_licence`` adds ``finma_licence``, ``finma_category``,
    ``finma_city`` and ``finma_flags``. ``lei`` adds ``lei``, ``lei_status``,
    ``direct_parent`` and ``ultimate_parent``.

    ``purpose`` is the statutory purpose: how the company describes what it
    does, in its own words, filed with the register.
    """
    notes: list[str] = []
    settings = _settings()
    asked = uid
    uid = companies.resolve_uid(uid)

    with sources.lindas(settings) as client:
        entity = companies.lookup(client, uid)
    if entity is None:
        raise ToolError(
            f"no company with UID {asked} in the LINDAS dataset. The dataset "
            "covers the active commercial register, so a deleted company can "
            "be missing from it while its gazette publications remain."
        )

    row = companies.entity_row(entity)
    if settings.has_credentials:
        with sources.zefix_rest(settings) as rest:
            company = rest.get_by_uid(uid)
        if company is not None:
            row.update(companies.rest_row(company))
    else:
        notes.append(LINDAS_ONLY)

    if finma_licence:
        with sources.finma(settings, on_note=notes.append) as client:
            snapshot = finma.snapshot(
                client,
                cache_dir=settings.state_dir / "cache",
                on_note=notes.append,
            )
        record = finma.by_uid(snapshot, uid)
        if record is None:
            notes.append(
                "not on FINMA's authorised banks and securities firms list. "
                "That list omits insurers, portfolio managers and fund "
                "management companies, which FINMA publishes separately."
            )
        else:
            row.update(finma.lookup_fields(record))

    if lei:
        with sources.gleif(settings, on_note=notes.append) as client:
            lei_record = gleif.find_by_uid(client, uid)
            if lei_record is None:
                notes.append(
                    "no LEI on file at GLEIF. About 28,000 Swiss entities hold "
                    "one against roughly 790,000 in the commercial register, "
                    "so a miss here says nothing about the company."
                )
            else:
                found = gleif.group(client, lei_record.lei)
                row.update(gleif.lookup_fields(lei_record, found))
                notes.append(GLEIF_CONSOLIDATION)

    return _result([row], notes)


@mcp.tool(annotations=READ_ONLY)
@_readable
def swissco_search(
    term: Annotated[
        str,
        Field(description="Text to look for in the legal name or the statutory purpose."),
    ],
    canton: Annotated[
        str, Field(description="Two-letter canton code, e.g. VD. LINDAS only.")
    ] = "",
    legal_form: Annotated[
        str, Field(description="eCH-0097 legal-form code, e.g. 0106 for an AG. LINDAS only.")
    ] = "",
    via: Annotated[
        Literal["lindas", "rest"],
        Field(
            description="lindas matches a substring of the name or the purpose; "
            "rest matches a name prefix and needs Zefix PublicREST credentials."
        ),
    ] = "lindas",
    limit: Annotated[int, Field(description="Maximum rows.")] = 20,
) -> ToolResult:
    """Companies whose name or statutory purpose contains *term*.

    Over LINDAS, each row carries ``legal_name``, ``uid``, ``legal_form``,
    ``municipality``, ``canton`` and ``purpose``. Over PublicREST:
    ``legal_name``, ``uid``, ``chid``, ``ehra_id``, ``canton`` and ``status``.

    The purpose is what makes this worth running. It is how a company
    describes its own business to the register, so "hydrogen storage" finds
    companies whose name mentions neither word. ``via="rest"`` matches the
    start of a name instead.
    """
    notes: list[str] = []
    settings = _settings()
    limit = _capped(limit, notes)

    if via == "rest":
        if not settings.has_credentials:
            raise ToolError(
                "via='rest' needs Zefix PublicREST credentials in ZEFIX_USER "
                "and ZEFIX_PASSWORD. via='lindas' needs none and searches the "
                "purpose as well as the name."
            )
        if canton or legal_form:
            notes.append(
                "canton and legal_form filter the LINDAS path only; PublicREST "
                "search takes a name prefix and nothing else."
            )
        with sources.zefix_rest(settings) as client:
            hits = companies.search_rest(client, term, limit=limit)
        rows = [companies.rest_search_row(hit) for hit in hits]
    else:
        with sources.lindas(settings) as client:
            found = companies.search(
                client, term, canton=canton, legal_form=legal_form, limit=limit
            )
        rows = [companies.search_row(entity) for entity in found]

    if not rows:
        notes.append(
            f"no companies matching {term!r}. LINDAS matches a substring "
            "case-insensitively, so a shorter term usually finds more."
        )
    return _result(rows, notes)


# -- the gazette -------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
@_enumerating(event_types=", ".join(EVENT_TYPES))
@_readable
def swissco_publications(
    since: Annotated[
        str, Field(description="First publication date, YYYY-MM-DD. Defaults to yesterday.")
    ] = "",
    until: Annotated[
        str, Field(description="Last publication date, YYYY-MM-DD. Defaults to today.")
    ] = "",
    cantons: Annotated[
        list[str] | None, Field(description="Canton codes to keep, e.g. ['ZH', 'ZG'].")
    ] = None,
    sub_rubrics: Annotated[
        list[str] | None,
        Field(description="HR01 registrations, HR02 mutations, HR03 deletions."),
    ] = None,
    event_types: Annotated[
        list[str] | None,
        Field(
            description="Keep only publications carrying one of these events. "
            "Each one costs a body fetch."
        ),
    ] = None,
    query: Annotated[
        str, Field(description="Text to look for in the title, in any of the four languages.")
    ] = "",
    limit: Annotated[int, Field(description="Maximum rows.")] = 20,
) -> ToolResult:
    """Commercial-register publications from the Swiss Official Gazette of Commerce.

    Each row carries ``publication_date``, ``canton``, ``sub_rubric``,
    ``title``, ``language``, ``state``, ``id`` and ``url``. With
    ``event_types``, each body is fetched and parsed, and the rows instead
    carry ``publication_date``, ``canton``, ``sub_rubric``, ``company_name``,
    ``uid``, ``events``, ``effective_date``, ``state``, ``id`` and ``url``.

    The event types are: {event_types}.

    The gazette publishes around a thousand commercial-register entries a day.
    Every filter here is applied over the listed publications, because the
    anonymous API ignores its own ``cantons``, ``subRubrics`` and ``q``
    parameters.
    """
    notes: list[str] = []
    settings = _settings()
    limit = _capped(limit, notes)
    start, end = _window(
        since, until, default_days=1, max_days=MAX_PUBLICATION_DAYS, notes=notes
    )
    wanted = _choices(event_types, EVENT_TYPES, "event type")

    notes.append(publications.estimate(start, end))
    entries = publications.filter_entries(
        _listed(settings, start, end, notes),
        cantons=cantons,
        sub_rubrics=sub_rubrics,
        since=start,
        until=end,
        query=query,
    )

    if not wanted:
        return _result([publications.entry_row(entry) for entry in entries[:limit]], notes)

    notes.append(
        f"{len(entries)} publications match the filters; each body is fetched "
        f"to classify it, at {settings.interval}s per request."
    )
    rows = []
    with sources.shab(settings) as client:
        for entry in entries:
            if len(rows) >= limit:
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
            if not set(wanted).intersection(found):
                continue
            rows.append(publications.publication_row(entry, publication, found))

    return _result(rows, notes)


@mcp.tool(annotations=READ_ONLY)
@_readable
def swissco_events(
    uid: Annotated[str, Field(description="The company's UID.")],
    since: Annotated[
        str, Field(description="First publication date, YYYY-MM-DD. Defaults to a year ago.")
    ] = "",
    until: Annotated[
        str, Field(description="Last publication date, YYYY-MM-DD. Defaults to today.")
    ] = "",
    limit: Annotated[int, Field(description="Maximum rows.")] = 20,
) -> ToolResult:
    """One company's registry events, each confirmed against the publication's own UID.

    Each row carries ``publication_date``, ``event_type``,
    ``effective_date``, ``company_name``, ``uid``, ``canton``,
    ``sub_rubric``, ``id`` and ``url``, newest first.

    The gazette's list page carries a title and no UID, so the UID resolves to
    a legal name, the name selects candidate publications, and each candidate's
    body is fetched and kept only when its own UID matches. A publication
    carrying no UID is dropped.

    Bodies are cached under the state directory and keyed by publication id, so
    an overlapping second call over the same range costs almost nothing.
    """
    notes: list[str] = []
    settings = _settings()
    limit = _capped(limit, notes)
    asked = uid
    uid = companies.resolve_uid(uid)

    with sources.lindas(settings) as client:
        entity = companies.lookup(client, uid)
    if entity is None:
        raise ToolError(f"no company with UID {asked} in the LINDAS dataset")

    start, end = _window(
        since, until, default_days=MAX_EVENT_DAYS, max_days=MAX_EVENT_DAYS, notes=notes
    )
    notes.append(f"{entity.legal_name}: {publications.estimate(start, end)}")

    entries = _listed(settings, start, end, notes)
    candidates = events.prefilter(entries, entity.legal_name)
    notes.append(
        f"{len(candidates)} of them match the name; those bodies are fetched "
        "to confirm the UID."
    )

    with sources.shab(settings) as client:
        found = events.collect(
            client, candidates, uid, cache_dir=settings.state_dir / "cache"
        )

    rows = [events.event_row(event) for event in found[:limit]]
    if not rows:
        notes.append(
            "no confirmed events in this range. The register publishes only "
            "what changed, so a company that filed nothing has nothing here."
        )
    return _result(rows, notes)


# -- procurement -------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
@_enumerating(pub_types=", ".join(simap.KNOWN_PUB_TYPES))
@_readable
def swissco_tenders(
    since: Annotated[
        str, Field(description="First publication date, YYYY-MM-DD. Defaults to a week ago.")
    ] = "",
    until: Annotated[
        str, Field(description="Last publication date, YYYY-MM-DD. Defaults to today.")
    ] = "",
    cantons: Annotated[
        list[str] | None, Field(description="Canton codes to keep, e.g. ['ZH', 'ZG'].")
    ] = None,
    pub_types: Annotated[
        list[str] | None,
        Field(description="Publication types to keep, e.g. ['tender', 'award']."),
    ] = None,
    lang: Annotated[
        str,
        Field(
            description="Preferred language for the title and buyer: de, fr, "
            "it or en. Defaults to de, then fr, it, en."
        ),
    ] = "",
    limit: Annotated[int, Field(description="Maximum rows.")] = 20,
) -> ToolResult:
    """Public-procurement projects published on simap.

    Each row carries ``title``, ``project_number``, ``buyer``, ``canton``,
    ``city``, ``project_type``, ``process_type``, ``publication_date``,
    ``publication_type``, ``project_id`` and ``publication_id``.

    The publication types are: {pub_types}.

    The date matches each project's newest publication, whichever type that
    publication is, and ``pub_types`` is what narrows it to awards. The
    supplier named on an award carries no UID, so this lists projects and
    buyers. Use ``swissco_vendor`` for whether a given company is in simap's
    vendor directory.
    """
    notes: list[str] = []
    settings = _settings()
    limit = _capped(limit, notes)
    start, end = _window(since, until, default_days=7, notes=notes)
    wanted = _choices(pub_types, simap.KNOWN_PUB_TYPES, "publication type")
    if lang and lang not in simap.LANGUAGE_ORDER:
        raise ToolError(
            f"lang is {lang!r}; simap publishes in {', '.join(simap.LANGUAGE_ORDER)}"
        )

    notes.append(
        f"simap projects published {start} to {end}. The date matches each "
        "project's newest publication, whichever type that publication is."
    )
    with sources.simap(settings, on_note=notes.append) as client:
        rows = [
            simap.tender_row(project, lang=lang)
            for project in simap.iter_projects(
                client,
                since=start,
                until=end,
                pub_types=wanted,
                cantons=_cantons(cantons),
                limit=limit,
            )
        ]

    if not rows:
        notes.append("no projects in this range.")
    return _result(rows, notes)


@mcp.tool(annotations=READ_ONLY)
@_readable
def swissco_vendor(
    query: Annotated[
        str,
        Field(
            description="A UID, which is confirmed exactly, or text to search "
            "vendor names for."
        ),
    ],
    limit: Annotated[int, Field(description="Maximum rows on the text path.")] = 20,
) -> ToolResult:
    """A company in simap's vendor directory, by UID or by name.

    A text query returns rows of ``name``, ``uid_no``, ``canton``, ``city``,
    ``postal_code``, ``active``, ``is_bidding_consortium`` and ``vendor_id``.

    A UID resolves to a legal name, searches the directory for it and keeps
    only profiles whose own ``uidNo`` matches, then returns that profile:
    ``name``, ``uid_no``, ``additional_name``, ``street``, ``postal_code``,
    ``city``, ``canton``, ``url``, ``company_size``, ``type_of_services``,
    ``cpv_codes``, ``bkp_codes``, ``npk_codes``, ``business_purpose``,
    ``is_bidding_consortium``, ``leading_vendor_name`` and ``vendor_id``.

    A company can bid without holding a directory profile, and a bidding
    consortium carries no UID at all, so an absent UID means only that no
    profile is filed under it.
    """
    notes: list[str] = []
    settings = _settings()
    limit = _capped(limit, notes)
    try:
        uid = companies.resolve_uid(query)
    except NotAUid:
        uid = ""

    with sources.simap(settings, on_note=notes.append) as client:
        if not uid:
            rows = [
                simap.vendor_row(vendor)
                for vendor in simap.iter_vendors(client, search=query, limit=limit)
            ]
            if not rows:
                notes.append(f"no vendor profile whose name matches {query!r}.")
            return _result(rows, notes)

        with sources.lindas(settings) as lindas:
            entity = companies.lookup(lindas, uid)
        if entity is None:
            raise ToolError(f"no company with UID {query} in the LINDAS dataset")

        notes.append(f"searching the simap vendor directory for {entity.legal_name!r}.")
        found = list(
            simap.iter_vendors(client, search=entity.legal_name, limit=max(limit, 50))
        )
        confirmed = simap.confirmed_by_uid(found, uid)
        if not confirmed:
            raise ToolError(
                f"{entity.legal_name} is not in the simap vendor directory "
                f"under {uid}. A company can bid without a directory profile, "
                "and a consortium profile carries no UID at all."
            )
        notes.append(
            f"{len(confirmed)} profile(s) confirmed on the directory's own uidNo."
        )
        profile = simap.parse_vendor_public(
            client.fetch_vendor_public(confirmed[0].vendor_id)
        )

    return _result([simap.vendor_profile_row(profile)], notes)


# -- supervision, identifiers, research --------------------------------------


@mcp.tool(annotations=READ_ONLY)
@_readable
def swissco_finma(
    query: Annotated[
        str, Field(description="Text to match in the institution's name or city.")
    ] = "",
    uid: Annotated[str, Field(description="One institution by UID.")] = "",
    licence_type: Annotated[
        str,
        Field(
            description="Bank, Securities firm, Foreign bank branch office, or "
            "Foreign securities firm branch office."
        ),
    ] = "",
    category: Annotated[
        str, Field(description="FINMA supervisory category, 1 to 5. 1 is the largest.")
    ] = "",
    limit: Annotated[int, Field(description="Maximum rows.")] = 20,
) -> ToolResult:
    """Institutions on FINMA's list of authorised banks and securities firms.

    Each row carries ``name``, ``city``, ``licence_type``,
    ``supervisory_category``, ``uid``, ``foreign_control``,
    ``no_securities_firm_activity``,
    ``non_account_holding_securities_firm`` and
    ``about_to_cease_operations``.

    This one list covers banks and securities firms. Insurers, portfolio
    managers and fund management companies hold their authorisations on other
    FINMA lists, so a company absent here may still be supervised. FINMA also
    publishes some authorised institutions with no UID, which no UID lookup can
    reach.

    Both published files are cached under the state directory for a day, so the
    first call in a day is the slow one.
    """
    notes: list[str] = []
    settings = _settings()
    limit = _capped(limit, notes)
    if licence_type and licence_type not in finma.LICENCE_TYPES:
        raise ToolError(
            f"licence_type is {licence_type!r}; FINMA publishes "
            f"{', '.join(sorted(finma.LICENCE_TYPES))}"
        )
    if category and category not in finma.CATEGORIES:
        raise ToolError(f"category is {category!r}; FINMA uses 1 to 5")

    with sources.finma(settings, on_note=notes.append) as client:
        snapshot = finma.snapshot(
            client, cache_dir=settings.state_dir / "cache", on_note=notes.append
        )

    notes.append(
        f"FINMA lists {snapshot.declared_total} authorised banks and "
        f"securities firms; {snapshot.with_uid} carry a UID. Insurers, "
        "portfolio managers and fund management companies are on other lists."
    )

    if uid:
        record = finma.by_uid(snapshot, companies.resolve_uid(uid))
        if record is None:
            raise ToolError(
                f"{uid} is not on FINMA's authorised banks and securities "
                "firms list. That differs from unauthorised: FINMA publishes "
                "some authorised institutions with no UID, and other licence "
                "types on other lists."
            )
        return _result([finma.bank_row(record)], notes)

    records = finma.filter_records(
        snapshot, query=query, licence_type=licence_type, category=category
    )
    return _result([finma.bank_row(record) for record in records[:limit]], notes)


@mcp.tool(annotations=READ_ONLY)
@_readable
def swissco_lei(
    uid: Annotated[str, Field(description="The company's UID.")],
    children: Annotated[
        bool,
        Field(description="List the entities this one consolidates instead of counting them."),
    ] = False,
    limit: Annotated[int, Field(description="Maximum children.")] = 20,
) -> ToolResult:
    """A company's Legal Entity Identifier and the group it is consolidated into.

    One row: ``legal_name``, ``lei``, ``registered_as``, ``jurisdiction``,
    ``status``, ``registration_status``, ``legal_form``, ``city``,
    ``country``, ``other_names``, ``bic``, ``initial_registration_date``,
    ``last_update_date``, ``next_renewal_date``, ``direct_parent``,
    ``ultimate_parent`` and ``direct_children``.

    With ``children``, one row per consolidated entity: ``legal_name``,
    ``lei``, ``jurisdiction``, ``registered_as``, ``status``, ``city`` and
    ``country``.

    GLEIF Level 2 records accounting consolidation, so a parent here is the
    entity that consolidates this one into its accounts. That parent is
    frequently foreign, which is the case for reading it: the Swiss commercial
    register carries no entry for a Swiss company's owner abroad.

    About 28,000 Swiss entities hold an LEI against roughly 790,000 in the
    commercial register. An absent LEI is the normal case.
    """
    notes: list[str] = []
    settings = _settings()
    limit = _capped(limit, notes)
    uid = companies.resolve_uid(uid)

    with sources.gleif(settings, on_note=notes.append) as client:
        record = gleif.find_by_uid(client, uid)
        if record is None:
            raise ToolError(
                f"no LEI filed at GLEIF under {gleif.dotted(uid)}. About "
                "28,000 Swiss entities hold an LEI against roughly 790,000 in "
                "the commercial register, so this means the company has no "
                "LEI on file."
            )
        found = gleif.group(client, record.lei, children=True, page_size=limit)

    notes.append(GLEIF_CONSOLIDATION)
    if children:
        page = found.direct_children
        notes.append(
            f"{record.legal_name} consolidates {page.total} entities directly."
        )
        return _result([gleif.child_row(e) for e in page.entities[:limit]], notes)

    return _result([gleif.lei_row(record, found)], notes)


@mcp.tool(annotations=READ_ONLY)
@_readable
def swissco_research(
    query: Annotated[
        str,
        Field(
            description="A UID, which is confirmed against each project's "
            "participant UID, or text to search projects for."
        ),
    ],
    language: Annotated[
        str, Field(description="Service language: DE, EN, FR or IT. Case-sensitive.")
    ] = aramis.DEFAULT_LANGUAGE,
    limit: Annotated[int, Field(description="Maximum rows.")] = 20,
) -> ToolResult:
    """Federally funded research projects from ARAMIS, Innosuisse and SNSF money included.

    A text query returns rows of ``title``, ``project_number``, ``office``,
    ``status``, ``start_date``, ``end_date``, ``granted_total_costs``,
    ``participants`` and ``aramis_id``.

    A UID searches ARAMIS for the company's name, then keeps only projects
    carrying a participant whose own UID matches, and reports ``role`` and
    ``uid`` in place of ``participants``.

    ARAMIS searches project titles, abstracts and the free-text contractor
    field, and indexes the structured participant list under none of them. A
    company named only as a structured partner cannot be found, which is where
    Innosuisse implementation partners usually sit. An empty result means no
    project mentions the company by name, and is not evidence that it took no
    federal research money.
    """
    notes: list[str] = []
    settings = _settings()
    limit = _capped(limit, notes)
    language = aramis.check_language(language)
    try:
        uid = companies.resolve_uid(query)
    except NotAUid:
        uid = ""

    with sources.aramis(settings, on_note=notes.append) as client:
        if not uid:
            found = aramis.search(client, keywords=query, language=language, limit=limit)
            if not found:
                notes.append(
                    f"no ARAMIS project matching {query!r}. The service reaches "
                    "titles, abstracts and the contractor field, and no "
                    "participant list."
                )
                return _result([], notes)
            notes.append(
                f"{len(found)} projects match; each is fetched to list its "
                f"participants, at {settings.interval}s per request."
            )
            details = aramis.hydrate(client, found, language=language)
            return _result([aramis.project_row(d) for d in details], notes)

        with sources.lindas(settings) as lindas:
            entity = companies.lookup(lindas, uid)
        if entity is None:
            raise ToolError(f"no company with UID {query} in the LINDAS dataset")

        term = aramis.search_term(entity.legal_name)
        notes.append(
            f"searching ARAMIS for {term!r}, then confirming each candidate on "
            f"its own participant UID at {settings.interval}s per request."
        )
        confirmed = aramis.confirmed_projects(
            client, uid, term, language=language, limit=limit
        )

    if not confirmed:
        notes.append(
            f"no ARAMIS project confirms {entity.legal_name} under "
            f"{aramis.dotted(uid)}. The service searches project titles, "
            "abstracts and the free-text contractor field, and a company "
            "named only in the structured participant list cannot be found "
            "through it."
        )
    return _result(
        [aramis.confirmed_row(detail, person) for detail, person in confirmed], notes
    )


def main() -> None:
    """Serve the tools over stdio, which is the transport a local host speaks."""
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
