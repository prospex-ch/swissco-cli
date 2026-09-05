"""simap.ch: Swiss public procurement, browsed and looked up.

Two things this module does, and one it deliberately does not.

**It browses publications by canton and date.** ``/api/publications/v2/project/
project-search`` takes both as first-class filters and pages with an opaque
cursor -- ``lastItem``, echoed back from the response -- rather than an offset.
That is a happier arrangement than the gazette's: there is no offset ceiling to
run into, so a wide range costs pages rather than failing.

**It looks a company up in the vendor directory.** A vendor row carries
``uidNo``, so a UID resolved to a legal name, searched for, and then matched on
``uid_no`` is an *exact* confirmation -- stronger than the title matching
``swissco events`` has to fall back on.

**It does not report what a company has won.** The vendor named on an award --
``VendorRef`` in the platform's own schema -- carries no UID. Matching an award
to a company would therefore mean comparing a procurement office's free-text
supplier name against the register's legal name, with nothing to confirm it
against afterwards. The fixture that prompted this module says
``"Egli Gartenbau AG Sursee"`` where the register says ``"Egli Gartenbau AG"``;
a matcher loose enough for that is loose enough for the wrong Egli. So an
award history keyed on a UID is not offered here at all, rather than offered
with a caveat nobody reads.

Every translated field is kept whole as a ``{de,en,fr,it}`` mapping and
collapsed to one language only at the moment a row is built. simap publishes
each project in the procurement office's own language and translates only
sometimes, so choosing at parse time would throw away the only text a large
part of the corpus has.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterator
from urllib.parse import urlencode

from ._http import HttpClient

BASE = "https://www.simap.ch"
API = f"{BASE}/api"

#: The floor the Prospex collectors use against this host. The CLI's own floor
#: is higher (0.5s), and the higher of the two always wins.
MIN_INTERVAL = 0.35

#: The four platform languages, in the order simap returns them.
LANGUAGES = ("de", "en", "fr", "it")

#: Preference order when one language has to be chosen. German is present most
#: often; English is last because it is usually a courtesy translation.
LANGUAGE_ORDER = ("de", "fr", "it", "en")

#: The ``PubType`` enum as of spec v1.5.1, listed rather than inferred so a new
#: type shows up as one we have never seen instead of being waved through.
KNOWN_PUB_TYPES = (
    "abandonment",
    "advance_notice",
    "award",
    "competition",
    "direct_award",
    "participant_selection",
    "request_for_information",
    "revocation",
    "selective_offering_phase",
    "study_contract",
    "tender",
)

Translation = dict[str, str]


class SimapError(Exception):
    """A simap response that could not be read."""


class ContractError(SimapError):
    """Valid JSON, but not the shape the documented contract promises."""


# -- contracts ---------------------------------------------------------------


@dataclass(frozen=True)
class Address:
    country_id: str = ""
    canton_id: str = ""
    postal_code: str = ""
    city: str = ""
    street: str = ""


@dataclass(frozen=True)
class PublicationRef:
    """One publication in a project's (or one lot's) chain."""

    publication_id: str
    publication_number: str = ""
    pub_type: str = ""
    publication_date: date | None = None
    corrected: bool = False
    lot_id: str = ""
    lot_number: int | None = None
    project_type: str = ""
    project_sub_type: str = ""
    process_type: str = ""


@dataclass(frozen=True)
class ProjectRow:
    """A project-search result row.

    ``heads`` is the newest publication per lot: one entry for a project
    without lots, one per lot otherwise.
    """

    project_id: str
    project_number: str = ""
    title: Translation = field(default_factory=dict)
    project_type: str = ""
    project_sub_type: str = ""
    process_type: str = ""
    lots_type: str = ""
    proc_office_name: Translation = field(default_factory=dict)
    order_address: Address | None = None
    heads: tuple[PublicationRef, ...] = ()

    @property
    def newest_publication_date(self) -> date | None:
        dates = [head.publication_date for head in self.heads if head.publication_date]
        return max(dates) if dates else None


@dataclass(frozen=True)
class ProjectSearchPage:
    projects: tuple[ProjectRow, ...]
    last_item: str = ""
    items_per_page: int = 0


@dataclass(frozen=True)
class VendorRow:
    """A vendor-directory search result row."""

    vendor_id: str
    name: str
    uid_no: str = ""
    duns_no: str = ""
    is_bidding_consortium: bool = False
    active: bool = True
    address: Address = field(default_factory=Address)


@dataclass(frozen=True)
class VendorSearchPage:
    vendors: tuple[VendorRow, ...]
    last_item: str = ""
    items_per_page: int = 0


@dataclass(frozen=True)
class VendorProfile:
    """One vendor's public directory profile."""

    vendor_id: str
    name: str = ""
    uid_no: str = ""
    duns_no: str = ""
    additional_name: str = ""
    url: str = ""
    address: Address = field(default_factory=Address)
    company_size: str = ""
    type_of_services: tuple[str, ...] = ()
    cpv_codes: tuple[str, ...] = ()
    bkp_codes: tuple[str, ...] = ()
    npk_codes: tuple[str, ...] = ()
    business_purpose: str = ""
    is_bidding_consortium: bool = False
    leading_vendor_name: str = ""


