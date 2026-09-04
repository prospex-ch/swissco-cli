"""Looking a company up, and searching for one.

Both run over LINDAS, the open SPARQL endpoint, because that is the only Zefix
path that answers an anonymous request: the PublicREST API returns 401 to
everyone without credentials from ``zefix@bj.admin.ch``. When credentials *are*
present, REST is layered on top rather than swapped in — it carries capital,
status, deletion date, former names and corporate relations, none of which
LINDAS publishes.
"""

from __future__ import annotations

from zefix_parser import (
    Company,
    RegistryEntity,
    clean_uid,
    format_chid,
    format_uid,
    is_valid_uid,
    normalize_uid,
)
from zefix_parser.client import LindasClient, ZefixRestClient
from zefix_parser.lindas import PREFIXES, parse_entity_page

from ._sparql import ENTITY_FIELDS, ENTITY_PATTERN, escape_literal

#: Legal forms are eCH-0097 codes behind this prefix, which is what
#: ``schema:additionalType`` points at.
LEGAL_FORM_BASE = "https://ld.admin.ch/ech/97/legalforms/"

SEARCH_QUERY = """\
{prefixes}
{fields}WHERE {{
  {{
    SELECT DISTINCT ?entity WHERE {{
      ?entity a admin:ZefixOrganisation ;
              schema:legalName ?searchName .
      OPTIONAL {{ ?entity schema:description ?searchPurpose . }}
{filters}    }}
    ORDER BY STR(?entity)
    LIMIT {limit}
  }}

{pattern}}}
"""


class NotAUid(ValueError):
    """The value given where a UID was expected is not one."""


def resolve_uid(value: str) -> str:
    """*value* as a normalized UID, or raise :class:`NotAUid`.

    Accepts every form a user is likely to paste: ``CHE-444.420.929``,
    ``CHE444420929``, or the same wrapped in other text ("VAT: CHE-... MWST").
    The check digit is verified, because a mistyped UID can never match the
    register and rejecting it here costs no request.
    """
    for candidate in (normalize_uid(value), clean_uid(value)):
        if candidate and is_valid_uid(candidate):
            return candidate
    raise NotAUid(
        f"{value!r} is not a valid Swiss UID "
        "(expected CHE-123.456.789 with a valid check digit)"
    )


def build_search_query(
    term: str,
    *,
    canton: str = "",
    legal_form: str = "",
    limit: int = 20,
) -> str:
    """A SPARQL query for companies matching *term*.

    *term* is matched case-insensitively against both the legal name and the
    statutory purpose (``schema:description``). ``||`` is what makes a missing
    purpose harmless: a name hit short-circuits before the unbound purpose can
    raise, and a row where both are absent is dropped rather than returned.

    Every interpolated value is escaped — neither library escapes for you, and
    a term containing a quote would otherwise close the literal and change the
    query.
    """
    needle = escape_literal(term.strip().lower())
    filters = [
        f'      FILTER (CONTAINS(LCASE(STR(?searchName)), "{needle}")\n'
        f'              || CONTAINS(LCASE(STR(?searchPurpose)), "{needle}"))\n'
    ]
    if canton:
        code = escape_literal(canton.strip().upper()[:2])
        filters.append(
            "      ?entity schema:address/schema:addressRegion ?searchCanton .\n"
            f'      FILTER (UCASE(STR(?searchCanton)) = "{code}")\n'
        )
    if legal_form:
        code = escape_literal(legal_form.strip())
        filters.append(
            f"      ?entity schema:additionalType <{LEGAL_FORM_BASE}{code}> .\n"
        )
    return SEARCH_QUERY.format(
        prefixes=PREFIXES,
        fields=ENTITY_FIELDS,
        filters="".join(filters),
        limit=_limit(limit),
        pattern=ENTITY_PATTERN,
    )


def lookup(client: LindasClient, uid: str) -> RegistryEntity | None:
    """The LINDAS record for *uid*, or ``None`` when the dataset has none."""
    entities = client.fetch_by_uids([uid])
    return entities[0] if entities else None


