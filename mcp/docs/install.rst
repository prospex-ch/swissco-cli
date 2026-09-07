Install
=======

The server speaks stdio and needs Python 3.14 or newer.

.. code-block:: console

   $ uvx swissco-mcp              # run it without installing
   $ pip install swissco-mcp      # or install it

Registering it
--------------

Claude Code takes one command:

.. code-block:: console

   $ claude mcp add swissco -- uvx swissco-mcp

Anything that reads a JSON config takes the equivalent block:

.. code-block:: json

   {
     "mcpServers": {
       "swissco": {
         "command": "uvx",
         "args": ["swissco-mcp"]
       }
     }
   }

Credentials go in the same block, under ``env``:

.. code-block:: json

   {
     "mcpServers": {
       "swissco": {
         "command": "uvx",
         "args": ["swissco-mcp"],
         "env": {
           "ZEFIX_USER": "…",
           "ZEFIX_PASSWORD": "…"
         }
       }
     }
   }

Configuration
-------------

Every tool works with nothing set. Four environment variables change what
happens.

.. list-table::
   :widths: 30 70

   * - ``ZEFIX_USER``
     - Zefix PublicREST username, issued by ``zefix@bj.admin.ch``
   * - ``ZEFIX_PASSWORD``
     - The matching password
   * - ``SWISSCO_STATE``
     - Where gazette bodies and the two FINMA files are cached. Defaults to
       ``~/.swissco``
   * - ``SWISSCO_INTERVAL``
     - Seconds between requests. Raises the floor of 0.5s, and cannot lower it

Credentials extend two tools. ``swissco_lookup`` gains ``status``,
``capital_nominal``, ``capital_currency``, ``deletion_date``, ``old_names``,
``branch_offices``, ``head_offices``, ``has_taken_over``,
``was_taken_over_by`` and ``cantonal_excerpt``. ``swissco_search`` gains
``via="rest"``, a name-prefix search. Everything else answers anonymously.

Rate limiting
-------------

Requests are paced half a second apart, and a source that asks for something
slower gets it: FINMA is paced at a second. ``SWISSCO_INTERVAL`` can raise
that floor. Lowering it below 0.5s is refused.

What a call costs
-----------------

Most tools are one request, or one per page of results. Three of them are
heavier, and each one reports what it is about to do in ``notes``.

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Tool
     - Cost
   * - ``swissco_publications``
     - Two list requests per publication state for a day. With
       ``event_types``, one further request per publication in range
   * - ``swissco_events``
     - Two list requests per window across the range, then one per publication
       whose title matches the company name
   * - ``swissco_finma``
     - Two file downloads on a cold cache, then nothing for a day

``swissco_search`` is one request, and LINDAS takes its time over it: a
substring match against 790,000 legal names and purposes runs for twenty
seconds or so. A host with a short tool timeout needs a longer one for that
call.

Caps
----

Three limits apply.

.. list-table::
   :widths: 30 70

   * - ``limit``
     - At most 100 rows on every tool
   * - ``swissco_publications``
     - At most 7 days of the gazette per call
   * - ``swissco_events``
     - At most 365 days of the gazette per call

A trimmed range keeps its newest end and moves its start forward. Whenever a
call trims something, it says so in ``notes``.
