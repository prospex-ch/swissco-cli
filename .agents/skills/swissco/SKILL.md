---
name: swissco
description: >
  Query Swiss company data from the shell with `swissco`: look up a company by
  UID, search 790,000 companies by name or statutory purpose, list commercial
  register publications from the SHAB gazette, trace one company's registry
  events, watch a list of companies for change, browse public procurement on
  simap, or check FINMA's authorised banks and securities firms.
  Triggers: "Swiss company", "Swiss commercial register", "Handelsregister",
  "registre du commerce", "Zefix", "SHAB", "SOGC", "FUSC", "Amtsblattportal",
  "UID", "CHE-", "Swiss company lookup", "Swiss company search",
  "incorporations in Switzerland", "who was appointed", "capital increase",
  "company purpose", "watch a company", "simap", "public procurement",
  "public tender", "Ausschreibung", "Beschaffung", "appel d'offres",
  "Zuschlag", "FINMA", "authorised bank", "bank licence",
  "Bewilligungstraeger", "securities firm", "swissco".
license: MIT
compatibility: >
  Requires the `swissco` CLI on PATH, or `uvx` to run it without installing,
  and outbound network access to lindas.admin.ch, amtsblattportal.ch,
  www.simap.ch and www.finma.ch. Zefix PublicREST credentials are optional and
  extend two commands; nothing else needs any.
allowed-tools: Bash(swissco:*) Bash(uvx swissco:*)
metadata:
  author: prospex-ch
  version: "0.2.0"
  repository: https://github.com/prospex-ch/swissco-cli
  documentation: https://swissco.readthedocs.io
---

# swissco

A zero-config CLI over two Swiss federal open-data sources. No API key, no
signup, no config file.

```bash
uvx swissco --help          # run without installing
pip install swissco         # or install it
```

## The eight commands

| Command | Answers |
|---|---|
| `swissco lookup <uid>` | Everything the register publishes about one company |
| `swissco search <term>` | Which companies match a name or a statutory purpose |
| `swissco publications` | What the gazette published in a date range |
| `swissco events <uid>` | One company's registry history |
| `swissco watch <file>` | What changed since the last run |
| `swissco tenders` | Which public tenders and awards were published, by canton and date |
| `swissco vendor <uid>` | Whether a company is in simap's vendor directory |
| `swissco finma` | Whether a company is a FINMA-authorised bank or securities firm |

All eight take `--format table|json|csv` (default `table`), `--limit`, `--quiet`,
`--interval`, `--state`, `--user`, `--password`.

**Always pass `--format json` when you intend to parse the output.** The table
format truncates long cells at 60 characters and marks them with `…`.

## Reading the output

Output never depends on whether stdout is a terminal, so a command produces the
same bytes in a pipe as on screen. Progress notes go to stderr and `--quiet`
silences them. Errors go to stderr as one JSON object:

```json
{"error": "not_found", "message": "no company with UID CHE-... in the LINDAS dataset"}
```

Exit codes: `0` success, `1` the request failed, `10` `watch` found a change.

## lookup

```bash
swissco lookup CHE-444.420.929 --format json
```

Takes `CHE-444.420.929`, `CHE444420929`, or a UID embedded in other text. The
check digit is verified locally, so a typo fails immediately with
`{"error": "invalid_uid"}` and costs no request.

Returns `legal_name`, `uid`, `chid`, `ehra_id`, `legal_form_code`, `legal_form`,
`municipality`, `canton`, `address`, `purpose`, `zefix_uri`.

With Zefix PublicREST credentials it also returns `status`, `capital_nominal`,
`deletion_date`, `old_names`, `branch_offices`, `head_offices`,
`has_taken_over`, `was_taken_over_by`.

## search

```bash
swissco search "precision machining" --canton VD --limit 20 --format json
swissco search "blockchain" --canton ZG --legal-form 0106
```

Matches a case-insensitive substring of the **legal name or the statutory
purpose**. The purpose is the useful half: it is how a company describes its own
business to the register, so it finds companies whose name gives nothing away.

`--legal-form` takes an eCH-0097 code. The common ones: `0106` AG, `0107` GmbH,
`0101` Einzelunternehmen, `0103` Kollektivgesellschaft, `0108` Genossenschaft,
`0109` Verein.

