# CLAUDE.md

Guidance for Claude Code working in **rd-cli**, a stdlib-only command-line
client for the [Raindrop.io](https://raindrop.io) bookmarking service. This file
documents both the Raindrop REST API and this codebase. Read it before changing
API behavior or the command surface.

The portfolio conventions in `~/.claude/CLAUDE.md` and `~/.gitrepos/CLAUDE.md`
apply. Where they conflict with this file, this file wins for rd-cli.

## What this is

`rd` is a single-user CLI over Raindrop.io's REST API v1. It is a reader and a
writer: list/search/add/edit/remove bookmarks (raindrops), manage collections,
tags, and highlights, and reach the account-level endpoints (user, stats,
filters, suggestions, import-dedup, export, backups). Every command speaks
human-readable ANSI **and** `--json`, so it doubles as an automation and
AI-agent surface.

As of v0.2.0 it is also a **Pinboard** client: a `rd pinboard` (`pb`) command
group manages a second bookmarking service through `PinboardClient`, a stdlib
sibling of `RaindropClient`. Pinboard's model is flat (bookmarks keyed by URL,
tags, notes, `toread`/`shared`), so it gets its own honest command surface
rather than being forced through the Raindrop-shaped verbs. See the Pinboard API
reference at the bottom of this file.

House constraints that shaped it:

- **Zero runtime dependencies.** Pure stdlib (`urllib`, `json`, `tomllib`,
  `argparse`). No `requests`, no `python-dotenv`. Matches the stdlib-lean CLI
  siblings (CalibreQuarry, Bindery, oceanstrip). Do not add a dependency without
  asking Brandon.
- **Local-first, no accounts beyond the token.** No OAuth server flow yet; a
  personal test token is enough (see Auth).
- **TTY-aware output.** Colour on a terminal, plain when piped, `NO_COLOR`
  and `--no-color` respected.

## Layout

```
rd-cli/
  VERSION                  single source of truth for the version
  pyproject.toml           reads VERSION dynamically (hatchling); rd script entry
  src/rd_cli/
    __init__.py            __version__ (importlib.metadata -> VERSION fallback)
    __main__.py            python -m rd_cli entry
    errors.py              exception hierarchy (RaindropError base)
    config.py              token + config resolution (env -> config.toml -> .env)
    client.py              RaindropClient: the whole API over urllib  <-- core
    output.py              ANSI palette, TTY detection, table/tree/json renderers
    commands.py            one cmd_* / cfg_* handler per command
    cli.py                 argparse construction + dispatch + bootstrap
  tests/                   pytest; a FakeOpener stubs urllib (no network)
```

**`client.py` is the reusable core** and a future library-graduation candidate:
it has a clean, domain-agnostic public surface (one method per endpoint) and no
CLI coupling. If another project wants Raindrop access, extract it before
forking. Not now; post-1.0 call.

### Module responsibilities

- **`config.resolve_token()`** is the only place that decides the token. Order:
  `RAINDROP_TOKEN` env, `RAINDROP_TEST_TOKEN` env (back-compat alias),
  `token` in `$XDG_CONFIG_HOME/rd-cli/config.toml`, then a `.env` file
  (`./.env`, then `$XDG_CONFIG_HOME/rd-cli/.env`). The `.env` reader is a tiny
  hand-rolled parser (`parse_env`) and is non-clobbering (real env wins).
- **`RaindropClient._request()`** is the only place that touches the network.
  It attaches auth, applies a timeout, lowercases boolean query params,
  JSON-encodes bodies, retries `429`/`5xx`, and maps errors to typed exceptions.
  Add endpoints as small methods that delegate to it. The constructor takes
  `opener` and `sleep` so tests inject a fake transport (see `tests/conftest.py`).
- **`output.configure()`** decides colour once per run; **`output.color()`** is
  a no-op when colour is off. Domain formatters (`format_raindrop_line`,
  `format_collection_tree`, ...) never print; they return strings.
- **`commands.cmd_*(client, args)`** handlers return an exit code and choose
  between `--json` (`output.emit_json`) and human output. `cfg_*` handlers do not
  need a client.
- **`cli.build_parser()`** wires everything. A shared `common` parent parser
  carries `--json`/`--no-color` onto every subcommand (with `SUPPRESS` defaults
  so a flag before the subcommand is not clobbered by the child's default;
  `main()` normalizes the absent case back to `False`).

## Conventions

- Python 3.11+ (`tomllib` floor). `from __future__ import annotations` at the
  top of every module. Type hints throughout.
