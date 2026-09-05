"""The shared transport: pacing, backoff, the status policy and the guards.

Every test here injects a clock and a sleep, so the suite proves the waits
without serving them.
"""

from __future__ import annotations

import httpx
import pytest

from swissco import _http


class _Clock:
    """A hand-wound clock, and a record of every sleep asked for."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class _Response:
    def __init__(self, status: int = 200, headers: dict | None = None) -> None:
        self.status_code = status
        self.headers = headers or {}


def client(**kwargs) -> _http.HttpClient:
    clock = kwargs.pop("clock", _Clock())
    instance = _http.HttpClient(
        client=object(), clock=clock, sleep=clock.sleep, **kwargs
    )
    instance.clock = clock
    return instance


class TestPacing:
    def test_the_first_request_does_not_wait(self):
        instance = client(min_interval=1.0)
        instance._throttle()
        assert instance.clock.slept == []

    def test_the_second_request_waits_out_the_interval(self):
        instance = client(min_interval=1.0)
        instance._throttle()
        instance._throttle()
        assert instance.clock.slept == [1.0]

    def test_a_slow_response_does_not_bank_credit_for_a_burst(self):
        instance = client(min_interval=1.0)
        instance._throttle()
        instance.clock.now += 10.0  # a slow response
        instance._throttle()
        instance._throttle()
        # The stall pays for one slot, not for ten.
        assert instance.clock.slept == [1.0]


class TestBackoff:
    def test_it_doubles(self):
        instance = client()
        assert [instance._backoff(n) for n in (1, 2, 3)] == [2.0, 4.0, 8.0]

    def test_it_is_capped(self):
        instance = client()
        assert instance._backoff(20) == _http.BACKOFF_CAP


class TestTheStatusPolicy:
    def test_a_429_is_retryable(self):
        with pytest.raises(_http.RetryableError):
            client().check_response(_Response(429), "https://x.test")

    def test_a_500_is_retryable(self):
        with pytest.raises(_http.RetryableError):
            client().check_response(_Response(503), "https://x.test")

    def test_a_404_is_permanent(self):
        with pytest.raises(_http.HttpError) as caught:
            client().check_response(_Response(404), "https://x.test")
        assert not isinstance(caught.value, _http.RetryableError)

    def test_a_200_passes(self):
        assert client().check_response(_Response(200), "https://x.test") is None

    def test_a_retry_after_the_user_would_wait_through_is_honoured(self):
        with pytest.raises(_http.RetryableError) as caught:
            client().check_response(_Response(429, {"Retry-After": "5"}), "https://x.test")
        assert caught.value.retry_after == 5.0

    def test_a_retry_after_too_long_to_sit_through_fails_instead(self):
        # A daemon can sleep five minutes. A person at a prompt should be told.
        with pytest.raises(_http.HttpError, match="rate limited") as caught:
            client().check_response(_Response(429, {"Retry-After": "600"}), "https://x.test")
        assert not isinstance(caught.value, _http.RetryableError)


class TestRetryAfter:
    def test_a_number_of_seconds(self):
        assert _http.parse_retry_after({"Retry-After": "12"}) == 12.0

    def test_an_http_date(self):
        assert _http.parse_retry_after(
            {"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}
        ) is not None

    def test_a_header_that_is_not_there(self):
        assert _http.parse_retry_after({}) is None

    def test_a_header_that_makes_no_sense(self):
        assert _http.parse_retry_after({"Retry-After": "soon"}) is None

    def test_the_header_name_is_matched_either_way_round(self):
        assert _http.parse_retry_after({"retry-after": "3"}) == 3.0


class TestTheGuards:
    def test_https_is_required(self):
        with pytest.raises(ValueError, match="non-https"):
            client().check_url("http://example.test/x")

    def test_an_empty_allowlist_permits_any_https_host(self):
        assert client().check_url("https://example.test/x")

    def test_an_allowlist_is_enforced(self):
        instance = client()
        instance.allowed_hosts = frozenset({"a.test"})
        with pytest.raises(ValueError, match="refusing host"):
            instance.check_url("https://b.test/x")

    def test_a_disallowed_prefix_is_refused(self):
        instance = client()
        instance.disallowed_prefixes = ("/private",)
        with pytest.raises(ValueError, match="robots.txt"):
            instance.check_url("https://a.test/private/thing")


class TestRetrying:
    def test_it_gives_up_after_the_budget_and_says_so(self):
        instance = client(max_retries=3)
        attempts = []

        def send():
            attempts.append(1)
            raise _http.RetryableError("still 503")

        with pytest.raises(_http.HttpError, match="gave up"):
            instance._with_retries("https://a.test/x", send)
        assert len(attempts) == 3

    def test_a_permanent_failure_is_not_retried(self):
        instance = client(max_retries=3)
        attempts = []

        def send():
            attempts.append(1)
            raise _http.HttpError("404")

        with pytest.raises(_http.HttpError):
            instance._with_retries("https://a.test/x", send)
        assert len(attempts) == 1

    def test_a_body_over_the_ceiling_is_never_retried(self):
        instance = client(max_retries=3)
        attempts = []

        def send():
            attempts.append(1)
            raise _http.ResponseTooLarge("too big")

        with pytest.raises(_http.ResponseTooLarge):
            instance._with_retries("https://a.test/x", send)
        assert len(attempts) == 1

    def test_a_transport_error_is_retried(self):
        instance = client(max_retries=2)
        attempts = []

        def send():
            attempts.append(1)
            if len(attempts) == 1:
                raise httpx.ConnectError("no route")
            return "ok"

        assert instance._with_retries("https://a.test/x", send) == "ok"

    def test_the_user_is_told_a_retry_is_happening(self):
        notes: list[str] = []
        instance = client(max_retries=2, on_retry=notes.append)

        def send():
            raise _http.RetryableError("503")

        with pytest.raises(_http.HttpError):
            instance._with_retries("https://a.test/x", send)
        assert notes and "retrying" in notes[0]

    def test_a_url_off_the_allowlist_fails_before_any_attempt(self):
        instance = client()
        instance.allowed_hosts = frozenset({"a.test"})
        attempts = []
        with pytest.raises(ValueError):
            instance._with_retries("https://b.test/x", lambda: attempts.append(1))
        assert attempts == []