`--via rest` switches to a name-prefix search through the PublicREST API and
needs credentials. Reach for it when the user typed something that reads like a
company name and the substring search returned noise.

## publications

```bash
swissco publications --since 2026-08-01 --until 2026-08-07 --canton ZH --format json
swissco publications --since 2026-09-01 --canton ZG --type CAPITAL_INCREASED
```

Options: `--since`, `--until` (`YYYY-MM-DD`, defaults to yesterday), `--canton`
(repeatable), `--sub-rubric` (`HR01` registrations, `HR02` mutations, `HR03`
deletions, repeatable), `--query` (matches the title in any of four languages),
`--type` (repeatable).

`--type` accepts the eleven `shab-parser` event types: `INCORPORATION`,
`BRANCH_CREATED`, `SEAT_MOVED`, `ADDRESS_CHANGED`, `NAME_CHANGED`,
`PURPOSE_CHANGED`, `CAPITAL_INCREASED`, `MERGER`, `OFFICERS_CHANGED`,
`LIQUIDATION`, `DELETED`.

**Cost model, which decides how to phrase the command.** Without `--type`, only
list pages are read: one request per 2,000 publications, so a week costs a
handful of requests. With `--type`, every publication surviving the other
filters has its body fetched at 0.5 seconds each, because the event types live
in the body. The gazette publishes around a thousand entries a day, so
`--type` over an unfiltered month is hours of requests. Narrow by `--canton`
and by date first, then add `--type`.

## events

```bash
swissco events CHE-444.420.929 --since 2026-01-01 --format json
```

The join between the two sources. The gazette's list pages carry a title and no
UID, so `swissco` resolves the UID to a legal name through Zefix, keeps the
publications whose title resembles that name, fetches only those bodies, and
keeps the events whose body UID matches. Report what it returns as confirmed;
the title match alone never reaches the output.

Bodies are cached under the state directory by publication id, so an
overlapping re-run is nearly free. `--no-cache` bypasses it.

A wide range is slow before it is useful: listing a year takes a few hundred
requests before the first body is fetched. Tell the user the range you are
about to scan, and prefer the narrowest one that answers their question.

## watch

```bash
printf 'CHE-444.420.929\nCHE-114.723.217\n' > uids.txt
swissco watch uids.txt --state ~/.swissco/ --format json
```

The UID file takes one per line; blank lines and `#` comments are skipped, and
a UID that fails its check digit is reported on stderr and passed over.

Each company is compared by fingerprint, a digest over its identity, address and
purpose fields. Rows come back with `uid`, `status`, `legal_name` and `changes`,
where `status` is `added`, `changed`, or `no longer in the dataset`, and
`changes` names the fields that moved.

Exit `10` on any change and `0` on none, so a cron job can branch on it:

```crontab
0 7 * * * swissco watch ~/uids.txt --quiet --format json > ~/changes.json \
          || mail -s "registry changes" me@example.com < ~/changes.json
```

**The first run reports every company as `added` and exits `10`.** That is the
state file being written for the first time, not a change in the register. Say
so when you report it.

## tenders

Public procurement projects from simap, by canton and publication date.

```bash
swissco tenders --canton ZH --since 2026-08-01 --format json
swissco tenders --canton VD --canton GE --since 2026-08-01 --type award --lang fr
```

Returns `title`, `project_number`, `buyer`, `canton`, `city`, `project_type`,
`process_type`, `publication_date`, `publication_type`, `project_id`,
`publication_id`.

`--type` takes one of `abandonment`, `advance_notice`, `award`, `competition`,
`direct_award`, `participant_selection`, `request_for_information`,
`revocation`, `selective_offering_phase`, `study_contract`, `tender`;
repeatable. `--lang` picks which language the title and buyer are reported in
when the office published more than one.

**This lists projects, not winners.** See the caveat below before answering any
question about which company won a contract.

## vendor

Whether a company is registered as a supplier on simap, and what it lists
itself as doing.

```bash
swissco vendor CHE-409.633.691       # a UID: confirmed exactly
swissco vendor "Egli Gartenbau"      # free text: every hit, unfiltered
```

