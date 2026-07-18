"""Argument parsing and dispatch.

A shared ``common`` parent parser carries ``--json`` and ``--no-color`` onto
every subcommand, so they work in any position (``rd list --json`` as well as
``rd --json list``). Each subparser stores its handler in ``func`` and whether
it needs an API client in ``needs_client``; ``main`` resolves the token and
builds the :class:`RaindropClient` only when required (config subcommands do
not touch the network).
"""

from __future__ import annotations

import argparse
import sys

from . import __version__, commands, config, output
from .client import RaindropClient
from .errors import RaindropError
from .pinboard import PinboardClient

COLORS = "blue brown cyan gray green indigo orange pink purple red teal yellow".split()
VIEWS = ("list", "simple", "grid", "masonry")
SORTS = (
    "-created",
    "created",
    "title",
    "-title",
    "domain",
    "-domain",
    "score",
    "-sort",
)


def build_parser() -> argparse.ArgumentParser:
    # SUPPRESS defaults so a flag given before the subcommand is not clobbered
    # by the subparser re-parsing with its own default (see main() for the
    # normalisation back to False).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS, help="output raw JSON"
    )
    common.add_argument(
        "--no-color",
        action="store_true",
        default=argparse.SUPPRESS,
        help="disable ANSI colour",
    )
    common.add_argument(
        "--dry-run",
        action="store_true",
        default=argparse.SUPPRESS,
        help="preview writes (log method + payload) without calling the API",
    )

    parser = argparse.ArgumentParser(
        prog="rd",
        description="A command-line client for Raindrop.io.",
        parents=[common],
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    _add_raindrop_commands(sub, common)
    _add_collection_commands(sub, common)
    _add_tag_commands(sub, common)
    _add_highlight_commands(sub, common)
    _add_pinboard_commands(sub, common)
    _add_misc_commands(sub, common)
    _add_config_commands(sub, common)
    _add_aliases(sub, common)
    return parser


def _p(
    sub, name, common, handler, *, needs_client=True, needs_pinboard=False, **kwargs
):
    """Register a subparser wired to ``handler`` with the common flags."""
    parser = sub.add_parser(name, parents=[common], **kwargs)
    parser.set_defaults(
        func=handler, needs_client=needs_client, needs_pinboard=needs_pinboard
    )
    return parser


def _pb(sub, name, common, handler, **kwargs):
    """Register a Pinboard subparser (wants a ``PinboardClient``, not Raindrop)."""
    return _p(
        sub, name, common, handler, needs_client=False, needs_pinboard=True, **kwargs
    )


# -- raindrops ----------------------------------------------------------------


def _add_raindrop_commands(sub, common):
    p = _p(sub, "list", common, commands.cmd_list, help="list raindrops")
    p.add_argument(
        "-c",
        "--collection",
        type=int,
        default=0,
        help="collection id (0 all, -1 unsorted, -99 trash)",
    )
    p.add_argument("-s", "--search", default="", help="search query")
    p.add_argument("--sort", default="-created", choices=SORTS, help="sort order")
    p.add_argument("--page", type=int, default=0, help="page number")
    p.add_argument("--perpage", type=int, default=50, help="items per page (max 50)")
    p.add_argument("-a", "--all", action="store_true", help="fetch all pages")
    p.add_argument(
        "-n", "--nested", action="store_true", help="include nested collections"
    )
    p.add_argument(
        "-d", "--detailed", action="store_true", help="show excerpt, note, tags"
    )

    p = _p(
        sub,
        "search",
        common,
        commands.cmd_list,
        help="search raindrops (alias of list -s)",
    )
    p.add_argument("search", help="search query")
    p.add_argument("-c", "--collection", type=int, default=0, help="collection id")
    p.add_argument("--sort", default="-created", choices=SORTS, help="sort order")
    p.add_argument("--page", type=int, default=0, help="page number")
    p.add_argument("--perpage", type=int, default=50, help="items per page (max 50)")
    p.add_argument("-a", "--all", action="store_true", help="fetch all pages")
    p.add_argument(
        "-n", "--nested", action="store_true", help="include nested collections"
    )
    p.add_argument(
        "-d", "--detailed", action="store_true", help="show excerpt, note, tags"
    )

    p = _p(sub, "view", common, commands.cmd_view, help="view a single raindrop")
    p.add_argument("id", type=int, help="raindrop id")

    p = _p(sub, "add", common, commands.cmd_add, help="add a raindrop (or many)")
    p.add_argument("url", nargs="?", help="URL to bookmark")
    p.add_argument("-t", "--title", help="custom title")
    p.add_argument(
        "-c",
        "--collection",
        type=int,
        default=-1,
        help="collection id (default -1 unsorted)",
    )
    p.add_argument("--tags", nargs="*", help="tags")
    p.add_argument("--excerpt", help="excerpt / description")
    p.add_argument("--note", help="note")
    p.add_argument("--important", action="store_true", help="mark as favourite")
    p.add_argument(
        "--no-parse", action="store_true", help="skip background metadata parsing"
    )
    p.add_argument("--file", help="add many: read one URL per line from a file")
    p.add_argument(
        "--stdin",
        action="store_true",
        help="add many: read one URL per line from stdin",
    )

    p = _p(sub, "edit", common, commands.cmd_edit, help="edit a raindrop")
    p.add_argument("id", type=int, help="raindrop id")
    p.add_argument("-t", "--title", help="new title")
    p.add_argument("--tags", nargs="*", help="replace tags")
    p.add_argument("-c", "--collection", type=int, help="move to collection id")
    p.add_argument("--excerpt", help="new excerpt")
    p.add_argument("--note", help="new note")
    p.add_argument("--important", action="store_true", help="mark as favourite")
    p.add_argument("--not-important", action="store_true", help="unmark as favourite")

    p = _p(sub, "rm", common, commands.cmd_rm, help="remove raindrop(s) (to trash)")
    p.add_argument("ids", type=int, nargs="*", help="raindrop id(s)")
    p.add_argument(
        "--from",
        dest="from_collection",
        type=int,
        help="scope: remove all raindrops in this collection",
    )
    p.add_argument("-s", "--search", default="", help="scope: filter by search query")
    p.add_argument(
        "-n", "--nested", action="store_true", help="scope: include nested collections"
    )
    p.add_argument(
        "--permanent", action="store_true", help="delete permanently (skip trash)"
    )

    p = _p(sub, "mv", common, commands.cmd_mv, help="move raindrop(s) to a collection")
    p.add_argument("collection", type=int, help="destination collection id")
    p.add_argument("ids", type=int, nargs="*", help="raindrop id(s) to move")
    p.add_argument(
        "--from",
        dest="from_collection",
        type=int,
        help="scope: move all raindrops from this source collection",
    )
    p.add_argument("-s", "--search", default="", help="scope: filter by search query")
    p.add_argument(
        "-n", "--nested", action="store_true", help="scope: include nested collections"
    )

    p = _p(sub, "tag", common, commands.cmd_tag, help="add/remove tags on raindrop(s)")
    p.add_argument("ids", type=int, nargs="*", help="raindrop id(s)")
    p.add_argument("--add", nargs="+", help="tags to add")
    p.add_argument("--remove", nargs="+", help="tags to remove (id mode only)")
    p.add_argument("--clear", action="store_true", help="remove all tags first")
    p.add_argument(
        "--from",
        dest="from_collection",
        type=int,
        help="scope: apply to all raindrops in this collection",
    )
    p.add_argument("-s", "--search", default="", help="scope: filter by search query")
    p.add_argument(
        "-n", "--nested", action="store_true", help="scope: include nested collections"
    )

    p = _p(sub, "cover", common, commands.cmd_cover, help="upload a raindrop cover")
    p.add_argument("id", type=int, help="raindrop id")
    p.add_argument("file", help="image file (PNG, GIF, or JPEG)")

    p = _p(
        sub,
        "import",
        common,
        commands.cmd_import,
        help="parse/import a Netscape/Pocket/Instapaper HTML export",
    )
    p.add_argument("file", help="HTML bookmark export file")
    p.add_argument(
        "--create",
        action="store_true",
        help="actually create the parsed bookmarks (default: just parse)",
    )
    p.add_argument(
        "-c", "--collection", type=int, default=-1, help="destination collection id"
    )

    p = _p(sub, "export", common, commands.cmd_export, help="export raindrops")
    p.add_argument(
        "-c", "--collection", type=int, default=0, help="collection id (0 all)"
    )
    p.add_argument(
        "-f",
        "--format",
        default="csv",
        choices=("csv", "html", "zip"),
        help="export format",
    )
    p.add_argument("--sort", default="-created", choices=SORTS, help="sort order")
    p.add_argument("-s", "--search", default="", help="search query")
    p.add_argument("-o", "--output", help="write to file instead of stdout")


# -- collections --------------------------------------------------------------


def _add_collection_commands(sub, common):
    c = sub.add_parser("collections", aliases=["c"], help="manage collections")
    csub = c.add_subparsers(dest="subcommand", metavar="<action>", required=True)

    _p(
        csub,
        "list",
        common,
        commands.cmd_collections_list,
        help="list root collections",
    )
    _p(
        csub,
        "tree",
        common,
        commands.cmd_collections_tree,
        help="nested collection tree",
    )

    p = _p(
        csub, "view", common, commands.cmd_collections_view, help="view a collection"
    )
    p.add_argument("id", type=int, help="collection id")

    p = _p(
        csub, "add", common, commands.cmd_collections_add, help="create a collection"
    )
    p.add_argument("title", help="collection title")
    p.add_argument("--view", choices=VIEWS, help="view style")
    p.add_argument("--parent", type=int, help="parent collection id")
    p.add_argument("--public", action="store_true", help="make public")

    p = _p(
        csub, "edit", common, commands.cmd_collections_edit, help="edit a collection"
    )
    p.add_argument("id", type=int, help="collection id")
    p.add_argument("-t", "--title", help="new title")
    p.add_argument("--view", choices=VIEWS, help="view style")
    p.add_argument("--parent", type=int, help="move under parent id")
    p.add_argument("--public", action="store_true", help="make public")
    p.add_argument("--private", action="store_true", help="make private")

    p = _p(csub, "rm", common, commands.cmd_collections_rm, help="delete a collection")
    p.add_argument("id", type=int, help="collection id")

    p = _p(
        csub, "merge", common, commands.cmd_collections_merge, help="merge collections"
    )
    p.add_argument("to", type=int, help="destination collection id")
    p.add_argument("ids", type=int, nargs="+", help="source collection ids")

    _p(
        csub,
        "clean",
        common,
        commands.cmd_collections_clean,
        help="remove empty collections",
    )
    _p(
        csub,
        "empty-trash",
        common,
        commands.cmd_collections_empty_trash,
        help="permanently empty trash",
    )

    p = _p(
        csub,
        "reorder",
        common,
        commands.cmd_collections_reorder,
        help="reorder all collections",
    )
    p.add_argument(
        "--by",
        default="title",
        choices=("title", "-title", "-count"),
        help="sort key",
    )

    p = _p(
        csub,
        "cover",
        common,
        commands.cmd_collections_cover,
        help="upload a collection cover",
    )
    p.add_argument("id", type=int, help="collection id")
    p.add_argument("file", help="image file (PNG, GIF, or JPEG)")

    p = _p(
        csub,
        "covers",
        common,
        commands.cmd_collections_covers,
        help="search the icon/cover library",
    )
    p.add_argument("text", help="search text (e.g. 'pokemon')")


# -- tags ---------------------------------------------------------------------


def _add_tag_commands(sub, common):
    t = sub.add_parser("tags", aliases=["t"], help="manage tags")
    tsub = t.add_subparsers(dest="subcommand", metavar="<action>", required=True)

    p = _p(tsub, "list", common, commands.cmd_tags_list, help="list tags")
    p.add_argument("-c", "--collection", type=int, help="restrict to collection id")

    p = _p(tsub, "rename", common, commands.cmd_tags_rename, help="rename a tag")
    p.add_argument("old", help="existing tag")
    p.add_argument("new", help="new name")
    p.add_argument("-c", "--collection", type=int, help="restrict to collection id")

    p = _p(tsub, "merge", common, commands.cmd_tags_merge, help="merge tags into one")
    p.add_argument("into", help="destination tag name")
    p.add_argument("tags", nargs="+", help="tags to merge")
    p.add_argument("-c", "--collection", type=int, help="restrict to collection id")

    p = _p(tsub, "rm", common, commands.cmd_tags_rm, help="delete tags")
    p.add_argument("tags", nargs="+", help="tags to delete")
    p.add_argument("-c", "--collection", type=int, help="restrict to collection id")


# -- highlights ---------------------------------------------------------------


def _add_highlight_commands(sub, common):
    h = sub.add_parser("highlights", aliases=["h"], help="manage highlights")
    hsub = h.add_subparsers(dest="subcommand", metavar="<action>", required=True)

    p = _p(hsub, "list", common, commands.cmd_highlights_list, help="list highlights")
    p.add_argument("-r", "--raindrop", type=int, help="highlights of one raindrop")
    p.add_argument("-a", "--all", action="store_true", help="fetch all pages")
    p.add_argument("--page", type=int, default=0, help="page number")
    p.add_argument("--perpage", type=int, default=25, help="items per page (max 50)")

    p = _p(hsub, "add", common, commands.cmd_highlights_add, help="add a highlight")
    p.add_argument("raindrop", type=int, help="raindrop id")
    p.add_argument("text", help="text to highlight")
    p.add_argument("--color", default="yellow", choices=COLORS, help="highlight colour")
    p.add_argument("--note", default="", help="note for the highlight")

    p = _p(hsub, "edit", common, commands.cmd_highlights_edit, help="edit a highlight")
    p.add_argument("raindrop", type=int, help="raindrop id")
    p.add_argument("highlight", help="highlight id")
    p.add_argument("--text", help="new text")
    p.add_argument("--color", choices=COLORS, help="new colour")
    p.add_argument("--note", help="new note")

    p = _p(hsub, "rm", common, commands.cmd_highlights_rm, help="remove a highlight")
    p.add_argument("raindrop", type=int, help="raindrop id")
    p.add_argument("highlight", help="highlight id")


# -- pinboard -----------------------------------------------------------------


def _add_pinboard_commands(sub, common):
    pb = sub.add_parser(
        "pinboard", aliases=["pb"], help="manage Pinboard bookmarks (second service)"
    )
    psub = pb.add_subparsers(dest="subcommand", metavar="<action>", required=True)

    p = _pb(psub, "list", common, commands.cmd_pb_list, help="list bookmarks")
    p.add_argument("--tag", action="append", help="filter by tag (repeatable, max 3)")
    p.add_argument("--count", type=int, default=15, help="recent count (max 100)")
    p.add_argument("-a", "--all", action="store_true", help="fetch all bookmarks")
    p.add_argument("--toread", action="store_true", help="only unread (to-read) items")
    p.add_argument("-d", "--detailed", action="store_true", help="show description")

    p = _pb(psub, "get", common, commands.cmd_pb_get, help="show one bookmark by URL")
    p.add_argument("url", help="bookmark URL (Pinboard's key)")

    p = _pb(psub, "add", common, commands.cmd_pb_add, help="add a bookmark")
    p.add_argument("url", help="URL to bookmark")
    p.add_argument("-t", "--title", help="title (Pinboard 'description')")
    p.add_argument("--extended", help="extended note (Pinboard 'extended')")
    p.add_argument("--tags", nargs="*", help="tags")
    p.add_argument("--toread", action="store_true", help="mark unread")
    p.add_argument("--shared", action="store_true", help="make public")
    p.add_argument("--private", action="store_true", help="make private")
    p.add_argument(
        "--no-replace", action="store_true", help="fail if the URL is already saved"
    )
    p.add_argument("--dt", help="UTC datetime (YYYY-MM-DDTHH:MM:SSZ)")

    p = _pb(psub, "rm", common, commands.cmd_pb_rm, help="delete a bookmark by URL")
    p.add_argument("url", help="bookmark URL")

    p = _pb(psub, "edit", common, commands.cmd_pb_edit, help="edit a bookmark")
    p.add_argument("url", help="bookmark URL")
    p.add_argument("-t", "--title", help="new title")
    p.add_argument("--extended", help="new extended note")
    p.add_argument("--tags", nargs="*", help="replace tags")
    p.add_argument("--toread", action="store_true", help="mark unread")
    p.add_argument("--not-toread", action="store_true", help="mark read")
    p.add_argument("--shared", action="store_true", help="make public")
    p.add_argument("--private", action="store_true", help="make private")

    p = _pb(psub, "tag", common, commands.cmd_pb_tag, help="add/remove tags on a URL")
    p.add_argument("url", help="bookmark URL")
    p.add_argument("--add", nargs="+", help="tags to add")
    p.add_argument("--remove", nargs="+", help="tags to remove")
    p.add_argument("--clear", action="store_true", help="remove all tags first")

    p = _pb(
        psub, "suggest", common, commands.cmd_pb_suggest, help="suggest tags for a URL"
    )
    p.add_argument("url", help="URL to get tag suggestions for")

    t = psub.add_parser("tags", help="manage Pinboard tags")
    tsub = t.add_subparsers(dest="tagaction", metavar="<action>", required=True)
    _pb(tsub, "list", common, commands.cmd_pb_tags_list, help="list tags")
    pr = _pb(tsub, "rename", common, commands.cmd_pb_tags_rename, help="rename a tag")
    pr.add_argument("old", help="existing tag")
    pr.add_argument("new", help="new name")
    prm = _pb(tsub, "rm", common, commands.cmd_pb_tags_rm, help="delete tag(s)")
    prm.add_argument("tags", nargs="+", help="tags to delete")

    n = psub.add_parser("notes", help="read Pinboard notes")
    nsub = n.add_subparsers(dest="noteaction", metavar="<action>", required=True)
    _pb(nsub, "list", common, commands.cmd_pb_notes_list, help="list notes")
    nv = _pb(nsub, "view", common, commands.cmd_pb_notes_view, help="view a note")
    nv.add_argument("id", help="note id")


# -- misc ---------------------------------------------------------------------


def _add_misc_commands(sub, common):
    # `rd user` shows the account; `rd user set ...` updates it.
    u = sub.add_parser(
        "user", parents=[common], help="show or update the authenticated user"
    )
    u.set_defaults(func=commands.cmd_user, needs_client=True)
    usub = u.add_subparsers(dest="subcommand", metavar="<action>")
    _p(usub, "show", common, commands.cmd_user, help="show authenticated user")
    us = _p(usub, "set", common, commands.cmd_user_set, help="update user settings")
    us.add_argument("--name", help="full name")
    us.add_argument("--email", help="email address")
    us.add_argument("--new-password", help="new password (needs --old-password)")
    us.add_argument("--old-password", help="current password")
    us.add_argument(
        "--config", nargs="+", metavar="KEY=VALUE", help="config key=value pairs"
    )

    _p(sub, "stats", common, commands.cmd_stats, help="system collection counts")

    p = _p(
        sub,
        "sync",
        common,
        commands.cmd_sync,
        needs_client=False,
        help="two-way additive sync between Raindrop and Pinboard (try --dry-run)",
    )
    p.add_argument(
        "--direction",
        choices=("both", "to-pinboard", "to-raindrop"),
        default="both",
        help="limit which side is written (default both)",
    )
    p.add_argument(
        "--collection",
        type=int,
        action="append",
        help="scope: only push Raindrop items in this collection id (repeatable)",
    )
    p.add_argument(
        "--rd-tag",
        action="append",
        help="scope: only push Raindrop items with this tag (repeatable)",
    )
    p.add_argument(
        "--pb-tag",
        action="append",
        help="scope: only push Pinboard items with this tag (repeatable)",
    )

    p = _p(
        sub,
        "filters",
        common,
        commands.cmd_filters,
        help="context filters for a collection",
    )
    p.add_argument(
        "-c", "--collection", type=int, default=0, help="collection id (0 all)"
    )
    p.add_argument(
        "--tags-sort", default="-count", choices=("-count", "_id"), help="tag sort"
    )
    p.add_argument("-s", "--search", default="", help="search query")

    p = _p(
        sub,
        "suggest",
        common,
        commands.cmd_suggest,
        help="suggest collections/tags for a URL",
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="suggest for a new URL")
    group.add_argument("--id", type=int, help="suggest for an existing raindrop id")

    p = _p(
        sub,
        "exists",
        common,
        commands.cmd_exists,
        help="check if URL(s) are already saved",
    )
    p.add_argument("urls", nargs="+", help="URLs to check")

    b = sub.add_parser("backups", help="manage backups")
    bsub = b.add_subparsers(dest="subcommand", metavar="<action>", required=True)
    _p(bsub, "list", common, commands.cmd_backups_list, help="list backups")
    _p(bsub, "create", common, commands.cmd_backups_create, help="request a new backup")
    p = _p(
        bsub,
        "download",
        common,
        commands.cmd_backups_download,
        help="download a backup",
    )
    p.add_argument("id", help="backup id")
    p.add_argument(
        "-f", "--format", default="csv", choices=("csv", "html"), help="format"
    )
    p.add_argument("-o", "--output", help="output path")


# -- config -------------------------------------------------------------------


def _add_config_commands(sub, common):
    c = sub.add_parser("config", help="manage rd-cli configuration")
    csub = c.add_subparsers(dest="subcommand", metavar="<action>", required=True)
    _p(
        csub,
        "path",
        common,
        commands.cfg_path,
        needs_client=False,
        help="print config file path",
    )
    _p(
        csub,
        "show",
        common,
        commands.cfg_show,
        needs_client=False,
        help="show config (token masked)",
    )
    p = _p(
        csub,
        "set-token",
        common,
        commands.cfg_set_token,
        needs_client=False,
        help="store the Raindrop API token",
    )
    p.add_argument("token", help="Raindrop.io test/access token")

    p = _p(
        csub,
        "set-pinboard-token",
        common,
        commands.cfg_set_pinboard_token,
        needs_client=False,
        help="store the Pinboard API token",
    )
    p.add_argument("token", help="Pinboard token (format user:HEX)")


# -- back-compat aliases ------------------------------------------------------


def _add_aliases(sub, common):
    """Hidden flat aliases for the original command names (no regression)."""
    p = _p(sub, "c-list", common, commands.cmd_collections_list)
    p = _p(sub, "c-add", common, commands.cmd_collections_add)
    p.add_argument("title")
    p.add_argument("--view", choices=VIEWS)
    p.add_argument("--parent", type=int)
    p.add_argument("--public", action="store_true")
    p = _p(sub, "c-rm", common, commands.cmd_collections_rm)
    p.add_argument("id", type=int)

    p = _p(sub, "t-list", common, commands.cmd_tags_list)
    p.add_argument("-c", "--collection", type=int)
    p = _p(sub, "t-rm", common, commands.cmd_tags_rm)
    p.add_argument("tags", nargs="+")
    p.add_argument("-c", "--collection", type=int)

    p = _p(sub, "h-list", common, commands.cmd_highlights_list)
    p.add_argument("-r", "--raindrop", type=int)
    p.add_argument("-a", "--all", action="store_true")
    p.add_argument("--page", type=int, default=0)
    p.add_argument("--perpage", type=int, default=25)
    p = _p(sub, "h-add", common, commands.cmd_highlights_add)
    p.add_argument("raindrop", type=int)
    p.add_argument("text")
    p.add_argument("--color", default="yellow", choices=COLORS)
    p.add_argument("--note", default="")
    p = _p(sub, "h-rm", common, commands.cmd_highlights_rm)
    p.add_argument("raindrop", type=int)
    p.add_argument("highlight")


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()
    if not argv:
        parser.print_help()
        return 0

    args = parser.parse_args(argv)
    args.json = getattr(args, "json", False)
    args.no_color = getattr(args, "no_color", False)
    args.dry_run = getattr(args, "dry_run", False)
    output.configure(no_color=args.no_color)

    if not getattr(args, "func", None):
        parser.print_help()
        return 0

    try:
        client = None
        if getattr(args, "needs_pinboard", False):
            client = PinboardClient(
                config.resolve_pinboard_token(), dry_run=args.dry_run
            )
        elif getattr(args, "needs_client", False):
            client = RaindropClient(config.resolve_token(), dry_run=args.dry_run)
        return args.func(client, args)
    except RaindropError as exc:
        if getattr(args, "json", False):
            output.emit_json({"error": str(exc)})
        else:
            output.error(str(exc))
        return 1
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    sys.exit(main())
