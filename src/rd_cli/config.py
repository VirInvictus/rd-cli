"""Token and configuration resolution.

Resolution order for the access token (first hit wins):

1. ``RAINDROP_TOKEN`` environment variable.
2. ``RAINDROP_TEST_TOKEN`` environment variable (back-compat alias).
3. ``token`` key in ``$XDG_CONFIG_HOME/rd-cli/config.toml``.
4. ``RAINDROP_TOKEN`` / ``RAINDROP_TEST_TOKEN`` in a ``.env`` file, searched in
   the current directory then ``$XDG_CONFIG_HOME/rd-cli/.env``.

The ``.env`` reader is a deliberately tiny stdlib parser so we carry no
``python-dotenv`` dependency. It only loads keys that are not already in the
environment, matching python-dotenv's default and keeping real env vars
authoritative.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from .errors import ConfigError

ENV_VARS = ("RAINDROP_TOKEN", "RAINDROP_TEST_TOKEN")
PINBOARD_ENV_VARS = ("PINBOARD_TOKEN", "PINBOARD_API_TOKEN")


def config_dir() -> Path:
    """Return the rd-cli config directory (respects ``XDG_CONFIG_HOME``)."""
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / "rd-cli"


def config_path() -> Path:
    """Path to ``config.toml`` (may not exist)."""
    return config_dir() / "config.toml"


def parse_env(text: str) -> dict[str, str]:
    """Parse ``.env`` text into a dict. Supports ``KEY=value``, ``export KEY=v``,
    ``#`` comments, blank lines, and single/double quoted values."""
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            result[key] = value
    return result


def load_env_files(paths: list[Path] | None = None) -> None:
    """Load the first existing ``.env`` file into ``os.environ`` (non-clobbering)."""
    if paths is None:
        paths = [Path.cwd() / ".env", config_dir() / ".env"]
    for path in paths:
        if not path.is_file():
            continue
        for key, value in parse_env(path.read_text(encoding="utf-8")).items():
            os.environ.setdefault(key, value)
        return


def read_config() -> dict:
    """Read ``config.toml`` as a dict; empty dict if it does not exist."""
    path = config_path()
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc


def resolve_token() -> str:
    """Resolve the access token, or raise :class:`ConfigError` if none is found."""
    load_env_files()
    for var in ENV_VARS:
        token = os.environ.get(var)
        if token:
            return token.strip()
    token = read_config().get("token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    raise ConfigError(
        "No Raindrop token found. Set RAINDROP_TOKEN, add it to "
        f"{config_path()} via `rd config set-token <token>`, or put it in a "
        ".env file. Get a test token at "
        "https://app.raindrop.io/settings/integrations"
    )


def resolve_pinboard_token() -> str:
    """Resolve the Pinboard API token (format ``user:HEX``), or raise.

    Same precedence as :func:`resolve_token` but for the ``PINBOARD_TOKEN`` /
    ``PINBOARD_API_TOKEN`` env vars and the ``pinboard_token`` config key.
    """
    load_env_files()
    for var in PINBOARD_ENV_VARS:
        token = os.environ.get(var)
        if token:
            return token.strip()
    token = read_config().get("pinboard_token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    raise ConfigError(
        "No Pinboard token found. Set PINBOARD_TOKEN, add it to "
        f"{config_path()} via `rd config set-pinboard-token <token>`, or put it "
        "in a .env file. Your token (format user:HEX) is at "
        "https://pinboard.in/settings/password"
    )


def write_token(token: str) -> Path:
    """Persist the Raindrop ``token`` to ``config.toml`` (0600), keeping others."""
    return _write_config_key("token", token)


def write_pinboard_token(token: str) -> Path:
    """Persist ``pinboard_token`` to ``config.toml`` (0600), keeping others."""
    return _write_config_key("pinboard_token", token)


def _write_config_key(key: str, value: str) -> Path:
    """Set one string key in ``config.toml`` (0600), preserving every other key.
    The written key is emitted first; order is cosmetic."""
    value = value.strip()
    if not value:
        raise ConfigError(f"Refusing to write an empty {key}.")
    data = read_config()
    data[key] = value
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [_toml_line(key, value)]
    for other, val in data.items():
        if other == key:
            continue
        lines.append(_toml_line(other, val))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def _toml_line(key: str, value: object) -> str:
    if isinstance(value, bool):
        return f"{key} = {str(value).lower()}"
    if isinstance(value, (int, float)):
        return f"{key} = {value}"
    return f'{key} = "{value}"'
