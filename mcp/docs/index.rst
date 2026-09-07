swissco-mcp
===========

An MCP server for Swiss company data. Nine tools that look a company up by UID,
search 790,000 of them by name or by statutory purpose, trace what changed in
the commercial register, browse public tenders, check a bank licence, resolve a
UID to an LEI and its group parent, and find federally funded research a
company took part in.

.. code-block:: console

   $ claude mcp add swissco -- uvx swissco-mcp

All data comes from six open-data sources, and every one of them answers
without a credential: `Zefix on LINDAS <https://ld.admin.ch/>`_ for the
commercial register, the `Amtsblattportal <https://amtsblattportal.ch>`_ for
the Swiss Official Gazette of Commerce, `simap.ch <https://www.simap.ch>`_ for
public procurement, `FINMA <https://www.finma.ch>`_ for authorised banks and
securities firms, `GLEIF <https://www.gleif.org>`_ for the Legal Entity
Identifier and group structure, and
`ARAMIS <https://www.aramis.admin.ch>`_ for federally funded research.

Every tool returns the same envelope:

.. code-block:: json

   {
     "rows": [{"legal_name": "Baumberger Bau AG", "uid": "CHE-444.420.929"}],
     "count": 1,
     "notes": ["LINDAS only. Zefix PublicREST credentials add capital, status, former names and corporate relations."]
   }

``rows`` are the same dicts ``swissco --format json`` prints, so a field carries
the same name in both surfaces. ``notes`` carry what each source covers, which
is what turns an empty result into an answer.

The same data is available as a shell command from the same repository. See
`swissco <https://swissco.readthedocs.io>`_.

Built and maintained by `Prospex <https://prospex.ch>`_.

.. toctree::
   :maxdepth: 2

   install
   tools
   changelog