With a UID, the command resolves it to a legal name, searches the directory,
and keeps only rows whose own `uidNo` matches. Returns `name`, `uid_no`,
`additional_name`, `street`, `postal_code`, `city`, `canton`, `url`,
`company_size`, `type_of_services`, `cpv_codes`, `bkp_codes`, `npk_codes`,
`business_purpose`, `is_bidding_consortium`, `leading_vendor_name`,
`vendor_id`. With free text, returns the search rows instead.

`not_in_vendor_directory` means no profile carries that UID. A company can bid
without a directory profile, so report it as "not in the directory", never as
"does not bid for public contracts".

## finma

FINMA's list of authorised banks and securities firms.

```bash
swissco finma --uid CHE-105.845.287
swissco finma "Raiffeisen" --limit 50
swissco finma --licence "Securities firm" --category 3
```

Returns `name`, `city`, `licence_type`, `supervisory_category`, `uid`,
`foreign_control`, `no_securities_firm_activity`,
`non_account_holding_securities_firm`, `about_to_cease_operations`.

`licence_type` is one of `Bank`, `Securities firm`, `Foreign bank branch
office`, `Foreign securities firm branch office`. `supervisory_category` runs
1 (largest) to 5 (smallest).

The two files are cached under the state directory for a week; `--refresh`
re-downloads them.

## Six things that will otherwise catch you out

**A vanished UID has not been deleted.** `status` reads `no longer in the
dataset` and must be reported that way. The Zefix LINDAS dataset carries active
entities, so a UID can leave it after a re-registration, a correction, or a
publication lag. To find out which, run `swissco events` on it, or `lookup` with
PublicREST credentials, whose `status` and `deletion_date` answer directly.

**The gazette API accepts filter parameters and ignores them.** `cantons`,
`subRubrics`, `q` and `keywords` return HTTP 200 for an anonymous caller and
change nothing. `swissco` filters client-side over the list page's own metadata.
If you ever query that API yourself, compare the filtered total against the
unfiltered one before trusting it.

**The gazette rejects any request whose page offset reaches 10,000.** `swissco`
splits a long date range into windows automatically and reports each on stderr.
A range of several months is many requests, so it is worth narrowing.

**`swissco` cannot tell you what a company has won on simap.** The supplier
named on an award publication carries no UID, only a free-text name typed by a
procurement office — the directory has both an "Egli Gartenbau AG Sursee" and
an "Egli Gartenbau AG Uster", and nothing on the award distinguishes them. So
there is no award-history command, and you must not assemble one by matching
names from `swissco tenders`. `swissco vendor` answers the question that *can*
be confirmed: is this company in the directory, under this exact UID.

**FINMA's list is banks and securities firms only.** It does not cover
insurers, portfolio managers, trustees, fund management companies, market
infrastructures or fintech licensees — FINMA publishes those on separate lists
that `swissco` does not read. A company absent from `swissco finma` is not
"unlicensed"; it is "not a bank or securities firm on this list". FINMA also
publishes a few authorised entities with no UID at all, so a UID lookup can
miss one that is on the list.

**Credentials are optional everywhere.** Every command works anonymously
through LINDAS. `ZEFIX_USER` and `ZEFIX_PASSWORD` (or `--user`/`--password`)
extend `lookup` and enable `search --via rest`. The credentials come from
`zefix@bj.admin.ch` on request. Never suggest that the tool is unusable without
them.

## Rate limits

One request per 0.5 seconds, exponential backoff over four attempts, and a
`User-Agent` naming the project. FINMA is paced slower still, at one request a
second. `--interval` raises those floors and cannot lower them. These are small
public services run by federal offices; leave the pacing alone.

## Going further

`swissco` is a shell over two libraries, and either can be imported directly
when a command is the wrong shape:

- [`zefix-parser`](https://zefix-parser.readthedocs.io): LINDAS SPARQL queries,
  the PublicREST client, UID and CH-ID validation.
- [`shab-parser`](https://shab-parser.readthedocs.io): gazette discovery, fetch,
  XML parsing, and the eleven-type event classifier with its text extractors.

Full documentation: <https://swissco.readthedocs.io>.
