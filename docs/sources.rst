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


simap
-----

Swiss public procurement. The read API at ``www.simap.ch/api`` answers
unauthenticated on project search, publication detail, the vendor directory,
procurement offices and institutions. The site's ``robots.txt`` disallows the
single-page app's ``/de/project-detail`` and ``/fr/project-detail`` routes; it
says nothing about ``/api``, which is where every request here goes. ``swissco``
refuses those two prefixes outright rather than relying on never building one.

Pagination is a cursor, not an offset: each page carries a ``lastItem`` that is
handed back to fetch the next. That is a happier arrangement than the gazette's
— there is no ceiling to run into, so a wide range costs pages rather than
failing. ``swissco`` stops when the cursor stops moving, which is also what
protects it from a service that keeps returning the same page.

There is no UID-indexed endpoint
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is the constraint that shapes both commands, and it is worth knowing even
if you never run ``swissco``.

The vendor *directory* publishes a ``uidNo`` on every row, so a company can be
confirmed there exactly. The vendor named on an *award* cannot: that record
carries a ``vendorId`` and a free-text name typed by a procurement office, and
nothing else. The directory holds both an "Egli Gartenbau AG Sursee" and an
"Egli Gartenbau AG Uster" — two unrelated companies, different cantons — and no
name comparison distinguishes them reliably.

So ``swissco tenders`` browses projects and ``swissco vendor`` confirms a
directory profile, and neither claims to say what a company has won. Building
that from names would produce a plausible answer that is sometimes about a
different company, which is worse than not answering.

The archive is not wired up
~~~~~~~~~~~~~~~~~~~~~~~~~~~

``archiv.simap.ch`` holds the pre-relaunch platform, roughly 2008-06 to
2024-06, behind a POST search and an XML detail document. ``swissco`` does not
read it yet. When it does, note that the archive's supplier UID field does not
exist before 2023, so most of that history will never be UID-confirmable.

FINMA
-----

Two files, both static downloads, neither needing a credential: ``beh.xlsx``,
the authorised banks and securities firms, and ``uid.csv``, a separate
``(name, city, authorisation type) -> UID`` crosswalk. The ``?sc_lang=en``
parameter is not cosmetic — it fixes the column headers the parser matches on.

**Banks and securities firms only.** FINMA publishes two dozen further lists —
insurers, portfolio managers, fund management companies, market
infrastructures, self-regulatory organisations — and ``swissco`` reads none of
them. The reason is that this workbook's parser finds its columns by header
name and checks itself against FINMA's own declared total, so a layout change
stops it loudly; the other lists are laid out such that the same change shifts
a value into the wrong column and reports success. A company absent from
``swissco finma`` is therefore not "unlicensed" — it is "not a bank or
securities firm on this list", which is a much smaller claim.

FINMA republishes both files rather than versioning them, so ``swissco`` caches
them for a week under the state directory and re-downloads after that.
``--refresh`` ignores the cache. A download that fails while a stale copy
exists falls back to that copy and says how old it is, because an answer whose
age is visible beats no answer.

Being a good citizen
--------------------

These are small public services run by federal offices, and a tool that
hammers them is a tool that gets blocked for everybody.

``swissco`` sends at most one request every 0.5 seconds, backs off
exponentially over four attempts, and identifies itself with a ``User-Agent``
carrying this repository's URL so an operator reading their logs knows what it
is. ``--interval`` raises that floor and cannot lower it.
