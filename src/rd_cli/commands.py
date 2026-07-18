"""Command handlers. Each ``cmd_*`` function takes ``(client, args)`` and returns
a process exit code. ``cfg_*`` handlers operate on local config and ignore the
client (which may be ``None``). ``cli.py`` wires these to argparse subcommands.
"""

from __future__ import annotations

import mimetypes
import sys
from pathlib import Path
from typing import Any

from . import config, output
from .client import RaindropClient

# -- raindrops ----------------------------------------------------------------


def cmd_list(client: RaindropClient, args: Any) -> int:
    if getattr(args, "all", False):
        items = list(
            client.iter_raindrops(
                args.collection,
                search=args.search,
                sort=args.sort,
                nested=args.nested,
            )
        )
    else:
        items = client.get_raindrops(
            args.collection,
            search=args.search,
            sort=args.sort,
            page=args.page,
            perpage=args.perpage,
            nested=args.nested,
        ).get("items", [])
    if args.json:
        output.emit_json(items)
        return 0
    if not items:
        output.error("no raindrops found")
        return 0
    for item in items:
        print(output.format_raindrop_line(item, detailed=args.detailed))
    return 0


def cmd_view(client: RaindropClient, args: Any) -> int:
    item = client.get_raindrop(args.id)
    if args.json:
        output.emit_json(item)
        return 0
    if not item:
        output.error(f"raindrop {args.id} not found")
        return 1
    print(output.format_raindrop_detail(item))
    return 0


def cmd_add(client: RaindropClient, args: Any) -> int:
    urls = _collect_urls(args)
    if urls is not None:
        return _add_many(client, args, urls)
    if not args.url:
        output.error("provide a URL, or --file/--stdin to add many")
        return 1
    item = client.create_raindrop(
        args.url,
        title=args.title,
        collection_id=args.collection,
        tags=args.tags,
        excerpt=args.excerpt,
        note=args.note,
        important=args.important or None,
        please_parse=not args.no_parse,
    )
    if args.json:
        output.emit_json(item)
        return 0
    output.success(f"added [{item.get('_id')}] {item.get('title') or args.url}")
    return 0


def _collect_urls(args: Any) -> list[str] | None:
    """URLs for batch add from ``--file`` / ``--stdin``, or ``None`` for single."""
    if getattr(args, "stdin", False):
        text = sys.stdin.read()
    elif getattr(args, "file", None):
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        return None
    return [line.strip() for line in text.splitlines() if line.strip()]


def _add_many(client: RaindropClient, args: Any, urls: list[str]) -> int:
    created: list[dict] = []
    for chunk in _chunks(urls, 100):  # API caps a batch at 100 items
        items = [
            {"link": url, "collection": {"$id": args.collection}, "pleaseParse": {}}
            for url in chunk
        ]
        created.extend(client.create_raindrops(items))
    if args.json:
        output.emit_json(created)
        return 0
    output.success(f"added {len(created)} raindrop(s)")
    return 0


def cmd_edit(client: RaindropClient, args: Any) -> int:
    item = client.update_raindrop(
        args.id,
        title=args.title,
        tags=args.tags,
        collection_id=args.collection,
        note=args.note,
        excerpt=args.excerpt,
        important=_tristate(args.important, args.not_important),
    )
    if args.json:
        output.emit_json(item)
        return 0
    output.success(f"edited [{item.get('_id')}] {item.get('title') or ''}".rstrip())
    return 0


def cmd_rm(client: RaindropClient, args: Any) -> int:
    if not args.ids and args.from_collection is None:
        output.error("provide raindrop id(s), or --from <collection> for scope mode")
        return 1
    # Scope mode: delete everything in a source collection (optionally filtered
    # by search) in one batch call. The batch endpoint's path is a scope, so a
    # real source collection is required (0 is unsupported for remove-many).
    if getattr(args, "from_collection", None) is not None:
        n = client.delete_raindrops(
            args.from_collection, search=args.search or "", nested=args.nested
        )
        if args.json:
            output.emit_json({"modified": n})
            return 0
        output.success(
            f"removed {n} raindrop(s) from collection {args.from_collection}"
        )
        return 0

    # Id mode: loop the single-item endpoint (always correct regardless of which
    # collection each raindrop lives in).
    results = {
        rid: client.delete_raindrop(rid, permanent=args.permanent) for rid in args.ids
    }
    if args.json:
        output.emit_json(results)
        return 0 if all(results.values()) else 1
    ok = sum(1 for v in results.values() if v)
    verb = "permanently deleted" if args.permanent else "moved to trash"
    output.success(f"{verb} {ok}/{len(results)} raindrop(s)")
    return 0 if ok == len(results) else 1


