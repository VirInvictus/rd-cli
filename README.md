<p align="center">
  <img src="logo.svg" alt="rd-cli" width="96" height="96">
</p>

# rd-cli

A fast, dependency-free command-line client for [Raindrop.io](https://raindrop.io).
Read, add, edit, reorganize, and remove your bookmarks (raindrops), collections,
tags, and highlights from the terminal, with designed ANSI output for humans and
`--json` for scripts and AI agents.

- **Zero runtime dependencies.** Pure Python standard library (`urllib`, `json`,
  `tomllib`, `argparse`). Nothing to audit, nothing to break.
- **Full API coverage.** Every practical Raindrop REST API v1 endpoint:
  raindrops (single, bulk, upload, suggest, export), collections (including
  merge, reorder, clean, covers), tags, highlights, user (read and edit), stats,
  filters, import dedup, HTML-file import, and backups.
- **Built for reorganizing at scale.** Bulk move, tag, and delete by id or by
  whole-collection scope, plus a global `--dry-run` that previews every write.
- **Resilient.** Per-request timeouts, typed errors that surface the API's own
  message, and automatic retry with backoff on rate limits and server errors.
- **Terminal-native.** Colour on a TTY, plain when piped; `NO_COLOR` and
  `--no-color` respected.

## Contents

- [Install](#install)
- [Authentication](#authentication)
- [Quick start](#quick-start)
- [Global options](#global-options)
- [Command reference](#command-reference)
  - [Raindrops](#raindrops)
  - [Bulk operations and the id-list vs scope model](#bulk-operations-and-the-id-list-vs-scope-model)
  - [Collections](#collections)
  - [Tags](#tags)
  - [Highlights](#highlights)
  - [Account: user, stats, filters, suggest, exists](#account)
  - [Import, export, backups](#import-export-backups)
  - [Pinboard](#pinboard)
  - [Sync (Raindrop and Pinboard)](#sync-raindrop-and-pinboard)
  - [Config](#config)
- [Output modes](#output-modes)
- [Exit codes](#exit-codes)
- [System collection ids](#system-collection-ids)
- [Rate limits and retries](#rate-limits-and-retries)
- [Using rd-cli as a library](#using-rd-cli-as-a-library)
- [Development](#development)
- [License](#license)

## Install

Requires Python 3.11 or newer (the floor for the standard-library `tomllib`).

```bash
# From a clone, into the current environment:
uv pip install -e .

# Or set up a dev environment (editable install + dev tools):
uv sync
```

After installation the `rd` command is on your `PATH`. You can also run it
without installing via `python -m rd_cli`.

## Authentication

Every call is authenticated with a bearer token. For personal use, the simplest
option is a **test token**, which does not expire and is scoped to your own
account:

1. Open [App Management Console](https://app.raindrop.io/settings/integrations).
2. Create an application (any name).
3. Copy its **Test token**.

Provide the token in any of the following ways. Resolution stops at the first
one found:

| Priority | Source | Notes |
| -------- | ------ | ----- |
| 1 | `RAINDROP_TOKEN` environment variable | Recommended for shells and CI. |
| 2 | `RAINDROP_TEST_TOKEN` environment variable | Back-compat alias. |
| 3 | `token` in `~/.config/rd-cli/config.toml` | Written by `rd config set-token`, `0600`. |
| 4 | `RAINDROP_TOKEN` / `RAINDROP_TEST_TOKEN` in a `.env` file | `./.env`, then `~/.config/rd-cli/.env`. Real env vars always win. |

```bash
export RAINDROP_TOKEN=your-token-here       # option 1: environment
rd config set-token your-token-here         # option 3: config file (chmod 0600)
echo 'RAINDROP_TOKEN=your-token-here' > .env  # option 4: local .env
```

`XDG_CONFIG_HOME` is honoured, so the config directory follows your XDG setup.
Full OAuth2 (login flow + refresh) is planned but not yet implemented; the test
token covers single-user needs.

For the optional **Pinboard** support (see [Pinboard](#pinboard) and
[Sync](#sync-raindrop-and-pinboard)), add a Pinboard API token, format
`user:HEX`, from [pinboard.in/settings/password](https://pinboard.in/settings/password),
the same three ways: the `PINBOARD_TOKEN` (or `PINBOARD_API_TOKEN`) environment
variable, `rd config set-pinboard-token <token>`, or `PINBOARD_TOKEN=` in a
`.env` file. Both service tokens live side by side in the one `config.toml`.

## Quick start

```bash
rd user                              # who am I?
rd stats                             # counts across All / Unsorted / Trash
rd list --all                        # every bookmark, all pages
rd add "https://example.com" -t "Example" --tags read-later
rd search "python #tutorial" --detailed
```

## Global options

These work with any command and may appear **before or after** the subcommand
(`rd --json list` and `rd list --json` are equivalent):

| Flag | Effect |
| ---- | ------ |
| `--json` | Emit a single JSON document to stdout and nothing else. See [Output modes](#output-modes). |
| `--no-color` | Force plain text even on a TTY. |
| `--dry-run` | Preview every **write**: log its method and payload to stderr and skip the API call. Reads still run, so you can plan a change safely first. |
| `--version` | Print the version and exit. |
| `-h`, `--help` | Show help for the program or any subcommand. |

`--dry-run` is enforced in one place (the HTTP layer) for any non-GET request,
so it reliably covers every command that changes data, including bulk ones.

## Command reference

Run `rd <command> --help` or `rd <group> <action> --help` for the exact flags of
any command. Grouped commands also have one-letter aliases: `c` for
`collections`, `t` for `tags`, `h` for `highlights`.

### Raindrops

| Command | Description |
| ------- | ----------- |
| `rd list` | List raindrops. Flags: `-c/--collection <id>` (default `0` = all), `-s/--search <query>`, `--sort <key>`, `--page <n>`, `--perpage <n>` (max 50), `-a/--all` (fetch every page), `-n/--nested` (include nested collections), `-d/--detailed` (show excerpt, note, tags). |
| `rd search <query>` | Shorthand for `list` with a positional search query. Same flags as `list`. |
| `rd view <id>` | Show one raindrop in full (link, domain, type, dates, collection, excerpt, note, tags, highlights). |
| `rd add <url>` | Create a raindrop. Flags: `-t/--title`, `-c/--collection` (default `-1` = Unsorted), `--tags <t...>`, `--excerpt`, `--note`, `--important`, `--no-parse` (skip background metadata fetch), and `--file <path>` / `--stdin` for [bulk add](#bulk-operations-and-the-id-list-vs-scope-model). |
| `rd edit <id>` | Update a raindrop. Flags: `-t/--title`, `--tags <t...>` (replaces), `-c/--collection` (move), `--excerpt`, `--note`, `--important` / `--not-important`. |
| `rd rm <ids...>` | Move raindrop(s) to Trash. `--permanent` deletes for good; scope flags `--from`, `-s`, `-n` remove a whole collection. See [bulk](#bulk-operations-and-the-id-list-vs-scope-model). |
| `rd mv <dest> <ids...>` | Move raindrop(s) into collection `<dest>`. Scope flags `--from`, `-s`, `-n`. |
| `rd tag <ids...>` | Modify tags. Flags: `--add <t...>`, `--remove <t...>`, `--clear`. Scope flags `--from`, `-s`, `-n`. |
| `rd cover <id> <file>` | Upload a cover image (PNG, GIF, or JPEG) for a raindrop. |
| `rd import <file>` | Parse a Netscape/Pocket/Instapaper HTML export to JSON. Add `--create -c <id>` to actually import the bookmarks into a collection. |
| `rd export` | Export raindrops. Flags: `-c/--collection` (default `0`), `-f/--format {csv,html,zip}`, `--sort`, `-s/--search`, `-o/--output <file>` (otherwise stdout). |

```bash
rd list -c 0 --detailed                     # everything with excerpts and tags
rd list --all --json > all.json             # every page as JSON
rd add "https://example.com" --tags ai read-later --important
rd add --file urls.txt -c 12345             # one URL per line, chunked at 100
rd edit 12345 --note "revisit" --important
rd export -c 0 -f csv -o bookmarks.csv
rd import pocket.html --create -c 12345      # import an export file
```

`add` auto-parses page metadata (title, cover, type) in the background unless you
pass `--no-parse`. When you supply only a URL, a title is fetched for you.

### Bulk operations and the id-list vs scope model

`mv`, `rm`, and `tag` each work in two modes, and the distinction matters
because of how the Raindrop API scopes its batch endpoints:

- **Id-list mode** (`rd mv 999 111 222`, `rd rm 1 2 3`, `rd tag 1 2 --add x`)
  operates on the raindrop ids you name. Internally it loops the single-item
  endpoints, which is **correct no matter which collection each raindrop lives
  in**.
- **Scope mode** (`--from <collection>`, optionally narrowed with `-s <search>`
  and `-n/--nested`) operates on **every raindrop in that source collection** in
  a single batch call. `--from` is required for scope, and it must be a real
  collection: the batch endpoints do not accept the `0` (all) pseudo-collection,
  and they only touch raindrops that are actually in the given collection.

```bash
# Id-list mode
rd mv 999 111 222 333            # move three raindrops into collection 999
rd rm 111 222 333                # trash three raindrops
rd rm 111 222 --permanent        # delete them for good (skips Trash)
rd tag 111 222 --add ai --remove old   # precise add + remove per raindrop
rd tag 111 --clear               # remove all tags from a raindrop

# Scope mode (whole collection, one batch call)
rd mv 999 --from 111             # move everything in 111 into 999
rd rm --from 111 -s "is:broken"  # trash everything matching a search in 111
rd tag --from 111 --add reviewed # append a tag to every raindrop in 111
rd tag --from 111 --clear        # strip all tags across a collection

# Preview any of the above without touching the API
rd --dry-run mv 999 --from 111
```

Notes:

- `tag` in id-list mode does precise add/remove/clear (it reads each raindrop's
  current tags, computes the new set, and writes it back). In scope mode the API
  can only **append** (`--add`) or **clear all** (`--clear`); to strip one
  specific tag from every raindrop, use `rd tags rm <tag>`.
- `rm --permanent` deletes via the documented two-step (to Trash, then from
  Trash). Deleting a raindrop that is already in Trash also removes it
  permanently.

### Collections

| Command | Description |
| ------- | ----------- |
| `rd collections list` | List root collections with ids and counts. |
| `rd collections tree` | Nested tree of all collections, indented by parent. |
| `rd collections view <id>` | Show one collection. |
| `rd collections add <title>` | Create a collection. Flags: `--view {list,simple,grid,masonry}`, `--parent <id>`, `--public`. |
| `rd collections edit <id>` | Update a collection. Flags: `-t/--title`, `--view`, `--parent` (re-nest), `--public` / `--private`. |
| `rd collections rm <id>` | Delete a collection (its raindrops move to Trash). |
| `rd collections merge <to> <ids...>` | Merge the listed collections into `<to>`. |
| `rd collections clean` | Remove all empty collections. |
| `rd collections empty-trash` | Permanently empty Trash. |
| `rd collections reorder --by <key>` | Reorder all collections. `<key>` is `title`, `-title`, or `-count`. |
| `rd collections cover <id> <file>` | Upload a collection cover image. |
| `rd collections covers <text>` | Search Raindrop's icon/cover library. |

```bash
rd collections tree
rd collections add "Reading" --public --view grid
rd collections merge 111 222 333        # fold 222 and 333 into 111
rd collections reorder --by=-count      # note: leading-dash values need '='
rd collections covers pokemon
```

> Values that start with a dash (`-count`, `-title`) must be attached with `=`,
> e.g. `--by=-count`, because argparse otherwise reads them as flags.

### Tags

| Command | Description |
| ------- | ----------- |
| `rd tags list` | List tags with counts. `-c/--collection <id>` restricts to one collection. |
| `rd tags rename <old> <new>` | Rename a tag (merges into `<new>` if it exists). `-c` to scope. |
| `rd tags merge <into> <tags...>` | Merge several tags into `<into>`. `-c` to scope. |
| `rd tags rm <tags...>` | Delete tags (removes them from every raindrop). `-c` to scope. |

```bash
rd tags list
rd tags rename ml machine-learning
rd tags merge ai artificial-intelligence machine-learning   # into "ai"
rd tags rm obsolete-tag
```

### Highlights

| Command | Description |
| ------- | ----------- |
| `rd highlights list` | List highlights. `-r/--raindrop <id>` for one raindrop; otherwise all highlights, with `-a/--all`, `--page`, `--perpage`. |
| `rd highlights add <raindrop> <text>` | Add a highlight. `--color <name>`, `--note <text>`. |
| `rd highlights edit <raindrop> <highlight>` | Edit a highlight. `--text`, `--color`, `--note`. |
| `rd highlights rm <raindrop> <highlight>` | Remove a highlight. |

Colours: `blue`, `brown`, `cyan`, `gray`, `green`, `indigo`, `orange`, `pink`,
`purple`, `red`, `teal`, `yellow` (default `yellow`).

```bash
rd highlights list -r 12345
rd highlights add 12345 "an important sentence" --color green --note "why"
```

### Account

| Command | Description |
| ------- | ----------- |
| `rd user` (or `rd user show`) | Show the authenticated user (id, email, plan, file quota). |
| `rd user set` | Update settings: `--name`, `--email`, `--new-password` (with `--old-password`), `--config KEY=VALUE ...`. |
| `rd stats` | System collection counts (All / Unsorted / Trash) plus duplicate and broken counts. |
| `rd filters` | Context filters for a collection: `-c/--collection`, `--tags-sort {-count,_id}`, `-s/--search`. Shows broken/duplicate/important/untagged counts and type/tag breakdowns. |
| `rd suggest` | Suggest collections and tags. Provide `--url <url>` (new) or `--id <raindrop>` (existing). PRO plan only. |
| `rd exists <urls...>` | Check whether URLs are already saved (dedup). Prints the matching ids. |

```bash
rd user
rd user set --name "New Name" --config lang=en
rd filters -c 0
rd exists "https://example.com" "https://other.com"
```

### Import, export, backups

| Command | Description |
| ------- | ----------- |
| `rd import <file> [--create -c <id>]` | Parse an HTML bookmark export (Netscape/Pocket/Instapaper); with `--create`, import the bookmarks into a collection. |
| `rd export ...` | See [Raindrops](#raindrops). CSV, HTML, or ZIP, to a file or stdout. |
| `rd backups list` | List server-side backups (id + date). |
| `rd backups create` | Request a new backup (Raindrop emails the export when ready). |
| `rd backups download <id>` | Download a backup. `-f/--format {csv,html}`, `-o/--output <path>`. |

### Pinboard

rd-cli also speaks [Pinboard](https://pinboard.in), the other bookmarking
service, through a `pinboard` (alias `pb`) command group. Pinboard's model is
**flat**: bookmarks are keyed by their URL (there are no numeric ids and no
collections), organized only by tags, with `toread` and `shared` flags and
separate notes. The commands match that model rather than pretending Pinboard
has Raindrop's collections. Needs a `PINBOARD_TOKEN` (see
[Authentication](#authentication)).

| Command | Description |
| ------- | ----------- |
| `rd pinboard list` | List bookmarks (recent by default). Flags: `--tag <t>` (repeatable, max 3), `--count <n>` (max 100), `-a/--all` (every bookmark), `--toread` (only unread), `-d/--detailed`. |
| `rd pinboard get <url>` | Show one bookmark by its URL. |
| `rd pinboard add <url>` | Add a bookmark. Flags: `-t/--title`, `--extended <note>`, `--tags <t...>`, `--toread`, `--shared`/`--private`, `--no-replace` (fail if the URL exists), `--dt <iso>`. |
| `rd pinboard rm <url>` | Delete a bookmark. **Permanent; Pinboard has no trash.** |
| `rd pinboard edit <url>` | Edit a bookmark (read-modify-write, since Pinboard has no update endpoint). Flags: `-t/--title`, `--extended`, `--tags <t...>`, `--toread`/`--not-toread`, `--shared`/`--private`. |
| `rd pinboard tag <url>` | Modify tags on a bookmark: `--add <t...>`, `--remove <t...>`, `--clear`. |
| `rd pinboard suggest <url>` | Popular and recommended tags for a URL. |
| `rd pinboard tags list` | List tags with counts. |
| `rd pinboard tags rename <old> <new>` | Rename a tag across all bookmarks. |
| `rd pinboard tags rm <tags...>` | Delete tag(s). |
| `rd pinboard notes list` | List notes (metadata). |
| `rd pinboard notes view <id>` | Show a note's full text. |

```bash
rd pinboard list --tag cooking --count 20
rd pinboard add "https://example.com" -t "Example" --tags read-later --toread
rd pinboard tag "https://example.com" --add reference --remove read-later
rd pinboard tags list --json | jq 'to_entries | sort_by(-.value)[:10]'
```

Pinboard's rate limit is strict (about one request every three seconds), so the
client paces itself automatically; bulk operations will feel slower than
Raindrop's on purpose.

### Sync (Raindrop and Pinboard)

`rd sync` performs a **two-way additive** sync between the two services:
bookmarks are matched by a normalized URL (which doubles as the dedup key), and
the two libraries converge to their union. It only ever **adds and merges,
never deletes**, so nothing is lost. The model gap is bridged reversibly in
tags: a Raindrop collection becomes a slugged Pinboard tag; `toread` and
`important` ride along as tags; a Pinboard tag that matches a collection routes
the item back into it. On a shared URL, tags are unioned and notes merged.

| Flag | Effect |
| ---- | ------ |
| `--dry-run` | Print the plan (counts per direction, near-dupes collapsed) and write nothing. **Run this first.** |
| `--direction {both,to-pinboard,to-raindrop}` | Limit which side is written (default `both`). |
| `--collection <id>` | Only push Raindrop items in this collection (repeatable). |
| `--rd-tag <tag>` | Only push Raindrop items with this tag (repeatable). |
| `--pb-tag <tag>` | Only push Pinboard items with this tag (repeatable). |

Scope flags narrow what gets **written**, but matching always uses the full sets
on both sides, so an out-of-scope bookmark that already exists on the other
service is recognized and never re-imported as a duplicate.

```bash
rd sync --dry-run                                       # preview the full union
rd sync --dry-run --direction to-pinboard --collection 123   # just one collection, one way
rd sync --direction to-raindrop --pb-tag toread         # pull only your Pinboard to-reads
```

Delete propagation and conflict resolution (which need a persistent sync
manifest) are intentionally not implemented yet; see `roadmap.md`.

### Config

| Command | Description |
| ------- | ----------- |
| `rd config path` | Print the config file path. |
| `rd config show` | Show config (tokens are masked). Add `--json` for raw. |
| `rd config set-token <token>` | Store the Raindrop API token in `config.toml` (`0600`). |
| `rd config set-pinboard-token <token>` | Store the Pinboard API token (`user:HEX`) in `config.toml` (`0600`). |

The `config` commands never touch the network and do not require a token.

### Back-compat aliases

The original flat command names still work as hidden aliases, so older scripts
keep running: `c-list`, `c-add`, `c-rm`, `t-list`, `t-rm`, `h-list`, `h-add`,
`h-rm`. Prefer the grouped forms (`rd collections list`, etc.) going forward.

## Output modes

**Human mode (default).** Rendered with ANSI colour only when stdout is a
terminal, `NO_COLOR` is unset, and `--no-color` was not passed; otherwise plain
text. Layout and colour are presentation only and may change between versions,
so **do not parse human output** in scripts.

**JSON mode (`--json`).** A single indented UTF-8 JSON document on stdout and
nothing else. Shapes:

- List commands emit the array of API objects (`list`, `tags list`,
  `highlights list`, ...).
- Single-object commands emit the object (`view`, `add`, `edit`,
  `collections view`).
- Boolean/count commands emit a small object (`{"result": true}`,
  `{"modified": 3}`, `{"moved": 2, "collection": 999}`, ...).
- Errors emit `{"error": "<message>"}` on stdout and still exit non-zero.

Objects are passed through from the API unchanged. Per Raindrop's own docs,
responses may contain undocumented fields that are unsafe to rely on.

```bash
rd list --all --json | jq '.[].link'
rd stats --json | jq '.meta.duplicates.count'
```

## Exit codes

| Code | Meaning |
| ---- | ------- |
| 0 | Success (also: broken pipe, and the no-args help screen) |
| 1 | Handled error (a `RaindropError`, or an operation whose `result` was false) |
| 2 | Usage error (bad flags or arguments; from argparse) |
| 130 | Interrupted (`Ctrl-C`) |

## System collection ids

Several commands accept a collection id, including these system pseudo-ids:

| id | Meaning |
| --- | ------- |
| `0` | All raindrops (except Trash). Not valid for the bulk `--from` scope of `mv`/`rm`/`tag`. |
| `-1` | Unsorted (the default target for `add`). |
| `-99` | Trash. |

## Rate limits and retries

The Raindrop API allows 120 requests per minute per user. rd-cli retries
automatically:

- **429 (rate limited):** waits for the `Retry-After` header (integer seconds or
  an HTTP-date) or `X-RateLimit-Reset`, capped at 60 seconds.
- **5xx and transient network errors:** exponential backoff.
- Retries are bounded (3 by default). Other `4xx` responses are not retried;
  their error message (the API's `errorMessage`) is surfaced to you.

Each request also has a 30-second timeout.

## Using rd-cli as a library

The HTTP client is a clean, dependency-free class you can import directly. Every
endpoint is one method, and all requests go through a single retrying core.

```python
from rd_cli.config import resolve_token
from rd_cli.client import RaindropClient

client = RaindropClient(resolve_token())

for rd in client.iter_raindrops(0, search="python"):   # auto-paginates
    print(rd["_id"], rd["link"])

client.create_raindrop("https://example.com", tags=["read-later"], please_parse=True)
client.update_raindrops(111, search="is:broken", move_to=999)   # scope move
```

Construction options: `RaindropClient(token, *, base_url=..., timeout=30.0,
max_retries=3, dry_run=False, opener=None, sleep=time.sleep)`. The `opener` and
`sleep` hooks make it trivial to test without a network (see `tests/`).

## Development

```bash
uv sync
uv run pytest                     # tests (no network; a fake transport stubs urllib)
uv run ruff check src tests       # lint
uv run ruff format src tests      # format
```

Project docs: `CLAUDE.md` is the full Raindrop API reference and codebase map;
`spec.md` is the CLI contract; `roadmap.md` tracks phases; `patchnotes.md` is the
changelog. The version lives in a single `VERSION` file.

## License

MIT. See `LICENSE`.
