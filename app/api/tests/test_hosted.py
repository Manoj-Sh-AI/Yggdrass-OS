"""The hosted (Railway) startup: settings come only from variables and land in the two
private files the existing runtime reads. Invented values only; nothing is started."""

import json
from pathlib import Path

import pytest

from yggdress_app import hosted

VARIABLES = {
    "YGGDRESS_DATABASE_URL": "host=db user=yggdras_application password=a sslmode=require",
    "YGGDRESS_MIGRATION_URL": "host=db user=ygg_app_owner password=b sslmode=require",
    "YGGDRESS_ADMIN_URL": "host=db user=postgres password=c sslmode=require",
    "BRAIN_DATABASE_URL": "host=db user=ygg_brain password=d sslmode=require",
    "YGGDRESS_PASSWORD_HASH": "scrypt$invented",
    "YGGDRESS_ORIGIN": "http://127.0.0.1:3000/",
    "ANTHROPIC_API_KEY": "invented-key",
    "LIVEKIT_URL": "wss://invented.livekit.cloud",
    "YGGDRAS_CALLS_MODE": "live",
    "UNRELATED_SECRET": "must-not-be-copied",
}


@pytest.fixture
def binary(tmp_path):
    path = tmp_path / "temporal"
    path.write_bytes(b"invented temporal binary")
    return str(path)


def test_missing_variables_are_named_and_nothing_is_written(tmp_path):
    with pytest.raises(SystemExit, match="YGGDRESS_ORIGIN"):
        hosted.bootstrap({k: v for k, v in VARIABLES.items() if k != "YGGDRESS_ORIGIN"}, tmp_path)
    assert not (tmp_path / "runtime.json").exists()


def test_the_brain_env_holds_only_the_brain_settings_and_a_fresh_service_password(tmp_path):
    first = hosted.brain_env(VARIABLES, tmp_path)
    second = hosted.brain_env(VARIABLES, tmp_path)
    assert "BRAIN_DATABASE_URL='host=db user=ygg_brain password=d sslmode=require'" in first
    assert "YGGDRAS_BRAIN_SOURCE='rows'" in first and "LIVEKIT_URL='wss://" in first
    assert "UNRELATED_SECRET" not in first and "YGGDRESS_ADMIN_URL" not in first
    password = [line for line in first.splitlines() if line.startswith("BRAIN_API_PASSWORD=")]
    assert password and password[0] not in second  # new on every start
    with pytest.raises(ValueError):
        hosted.brain_env({**VARIABLES, "ANTHROPIC_API_KEY": "it's"}, tmp_path)


def test_runtime_settings_are_the_hosted_remote_layout(tmp_path, binary):
    config = hosted.runtime({**VARIABLES, "TEMPORAL_BINARY": binary}, tmp_path)
    assert config["database_host"] == "remote" and config["origin"] == "http://127.0.0.1:3000"
    assert config["agents"]["execution_backend"] == "temporal"
    assert Path(config["agents"]["lia_skills"]).name == "lia"
    assert len(config["agents"]["temporal"]["sha256"]) == 64
    assert config["mobile_sensitive_access"] is True
    assert Path(config["brain_env"]) == hosted.REPO / ".env"


def test_lias_skills_ship_with_the_app():
    skills = hosted.REPO / "app" / "skills" / "lia"
    assert (skills / "core.md").is_file() and any((skills / "library").glob("*.md"))
    assert not (hosted.REPO / "app" / "skills" / "dharma-check").exists()  # stays private


def test_bootstrap_writes_private_runtime_settings(tmp_path, binary, monkeypatch):
    written = {}
    monkeypatch.setattr(hosted, "REPO", tmp_path / "repo")
    (tmp_path / "repo").mkdir()
    folder = hosted.bootstrap({**VARIABLES, "TEMPORAL_BINARY": binary}, tmp_path / "data")
    written["runtime"] = json.loads((folder / "runtime.json").read_text())
    assert written["runtime"]["database_url"] == VARIABLES["YGGDRESS_DATABASE_URL"]
    assert (tmp_path / "repo" / ".env").read_text().count("\n") >= 6
    assert (folder / "local-data").is_dir()


def test_serve_needs_no_laptop_only_setting_in_hosted_mode(tmp_path, binary):
    """Regression: the first Railway start failed on the laptop's web build folder."""
    from yggdress_app.local_runtime import web_environment

    config = hosted.runtime({**VARIABLES, "TEMPORAL_BINARY": binary}, tmp_path)
    assert "build_dir" not in config and "node" not in config and "web" not in config
    assert web_environment(config, 8080)["YGGDRESS_API_URL"] == "http://127.0.0.1:8080"