def cmd_export(client: RaindropClient, args: Any) -> int:
    data = client.export(
        args.collection, fmt=args.format, sort=args.sort, search=args.search
    )
    if args.output:
        with open(args.output, "wb") as fh:
            fh.write(data)
        output.success(f"wrote {len(data)} bytes to {args.output}")
    else:
        sys.stdout.buffer.write(data)
    return 0


def cmd_mv(client: RaindropClient, args: Any) -> int:
    dest = args.collection
    if not args.ids and args.from_collection is None:
        output.error("provide raindrop id(s), or --from <collection> for scope mode")
        return 1
    # Scope mode: move everything in a source collection (optional search) at once.
    if getattr(args, "from_collection", None) is not None:
        n = client.update_raindrops(
            args.from_collection,
            search=args.search or "",
            nested=args.nested,
            move_to=dest,
        )
        if args.json:
            output.emit_json({"modified": n})
            return 0
        output.success(f"moved {n} raindrop(s) to collection {dest}")
        return 0

    # Id mode: loop single-item updates (correct across heterogeneous sources).
    moved = 0
    for rid in args.ids:
        client.update_raindrop(rid, collection_id=dest)
        moved += 1
    if args.json:
        output.emit_json({"moved": moved, "collection": dest})
        return 0
    output.success(f"moved {moved} raindrop(s) to collection {dest}")
    return 0


def cmd_tag(client: RaindropClient, args: Any) -> int:
    add = args.add or []
    remove = set(args.remove or [])
    if not (add or remove or args.clear):
        output.error("nothing to do: pass --add, --remove, or --clear")
        return 1

    # Scope mode: append tags (or clear all) across a whole collection/search.
    if getattr(args, "from_collection", None) is not None:
        if remove:
            output.error(
                "--remove is not supported in scope mode; use ids, or "
                "`tags rm <tag>` to strip a tag from every raindrop"
            )
            return 1
        new_tags: list[str] = [] if args.clear else add
        n = client.update_raindrops(
            args.from_collection,
            search=args.search or "",
            nested=args.nested,
            tags=new_tags,
        )
        if args.json:
            output.emit_json({"modified": n})
            return 0
        output.success(f"updated tags on {n} raindrop(s)")
        return 0

    # Id mode: compute the new tag set per raindrop (add/remove/clear precisely).
    changed = 0
    for rid in args.ids:
        current = [] if args.clear else list(client.get_raindrop(rid).get("tags") or [])
        merged = [t for t in current if t not in remove]
        for t in add:
            if t not in merged:
                merged.append(t)
        client.update_raindrop(rid, tags=merged)
        changed += 1
    if args.json:
        output.emit_json({"updated": changed})
        return 0
    output.success(f"updated tags on {changed} raindrop(s)")
    return 0


# -- collections --------------------------------------------------------------


def cmd_collections_list(client: RaindropClient, args: Any) -> int:
    items = client.get_collections()
    if args.json:
        output.emit_json(items)
        return 0
    print(output.format_collections_flat(items))
    return 0


def cmd_collections_tree(client: RaindropClient, args: Any) -> int:
    roots = client.get_collections()
    children = client.get_child_collections()
    if args.json:
        output.emit_json({"roots": roots, "children": children})
        return 0
    print(output.format_collection_tree(roots, children))
    return 0


def cmd_collections_view(client: RaindropClient, args: Any) -> int:
    item = client.get_collection(args.id)
    if args.json:
        output.emit_json(item)
        return 0
    if not item:
        output.error(f"collection {args.id} not found")
        return 1
    print(output.format_collections_flat([item]))
    return 0


def cmd_collections_add(client: RaindropClient, args: Any) -> int:
    item = client.create_collection(
        args.title,
        view=args.view,
        public=args.public or None,
        parent_id=args.parent,
    )
    if args.json:
        output.emit_json(item)
        return 0
    output.success(f"created collection [{item.get('_id')}] {item.get('title')}")
    return 0


