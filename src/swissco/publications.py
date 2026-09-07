"""Listing SHAB publications, and filtering them where the API will not.

The Amtsblattportal bulk export takes a date range and a rubric and honours
both. It also *accepts* ``cantons``, ``subRubrics``, ``q`` and ``keywords`` —
and, anonymously, ignores them: the same request returns the identical total
with and without each one (verified 2026-09-04 against a day holding 1,027
publications). A silently ignored filter is worse than a rejected one, because
a caller that trusted it would report a canton's publications and quietly be
showing the whole country's.

So the filtering happens here, over the same bytes. The list page's ``<meta>``
block already carries ``cantons``, ``subRubric``, ``publicationDate`` and a
title in four languages; ``shab_parser.PublicationRef`` keeps only the fields
it needs and drops those, so this module re-reads the XML it was parsed from.
That is a few lines of ElementTree over a response already in memory — not a
second request, and not a fork of the library's parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from urllib.parse import urlencode
from xml.etree import ElementTree as ET

from shab_parser import PublicationRef, PublicationState
from shab_parser.client import ShabClient

_TITLE_LANGUAGES = ("de", "fr", "it", "en")


@dataclass(frozen=True)
class ListEntry:
    """One publication as the list page describes it, before its body is fetched.

    Everything here is free — it arrived with the list page. ``sub_rubric`` and
    ``canton`` are what the client-side filters run on, and ``titles`` is what
    the :mod:`swissco.events` name prefilter matches against.
    """

    ref: PublicationRef
    sub_rubric: str = ""
    canton: str = ""
    titles: dict[str, str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.titles is None:
            object.__setattr__(self, "titles", {})

    @property
    def title(self) -> str:
        """The title in the publication's own language, else any language."""
        own = self.titles.get(self.ref.language)
        if own:
            return own
        for language in _TITLE_LANGUAGES:
            if self.titles.get(language):
                return self.titles[language]
        return ""


#: The API refuses any request whose ``page * size`` reaches this. A range
#: holding more publications than this cannot be paged through in one pass,
#: however small the pages are, so :func:`discover` splits the range instead.
OFFSET_WINDOW = 10_000

#: Commercial-register publications the gazette issues on an average day, used
#: only to tell a caller how long a wide range will take before it starts.
PUBLICATIONS_PER_DAY = 1000


