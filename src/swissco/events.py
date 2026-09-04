"""The join: a company's registry events, from a UID.

This is the claim worth making and the one that needs the most care, because
the two halves do not share a key. The SHAB list page carries no UID — only a
title — and every search parameter the API accepts is ignored anonymously, so
there is no server-side way to ask "publications about this company".

The join therefore runs in two stages, and the order matters:

1. **A title prefilter**, cheap and deliberately loose. The list page's title
   is "Mutation Baumberger Bau AG, Koppigen", so a normalised form of the legal
   name resolved from LINDAS is looked for inside it. This is a *filter*, not
   an answer: a title match is not proof, and two companies can share a name.
2. **A body confirmation**, authoritative and expensive. Only the survivors are
   fetched and parsed, and an event is kept only when the parsed body's own UID
   equals the one that was asked for.

Getting that order backwards would mean fetching every publication in the range
— a year is around half a million bodies. Trusting stage 1 alone would mean
reporting another company's events under this company's UID. Stage 1 buys the
request budget; stage 2 is what makes the output true.

Fetched bodies are cached under the state directory, keyed by publication id,
so an overlapping re-run costs nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from shab_parser import Publication, parse_xml
from shab_parser.client import ShabClient
from zefix_parser import format_uid, normalize_uid
from zefix_parser.rest import normalize_name

from .publications import ListEntry

#: Roughly how many publications one list request returns at the maximum page
#: size, used only to tell the user how long a wide range will take.
PAGE_SIZE = 2000

_LEGAL_FORM_NOISE = re.compile(
    r"\b(?:ag|sa|sagl|gmbh|sarl|s[àa]rl|srl|snc|senc|se|ltd|limited|inc|corp"
    r"|kg|klg|kgaa|llc|plc)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CompanyEvent:
    """One classified event, with the publication it was read from."""

    uid: str
    company_name: str
    event_type: str
    effective_date: date | None
    publication_date: date
    sub_rubric: str
    canton: str
    external_id: str
    url: str
    payload: dict


def name_keys(legal_name: str) -> tuple[str, str]:
    """``(full_key, core_key)`` — the two forms a title is matched against.

    The full key is the whole legal name normalised. The core key is that with
    the legal-form token dropped, because a register title does not always
    print it the way the register stores it ("Muster AG" against "Muster SA" in
    a bilingual canton, "Sàrl" against "S.à r.l."). The core key is used only
    when it is long enough to still be distinctive.
    """
    full = normalize_name(legal_name)
    core = normalize_name(_LEGAL_FORM_NOISE.sub(" ", legal_name))
    return full, core


def title_matches(titles: dict[str, str], full_key: str, core_key: str) -> bool:
    """Whether any language's title looks like it is about this company.

    Loose on purpose — this decides only which bodies are worth fetching, and
    :func:`confirm` throws out anything the body contradicts. A short core key
    is ignored rather than matched: a two-character name would match most of
    the register.
    """
    for title in titles.values():
        normalized = normalize_name(title)
        if full_key and full_key in normalized:
            return True
        if len(core_key) >= 6 and core_key in normalized:
            return True
    return False


def prefilter(entries: list[ListEntry], legal_name: str) -> list[ListEntry]:
    """The entries whose title could plausibly be about *legal_name*."""
    full_key, core_key = name_keys(legal_name)
    if not full_key:
        return []
    return [e for e in entries if title_matches(e.titles, full_key, core_key)]


def confirm(publication: Publication, uid: str) -> bool:
    """Whether a parsed body really is about *uid*.

    The body's own ``<uid>`` is the authority. A publication that carries no
    UID at all is rejected rather than accepted on the title alone: an
    unattributable event under a specific company's UID is worse than a
    missing one.
    """
    return bool(publication.uid) and normalize_uid(publication.uid) == normalize_uid(uid)


def collect(
    client: ShabClient,
    entries: list[ListEntry],
    uid: str,
    *,
    cache_dir: Path | None = None,
) -> list[CompanyEvent]:
    """Fetch, parse and confirm *entries*, returning the events that survive.

    Newest first, and within one publication in the parser's own taxonomy
    order.
    """
    events: list[CompanyEvent] = []
    for entry in entries:
        content = body(client, entry, cache_dir)
        if content is None:
            continue
        try:
            publication = parse_xml(
                content,
                source_url=entry.ref.url,
                ref_state=entry.ref.publication_state,
            )
        except Exception:
            # A body the parser rejects is one publication lost, not a run.
            # The register occasionally serves a truncated or schema-drifted
            # document, and stopping would throw away every event already
            # confirmed.
            continue
        if not confirm(publication, uid):
            continue
        for event in publication.events:
            events.append(
                CompanyEvent(
                    uid=format_uid(publication.uid or uid),
                    company_name=publication.company_name,
                    event_type=event.event_type.value,
                    effective_date=event.effective_date,
                    publication_date=publication.publication_date,
                    sub_rubric=publication.sub_rubric,
                    canton=publication.canton or entry.canton,
                    external_id=publication.external_id,
                    url=entry.ref.url,
                    payload=event.payload,
                )
            )
    events.sort(key=lambda e: (e.publication_date, e.external_id), reverse=True)
    return events


def event_row(event: CompanyEvent) -> dict:
    """One event as a flat, render-ready dict."""
    return {
        "publication_date": event.publication_date.isoformat(),
        "event_type": event.event_type,
        "effective_date": (
            event.effective_date.isoformat() if event.effective_date else ""
        ),
        "company_name": event.company_name,
        "uid": event.uid,
        "canton": event.canton,
        "sub_rubric": event.sub_rubric,
        "id": event.external_id,
        "url": event.url,
    }


def body(client: ShabClient, entry: ListEntry, cache_dir: Path | None = None) -> bytes | None:
    """The publication's XML, from the cache when it is there.

    A published SHAB document does not change — a correction is issued as a new
    publication with its own id — so a cache keyed by id needs no expiry.
    """
    cached = cache_dir / f"{entry.ref.external_id}.xml" if cache_dir else None
    if cached is not None and cached.exists():
        return cached.read_bytes()

    try:
        raw = client.fetch(entry.ref)
    except Exception:
        return None

    if cached is not None:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(raw.content)
    return raw.content
