# swissco-mcp

<!-- mcp-name: ch.prospex/swissco -->

An MCP server for Swiss company data. Nine tools that look a company up by UID,
search 790,000 of them by name or by statutory purpose, trace what changed in
the commercial register, browse public tenders, check a bank licence, resolve a
UID to an LEI and its group parent, and find federally funded research a company
took part in.

```bash
npx swissco-mcp
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

## What this package is

This package is a launcher. The server itself is the Python package
[`swissco-mcp`](https://pypi.org/project/swissco-mcp/), and this hands stdio
straight through to it, so an npm-shaped host can start it with `npx`.

It needs [uv](https://docs.astral.sh/uv/) on the path:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

To skip the launcher entirely, install the Python package and run `swissco-mcp`:

```bash
pip install swissco-mcp
```

## Register it

Claude Code takes one command:

```bash
claude mcp add swissco -- npx swissco-mcp
```

Anything that reads a JSON config takes the equivalent block:

```json
{
  "mcpServers": {
    "swissco": {
      "command": "npx",
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

Every tool returns `rows`, a `count`, and `notes`. The notes carry what each
source covers, which is what turns an empty result into an answer: FINMA's list
omits insurers and portfolio managers, and about 28,000 Swiss entities hold an
LEI against roughly 790,000 in the register.

## Configuration

Every tool works with nothing set.

| Variable | Effect |
| --- | --- |
| `ZEFIX_USER`, `ZEFIX_PASSWORD` | Zefix PublicREST credentials, issued by `zefix@bj.admin.ch`. They add capital, status, former names and corporate relations to `swissco_lookup`, and a name-prefix search to `swissco_search` |
| `SWISSCO_STATE` | Where gazette bodies and the two FINMA files are cached. Defaults to `~/.swissco` |
| `SWISSCO_INTERVAL` | Seconds between requests. It can raise the floor of 0.5s and cannot lower it |

## Documentation

Full reference for every tool, its arguments and its caveats:
[swissco-mcp.readthedocs.io](https://swissco-mcp.readthedocs.io).

The same data is available as a shell command:
[swissco](https://pypi.org/project/swissco/).

## Licence

MIT. The data belongs to its publishers, and each source's own terms apply;
the [access and terms](https://github.com/prospex-ch/swissco-cli#access-and-terms)
section lists them.
