Changelog
=========

0.1.1 (2026-09-07)
------------------

- ``swissco_tenders`` says what its date filter matches: each project's newest
  publication, whichever type that publication is. ``pub_types`` is what
  narrows a result to awards.

0.1.0 (2026-09-07)
------------------

First release. Nine tools over the six sources ``swissco`` already reads.

- ``swissco_lookup``, ``swissco_search``, ``swissco_publications``,
  ``swissco_events``, ``swissco_tenders``, ``swissco_vendor``,
  ``swissco_finma``, ``swissco_lei`` and ``swissco_research``. One per
  ``swissco`` command except ``watch``, which needs state a tool call has no
  place to keep.
- Every tool returns ``rows``, a ``count`` and ``notes``. The rows are the
  dicts ``swissco --format json`` prints, so a field carries the same name and
  the same value in both surfaces.
- ``notes`` carry the domain caveats the command line writes to stderr: what
  FINMA's list omits, how rare an LEI is, which part of ARAMIS a search
  reaches, and what absence from LINDAS does and does not mean.
- ``limit`` caps at 100 rows. ``swissco_publications`` reads at most 7 days of
  the gazette per call and ``swissco_events`` at most 365, keeping the newest
  end of a wider range and saying so in ``notes``.
- Settings come from the environment: ``ZEFIX_USER`` and ``ZEFIX_PASSWORD``
  extend two tools, ``SWISSCO_STATE`` moves the cache, and
  ``SWISSCO_INTERVAL`` raises the request pacing floor. Lowering the floor is
  refused inside the client.
- Every tool is annotated read-only, idempotent and open-world.
