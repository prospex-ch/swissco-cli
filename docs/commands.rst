Commands
========

Five commands. Each takes ``--format table|json|csv`` (default ``table``),
``--limit``, ``--quiet``, ``--interval``, ``--state``, ``--user`` and
``--password``.

Exit codes are ``0`` for success, ``1`` for a failed request, and ``10`` for
``swissco watch`` when it found a change.


lookup
------

.. code-block:: console

   $ swissco lookup CHE-444.420.929
   legal name       Baumberger Bau AG
   uid              CHE-444.420.929
   chid             CH-036.9.103.786-9
   ehra id          1702823
   legal form code  0151
   legal form       Schweizerische Zweigniederlassung im Handelsregister eingetragen
   municipality     Koppigen
   canton           BE
   address          Hauptstrasse 6, 3425 Koppigen
   purpose          Anbieten von Kleintransporte aller Art.
   zefix uri        https://register.ld.admin.ch/zefix/company/1702823

Takes a UID in any punctuation, and verifies its check digit before spending a
request.

The UID comes back punctuated. LINDAS stores it bare (``CHE444420929``), and
every other place a person meets it writes ``CHE-444.420.929``.

With Zefix PublicREST credentials, ``lookup`` also prints ``status``,
``capital_nominal``, ``deletion_date``, ``old_names``, ``branch_offices``,
``head_offices``, ``has_taken_over`` and ``was_taken_over_by``. Those fields
come from a second source and LINDAS does not publish them.


search
------

.. code-block:: console

   $ swissco search "usinage" --canton VD --limit 5

Matches the legal name and the statutory purpose, case-insensitively, as a
substring. The purpose is what makes this worth running: it is a company's own
description of its business, filed with the register.

.. list-table::
   :widths: 30 70

   * - ``--canton``
     - Two-letter code, e.g. ``VD``
   * - ``--legal-form``
     - eCH-0097 code: ``0106`` an AG, ``0107`` a GmbH
   * - ``--via rest``
     - Name-prefix search through PublicREST; needs credentials

``--via rest`` answers a different question. LINDAS matches a substring
anywhere in the name or the purpose; PublicREST matches the start of the name,
which is usually what a person means when they type a company name.


publications
------------

.. code-block:: console

   $ swissco publications --canton ZH --since 2026-09-03 --until 2026-09-03 --limit 5
   PUBLICATION_DATE  CANTON  SUB_RUBRIC  TITLE                                       LANGUAGE  STATE
   ----------------  ------  ----------  ------------------------------------------  --------  ---------
   2026-09-03        ZH      HR03        Löschung Bukos GmbH in Liquidation, Zürich  de        PUBLISHED
   2026-09-03        ZH      HR02        Mutation LCH (Dachverband Lehrerinnen …     de        PUBLISHED
   2026-09-03        ZH      HR02        Mutation Direc Recycling GmbH, Winterthur…  de        PUBLISHED

.. list-table::
   :widths: 30 70

   * - ``--since``, ``--until``
     - Date bounds, ``YYYY-MM-DD``. Defaults to yesterday
   * - ``--canton``
     - Canton code, repeatable
   * - ``--sub-rubric``
     - ``HR01`` registrations, ``HR02`` mutations, ``HR03`` deletions
   * - ``--query``
     - Text to look for in the title, in any of the four languages
   * - ``--type``
     - Keep only publications carrying this event, repeatable

Without ``--type``, only list pages are read: one request per 2,000
publications, and the filters run over the ``<meta>`` block those pages
already carry.

``--type`` costs a request per surviving publication, because the event types
live in the body. Narrow the range and the canton first.

.. code-block:: console

   $ swissco publications --canton ZG --since 2026-09-03 --until 2026-09-03 --type CAPITAL_INCREASED
   57 publications match the filters; fetching each body to classify it, at 0.5s per request

The eleven types are ``INCORPORATION``, ``BRANCH_CREATED``, ``SEAT_MOVED``,
``ADDRESS_CHANGED``, ``NAME_CHANGED``, ``PURPOSE_CHANGED``,
``CAPITAL_INCREASED``, ``MERGER``, ``OFFICERS_CHANGED``, ``LIQUIDATION`` and
``DELETED``. `shab-parser's documentation
<https://shab-parser.readthedocs.io/en/latest/events.html>`_ says what fires
each one.

Long ranges are split
~~~~~~~~~~~~~~~~~~~~~

The API refuses any request whose page offset reaches 10,000, and the gazette
publishes around a thousand commercial-register entries a day. Past about ten
days, ``swissco`` splits the range into windows and fetches each one, reporting
them as they land:

.. code-block:: console

   $ swissco events CHE-444.420.929 --since 2026-06-01
   Baumberger Bau AG: scanning the gazette from 2026-06-01 to 2026-09-04.
     2026-06-01 to 2026-06-06: 6743 publications
     2026-06-07 to 2026-06-12: 6594 publications


events
------

.. code-block:: bash

   swissco events CHE-444.420.929 --since 2024-01-01

One company's registry history, joined across the two sources.

The gazette's list pages carry a title and no UID, and every search parameter
the API accepts is ignored for anonymous callers. So the join runs in two
stages. The UID is resolved to a legal name through LINDAS, and publications
whose title looks like that name are kept. Those bodies are then fetched and
parsed, and an event survives only when the body's own UID equals the one
asked for.

The title match decides what is worth downloading; the body's UID decides what
is reported. A publication carrying no UID at all is dropped.

Fetched bodies are cached under the state directory, keyed by publication id,
so an overlapping re-run costs nothing. A published gazette document never
changes, so the cache needs no expiry. ``--no-cache`` fetches everything.


watch
-----

.. code-block:: console

   $ swissco watch uids.txt --state ~/.swissco/
   2 of 2 companies found; 1 unchanged. State written to /home/me/.swissco/state.json
   UID              STATUS   LEGAL_NAME         CHANGES
   ---------------  -------  -----------------  -------
   CHE-444.420.929  changed  Baumberger Bau AG  purpose

The UID file takes one UID per line. Blank lines and ``#`` comments are
skipped, and a UID that fails its check digit is reported on stderr and passed
over.

Each company is compared by fingerprint: a SHA-256 over the canonical JSON of
its identity, address and purpose fields, computed by ``zefix-parser``. When
that digest moves, ``changes`` names the fields that differ.

Exit ``10`` on any change, ``0`` on none, so cron and shell scripts can branch
on the result without parsing the output.

Absence is not deletion
~~~~~~~~~~~~~~~~~~~~~~~

A UID that was in the dataset and now is not is reported as **no longer in the
dataset**. LINDAS carries active entities, so a UID can leave it after a
re-registration, a correction, or a publication lag, none of which means the
company ended. Use ``swissco events`` to find out which, or ``lookup`` with
PublicREST credentials, whose ``status`` and ``deletion_date`` answer it
directly.

Only UIDs in the file you passed can be reported as vanished. Dropping a UID
from the list takes it off the watch, and says nothing about the register.