def search(
    client: LindasClient,
    term: str,
    *,
    canton: str = "",
    legal_form: str = "",
    limit: int = 20,
) -> list[RegistryEntity]:
    """Companies whose name or purpose contains *term*, name-sorted."""
    query = build_search_query(term, canton=canton, legal_form=legal_form, limit=limit)
    entities = parse_entity_page(client.query(query))
    entities.sort(key=lambda e: (e.legal_name.casefold(), e.uid))
    return entities


def search_rest(
    client: ZefixRestClient, term: str, *, limit: int = 20
) -> list[Company]:
    """Companies whose name *starts with* term, via the PublicREST API.

    A different question from :func:`search`, and usually the one a person
    means when they type a company name: REST matches a name prefix, where
    LINDAS matches a substring of the name or of the purpose. Needs
    credentials.
    """
    return client.search(term, max_entries=_limit(limit))


def entity_row(entity: RegistryEntity) -> dict:
    """One LINDAS record as a flat, render-ready dict.

    The UID is re-punctuated on the way out: LINDAS stores it bare
    (``CHE444420929``), and every other place a person meets it — the register,
    an invoice, the REST API's own path — writes ``CHE-444.420.929``.
    """
    return {
        "legal_name": entity.legal_name,
        "uid": format_uid(entity.uid) if entity.uid else "",
        "chid": format_chid(entity.chid) if entity.chid else "",
        "ehra_id": entity.ehra_id,
        "legal_form_code": entity.legal_form_code,
        "legal_form": entity.legal_form_name,
        "municipality": entity.municipality_name,
        "canton": entity.canton,
        "address": _address(entity),
        "purpose": entity.purpose,
        "zefix_uri": entity.zefix_uri,
    }


def search_row(entity: RegistryEntity) -> dict:
    """One search hit as a flat, render-ready dict.

    Narrower than :func:`entity_row`: a result list is scanned, and the CH-ID,
    the EHRA id and the entity URI are identifiers to act on once a company has
    been picked out. ``swissco lookup`` prints those.
    """
    return {
        "legal_name": entity.legal_name,
        "uid": format_uid(entity.uid) if entity.uid else "",
        "legal_form": entity.legal_form_name,
        "municipality": entity.municipality_name,
        "canton": entity.canton,
        "purpose": entity.purpose,
    }


def rest_row(company: Company) -> dict:
    """The fields the REST detail record adds over :func:`entity_row`.

    Deliberately only the additions. The overlapping fields are already in the
    LINDAS row, and printing both invites a reader to wonder which one is
    right when they momentarily disagree.
    """
    return {
        "status": company.status,
        "capital_nominal": (
            str(company.capital_nominal) if company.capital_nominal is not None else ""
        ),
        "capital_currency": company.capital_currency if company.capital_nominal else "",
        "deletion_date": (
            company.deletion_date.isoformat() if company.deletion_date else ""
        ),
        "old_names": [old.name for old in company.old_names],
        "branch_offices": [related.name for related in company.branch_offices],
        "head_offices": [related.name for related in company.head_offices],
        "has_taken_over": [related.name for related in company.has_taken_over],
        "was_taken_over_by": [related.name for related in company.was_taken_over_by],
        "cantonal_excerpt": company.cantonal_excerpt_web,
    }


def rest_search_row(company: Company) -> dict:
    """One REST search hit as a render-ready dict."""
    return {
        "legal_name": company.name,
        "uid": format_uid(company.uid) if company.uid else "",
        "chid": format_chid(company.chid) if company.chid else "",
        "ehra_id": str(company.ehraid),
        "canton": company.canton,
        "status": company.status,
    }


def _address(entity: RegistryEntity) -> str:
    parts = [entity.street_address, " ".join(
        p for p in (entity.postal_code, entity.locality) if p
    )]
    return ", ".join(part for part in parts if part)


def _limit(limit: int) -> int:
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit!r}")
    return int(limit)
