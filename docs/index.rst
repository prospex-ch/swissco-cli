swissco
=======

Swiss company data from the shell. Look a company up by UID, search 800,000 of
them by name or by what they say they do, list gazette publications, or watch a
list of companies for change.

.. code-block:: console

   $ uvx swissco lookup CHE-444.420.929
   legal name       Baumberger Bau AG
   uid              CHE-444.420.929
   municipality     Koppigen
   canton           BE
   purpose          Anbieten von Kleintransporte aller Art.

All data comes from two federal open-data sources:
`Zefix on LINDAS <https://ld.admin.ch/>`_ for the commercial register, and the
`Amtsblattportal <https://amtsblattportal.ch>`_ for the Swiss Official Gazette
of Commerce.

Built and maintained by `Prospex <https://prospex.ch>`_.

.. toctree::
   :maxdepth: 2

   quickstart
   commands
   sources
   api
   changelog