- Lint + format with `ruff` (config in `pyproject.toml`, selects `E,F,I,UP,B`).
  Run `uv run ruff check` and `uv run ruff format` before finishing.
- Tests are not optional. `uv run pytest`. No network in tests; use the
  `FakeOpener` (queue dicts for 200s, exceptions for errors) and inject
  `sleep=lambda s: ...` so retry paths do not actually wait.
- Comments sparingly: explain a quirk or a workaround, not the obvious.
- Prose in docs uses no em-dashes (Brandon's rule); source comments are exempt.

## Common tasks

```bash
uv sync                       # install (editable) + dev tools
uv run rd <command>           # run the CLI
uv run pytest                 # tests
uv run ruff check src tests   # lint
uv run ruff format src tests  # format
```

Bumping the version means editing `VERSION` only (pyproject and `__version__`
read from it). Update `patchnotes.md` (newest at top) and tick `roadmap.md`.

---

# Raindrop.io REST API v1 reference

Base URL: `https://api.raindrop.io/rest/v1`. Official docs mirror is cloned at
`../developer-site` (read it there for exhaustive field tables). Summary below
is what rd-cli relies on.

## Auth

Every call needs `Authorization: Bearer <token>`. Two token kinds:

- **Test token**: from the [App Management Console](https://app.raindrop.io/settings/integrations),
  scoped to your own account, **does not expire**. This is what rd-cli uses.
- **OAuth access token**: from the 3-legged OAuth2 flow, **expires after two
  weeks**, refreshable via `refresh_token`. Not implemented yet (roadmap).

## Conventions and gotchas

- **JSON envelope.** Most responses are `{"result": true, "item": {...}}` or
  `{"result": true, "items": [...]}`. `client.py` unwraps `item`/`items`.
- **Errors.** Non-2xx returns `{"result": false, "error": ..., "errorMessage":
  "..."}`. `_to_api_error()` parses `errorMessage` and raises `AuthError` (401/
  403), `NotFoundError` (404), `RateLimitError` (429), or `APIError`. Never let a
  bare `HTTPError` escape.
- **Boolean query params must be lowercase** (`nested=true`, not `True`).
  `_encode_params()` handles this; do not build query strings by hand.
- **Rate limit: 120 requests/minute** per user. `429` includes `Retry-After`
  and/or `X-RateLimit-Reset` (epoch seconds). The client honors them and backs
  off, capped, with bounded retries. `5xx` is safe to retry; `4xx` is not.
- **Timestamps** are ISO 8601 (`YYYY-MM-DDTHH:MM:SSZ`).
- **`perpage` max is 50.** The client clamps. Use the `iter_*` generators (or
  CLI `--all`) to walk all pages.

## System collection ids

Passed as the `collectionId` path segment for the "multiple raindrops"
endpoints:

| id    | meaning                                        |
| ----- | ---------------------------------------------- |
| `0`   | All raindrops (except Trash)                   |
| `-1`  | Unsorted                                       |
| `-99` | Trash                                          |

Caveat from the API docs: **update-many and remove-many do not support `0`
yet.** Pick a real collection or a system id other than `0` for batch writes.
Removing a raindrop moves it to Trash; removing it *again from Trash* (or
targeting `-99`) deletes it permanently.

**Verified batch-scope quirk (important, empirically tested 2026-07-18).**
`PUT /raindrops/{cid}` and `DELETE /raindrops/{cid}` with an `ids` body only
affect raindrops **that are actually in `{cid}`** — the `ids` list filters
*within* that path collection, it does not select globally. Consequences:

- Path `cid` must be a real collection (a bogus id 404s).
- Using the **destination** (or a collection the items are not in) as the path
  silently does nothing: `modified: 0`, no error. This is a footgun.
- So there is no "move/delete these ids wherever they live" batch call. In
  rd-cli, **id-lists loop the single-item endpoints** (`PUT`/`DELETE
  /raindrop/{id}`, which carry no collection scope and always work), and the
  batch endpoints are reserved for **collection/search scope** (move or delete
  "everything in collection X matching search Y" in one call). See `cmd_mv` /
  `cmd_rm` in `commands.py`.

## Endpoint map (and the client method that wraps it)

### Raindrops (single) `→ client.py`

| Method / path                          | Client method            |
| -------------------------------------- | ------------------------ |
| `GET /raindrop/{id}`                    | `get_raindrop`           |
| `POST /raindrop`                        | `create_raindrop`        |
| `PUT /raindrop/{id}`                    | `update_raindrop`        |
| `DELETE /raindrop/{id}`                 | `delete_raindrop` (two-step when `permanent`) |
| `PUT /raindrop/file` (multipart)        | `upload_file`            |
| `PUT /raindrop/{id}/cover` (multipart)  | `upload_cover`           |
| `POST /raindrop/suggest`                | `suggest_new`            |
| `GET /raindrop/{id}/suggest`            | `suggest_existing`       |

Create/update body is built by `_raindrop_payload()`. Key fields: `link`
(required on create), `title`, `excerpt` (max 10000), `note` (max 10000),
`tags` (array), `important` (bool), `collection` as `{"$id": id}` (from the
`collection_id` kwarg), `pleaseParse: {}` to trigger background metadata fetch
(from `please_parse=True`), plus `cover`, `type`, `order`, `media`, `highlights`,
`reminder`.

### Raindrops (multiple)

| Method / path                              | Client method       |
| ------------------------------------------ | ------------------- |
| `GET /raindrops/{cid}`                      | `get_raindrops` / `iter_raindrops` |
| `POST /raindrops` (max 100 items)           | `create_raindrops`  |
| `PUT /raindrops/{cid}`                       | `update_raindrops`  |
| `DELETE /raindrops/{cid}`                    | `delete_raindrops`  |
| `GET /raindrops/{cid}/export.{fmt}`          | `export`            |

Query params: `search` (Raindrop's [search grammar](https://help.raindrop.io/using-search)),
`sort` (`-created` default, `created`, `title`, `-title`, `domain`, `-domain`,
`score` when searching, `-sort`), `page`, `perpage` (max 50), `nested`.
Batch update appends tags; `tags: []` clears them. Move via `collection:
{"$id": id}`.

### Collections

| Method / path                        | Client method             |
| ------------------------------------ | ------------------------- |
| `GET /collections`                    | `get_collections` (roots) |
| `GET /collections/childrens`          | `get_child_collections`   |
| `GET /collection/{id}`                | `get_collection`          |
| `POST /collection`                    | `create_collection`       |
| `PUT /collection/{id}`                | `update_collection`       |
| `DELETE /collection/{id}`             | `delete_collection`       |
| `DELETE /collections` (body `ids`)    | `delete_collections`      |
| `PUT /collections` (`sort`)           | `reorder_collections`     |
| `PUT /collections` (`expanded`)       | `expand_collections`      |
| `PUT /collections/merge`              | `merge_collections`       |
| `PUT /collections/clean`              | `clean_collections`       |
| `DELETE /collection/-99`              | `empty_trash`             |
| `PUT /collection/{id}/cover` (multipart) | `upload_collection_cover` |
| `GET /collections/covers/{text}`      | `search_covers`           |
| `GET /collections/covers`             | `featured_covers`         |

Fields: `title`, `view` (`list`/`simple`/`grid`/`masonry`), `sort` (int order),
`public` (bool), `parent` as `{"$id": id}` (from `parent_id`), `expanded`,
`cover`. Nested structure: root order lives in the user object's `groups[]`;
child order lives in each collection's `sort`. `format_collection_tree()`
reconstructs the tree from `parent.$id` links.

### Tags

| Method / path                      | Client method  |
| ---------------------------------- | -------------- |
| `GET /tags[/{cid}]`                 | `get_tags`     |
| `PUT /tags[/{cid}]` (rename/merge)  | `rename_tag` / `merge_tags` |
| `DELETE /tags[/{cid}]`              | `delete_tags`  |

Rename is merge with one source tag: body `{"replace": new, "tags": [...]}`.
Optional `{cid}` restricts the action to one collection.

### Highlights `→ live on the raindrop`

Highlights are edited by `PUT /raindrop/{id}` with a `highlights` array:

- **Add**: `{"highlights": [{"text": ..., "color": ..., "note": ...}]}`
- **Update**: include the highlight's `_id` plus changed fields.
- **Remove**: include `_id` with `text: ""`.

Client: `add_highlight`, `update_highlight`, `delete_highlight`,
`get_raindrop_highlights`. Account-wide reads: `GET /highlights[/{cid}]` →
`get_all_highlights` / `get_collection_highlights` / `iter_highlights` (perpage
max 50, default 25). Colours: blue, brown, cyan, gray, green, indigo, orange,
pink, purple, red, teal, yellow (default yellow).

### User / filters / stats

| Method / path            | Client method       |
| ------------------------ | ------------------- |
| `GET /user`               | `get_user`         |
| `GET /user/{name}`        | `get_user_by_name` |
| `PUT /user`               | `update_user`      |
| `GET /user/stats`         | `get_stats`        |
| `GET /filters/{cid}`      | `get_filters`      |

`get_user` returns `_id`, `email`, `fullName`, `pro`, `groups`, `files`, etc.
`update_user` (CLI `rd user set`) takes `fullName`, `email`, `config` (dict),
`groups`, and `newpassword`+`oldpassword`; only non-`None` fields are sent.
`get_stats` returns per-system-collection counts plus `meta` (pro, duplicates,
broken). `get_filters` returns context counts (broken, duplicates, important,
notag) and `tags`/`types` breakdowns; `tagsSort` is `-count` (default) or `_id`.
Not wrapped (deliberately, low personal value): sharing/collaborator endpoints
and the permanent-copy/cache PRO endpoint.

### Import / export / backups

| Method / path                       | Client method       |
| ----------------------------------- | ------------------- |
| `GET /import/url/parse`              | `parse_url`         |
| `POST /import/url/exists`            | `check_urls_exist`  |
| `POST /import/file` (multipart)      | `parse_import_file` |
| `GET /raindrops/{cid}/export.{fmt}`  | `export` (csv/html/zip) |
| `GET /backups`                       | `get_backups`       |
| `GET /backup`                        | `generate_backup`   |
| `GET /backup/{id}.{fmt}`             | `download_backup`   |

`check_urls_exist` is the dedup primitive: returns `{"result", "ids"}` for URLs
already saved. `generate_backup` triggers an emailed export (async). Export and
backup downloads return raw bytes (`expect_json=False`).

## CLI command surface

Raindrop verbs are top-level (the 80% path); everything else is grouped
noun→verb. The original flat commands (`c-list`, `c-add`, `c-rm`, `t-list`,
`t-rm`, `h-list`, `h-add`, `h-rm`) survive as hidden back-compat aliases; keep
them working.

```
rd list | search | view | add | edit | rm | mv | tag | cover | import | export
rd collections (c)  list|tree|view|add|edit|rm|merge|clean|empty-trash|reorder|cover|covers
rd tags (t)         list|rename|merge|rm
rd highlights (h)   list|add|edit|rm
rd user [show|set] | stats | filters | suggest | exists
rd backups          list|create|download
rd pinboard (pb)    list|get|add|rm|edit|tag|suggest ; tags list|rename|rm ; notes list|view
rd sync             two-way additive Raindrop<->Pinboard sync (--dry-run, scoping)
rd config           path|show|set-token|set-pinboard-token
```

The `pinboard` group is dispatched to a `PinboardClient` (not the Raindrop
client): `cli.main()` builds one when a subparser carries `needs_pinboard`
(set by the `_pb` helper), resolving the token via `config.resolve_pinboard_token`.

`rd sync` (`commands.cmd_sync`, `needs_client=False`) builds *both* clients
itself and drives `sync.py`. The planner (`sync.plan_sync` + the mapping helpers)
is pure and network-free; only `sync.apply_plan` writes. It is **additive only**
(adds + merges, never deletes), matches by `sync.normalize_url` (which is also
the dedup key), and bridges the model gap reversibly in tags (collection <-> slug
tag, `toread`, `important`). Scope flags (`--direction`, `--collection`,
`--rd-tag`, `--pb-tag`) narrow what is *written* while matching stays on the full
sets, so an out-of-scope item already present on the other side is never
re-imported. Delete propagation / conflict resolution (needs a persistent
manifest) is deliberately not built; see `roadmap.md` Phase 6.

Global: `--json` (any position), `--no-color`, `--version`, and **`--dry-run`**
(logs the method + payload of every write to stderr and skips the API call;
reads still run so plans can be built). `--dry-run` is enforced centrally in
`RaindropClient._request` for any non-GET method, so it covers every write
command automatically.

**Bulk commands and the id-list vs scope split** (this is the important part,
grounded in the verified batch-scope quirk above):

- `rd mv <dest> <ids...>` and `rd rm <ids...>` and `rd tag <ids...>` operate on
  **explicit ids by looping the single-item endpoints** — correct no matter
  which collection each id lives in.
- The same commands in **scope mode** (`--from <collection>`, optional `-s
  <search>`, `-n`) use the **batch endpoints** to move/delete/tag *everything in
  a source collection* in one call. `--from` is required for scope (batch does
  not accept `0`).
- `rd tag` id-mode does precise add/remove/clear (it GETs current tags, computes
  the new set, PUTs). Scope-mode can only append (`--add`) or clear-all
  (`--clear`); to strip one tag everywhere use `rd tags rm <tag>`.
- `rd rm --permanent` deletes for good via the documented two-step (to Trash,
  then from Trash); the undocumented `?permanent=true` was tested and does *not*
  one-shot a live raindrop.
- `rd add --file <f>` / `--stdin` batch-creates (chunks of 100, the API cap).
- `rd import <file>` parses a Netscape/Pocket/Instapaper HTML export to JSON;
  add `--create -c <collection>` to actually import it.

Note: values that start with `-` (the `-count`/`-title` sort keys) must use
`=` with argparse, e.g. `rd collections reorder --by=-count`.

## Exit codes

`0` success, `1` handled error (`RaindropError`, or a false `result`), `130`
`KeyboardInterrupt`. Broken pipe exits `0` (clean `| head`).

---

# Pinboard API v1 reference

Base URL: `https://api.pinboard.in/v1`. Wrapped by `PinboardClient` in
`pinboard.py`. Only what rd-cli relies on is summarized here.

## Auth and format

- **Token in the query string**, not a header: `?auth_token=user:HEX`. The token
  (format `username:HEX`) is at https://pinboard.in/settings/password; requesting
  a new one invalidates the old. rd-cli also accepts HTTP Basic in principle, but
  only the token path is wired.
- **`format=json`** is added to every call (Pinboard defaults to XML).
- Resolution order mirrors Raindrop: `PINBOARD_TOKEN` / `PINBOARD_API_TOKEN`
  env, then `pinboard_token` in `config.toml`, then `.env`.

## Conventions and gotchas

- **Every endpoint is a GET**, including the mutating ones (`posts/add`,
  `posts/delete`, `tags/rename`, `tags/delete`). So `--dry-run` cannot key off
  the HTTP method: `_request` takes an explicit `write=True` for the mutators.
- **Bookmarks are keyed by URL.** There are no numeric ids and **no collections**
  (tags are the only organization). A `hash` field identifies content but rd-cli
  addresses bookmarks by their `url`.
- **No update endpoint.** An edit is a re-`add` of the same URL with
  `replace=yes`. `PinboardClient.edit_post` does the read-modify-write so a
  partial edit keeps the untouched fields.
- **Strict rate limit**: about one call every 3 seconds, `posts/all` once per 5
  minutes, `posts/recent` once per minute; `429` on breach. `PinboardClient`
  paces itself with `min_interval` (default 3.0s, via the injectable `clock`)
  on top of `429`/`5xx` backoff.
- **No full-text search** in the API. Filtering is by `tag` (up to 3) and date
  only. `rd pinboard list --tag` is the filter path.
- Write responses carry `{"result_code": "done"}` (or `{"result": "done"}` for
  tags); `_check` raises `APIError` on anything else (e.g. "item already exists").
- Tags are space-joined in requests and space-separated in responses; a tag may
  not contain a space or comma. `tags/get` returns counts as strings.

## Endpoint map (and the client method that wraps it)

| Method / path            | Client method     | Notes |
| ------------------------ | ----------------- | ----- |
| `GET /posts/update`       | `last_update`     | last change timestamp (cheap; for a future sync) |
| `GET /posts/all`          | `get_all`         | array of posts; 5-min limit |
| `GET /posts/recent`       | `get_recent`      | `{posts:[...]}`; `count` max 100 |
| `GET /posts/get`          | `get_post`        | one URL; `None` if unsaved |
| `GET /posts/add`          | `add_post` (write)| fields below |
| `GET /posts/delete`       | `delete_post` (write) | by `url` |
| `GET /posts/suggest`      | `suggest_tags`    | `{popular, recommended}` |
| `GET /tags/get`           | `get_tags`        | `{tag: count}` |
| `GET /tags/rename`        | `rename_tag` (write) | `old`, `new` |
| `GET /tags/delete`        | `delete_tag` (write) | one `tag` per call |
| `GET /notes/list`         | `list_notes`      | metadata only |
| `GET /notes/{id}`         | `get_note`        | full text |

Bookmark fields on `posts/add`: `url`, `description` (title, max 255), `extended`
(note, max 65536), `tags` (space-joined, max 100), `dt` (UTC ISO 8601),
`replace` (yes/no, default yes), `shared` (yes/no), `toread` (yes/no).

## Not wrapped (deliberately)

`posts/dates`, `user/secret`, `user/api_token`, and note *creation* (Pinboard has
no note-write endpoint). A cross-service `rd sync` is on the roadmap, not built.
