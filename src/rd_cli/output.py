"""Terminal output helpers: colour, alignment, trees, and JSON emission.

Colour is TTY-aware and opt-out: it is disabled automatically when stdout is
not a terminal (so piped output stays clean), when ``NO_COLOR`` is set, or when
the CLI is passed ``--no-color``. The palette leans on the Kanagawa Dragon
family Brandon uses everywhere.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

# ANSI SGR codes.
_CODES = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "id": "\033[38;5;109m",  # muted blue — identifiers
    "title": "\033[1m",  # bold — titles
    "url": "\033[38;5;150m",  # green — links
    "tag": "\033[38;5;179m",  # yellow — tags
    "star": "\033[38;5;174m",  # red/pink — important
    "muted": "\033[2m",  # dim — secondary text
    "error": "\033[38;5;174m",  # red — errors
    "ok": "\033[38;5;150m",  # green — success
}

_color_enabled = True


def configure(*, no_color: bool = False, stream=None) -> None:
    """Decide whether colour is on, based on flags, env, and TTY status."""
    global _color_enabled
    stream = stream or sys.stdout
    _color_enabled = not (
        no_color
        or os.environ.get("NO_COLOR") is not None
        or not hasattr(stream, "isatty")
        or not stream.isatty()
    )


def color(text: str, name: str) -> str:
    """Wrap ``text`` in the named colour when colour is enabled."""
    if not _color_enabled:
        return text
    code = _CODES.get(name, "")
    return f"{code}{text}{_CODES['reset']}" if code else text


def emit_json(data: Any) -> None:
    """Print ``data`` as compact-but-readable UTF-8 JSON."""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def error(message: str) -> None:
    print(color(f"error: {message}", "error"), file=sys.stderr)


def success(message: str) -> None:
    print(color(message, "ok"))


# -- domain formatters --------------------------------------------------------


def format_raindrop_line(item: dict, *, detailed: bool = False) -> str:
    """One-line (or multi-line when detailed) rendering of a raindrop."""
    rid = color(f"[{item.get('_id')}]", "id")
    title = color(item.get("title") or "(no title)", "title")
    star = " " + color("★", "star") if item.get("important") else ""
    lines = [f"{rid} {title}{star}"]
    link = item.get("link")
    if link:
        lines.append("      " + color(link, "url"))
    if detailed:
        excerpt = (item.get("excerpt") or "").strip()
        if excerpt:
            lines.append("      " + color(_truncate(excerpt, 200), "muted"))
        note = (item.get("note") or "").strip()
        if note:
            lines.append("      " + color("note: " + _truncate(note, 200), "muted"))
        tags = item.get("tags") or []
        if tags:
            lines.append("      " + " ".join(color(f"#{t}", "tag") for t in tags))
    return "\n".join(lines)


def format_raindrop_detail(item: dict) -> str:
    rid = color(str(item.get("_id")), "id")
    title = color(item.get("title") or "(no title)", "title")
    lines = [f"{rid}  {title}"]
    if item.get("important"):
        lines[0] += " " + color("★", "star")
    fields = [
        ("link", item.get("link")),
        ("domain", item.get("domain")),
        ("type", item.get("type")),
        ("created", item.get("created")),
        ("updated", item.get("lastUpdate")),
    ]
    collection_id = _collection_id_of(item)
    if collection_id is not None:
        fields.append(("collection", collection_id))
    for label, value in fields:
        if value:
            lines.append(f"  {color(label + ':', 'muted')} {value}")
    excerpt = (item.get("excerpt") or "").strip()
    if excerpt:
        lines.append(f"  {color('excerpt:', 'muted')} {excerpt}")
    note = (item.get("note") or "").strip()
    if note:
        lines.append(f"  {color('note:', 'muted')} {note}")
    tags = item.get("tags") or []
    if tags:
        lines.append("  " + " ".join(color(f"#{t}", "tag") for t in tags))
    highlights = item.get("highlights") or []
    if highlights:
        lines.append(f"  {color('highlights:', 'muted')}")
        for hl in highlights:
            lines.append(f"    {color('▍', hl.get('color', 'muted'))} {hl.get('text')}")
    return "\n".join(lines)


def format_collections_flat(items: list[dict]) -> str:
    rows = [
        (
            color(f"[{c.get('_id')}]", "id"),
            c.get("title") or "(untitled)",
            str(c.get("count", 0)),
        )
        for c in items
    ]
    return _columns(rows, headers=None)


def format_collection_tree(roots: list[dict], children: list[dict]) -> str:
    """Render nested collections as an indented tree using ``parent.$id`` links."""
    kids: dict[int, list[dict]] = {}
    for child in children:
        parent = (child.get("parent") or {}).get("$id")
        if parent is not None:
            kids.setdefault(parent, []).append(child)
    for group in kids.values():
        group.sort(key=lambda c: c.get("sort", 0))

    lines: list[str] = []

    def walk(node: dict, depth: int) -> None:
        indent = "  " * depth
        rid = color(f"[{node.get('_id')}]", "id")
        count = color(f"({node.get('count', 0)})", "muted")
        lines.append(f"{indent}{rid} {node.get('title') or '(untitled)'} {count}")
        for child in kids.get(node.get("_id", 0), []):
            walk(child, depth + 1)

    for root in roots:
        walk(root, 0)
    return "\n".join(lines)


def format_tags(items: list[dict]) -> str:
    rows = [
        (color(f"#{t.get('_id')}", "tag"), color(f"({t.get('count', 0)})", "muted"))
        for t in items
    ]
    return _columns(rows, headers=None)


def format_highlight_line(hl: dict) -> str:
    marker = color("▍", hl.get("color", "muted"))
    ref = hl.get("raindropRef")
    hid = color(f"[{hl.get('_id')}]", "id")
    ref_str = color(f"rd:{ref}", "muted") if ref else ""
    lines = [f"{hid} {ref_str} {marker} {hl.get('text', '')}".rstrip()]
    note = (hl.get("note") or "").strip()
    if note:
        lines.append("      " + color("note: " + note, "muted"))
    return "\n".join(lines)


# -- generic helpers ----------------------------------------------------------


def _columns(rows: list[tuple[str, ...]], headers: tuple[str, ...] | None) -> str:
    """Left-align rows into columns. Widths are computed on visible width so
    ANSI codes do not throw off alignment."""
    all_rows = ([headers] if headers else []) + rows
    if not all_rows:
        return ""
    ncols = max(len(r) for r in all_rows)
    widths = [0] * ncols
    for row in all_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], _visible_len(cell))
    out = []
    for row in all_rows:
        cells = []
        for i, cell in enumerate(row):
            pad = widths[i] - _visible_len(cell)
            cells.append(cell + " " * pad if i < ncols - 1 else cell)
        out.append("  ".join(cells).rstrip())
    return "\n".join(out)


def _visible_len(text: str) -> int:
    """Length of ``text`` ignoring ANSI escape sequences."""
    result = 0
    i = 0
    while i < len(text):
        if text[i] == "\033":
            end = text.find("m", i)
            if end == -1:
                break
            i = end + 1
        else:
            result += 1
            i += 1
    return result


def _truncate(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _collection_id_of(item: dict) -> int | None:
    collection = item.get("collection")
    if isinstance(collection, dict):
        return collection.get("$id")
    return item.get("collectionId")
