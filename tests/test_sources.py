"""One place builds every client, so the politeness cannot drift apart."""

from __future__ import annotations

from swissco import finma, simap, sources
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

    def test_a_raised_interval_reaches_every_client(self):
        settings = Config(interval=3.0)
        clients = [
            sources.lindas(settings),
            sources.shab(settings),
            sources.simap(settings),
            sources.finma(settings),
        ]
        try:
            lindas, shab, sim, fin = clients
            assert lindas._min_interval == 3.0
            assert shab.min_interval == 3.0
            assert sim.min_interval == 3.0
            assert fin.min_interval == 3.0
        finally:
            for client in clients:
                client.close()

    def test_the_new_clients_are_restricted_to_their_own_host(self):
        sim, fin = sources.simap(Config()), sources.finma(Config())
        try:
            assert sim.allowed_hosts == frozenset({"www.simap.ch"})
            assert fin.allowed_hosts == frozenset({"www.finma.ch"})
        finally:
            sim.close()
            fin.close()


class TestShabPageSize:
    def test_the_default_is_the_operators_maximum(self):
        client = sources.shab(Config())
        try:
            assert client.page_size == 2000
        finally:
            client.close()
