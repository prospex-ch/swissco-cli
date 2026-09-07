Tools
=====

Nine tools. Every one of them returns ``rows``, a ``count`` and ``notes``, and
every one is read-only.

Each source covers a slice of Swiss economic life, and each tool's caveat
section says which slice. A company's absence from one of them usually says
where the company sits.


swissco_lookup
--------------

Everything the commercial register publishes about one company.

.. code-block:: json

   {"uid": "CHE-444.420.929"}

.. list-table::
   :widths: 30 70

   * - ``uid``
     - A Swiss UID in any punctuation: ``CHE-444.420.929``, ``CHE444420929``,
       or a CH-ID
   * - ``finma_licence``
     - Add the FINMA licence type and supervisory category
   * - ``lei``
     - Add the LEI and the entities that consolidate this one

One row: ``legal_name``, ``uid``, ``chid``, ``ehra_id``, ``legal_form_code``,
``legal_form``, ``municipality``, ``canton``, ``address``, ``purpose`` and
``zefix_uri``.

``purpose`` is the statutory purpose: how the company describes what it does,
in its own words, filed with the register.

The UID comes back punctuated. LINDAS stores it bare (``CHE444420929``), and
every other place a person meets it writes ``CHE-444.420.929``.

The check digit is verified before a request is spent, so a mistyped UID fails
immediately with the expected form in the message.

**Caveats.** LINDAS publishes the active commercial register. A company deleted
from it can still have gazette publications, which ``swissco_publications``
reaches. Without credentials the row stops at what LINDAS carries, and the note
says so.

``finma_licence`` adds ``finma_licence``, ``finma_category``, ``finma_city``
and ``finma_flags``, and costs two downloads on a cold cache. ``lei`` adds
``lei``, ``lei_status``, ``direct_parent`` and ``ultimate_parent``, and costs
three requests.


swissco_search
--------------

Companies whose legal name or statutory purpose contains a term.

.. code-block:: json

   {"term": "usinage", "canton": "VD", "limit": 5}

.. list-table::
   :widths: 30 70

   * - ``term``
     - Text to look for in the legal name or the statutory purpose
   * - ``canton``
     - Two-letter code, e.g. ``VD``
   * - ``legal_form``
     - eCH-0097 code: ``0106`` an AG, ``0107`` a GmbH
   * - ``via``
     - ``lindas`` matches a substring; ``rest`` matches a name prefix and needs
       credentials
   * - ``limit``
     - Maximum rows, up to 100

Over LINDAS: ``legal_name``, ``uid``, ``legal_form``, ``municipality``,
``canton`` and ``purpose``. Over PublicREST: ``legal_name``, ``uid``,
``chid``, ``ehra_id``, ``canton`` and ``status``.

Searching the purpose is what makes this worth running. "hydrogen storage"
finds companies whose name mentions neither word, because a company's filed
description of its own business is a different text from its name.

**Caveats.** The two paths answer different questions. LINDAS matches a
substring anywhere in the name or the purpose; PublicREST matches the start of
the name, which is usually what a person means when they type a company name.
``canton`` and ``legal_form`` filter the LINDAS path alone, and a call that
sets them with ``via="rest"`` gets a note saying they were ignored.


swissco_publications
--------------------

Commercial-register publications from the Swiss Official Gazette of Commerce.

.. code-block:: json

   {"since": "2026-09-03", "until": "2026-09-03", "cantons": ["ZH"], "limit": 5}

.. list-table::
   :widths: 30 70

   * - ``since``, ``until``
     - Date bounds, ``YYYY-MM-DD``. Defaults to yesterday and today
   * - ``cantons``
     - Canton codes to keep, e.g. ``["ZH", "ZG"]``
   * - ``sub_rubrics``
     - ``HR01`` registrations, ``HR02`` mutations, ``HR03`` deletions
   * - ``event_types``
     - Keep only publications carrying one of these events
   * - ``query``
     - Text to look for in the title, in any of the four languages
   * - ``limit``
     - Maximum rows, up to 100

Each row: ``publication_date``, ``canton``, ``sub_rubric``, ``title``,
``language``, ``state``, ``id`` and ``url``.