def estimate(start: date, end: date) -> str:
    """How long listing this range will take, before any body is fetched.

    The gazette publishes roughly a thousand commercial-register entries a day.
    Each list page holds :data:`swissco.events.PAGE_SIZE`, and a range past
    about ten days is split into several windows, so both numbers grow with the
    range. Short ranges get a sentence with no arithmetic in it, because the
    answer is "immediately".
    """
    # Imported here rather than at the top: :mod:`swissco.events` reads
    # :class:`ListEntry` from this module, so a module-level import would
    # close the loop.
    from . import events

    days = (end - start).days + 1
    listed = days * PUBLICATIONS_PER_DAY
    windows = max(1, -(-listed // OFFSET_WINDOW))
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


def discover(
    client: ShabClient,
    start: date,
    end: date,
    *,
    on_window=None,
) -> list[ListEntry]:
    """Every commercial-register publication listed between *start* and *end*.

    Both publication states are paged and the results deduplicated, which is
    what :meth:`shab_parser.client.ShabClient.discover` does; this walks the
    same pages to keep the ``<meta>`` fields that method's return type drops.

    A range holding more than :data:`OFFSET_WINDOW` publications is split in
    half and each half fetched separately. The gazette publishes roughly a
    thousand commercial-register entries a day, so anything past about ten days
    needs this: the API rejects the request that would reach past the window
    rather than truncating it. Splitting by date is the only way through,
    because the window is on the offset and not on the page size.

    *on_window* is called with ``(start, end, total)`` for each window actually
    fetched, which is how the CLI reports progress on a long range.

    Requests go through :meth:`~shab_parser.client.ShabClient.fetch`, so the
    library's rate limit, retry budget and User-Agent apply to them exactly as
    they do to a body fetch.
    """
    entries: list[ListEntry] = []
    for state in (PublicationState.PUBLISHED.value, PublicationState.CANCELLED.value):
        entries.extend(_window(client, start, end, state, on_window))
    return dedupe(entries)


def _window(
    client: ShabClient,
    start: date,
    end: date,
    state: str,
    on_window,
) -> list[ListEntry]:
    """One state's publications for one date range, splitting when too large."""
    first = _page(client, start, end, state, 0)
    found, total = parse_list_page(first)

    if total > OFFSET_WINDOW and start < end:
        middle = start + (end - start) / 2
        return [
            *_window(client, start, middle, state, on_window),
            *_window(client, middle + timedelta(days=1), end, state, on_window),
        ]

    if on_window is not None:
        on_window(start, end, total)

    entries = list(found)
    page = 1
    while found and page * client.page_size < min(total, OFFSET_WINDOW):
        found, _ = parse_list_page(_page(client, start, end, state, page))
        entries.extend(found)
        page += 1
    return entries


def _page(client: ShabClient, start: date, end: date, state: str, page: int) -> bytes:
    url = list_url(client.base_url, start, end, state, page, client.page_size)
    return client.fetch(_as_ref(url, start)).content


def list_url(
    base_url: str,
    start: date,
    end: date,
    state: str,
    page: int,
    page_size: int,
) -> str:
    """The bulk-export URL for one page of one publication state.

    ``tenant``, ``rubrics``, ``publicationStates``, the date bounds and the
    page request are the parameters the API honours. ``cantons``,
    ``subRubrics``, ``q`` and ``keywords`` are deliberately absent: they are
    accepted and ignored, and :func:`filter_entries` does that work instead.
    """
    params = urlencode(
        {
            "tenant": "shab",
            "rubrics": "HR",
            "publicationStates": state,
            "publicationDate.start": start.isoformat(),
            "publicationDate.end": end.isoformat(),
            "pageRequest.page": page,
            "pageRequest.size": page_size,
        }
    )
    return f"{base_url.rstrip('/')}/publications/xml?{params}"


def _as_ref(url: str, day: date) -> PublicationRef:
    return PublicationRef(
        external_id="bulk-export",
        publication_date=day,
        language="",
        url=url,
    )


def parse_list_page(xml_bytes: bytes) -> tuple[list[ListEntry], int]:
    """Parse one bulk-export page into entries and the reported total.

    Namespace-agnostic, like the library's own paths: the bulk export uses its
    own namespace and the ``{*}`` wildcard matches any of them.
    """
    root = ET.fromstring(xml_bytes)
    total = int(_text(root, "{*}total") or "0")

    entries: list[ListEntry] = []
    for publication in root.findall("{*}publication"):
        url = publication.get("ref")
        meta = publication.find("{*}meta")
        if meta is None or not url:
            continue
        external_id = _text(meta, "{*}id")
        published = _text(meta, "{*}publicationDate")
        if not (external_id and published):
            continue

        titles = {}
        title_el = meta.find("{*}title")
        if title_el is not None:
            for language in _TITLE_LANGUAGES:
                value = _text(title_el, f"{{*}}{language}")
                if value:
                    titles[language] = value

        entries.append(
            ListEntry(
                ref=PublicationRef(
                    external_id=external_id,
                    publication_date=date.fromisoformat(published),
                    language=(_text(meta, "{*}language") or "").lower(),
                    url=url,
                    publication_state=(
                        _text(meta, "{*}publicationState") or PublicationState.PUBLISHED
                    ).upper(),
                ),
                sub_rubric=_text(meta, "{*}subRubric") or "",
                canton=(_text(meta, "{*}cantons") or "").upper(),
                titles=titles,
            )
        )
    return entries, total


def filter_entries(
    entries: list[ListEntry],
    *,
    cantons: list[str] | None = None,
    sub_rubrics: list[str] | None = None,
    since: date | None = None,
    until: date | None = None,
    query: str = "",
) -> list[ListEntry]:
    """The entries matching every filter given. Omitted filters match everything.

    ``query`` is matched case-insensitively against the title in *any* of the
    four languages the register publishes it in, so searching for a French word
    still finds a German-language publication whose French title carries it.
    """
    wanted_cantons = {c.strip().upper() for c in (cantons or []) if c.strip()}
    wanted_rubrics = {r.strip().upper() for r in (sub_rubrics or []) if r.strip()}
    needle = query.strip().casefold()

    kept = []
    for entry in entries:
        if wanted_cantons and entry.canton not in wanted_cantons:
            continue
        if wanted_rubrics and entry.sub_rubric.upper() not in wanted_rubrics:
            continue
        if since and entry.ref.publication_date < since:
            continue
        if until and entry.ref.publication_date > until:
            continue
        if needle and not any(
            needle in title.casefold() for title in entry.titles.values()
        ):
            continue
        kept.append(entry)
    return kept


def dedupe(entries: list[ListEntry]) -> list[ListEntry]:
    """Collapse by publication id, preferring CANCELLED over PUBLISHED.

    The two states are listed by separate requests, and a withdrawn
    publication appears in both. The withdrawal supersedes it, which is the
    same rule ``shab_parser`` applies to its own refs.
    """
    seen: dict[str, ListEntry] = {}
    for entry in entries:
        existing = seen.get(entry.ref.external_id)
        if existing is None or (
            entry.ref.publication_state == PublicationState.CANCELLED
            and existing.ref.publication_state != PublicationState.CANCELLED
        ):
            seen[entry.ref.external_id] = entry
    ordered = list(seen.values())
    ordered.sort(key=lambda e: (e.ref.publication_date, e.ref.external_id))
    return ordered


def entry_row(entry: ListEntry) -> dict:
    """One list entry as a flat, render-ready dict."""
    return {
        "publication_date": entry.ref.publication_date.isoformat(),
        "canton": entry.canton,
        "sub_rubric": entry.sub_rubric,
        "title": entry.title,
        "language": entry.ref.language,
        "state": entry.ref.publication_state,
        "id": entry.ref.external_id,
        "url": entry.ref.url,
    }


def publication_row(entry: ListEntry, publication, event_types: list[str]) -> dict:
    """One fetched-and-parsed publication as a flat, render-ready dict."""
    return {
        "publication_date": publication.publication_date.isoformat(),
        "canton": publication.canton or entry.canton,
        "sub_rubric": publication.sub_rubric,
        "company_name": publication.company_name,
        "uid": publication.uid or "",
        "events": event_types,
        "effective_date": (
            publication.effective_date.isoformat() if publication.effective_date else ""
        ),
        "state": publication.publication_state,
        "id": publication.external_id,
        "url": entry.ref.url,
    }


def _text(elem: ET.Element | None, path: str) -> str | None:
    if elem is None:
        return None
    found = elem.find(path)
    if found is None or found.text is None:
        return None
    return found.text.strip() or None
