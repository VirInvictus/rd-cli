"""``PinboardClient`` — a stdlib-only wrapper over the Pinboard API v1
(https://api.pinboard.in/v1).

Sibling to :class:`rd_cli.client.RaindropClient`, and deliberately the same
shape (one ``_request`` chokepoint, injectable ``opener``/``sleep`` for tests,
the shared typed-error family), but adapted to Pinboard's realities:

- **Auth is a query parameter**, ``auth_token=user:HEX`` (not a Bearer header).
- **Every endpoint is a GET**, including the mutating ones, so writes are marked
  with ``write=True`` rather than inferred from the HTTP method (that is what
  ``--dry-run`` keys off).
- **JSON is opt-in** via ``format=json`` on every call.
- **The rate limit is strict** (one call per ~3s, ``posts/all`` once per 5 min),
  so the client paces itself with a minimum inter-request interval on top of the
  usual ``429`` backoff.

Pinboard's data model is flat: bookmarks keyed by URL (there are no numeric ids
and no collections), tags, and notes. There is no full-text search endpoint;
filtering is by tag and date only.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from . import __version__
from .client import _backoff, _encode_params, _to_api_error
from .errors import APIError

BASE_URL = "https://api.pinboard.in/v1"
USER_AGENT = f"rd-cli/{__version__} (+https://github.com/VirInvictus/rd-cli)"

# Pinboard asks for at least three seconds between calls for most endpoints.
MIN_INTERVAL = 3.0


class PinboardClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 3,
        min_interval: float = MIN_INTERVAL,
        dry_run: bool = False,
        opener: urllib.request.OpenerDirector | None = None,
        sleep=time.sleep,
        clock=time.monotonic,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval = min_interval
        self.dry_run = dry_run
        self._opener = opener or urllib.request.build_opener()
        self._sleep = sleep
        self._clock = clock
        self._last_call: float | None = None

    # -- core -----------------------------------------------------------------

    def _request(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        write: bool = False,
    ) -> Any:
        query = dict(params or {})
        query["auth_token"] = self.token
        query["format"] = "json"

        if self.dry_run and write:
            shown = dict(params or {})
            print(f"DRY RUN GET {path} {json.dumps(shown)}", file=sys.stderr)
            return {"result_code": "done", "result": "done"}

        url = f"{self.base_url}{path}?{_encode_params(query)}"
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        req = urllib.request.Request(url, headers=headers, method="GET")

        attempt = 0
        while True:
            self._pace()
            try:
                with self._opener.open(req, timeout=self.timeout) as resp:
                    body = resp.read()
                self._last_call = self._clock()
                return json.loads(body) if body else {}
            except urllib.error.HTTPError as exc:
                self._last_call = self._clock()
                if (
                    exc.code == 429 or 500 <= exc.code < 600
                ) and attempt < self.max_retries:
                    self._sleep(_backoff(attempt))
                    attempt += 1
                    continue
                raise _to_api_error(exc) from exc
            except urllib.error.URLError as exc:
                if attempt < self.max_retries:
                    self._sleep(_backoff(attempt))
                    attempt += 1
                    continue
                raise APIError(f"Network error: {exc.reason}") from exc

    def _pace(self) -> None:
        """Sleep so consecutive calls are at least ``min_interval`` apart."""
        if self._last_call is None or self.min_interval <= 0:
            return
        elapsed = self._clock() - self._last_call
        if elapsed < self.min_interval:
            self._sleep(self.min_interval - elapsed)

    @staticmethod
    def _check(data: dict) -> dict:
        """Raise if a write response is not ``done``; else return it."""
        code = data.get("result_code") or data.get("result")
        if code and code != "done":
            raise APIError(str(code))
        return data

    # -- posts ----------------------------------------------------------------

    def last_update(self) -> str:
        """Timestamp of the most recent bookmark change (cheap, for sync)."""
        return self._request("/posts/update").get("update_time", "")

    def get_all(
        self,
        *,
        tags: list[str] | None = None,
        start: int | None = None,
        results: int | None = None,
        fromdt: str = "",
        todt: str = "",
    ) -> list[dict]:
        """All bookmarks (rate-limited to once per five minutes)."""
        params: dict[str, Any] = {}
        if tags:
            params["tag"] = " ".join(tags)
        if start is not None:
            params["start"] = start
        if results is not None:
            params["results"] = results
        if fromdt:
            params["fromdt"] = fromdt
        if todt:
            params["todt"] = todt
        data = self._request("/posts/all", params=params or None)
        return data if isinstance(data, list) else data.get("posts", [])

    def get_recent(
        self, *, tags: list[str] | None = None, count: int = 15
    ) -> list[dict]:
        params: dict[str, Any] = {"count": min(count, 100)}
        if tags:
            params["tag"] = " ".join(tags)
        return self._request("/posts/recent", params=params).get("posts", [])

    def get_post(self, url: str, *, meta: bool = True) -> dict | None:
        """The bookmark for ``url``, or ``None`` if it is not saved."""
        params: dict[str, Any] = {"url": url}
        if meta:
            params["meta"] = "yes"
        posts = self._request("/posts/get", params=params).get("posts", [])
        return posts[0] if posts else None

    def add_post(
        self,
        url: str,
        title: str,
        *,
        extended: str = "",
        tags: list[str] | None = None,
        dt: str = "",
        replace: bool = True,
        shared: bool | None = None,
        toread: bool | None = None,
    ) -> dict:
        params: dict[str, Any] = {"url": url, "description": title}
        if extended:
            params["extended"] = extended
        if tags:
            params["tags"] = " ".join(tags)
        if dt:
            params["dt"] = dt
        params["replace"] = "yes" if replace else "no"
        if shared is not None:
            params["shared"] = "yes" if shared else "no"
        if toread is not None:
            params["toread"] = "yes" if toread else "no"
        return self._check(self._request("/posts/add", params=params, write=True))

    def delete_post(self, url: str) -> dict:
        return self._check(
            self._request("/posts/delete", params={"url": url}, write=True)
        )

    def suggest_tags(self, url: str) -> dict:
        """``{"popular": [...], "recommended": [...]}`` for ``url``."""
        raw = self._request("/posts/suggest", params={"url": url})
        out: dict[str, list[str]] = {"popular": [], "recommended": []}
        for group in raw if isinstance(raw, list) else []:
            for key in out:
                if key in group:
                    out[key] = group[key]
        return out

    # -- tags -----------------------------------------------------------------

    def get_tags(self) -> dict[str, int]:
        """Map of tag -> count (Pinboard returns the counts as strings)."""
        raw = self._request("/tags/get")
        return {tag: int(count) for tag, count in raw.items()}

    def rename_tag(self, old: str, new: str) -> dict:
        return self._check(
            self._request("/tags/rename", params={"old": old, "new": new}, write=True)
        )

    def delete_tag(self, tag: str) -> dict:
        return self._check(
            self._request("/tags/delete", params={"tag": tag}, write=True)
        )

    # -- notes ----------------------------------------------------------------

    def list_notes(self) -> list[dict]:
        return self._request("/notes/list").get("notes", [])

    def get_note(self, note_id: str) -> dict:
        return self._request(f"/notes/{note_id}")

    # -- convenience (Pinboard has no PUT; edits re-add with replace) ---------

    def edit_post(self, url: str, **changes: Any) -> dict:
        """Fetch ``url``, apply ``changes`` (title, extended, tags, shared,
        toread), and re-add it with ``replace=yes``. Pinboard has no update
        endpoint, so a partial edit is a read-modify-write."""
        current = self.get_post(url)
        if current is None:
            raise APIError(f"not saved: {url}")
        title = changes.get("title")
        if title is None:
            title = current.get("description", "")
        extended = changes.get("extended")
        if extended is None:
            extended = current.get("extended", "")
        tags: list[str]
        if "tags" in changes and changes["tags"] is not None:
            tags = list(changes["tags"])
        else:
            tags = str(current.get("tags") or "").split()
        shared = changes.get("shared")
        if shared is None:
            shared = current.get("shared") == "yes"
        toread = changes.get("toread")
        if toread is None:
            toread = current.get("toread") == "yes"
        return self.add_post(
            url,
            title,
            extended=extended,
            tags=tags,
            replace=True,
            shared=shared,
            toread=toread,
        )
