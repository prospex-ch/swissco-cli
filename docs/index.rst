swissco
=======

Swiss company data from the shell. Look a company up by UID, search 800,000 of
them by name or by legal purpose, list gazette publications, or watch a
list of companies for change.

.. code-block:: console

   $ uvx swissco lookup CHE-444.420.929
   legal name       Baumberger Bau AG
   uid              CHE-444.420.929
   municipality     Koppigen
   canton           BE
   purpose          Anbieten von Kleintransporte aller Art.

All data comes from six open-data sources, and every one of them answers
without a credential: `Zefix on LINDAS <https://ld.admin.ch/>`_ for the
commercial register, the `Amtsblattportal <https://amtsblattportal.ch>`_ for the
Swiss Official Gazette of Commerce, `simap.ch <https://www.simap.ch>`_ for
public procurement, `FINMA <https://www.finma.ch>`_ for authorised banks and
securities firms, `GLEIF <https://www.gleif.org>`_ for the Legal Entity
Identifier and group structure, and
`ARAMIS <https://www.aramis.admin.ch>`_ for federally funded research.

Built and maintained by `Prospex <https://prospex.ch>`_.

.. toctree::
   :maxdepth: 2

   quickstart
   commands
   skill
   mcp
   sources
   api
   changelog
