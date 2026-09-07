Commands
========

Ten commands. Each takes ``--format table|json|csv`` (default ``table``),
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

``--finma`` adds the licence type and supervisory category. ``--lei`` adds the
LEI and the entities that consolidate this company. Both are opt-in, because
each costs requests a plain ``lookup`` does not.

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

tenders
-------

Public procurement projects from simap, by canton and publication date.

.. code-block:: console

   $ swissco tenders --canton ZG --since 2026-08-25 --limit 3
   simap projects published 2026-08-25 to 2026-09-05 in ZG. The date matches each project's newest publication, whichever type that publication is.
     page of 13 projects (after 0)
   TITLE                                                  PROJECT_NUMBER  BUYER                           CANTON  CITY  PUBLICATION_DATE  PUBLICATION_TYPE
   -----------------------------------------------------  --------------  ------------------------------  ------  ----  ----------------  ----------------
   Neubau Pfarreizentrum, Katholische Kirchgemeinde Baar  22047           Katholische Kirchgemeinde Baar  ZG      Baar  2026-09-05        award

.. list-table::
   :header-rows: 1

   * - Flag
     - Does
   * - ``--since`` / ``--until``
     - Publication date range, ``YYYY-MM-DD``. Defaults to the last seven days.
   * - ``--canton``
     - Two-letter canton code, repeatable.
   * - ``--type``
     - Publication type, repeatable: ``award``, ``tender``, ``direct_award``,
       ``abandonment``, ``revocation`` and six more.
   * - ``--lang``
     - Which language to report the title and buyer in, when the office
       published more than one. Defaults to de, then fr, it, en.

Paging is a cursor rather than an offset, so a wide range costs pages and never
fails the way a deep gazette query does. Each page is reported on stderr as it
lands.

The date range is on the newest publication
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``--since`` and ``--until`` filter each project's **newest** publication, not
the date of the award or the tender inside it. A project awarded in March whose
newest publication is an August correction appears only in a range covering
August. This is the endpoint's own filter, not something ``swissco`` imposes,
and it is the easiest thing here to misread.

vendor
------

Whether a company is registered as a supplier on simap.

.. code-block:: console

   $ swissco vendor CHE-409.633.691
   searching the simap vendor directory for 'Egli Gartenbau AG Sursee'
   1 profile(s) confirmed on the directory's own uidNo
   name                   Egli Gartenbau AG Sursee
   uid no                 CHE-409.633.691
   street                 Schlottermilch 18
   postal code            6210
   city                   Sursee
   canton                 LU
   url                    https://www.gartenbau-egli.ch
   company size           medium

A UID is resolved to a legal name through LINDAS, searched for in the
directory, and then **confirmed on the directory's own** ``uidNo``. The name
finds the candidates; the UID decides between them. Anything else is treated as
free text and every hit is returned unfiltered.

``not_in_vendor_directory`` means no profile carries that UID. A company can bid
without a directory profile, and a bidding consortium has a profile with no UID
at all, so that is "not in the directory", never "does not bid for public work".

.. warning::

   ``swissco`` has no command for what a company has **won**. The supplier named
   on a simap award carries no UID, only a free-text name typed by a procurement
   office — the directory holds both an "Egli Gartenbau AG Sursee" and an "Egli
   Gartenbau AG Uster". Joining an award to a company would mean matching those
   names with nothing to confirm the match against, so it is not offered.

finma
-----

FINMA's authorised banks and securities firms, joined to a UID.

.. code-block:: console

   $ swissco finma --uid CHE-105.845.287
   FINMA lists 278 authorised banks and securities firms; 277 carry a UID.
   name                  Aargauische Kantonalbank
   city                  Aarau 1
   licence type          Bank
   supervisory category  3
   uid                   CHE-105.845.287
   foreign control       false

.. list-table::
   :header-rows: 1

   * - Flag
     - Does
   * - ``QUERY``
     - Optional text matched against the name or the city.
   * - ``--uid``
     - One institution by UID, printed as label/value pairs.
   * - ``--licence``
     - ``Bank``, ``Securities firm``, ``Foreign bank branch office`` or
       ``Foreign securities firm branch office``.
   * - ``--category``
     - FINMA supervisory category, ``1`` (largest) to ``5``.
   * - ``--refresh``
     - Re-download both files, ignoring the week-long cache.

Absence is not a missing licence
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A UID that is not on this list is reported as **not on FINMA's authorised banks
and securities firms list**, which is all it means. FINMA licenses insurers,
portfolio managers, trustees, fund management companies and more on separate
lists ``swissco`` does not read, and publishes a few authorised entities with
no UID at all. Never read a miss here as "unlicensed".


