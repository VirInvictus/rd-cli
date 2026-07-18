"""``RaindropClient`` — a thin, dependency-free wrapper over the Raindrop.io
REST API v1 (https://api.raindrop.io/rest/v1).

Everything goes through :meth:`RaindropClient._request`, which is the single
place that attaches the auth header, applies a timeout, JSON-encodes bodies,
lowercases boolean query params (the API rejects Python's ``True``/``False``),
retries on ``429``/``5xx``, and maps error responses to the typed exceptions in
:mod:`rd_cli.errors`. The per-endpoint methods below are deliberately small so
this class can later graduate into a standalone client library.

The constructor accepts an ``opener`` and ``sleep`` so tests can inject a fake
transport and avoid real network / real waiting.
"""

from __future__ import annotations

import calendar
import email.utils
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Any

from . import __version__
from .errors import APIError, AuthError, NotFoundError, RateLimitError

BASE_URL = "https://api.raindrop.io/rest/v1"
USER_AGENT = f"rd-cli/{__version__} (+https://github.com/VirInvictus/rd-cli)"

# System collection ids (see CLAUDE.md).
ALL = 0
UNSORTED = -1
TRASH = -99

PERPAGE_MAX = 50


class RaindropClient:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 3,
        dry_run: bool = False,
        opener: urllib.request.OpenerDirector | None = None,
        sleep=time.sleep,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.dry_run = dry_run
        self._opener = opener or urllib.request.build_opener()
        self._sleep = sleep

    # -- core -----------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        form: dict[str, str] | None = None,
        expect_json: bool = True,
    ) -> Any:
        url = self.base_url + path
        query = _encode_params(params)
        if query:
            url = f"{url}?{query}"

        data: bytes | None = None
        headers = {
            "Authorization": f"Bearer {self.token}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if files is not None:
            data, content_type = _multipart(files, form or {})
            headers["Content-Type"] = content_type
        elif json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        if self.dry_run and method != "GET":
            preview = json_body if json_body is not None else (form or "<multipart>")
            print(f"DRY RUN {method} {path} {json.dumps(preview)}", file=sys.stderr)
            return {"result": True, "item": {}, "items": [], "modified": 0, "count": 0}

        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        attempt = 0
        while True:
            try:
                with self._opener.open(req, timeout=self.timeout) as resp:
                    body = resp.read()
                if not expect_json:
                    return body
                return json.loads(body) if body else {}
            except urllib.error.HTTPError as exc:
                retry_after = self._retry_wait(exc, attempt)
                if retry_after is not None and attempt < self.max_retries:
                    self._sleep(retry_after)
                    attempt += 1
                    continue
                raise _to_api_error(exc) from exc
            except urllib.error.URLError as exc:
                if attempt < self.max_retries:
                    self._sleep(_backoff(attempt))
                    attempt += 1
                    continue
                raise APIError(f"Network error: {exc.reason}") from exc

    def _retry_wait(self, exc: urllib.error.HTTPError, attempt: int) -> float | None:
        """Return seconds to wait before retrying, or ``None`` if not retryable."""
        if exc.code == 429:
            header = exc.headers.get("Retry-After")
            if header:
                if header.strip().isdigit():
                    return min(float(header), 60.0)
                # Retry-After may also be an HTTP-date.
                parsed = email.utils.parsedate(header)
                if parsed:
                    wait = calendar.timegm(parsed) - time.time()
                    return max(0.0, min(wait, 60.0))
            reset = exc.headers.get("X-RateLimit-Reset")
            if reset and reset.isdigit():
                return max(0.0, min(float(reset) - time.time(), 60.0))
            return _backoff(attempt)
        if 500 <= exc.code < 600:
            return _backoff(attempt)
        return None

    # -- raindrops: single ----------------------------------------------------

    def get_raindrop(self, raindrop_id: int) -> dict:
        return self._request("GET", f"/raindrop/{raindrop_id}").get("item", {})

    def create_raindrop(self, link: str, **fields: Any) -> dict:
        payload = _raindrop_payload(link=link, **fields)
        return self._request("POST", "/raindrop", json_body=payload).get("item", {})

    def update_raindrop(self, raindrop_id: int, **fields: Any) -> dict:
        payload = _raindrop_payload(**fields)
        return self._request("PUT", f"/raindrop/{raindrop_id}", json_body=payload).get(
            "item", {}
        )

    def delete_raindrop(self, raindrop_id: int, *, permanent: bool = False) -> bool:
        """Delete a raindrop. It moves to Trash first; with ``permanent=True`` a
        second delete removes it from Trash for good. (The undocumented
        ``?permanent=true`` query param was tested and does *not* one-shot a live
        raindrop, so we use the documented two-step instead.)"""
        ok = bool(
            self._request("DELETE", f"/raindrop/{raindrop_id}").get("result", False)
        )
        if permanent:
            try:
                self._request("DELETE", f"/raindrop/{raindrop_id}")
            except NotFoundError:
                pass  # already gone (it was in Trash before the first delete)
        return ok

    def upload_file(
        self, filename: str, content: bytes, mime: str, collection_id: int = UNSORTED
    ) -> dict:
        files = {"file": (filename, content, mime)}
        form = {"collectionId": str(collection_id)}
        return self._request("PUT", "/raindrop/file", files=files, form=form).get(
            "item", {}
        )

    def upload_cover(
        self, raindrop_id: int, filename: str, content: bytes, mime: str
    ) -> dict:
        files = {"cover": (filename, content, mime)}
        return self._request("PUT", f"/raindrop/{raindrop_id}/cover", files=files).get(
            "item", {}
        )

    def suggest_new(self, link: str) -> dict:
        return self._request("POST", "/raindrop/suggest", json_body={"link": link}).get(
            "item", {}
        )

    def suggest_existing(self, raindrop_id: int) -> dict:
        return self._request("GET", f"/raindrop/{raindrop_id}/suggest").get("item", {})

    # -- raindrops: multiple --------------------------------------------------

    def get_raindrops(
        self,
        collection_id: int = ALL,
        *,
        search: str = "",
        sort: str = "-created",
        page: int = 0,
        perpage: int = PERPAGE_MAX,
        nested: bool = False,
    ) -> dict:
        params: dict[str, Any] = {
            "sort": sort,
            "page": page,
            "perpage": min(perpage, PERPAGE_MAX),
            "nested": nested,
        }
        if search:
            params["search"] = search
        return self._request("GET", f"/raindrops/{collection_id}", params=params)

    def iter_raindrops(
        self,
        collection_id: int = ALL,
        *,
        search: str = "",
        sort: str = "-created",
        nested: bool = False,
        perpage: int = PERPAGE_MAX,
    ) -> Iterator[dict]:
        """Yield every raindrop across all pages."""
        page = 0
        while True:
            data = self.get_raindrops(
                collection_id,
                search=search,
                sort=sort,
                page=page,
                perpage=perpage,
                nested=nested,
            )
            items = data.get("items", [])
            yield from items
            if len(items) < perpage:
                return
            page += 1

    def create_raindrops(self, items: list[dict]) -> list[dict]:
        return self._request("POST", "/raindrops", json_body={"items": items}).get(
            "items", []
        )

    def update_raindrops(
        self,
        collection_id: int,
        *,
        ids: list[int] | None = None,
        search: str = "",
        nested: bool = False,
        move_to: int | None = None,
        **fields: Any,
    ) -> int:
        """Batch-update raindrops. ``collection_id`` is the path scope (the
        collection the raindrops currently live in; system ``0`` is *not*
        supported here per the API). ``move_to`` sets the destination
        collection; other fields (``important``, ``tags`` (append; ``[]``
        clears), ``cover``) pass through."""
        params = {"nested": nested} if nested else None
        payload = _raindrop_payload(**fields)
        if move_to is not None:
            payload["collection"] = {"$id": move_to}
        if ids:
            payload["ids"] = ids
        if search:
            payload["search"] = search
        data = self._request(
            "PUT", f"/raindrops/{collection_id}", params=params, json_body=payload
        )
        return int(data.get("modified", 0))

    def delete_raindrops(
        self,
        collection_id: int,
        *,
        ids: list[int] | None = None,
        search: str = "",
        nested: bool = False,
    ) -> int:
        params: dict[str, Any] = {}
        if nested:
            params["nested"] = nested
        if search:
            params["search"] = search
        payload = {"ids": ids} if ids else None
        data = self._request(
            "DELETE",
            f"/raindrops/{collection_id}",
            params=params or None,
            json_body=payload,
        )
        return int(data.get("modified", 0))

    def export(
        self,
        collection_id: int = ALL,
        *,
        fmt: str = "csv",
        sort: str = "-created",
        search: str = "",
    ) -> bytes:
        params: dict[str, Any] = {"sort": sort}
        if search:
            params["search"] = search
        return self._request(
            "GET",
            f"/raindrops/{collection_id}/export.{fmt}",
            params=params,
            expect_json=False,
        )

    # -- collections ----------------------------------------------------------

    def get_collections(self) -> list[dict]:
        return self._request("GET", "/collections").get("items", [])

    def get_child_collections(self) -> list[dict]:
        return self._request("GET", "/collections/childrens").get("items", [])

    def get_collection(self, collection_id: int) -> dict:
        return self._request("GET", f"/collection/{collection_id}").get("item", {})

    def create_collection(
        self,
        title: str,
        *,
        view: str | None = None,
        sort: int | None = None,
        public: bool | None = None,
        parent_id: int | None = None,
    ) -> dict:
        payload = _collection_payload(
            title=title, view=view, sort=sort, public=public, parent_id=parent_id
        )
        return self._request("POST", "/collection", json_body=payload).get("item", {})

    def update_collection(self, collection_id: int, **fields: Any) -> dict:
        payload = _collection_payload(**fields)
        return self._request(
            "PUT", f"/collection/{collection_id}", json_body=payload
        ).get("item", {})

    def delete_collection(self, collection_id: int) -> bool:
        return bool(
            self._request("DELETE", f"/collection/{collection_id}").get("result", False)
        )

    def delete_collections(self, ids: list[int]) -> bool:
        return bool(
            self._request("DELETE", "/collections", json_body={"ids": ids}).get(
                "result", False
            )
        )

    def reorder_collections(self, sort: str) -> bool:
        return bool(
            self._request("PUT", "/collections", json_body={"sort": sort}).get(
                "result", False
            )
        )

    def expand_collections(self, expanded: bool) -> bool:
        return bool(
            self._request("PUT", "/collections", json_body={"expanded": expanded}).get(
                "result", False
            )
        )

    def merge_collections(self, to: int, ids: list[int]) -> bool:
        return bool(
            self._request(
                "PUT", "/collections/merge", json_body={"to": to, "ids": ids}
            ).get("result", False)
        )

    def clean_collections(self) -> int:
        """Remove all empty collections; return how many were removed."""
        return int(self._request("PUT", "/collections/clean").get("count", 0))

    def empty_trash(self) -> bool:
        return bool(
            self._request("DELETE", f"/collection/{TRASH}").get("result", False)
        )

    def upload_collection_cover(
        self, collection_id: int, filename: str, content: bytes, mime: str
    ) -> dict:
        files = {"cover": (filename, content, mime)}
        return self._request(
            "PUT", f"/collection/{collection_id}/cover", files=files
        ).get("item", {})

    def search_covers(self, text: str) -> list[dict]:
        """Search the icon/cover library (grouped by provider)."""
        return self._request(
            "GET", f"/collections/covers/{urllib.parse.quote(text)}"
        ).get("items", [])

    def featured_covers(self) -> list[dict]:
        return self._request("GET", "/collections/covers").get("items", [])

    # -- tags -----------------------------------------------------------------

    def get_tags(self, collection_id: int | None = None) -> list[dict]:
        path = "/tags" + (f"/{collection_id}" if collection_id is not None else "")
        return self._request("GET", path).get("items", [])

    def rename_tag(self, old: str, new: str, collection_id: int | None = None) -> bool:
        return self.merge_tags([old], new, collection_id)

    def merge_tags(
        self, tags: list[str], new: str, collection_id: int | None = None
    ) -> bool:
        path = "/tags" + (f"/{collection_id}" if collection_id is not None else "")
        payload = {"replace": new, "tags": tags}
        return bool(self._request("PUT", path, json_body=payload).get("result", False))

    def delete_tags(self, tags: list[str], collection_id: int | None = None) -> bool:
        path = "/tags" + (f"/{collection_id}" if collection_id is not None else "")
        return bool(
            self._request("DELETE", path, json_body={"tags": tags}).get("result", False)
        )

    # -- highlights -----------------------------------------------------------

    def get_all_highlights(self, *, page: int = 0, perpage: int = 25) -> list[dict]:
        params = {"page": page, "perpage": min(perpage, PERPAGE_MAX)}
        return self._request("GET", "/highlights", params=params).get("items", [])

    def get_collection_highlights(
        self, collection_id: int, *, page: int = 0, perpage: int = 25
    ) -> list[dict]:
        params = {"page": page, "perpage": min(perpage, PERPAGE_MAX)}
        return self._request("GET", f"/highlights/{collection_id}", params=params).get(
            "items", []
        )

    def iter_highlights(self, *, perpage: int = PERPAGE_MAX) -> Iterator[dict]:
        page = 0
        while True:
            items = self.get_all_highlights(page=page, perpage=perpage)
            yield from items
            if len(items) < perpage:
                return
            page += 1

    def get_raindrop_highlights(self, raindrop_id: int) -> list[dict]:
        return self.get_raindrop(raindrop_id).get("highlights", [])

    def add_highlight(
        self, raindrop_id: int, text: str, *, color: str = "yellow", note: str = ""
    ) -> list[dict]:
        highlight = {"text": text, "color": color}
        if note:
            highlight["note"] = note
        item = self._request(
            "PUT", f"/raindrop/{raindrop_id}", json_body={"highlights": [highlight]}
        ).get("item", {})
        return item.get("highlights", [])

    def update_highlight(
        self,
        raindrop_id: int,
        highlight_id: str,
        *,
        text: str | None = None,
        color: str | None = None,
        note: str | None = None,
    ) -> list[dict]:
        highlight: dict[str, Any] = {"_id": highlight_id}
        if text is not None:
            highlight["text"] = text
        if color is not None:
            highlight["color"] = color
        if note is not None:
            highlight["note"] = note
        item = self._request(
            "PUT", f"/raindrop/{raindrop_id}", json_body={"highlights": [highlight]}
        ).get("item", {})
        return item.get("highlights", [])

    def delete_highlight(self, raindrop_id: int, highlight_id: str) -> list[dict]:
        """Remove a highlight (empty ``text`` signals deletion). Returns the
        remaining highlights."""
        item = self._request(
            "PUT",
            f"/raindrop/{raindrop_id}",
            json_body={"highlights": [{"_id": highlight_id, "text": ""}]},
        ).get("item", {})
        return item.get("highlights", [])

    # -- user / filters / stats ----------------------------------------------

    def get_user(self) -> dict:
        return self._request("GET", "/user").get("user", {})

    def get_user_by_name(self, name: str) -> dict:
        return self._request("GET", f"/user/{name}").get("user", {})

    def update_user(self, **fields: Any) -> dict:
        """Update the authenticated user. Accepts ``fullName``, ``email``,
        ``config`` (dict), ``groups`` (list), and ``newpassword`` +
        ``oldpassword``. Only non-``None`` fields are sent."""
        payload = {k: v for k, v in fields.items() if v is not None}
        return self._request("PUT", "/user", json_body=payload).get("user", {})

    def get_stats(self) -> dict:
        """System collection counts plus meta (pro, duplicates, broken)."""
        return self._request("GET", "/user/stats")

    def get_filters(
        self, collection_id: int = ALL, *, tags_sort: str = "-count", search: str = ""
    ) -> dict:
        params: dict[str, Any] = {"tagsSort": tags_sort}
        if search:
            params["search"] = search
        return self._request("GET", f"/filters/{collection_id}", params=params)

    # -- import ---------------------------------------------------------------

    def parse_url(self, url: str) -> dict:
        return self._request("GET", "/import/url/parse", params={"url": url}).get(
            "item", {}
        )

    def check_urls_exist(self, urls: list[str]) -> dict:
        """Return ``{"result": bool, "ids": [...]}`` for already-saved URLs."""
        return self._request("POST", "/import/url/exists", json_body={"urls": urls})

    def parse_import_file(self, filename: str, content: bytes, mime: str) -> list[dict]:
        """Convert a Netscape/Pocket/Instapaper HTML export to structured JSON
        (folders + bookmarks). Does not create anything; feed the result to
        ``create_raindrops`` to import."""
        files = {"import": (filename, content, mime)}
        return self._request("POST", "/import/file", files=files).get("items", [])

    # -- backups --------------------------------------------------------------

    def get_backups(self) -> list[dict]:
        return self._request("GET", "/backups").get("items", [])

    def generate_backup(self) -> bytes:
        return self._request("GET", "/backup", expect_json=False)

    def download_backup(self, backup_id: str, fmt: str = "csv") -> bytes:
        return self._request("GET", f"/backup/{backup_id}.{fmt}", expect_json=False)


# -- payload builders ---------------------------------------------------------


def _raindrop_payload(**fields: Any) -> dict:
    """Build a raindrop create/update body from keyword fields, dropping ``None``.

    ``collection_id`` is translated to the API's ``{"collection": {"$id": id}}``
    shape; ``please_parse`` sends an empty object to trigger background parsing.
    """
    payload: dict[str, Any] = {}
    simple = (
        "link",
        "title",
        "excerpt",
        "note",
        "important",
        "tags",
        "cover",
        "type",
        "order",
        "media",
        "created",
        "lastUpdate",
        "highlights",
        "reminder",
    )
    for key in simple:
        if key in fields and fields[key] is not None:
            payload[key] = fields[key]
    collection_id = fields.get("collection_id")
    if collection_id is not None:
        payload["collection"] = {"$id": collection_id}
    if fields.get("please_parse"):
        payload["pleaseParse"] = {}
    return payload


def _collection_payload(**fields: Any) -> dict:
    payload: dict[str, Any] = {}
    for key in ("title", "view", "sort", "public", "expanded", "cover"):
        if key in fields and fields[key] is not None:
            payload[key] = fields[key]
    parent_id = fields.get("parent_id")
    if parent_id is not None:
        payload["parent"] = {"$id": parent_id}
    return payload


# -- request helpers ----------------------------------------------------------


def _encode_params(params: dict[str, Any] | None) -> str:
    if not params:
        return ""
    clean: dict[str, str] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            clean[key] = "true" if value else "false"
        else:
            clean[key] = str(value)
    return urllib.parse.urlencode(clean)


def _multipart(
    files: dict[str, tuple[str, bytes, str]], form: dict[str, str]
) -> tuple[bytes, str]:
    """Encode a ``multipart/form-data`` body without external deps."""
    boundary = "----rdcli" + os.urandom(8).hex()
    crlf = b"\r\n"
    parts: list[bytes] = []
    for name, value in form.items():
        parts.append(f"--{boundary}".encode())
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode())
        parts.append(b"")
        parts.append(value.encode("utf-8"))
    for name, (filename, content, mime) in files.items():
        parts.append(f"--{boundary}".encode())
        parts.append(
            f'Content-Disposition: form-data; name="{name}"; '
            f'filename="{filename}"'.encode()
        )
        parts.append(f"Content-Type: {mime}".encode())
        parts.append(b"")
        parts.append(content)
    parts.append(f"--{boundary}--".encode())
    parts.append(b"")
    body = crlf.join(parts)
    return body, f"multipart/form-data; boundary={boundary}"


def _backoff(attempt: int) -> float:
    """Exponential backoff: 0.5s, 1s, 2s, ... capped at 30s."""
    return min(0.5 * (2**attempt), 30.0)


def _to_api_error(exc: urllib.error.HTTPError) -> APIError:
    message = exc.reason or "request failed"
    payload: dict | None = None
    try:
        raw = exc.read()
        if raw:
            decoded = json.loads(raw)
            if isinstance(decoded, dict):
                payload = decoded
                message = decoded.get("errorMessage") or decoded.get("error") or message
    except (ValueError, OSError):
        pass
    if exc.code in (401, 403):
        return AuthError(message, status=exc.code, payload=payload)
    if exc.code == 404:
        return NotFoundError(message, status=exc.code, payload=payload)
    if exc.code == 429:
        return RateLimitError(message, status=exc.code, payload=payload)
    return APIError(message, status=exc.code, payload=payload)
