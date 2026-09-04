"""Watching a list of companies for change, by fingerprint.

``zefix-parser`` computes a SHA-256 over the canonical JSON of a company's
identity, address and purpose fields. Two fetches of an unchanged company give
the same digest, so a watch is: fetch, compare against last time, write the new
state. No diffing of the whole record, and no dependence on a
modification-date predicate — LINDAS publishes none, which is why a server-side
delta fetch is impossible in the first place.

Absence is not deletion
-----------------------

LINDAS carries active entities. It is not a historical export, and a UID can
leave it for reasons that have nothing to do with the company ending: a
re-registration under a new identifier, a correction, a publication lag. So a
UID that was there and now is not is reported as *no longer in the dataset* and
never as deleted. Saying "deleted" would be a claim this data cannot support,
and the one place a user would most want to trust it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from zefix_parser import RegistryEntity, format_uid, normalize_uid

STATE_FILENAME = "state.json"
STATE_VERSION = 1

#: The fields compared when a fingerprint moves, in the order they are reported.
#: A subset of what the fingerprint covers — these are the ones worth naming to
#: a person, and a change outside them still shows up as a changed digest.
WATCHED_FIELDS = (
    "legal_name",
    "legal_form_name",
    "municipality_name",
    "canton",
    "street_address",
    "postal_code",
    "locality",
    "purpose",
)


@dataclass
class WatchReport:
    """What one watch run found."""

    added: list[dict] = field(default_factory=list)
    changed: list[dict] = field(default_factory=list)
    vanished: list[dict] = field(default_factory=list)
    unchanged: int = 0

    @property
    def has_changes(self) -> bool:
        """Whether anything at all moved, which is what the exit code reports."""
        return bool(self.added or self.changed or self.vanished)

    def rows(self) -> list[dict]:
        """Every finding as flat, render-ready dicts, added first."""
        return [*self.added, *self.changed, *self.vanished]


def read_uids(path: Path) -> list[str]:
    """UIDs from a file, one per line.

    Blank lines and ``#`` comments are skipped, and duplicates collapse while
    keeping first-seen order. Nothing is validated here — an unusable UID is
    reported against its own line by the command, not dropped silently.
    """
    uids: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.split("#", 1)[0].strip()
        if not value:
            continue
        key = normalize_uid(value)
        if key in seen:
            continue
        seen.add(key)
        uids.append(value)
    return uids


def state_path(state_dir: Path) -> Path:
    """Where the state file for *state_dir* lives."""
    return state_dir / STATE_FILENAME


def load_state(state_dir: Path) -> dict[str, dict]:
    """The previous run's records, keyed by normalized UID.

    A missing file is a first run, not an error. A corrupt one is treated the
    same way: the alternative is refusing to run until a user hand-edits JSON,
    and the cost of being wrong is one run reporting everything as added.
    """
    path = state_path(state_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError, OSError):
        return {}
    companies = data.get("companies") if isinstance(data, dict) else None
    if not isinstance(companies, dict):
        return {}
    return {key: value for key, value in companies.items() if isinstance(value, dict)}


def save_state(state_dir: Path, companies: dict[str, dict]) -> Path:
    """Write *companies* as the new state, and return the file written.

    Written to a temporary file and moved into place, so an interrupted run
    leaves the previous state intact rather than a half-written file that the
    next run would read as "everything is new".
    """
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_path(state_dir)
    payload = {
        "version": STATE_VERSION,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "companies": companies,
    }
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def snapshot(entity: RegistryEntity) -> dict:
    """The stored record for one company: its fingerprint and the named fields."""
    record = {"fingerprint": entity.fingerprint}
    for name in WATCHED_FIELDS:
        record[name] = getattr(entity, name, "") or ""
    return record


def diff(
    previous: dict[str, dict],
    current: dict[str, dict],
    *,
    requested: list[str] | None = None,
) -> WatchReport:
    """Compare two generations of state.

    *requested* is the UID list this run actually asked about. Only those can
    be reported as vanished: a UID in the previous state that was not asked
    about this time has not disappeared from the dataset, it was taken off the
    watch list.
    """
    asked = {normalize_uid(uid) for uid in requested} if requested is not None else None
    report = WatchReport()

    for key, record in current.items():
        before = previous.get(key)
        if before is None:
            report.added.append(
                {
                    "uid": format_uid(key),
                    "status": "added",
                    "legal_name": record.get("legal_name", ""),
                    "changes": "",
                }
            )
            continue
        if before.get("fingerprint") == record.get("fingerprint"):
            report.unchanged += 1
            continue
        report.changed.append(
            {
                "uid": format_uid(key),
                "status": "changed",
                "legal_name": record.get("legal_name", ""),
                "changes": ", ".join(changed_fields(before, record)),
            }
        )

    for key, record in previous.items():
        if key in current:
            continue
        if asked is not None and key not in asked:
            continue
        report.vanished.append(
            {
                "uid": format_uid(key),
                "status": "no longer in the dataset",
                "legal_name": record.get("legal_name", ""),
                "changes": "",
            }
        )

    report.added.sort(key=lambda row: row["uid"])
    report.changed.sort(key=lambda row: row["uid"])
    report.vanished.sort(key=lambda row: row["uid"])
    return report


def changed_fields(before: dict, after: dict) -> list[str]:
    """The names of the watched fields that differ, in :data:`WATCHED_FIELDS` order.

    Can come back empty when the fingerprint moved on a field outside the
    watched set. The caller still reports the company as changed — the digest
    is the authority on *whether* something changed, and this list is only the
    part that can be named.
    """
    return [
        name
        for name in WATCHED_FIELDS
        if (before.get(name) or "") != (after.get(name) or "")
    ]
