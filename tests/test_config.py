"""The politeness floor and where settings come from."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import pytest

from swissco import config


def args(**overrides) -> Namespace:
    defaults = {
        "user": "",
        "password": "",
        "interval": None,
        "state": "",
        "quiet": False,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


class TestInterval:
    def test_the_default_is_the_floor(self):
        assert config.resolve(args()).interval == config.MIN_INTERVAL

    def test_it_can_be_raised(self):
        assert config.resolve(args(interval=2.0)).interval == 2.0

    @pytest.mark.parametrize("value", [0.0, 0.1, -5.0])
    def test_it_cannot_be_lowered(self, value):
        """These are small public services; the floor is not negotiable."""
        assert config.resolve(args(interval=value)).interval == config.MIN_INTERVAL


class TestCredentials:
    def test_flags_win_over_the_environment(self, monkeypatch):
        monkeypatch.setenv("ZEFIX_USER", "from-env")
        settings = config.resolve(args(user="from-flag", password="p"))
        assert settings.username == "from-flag"

    def test_the_environment_is_read(self, monkeypatch):
        monkeypatch.setenv("ZEFIX_USER", "u")
        monkeypatch.setenv("ZEFIX_PASSWORD", "p")
        settings = config.resolve(args())
        assert (settings.username, settings.password) == ("u", "p")
        assert settings.has_credentials

    def test_no_credentials_is_the_normal_case(self, monkeypatch):
        monkeypatch.delenv("ZEFIX_USER", raising=False)
        monkeypatch.delenv("ZEFIX_PASSWORD", raising=False)
        assert not config.resolve(args()).has_credentials

    def test_half_a_credential_pair_is_none(self, monkeypatch):
        monkeypatch.delenv("ZEFIX_PASSWORD", raising=False)
        assert not config.resolve(args(user="u")).has_credentials


class TestStateDir:
    def test_the_default_is_under_home(self):
        assert config.resolve(args()).state_dir == config.DEFAULT_STATE_DIR

    def test_a_flag_wins(self, tmp_path):
        assert config.resolve(args(state=str(tmp_path))).state_dir == tmp_path

    def test_a_tilde_is_expanded(self):
        assert config.resolve(args(state="~/elsewhere")).state_dir == (
            Path.home() / "elsewhere"
        )


class TestUserAgent:
    def test_it_names_the_tool_and_where_to_complain(self):
        assert config.USER_AGENT.startswith("swissco/")
        assert "github.com/prospex-ch/swissco-cli" in config.USER_AGENT
