"""Caching a file that upstream keeps republishing.

``events`` caches SHAB publication bodies with no expiry, and that is right: a
published gazette document never changes, so the id is the whole cache key.

FINMA's two files are the opposite. They live at one URL, they are rewritten
roughly weekly, and nothing in the URL says which week you got. So this is a
second, deliberately separate cache: same atomic-write discipline as
:mod:`swissco.watch`, but keyed by age rather than by id.

Three properties are worth stating, because each is a decision rather than an
accident:

**The sidecar is advisory.** A missing, unreadable or nonsense ``.meta.json``
means "stale", never an exception. The bytes on disk are the cache; the sidecar
only says how old they are.

**The new copy is parsed before the old one is replaced.** ``download`` hands
back bytes and lets the caller parse them; the caller writes to the cache only
after the parse succeeded. A FINMA layout change therefore leaves the last good
copy in place instead of overwriting it with something unreadable.

**A failed download falls back to a stale copy** rather than to nothing, and
says so. An answer whose age is visible beats no answer at all.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

#: How long a cached FINMA file is served before it is fetched again.
DEFAULT_MAX_AGE = timedelta(days=7)


def read(path: Path, *, max_age: timedelta) -> bytes | None:
    """The cached bytes at *path*, or ``None`` if absent or older than *max_age*."""
    if not path.exists():
        return None
    stamp = fetched_at(path)
    if stamp is None:
        return None
    if datetime.now(timezone.utc) - stamp > max_age:
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def write(path: Path, content: bytes, *, url: str = "") -> None:
    """Write *content* to *path* atomically and stamp its sidecar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(content)
    temporary.replace(path)
    meta = {
        "url": url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "bytes": len(content),
    }
    sidecar = _sidecar(path)
    temporary = sidecar.with_name(sidecar.name + ".tmp")
    temporary.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    temporary.replace(sidecar)


def fetched_at(path: Path) -> datetime | None:
    """When *path* was last written, per its sidecar, or ``None``."""
    try:
        meta = json.loads(_sidecar(path).read_text(encoding="utf-8"))
        return datetime.fromisoformat(meta["fetched_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def download(
    url: str,
    path: Path,
    *,
    fetch: Callable[[str], bytes],
    max_age: timedelta = DEFAULT_MAX_AGE,
    use_cache: bool = True,
    on_note: Callable[[str], None] | None = None,
) -> bytes:
    """Serve *url* from *path* when fresh, else fetch it.

    The caller is handed bytes and is expected to call :func:`write` itself once
    it has parsed them successfully. Nothing here writes the cache, because
    nothing here can tell whether what arrived is usable.
    """
    if use_cache:
        cached = read(path, max_age=max_age)
        if cached is not None:
            stamp = fetched_at(path)
            when = stamp.date().isoformat() if stamp else "an earlier run"
            _say(on_note, f"{path.name}: cached copy from {when}")
            return cached
    try:
        return fetch(url)
    except Exception as exc:
        stale = _stale(path)
        if stale is None:
            raise
        stamp = fetched_at(path)
        when = stamp.date().isoformat() if stamp else "an earlier run"
        _say(on_note, f"{path.name}: download failed ({exc}); using the copy from {when}")
        return stale


def _stale(path: Path) -> bytes | None:
    try:
        return path.read_bytes() if path.exists() else None
    except OSError:
        return None


def _sidecar(path: Path) -> Path:
    return path.with_name(path.name + ".meta.json")


def _say(on_note: Callable[[str], None] | None, message: str) -> None:
    if on_note is not None:
        on_note(message)
