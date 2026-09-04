Quickstart
==========

Install
-------

.. code-block:: bash

   uvx swissco --help          # run it without installing
   pip install swissco         # or install it

Python 3.14 or newer. The two libraries it wraps,
`zefix-parser <https://pypi.org/project/zefix-parser/>`_ and
`shab-parser <https://pypi.org/project/shab-parser/>`_, come with it.

One company
-----------

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

``CHE-444.420.929``, ``CHE444420929`` and the UID buried inside other text all
work. The check digit is verified locally, so a typo is caught before any
request leaves.

Many companies
--------------

``search`` matches the legal name and the statutory purpose: how a company
describes what it does, in its own words, in the register.

.. code-block:: console

   $ swissco search "usinage" --canton VD --limit 5
   LEGAL_NAME                             UID              LEGAL_FORM                                         MUNICIPALITY  CANTON  PURPOSE
   -------------------------------------  ---------------  -------------------------------------------------  ------------  ------  ------------------------------------------------------------
   Atelier roue libre S.A.                CHE-261.821.895  Aktiengesellschaft                                 Penthalaz     VD      La société a pour but l'usinage, la réparation, la révision…
   Cute Cut Sàrl                          CHE-403.577.924  Gesellschaft mit beschränkter Haftung GMBH / SARL  Lausanne      VD      la société a pour but toutes activités, notamment la fabric…
   DecoupART CNC Sàrl                     CHE-342.723.896  Gesellschaft mit beschränkter Haftung GMBH / SARL  Paudex        VD      la société a pour but tous types de travaux dans les domain…
   LAVA Technologies Sàrl en liquidation  CHE-217.431.384  Gesellschaft mit beschränkter Haftung GMBH / SARL  Nyon          VD      la société a pour but: développement de machines d'usinage …
   Pousaz Mécanique SA                    CHE-166.712.190  Aktiengesellschaft                                 Oron          VD      La société a pour but l'exploitation d'un atelier mécanique…

Piping it somewhere
-------------------

.. code-block:: bash

   swissco search "blockchain" --canton ZG --format json | jq -r '.[].legal_name'
   swissco publications --since 2026-08-01 --canton ZH --format csv > zh.csv

``--format`` is the only thing that changes the output. The same command
produces the same bytes in a terminal and in a pipe, so a script that works
interactively works in CI.

A cron job
----------

.. code-block:: bash

   printf 'CHE-444.420.929\nCHE-105.943.826\n' > uids.txt
   swissco watch uids.txt --state ~/.swissco/

``watch`` exits ``10`` when something changed and ``0`` when nothing did:

.. code-block:: text

   0 7 * * * swissco watch ~/uids.txt --quiet --format json > ~/changes.json \
             || mail -s "registry changes" me@example.com < ~/changes.json

Credentials
-----------

Every command works without them.
`Zefix PublicREST <https://www.zefix.admin.ch>`_ credentials, issued on request
by ``zefix@bj.admin.ch``, add capital, status, deletion date, former names and
corporate relations to ``lookup``, and a name-prefix search to ``search``.

.. code-block:: bash

   export ZEFIX_USER=...
   export ZEFIX_PASSWORD=...
   swissco lookup CHE-444.420.929

``--user`` and ``--password`` do the same thing for one invocation.
