Changelog
=========

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
