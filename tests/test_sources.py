"""One place builds every client, so the politeness cannot drift apart."""

from __future__ import annotations

import pytest

from swissco import aramis, finma, gleif, simap, sources
from swissco.config import MAX_RETRIES, MIN_INTERVAL, USER_AGENT, Config


class TestPoliteness:
    def test_lindas_carries_the_floor_and_the_user_agent(self):
        client = sources.lindas(Config())
        try:
            assert client._min_interval == MIN_INTERVAL
            assert client._max_retries == MAX_RETRIES
            assert client._client.headers["user-agent"] == USER_AGENT
        finally:
            client.close()

    def test_shab_carries_the_floor_and_the_user_agent(self):
        client = sources.shab(Config())
        try:
            assert client.min_interval == MIN_INTERVAL
            assert client.max_retries == MAX_RETRIES
            assert client._client.headers["user-agent"] == USER_AGENT
        finally:
            client.close()

    def test_zefix_rest_carries_the_floor_and_the_user_agent(self):
        client = sources.zefix_rest(Config(username="u", password="p"))
        try:
            assert client._min_interval == MIN_INTERVAL
            assert client._client.headers["user-agent"] == USER_AGENT
        finally:
            client.close()

    def test_simap_carries_the_floor_and_the_user_agent(self):
        client = sources.simap(Config())
        try:
            # simap's own floor is lower than this CLI's. Where two politeness
            # settings disagree, the slower one wins.
            assert simap.MIN_INTERVAL < MIN_INTERVAL
            assert client.min_interval == MIN_INTERVAL
            assert client.max_retries == MAX_RETRIES
            assert client._client.headers["user-agent"] == USER_AGENT
        finally:
            client.close()

    def test_finma_is_paced_slower_than_the_shared_floor(self):
        client = sources.finma(Config())
        try:
            # The one source that asks for more room than the CLI's own floor.
            assert client.min_interval == finma.MIN_INTERVAL > MIN_INTERVAL
            assert client._client.headers["user-agent"] == USER_AGENT
        finally:
            client.close()

    def test_gleif_carries_the_floor_and_the_user_agent(self):
        client = sources.gleif(Config())
        try:
            assert client.min_interval == gleif.MIN_INTERVAL == MIN_INTERVAL
            assert client.max_retries == MAX_RETRIES
            assert client._client.headers["user-agent"] == USER_AGENT
        finally:
            client.close()

    def test_aramis_carries_the_floor_and_the_user_agent(self):
        client = sources.aramis(Config())
        try:
            assert client.min_interval == aramis.MIN_INTERVAL == MIN_INTERVAL
            assert client.max_retries == MAX_RETRIES
            assert client._client.headers["user-agent"] == USER_AGENT
        finally:
            client.close()

    def test_a_raised_interval_reaches_every_client(self):
        settings = Config(interval=3.0)
        clients = [
            sources.lindas(settings),
            sources.shab(settings),
            sources.simap(settings),
            sources.finma(settings),
            sources.gleif(settings),
            sources.aramis(settings),
        ]
        try:
            lindas, shab, sim, fin, lei, research = clients
            assert lindas._min_interval == 3.0
            assert shab.min_interval == 3.0
            assert sim.min_interval == 3.0
            assert fin.min_interval == 3.0
            assert lei.min_interval == 3.0
            assert research.min_interval == 3.0
        finally:
            for client in clients:
                client.close()

    def test_every_client_this_package_builds_is_restricted_to_its_own_host(self):
        clients = [
            sources.simap(Config()),
            sources.finma(Config()),
            sources.gleif(Config()),
            sources.aramis(Config()),
        ]
        try:
            sim, fin, lei, research = clients
            assert sim.allowed_hosts == frozenset({"www.simap.ch"})
            assert fin.allowed_hosts == frozenset({"www.finma.ch"})
            assert lei.allowed_hosts == frozenset({"api.gleif.org"})
            assert research.allowed_hosts == frozenset({"www.webservice.aramis.admin.ch"})
        finally:
            for client in clients:
                client.close()

    def test_the_aramis_client_cannot_reach_the_43_mb_bulk_export(self):
        """The export host is off the allowlist, so no command can pull it."""
        client = sources.aramis(Config())
        try:
            with pytest.raises(ValueError, match="refusing host"):
                client.check_url("https://datenausgabe.aramis.admin.ch/full_export.json")
        finally:
            client.close()


class TestShabPageSize:
    def test_the_default_is_the_operators_maximum(self):
        client = sources.shab(Config())
        try:
            assert client.page_size == 2000
        finally:
            client.close()
