# swissco

[![PyPI](https://img.shields.io/pypi/v/swissco)](https://pypi.org/project/swissco/)
[![Documentation](https://readthedocs.org/projects/swissco/badge/?version=latest)](https://swissco.readthedocs.io/en/latest/)

Swiss company data from the shell. Look a company up by UID, search 790,000 of them
by name or by legal purpose, list gazette publications, browse public
tenders, check a bank licence, or watch a list of companies for change.

```bash
uvx swissco lookup CHE-444.420.929
```

All data comes from six open-data sources, none of which needs a credential:
[Zefix on LINDAS](https://ld.admin.ch/) for the commercial register, the
[Amtsblattportal](https://amtsblattportal.ch) for the Swiss Official Gazette of
Commerce, [simap.ch](https://www.simap.ch) for public procurement,
[FINMA](https://www.finma.ch) for authorised banks and securities firms,
[GLEIF](https://www.gleif.org) for the Legal Entity Identifier and group
structure, and [ARAMIS](https://www.aramis.admin.ch) for federally funded
research.

Built and maintained by [Prospex](https://prospex.ch), a Swiss B2B sales intelligence platform.

## Install

```bash
uvx swissco --help          # run it without installing
pip install swissco         # or install it
```

Python 3.14 or newer.

### Docker

```bash
docker run --rm prospexch/swissco search "Nestlé" --limit 5
```

The image runs as an unprivileged user and keeps its state — `watch`'s seen-ids
and the cached FINMA files — in `/home/swissco/.swissco`. Mount a volume there
for anything that needs to remember what it saw last time:

```bash
docker run --rm -v swissco-state:/home/swissco/.swissco \
  prospexch/swissco watch --uid CHE-105.909.036
```

Zefix credentials, which every command works without, are passed through as
environment variables:

```bash
docker run --rm -e ZEFIX_USER -e ZEFIX_PASSWORD prospexch/swissco lookup CHE-105.909.036
```

## Commands

Every command takes `--format table|json|csv`, `--limit` and `--quiet`.

### `swissco lookup`

Everything the register publishes about one company.

```console
$ swissco lookup CHE-444.420.929
legal name       Baumberger Bau AG
uid              CHE-444.420.929
chid             CH-036.9.103.786-9
ehra id          1702823
legal form code  0151
legal form       Schweizerische Zweigniederlassung im Handelsregister eingetragen
municipality     Koppigen
canton           BE
address          Hauptstrasse 6, 3425 Koppigen
purpose          Anbieten von Kleintransporte aller Art.
zefix uri        https://register.ld.admin.ch/zefix/company/1702823
```

Accepts `CHE-444.420.929`, `CHE444420929`, or the UID buried in other text.

### `swissco search`

Companies by legal name **or by statutory purpose**: how a company describes what it
does, in its own words, in the register.

```console
$ swissco search "usinage" --canton VD --limit 5
LEGAL_NAME                             UID              LEGAL_FORM                                         MUNICIPALITY  CANTON  PURPOSE
-------------------------------------  ---------------  -------------------------------------------------  ------------  ------  ------------------------------------------------------------
Atelier roue libre S.A.                CHE-261.821.895  Aktiengesellschaft                                 Penthalaz     VD      La société a pour but l'usinage, la réparation, la révision…
Cute Cut Sàrl                          CHE-403.577.924  Gesellschaft mit beschränkter Haftung GMBH / SARL  Lausanne      VD      la société a pour but toutes activités, notamment la fabric…
DecoupART CNC Sàrl                     CHE-342.723.896  Gesellschaft mit beschränkter Haftung GMBH / SARL  Paudex        VD      la société a pour but tous types de travaux dans les domain…
LAVA Technologies Sàrl en liquidation  CHE-217.431.384  Gesellschaft mit beschränkter Haftung GMBH / SARL  Nyon          VD      la société a pour but: développement de machines d'usinage …
Pousaz Mécanique SA                    CHE-166.712.190  Aktiengesellschaft                                 Oron          VD      La société a pour but l'exploitation d'un atelier mécanique…
```

`--canton` takes a two-letter code, `--legal-form` an eCH-0097 code (`0106` is an AG,
`0107` a GmbH).

### `swissco publications`

Commercial-register publications from the gazette, in a date range.

```bash
swissco publications --canton ZH --since 2026-08-01
swissco publications --canton ZH --since 2026-08-01 --type CAPITAL_INCREASED
```

Without `--type`, only the list pages are read: one request per 2,000 publications.
With `--type`, each surviving publication's body is fetched and classified into the
[eleven event types](https://shab-parser.readthedocs.io/en/latest/events.html)
`shab-parser` recognises, so narrow the range and the canton first.

Ranges past about ten days are split into windows automatically. The API rejects any
request whose page offset reaches 10,000, and the gazette publishes around a thousand
commercial-register entries a day.

### `swissco events`

One company's registry history.

```bash
swissco events CHE-444.420.929 --since 2024-01-01
```

The gazette's list pages carry no UID, only a title, so this resolves the UID to a
legal name, keeps the publications whose title looks like that name, then fetches
those bodies and keeps the events whose own UID matches. The title match decides
what is worth downloading; the body's UID decides what is reported. Fetched bodies
are cached under the state directory, so an overlapping re-run costs nothing.

### `swissco watch`

What changed since last time.

```bash
printf 'CHE-444.420.929\nCHE-105.943.826\n' > uids.txt
swissco watch uids.txt --state ~/.swissco/
```

Each company is compared by fingerprint, a digest over its identity, address and
purpose fields. Exits `10` when something changed and `0` when nothing did, so cron
can branch on it:

```crontab
0 7 * * * swissco watch ~/uids.txt --quiet --format json > ~/changes.json \
          || mail -s "registry changes" me@example.com < ~/changes.json
```

A UID that has left the dataset is reported as **no longer in the dataset**, never as
deleted. LINDAS carries only active entities, so a UID can leave the dataset after a
re-registration, a correction, or a publication lag.

### `swissco tenders`

Public procurement projects from simap, by canton and publication date.

```console
$ swissco tenders --canton ZG --since 2026-08-25 --limit 3
TITLE                                                  PROJECT_NUMBER  BUYER                           CANTON  CITY  PUBLICATION_DATE  PUBLICATION_TYPE
-----------------------------------------------------  --------------  ------------------------------  ------  ----  ----------------  ----------------
Neubau Pfarreizentrum, Katholische Kirchgemeinde Baar  22047           Katholische Kirchgemeinde Baar  ZG      Baar  2026-09-05        award
```

`--canton` and `--type` are repeatable; `--lang` picks which language the title and
buyer are reported in. Paging is a cursor rather than an offset, so a wide range
costs pages instead of failing.

The date range filters each project's **newest publication**, not the award inside
it. A project awarded in March whose newest publication is an August correction
appears only in a range covering August.

### `swissco vendor`

Whether a company is registered as a supplier on simap.

```console
$ swissco vendor CHE-409.633.691
name                   Egli Gartenbau AG Sursee
uid no                 CHE-409.633.691
city                   Sursee
canton                 LU
url                    https://www.gartenbau-egli.ch
company size           medium
```

A UID is resolved to a legal name, searched for, and then confirmed against the
directory's own `uidNo`. The name finds the candidates; the UID decides between
them — the directory holds both an "Egli Gartenbau AG Sursee" and an "Egli
Gartenbau AG Uster".

**There is no command for what a company has won.** The supplier named on a simap
award carries no UID, only free text typed by a procurement office. Matching those
names would produce a plausible answer that is sometimes about a different company,
so it is not offered.

### `swissco finma`

FINMA's authorised banks and securities firms, joined to a UID.

```console
$ swissco finma --uid CHE-105.845.287
name                  Aargauische Kantonalbank
city                  Aarau 1
licence type          Bank
supervisory category  3
uid                   CHE-105.845.287
```

Also `swissco finma "Raiffeisen"`, `--licence`, `--category`, and `--finma` on
`lookup`. Both files are cached for a week under the state directory.

Banks and securities firms only: FINMA licenses insurers, portfolio managers and
fund management companies on separate lists this does not read. A miss means "not
on this list", never "unlicensed".

### `swissco lei`

A company's Legal Entity Identifier, and the group it is consolidated into.

```console
$ swissco lei CHE-412.669.376
legal name                 UBS Switzerland AG
lei                        549300WOIFUSNYH0FL22
registered as              CHE-412.669.376
jurisdiction               CH
status                     ACTIVE
initial registration date  2014-12-15
direct parent              UBS AG (BFM8T61CT2L1QCEMIK50, CH)
ultimate parent            UBS Group AG (549300SZJ9VS8SGXAN81, CH)
direct children            0
```

`--children` lists what this company consolidates instead of counting it, and
`--lei` on `lookup` folds the same fields into a company profile.

The parent is often foreign, and that is the reason to run this: a Swiss
subsidiary's owner abroad has no commercial-register entry, so the register
cannot answer the question at all.

GLEIF Level 2 records **accounting consolidation**: a parent is the entity that
consolidates this one into its accounts, which it may do without owning all of
it. About 28,000 Swiss entities hold an LEI against roughly 790,000 in the
register, so a miss means "no LEI on file" and nothing more.

### `swissco research`

Federally funded research projects from ARAMIS, the Confederation's register of
research and innovation mandates. Innosuisse and SNSF money included.

```console
$ swissco research CHE-337.958.399
TITLE                                 PROJECT_NUMBER    OFFICE      STATUS      START_DATE  ROLE
Reducing Documentation Burden in S…   137.839 INNO-ICT  INNOSUISSE  In Process  2026-06-01  Implementation Partner
```

A UID is confirmed against each project's own participant UID, so every row
reported is exact. Free text is searched as given and every hit comes back with
its participating organisations. `--limit` caps how many candidates are hydrated,
since the participant list costs one request per project, and `--lang` picks `DE`,
`EN`, `FR` or `IT`.

ARAMIS searches project titles, abstracts and the free-text contractor field, and
indexes the structured participant list under none of them. A company named only
as a structured partner cannot be found, which is where Innosuisse implementation
partners usually sit, so an empty result means only that no project mentions
this company by name. It is not evidence that the company has taken no federal
research money.

`swissco` reads the organisation, the role, the UID and the place off a
participant. ARAMIS also publishes the researcher's name, e-mail address and
telephone numbers, and none of those has a field in the parser.

## Output

`--format` is the only thing that changes the output. A command piped into `jq` and
the same command watched by a person produce identical bytes, so a script that works
in your terminal works in CI.

`table` and `csv` are rendered from the same rows that `json` serialises, so a column
cannot appear in one format and be missing from another. Progress notes go to stderr,
where `--quiet` silences them; errors go to stderr as a single JSON object.

## Use it from a coding agent

This repository ships an [Agent Skill](https://agentskills.io/specification). It
teaches Claude Code, Cursor, Codex and around twenty other agents how to drive
`swissco`: every command, and the traps that quietly produce a wrong answer.

The skill is the directory `.agents/skills/swissco/`, the cross-client location
every compliant agent scans, with `.claude/skills/swissco` symlinked to it so
Claude Code finds it in its own. `tests/test_skill.py` asserts the spec's rules
against it on every run, so the skill cannot drift out of the format without the
suite saying so.

```bash
npx skills add prospex-ch/swissco-cli
```

It lands in the consuming project's own `.agents/skills/swissco/`, symlinked
into each agent's directory. Add `-g` to install it once for every project,
`--all` to accept the defaults without being asked. `swissco` still has to be on
the path or reachable through `uvx`.

The agent can then answer questions like "which companies in Zug mention
blockchain in their purpose" or "has anything changed at CHE-105.943.826 since
June" by running the right command itself.

## Use it as an MCP server

The same six sources are available as an MCP server, from this repository.
Nine tools, one per command except `watch`.

```bash
claude mcp add swissco -- uvx swissco-mcp
```

Every tool returns `rows`, a `count`, and `notes`. The rows are the dicts
`swissco --format json` prints, so a field carries the same name in both
surfaces. The notes carry what each source covers, which is what turns an empty
result into an answer: FINMA's list omits insurers and portfolio managers, and
about 28,000 Swiss entities hold an LEI against roughly 790,000 in the
register.

It lives in [`mcp/`](mcp/), ships as the PyPI package
[`swissco-mcp`](https://pypi.org/project/swissco-mcp/) and the npm package of
the same name, and is registered as `ch.prospex/swissco`. Full reference for
every tool, its arguments and its caveats:
[swissco-mcp.readthedocs.io](https://swissco-mcp.readthedocs.io).

## Access and terms

**SHAB / Amtsblattportal.** The REST API is the channel the operator offers for
machine access: freely accessible, no authentication for published data, no
documented rate limit, page size capped at 2,000. The website UI is disallowed by
`robots.txt`, which does not reach the API. The operator disclaims completeness, and
only the signed PDF is legally binding.

**Zefix on LINDAS.** Published on [opendata.swiss](https://opendata.swiss), no
credentials. Commercial-use terms have never been settled; the
[dataset page](https://opendata.swiss/en/dataset/zefix-lindas) states what applies.

**Zefix PublicREST.** Requires credentials issued by `zefix@bj.admin.ch`. Every
command here works without them. Supplying them through `--user`/`--password` or
`ZEFIX_USER`/`ZEFIX_PASSWORD` adds capital, status, deletion date, former names and
corporate relations to `lookup`, and a name-prefix search to `search`.

**simap.** The read API answers unauthenticated. The site's `robots.txt` disallows
the single-page app's project-detail routes, which `swissco` refuses outright; it
says nothing about `/api`, where every request here goes.

**FINMA.** Two published files, downloaded as any browser would. FINMA republishes
rather than versions them, so they are cached for a week and re-fetched after
that.

**GLEIF.** The record API answers unauthenticated. GLEIF publishes the LEI data
for anyone to use, and the [terms of
use](https://www.gleif.org/en/meta/gleif-data-use-policy) state what applies.

**ARAMIS.** The public service answers unauthenticated and asks not to be
flooded, so `swissco` paces it and reads one project at a time. The 43 MB bulk
export sits on a host this client's allowlist omits, which is why no command can
pull it.

## Being a good citizen

These are small public services run by federal offices. `swissco` sends one request
every 0.5 seconds at most — one a second for FINMA, which asks for more room — backs
off exponentially on failure, and identifies itself with a real `User-Agent` carrying
this repository's URL. `--interval` can raise those floors and cannot lower them.

## Built on

| Package | Does |
|---|---|
| [`zefix-parser`](https://pypi.org/project/zefix-parser/) | Zefix: LINDAS SPARQL, PublicREST, UID validation |
| [`shab-parser`](https://pypi.org/project/shab-parser/) | SHAB: discovery, fetch, parse, eleven-type event classification |

Both are MIT and maintained alongside this one. simap, FINMA, GLEIF and ARAMIS
ship no client, so `swissco` carries its own for those four.

## Watching more than a list

`swissco watch` from cron is the free version of what [Prospex](https://prospex.ch)
sells. Prospex watches the whole register continuously, joins it to hiring, funding,
tenders and web signals — including the award side of simap that this tool
deliberately leaves alone — and tells you which of those changes is worth a call. If a
cron job and a UID list cover it, this tool is all you need.

## License

MIT