lei
---

One company's Legal Entity Identifier, and the group it is consolidated into.

.. code-block:: console

   $ swissco lei CHE-412.669.376
   legal name                 UBS Switzerland AG
   lei                        549300WOIFUSNYH0FL22
   registered as              CHE-412.669.376
   jurisdiction               CH
   status                     ACTIVE
   registration status        ISSUED
   city                       Zurich
   initial registration date  2014-12-15
   direct parent              UBS AG (BFM8T61CT2L1QCEMIK50, CH)
   ultimate parent            UBS Group AG (549300SZJ9VS8SGXAN81, CH)
   direct children            0

.. list-table::
   :header-rows: 1

   * - Flag
     - Does
   * - ``UID``
     - The company, in any punctuation. The check digit is verified locally.
   * - ``--children``
     - List the entities this one consolidates as rows, instead of counting
       them. ``--limit`` sets the page size.

One lookup costs one search request plus three relationship requests.
``--children`` changes only what is printed; the requests are the same.
``swissco lookup --lei`` skips the child count and costs three requests.

The parent is a foreign entity as often as a Swiss one, which is the reason to
run this: a Swiss subsidiary's owner abroad has no commercial-register entry,
so the register cannot answer the question at all.

A parent is an accounting relationship
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

GLEIF Level 2 records **accounting consolidation**: the parent is the entity
that consolidates this one into its financial statements. A parent that
consolidates a subsidiary may hold less than all of it, and a majority owner
that consolidates nothing is absent from the file. Report a parent as
"consolidated by", and treat the shareholding question as unanswered.

Most Swiss companies have no LEI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

About 28,000 Swiss entities hold an LEI, against roughly 790,000 in the
commercial register, and about 81% of those LEIs carry a register number that
``swissco`` can join on. A ``not_found`` here means the company has no LEI on
file. It says nothing about whether the company exists, trades, or is in good
standing.

GLEIF stores the register number in whichever spelling the entity filed, and
both are in live use: Aargauische Kantonalbank is ``CHE105845287`` and UBS
Switzerland AG is ``CHE-412.669.376``. ``swissco`` tries the squashed form
first and the dotted form second, so a lookup costs one request more when the
company filed the dotted one.

research
--------

Federally funded research projects from ARAMIS, the Confederation's register of
research and innovation mandates. Innosuisse grants, SNSF money and every
departmental research contract are in it.

.. code-block:: console

   $ swissco research CHE-337.958.399
   searching ARAMIS for 'MPAssist', then confirming each candidate on its own participant UID
   TITLE                                  PROJECT_NUMBER    OFFICE      STATUS      START_DATE  ROLE
   Reducing Documentation Burden in Sw…   137.839 INNO-ICT  INNOSUISSE  In Process  2026-06-01  Implementation Partner

.. list-table::
   :header-rows: 1

   * - Flag
     - Does
   * - ``QUERY``
     - A UID, confirmed exactly against each project's own participant UID, or
       free text, searched as given and reported unconfirmed.
   * - ``--limit``
     - How many candidate projects are hydrated. Each one is a request.
   * - ``--lang``
     - ``DE``, ``EN``, ``FR`` or ``IT``, case-sensitive. Defaults to ``EN``.

A project's participant list is the only place a UID appears, and the list page
does not carry it, so every candidate costs one detail request at the current
interval. ``swissco`` says how many it is about to fetch before it starts.

Free text returns every hit with its participating organisations and their
UIDs. A UID returns only the projects carrying a participant whose own UID
matches, so a project found by name that belongs to a different company is
dropped.

The search does not reach the participant list
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ARAMIS offers three text keys: the project title and abstract, the free-text
contractor field, and the budget field. A company is findable through this
command when its name appears in one of those texts. A company named only in
the structured participant list cannot be reached at all, and that is where an
Innosuisse implementation partner usually sits.

An empty result therefore means "no project mentions this company by name",
which is a good deal weaker than "this company has taken no federal research
money".

Structured participants start around 2015
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A project from before about 2015 carries no structured partner, and the
partner's UID only appears from about 2022. Older projects can never be
confirmed against a UID, so a UID query leaves them out. Both search paths ask
for the newest projects first, which is where the UIDs are.

``swissco`` reads the organisational fields
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

ARAMIS publishes a named researcher on most projects, with an e-mail address,
up to three telephone numbers and a fax number. ``swissco`` reads the
organisation, the role, the UID and the place, and
:class:`swissco.aramis.Participant` has no field for anything else, so no
output format can emit a person's contact details.
