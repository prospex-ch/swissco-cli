"""The SELECT list and graph pattern a searched entity is read back with.

``zefix-parser`` owns the shape of a :class:`~zefix_parser.RegistryEntity` and
the parser that folds SPARQL rows into one. It builds queries for the three
accesses it supports — count, keyset page, detail by URI or UID — but a
filtered search is not among them, so the pattern has to be restated here.

It is a restatement rather than an import because ``_ENTITY_FIELDS`` and
``_ENTITY_PATTERN`` are private to that library: reaching into them would tie
this CLI to an internal name, and a rename upstream would break the search with
no warning. The coupling that remains is the honest one — every variable below
must keep the name ``zefix_parser.parse_entity_page`` reads it under, which the
tests assert against a recorded response.
"""

from __future__ import annotations

#: One row per language-tagged literal, folded down by ``parse_entity_page``.
ENTITY_FIELDS = """\
SELECT ?entity ?legalName ?name ?uid ?chid ?ehraId
       ?legalFormUri ?legalFormLabel
       ?municipalityUri ?municipalityLabel
       ?canton
       ?streetAddress ?postalCode ?locality
       ?purpose
"""

ENTITY_PATTERN = """\
  ?entity schema:legalName ?legalName .

  OPTIONAL { ?entity schema:name ?name . }

  OPTIONAL {
    ?entity schema:identifier ?uidNode .
    ?uidNode schema:name "CompanyUID" ;
             schema:value ?uid .
  }

  OPTIONAL {
    ?entity schema:identifier ?chidNode .
    ?chidNode schema:name "CompanyCHID" ;
              schema:value ?chid .
  }

  OPTIONAL {
    ?entity schema:identifier ?ehraIdNode .
    ?ehraIdNode schema:name "CompanyEHRAID" ;
                schema:value ?ehraId .
  }

  OPTIONAL {
    ?entity schema:additionalType ?legalFormUri .
    OPTIONAL { ?legalFormUri (schema:name|rdfs:label) ?legalFormLabel . }
  }

  OPTIONAL {
    ?entity admin:municipality ?municipalityUri .
    ?municipalityUri schema:name ?municipalityLabel .
  }

  OPTIONAL { ?entity schema:address/schema:addressRegion ?canton . }
  OPTIONAL { ?entity schema:address/schema:streetAddress ?streetAddress . }
  OPTIONAL { ?entity schema:address/schema:postalCode ?postalCode . }
  OPTIONAL { ?entity schema:address/schema:addressLocality ?locality . }

  OPTIONAL { ?entity schema:description ?purpose . }
"""


def escape_literal(value: str) -> str:
    """*value* made safe to sit inside a double-quoted SPARQL literal.

    Nothing upstream does this: every query builder in ``zefix-parser`` takes
    values it produced itself, where this CLI takes them from a shell argument.
    A search term containing a quote would close the literal and let the rest
    of the term be read as query syntax, so the two characters that can do that
    — the quote and the backslash that would smuggle one back in — are escaped,
    along with the newlines a literal may not contain.
    """
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )
