"""The bundled agent skill, checked against the Agent Skills specification.

The spec lives at <https://agentskills.io/specification>. It is the contract
that lets one ``SKILL.md`` teach Claude Code, Cursor, Codex and the rest of the
ecosystem the same thing, so a change that quietly breaks it would only show up
in somebody else's agent. The rules are cheap to assert, so they are asserted
here rather than trusted.

No YAML library: the suite has no third-party dependency and the frontmatter
this file parses is a deliberately small subset (scalars, folded scalars, and
one level of nesting), which is all the spec allows.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = ROOT / ".agents" / "skills" / "swissco"
SKILL_MD = SKILL_DIR / "SKILL.md"

NAME_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-")
KNOWN_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}


def split_frontmatter(text: str) -> tuple[str, str]:
    """The YAML block between the two ``---`` fences, and the body after it."""
    assert text.startswith("---\n"), "SKILL.md must open with a --- fence"
    end = text.index("\n---\n", 3)
    return text[4:end], text[end + len("\n---\n") :]


def parse(block: str) -> dict[str, object]:
    """The subset of YAML the spec permits in a SKILL.md frontmatter."""
    fields: dict[str, object] = {}
    key: str | None = None
    folded: list[str] = []
    nested: dict[str, str] | None = None

    def flush() -> None:
        if key is not None and folded:
            fields[key] = " ".join(folded)

    for line in block.split("\n"):
        if not line.strip():
            continue
        if line.startswith("  "):  # a continuation, folded or nested
            if nested is not None:
                sub, _, value = line.strip().partition(":")
                nested[sub] = value.strip().strip('"')
            else:
                folded.append(line.strip())
            continue
        flush()
        folded, nested = [], None
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if value == ">" or value == "|":
            continue
        if value == "":
            nested = {}
            fields[key] = nested
            continue
        fields[key] = value.strip('"')
    flush()
    return fields


@pytest.fixture(scope="module")
def frontmatter() -> dict[str, object]:
    return parse(split_frontmatter(SKILL_MD.read_text(encoding="utf-8"))[0])


@pytest.fixture(scope="module")
def body() -> str:
    return split_frontmatter(SKILL_MD.read_text(encoding="utf-8"))[1]


class TestLayout:
    def test_the_skill_lives_where_every_client_looks(self):
        assert SKILL_MD.is_file()

    def test_claude_code_reaches_the_same_file(self):
        """``.claude/skills/`` is a symlink, so there is one copy to maintain."""
        link = ROOT / ".claude" / "skills" / "swissco"
        assert link.is_symlink()
        assert link.resolve() == SKILL_DIR


class TestFrontmatter:
    def test_declares_only_fields_the_spec_defines(self, frontmatter):
        assert set(frontmatter) <= KNOWN_FIELDS

    def test_carries_both_required_fields(self, frontmatter):
        assert frontmatter.keys() >= {"name", "description"}

    def test_name_matches_the_parent_directory(self, frontmatter):
        assert frontmatter["name"] == SKILL_DIR.name

    @pytest.mark.parametrize(
        "rule",
        [
            lambda n: 1 <= len(n) <= 64,
            lambda n: set(n) <= NAME_CHARS,
            lambda n: not n.startswith("-") and not n.endswith("-"),
            lambda n: "--" not in n,
        ],
    )
    def test_name_is_a_valid_slug(self, frontmatter, rule):
        assert rule(frontmatter["name"])

    def test_description_fits_the_catalogue(self, frontmatter):
        assert 1 <= len(frontmatter["description"]) <= 1024

    def test_description_says_when_to_reach_for_the_skill(self, frontmatter):
        assert "Triggers:" in frontmatter["description"]

    def test_compatibility_fits(self, frontmatter):
        assert len(frontmatter["compatibility"]) <= 500

    def test_metadata_maps_strings_to_strings(self, frontmatter):
        assert all(
            isinstance(k, str) and isinstance(v, str)
            for k, v in frontmatter["metadata"].items()
        )

    def test_the_declared_version_is_the_one_being_shipped(self, frontmatter):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert f'version = "{frontmatter["metadata"]["version"]}"' in pyproject

    def test_the_declared_licence_is_the_one_being_shipped(self, frontmatter):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert f'license = "{frontmatter["license"]}"' in pyproject


class TestBody:
    def test_stays_inside_the_recommended_length(self, body):
        """The spec asks for under 500 lines, loaded whole on activation."""
        assert len(body.splitlines()) < 500

    def test_every_relative_reference_resolves(self, body):
        import re

        for target in re.findall(r"\]\((?!https?:|#|mailto:)([^)]+)\)", body):
            assert (SKILL_DIR / target).exists(), target
