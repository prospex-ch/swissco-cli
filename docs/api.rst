Python API
==========

``swissco`` is a command-line tool, and its modules are importable when the
command is not the right shape for what you need. Nothing here is stable across
minor versions the way the two libraries underneath it are: for a durable
interface, use `zefix-parser <https://zefix-parser.readthedocs.io>`_ and
`shab-parser <https://shab-parser.readthedocs.io>`_ directly.

Clients
-------

.. automodule:: swissco.sources
   :members:

Configuration
-------------

.. automodule:: swissco.config
   :members:

Companies
---------

.. automodule:: swissco.companies
   :members:

Publications
------------

.. automodule:: swissco.publications
   :members:

Events
------

.. automodule:: swissco.events
   :members:

Watch
-----

.. automodule:: swissco.watch
   :members:

Procurement
-----------

.. automodule:: swissco.simap
   :members:

FINMA
-----

.. automodule:: swissco.finma
   :members:

Rendering
---------

.. automodule:: swissco.render
   :members:

Command line
------------

.. automodule:: swissco.cli
   :members: main, build_parser
