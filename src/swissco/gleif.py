"""GLEIF: the Legal Entity Identifier, and the group a company sits in.

Two things the register does not publish, and one thing this module is careful
not to claim.

**The LEI.** ``api.gleif.org/api/v1/lei-records`` is free, global and
unauthenticated. ``filter[entity.registeredAs]`` matches the register number an
entity gave its LEI issuer, which for a Swiss entity is the UID, so a UID
resolves to an LEI in one request. GLEIF stores that number in whichever
spelling the entity supplied: Aargauische Kantonalbank is filed as
``CHE105845287`` and UBS Switzerland AG as ``CHE-412.669.376``. Both spellings
are tried, squashed first.

**The group.** Level 2 relationship records answer who a company reports up to,
including a parent with no Swiss register entry at all. ``/direct-parent`` and
``/ultimate-parent`` return the parent's own LEI record; ``/direct-children``
and ``/ultimate-children`` return a paginated page with the total in
``meta.pagination``. An entity that reports no parent answers 404, which is a
normal outcome here rather than a failure, so :meth:`GleifClient.check_response`
lets it through as an absence.

**Level 2 records accounting consolidation.** A parent in GLEIF is the entity
that consolidates this one into its financial statements. That is close to
ownership and not the same thing: a parent that consolidates a subsidiary need
not own it outright, and a majority owner that does not consolidate is absent
from the file. Read a parent as "consolidated by", and the copy in this package
says exactly that.

Coverage is the other thing to keep in view. About 28,000 Swiss entities hold
an LEI against roughly 790,000 in the commercial register, and about 81% of
those LEIs carry a register number. A miss means "no LEI on file", never "no
such company".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from urllib.parse import quote

from ._http import HttpClient, HttpError

BASE = "https://api.gleif.org/api/v1"

#: GLEIF publishes no rate limit for the record API. The CLI's own floor is
#: what paces it, and ``--interval`` may raise it further.
MIN_INTERVAL = 0.5

#: The four Level 2 relationships this module reads. Each is a path segment
#: under a record, and each may legitimately answer 404.
RELATIONS = ("direct-parent", "ultimate-parent", "direct-children", "ultimate-children")

#: The largest page GLEIF serves. Children are listed one page at a time, and
#: the whole set's size comes back in ``meta.pagination`` either way.
MAX_PAGE_SIZE = 200


class GleifError(Exception):
    """A GLEIF response that could not be read."""


class ContractError(GleifError):
    """Valid JSON, but not the shape the documented contract promises."""


class RelationAbsent(HttpError):
    """The entity reports no such relationship. Caught inside this module."""


# -- contracts ---------------------------------------------------------------


@dataclass(frozen=True)
class RelatedEntity:
    """One end of a Level 2 relationship, as GLEIF's own record describes it."""

    lei: str
    legal_name: str = ""
    jurisdiction: str = ""
    registered_as: str = ""
    status: str = ""
    city: str = ""
    country: str = ""

    def label(self) -> str:
        """``Name (LEI, jurisdiction)``, the form the ``lei`` command prints."""
        parts = [part for part in (self.lei, self.jurisdiction) if part]
        return f"{self.legal_name} ({', '.join(parts)})" if parts else self.legal_name


@dataclass(frozen=True)
class LeiRecord:
    """One LEI record, trimmed to the fields a company profile can use."""

    lei: str
    legal_name: str = ""
    registered_as: str = ""
    jurisdiction: str = ""
    status: str = ""
    registration_status: str = ""
    legal_form: str = ""
    city: str = ""
    country: str = ""
    postal_code: str = ""
    other_names: tuple[str, ...] = ()
    bic: tuple[str, ...] = ()
    initial_registration_date: date | None = None
    last_update_date: date | None = None
    next_renewal_date: date | None = None


@dataclass(frozen=True)
class RelatedPage:
    """One page of children, with the total GLEIF declares for the whole set."""

    entities: tuple[RelatedEntity, ...]
    total: int = 0


@dataclass(frozen=True)
class Group:
    """What one company's Level 2 file says.

    ``direct_children`` is ``None`` when the children were not asked for, and a
    page with a total when they were. The distinction is what keeps
    ``swissco lookup --lei`` down to two relationship requests.
    """

    direct_parent: RelatedEntity | None = None
    ultimate_parent: RelatedEntity | None = None
    direct_children: RelatedPage | None = None


# -- the client --------------------------------------------------------------