# -- the client --------------------------------------------------------------


class SimapClient(HttpClient):
    """The documented read API, and nothing else on the host.

    ``disallowed_prefixes`` is the site's own ``robots.txt`` as it applies to
    the single-page app. Every call here goes to ``/api``, which ``robots.txt``
    does not mention; the guard exists so a future caller cannot reach the SPA
    routes by accident.
    """

    allowed_hosts = frozenset({"www.simap.ch"})
    disallowed_prefixes = ("/de/project-detail", "/fr/project-detail")

    def fetch_project_search_page(
        self,
        *,
        publication_from: date | None = None,
        publication_until: date | None = None,
        pub_types: tuple[str, ...] = (),
        cantons: tuple[str, ...] = (),
        last_item: str = "",
    ) -> bytes:
        params: list[tuple[str, str]] = []
        if publication_from:
            params.append(("newestPublicationFrom", publication_from.isoformat()))
        if publication_until:
            params.append(("newestPublicationUntil", publication_until.isoformat()))
        params += [("newestPubTypes", value) for value in pub_types]
        params += [("orderAddressCantons", value) for value in cantons]
        if last_item:
            params.append(("lastItem", last_item))
        url = f"{API}/publications/v2/project/project-search"
        if params:
            url = f"{url}?{urlencode(params)}"
        return self.get(url).content

    def fetch_vendor_search_page(self, *, search: str = "", last_item: str = "") -> bytes:
        params: list[tuple[str, str]] = []
        if search:
            params.append(("search", search))
        if last_item:
            params.append(("lastItem", last_item))
        url = f"{API}/vendors/v1"
        if params:
            url = f"{url}?{urlencode(params)}"
        return self.get(url).content

    def fetch_vendor_public(self, vendor_id: str) -> bytes:
        return self.get(f"{API}/vendors/v1/vendor/{vendor_id}/public").content


# -- parsing -----------------------------------------------------------------


def parse_project_search_page(content: bytes) -> ProjectSearchPage:
    data = _load(content)
    rows = data.get("projects")
    if not isinstance(rows, list):
        raise ContractError("the project-search response has no projects array")

    projects = []
    for row in rows:
        if not isinstance(row, dict):
            raise ContractError("a project-search row is not an object")
        project_id = _text(row.get("id"))
        if not project_id:
            raise ContractError("a project-search row has no id")
        shared = {
            "projectType": row.get("projectType"),
            "projectSubType": row.get("projectSubType"),
            "processType": row.get("processType"),
        }
        lots = row.get("lots")
        if isinstance(lots, list) and lots:
            heads = tuple(
                _publication_ref(lot, defaults=shared) for lot in lots if isinstance(lot, dict)
            )
        else:
            heads = (_publication_ref(row, defaults=shared),)
        projects.append(
            ProjectRow(
                project_id=project_id,
                project_number=_text(row.get("projectNumber")),
                title=_translation(row.get("title")),
                project_type=_text(row.get("projectType")),
                project_sub_type=_text(row.get("projectSubType")),
                process_type=_text(row.get("processType")),
                lots_type=_text(row.get("lotsType")),
                proc_office_name=_translation(row.get("procOfficeName")),
                order_address=(
                    _address(row.get("orderAddress"))
                    if isinstance(row.get("orderAddress"), dict)
                    else _first_lot_address(lots)
                ),
                heads=heads,
            )
        )

    pagination = data.get("pagination") or {}
    return ProjectSearchPage(
        projects=tuple(projects),
        last_item=_text(pagination.get("lastItem")),
        items_per_page=_int(pagination.get("itemsPerPage")) or 0,
    )


