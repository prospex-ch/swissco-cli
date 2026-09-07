MCP server
==========

The same six sources are available as an MCP server, from the same repository.
Nine tools, one per command except ``watch``.

.. code-block:: console

   $ claude mcp add swissco -- uvx swissco-mcp

Every tool returns ``rows``, a ``count`` and ``notes``. The rows are the dicts
``swissco --format json`` prints, so a field carries the same name and the same
value in both surfaces. The notes carry what each source covers, which is what
turns an empty result into an answer: FINMA's list omits insurers and portfolio
managers, and about 28,000 Swiss entities hold an LEI against roughly 790,000
in the register.

The tools add a few things over the command line. Results are capped at 100
rows, and at a week of the gazette for ``swissco_publications``. Progress and
caveats come back in ``notes``. ``SWISSCO_INTERVAL``, ``SWISSCO_STATE`` and the
two Zefix credentials are read from the environment.

It ships as the PyPI package `swissco-mcp <https://pypi.org/project/swissco-mcp/>`_
and the npm package of the same name, and is registered as ``ch.prospex/swissco``.

Full reference for every tool, its arguments and its caveats:
`swissco-mcp.readthedocs.io <https://swissco-mcp.readthedocs.io>`_.
