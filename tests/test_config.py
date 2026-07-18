from __future__ import annotations

import stat

import pytest

from rd_cli import config
from rd_cli.errors import ConfigError


def test_parse_env_handles_comments_quotes_and_export():
    text = (
        "# a comment\n"
        "\n"
        "RAINDROP_TOKEN=plain\n"
        'export QUOTED="with spaces"\n'
        "SINGLE='sq'\n"
        "NOEQ line without equals\n"
    )
    parsed = config.parse_env(text)
    assert parsed == {
        "RAINDROP_TOKEN": "plain",
        "QUOTED": "with spaces",
        "SINGLE": "sq",
    }


def test_resolve_token_prefers_primary_env(monkeypatch):
    monkeypatch.setenv("RAINDROP_TOKEN", "primary")
    monkeypatch.setenv("RAINDROP_TEST_TOKEN", "alias")
    assert config.resolve_token() == "primary"


def test_resolve_token_falls_back_to_alias(monkeypatch):
    monkeypatch.delenv("RAINDROP_TOKEN", raising=False)
    monkeypatch.setenv("RAINDROP_TEST_TOKEN", "alias")
    assert config.resolve_token() == "alias"


def test_resolve_token_reads_config_file(monkeypatch, tmp_path):
    monkeypatch.delenv("RAINDROP_TOKEN", raising=False)
    monkeypatch.delenv("RAINDROP_TEST_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)  # avoid picking up a stray ./.env
    cfg_dir = tmp_path / "rd-cli"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text('token = "from-file"\n')
    assert config.resolve_token() == "from-file"


def test_resolve_token_missing_raises(monkeypatch, tmp_path):
    monkeypatch.delenv("RAINDROP_TOKEN", raising=False)
    monkeypatch.delenv("RAINDROP_TEST_TOKEN", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        config.resolve_token()


def test_env_file_does_not_clobber_real_env(monkeypatch, tmp_path):
    monkeypatch.setenv("RAINDROP_TOKEN", "real")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("RAINDROP_TOKEN=fromfile\n")
    config.load_env_files()
    assert config.resolve_token() == "real"


def test_write_token_roundtrip_and_permissions(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = config.write_token("secret-token")
    assert path.exists()
    assert config.read_config()["token"] == "secret-token"
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600


def test_write_token_rejects_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(ConfigError):
        config.write_token("   ")
