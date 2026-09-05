"""One polite HTTP client, shared by the sources this repository fetches itself.

``zefix-parser`` and ``shab-parser`` bring their own clients. simap and FINMA do
not, so this module is the third: a trimmed port of the transport the Prospex
collectors use, keeping the parts that make a request polite and dropping the
parts that only matter to a long-running ingestion process.

Kept, because each one changes what the operator sees:

* an interval floor, so a walk over many pages arrives at a steady rate rather
  than in a burst. A slow response does not bank credit for a catch-up burst:
  the next slot is reserved before the request goes out, not after it returns;
* exponential backoff, capped, so a service that is briefly unwell is not
  hammered while it recovers;
* ``Retry-After``, honoured when the operator sends one -- but only up to
  :data:`MAX_RETRY_AFTER`. A daemon can sleep five minutes; a person waiting at
  a prompt should be told what the service asked for and left to decide;
* a byte ceiling checked *while the body arrives*, so a source that starts
  answering with something enormous is abandoned part-way rather than after it
  has been read into memory;
* an allowlist of hosts, https only, and a refusal of paths the operator's
  ``robots.txt`` disallows. Checked on every URL rather than on the base, so a
  redirect or a hand-built path cannot wander off the documented API surface.

Dropped: the cross-thread lock (nothing here runs concurrently), proxy support,
the linear-backoff mode, and the logging. A retry that no one sees is not a
courtesy to the user, so retries are reported through *on_retry*, which
``sources`` wires to the same stderr channel every other progress note uses.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable
from urllib.parse import urlsplit

import httpx

#: A ``Retry-After`` longer than this is refused rather than slept through.
MAX_RETRY_AFTER = 60.0

#: The longest a single backoff sleep may last.
BACKOFF_CAP = 30.0

BACKOFF_BASE = 2.0


class HttpError(Exception):
    """Any failure that reached the caller rather than being retried away."""


class RetryableError(HttpError):
    """A failure worth trying again: a 429, a 5xx, or a transport hiccup."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ResponseTooLarge(HttpError):
    """The body passed the byte ceiling and was abandoned unread."""


@dataclass(frozen=True)
class RawFetchResponse:
    """One response, kept as bytes so the parser decides how to read it."""

    url: str
    content: bytes
    content_type: str
    http_status: int
    fetched_at: datetime


def parse_retry_after(headers) -> float | None:
    """Seconds from a ``Retry-After`` header, numeric or HTTP-date.

    ``None`` when the header is absent or unreadable, which is the common case:
    neither simap nor FINMA sends one, so backoff rather than the header is what
    actually paces a retry.
    """
    value = headers.get("Retry-After") or headers.get("retry-after")
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            target = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        seconds = (target - datetime.now(timezone.utc)).total_seconds()
    return max(seconds, 0.0)