With ``event_types``, each body is fetched and parsed, and the rows carry
``publication_date``, ``canton``, ``sub_rubric``, ``company_name``, ``uid``,
``events``, ``effective_date``, ``state``, ``id`` and ``url``.

**Caveats.** Every filter here runs over the listed publications, because the
anonymous API ignores its own ``cantons``, ``subRubrics`` and ``q`` parameters.
Filtering after the listing narrows what comes back and not what is fetched.

``event_types`` costs one request per publication in range at half a second
each. The note tells you how many that is before the fetching starts.

A range wider than 7 days is trimmed to its newest 7, with a note.


swissco_events
--------------

One company's registry events, each confirmed against the publication's own
UID.

.. code-block:: json

   {"uid": "CHE-444.420.929", "since": "2026-01-01"}

.. list-table::
   :widths: 30 70

   * - ``uid``
     - The company's UID
   * - ``since``, ``until``
     - Date bounds, ``YYYY-MM-DD``. Defaults to the last 365 days
   * - ``limit``
     - Maximum rows, up to 100

Each row: ``publication_date``, ``event_type``, ``effective_date``,
``company_name``, ``uid``, ``canton``, ``sub_rubric``, ``id`` and ``url``,
newest first.

**The UID is confirmed on the body.** The gazette's list page carries a title
and no UID, and every search parameter the API accepts is ignored for an
anonymous caller. So the UID resolves to a legal name, the name selects
candidate publications from the list, and each candidate's body is fetched and
kept only when the body's own UID matches the one asked for. A publication
carrying no UID is dropped.

Two companies can share a name, and the body confirmation is what separates
them.

**Caveats.** The register publishes what changed, so a company that filed
nothing in the range has nothing here. Bodies are cached under the state
directory and keyed by publication id, so an overlapping second call over the
same range costs almost nothing.

A range wider than 365 days is trimmed to its newest 365, with a note.


swissco_tenders
---------------

Public-procurement projects published on simap.

.. code-block:: json

   {"since": "2026-08-01", "cantons": ["ZH"], "pub_types": ["award"]}

.. list-table::
   :widths: 30 70

   * - ``since``, ``until``
     - Date bounds, ``YYYY-MM-DD``. Defaults to the last 7 days
   * - ``cantons``
     - Canton codes to keep
   * - ``pub_types``
     - Publication types to keep, e.g. ``["tender", "award"]``
   * - ``lang``
     - Preferred language for the title and buyer: ``de``, ``fr``, ``it`` or
       ``en``
   * - ``limit``
     - Maximum rows, up to 100

Each row: ``title``, ``project_number``, ``buyer``, ``canton``, ``city``,
``project_type``, ``process_type``, ``publication_date``,
``publication_type``, ``project_id`` and ``publication_id``.

The publication types are ``abandonment``, ``advance_notice``, ``award``,
``competition``, ``direct_award``, ``participant_selection``,
``request_for_information``, ``revocation``, ``selective_offering_phase``,
``study_contract`` and ``tender``.

**Caveats.** The date filters each project's newest publication rather than its
award. The supplier named on an award carries no UID, so this reaches projects
and buyers; ``swissco_vendor`` is the tool for a specific company.


swissco_vendor
--------------

Whether a company holds a simap vendor profile, and what it says.

.. code-block:: json

   {"query": "CHE-409.633.691"}

.. list-table::
   :widths: 30 70

   * - ``query``
     - A UID, which is confirmed exactly, or text to search vendor names for
   * - ``limit``
     - Maximum rows on the text path, up to 100

A text query returns rows of ``name``, ``uid_no``, ``canton``, ``city``,
``postal_code``, ``active``, ``is_bidding_consortium`` and ``vendor_id``.

A UID resolves to a legal name, searches the directory for it, and keeps only
profiles whose own ``uidNo`` matches. The confirmed profile carries ``name``,
``uid_no``, ``additional_name``, ``street``, ``postal_code``, ``city``,
``canton``, ``url``, ``company_size``, ``type_of_services``, ``cpv_codes``,
``bkp_codes``, ``npk_codes``, ``business_purpose``,
``is_bidding_consortium``, ``leading_vendor_name`` and ``vendor_id``.

