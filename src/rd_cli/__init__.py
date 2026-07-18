"""rd-cli — a stdlib-only command-line client for Raindrop.io.

The version is sourced from installed package metadata, falling back to the
root ``VERSION`` file for editable/source checkouts. ``VERSION`` is the single
source of truth (see CLAUDE.md).
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _version() -> str:
    try:
        return version("rd-cli")
    except PackageNotFoundError:
        version_file = Path(__file__).resolve().parent.parent.parent / "VERSION"
        try:
            return version_file.read_text(encoding="utf-8").strip()
        except OSError:
            return "0.0.0"


__version__ = _version()