def cmd_collections_edit(client: RaindropClient, args: Any) -> int:
    item = client.update_collection(
        args.id,
        title=args.title,
        view=args.view,
        public=_tristate(args.public, args.private),
        parent_id=args.parent,
    )
    if args.json:
        output.emit_json(item)
        return 0
    output.success(f"edited collection [{item.get('_id')}] {item.get('title')}")
    return 0


def cmd_collections_rm(client: RaindropClient, args: Any) -> int:
    ok = client.delete_collection(args.id)
    if args.json:
        output.emit_json({"result": ok})
        return 0 if ok else 1
    if ok:
        output.success(f"deleted collection {args.id}")
        return 0
    output.error(f"failed to delete collection {args.id}")
    return 1


def cmd_collections_merge(client: RaindropClient, args: Any) -> int:
    ok = client.merge_collections(args.to, args.ids)
    if args.json:
        output.emit_json({"result": ok})
        return 0 if ok else 1
    output.success(f"merged {len(args.ids)} collection(s) into {args.to}")
    return 0


def cmd_collections_clean(client: RaindropClient, args: Any) -> int:
    count = client.clean_collections()
    if args.json:
        output.emit_json({"removed": count})
        return 0
    output.success(f"removed {count} empty collection(s)")
    return 0


def cmd_collections_empty_trash(client: RaindropClient, args: Any) -> int:
    ok = client.empty_trash()
    if args.json:
        output.emit_json({"result": ok})
        return 0 if ok else 1
    output.success("emptied trash")
    return 0


def cmd_collections_reorder(client: RaindropClient, args: Any) -> int:
    ok = client.reorder_collections(args.by)
    if args.json:
        output.emit_json({"result": ok})
        return 0 if ok else 1
    output.success(f"reordered all collections by {args.by}")
    return 0


def cmd_collections_cover(client: RaindropClient, args: Any) -> int:
    name, content, mime = _read_file(args.file)
    item = client.upload_collection_cover(args.id, name, content, mime)
    if args.json:
        output.emit_json(item)
        return 0
    output.success(f"set cover on collection {args.id}")
    return 0


def cmd_collections_covers(client: RaindropClient, args: Any) -> int:
    groups = client.search_covers(args.text)
    if args.json:
        output.emit_json(groups)
        return 0
    for group in groups:
        print(output.color(group.get("title", "?"), "title"))
        for icon in group.get("icons", []):
            url = icon.get("svg") or icon.get("png")
            if url:
                print(f"  {url}")
    return 0


# -- tags ---------------------------------------------------------------------


def cmd_tags_list(client: RaindropClient, args: Any) -> int:
    items = client.get_tags(args.collection)
    if args.json:
        output.emit_json(items)
        return 0
    if not items:
        output.error("no tags found")
        return 0
    print(output.format_tags(items))
    return 0


def cmd_tags_rename(client: RaindropClient, args: Any) -> int:
    ok = client.rename_tag(args.old, args.new, args.collection)
    if args.json:
        output.emit_json({"result": ok})
        return 0 if ok else 1
    output.success(f"renamed #{args.old} to #{args.new}")
    return 0


def cmd_tags_merge(client: RaindropClient, args: Any) -> int:
    ok = client.merge_tags(args.tags, args.into, args.collection)
    if args.json:
        output.emit_json({"result": ok})
        return 0 if ok else 1
    output.success(f"merged {', '.join('#' + t for t in args.tags)} into #{args.into}")
    return 0


def cmd_tags_rm(client: RaindropClient, args: Any) -> int:
    ok = client.delete_tags(args.tags, args.collection)
    if args.json:
        output.emit_json({"result": ok})
        return 0 if ok else 1
    output.success(f"deleted tag(s): {', '.join('#' + t for t in args.tags)}")
    return 0


# -- highlights ---------------------------------------------------------------


def cmd_highlights_list(client: RaindropClient, args: Any) -> int:
    if args.raindrop:
        items = client.get_raindrop_highlights(args.raindrop)
    elif getattr(args, "all", False):
        items = list(client.iter_highlights())
    else:
        items = client.get_all_highlights(page=args.page, perpage=args.perpage)
    if args.json:
        output.emit_json(items)
        return 0
    if not items:
        output.error("no highlights found")
        return 0
    for hl in items:
        print(output.format_highlight_line(hl))
    return 0