class HttpClient:
    """A throttled, retrying, host-restricted HTTP client.

    Subclasses set :attr:`allowed_hosts` and, where the operator's
    ``robots.txt`` calls for it, :attr:`disallowed_prefixes`. Both are enforced
    in :meth:`check_url`, which raises :class:`ValueError` -- the CLI already
    maps that to an ``invalid_argument`` error, so a URL that leaves the
    documented surface fails the same way a bad flag does.
    """

    #: Hosts this client may talk to. Empty means "no restriction", which no
    #: subclass in this package uses.
    allowed_hosts: frozenset[str] = frozenset()

    #: Path prefixes the operator's ``robots.txt`` disallows.
    disallowed_prefixes: tuple[str, ...] = ()

    default_headers: dict[str, str] = {}

    def __init__(
        self,
        *,
        min_interval: float = 1.0,
        timeout: float = 30.0,
        user_agent: str = "",
        max_retries: int = 3,
        max_response_bytes: int = 20_000_000,
        on_retry: Callable[[str], None] | None = None,
        client=None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.max_response_bytes = max_response_bytes
        self.on_retry = on_retry
        self._clock = clock
        self._sleep = sleep
        self._next_slot = 0.0
        headers = dict(self.default_headers)
        if user_agent:
            headers["User-Agent"] = user_agent
        self._client = client or httpx.Client(
            timeout=timeout, headers=headers, follow_redirects=True
        )

    # -- politeness ---------------------------------------------------------

    def check_url(self, url: str) -> str:
        """Return *url*, or raise :class:`ValueError` if it is off-limits."""
        parts = urlsplit(url)
        if parts.scheme != "https":
            raise ValueError(f"refusing a non-https URL: {url}")
        host = (parts.hostname or "").lower()
        if self.allowed_hosts and host not in self.allowed_hosts:
            allowed = ", ".join(sorted(self.allowed_hosts))
            raise ValueError(f"refusing host {host!r}; this client may only reach {allowed}")
        for prefix in self.disallowed_prefixes:
            if parts.path.startswith(prefix):
                raise ValueError(f"refusing {parts.path}: disallowed by the operator's robots.txt")
        return url

    def _throttle(self) -> None:
        now = self._clock()
        wait = self._next_slot - now
        if wait > 0:
            self._sleep(wait)
            now = self._next_slot
        self._next_slot = now + self.min_interval

    def _backoff(self, attempt: int) -> float:
        return min(BACKOFF_BASE * (2 ** (attempt - 1)), BACKOFF_CAP)

    def check_response(self, response, url: str) -> None:
        """The status policy: 429 and 5xx retry, every other 4xx is permanent."""
        status = response.status_code
        if status == 429:
            retry_after = parse_retry_after(response.headers)
            if retry_after is not None and retry_after > MAX_RETRY_AFTER:
                raise HttpError(
                    f"{url} is rate limited and asked for {retry_after:.0f}s; "
                    "try again later or raise --interval"
                )
            raise RetryableError(f"{url} answered 429", retry_after=retry_after)
        if status >= 500:
            raise RetryableError(f"{url} answered {status}")
        if status >= 400:
            raise HttpError(f"{url} answered {status}")

    # -- fetching -----------------------------------------------------------

    def get(self, url: str, *, accept: str = "application/json") -> RawFetchResponse:
        """One GET, throttled and retried, with the body size checked as it arrives."""
        return self._with_retries(url, lambda: self._stream("GET", url, accept=accept))

    def post(self, url: str, *, json_body: dict, accept: str = "application/json"):
        """One POST with a JSON body, throttled and retried."""
        return self._with_retries(
            url, lambda: self._stream("POST", url, accept=accept, json_body=json_body)
        )

    def _stream(self, method: str, url: str, *, accept: str, json_body=None) -> RawFetchResponse:
        headers = {"Accept": accept}
        kwargs = {"headers": headers}
        if json_body is not None:
            kwargs["json"] = json_body
        with self._client.stream(method, url, **kwargs) as response:
            declared = response.headers.get("Content-Length")
            if declared and declared.isdigit() and int(declared) > self.max_response_bytes:
                raise ResponseTooLarge(
                    f"{url} declared {int(declared)} bytes, over the "
                    f"{self.max_response_bytes} ceiling"
                )
            self.check_response(response, url)
            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > self.max_response_bytes:
                    raise ResponseTooLarge(
                        f"{url} passed the {self.max_response_bytes} byte ceiling; abandoned"
                    )
                chunks.append(chunk)
            content = b"".join(chunks)
            if not content:
                raise HttpError(f"{url} answered with an empty body")
            return RawFetchResponse(
                url=url,
                content=content,
                content_type=response.headers.get("Content-Type", accept),
                http_status=response.status_code,
                fetched_at=datetime.now(timezone.utc),
            )

    def _with_retries(self, url: str, send: Callable[[], RawFetchResponse]) -> RawFetchResponse:
        self.check_url(url)
        last: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                return send()
            except ResponseTooLarge:
                raise
            except RetryableError as exc:
                last = exc
                wait = exc.retry_after if exc.retry_after is not None else self._backoff(attempt)
            except httpx.HTTPError as exc:
                last = RetryableError(f"{url}: {exc}")
                wait = self._backoff(attempt)
            if attempt == self.max_retries:
                break
            self._note(f"{last} — retrying in {wait:.0f}s ({attempt}/{self.max_retries})")
            self._sleep(wait)
        raise HttpError(f"gave up on {url} after {self.max_retries} attempts: {last}")

    def _note(self, message: str) -> None:
        if self.on_retry is not None:
            self.on_retry(message)

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self.close()
