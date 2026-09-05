"""Constructing the seven upstream clients, all with the same politeness.

Nothing here talks to a network by itself; it hands back a configured client:
from ``zefix-parser`` and ``shab-parser`` for the two register sources, and from
this package for simap, FINMA, GLEIF and ARAMIS, which ship no client of their
own. The point of the module is that every client is built in exactly one place,
so the rate limit, the retry budget and the User-Agent cannot drift apart
between commands.

Importing this module stays cheap. ``swissco.finma`` is imported here, but
``openpyxl`` is imported inside the function that parses a workbook, so a
``lookup`` that never asks for FINMA never pays for a spreadsheet library.
"""

from __future__ import annotations

from shab_parser.client import ShabClient
from zefix_parser.client import LindasClient, ZefixRestClient

from .aramis import MIN_INTERVAL as ARAMIS_MIN_INTERVAL
from .aramis import AramisClient
from .config import MAX_RETRIES, USER_AGENT, Config
from .finma import MIN_INTERVAL as FINMA_MIN_INTERVAL
from .finma import FinmaClient
from .gleif import MIN_INTERVAL as GLEIF_MIN_INTERVAL
from .gleif import GleifClient
from .simap import MIN_INTERVAL as SIMAP_MIN_INTERVAL
from .simap import SimapClient

#: FINMA's two files are hundreds of kilobytes; a megabyte ceiling would be too
#: tight and the 20 MB default too loose to catch a host answering with a page.
MAX_FILE_BYTES = 8_000_000

#: A GLEIF record is a few kilobytes and a children page a few dozen. Four
#: megabytes leaves room for a large group and refuses a host answering with a
#: page instead of a record.
MAX_RECORD_BYTES = 4_000_000


def lindas(config: Config) -> LindasClient:
    """A LINDAS SPARQL client. Needs no credentials, and never has any."""
    return LindasClient(
        min_interval=config.interval,
        max_retries=MAX_RETRIES,
        user_agent=USER_AGENT,
    )


def zefix_rest(config: Config) -> ZefixRestClient:
    """A Zefix PublicREST client carrying whatever credentials were supplied.

    Callers must check :attr:`~swissco.config.Config.has_credentials` first.
    Building this without credentials is legal but every request 401s.
    """
    return ZefixRestClient(
        username=config.username,
        password=config.password,
        min_interval=config.interval,
        max_retries=MAX_RETRIES,
        user_agent=USER_AGENT,
    )


def shab(config: Config, *, page_size: int = 2000) -> ShabClient:
    """A SHAB client for the Amtsblattportal bulk export.

    The default page size is the maximum the operator allows. A day of
    commercial-register publications is roughly a thousand, so one page usually
    covers it and a wide range costs one request per 2,000 publications rather
    than one per 500.
    """
    return ShabClient(
        min_interval=config.interval,
        max_retries=MAX_RETRIES,
        page_size=page_size,
        user_agent=USER_AGENT,
    )


def simap(config: Config, *, on_note=None) -> SimapClient:
    """A simap read-API client. Unauthenticated, and never otherwise.

    simap's own floor is 0.35s and this CLI's is 0.5s, so the CLI's applies:
    where two politeness settings disagree, the slower one wins.
    """
    return SimapClient(
        min_interval=max(config.interval, SIMAP_MIN_INTERVAL),
        max_retries=MAX_RETRIES,
        user_agent=USER_AGENT,
        on_retry=on_note,
    )


def finma(config: Config, *, on_note=None) -> FinmaClient:
    """A FINMA client for the two published files.

    FINMA asks for a slower pace than the CLI's own floor, so unlike every
    other source here this one can raise the interval above what ``--interval``
    was set to. ``--interval`` may still raise it further.
    """
    return FinmaClient(
        min_interval=max(config.interval, FINMA_MIN_INTERVAL),
        max_retries=MAX_RETRIES,
        user_agent=USER_AGENT,
        max_response_bytes=MAX_FILE_BYTES,
        on_retry=on_note,
    )


def gleif(config: Config, *, on_note=None) -> GleifClient:
    """A GLEIF record-API client. Unauthenticated, and never otherwise."""
    return GleifClient(
        min_interval=max(config.interval, GLEIF_MIN_INTERVAL),
        max_retries=MAX_RETRIES,
        user_agent=USER_AGENT,
        max_response_bytes=MAX_RECORD_BYTES,
        on_retry=on_note,
    )


def aramis(config: Config, *, on_note=None) -> AramisClient:
    """An ARAMIS client for the public service.

    The 43 MB bulk export lives on ``datenausgabe.aramis.admin.ch``, which this
    client's allowlist omits. An interactive command cannot reach it, and the
    refusal is a property of the client rather than a convention callers keep.
    """
    return AramisClient(
        min_interval=max(config.interval, ARAMIS_MIN_INTERVAL),
        max_retries=MAX_RETRIES,
        user_agent=USER_AGENT,
        max_response_bytes=MAX_FILE_BYTES,
        on_retry=on_note,
    )
