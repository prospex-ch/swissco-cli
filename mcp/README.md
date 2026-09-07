# swissco-mcp

<!-- mcp-name: ch.prospex/swissco -->

[![PyPI](https://img.shields.io/pypi/v/swissco-mcp)](https://pypi.org/project/swissco-mcp/)
[![Documentation](https://readthedocs.org/projects/swissco-mcp/badge/?version=latest)](https://swissco-mcp.readthedocs.io/en/latest/)

An MCP server for Swiss company data. Nine tools that look a company up by UID,
search 790,000 of them by name or by statutory purpose, trace what changed in
the commercial register, browse public tenders, check a bank licence, resolve a
UID to an LEI and its group parent, and find federally funded research a company
took part in.

```bash
claude mcp add swissco -- uvx swissco-mcp
```

All data comes from six open-data sources, none of which needs a credential:
[Zefix on LINDAS](https://ld.admin.ch/) for the commercial register, the
[Amtsblattportal](https://amtsblattportal.ch) for the Swiss Official Gazette of
Commerce, [simap.ch](https://www.simap.ch) for public procurement,
[FINMA](https://www.finma.ch) for authorised banks and securities firms,
[GLEIF](https://www.gleif.org) for the Legal Entity Identifier and group
structure, and [ARAMIS](https://www.aramis.admin.ch) for federally funded
research.

Built and maintained by [Prospex](https://prospex.ch), a Swiss B2B sales
intelligence platform.

## Install

The server runs over stdio and needs Python 3.14 or newer.

```bash
uvx swissco-mcp              # run it without installing
pip install swissco-mcp      # or install it
```

Registering it depends on the host. Claude Code takes one command:

```bash
claude mcp add swissco -- uvx swissco-mcp
```

Anything that reads a JSON config takes the equivalent block:

```json
{
  "mcpServers": {
    "swissco": {
      "command": "uvx",
      "args": ["swissco-mcp"]
    }
  }
}
```

## Tools

| Tool | What it answers |
| --- | --- |
| `swissco_lookup` | Everything the register publishes about one company, optionally with its FINMA licence and its LEI |
| `swissco_search` | Companies whose legal name or statutory purpose contains a term |
| `swissco_publications` | Commercial-register publications from the gazette in a date range |
| `swissco_events` | One company's registry events, each confirmed against the publication's own UID |
| `swissco_tenders` | Public-procurement projects published on simap |
| `swissco_vendor` | Whether a company holds a simap vendor profile, and what it says |
| `swissco_finma` | Institutions on FINMA's list of authorised banks and securities firms |
| `swissco_lei` | A company's LEI, the entity that consolidates it, and the entity at the top of that chain |
| `swissco_research` | Federally funded research projects, Innosuisse and SNSF money included |

Every tool returns the same envelope: `rows`, a `count`, and `notes`.

## What the notes carry

Each source covers a slice of Swiss economic life, and a company's absence from
one of them usually means it sits outside that slice. `notes` says which:

- FINMA's list covers banks and securities firms. Insurers, portfolio managers
  and fund management companies hold their authorisations on other lists, so a
  company missing here may still be supervised.
- About 28,000 Swiss entities hold an LEI, against roughly 790,000 in the
  commercial register. An absent LEI is the normal case.
- ARAMIS searches project titles, abstracts and a free-text contractor field,
  and indexes the structured participant list under none of them. A company
  named only as a structured partner cannot be found through it.
- LINDAS publishes the active commercial register. A deleted company can be
  missing from it while its gazette publications remain.

`notes` also reports what a call did with a request it had to trim, and how many
requests a wide date range is about to cost.

## Configuration

Every tool works with no configuration at all. Four environment variables
change what it does:

| Variable | Effect |
| --- | --- |
| `ZEFIX_USER`, `ZEFIX_PASSWORD` | Zefix PublicREST credentials, issued by `zefix@bj.admin.ch`. They add capital, status, former names and corporate relations to `swissco_lookup`, and a name-prefix search to `swissco_search` |
| `SWISSCO_STATE` | Where gazette bodies and the two FINMA files are cached. Defaults to `~/.swissco` |
| `SWISSCO_INTERVAL` | Seconds between requests. It can raise the floor of 0.5s and cannot lower it |

## Rate limiting

Requests are paced at half a second apart, and each source that asks for
something slower gets it: FINMA is paced at a second. These are small public
services run by federal offices, and `SWISSCO_INTERVAL` can raise that floor
but never lower it.

## The command line

The same data is available as a shell command, from the same repository:

```bash
uvx swissco lookup CHE-444.420.929
```

See [swissco on PyPI](https://pypi.org/project/swissco/) and its
[documentation](https://swissco.readthedocs.io).

## Documentation

Full reference for every tool, its arguments and its caveats:
[swissco-mcp.readthedocs.io](https://swissco-mcp.readthedocs.io).

## Licence

MIT. The data belongs to its publishers, and each source's own terms apply;
the [access and terms](https://github.com/prospex-ch/swissco-cli#access-and-terms)
section lists them.
