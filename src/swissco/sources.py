"""Constructing the three upstream clients, all with the same politeness.

Nothing here talks to a network by itself; it hands back a configured client
from ``zefix-parser`` or ``shab-parser``. The point of the module is that every
client is built in exactly one place, so the rate limit, the retry budget and
the User-Agent cannot drift apart between commands.
"""

from __future__ import annotations

from shab_parser.client import ShabClient
from zefix_parser.client import LindasClient, ZefixRestClient

from .config import MAX_RETRIES, USER_AGENT, Config


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
