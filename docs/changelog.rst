Changelog
=========

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
