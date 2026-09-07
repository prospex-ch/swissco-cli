"""The MCP server: the tool surface, the field parity, the caps and the notes.

Tools are called over the real protocol. The SDK ships an in-process client, so
a call goes through argument validation, the tool registry and result
conversion the way a host's call does, without a socket and without a
subprocess.

The clients are hand-rolled stand-ins serving the same recorded fixtures the
rest of the suite uses, installed over the :mod:`swissco.sources` factories.
Those factories are the only place a client is built, which is what makes one
substitution enough to keep the whole server offline.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date

import pytest
from mcp.client import Client
from zefix_parser.lindas import parse_entity_page

from swissco import companies, sources
from swissco_mcp import server

TOOLS = (
    "swissco_lookup",
    "swissco_search",
    "swissco_publications",
    "swissco_events",
    "swissco_tenders",
    "swissco_vendor",
    "swissco_finma",
    "swissco_lei",
    "swissco_research",
)


# -- stand-ins ---------------------------------------------------------------


@dataclass(frozen=True)
class _Raw:
    """What ``ShabClient.fetch`` hands back, down to the field that is read."""

    content: bytes


class _Lindas:
    """A LINDAS client stand-in serving one recorded response.

    ``fetch_by_uids`` is what a lookup calls and ``query`` what a search calls,
    so one stand-in covers both paths. The SPARQL text is kept, because the row
    limit a tool decided on is visible only in the query it sent.
    """

    def __init__(self, page: bytes) -> None:
        self.page = page
        self.queries: list[str] = []
        self.uid_calls: list[list[str]] = []

    def __enter__(self) -> _Lindas:
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def fetch_by_uids(self, uids):
        self.uid_calls.append(list(uids))
        return parse_entity_page(self.page)

    def query(self, text: str) -> bytes:
        self.queries.append(text)
        return self.page


class _Shab:
    """A gazette client stand-in serving one recorded bulk-export page."""

    page_size = 2000
    base_url = "https://example.invalid/api/v1"

    def __init__(self, page: bytes) -> None:
        self.page = page
        self.urls: list[str] = []

    def __enter__(self) -> _Shab:
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def fetch(self, ref) -> _Raw:
        self.urls.append(ref.url)
        return _Raw(self.page)


def _install(monkeypatch, **clients) -> None:
    """Serve *clients* from the source factories they are named after."""
    for name, client in clients.items():
        monkeypatch.setattr(sources, name, lambda _config, client=client, **_: client)


@pytest.fixture
def call():
    """Call one tool over the protocol and hand back the result."""

    def run(name: str, arguments: dict | None = None):
        async def once():
            async with Client(server.mcp) as client:
                return await client.call_tool(name, arguments or {})

        return asyncio.run(once())

    return run


@pytest.fixture
def anonymous(monkeypatch):
    """No credentials in the environment, which is the normal case."""
    for variable in ("ZEFIX_USER", "ZEFIX_PASSWORD", "SWISSCO_INTERVAL"):
        monkeypatch.delenv(variable, raising=False)


# -- the surface -------------------------------------------------------------


class TestTheToolSurface:
    def test_every_tool_is_registered(self):
        async def listed():
            async with Client(server.mcp) as client:
                return (await client.list_tools()).tools

        found = {tool.name: tool for tool in asyncio.run(listed())}
        assert set(found) == set(TOOLS)

    @pytest.mark.parametrize("name", TOOLS)
    def test_every_tool_is_described_and_schematised(self, name):
        async def listed():
            async with Client(server.mcp) as client:
                return (await client.list_tools()).tools

        tool = next(t for t in asyncio.run(listed()) if t.name == name)
        assert tool.description
        assert tool.input_schema["type"] == "object"
        assert set(tool.output_schema["properties"]) == {"rows", "count", "notes"}

    def test_every_tool_declares_itself_read_only(self):
        async def listed():
            async with Client(server.mcp) as client:
                return (await client.list_tools()).tools

        for tool in asyncio.run(listed()):
            assert tool.annotations.read_only_hint
            assert tool.annotations.open_world_hint

    def test_the_event_types_reach_the_publications_description(self):
        async def listed():
            async with Client(server.mcp) as client:
                return (await client.list_tools()).tools

        tool = next(t for t in asyncio.run(listed()) if t.name == "swissco_publications")
        for event_type in server.EVENT_TYPES:
            assert event_type in tool.description

    def test_the_publication_types_reach_the_tenders_description(self):
        async def listed():
            async with Client(server.mcp) as client:
                return (await client.list_tools()).tools

        tool = next(t for t in asyncio.run(listed()) if t.name == "swissco_tenders")
        assert "direct_award" in tool.description

    def test_the_server_carries_the_project_url(self):
        assert server.mcp.website_url == "https://prospex.ch"


# -- field parity ------------------------------------------------------------


class TestLookup:
    def test_the_fields_are_the_ones_entity_row_builds(
        self, call, monkeypatch, anonymous, lindas_lookup
    ):
        _install(monkeypatch, lindas=_Lindas(lindas_lookup))
        result = call("swissco_lookup", {"uid": "CHE-444.420.929"})

        assert not result.is_error
        expected = companies.entity_row(parse_entity_page(lindas_lookup)[0])
        assert result.structured_content["rows"] == [expected]
        assert result.structured_content["count"] == 1

    def test_the_legal_name_is_the_one_in_the_register(
        self, call, monkeypatch, anonymous, lindas_lookup
    ):
        _install(monkeypatch, lindas=_Lindas(lindas_lookup))
        result = call("swissco_lookup", {"uid": "CHE-444.420.929"})
        assert result.structured_content["rows"][0]["legal_name"] == "Baumberger Bau AG"
        assert result.structured_content["rows"][0]["uid"] == "CHE-444.420.929"

    def test_without_credentials_the_notes_say_so(
        self, call, monkeypatch, anonymous, lindas_lookup
    ):
        _install(monkeypatch, lindas=_Lindas(lindas_lookup))
        result = call("swissco_lookup", {"uid": "CHE-444.420.929"})
        assert any("PublicREST" in note for note in result.structured_content["notes"])

    def test_a_bad_uid_is_a_tool_error_carrying_the_reason(self, call, anonymous):
        result = call("swissco_lookup", {"uid": "CHE-444.420.928"})
        assert result.is_error
        assert "valid check digit" in result.content[0].text

    def test_a_company_absent_from_lindas_says_what_that_means(
        self, call, monkeypatch, anonymous
    ):
        class _Empty(_Lindas):
            def fetch_by_uids(self, uids):
                return []

        _install(monkeypatch, lindas=_Empty(b""))
        result = call("swissco_lookup", {"uid": "CHE-444.420.929"})
        assert result.is_error
        assert "active commercial register" in result.content[0].text


# -- the caps ----------------------------------------------------------------


class TestTheLimitCap:
    def test_a_limit_over_the_ceiling_is_lowered_and_noted(
        self, call, monkeypatch, anonymous, lindas_search
    ):
        client = _Lindas(lindas_search)
        _install(monkeypatch, lindas=client)
        result = call("swissco_search", {"term": "usinage", "limit": 500})

        assert f"LIMIT {server.MAX_LIMIT}" in client.queries[0]
        assert any(str(server.MAX_LIMIT) in note for note in result.structured_content["notes"])

    def test_a_limit_within_the_ceiling_is_left_alone(
        self, call, monkeypatch, anonymous, lindas_search
    ):
        client = _Lindas(lindas_search)
        _install(monkeypatch, lindas=client)
        result = call("swissco_search", {"term": "usinage", "limit": 5})

        assert "LIMIT 5" in client.queries[0]
        assert result.structured_content["notes"] == []

    def test_a_limit_below_one_is_refused(self, call, anonymous):
        result = call("swissco_search", {"term": "x", "limit": 0})
        assert result.is_error
        assert "at least 1" in result.content[0].text


class TestTheRangeCaps:
    def test_a_publications_range_is_trimmed_to_a_week(self):
        notes: list[str] = []
        start, end = server._window(
            "2026-01-01",
            "2026-09-04",
            default_days=1,
            max_days=server.MAX_PUBLICATION_DAYS,
            notes=notes,
        )
        assert (end - start).days == server.MAX_PUBLICATION_DAYS
        assert end == date(2026, 9, 4)
        assert any("trimmed" in note for note in notes)

    def test_an_events_range_is_trimmed_to_a_year(self):
        notes: list[str] = []
        start, end = server._window(
            "2020-01-01",
            "2026-09-04",
            default_days=server.MAX_EVENT_DAYS,
            max_days=server.MAX_EVENT_DAYS,
            notes=notes,
        )
        assert (end - start).days == server.MAX_EVENT_DAYS
        assert any("trimmed" in note for note in notes)

    def test_a_range_inside_the_cap_is_left_alone(self):
        notes: list[str] = []
        start, end = server._window(
            "2026-09-01",
            "2026-09-04",
            default_days=1,
            max_days=server.MAX_PUBLICATION_DAYS,
            notes=notes,
        )
        assert (start, end) == (date(2026, 9, 1), date(2026, 9, 4))
        assert notes == []

    def test_the_newest_end_of_the_range_is_the_part_kept(self):
        notes: list[str] = []
        start, end = server._window(
            "2026-01-01", "2026-09-04", default_days=1, max_days=7, notes=notes
        )
        assert start == date(2026, 8, 28)

    def test_an_inverted_range_is_refused(self):
        with pytest.raises(server.ToolError, match="is after"):
            server._window(
                "2026-09-04", "2026-09-01", default_days=1, max_days=7, notes=[]
            )

    def test_a_date_that_is_not_a_date_names_the_argument(self):
        with pytest.raises(server.ToolError, match="since"):
            server._window("last tuesday", "", default_days=1, notes=[])


class TestPublications:
    def test_a_wide_range_is_trimmed_and_the_rows_still_land(
        self, call, monkeypatch, anonymous, shab_list_page
    ):
        _install(monkeypatch, shab=_Shab(shab_list_page))
        result = call(
            "swissco_publications",
            {"since": "2026-01-01", "until": "2026-09-04", "limit": 5},
        )

        payload = result.structured_content
        assert not result.is_error
        assert payload["count"] == 5
        assert any("trimmed" in note for note in payload["notes"])
        assert any("list requests" in note for note in payload["notes"])

    def test_the_rows_are_the_ones_entry_row_builds(
        self, call, monkeypatch, anonymous, shab_list_page
    ):
        _install(monkeypatch, shab=_Shab(shab_list_page))
        result = call("swissco_publications", {"since": "2026-09-03", "until": "2026-09-03"})
        row = result.structured_content["rows"][0]
        assert set(row) == {
            "publication_date", "canton", "sub_rubric", "title",
            "language", "state", "id", "url",
        }
        assert row["publication_date"] == "2026-09-03"

    def test_an_event_type_the_gazette_does_not_publish_is_refused(self, call, anonymous):
        result = call("swissco_publications", {"event_types": ["MERGED_WITH_A_BANK"]})
        assert result.is_error
        assert "is not one of" in result.content[0].text


# -- settings ----------------------------------------------------------------


class TestSettings:
    def test_credentials_come_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("ZEFIX_USER", "u")
        monkeypatch.setenv("ZEFIX_PASSWORD", "p")
        assert server._settings().has_credentials

    def test_no_credentials_is_the_normal_case(self, anonymous):
        assert not server._settings().has_credentials

    def test_the_interval_can_be_raised(self, monkeypatch):
        monkeypatch.setenv("SWISSCO_INTERVAL", "2.5")
        assert server._settings().interval == 2.5

    def test_the_interval_cannot_be_lowered_past_the_floor(self, monkeypatch):
        monkeypatch.setenv("SWISSCO_INTERVAL", "0.01")
        assert server._settings().interval == 0.5

    def test_an_interval_that_is_not_a_number_says_so(self, monkeypatch):
        monkeypatch.setenv("SWISSCO_INTERVAL", "fast")
        with pytest.raises(server.ToolError, match="not a number"):
            server._settings()

    def test_the_state_directory_can_be_moved(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SWISSCO_STATE", str(tmp_path))
        assert server._settings().state_dir == tmp_path

    def test_progress_notes_never_reach_stderr(self, anonymous):
        """A stdio server has no terminal, and stderr is the host's log."""
        assert server._settings().quiet


# -- the result envelope -----------------------------------------------------


class TestTheEnvelope:
    def test_a_date_in_a_row_becomes_a_day(self):
        result = server._result([{"published": date(2026, 9, 4)}], [])
        assert result.rows == [{"published": "2026-09-04"}]

    def test_a_date_nested_in_a_list_becomes_a_day(self):
        result = server._result([{"days": [date(2026, 9, 4)]}], [])
        assert result.rows == [{"days": ["2026-09-04"]}]

    def test_a_date_nested_in_a_dict_becomes_a_day(self):
        result = server._result([{"head": {"on": date(2026, 9, 4)}}], [])
        assert result.rows == [{"head": {"on": "2026-09-04"}}]

    def test_the_count_is_the_row_count(self):
        assert server._result([{"a": 1}, {"a": 2}], []).count == 2

    def test_notes_travel_with_the_rows(self):
        assert server._result([], ["a caveat"]).notes == ["a caveat"]
