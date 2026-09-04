Sources and terms
=================

Three upstream endpoints, with different access rules.


SHAB / Amtsblattportal
----------------------

The Swiss Official Gazette of Commerce, at
`amtsblattportal.ch <https://amtsblattportal.ch>`_. Every commercial-register
act passes through it: incorporations, mutations, deletions.

* The REST API is the channel the operator offers for machine access, described
  as freely accessible for anyone to use and designed for productive use.
* No authentication for ``PUBLISHED`` data.
* No documented rate limit. Page size is capped at 2,000.
* ``robots.txt`` disallows crawling the website UI. It does not reach the API.
* The operator disclaims completeness. Only the signed PDF is legally binding.

Filter parameters are accepted and ignored
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``cantons``, ``subRubrics``, ``q`` and ``keywords`` all return HTTP 200 for an
anonymous caller and change nothing: the same request returns an identical
total with and without each one, verified on 2026-09-04 against a day holding
1,027 publications.

``swissco`` therefore filters client-side, over the ``<meta>`` block the list
page already carries. Do the same in your own code, and treat a filtered total
that matches the unfiltered one as evidence the filter did nothing.

The offset window
~~~~~~~~~~~~~~~~~

Any request whose ``page * size`` reaches 10,000 is rejected with HTTP 400.
Since page size is capped at 2,000, that is five pages. A date range holding
more publications than the window has to be split into shorter ranges, which
is what :func:`swissco.publications.discover` does.


Zefix on LINDAS
---------------

The Swiss commercial register as linked data, at
`ld.admin.ch/query <https://ld.admin.ch/query>`_, published on
`opendata.swiss <https://opendata.swiss/en/dataset/zefix-lindas>`_.

* No credentials. This is the path every ``swissco`` command uses by default.
* Roughly 800,000 active companies with name, identifiers, legal form,
  municipality, canton, address and statutory purpose.
* Commercial-use terms have never been settled. The
  `dataset page <https://opendata.swiss/en/dataset/zefix-lindas>`_ carries what
  applies; check it before redistributing what you pull.
* Active entities only. There is no modification-date predicate, so a
  server-side delta fetch is impossible, and a UID that leaves the dataset has
  not necessarily been deleted from the register.


Zefix PublicREST
----------------

The official REST API at ``zefix.admin.ch/ZefixPublicREST``.

* Credentials are required, issued on request by ``zefix@bj.admin.ch``. An
  anonymous request returns HTTP 401, including for the reference endpoints
  (verified 2026-09-04).
* Adds what LINDAS does not publish: capital, legal status, deletion date,
  former names, branch offices, auditors and merger relations.
* Every ``swissco`` command works without it. Supplying credentials extends
  ``lookup`` and enables ``search --via rest``.


Being a good citizen
--------------------

These are small public services run by federal offices, and a tool that
hammers them is a tool that gets blocked for everybody.

``swissco`` sends at most one request every 0.5 seconds, backs off
exponentially over four attempts, and identifies itself with a ``User-Agent``
carrying this repository's URL so an operator reading their logs knows what it
is. ``--interval`` raises that floor and cannot lower it.