def parse_vendor_search_page(content: bytes) -> VendorSearchPage:
    data = _load(content)
    rows = data.get("vendors")
    if not isinstance(rows, list):
        raise ContractError("the vendor search response has no vendors array")
    vendors = []
    for row in rows:
        if not isinstance(row, dict):
            raise ContractError("a vendor search row is not an object")
        vendor_id = _text(row.get("id"))
        if not vendor_id:
            raise ContractError("a vendor search row has no id")
        vendors.append(
            VendorRow(
                vendor_id=vendor_id,
                name=_text(row.get("name")),
                uid_no=_text(row.get("uidNo")),
                duns_no=_text(row.get("dunsNo")),
                is_bidding_consortium=_bool(row.get("isBiddingConsortium")),
                active=row.get("active") is not False,
                address=_address(row.get("address")),
            )
        )
    pagination = data.get("pagination") or {}
    return VendorSearchPage(
        vendors=tuple(vendors),
        last_item=_text(pagination.get("lastItem")),
        items_per_page=_int(pagination.get("itemsPerPage")) or 0,
    )


def parse_vendor_public(content: bytes) -> VendorProfile:
    payload = _load(content)
    vendor_id = _text(payload.get("id"))
    if not vendor_id:
        raise ContractError("a vendor profile has no id")
    services = payload.get("typeOfServices")
    return VendorProfile(
        vendor_id=vendor_id,
        name=_text(payload.get("name")),
        uid_no=_text(payload.get("uidNo")),
        duns_no=_text(payload.get("dunsNo")),
        additional_name=_text(payload.get("additionalName")),
        url=_text(payload.get("url")),
        address=_address(payload.get("address")),
        company_size=_text(payload.get("companySize")),
        type_of_services=(
            tuple(_text(item) for item in services if _text(item))
            if isinstance(services, list)
            else ()
        ),
        cpv_codes=_codes(payload.get("cpvCodes")),
        bkp_codes=_codes(payload.get("bkpCodes")),
        npk_codes=_codes(payload.get("npkCodes")),
        business_purpose=_text(payload.get("businessPurpose")),
        is_bidding_consortium=_bool(payload.get("isBiddingConsortium")),
        leading_vendor_name=_text(payload.get("leadingVendor")),
    )


# -- walking the cursor ------------------------------------------------------


def iter_projects(
    client: SimapClient,
    *,
    since: date | None = None,
    until: date | None = None,
    pub_types: tuple[str, ...] = (),
    cantons: tuple[str, ...] = (),
    limit: int = 20,
    on_page=None,
) -> Iterator[ProjectRow]:
    """Walk project search until *limit* rows or the cursor stops moving.

    The cursor is opaque and comes back from the service, so the one failure
    mode worth guarding is a service that keeps handing back the same one. A
    repeated cursor ends the walk rather than looping forever.
    """
    seen: set[str] = set()
    cursor = ""
    yielded = 0
    while True:
        page = parse_project_search_page(
            client.fetch_project_search_page(
                publication_from=since,
                publication_until=until,
                pub_types=pub_types,
                cantons=cantons,
                last_item=cursor,
            )
        )
        if on_page is not None:
            on_page(len(page.projects), yielded)
        for project in page.projects:
            yield project
            yielded += 1
            if yielded >= limit:
                return
        if not page.last_item or page.last_item in seen or not page.projects:
            return
        seen.add(page.last_item)
        cursor = page.last_item


def iter_vendors(
    client: SimapClient, *, search: str, limit: int = 20, on_page=None
) -> Iterator[VendorRow]:
    """Walk the vendor directory for *search* until *limit* rows.

    ``lastItem`` here is a **name**, not a date-and-id pair, so paging past the
    first page walks the directory alphabetically from that name.
    """
    seen: set[str] = set()
    cursor = ""
    yielded = 0
    while True:
        page = parse_vendor_search_page(
            client.fetch_vendor_search_page(search=search, last_item=cursor)
        )
        if on_page is not None:
            on_page(len(page.vendors), yielded)
        for vendor in page.vendors:
            yield vendor
            yielded += 1
            if yielded >= limit:
                return
        if not page.last_item or page.last_item in seen or not page.vendors:
            return
        seen.add(page.last_item)
        cursor = page.last_item


def confirmed_by_uid(vendors, uid: str) -> list[VendorRow]:
    """Only the rows whose own ``uid_no`` equals *uid*.

    The name found the candidates; this is what decides. A row whose name
    matched but whose UID does not is dropped, which is the whole point.
    """
    return [vendor for vendor in vendors if _uid(vendor.uid_no) == _uid(uid)]


# -- rows --------------------------------------------------------------------


def tender_row(project: ProjectRow, *, lang: str = "") -> dict:
    """One project as a row. Key order is column order."""
    head = _newest(project.heads)
    address = project.order_address or Address()
    return {
        "title": preferred(project.title, lang),
        "project_number": project.project_number,
        "buyer": preferred(project.proc_office_name, lang),
        "canton": address.canton_id,
        "city": address.city,
        "project_type": project.project_type,
        "process_type": project.process_type,
        "publication_date": head.publication_date if head else None,
        "publication_type": head.pub_type if head else "",
        "project_id": project.project_id,
        "publication_id": head.publication_id if head else "",
    }


