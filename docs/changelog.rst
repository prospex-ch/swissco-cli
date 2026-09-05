Changelog
=========

0.3.0 (2026-09-05)
------------------

Two more sources, one of them the first from outside Switzerland.

- ``lei``: a company's Legal Entity Identifier from GLEIF, the entity that
  consolidates it, and the entity at the top of that chain. ``--children``
  lists what it consolidates in turn. The parent is frequently foreign, which
  is the case for reading it: the commercial register carries no entry for a
  Swiss company's owner abroad.
- ``lookup --lei`` adds the LEI and both parents to a company. Opt-in, the way
  ``--finma`` is, because it costs requests a plain ``lookup`` does not.
- Both UID spellings GLEIF stores are tried, squashed first. A 404 on a
  relationship is read as "reports no parent".
- ``research``: federally funded research projects from ARAMIS, Innosuisse and
  SNSF money included. A UID is confirmed against each project's own
  participant UID; free text is searched as given and reported unconfirmed.
- ARAMIS's ``Count`` ceiling and its case-sensitive ``Language`` are refused
  before the request, and an ``A2AFault`` body is recognised even when it
  arrives with HTTP 200.
- No participant search, because ARAMIS offers none. Its three text keys reach
  the title, the abstract, the contractor field and the budget field, so a
  company named only in the structured participant list cannot be found.
- ``swissco.aramis.Participant`` carries no field for a researcher's name,
  e-mail address or telephone number, and a test asserts that none of them
  survives the parser.
- No bulk export. The 43 MB ARAMIS file is off the client's host allowlist.

0.2.0 (2026-09-05)
------------------

Two new sources, both federal, both unauthenticated.

- ``tenders``: public procurement projects from simap, filtered by canton and
  publication date. Cursor pagination, so there is no offset ceiling to run
  into the way the gazette has one.
- ``vendor``: whether a company is in simap's vendor directory. A UID is
  confirmed against the directory's own ``uidNo`` rather than matched by name.
- ``finma``: FINMA's authorised banks and securities firms, joined to a UID
  through the crosswalk FINMA publishes alongside the list.
- ``lookup --finma`` adds the licence type and supervisory category to a
  company. Opt-in, because it costs two downloads a plain ``lookup`` does not.
- A week-long file cache under the state directory for the two FINMA files,
  which upstream republishes rather than versions. ``--refresh`` ignores it,
  and a failed download falls back to the last good copy rather than to
  nothing.
- No award-history command. The supplier named on a simap award carries no UID,
  so joining one to a company would mean matching a free-text name with nothing
  to confirm it against.

0.1.0 (2026-09-04)
-------------------

Initial release.

- ``lookup``, ``search``, ``publications``, ``events`` and ``watch``.
- LINDAS by default, so every command works without credentials. Zefix
  PublicREST is layered on when they are supplied.
- Client-side filtering of gazette list pages, because the API accepts its
  filter parameters and ignores them.
- Adaptive date-range splitting around the API's 10,000-result offset window.
- ``table``, ``json`` and ``csv`` output, identical in a terminal and in a pipe.
- A body cache under the state directory, so an overlapping ``events`` re-run
  costs nothing.