class GleifClient(HttpClient):
    """The public record API, and nothing else on the host."""

    allowed_hosts = frozenset({"api.gleif.org"})

    def check_response(self, response, url: str) -> None:
        """The shared status policy, with one addition GLEIF's shape requires.

        A 404 on a relationship path means the entity reports no parent, which
        is an answer rather than an error. It is raised as
        :class:`RelationAbsent` so :meth:`fetch_relation` can turn it into
        ``None`` while every other 404 stays the permanent failure it is.
        """
        if response.status_code == 404 and _is_relation(url):
            raise RelationAbsent(f"{url} reports no such relationship")
        super().check_response(response, url)

    def fetch_records_by_registered_as(self, value: str) -> bytes:
        """Every record whose ``entity.registeredAs`` equals *value*, exactly."""
        query = quote(value, safe="")
        return self.get(f"{BASE}/lei-records?filter%5Bentity.registeredAs%5D={query}").content

    def fetch_record(self, lei: str) -> bytes:
        return self.get(f"{BASE}/lei-records/{quote(lei, safe='')}").content

    def fetch_relation(self, lei: str, relation: str, *, page_size: int = 0) -> bytes | None:
        """One relationship, or ``None`` when the entity reports none."""
        if relation not in RELATIONS:
            raise ValueError(f"unknown GLEIF relation {relation!r}; expected one of {RELATIONS}")
        url = f"{BASE}/lei-records/{quote(lei, safe='')}/{relation}"
        if page_size > 0:
            url = f"{url}?page%5Bsize%5D={min(page_size, MAX_PAGE_SIZE)}"
        try:
            return self.get(url).content
        except RelationAbsent:
            return None


# -- parsing -----------------------------------------------------------------


def parse_records(content: bytes) -> tuple[LeiRecord, ...]:
    """A search response, which carries a JSON:API array in ``data``."""
    payload = _load(content)
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ContractError("the lei-records response has no data array")
    return tuple(_record(row) for row in rows)


def parse_record(content: bytes) -> LeiRecord:
    """A single-record response, which carries one object in ``data``."""
    payload = _load(content)
    row = payload.get("data")
    if not isinstance(row, dict):
        raise ContractError("the lei-record response has no data object")
    return _record(row)


def parse_related(content: bytes) -> RelatedEntity:
    """A parent response, read as the related entity rather than a full record."""
    return _related(parse_record(content))


def parse_related_page(content: bytes) -> RelatedPage:
    """A children page, with the whole set's size from ``meta.pagination``."""
    payload = _load(content)
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ContractError("the relationship response has no data array")
    pagination = (payload.get("meta") or {}).get("pagination") or {}
    total = pagination.get("total")
    return RelatedPage(
        entities=tuple(_related(_record(row)) for row in rows),
        total=total if isinstance(total, int) and not isinstance(total, bool) else len(rows),
    )


# -- finding and gathering ---------------------------------------------------


def squash(uid: str) -> str:
    """A UID with its separators removed: ``CHE105845287``."""
    return "".join(character for character in (uid or "").upper() if character.isalnum())


def dotted(uid: str) -> str:
    """A UID in the register's official spelling: ``CHE-105.845.287``.

    Anything that is not twelve characters of ``CHE`` plus nine digits comes
    back unchanged, so a malformed value reaches the service as it was given
    instead of being silently reshaped.
    """
    flat = squash(uid)
    if len(flat) != 12 or not flat.startswith("CHE") or not flat[3:].isdigit():
        return uid
    return f"CHE-{flat[3:6]}.{flat[6:9]}.{flat[9:12]}"


def find_by_uid(client: GleifClient, uid: str) -> LeiRecord | None:
    """The record filed under *uid*, in either spelling GLEIF stores.

    The squashed form is tried first because it is the more common filing, so
    the second request is spent only when the first finds nothing.
    """
    spellings = [squash(uid)]
    if dotted(uid) not in spellings:
        spellings.append(dotted(uid))
    for spelling in spellings:
        records = parse_records(client.fetch_records_by_registered_as(spelling))
        if records:
            return records[0]
    return None


def group(client: GleifClient, lei: str, *, children: bool = False, page_size: int = 0) -> Group:
    """The Level 2 file for *lei*: both parents, and the children when asked.

    Two requests, or three with ``children=True``. A company profile wants the
    parents alone, so the third is spent only by the command that prints a
    child count.
    """
    direct = client.fetch_relation(lei, "direct-parent")
    ultimate = client.fetch_relation(lei, "ultimate-parent")
    found = Group(
        direct_parent=parse_related(direct) if direct else None,
        ultimate_parent=parse_related(ultimate) if ultimate else None,
    )
    if not children:
        return found

    page = client.fetch_relation(lei, "direct-children", page_size=page_size)
    return Group(
        direct_parent=found.direct_parent,
        ultimate_parent=found.ultimate_parent,
        direct_children=parse_related_page(page) if page else RelatedPage((), 0),
    )


