# rd-cli specification

The contract for `rd`, a stdlib-only command-line client for Raindrop.io. This
document defines behavior that callers (humans and scripts) may rely on. The
API-side reference (endpoints, fields, quirks) lives in `CLAUDE.md`; this file
covers the CLI contract.

Version: see `VERSION`. Status: `0.1.0`, the first framework release.

## Goals

- A fast, dependency-free CLI for the Raindrop.io API surface a single user
  needs day to day: raindrops, collections, tags, highlights, and the
  account-level endpoints (user, stats, filters, suggestions, dedup, export,
  backups).
- Dual output: designed ANSI for humans, `--json` for scripts and AI agents.
- Correct, resilient HTTP: timeouts, typed errors carrying the API's message,
  rate-limit and 5xx retry with backoff.
- No third-party runtime dependencies.

## Non-goals (this version)

- OAuth2 server flow and token refresh (test token only for now).
- Collaboration/sharing endpoints and destructive `PUT /user` changes.
- A TUI, shell completion, or a config-profile system.
- Sharing/collaborator endpoints and the permanent-copy/cache PRO endpoint.
- Interactive confirmation prompts (bulk safety is via `--dry-run` for now).

## Authentication

The token is resolved by `config.resolve_token()` in this order; first hit wins:

1. `RAINDROP_TOKEN` environment variable.
2. `RAINDROP_TEST_TOKEN` environment variable (back-compat alias).
3. `token` key in `$XDG_CONFIG_HOME/rd-cli/config.toml`
   (default `~/.config/rd-cli/config.toml`).
4. `RAINDROP_TOKEN` / `RAINDROP_TEST_TOKEN` in a `.env` file: `./.env` first,
   then `$XDG_CONFIG_HOME/rd-cli/.env`.

Real environment variables always win over `.env` (the reader is
non-clobbering). `rd config set-token <token>` writes the config file with
`0600` permissions. If no token is found, the CLI exits `1` with a message
pointing at the integrations page. Commands that do not touch the network
(`rd config *`) never require a token.

## Output contract

### Human mode (default, no `--json`)

Rendered to stdout with ANSI colour **only** when: stdout is a TTY, `NO_COLOR`
is unset, and `--no-color` was not passed. When any of those fail, output is
plain text (safe to pipe). Colour is presentation only; the plain text carries
all information. Layout, wording, and colour are **not** part of the stable
contract and may change between versions. Do not parse human output; use
`--json`.

### JSON mode (`--json`)

`--json` may appear before or after the subcommand. Output is a single
UTF-8 JSON document (indented) on stdout, and nothing else. Shapes:

- List commands emit the raw array of API objects (e.g. `list`, `tags list`,
  `highlights list`).
- Single-object commands emit the object (`view`, `add`, `edit`,
  `collections view`).
- Boolean-result commands emit `{"result": <bool>}` (`rm`, `collections rm`,
  `tags rm`, ...).
- Errors emit `{"error": "<message>"}` on stdout and still exit non-zero.

JSON objects are passed through from the API unchanged. Per Raindrop's docs,
responses may contain undocumented fields; do not rely on fields not listed in
`CLAUDE.md`.

## Commands

Raindrop verbs are top-level; other resources are grouped. See `CLAUDE.md` for
the full tree and `rd --help` / `rd <group> --help` for flags. Stable command
names and their meaning:

- `list` / `search` — read raindrops (`--all` paginates; `-c/--collection`,
  `-s/--search`, `--sort`, `--page`, `--perpage`, `-n/--nested`, `-d/--detailed`).
- `view <id>` — one raindrop in detail.
- `add <url>` — create (auto-parses metadata unless `--no-parse`; default
  collection is Unsorted, `-1`). `--file`/`--stdin` batch-creates many URLs.
- `edit <id>` — update fields (`--important`/`--not-important` tri-state).
- `rm <ids...>` — move to Trash; `--permanent` deletes for good; `--from
  <collection> [-s search]` removes a whole scope in one batch call.
- `mv <dest> <ids...>` — move raindrops; `--from <src> [-s search]` for scope.
- `tag <ids...> --add/--remove/--clear` — modify tags; `--from` for scope.
- `cover <id> <file>` / `import <file> [--create -c <id>]`.
- `export` — write csv/html/zip to a file (`-o`) or stdout.
- `collections` (adds `reorder`, `cover`, `covers`), `tags`, `highlights`
  groups; `user` (with `set`), `stats`, `filters`, `suggest`, `exists`,
  `backups`, `config`.

**id-list vs scope.** `mv`/`rm`/`tag` with explicit ids loop the single-item
endpoints (correct regardless of each item's collection). With `--from` they use
the batch endpoints, which require a real source collection (`0` is unsupported)
and only affect raindrops actually in that scope.

**`--dry-run`** (global) logs the method and payload of every write to stderr
and makes no API call; reads still run, so a plan can be built safely first.

Back-compat aliases `c-list`, `c-add`, `c-rm`, `t-list`, `t-rm`, `h-list`,
`h-add`, `h-rm` remain valid and behave as their grouped equivalents.

## Error and retry behavior

- HTTP `401`/`403` → `AuthError`; `404` → `NotFoundError`; `429` → `RateLimitError`
  after retries are exhausted; other non-2xx → `APIError`. All carry the API's
  `errorMessage` when present.
- `429` retries honor `Retry-After` (integer seconds or an HTTP-date) and
  `X-RateLimit-Reset` (capped at 60s); `5xx` and transient transport errors
  retry with exponential backoff. Retries are bounded (`max_retries`, default
  3). `4xx` other than 429 is never retried.
- Request timeout defaults to 30s.

## Exit codes

| Code | Meaning                                             |
| ---- | --------------------------------------------------- |
| 0    | Success (also: broken pipe, no-args help)           |
| 1    | Handled error (`RaindropError`, or false `result`)  |
| 130  | Interrupted (`KeyboardInterrupt`)                   |
| 2    | argparse usage error (bad flags/args)               |

## Compatibility

- Requires Python 3.11+ (`tomllib`).
- Talks to Raindrop REST API v1 at `https://api.raindrop.io/rest/v1`.
- `VERSION` is the single source of truth; `pyproject.toml` and
  `rd_cli.__version__` derive from it.
