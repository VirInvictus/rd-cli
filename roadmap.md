# rd-cli roadmap

Newest phases at the bottom. Tick boxes when shipped.

## Phase 0: barebones prototype (pre-framework)

- [x] Initial `requests`-based `api.py` + `cli.py` (list/add/edit/rm,
      collections, tags, highlights). No tests, no docs.

## Phase 1: framework rebuild (v0.1.0)

The current release. Made it correct, dependency-free, and conformant to the
portfolio conventions.

- [x] Port to stdlib `urllib`; drop `requests` and `python-dotenv` (zero
      runtime deps).
- [x] `RaindropClient` core: single `_request`, request timeouts, boolean-param
      lowercasing, typed errors carrying the API `errorMessage`.
- [x] Rate-limit (`429`) and `5xx` retry with bounded backoff.
- [x] Token/config resolution: env, `config.toml`, `.env`; `rd config`.
      Removed the hard-coded personal `.env` path.
- [x] Full API coverage: raindrops (single + batch + suggest + upload + export),
      collections (tree/merge/clean/empty-trash/reorder), tags (rename/merge/rm),
      highlights (list/add/edit/rm), user, stats, filters, import-dedup, backups.
- [x] Pagination generators + `--all`.
- [x] TTY-aware ANSI output (colour off when piped, `NO_COLOR`/`--no-color`),
      tree and aligned-column renderers.
- [x] `--json` works in any position; consistent JSON contract.
- [x] Grouped command surface with hidden back-compat aliases.
- [x] pytest suite over a fake urllib transport (no network); ruff configured.
- [x] Docs: `CLAUDE.md` (API + codebase), `spec.md`, `README.md`, `logo.svg`,
      `VERSION`, this roadmap, patchnotes.
- [x] Bulk/reorg commands (pulled forward after mining prior-art CLIs):
      `mv`, multi-id/scope `rm` (`--permanent`), `tag` (add/remove/clear),
      `add --file/--stdin`, `collections reorder`. Grounded in an empirically
      verified batch-scope quirk (id-lists loop single-item endpoints; scope
      mode uses the batch endpoints; see `CLAUDE.md`).
- [x] `--dry-run` (log method + payload, skip the call) on every write.
- [x] Extra endpoints: raindrop/collection cover upload, icon/cover search,
      HTML-file import (`rd import`), and user-settings edit (`rd user set`).

## Phase 2: authentication and convenience (planned)

- [ ] OAuth2 3-legged flow (`rd auth login`): local redirect catcher, code
      exchange, token + refresh_token stored in `config.toml`.
- [ ] Automatic token refresh on `401` when a refresh token is present.
- [ ] Optional secret storage via the Secret Service (`oo7`/keyring) instead of
      plaintext `config.toml` (ask before adding the dep).
- [ ] `rd open <id>` to launch a raindrop (or its permanent copy) in the browser.

## Phase 3: batch and power features (mostly shipped in Phase 1)

- [x] CLI batch commands (`rd mv`, `rd tag`, multi-id `rm`) mapped to the client
      batch methods, plus `--dry-run` as the safety guard.
- [x] `rd import <file>` (Netscape/Pocket/Instapaper) via `POST /import/file`.
- [x] Collection cover upload / icon search commands.
- [ ] Interactive confirmation prompt for large destructive scope operations
      (currently guarded only by `--dry-run`).
- [ ] `--fields` projection for `--json` output; `--format` templates for human
      output.
- [ ] A `rd context`/`--schema` dump (whole tree + data-model schema) as an
      agent affordance (seen in kyoji2/raindrip).

## Phase 4: ergonomics (planned)

- [ ] Shell completion (bash/zsh/fish) generated from the parser.
- [ ] Config profiles (multiple accounts/tokens).
- [ ] Optional interactive picker (fzf-style) behind a flag, still dependency-free.

## Phase 5: a second backend, Pinboard (v0.2.0)

Turned rd-cli from a Raindrop client into a two-service bookmark CLI, reusing
the existing HTTP/output/config machinery.

- [x] `PinboardClient`: stdlib `urllib`, `auth_token` query-param auth,
      `format=json`, a minimum inter-request pacer for Pinboard's rate limit
      (~1 call / 3s), `429`/`5xx` backoff, and the shared typed errors.
- [x] `rd pinboard` (alias `pb`) command group honest to Pinboard's flat model
      (URL as key, no collections): `list`, `get`, `add`, `rm`, `edit`, `tag`,
      `suggest`, `tags list|rename|rm`, `notes list|view`.
- [x] Read-modify-write `edit`/`tag` (Pinboard has no update endpoint).
- [x] Pinboard token resolution + `rd config set-pinboard-token`; both service
      tokens coexist in `config.toml`.
- [x] `--dry-run` and `--json` across the Pinboard surface; pytest coverage
      against the fake transport (auth params, pacing, retry, read-modify-write).
- [x] Cross-service sync landed in Phase 6 (below).

## Phase 6: cross-service sync (v0.3.0)

`rd sync` between Raindrop and Pinboard, built additive-first for safety.

- [x] URL normalization as the match + dedup key (fold scheme/`www`/fragment,
      strip tracking params, keep meaningful query).
- [x] Two-way **additive** sync (adds + merges, never deletes); the two
      libraries converge to their union.
- [x] Reversible model-gap encoding in tags (collection <-> slug tag, `toread`,
      `important`); notes merged idempotently; tags unioned on a shared URL.
- [x] Scoping: `--direction`, `--collection`, `--rd-tag`, `--pb-tag`. Scope
      narrows what is written; matching uses the full sets (no re-import of an
      out-of-scope item that already exists on the other side).
- [x] `--dry-run` plan preview; pure, unit-tested planner.
- [ ] Delete propagation + conflict resolution via a persistent manifest
      (three-way diff). Deferred: it needs stored sync state and carries real
      data-loss risk (Pinboard deletes are permanent).
- [ ] A `--reconcile-dupes` pass that merges near-duplicate URLs *within* a
      single service, not just across the two.

## Considered, not committed

- A TUI (would pull a dependency or a lot of stdlib curses; low value over the
  Raindrop web app).
- Sharing/collaborator commands (little personal value; the web UI covers it).
- Library extraction of `client.py` into a standalone `raindrop` package
  (a post-1.0 call once the surface is stable and a second consumer exists).