# -- rows --------------------------------------------------------------------


def lei_row(record: LeiRecord, found: Group) -> dict:
    """One record and its group as a row. Key order is column order.

    ``direct_parent`` and ``ultimate_parent`` read "consolidated by": GLEIF
    Level 2 records accounting consolidation, so a parent here is the entity
    that consolidates this one rather than necessarily its owner.
    """
    row = {
        "legal_name": record.legal_name,
        "lei": record.lei,
        "registered_as": record.registered_as,
        "jurisdiction": record.jurisdiction,
        "status": record.status,
        "registration_status": record.registration_status,
        "legal_form": record.legal_form,
        "city": record.city,
        "country": record.country,
        "other_names": list(record.other_names),
        "bic": list(record.bic),
        "initial_registration_date": record.initial_registration_date,
        "last_update_date": record.last_update_date,
        "next_renewal_date": record.next_renewal_date,
        "direct_parent": found.direct_parent.label() if found.direct_parent else "none reported",
        "ultimate_parent": (
            found.ultimate_parent.label() if found.ultimate_parent else "none reported"
        ),
    }
    if found.direct_children is not None:
        row["direct_children"] = found.direct_children.total
    return row


def child_row(entity: RelatedEntity) -> dict:
    """One child as a row, for ``swissco lei --children``."""
    return {
        "legal_name": entity.legal_name,
        "lei": entity.lei,
        "jurisdiction": entity.jurisdiction,
        "registered_as": entity.registered_as,
        "status": entity.status,
        "city": entity.city,
        "country": entity.country,
    }


def lookup_fields(record: LeiRecord, found: Group) -> dict:
    """The subset ``swissco lookup --lei`` adds to a company row."""
    return {
        "lei": record.lei,
        "lei_status": record.status,
        "direct_parent": found.direct_parent.label() if found.direct_parent else "none reported",
        "ultimate_parent": (
            found.ultimate_parent.label() if found.ultimate_parent else "none reported"
        ),
    }


# -- helpers -----------------------------------------------------------------


def _is_relation(url: str) -> bool:
    path = url.split("?", 1)[0]
    return any(path.endswith(f"/{relation}") for relation in RELATIONS)


def _load(content: bytes) -> dict:
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise GleifError(f"invalid JSON from GLEIF: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"expected a JSON object, got {type(payload).__name__}")
    return payload


def _record(row) -> LeiRecord:
    if not isinstance(row, dict):
        raise ContractError("a lei-records entry is not an object")
    attributes = row.get("attributes")
    if not isinstance(attributes, dict):
        raise ContractError("a lei-records entry has no attributes")
    lei = _text(attributes.get("lei")) or _text(row.get("id"))
    if not lei:
        raise ContractError("a lei-records entry has no LEI")

    entity = attributes.get("entity") or {}
    registration = attributes.get("registration") or {}
    address = entity.get("legalAddress") or entity.get("headquartersAddress") or {}
    return LeiRecord(
        lei=lei,
        legal_name=_text((entity.get("legalName") or {}).get("name")),
        registered_as=_text(entity.get("registeredAs")),
        jurisdiction=_text(entity.get("jurisdiction")),
        status=_text(entity.get("status")),
        registration_status=_text(registration.get("status")),
        legal_form=_text((entity.get("legalForm") or {}).get("id")),
        city=_text(address.get("city")),
        country=_text(address.get("country")),
        postal_code=_text(address.get("postalCode")),
        other_names=_names(entity.get("otherNames")),
        bic=_strings(attributes.get("bic")),
        initial_registration_date=_date(registration.get("initialRegistrationDate")),
        last_update_date=_date(registration.get("lastUpdateDate")),
        next_renewal_date=_date(registration.get("nextRenewalDate")),
    )


def _related(record: LeiRecord) -> RelatedEntity:
    return RelatedEntity(
        lei=record.lei,
        legal_name=record.legal_name,
        jurisdiction=record.jurisdiction,
        registered_as=record.registered_as,
        status=record.status,
        city=record.city,
        country=record.country,
    )


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _strings(value) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(_text(item) for item in value if _text(item))


def _names(value) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names = (_text(item.get("name")) for item in value if isinstance(item, dict))
    return tuple(name for name in names if name)


def _date(value) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise ContractError(f"unparseable GLEIF date {text!r}") from exc
