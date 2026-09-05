The agent skill
===============

This repository ships a skill for the
`open agent skills ecosystem <https://github.com/vercel-labs/skills>`_, so a
coding agent can run ``swissco`` on your behalf and read the output correctly.

Install
-------

.. code-block:: bash

   npx skills add prospex-ch/swissco-cli

The skill is written once to ``.agents/skills/swissco/`` and symlinked into each
agent's own directory, which covers Claude Code, Cursor, Codex, Cline, Amp and
around twenty others.

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Flag
     - Effect
   * - ``-g``
     - Install for every project instead of the current one.
   * - ``--all``
     - Accept every agent and every skill without a prompt.
   * - ``-l``
     - List what the repository offers and install nothing.
   * - ``--copy``
     - Copy the files instead of symlinking them.

``swissco`` itself is not installed by this. Put it on the path with
``pip install swissco``, or let the agent reach it through ``uvx swissco``.

What it carries
---------------

The skill is a single ``SKILL.md``: the five commands with the flags each one
takes, how to read the three output formats, and four behaviours that produce a
plausible wrong answer if the agent does not know about them.

- A UID missing from LINDAS has left an active-entity dataset, which is not the
  same as a company being struck off.
- The gazette API accepts ``cantons``, ``q`` and ``keywords``, returns 200, and
  ignores them, so filtering happens client-side.
- Any list request whose page offset reaches 10,000 is rejected, which is why
  wide date ranges are split into windows.
- Zefix PublicREST credentials are optional and change what ``lookup`` and
  ``search`` can return.

Without the skill an agent tends to guess flags that do not exist, or trust the
gazette's filter parameters.

Using it once
-------------

To read the instructions into a session without installing anything:

.. code-block:: bash

   npx skills use prospex-ch/swissco-cli@swissco

Managing it
-----------

.. code-block:: bash

   npx skills list
   npx skills update swissco
   npx skills remove swissco
