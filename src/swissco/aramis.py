"""ARAMIS: the Confederation's register of publicly funded research projects.

Innosuisse grants, SNSF money and every departmental research mandate land
here, and a project's structured participant list carries the participating
organisation's UID. That join is what makes the source worth a command: it
answers which federally funded research a named Swiss company has taken part
in, which no other free tool exposes.

**What the search reaches, and what it does not.** ``ProjectQuery`` offers
three text keys: ``FullTextSearchKeywords`` over the title and abstract,
``ContractorFullTextSearchKeywords`` over the free-text contractor field, and
``BudgetFullTextSearchKeywords``. None of them indexes the structured
participant list, so a company is findable only where its name appears in one
of those texts. An Innosuisse implementation partner is typically named in the
participant block alone, and a search for it returns nothing at all. The
alternatives would be the 43 MB bulk export or a 47,800-request sweep of the
whole corpus, and both are out of reach of a single interactive invocation, so
the coverage limit stands and the copy states it.

**The UID decides, the name only finds.** A ``Company1`` is truncated at 35
characters upstream (``"inspire AG für mechatronische Produ"``), so an
organisation name from this source can never identify a company on its own.
When a UID is given, every candidate project is hydrated and only rows carrying
a participant whose own UID matches are reported.

**Personal data stops at the parser.** The wire payload carries a named
researcher's given name, family name, e-mail, three telephone numbers and a fax
number, plus a ``ShortViewName`` that concatenates the organisation with the
person. :class:`Participant` has a field for none of them, so no output format
can emit one. What survives is organisational: the organisation, the role, the
UID and the place.

Two upstream misspellings are read under their wire spelling, with the correct
spelling accepted as a fallback so a fix upstream does not blank a field:
``Titel`` on a project-list row, and ``Categroies`` inside a category group.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Callable

from ._http import HttpClient

SERVICE = "https://www.webservice.aramis.admin.ch/public/service.svc"

#: The service serialises at roughly 2.4 requests a second and publishes no
#: SLA. The CLI's own floor paces it, and ``--interval`` may raise it further.
MIN_INTERVAL = 0.5

#: ``Count`` above this answers HTTP 500 with an ``A2AFault`` body, so it is
#: refused here before the request rather than discovered from the response.
MAX_PAGE_SIZE = 100

#: The four service languages. The match is case-sensitive: ``EN`` answers and
#: ``en`` is an HTTP 400.
LANGUAGES = ("DE", "EN", "FR", "IT")

DEFAULT_LANGUAGE = "EN"

#: ``/Date(<signed ms>[<+|->HHMM])/``. The offset is optional and is what the
#: calendar day has to be read in.
WCF_DATE = re.compile(r"^/Date\((-?\d+)(?:([+-])(\d{2})(\d{2}))?\)/$")

#: The UID inside a participant URL,
#: ``www.uid.admin.ch/Detail.aspx?uid_id=CHE106209800``.
UID_IN_URL = re.compile(r"uid_id=\s*(CHE[\s.\-]?(?:\d[\s.\-]?){9})", re.IGNORECASE)

#: Legal-form suffixes stripped before a name becomes a search term. ``Company1``
#: is truncated at 35 characters upstream, so the suffix is often absent from
#: the stored value and searching for it would cost the match.
LEGAL_FORM_SUFFIXES = (
    "AG",
    "SA",
    "GmbH",
    "Sàrl",
    "Sarl",
    "SAGL",
    "Ltd",
    "LLC",
    "Holding AG",
    "in Liquidation",
    "en liquidation",
)

#: How much of a legal name is kept as a search term.
MAX_TERM_CHARS = 35

#: ``FirstOrderSort``, as the integer index of the CLR enum. The member name is
#: an HTTP 400. Newest first is what both search paths ask for: a structured
#: participant appears from about 2015 and its UID from about 2022, so the
#: oldest projects are the ones a UID can never confirm.
SORT_START_DATE_DESCENDING = 1

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


class AramisError(Exception):
    """An ARAMIS response that could not be read."""


class ContractError(AramisError):
    """Valid JSON, but not the shape the documented contract promises."""


class ServiceFault(AramisError):
    """The service answered with an ``A2AFault`` instead of a project."""


# -- contracts ---------------------------------------------------------------


@dataclass(frozen=True)
class Participant:
    """One organisation on a project.

    Every field here describes an organisation or a place. There is no field
    for a person's name, e-mail or telephone number, and a test asserts that
    none of those survives the parser.
    """

    organisation: str = ""
    role: str = ""
    uid: str = ""
    canton: str = ""
    country: str = ""
    city: str = ""


@dataclass(frozen=True)
class ProjectRow:
    """A ``projectlist`` result row. Eight fields, and no participants."""

    aramis_id: int
    project_number: str = ""
    title: str = ""
    office: str = ""
    status: str = ""
    start_date: date | None = None
    end_date: date | None = None
    abstract: str = ""


@dataclass(frozen=True)
class ProjectListPage:
    projects: tuple[ProjectRow, ...]
    matched: int = 0


@dataclass(frozen=True)
class ProjectDetail:
    """One hydrated project, with the participant list the list page omits."""

    aramis_id: int
    project_number: str = ""
    title: str = ""
    office: str = ""
    status: str = ""
    research_type: str = ""
    section: str = ""
    start_date: date | None = None
    end_date: date | None = None
    granted_total_costs: float | None = None
    categories: tuple[str, ...] = ()
    participants: tuple[Participant, ...] = ()

    @property
    def source_url(self) -> str:
        return f"https://www.aramis.admin.ch/Grunddaten/?ProjectID={self.aramis_id}"


# -- the client --------------------------------------------------------------


class AramisClient(HttpClient):
    """The public WCF service, and nothing else.

    ``datenausgabe.aramis.admin.ch`` serves a 43 MB bulk export that no
    interactive command should ever pull. It is absent from
    :attr:`allowed_hosts`, so the CLI cannot reach it by construction.
    """

    allowed_hosts = frozenset({"www.webservice.aramis.admin.ch"})

    def fetch_project_list(
        self,
        *,
        keywords: str = "",
        contractor: str = "",
        budget: str = "",
        language: str = DEFAULT_LANGUAGE,
        skip: int = 0,
        count: int = 20,
        sort: int | None = SORT_START_DATE_DESCENDING,
    ) -> bytes:
        """One ``projectlist`` page.

        ``Count`` and ``Language`` are checked here rather than upstream: 101
        answers HTTP 500, which the retry loop would treat as transient and
        hammer, and a mis-cased language answers HTTP 400.
        """
        if count < 1 or count > MAX_PAGE_SIZE:
            raise ValueError(f"ARAMIS Count must be 1..{MAX_PAGE_SIZE}; {count} answers HTTP 500")
        if skip < 0:
            raise ValueError(f"ARAMIS Skip must be 0 or more, got {skip}")
        body: dict = {"Language": check_language(language), "Skip": skip, "Count": count}
        if sort is not None:
            body["FirstOrderSort"] = int(sort)
        if keywords:
            body["FullTextSearchKeywords"] = keywords
        if contractor:
            body["ContractorFullTextSearchKeywords"] = contractor
        if budget:
            body["BudgetFullTextSearchKeywords"] = budget
        return _checked(self.post(f"{SERVICE}/projectlist", json_body=body).content)

    def fetch_project(self, aramis_id: int, *, language: str = DEFAULT_LANGUAGE) -> bytes:
        query = f"aramisId={int(aramis_id)}&Language={check_language(language)}"
        return _checked(self.get(f"{SERVICE}/project/?{query}").content)


def check_language(language: str) -> str:
    """*language*, or a :class:`ValueError` naming the four the service takes."""
    if language not in LANGUAGES:
        raise ValueError(
            f"ARAMIS Language must be one of {', '.join(LANGUAGES)} and is "
            f"case-sensitive; got {language!r}"
        )
    return language


# -- parsing -----------------------------------------------------------------


def parse_wcf_date(value) -> date | None:
    """The calendar day of a ``/Date(ms±HHMM)/`` timestamp, in its own offset.

    The milliseconds already encode the instant and the offset says where it
    was written. ``/Date(1798758000000+0100)/`` is 2026-12-01 in +0100 and
    2026-11-30 23:00 in UTC, so reading the UTC day would move a third of
    winter dates back by one. ARAMIS also publishes a 1901 start and a
    9999-12-30 "open end" sentinel, both outside what
    :class:`~datetime.datetime` arithmetic tolerates, so the overflow is
    clamped instead of aborting the row.
    """
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ContractError(f"not an ARAMIS date: {value!r}")
    text = value.strip()
    if not text:
        return None
    match = WCF_DATE.match(text)
    if match is None:
        try:
            return date.fromisoformat(text[:10])
        except ValueError as exc:
            raise ContractError(f"unrecognised ARAMIS date {value!r}") from exc

    milliseconds = int(match.group(1))
    try:
        moment = _EPOCH + timedelta(milliseconds=milliseconds)
    except OverflowError:
        return date.max if milliseconds > 0 else date.min
    if match.group(2) is not None:
        sign = 1 if match.group(2) == "+" else -1
        moment = moment + sign * timedelta(hours=int(match.group(3)), minutes=int(match.group(4)))
    return moment.date()


def parse_project_list(content: bytes) -> ProjectListPage:
    """One ``projectlist`` response."""
    payload = _load(content)
    rows = payload.get("Projects")
    if not isinstance(rows, list):
        raise ContractError("the projectlist response has no Projects array")
    matched = payload.get("CountOfMatchedProjects")
    if not isinstance(matched, int) or isinstance(matched, bool):
        matched = len(rows)
    return ProjectListPage(projects=tuple(_list_row(row) for row in rows), matched=matched)


def parse_project(content: bytes) -> ProjectDetail:
    """One ``project`` response, with its participants stripped of personal data."""
    payload = _load(content)
    aramis_id = payload.get("ProjectId")
    if not isinstance(aramis_id, int) or isinstance(aramis_id, bool):
        raise ContractError("a project detail has no ProjectId")
    participants = payload.get("Participants")
    if participants is not None and not isinstance(participants, list):
        raise ContractError("a project detail has a Participants field that is not an array")
    return ProjectDetail(
        aramis_id=aramis_id,
        project_number=_text(payload.get("ProjectNumber")),
        title=_localised(_pick(payload, "ProjectTitle", "Titel", "Title")),
        office=_localised(payload.get("ResearchUnit")),
        status=_localised(payload.get("ProjectStatus")),
        research_type=_localised(payload.get("ResearchType")),
        section=_localised(payload.get("Section")),
        start_date=parse_wcf_date(payload.get("StartDate")),
        end_date=parse_wcf_date(payload.get("EndDate")),
        granted_total_costs=_number(payload.get("GrantedTotalCosts")),
        categories=_categories(payload.get("Categories")),
        participants=tuple(
            _participant(row) for row in (participants or []) if isinstance(row, dict)
        ),
    )


def uid_from_url(*urls: object) -> str:
    """The UID inside a participant URL, in its official spelling, or ``""``.

    Both ``URL1`` and ``URL2`` are scanned together: the service files the UID
    link in either, depending on the office that entered the project. ARAMIS
    stores it without separators and the register writes it as
    ``CHE-106.209.800``, so it is reported in the register's spelling and
    compared with the separators removed.
    """
    for url in urls:
        if not isinstance(url, str):
            continue
        match = UID_IN_URL.search(url)
        if match:
            return dotted(match.group(1))
    return ""


def squash(uid: str) -> str:
    """A UID with its separators removed, for comparing two spellings of one."""
    return "".join(character for character in (uid or "").upper() if character.isalnum())


def dotted(uid: str) -> str:
    """A UID in the register's official spelling: ``CHE-106.209.800``.

    A value that is not ``CHE`` plus nine digits comes back with its
    separators removed and nothing else done to it.
    """
    flat = squash(uid)
    if len(flat) != 12 or not flat.startswith("CHE") or not flat[3:].isdigit():
        return flat
    return f"CHE-{flat[3:6]}.{flat[6:9]}.{flat[9:12]}"


def search_term(legal_name: str) -> str:
    """A search term from a legal name: the form stripped, the length capped.

    ``Company1`` is truncated at 35 characters upstream, so a term longer than
    that can only fail to match. A loose term is safe on the UID path, where
    the participant's own UID decides what is reported.
    """
    term = " ".join((legal_name or "").split())
    for suffix in sorted(LEGAL_FORM_SUFFIXES, key=len, reverse=True):
        if term.lower().endswith(f" {suffix.lower()}"):
            term = term[: -len(suffix) - 1].rstrip(" ,")
            break
    return term[:MAX_TERM_CHARS].strip()


# -- orchestration -----------------------------------------------------------


def search(
    client: AramisClient,
    *,
    keywords: str = "",
    contractor: str = "",
    language: str = DEFAULT_LANGUAGE,
    limit: int = 20,
) -> list[ProjectRow]:
    """One ``projectlist`` request, newest first, capped at one page."""
    count = max(1, min(limit, MAX_PAGE_SIZE))
    page = parse_project_list(
        client.fetch_project_list(
            keywords=keywords, contractor=contractor, language=language, count=count
        )
    )
    return list(page.projects)


def candidates_for_name(
    client: AramisClient,
    name: str,
    *,
    language: str = DEFAULT_LANGUAGE,
    limit: int = 20,
) -> list[ProjectRow]:
    """Projects whose contractor field or free text mentions *name*.

    Two requests, one per search key, merged with the contractor hits first and
    duplicates dropped. Neither key indexes the participant list, so this
    returns nothing for a company named only there.
    """
    found: dict[int, ProjectRow] = {}
    for key in ("contractor", "keywords"):
        for row in search(client, limit=limit, language=language, **{key: name}):
            found.setdefault(row.aramis_id, row)
    return list(found.values())[:limit]


def hydrate(
    client: AramisClient,
    rows: list[ProjectRow],
    *,
    language: str = DEFAULT_LANGUAGE,
    on_note: Callable[[str], None] | None = None,
) -> list[ProjectDetail]:
    """One detail request per row, which is the only way to see participants."""
    details = []
    for index, row in enumerate(rows, start=1):
        if on_note is not None:
            on_note(f"  hydrating {index}/{len(rows)}: {row.project_number or row.aramis_id}")
        details.append(parse_project(client.fetch_project(row.aramis_id, language=language)))
    return details


def confirmed_projects(
    client: AramisClient,
    uid: str,
    name: str,
    *,
    language: str = DEFAULT_LANGUAGE,
    limit: int = 20,
    on_note: Callable[[str], None] | None = None,
) -> list[tuple[ProjectDetail, Participant]]:
    """Projects carrying a participant whose own UID equals *uid*.

    *name* finds the candidates and the UID decides which of them are reported.
    A project whose participant UID differs is dropped, which is the point.
    """
    wanted = squash(uid)
    rows = candidates_for_name(client, name, language=language, limit=limit)
    confirmed = []
    for detail in hydrate(client, rows, language=language, on_note=on_note):
        for participant in detail.participants:
            if participant.uid and squash(participant.uid) == wanted:
                confirmed.append((detail, participant))
                break
    return confirmed


# -- rows --------------------------------------------------------------------


def confirmed_row(detail: ProjectDetail, participant: Participant) -> dict:
    """One confirmed project as a row. Key order is column order."""
    return {
        "title": detail.title,
        "project_number": detail.project_number,
        "office": detail.office,
        "status": detail.status,
        "start_date": detail.start_date,
        "end_date": detail.end_date,
        "granted_total_costs": detail.granted_total_costs,
        "role": participant.role,
        "uid": participant.uid,
        "aramis_id": detail.aramis_id,
    }


def project_row(detail: ProjectDetail) -> dict:
    """One text-matched project as a row, with its participating organisations."""
    return {
        "title": detail.title,
        "project_number": detail.project_number,
        "office": detail.office,
        "status": detail.status,
        "start_date": detail.start_date,
        "end_date": detail.end_date,
        "granted_total_costs": detail.granted_total_costs,
        "participants": [
            label for label in map(_participant_label, detail.participants) if label
        ],
        "aramis_id": detail.aramis_id,
    }


# -- helpers -----------------------------------------------------------------


def _fault_text(content: bytes) -> str:
    """The fault message when *content* is an ``A2AFault`` body, else ``""``."""
    if not content or len(content) > 4000:
        return ""
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    fault = payload.get("FaultText")
    if isinstance(fault, dict):
        return str(fault.get("Text") or "")[:500]
    return ""


def _checked(content: bytes) -> bytes:
    """*content*, unless the service sent a fault instead of a project.

    ARAMIS returns an ``A2AFault`` with HTTP 200 as well as with 500, so the
    body decides rather than the status line.
    """
    fault = _fault_text(content)
    if fault:
        raise ServiceFault(f"ARAMIS answered with a fault: {fault}")
    return content


def _load(content: bytes) -> dict:
    try:
        payload = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AramisError(f"invalid JSON from ARAMIS: {exc}") from exc
    if not isinstance(payload, dict):
        raise ContractError(f"expected a JSON object, got {type(payload).__name__}")
    return payload


def _pick(payload: dict, *names: str):
    """The first of *names* the payload actually carries, wire spelling first."""
    for name in names:
        if payload.get(name) is not None:
            return payload[name]
    return None


def _list_row(row) -> ProjectRow:
    if not isinstance(row, dict):
        raise ContractError("a projectlist row is not an object")
    aramis_id = row.get("Id")
    if not isinstance(aramis_id, int) or isinstance(aramis_id, bool):
        raise ContractError("a projectlist row has no Id")
    return ProjectRow(
        aramis_id=aramis_id,
        project_number=_text(row.get("ProjectNumber")),
        title=_localised(_pick(row, "Titel", "Title")),
        office=_localised(row.get("Department")),
        status=_localised(row.get("Status")),
        start_date=parse_wcf_date(row.get("StartDate")),
        end_date=parse_wcf_date(row.get("EndDate")),
        abstract=_localised(row.get("Abstract")),
    )


def _participant(row: dict) -> Participant:
    """One participant, organisational fields only.

    ``Company1`` through ``Company4`` are the organisation, its department and
    its sub-units. Only the first is kept: the others name an internal unit,
    and ``ShortViewName``, which reads like a fuller name, concatenates the
    organisation with the researcher and cannot be separated back into parts.
    """
    return Participant(
        organisation=_text(row.get("Company1")),
        role=_localised(row.get("KindOfParticipation")),
        uid=uid_from_url(row.get("URL1"), row.get("URL2")),
        canton=_text(row.get("Canton")),
        country=_text(row.get("Country")),
        city=_text(row.get("City")),
    )


def _categories(value) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    names = []
    for group in value:
        if not isinstance(group, dict):
            continue
        for category in _pick(group, "Categroies", "Categories") or ():
            if isinstance(category, dict):
                name = _localised(category.get("Name"))
                if name:
                    names.append(name)
    return tuple(names)


def _participant_label(person: Participant) -> str:
    """``Organisation (UID)``, or whichever half the service actually filed.

    A participant block sometimes names a person and no organisation, and by
    the time it reaches here that block is empty. It becomes an empty label,
    which the row builder drops rather than printing as a gap in a list.
    """
    if person.organisation and person.uid:
        return f"{person.organisation} ({person.uid})"
    return person.organisation or person.uid


def _localised(value) -> str:
    """The text out of a ``{LanguageCode, Text}`` block, or a plain string."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return _text(value.get("Text"))
    return ""


def _text(value) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def _number(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None
