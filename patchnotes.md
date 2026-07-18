# Patch notes

Newest at the top.

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