def cmd_highlights_add(client: RaindropClient, args: Any) -> int:
    highlights = client.add_highlight(
        args.raindrop, args.text, color=args.color, note=args.note
    )
    if args.json:
        output.emit_json(highlights)
        return 0
    output.success(f"added highlight to raindrop {args.raindrop}")
    return 0


def cmd_highlights_edit(client: RaindropClient, args: Any) -> int:
    highlights = client.update_highlight(
        args.raindrop,
        args.highlight,
        text=args.text,
        color=args.color,
        note=args.note,
    )
    if args.json:
        output.emit_json(highlights)
        return 0
    output.success(f"updated highlight {args.highlight}")
    return 0


def cmd_highlights_rm(client: RaindropClient, args: Any) -> int:
    remaining = client.delete_highlight(args.raindrop, args.highlight)
    if args.json:
        output.emit_json(remaining)
        return 0
    output.success(f"deleted highlight {args.highlight}")
    return 0


# -- user / filters / suggest / exists ---------------------------------------


def cmd_user(client: RaindropClient, args: Any) -> int:
    user = client.get_user()
    if args.json:
        output.emit_json(user)
        return 0
    pro = "PRO" if user.get("pro") else "free"
    print(output.color(user.get("fullName") or "(unknown)", "title"))
    print(f"  {output.color('id:', 'muted')} {user.get('_id')}")
    print(f"  {output.color('email:', 'muted')} {user.get('email')}")
    print(f"  {output.color('plan:', 'muted')} {pro}")
    files = user.get("files") or {}
    if files:
        used = files.get("used", 0)
        size = files.get("size", 0)
        print(f"  {output.color('files:', 'muted')} {used} / {size} bytes")
    return 0


def cmd_user_set(client: RaindropClient, args: Any) -> int:
    config_updates: dict[str, str] = {}
    for pair in args.config or []:
        key, sep, value = pair.partition("=")
        if not sep:
            output.error(f"bad --config entry (want key=value): {pair}")
            return 1
        config_updates[key.strip()] = value.strip()
    user = client.update_user(
        fullName=args.name,
        email=args.email,
        newpassword=args.new_password,
        oldpassword=args.old_password,
        config=config_updates or None,
    )
    if args.json:
        output.emit_json(user)
        return 0
    output.success("updated user settings")
    return 0


def cmd_cover(client: RaindropClient, args: Any) -> int:
    name, content, mime = _read_file(args.file)
    item = client.upload_cover(args.id, name, content, mime)
    if args.json:
        output.emit_json(item)
        return 0
    output.success(f"set cover on raindrop {args.id}")
    return 0


def cmd_import(client: RaindropClient, args: Any) -> int:
    name, content, mime = _read_file(args.file)
    groups = client.parse_import_file(name, content, mime)
    if not args.create:
        if args.json:
            output.emit_json(groups)
            return 0
        bookmarks = _flatten_bookmarks(groups)
        print(f"parsed {len(bookmarks)} bookmark(s) across {len(groups)} group(s)")
        print("re-run with --create -c <collection> to import them")
        return 0
    bookmarks = _flatten_bookmarks(groups)
    created: list[dict] = []
    for chunk in _chunks(bookmarks, 100):
        items = [
            {
                "link": b["link"],
                "title": b.get("title", ""),
                "excerpt": b.get("excerpt", ""),
                "tags": b.get("tags", []),
                "collection": {"$id": args.collection},
            }
            for b in chunk
            if b.get("link")
        ]
        created.extend(client.create_raindrops(items))
    if args.json:
        output.emit_json(created)
        return 0
    output.success(
        f"imported {len(created)} bookmark(s) into collection {args.collection}"
    )
    return 0


def cmd_stats(client: RaindropClient, args: Any) -> int:
    stats = client.get_stats()
    if args.json:
        output.emit_json(stats)
        return 0
    names = {0: "All", -1: "Unsorted", -99: "Trash"}
    for entry in stats.get("items", []):
        name = names.get(entry.get("_id"), str(entry.get("_id")))
        print(f"  {output.color(name + ':', 'muted')} {entry.get('count', 0)}")
    meta = stats.get("meta") or {}
    if meta:
        dups = (meta.get("duplicates") or {}).get("count", 0)
        broken = (meta.get("broken") or {}).get("count", 0)
        print(f"  {output.color('duplicates:', 'muted')} {dups}")
        print(f"  {output.color('broken:', 'muted')} {broken}")
    return 0