**Caveats.** A company can bid without holding a directory profile, and a
bidding consortium carries no UID at all. An absent UID means there is no
profile under it, and says nothing about whether the company has bid.


swissco_finma
-------------

Institutions on FINMA's list of authorised banks and securities firms.

.. code-block:: json

   {"category": "3", "limit": 10}

.. list-table::
   :widths: 30 70

   * - ``query``
     - Text to match in the institution's name or city
   * - ``uid``
     - One institution by UID
   * - ``licence_type``
     - ``Bank``, ``Securities firm``, ``Foreign bank branch office``, or
       ``Foreign securities firm branch office``
   * - ``category``
     - Supervisory category, ``1`` to ``5``. ``1`` is the largest
   * - ``limit``
     - Maximum rows, up to 100

Each row: ``name``, ``city``, ``licence_type``, ``supervisory_category``,
``uid``, ``foreign_control``, ``no_securities_firm_activity``,
``non_account_holding_securities_firm`` and ``about_to_cease_operations``.

**Caveats.** This one list covers banks and securities firms. Insurers,
portfolio managers and fund management companies hold their authorisations on
other FINMA lists, so a company absent here may still be supervised. FINMA also
publishes some authorised institutions with no UID, which no UID lookup can
reach.

Both published files are cached for a day under the state directory, so the
first call in a day is the slow one.


swissco_lei
-----------

A company's Legal Entity Identifier and the group it is consolidated into.

.. code-block:: json

   {"uid": "CHE-412.669.376"}

.. list-table::
   :widths: 30 70

   * - ``uid``
     - The company's UID
   * - ``children``
     - List the entities this one consolidates instead of counting them
   * - ``limit``
     - Maximum children, up to 100

One row: ``legal_name``, ``lei``, ``registered_as``, ``jurisdiction``,
``status``, ``registration_status``, ``legal_form``, ``city``, ``country``,
``other_names``, ``bic``, ``initial_registration_date``,
``last_update_date``, ``next_renewal_date``, ``direct_parent``,
``ultimate_parent`` and ``direct_children``.

With ``children``, one row per consolidated entity: ``legal_name``, ``lei``,
``jurisdiction``, ``registered_as``, ``status``, ``city`` and ``country``.

**Caveats.** GLEIF Level 2 records accounting consolidation, so a parent here
is the entity that consolidates this one into its accounts. That parent is
frequently foreign, which is the case for reading it: the Swiss commercial
register carries no entry for a Swiss company's owner abroad.

About 28,000 Swiss entities hold an LEI, against roughly 790,000 in the
commercial register. An absent LEI is the normal case and says nothing about
the company.

A 404 on a relationship is read as "reports no parent".


swissco_research
----------------

Federally funded research projects from ARAMIS, Innosuisse and SNSF money
included.

.. code-block:: json

   {"query": "hydrogen storage", "language": "EN"}

.. list-table::
   :widths: 30 70

   * - ``query``
     - A UID, which is confirmed against each project's participant UID, or
       text to search projects for
   * - ``language``
     - Service language: ``DE``, ``EN``, ``FR`` or ``IT``. Case-sensitive
   * - ``limit``
     - Maximum rows, up to 100

A text query returns rows of ``title``, ``project_number``, ``office``,
``status``, ``start_date``, ``end_date``, ``granted_total_costs``,
``participants`` and ``aramis_id``.

A UID searches ARAMIS for the company's name, then keeps only projects
carrying a participant whose own UID matches, and reports ``role`` and ``uid``
in place of ``participants``.

**Caveats.** ARAMIS searches project titles, abstracts and a free-text
contractor field, and indexes the structured participant list under none of
them. A company named only as a structured partner cannot be found, which is
where Innosuisse implementation partners usually sit. An empty result means no
project mentions the company by name, and is not evidence that the company took
no federal research money.

A structured participant appears in the data from about 2015 and its UID from
about 2022, so the oldest projects are the ones a UID can never confirm.

ARAMIS publishes researchers' names, e-mail addresses and telephone numbers on
a project detail. None of them reaches a tool result.
