"""One place builds every client, so the politeness cannot drift apart."""

from __future__ import annotations

from swissco import sources
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

    def test_a_raised_interval_reaches_every_client(self):
        settings = Config(interval=3.0)
        lindas, shab = sources.lindas(settings), sources.shab(settings)
        try:
            assert lindas._min_interval == 3.0
            assert shab.min_interval == 3.0
        finally:
            lindas.close()
            shab.close()


class TestShabPageSize:
    def test_the_default_is_the_operators_maximum(self):
        client = sources.shab(Config())
        try:
            assert client.page_size == 2000
        finally:
            client.close()
