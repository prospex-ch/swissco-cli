"""The TTL cache the FINMA files sit behind.

Its whole job is to be unremarkable: serve a fresh copy, re-fetch a stale one,
survive a sidecar that has been damaged, and fall back to an old copy rather
than to nothing when the download fails.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from swissco import _cache

DAY = timedelta(days=1)
WEEK = timedelta(days=7)


@pytest.fixture
def path(tmp_path):
    return tmp_path / "finma" / "beh.xlsx"


class TestReadingAndWriting:
    def test_a_fresh_copy_is_served(self, path):
        _cache.write(path, b"content", url="https://a.test/f")
        assert _cache.read(path, max_age=WEEK) == b"content"

    def test_a_missing_file_is_simply_absent(self, path):
        assert _cache.read(path, max_age=WEEK) is None

    def test_a_stale_copy_is_not_served(self, path):
        _cache.write(path, b"content")
        _age(path, days=9)
        assert _cache.read(path, max_age=WEEK) is None

    def test_the_write_is_atomic_and_leaves_no_temporary_behind(self, path):
        _cache.write(path, b"content")
        leftovers = [p.name for p in path.parent.iterdir() if p.name.endswith(".tmp")]
        assert leftovers == []

    def test_the_sidecar_records_where_the_bytes_came_from(self, path):
        _cache.write(path, b"content", url="https://a.test/f")
        meta = json.loads((path.parent / "beh.xlsx.meta.json").read_text())
        assert meta["url"] == "https://a.test/f"
        assert meta["bytes"] == 7

    def test_writing_twice_replaces_the_content(self, path):
        _cache.write(path, b"old")
        _cache.write(path, b"new")
        assert _cache.read(path, max_age=WEEK) == b"new"


class TestADamagedSidecar:
    def test_a_corrupt_sidecar_means_stale_rather_than_an_exception(self, path):
        _cache.write(path, b"content")
        (path.parent / "beh.xlsx.meta.json").write_text("{ not json")
        assert _cache.read(path, max_age=WEEK) is None
        assert _cache.fetched_at(path) is None

    def test_a_missing_sidecar_means_stale(self, path):
        _cache.write(path, b"content")
        (path.parent / "beh.xlsx.meta.json").unlink()
        assert _cache.read(path, max_age=WEEK) is None

    def test_a_sidecar_without_a_timestamp_means_stale(self, path):
        _cache.write(path, b"content")
        (path.parent / "beh.xlsx.meta.json").write_text('{"url": "x"}')
        assert _cache.read(path, max_age=WEEK) is None


class TestDownloading:
    def test_a_fresh_copy_is_served_without_fetching(self, path):
        _cache.write(path, b"cached")
        calls = []

        def fetch(url):
            calls.append(url)
            return b"fetched"

        assert _cache.download("https://a.test/f", path, fetch=fetch) == b"cached"
        assert calls == []

    def test_a_stale_copy_triggers_a_fetch(self, path):
        _cache.write(path, b"cached")
        _age(path, days=9)
        got = _cache.download("https://a.test/f", path, fetch=lambda url: b"fetched")
        assert got == b"fetched"

    def test_use_cache_false_always_fetches(self, path):
        _cache.write(path, b"cached")
        got = _cache.download(
            "https://a.test/f", path, fetch=lambda url: b"fetched", use_cache=False
        )
        assert got == b"fetched"

    def test_nothing_is_written_until_the_caller_says_so(self, path):
        _cache.download("https://a.test/f", path, fetch=lambda url: b"fetched")
        # download() hands back bytes; the caller writes them once they parse.
        assert not path.exists()

    def test_a_failed_download_falls_back_to_a_stale_copy(self, path):
        _cache.write(path, b"last good")
        _age(path, days=30)

        def fetch(url):
            raise RuntimeError("finma.ch is down")

        notes = []
        got = _cache.download(
            "https://a.test/f", path, fetch=fetch, on_note=notes.append
        )
        assert got == b"last good"
        assert notes and "download failed" in notes[0]

    def test_a_failed_download_with_no_copy_at_all_raises(self, path):
        def fetch(url):
            raise RuntimeError("finma.ch is down")

        with pytest.raises(RuntimeError):
            _cache.download("https://a.test/f", path, fetch=fetch)

    def test_serving_from_the_cache_says_how_old_it_is(self, path):
        _cache.write(path, b"cached")
        notes = []
        _cache.download("https://a.test/f", path, fetch=lambda url: b"x", on_note=notes.append)
        assert notes and "cached copy from" in notes[0]


def _age(path, *, days: int) -> None:
    """Backdate the sidecar, so the copy reads as older than it is."""
    sidecar = path.parent / (path.name + ".meta.json")
    meta = json.loads(sidecar.read_text())
    meta["fetched_at"] = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    sidecar.write_text(json.dumps(meta))
