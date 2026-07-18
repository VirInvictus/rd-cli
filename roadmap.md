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

## Considered, not committed

- A TUI (would pull a dependency or a lot of stdlib curses; low value over the
  Raindrop web app).
- Sharing/collaborator commands (little personal value; the web UI covers it).
- Library extraction of `client.py` into a standalone `raindrop` package
  (a post-1.0 call once the surface is stable and a second consumer exists).