def cmd_filters(client: RaindropClient, args: Any) -> int:
    filters = client.get_filters(
        args.collection, tags_sort=args.tags_sort, search=args.search
    )
    if args.json:
        output.emit_json(filters)
        return 0
    for key in ("broken", "duplicates", "important", "notag"):
        count = (filters.get(key) or {}).get("count")
        if count is not None:
            print(f"  {output.color(key + ':', 'muted')} {count}")
    types = filters.get("types") or []
    if types:
        print(output.color("types:", "muted"))
        for t in types:
            print(f"    {t.get('_id')}: {t.get('count', 0)}")
    tags = filters.get("tags") or []
    if tags:
        print(output.color("top tags:", "muted"))
        for t in tags[:20]:
            print(f"    #{t.get('_id')}: {t.get('count', 0)}")
    return 0


def cmd_suggest(client: RaindropClient, args: Any) -> int:
    if args.id is not None:
        item = client.suggest_existing(args.id)
    else:
        item = client.suggest_new(args.url)
    if args.json:
        output.emit_json(item)
        return 0
    collections = [c.get("$id") for c in item.get("collections", [])]
    tags = item.get("tags", [])
    print(output.color("collections:", "muted"), ", ".join(map(str, collections)))
    print(output.color("tags:", "muted"), " ".join(f"#{t}" for t in tags))
    return 0


def cmd_exists(client: RaindropClient, args: Any) -> int:
    result = client.check_urls_exist(args.urls)
    if args.json:
        output.emit_json(result)
        return 0
    ids = result.get("ids", [])
    if ids:
        output.success(f"already saved (ids: {', '.join(map(str, ids))})")
    else:
        print("not saved")
    return 0


# -- backups ------------------------------------------------------------------


def cmd_backups_list(client: RaindropClient, args: Any) -> int:
    items = client.get_backups()
    if args.json:
        output.emit_json(items)
        return 0
    if not items:
        output.error("no backups found")
        return 0
    for b in items:
        print(f"{output.color(b.get('_id'), 'id')}  {b.get('created')}")
    return 0


def cmd_backups_create(client: RaindropClient, args: Any) -> int:
    client.generate_backup()
    output.success("backup requested; Raindrop will email the export when ready")
    return 0


def cmd_backups_download(client: RaindropClient, args: Any) -> int:
    data = client.download_backup(args.id, args.format)
    path = args.output or f"raindrop-backup-{args.id}.{args.format}"
    with open(path, "wb") as fh:
        fh.write(data)
    output.success(f"wrote {len(data)} bytes to {path}")
    return 0


# -- config -------------------------------------------------------------------


def cfg_path(client: Any, args: Any) -> int:
    print(config.config_path())
    return 0


def cfg_show(client: Any, args: Any) -> int:
    data = config.read_config()
    if "token" in data:
        data = dict(data)
        data["token"] = _mask(data["token"])
    if args.json:
        output.emit_json(data)
        return 0
    if not data:
        print(f"(no config at {config.config_path()})")
        return 0
    for key, value in data.items():
        print(f"{key} = {value}")
    return 0


def cfg_set_token(client: Any, args: Any) -> int:
    path = config.write_token(args.token)
    output.success(f"token saved to {path}")
    return 0


# -- helpers ------------------------------------------------------------------


def _tristate(true_flag: bool, false_flag: bool) -> bool | None:
    """Map a pair of ``--x`` / ``--no-x`` flags to ``True``/``False``/``None``."""
    if true_flag:
        return True
    if false_flag:
        return False
    return None


def _mask(token: str) -> str:
    if len(token) <= 8:
        return "****"
    return f"{token[:4]}…{token[-4:]}"


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _read_file(path: str) -> tuple[str, bytes, str]:
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    return p.name, p.read_bytes(), mime


def _flatten_bookmarks(groups: list[dict]) -> list[dict]:
    """Flatten the nested folders/bookmarks tree from ``parse_import_file``."""
    out: list[dict] = []

    def walk(node: dict) -> None:
        out.extend(node.get("bookmarks") or [])
        for folder in node.get("folders") or []:
            walk(folder)

    for group in groups:
        walk(group)
    return out
