"""Where the CLI reads its settings from, and the politeness floor it keeps.

Three things live here: credentials (which are optional — every command works
without them), the state directory, and the request pacing. The pacing is not
configurable downward. ``--interval`` may raise the floor and never lower it:
these are two small public services run by federal offices, and a CLI that
lets a user hammer them is a CLI that gets the whole tool blocked.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import __version__

#: A real User-Agent, so an operator reading their logs can find out what this
#: is and who to complain to.
USER_AGENT = f"swissco/{__version__} (+https://github.com/prospex-ch/swissco-cli)"

#: Seconds between requests, below which ``--interval`` cannot go.
MIN_INTERVAL = 0.5

#: Attempts per request, including the first. Both library clients back off
#: exponentially between them.
MAX_RETRIES = 4

DEFAULT_STATE_DIR = Path.home() / ".swissco"


@dataclass(frozen=True)
class Config:
    """Everything the command functions need that is not a command argument."""

    username: str = ""
    password: str = ""
    interval: float = MIN_INTERVAL
    state_dir: Path = DEFAULT_STATE_DIR
    quiet: bool = False

    @property
    def has_credentials(self) -> bool:
        """Whether a Zefix PublicREST call can be attempted at all.

        The REST API rejects anonymous requests with 401, so the commands that
        can use it check this first and fall back to LINDAS rather than
        spending a request on a certain failure.
        """
        return bool(self.username and self.password)


def resolve(args) -> Config:
    """Build a :class:`Config` from parsed arguments and the environment.

    Command-line flags win over environment variables, which win over the
    defaults. ``--interval`` is clamped up to :data:`MIN_INTERVAL`.
    """
    interval = MIN_INTERVAL if args.interval is None else max(MIN_INTERVAL, args.interval)
    state_dir = Path(args.state).expanduser() if args.state else DEFAULT_STATE_DIR
    return Config(
        username=args.user or os.environ.get("ZEFIX_USER", ""),
        password=args.password or os.environ.get("ZEFIX_PASSWORD", ""),
        interval=interval,
        state_dir=state_dir,
        quiet=bool(args.quiet),
    )