def vendor_row(vendor: VendorRow) -> dict:
    return {
        "name": vendor.name,
        "uid_no": vendor.uid_no,
        "canton": vendor.address.canton_id,
        "city": vendor.address.city,
        "postal_code": vendor.address.postal_code,
        "active": vendor.active,
        "is_bidding_consortium": vendor.is_bidding_consortium,
        "vendor_id": vendor.vendor_id,
    }


def vendor_profile_row(profile: VendorProfile) -> dict:
    return {
        "name": profile.name,
        "uid_no": profile.uid_no,
        "additional_name": profile.additional_name,
        "street": profile.address.street,
        "postal_code": profile.address.postal_code,
        "city": profile.address.city,
        "canton": profile.address.canton_id,
        "url": profile.url,
        "company_size": profile.company_size,
        "type_of_services": list(profile.type_of_services),
        "cpv_codes": list(profile.cpv_codes),
        "bkp_codes": list(profile.bkp_codes),
        "npk_codes": list(profile.npk_codes),
        "business_purpose": profile.business_purpose,
        "is_bidding_consortium": profile.is_bidding_consortium,
        "leading_vendor_name": profile.leading_vendor_name,
        "vendor_id": profile.vendor_id,
    }


def preferred(translation: Translation, lang: str = "") -> str:
    """One language out of a translation.

    *lang* wins when the field has it. Otherwise de, fr, it, en in that order,
    so a row always carries the text that exists rather than an empty cell in
    the language that was asked for.
    """
    if lang and translation.get(lang):
        return translation[lang]
    for candidate in LANGUAGE_ORDER:
        if translation.get(candidate):
            return translation[candidate]
    return ""


# -- helpers -----------------------------------------------------------------


def _load(content: bytes) -> dict:
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SimapError(f"invalid JSON from simap: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError(f"expected a JSON object, got {type(data).__name__}")
    return data


def _translation(value) -> Translation:
    if not isinstance(value, dict):
        return {}
    return {
        lang: value[lang].strip()
        for lang in LANGUAGES
        if isinstance(value.get(lang), str) and value[lang].strip()
    }


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _bool(value) -> bool:
    return value is True


def _date(value) -> date | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise ContractError(f"unparseable date {text!r}") from exc


def _address(value) -> Address:
    if not isinstance(value, dict):
        return Address()
    city = value.get("city")
    street = value.get("street")
    return Address(
        country_id=_text(value.get("countryId")).upper(),
        canton_id=_text(value.get("cantonId")).upper(),
        postal_code=_text(value.get("postalCode")),
        # The vendor endpoints publish these as plain strings and the
        # publication ones as translations, so both shapes are accepted.
        city=_text(city) or preferred(_translation(city)),
        street=_text(street) or preferred(_translation(street)),
    )


def _codes(value) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        _text(entry.get("code"))
        for entry in value
        if isinstance(entry, dict) and _text(entry.get("code"))
    )


def _publication_ref(payload: dict, *, defaults: dict | None = None) -> PublicationRef:
    base = {**(defaults or {}), **payload}
    publication_id = _text(base.get("publicationId")) or _text(base.get("id"))
    if not publication_id:
        raise ContractError("a publication entry has no id")
    return PublicationRef(
        publication_id=publication_id,
        publication_number=_text(base.get("publicationNumber")),
        pub_type=_text(base.get("pubType")),
        publication_date=_date(base.get("publicationDate")),
        corrected=_bool(base.get("corrected")),
        lot_id=_text(base.get("lotId")),
        lot_number=_int(base.get("lotNumber")),
        project_type=_text(base.get("projectType")),
        project_sub_type=_text(base.get("projectSubType")),
        process_type=_text(base.get("processType")),
    )


def _first_lot_address(lots) -> Address | None:
    """A lots project has no project-level order address, only per-lot ones."""
    if not isinstance(lots, list):
        return None
    for lot in lots:
        if isinstance(lot, dict) and isinstance(lot.get("orderAddress"), dict):
            return _address(lot["orderAddress"])
    return None


def _newest(heads: tuple[PublicationRef, ...]) -> PublicationRef | None:
    dated = [head for head in heads if head.publication_date]
    if dated:
        return max(dated, key=lambda head: head.publication_date)
    return heads[0] if heads else None


def _uid(value: str) -> str:
    return "".join(character for character in (value or "").upper() if character.isalnum())
