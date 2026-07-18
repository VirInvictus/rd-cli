from __future__ import annotations

import io

from rd_cli import output


def test_configure_disables_color_when_not_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    output.configure(stream=io.StringIO())  # StringIO has no isatty->True
    assert output.color("x", "id") == "x"


def test_configure_respects_no_color_env(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")

    class TTY(io.StringIO):
        def isatty(self):
            return True

    output.configure(stream=TTY())
    assert output.color("x", "id") == "x"


def test_color_wraps_when_enabled(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)

    class TTY(io.StringIO):
        def isatty(self):
            return True

    output.configure(stream=TTY())
    wrapped = output.color("x", "id")
    assert wrapped.startswith("\033[")
    assert wrapped.endswith("\033[0m")
    assert "x" in wrapped


def test_visible_len_ignores_ansi():
    assert output._visible_len("\033[1mabc\033[0m") == 3
    assert output._visible_len("plain") == 5


def test_format_raindrop_line_plain(monkeypatch):
    output.configure(stream=io.StringIO())  # color off
    item = {
        "_id": 12,
        "title": "Hello",
        "link": "https://x.com",
        "tags": ["a", "b"],
        "excerpt": "desc",
        "important": True,
    }
    line = output.format_raindrop_line(item, detailed=True)
    assert "[12]" in line
    assert "Hello" in line
    assert "https://x.com" in line
    assert "#a" in line and "#b" in line


def test_collection_tree_indents_children():
    output.configure(stream=io.StringIO())
    roots = [{"_id": 1, "title": "Root", "count": 2}]
    children = [
        {"_id": 2, "title": "Child", "count": 0, "parent": {"$id": 1}, "sort": 0},
        {"_id": 3, "title": "Grand", "count": 0, "parent": {"$id": 2}, "sort": 0},
    ]
    tree = output.format_collection_tree(roots, children)
    lines = tree.splitlines()
    assert lines[0].startswith("[1]")
    assert lines[1].startswith("  [2]")
    assert lines[2].startswith("    [3]")


def test_columns_alignment():
    output.configure(stream=io.StringIO())
    rows = [("[1]", "short"), ("[100]", "longer title")]
    rendered = output._columns(rows, headers=None)
    lines = rendered.splitlines()
    # Both id columns padded to the same width -> titles start at same offset.
    assert lines[0].index("short") == lines[1].index("longer")
