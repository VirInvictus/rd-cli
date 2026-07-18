# Patch notes

Newest at the top.

## 0.3.0

### Added

- **`rd sync`: two-way additive sync between Raindrop and Pinboard.** Matches
  bookmarks across the two services by a *normalized* URL (scheme/`www`/fragment
  folded, tracking params like `utm_*`/`fbclid` stripped, meaningful query kept),
  which doubles as the cross-service dedup key. It only ever adds and merges,
  never deletes, so the two libraries converge to their union with no data loss.
- The model gap is bridged reversibly in tags: a Raindrop collection becomes a
  slugged Pinboard tag, Pinboard's `toread` and Raindrop's `important` ride along
  as tags, and a Pinboard tag that matches a collection routes the item back into
  that collection. Highlights stay Raindrop-only. On a URL that exists on both
  sides, tags are unioned and notes are merged idempotently (no duplication on
  repeat runs).
- **Scoping** so you never have to union everything at once: `--direction
  both|to-pinboard|to-raindrop`, and `--collection`/`--rd-tag`/`--pb-tag` to
  restrict which items are pushed. Scope narrows what is *written*, but matching
  always uses the full sets, so an out-of-scope item that already exists on the
  other side is never re-imported as a duplicate.
- `--dry-run` prints the plan (counts per direction, near-dupes collapsed) and
  writes nothing. The planning half (`sync.plan_sync` and the mapping helpers)
  is pure and covered by unit tests independent of the network.

## 0.2.0

### Added

- **Pinboard as a second bookmarking backend**, alongside Raindrop. A new `rd
  pinboard` (alias `pb`) command group speaks Pinboard's flat model natively
  (bookmarks keyed by URL, tags, notes, and the `toread`/`shared` flags) instead
  of pretending it has Raindrop's collections: `pinboard list|get|add|rm|edit|
  tag|suggest`, `pinboard tags list|rename|rm`, and `pinboard notes list|view`.
- `PinboardClient`, a stdlib sibling of `RaindropClient`: auth through the
  `auth_token` query param, `format=json` on every call, a minimum inter-request
  pacer for Pinboard's strict rate limit (about one call every three seconds) on
  top of the usual `429` backoff, and the shared typed-error family plus
  `--dry-run` and `--json` behavior. Pinboard writes are all GETs, so they are
  flagged explicitly rather than inferred from the HTTP method.
- Pinboard token resolution mirrors Raindrop: `PINBOARD_TOKEN` (or
  `PINBOARD_API_TOKEN`) env var, `pinboard_token` in `config.toml`, or a `.env`
  file; `rd config set-pinboard-token <token>` writes it (0600). Both service
  tokens coexist in the one config file without clobbering each other.
- Pinboard has no update endpoint, so `edit` and `tag` are a read-modify-write:
  fetch the bookmark, merge the change, and re-save with `replace=yes`, leaving
  untouched fields intact.

## 0.1.1

### Fixed

- `--dry-run` no longer mislabels a bodyless request as `<multipart>`. A plain
  DELETE or PUT with no body now previews as `<no body>`, JSON writes preview as
  their JSON (unchanged), and multipart uploads preview as
  `<multipart ... files=[...]>` without dumping the raw file bytes. Extracted the
  logic into `_dry_run_preview` with direct unit coverage.

## 0.1.0

The framework rebuild. The barebones prototype became a dependency-free,
tested, fully documented CLI.

### Added

- Complete API coverage: raindrops (single, batch, suggest, file/cover upload,
  export), collections (list, tree, view, add, edit, remove, merge, clean,
  empty-trash, reorder, cover, cover search), tags (list, rename, merge,
  remove), highlights (list, add, edit, remove), plus `user` (show + `set`),
  `stats`, `filters`, `suggest`, `exists` (import dedup), HTML-file import, and
  `backups` (list, create, download).
- Bulk/reorganization commands: `rd mv`, multi-id and scope `rd rm`
  (`--permanent`), `rd tag` (add/remove/clear), and `rd add --file/--stdin` for
  batch create. Explicit ids loop the single-item endpoints; `--from
  <collection>` uses the batch endpoints for whole-collection scope. (Grounded
  in an empirically verified quirk: the batch endpoints only touch raindrops
  actually in the path collection, so a naive id-based batch move silently
  no-ops. Two other CLIs surveyed carry exactly that latent bug.)
- `--dry-run`: previews every write (logs method + payload to stderr) without
  calling the API; reads still run so a plan can be built first.
- Grouped command surface (`rd collections tree`, `rd tags rename`,
  `rd highlights add`, ...) with `c`/`t`/`h` short aliases, keeping the original
  flat commands (`c-list`, `t-list`, `h-list`, ...) working as hidden aliases.
- `--all` to auto-paginate list and highlight reads.
- `rd config path|show|set-token`; token also resolvable from
  `~/.config/rd-cli/config.toml` and `.env`, with `RAINDROP_TOKEN` as the
  primary env var (`RAINDROP_TEST_TOKEN` still honored).
- TTY-aware ANSI output (Kanagawa-ish palette): colour on a terminal, plain when
  piped, `NO_COLOR` and `--no-color` respected. Nested collection tree view and
  aligned tag/collection columns.
- `--version`, and `--json` now works before or after the subcommand.
- pytest suite exercising the client, config, output, and CLI against a fake
  urllib transport (no network); ruff lint/format configured.
- Framework docs: comprehensive `CLAUDE.md` (Raindrop API + codebase), `spec.md`,
  `roadmap.md`, `logo.svg`, single-source `VERSION`.

### Changed

- Ported the whole client from `requests` to stdlib `urllib`; removed the
  `requests` and `python-dotenv` dependencies (zero runtime deps now).
- Split the two-file prototype into a package: `errors`, `config`, `client`,
  `output`, `commands`, `cli`.
- `add` now auto-parses page metadata by default (title, cover, type) unless
  `--no-parse`; default target collection is Unsorted.

### Fixed

- Requests now use a timeout (previously could hang forever).
- Boolean query params are sent lowercase (`nested=true`); the API rejected the
  previous `True`/`False`.
- API error messages surface to the user (the `errorMessage` from the response)
  instead of a bare HTTP status.
- Rate-limit (`429`) and transient `5xx` responses retry with backoff instead of
  failing immediately (`Retry-After` parsed as seconds or an HTTP-date).
- `rm --permanent` uses the documented two-step delete; the undocumented
  `?permanent=true` query param was tested and does not one-shot a live
  raindrop.
- Removed a hard-coded personal `.env` path that leaked into the repo.
