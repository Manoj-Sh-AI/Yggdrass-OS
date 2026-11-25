"""The hosted (Railway) startup: settings come only from variables and land in the two
private files the existing runtime reads. Invented values only; nothing is started."""

import json
import os
import stat
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
    assert config["agents"]["execution_backend"] == "threads"  # lean: no Temporal server
    assert "temporal" not in config["agents"]
    assert Path(config["agents"]["lia_skills"]).name == "lia"
    full = hosted.runtime(
        {**VARIABLES, "TEMPORAL_BINARY": binary, "YGGDRAS_EXECUTION_BACKEND": "temporal"}, tmp_path
    )
    assert len(full["agents"]["temporal"]["sha256"]) == 64
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


def test_the_laptop_web_app_talks_to_the_hosted_backend_when_one_is_set():
    from yggdress_app.local_runtime import web_environment

    laptop = {"origin": "http://127.0.0.1:3000", "build_dir": ".next-x"}
    assert web_environment(laptop, 8100)["YGGDRESS_API_URL"] == "http://127.0.0.1:8100"
    hosted_backend = {**laptop, "backend_url": "https://backend.example.up.railway.app"}
    env = web_environment(hosted_backend, 0)
    assert env["YGGDRESS_API_URL"] == "https://backend.example.up.railway.app"
    assert env["YGGDRESS_ORIGIN"] == "http://127.0.0.1:3000"


def test_without_temporal_a_thread_sweeps_the_calls_and_survives_a_failure(capsys):
    from yggdress_app.local_runtime import sweep_calls

    class Calls:
        ticks = 0

        def tick(self):
            Calls.ticks += 1
            if Calls.ticks == 2:
                raise RuntimeError("database briefly away")

    sweep_calls(Calls(), every=0, rounds=3)
    assert Calls.ticks == 3 and "call sweep failed: RuntimeError" in capsys.readouterr().out


def test_the_hosted_api_socket_answers_on_ipv4_loopback_and_ipv6():
    """Chat, delivery and the voice worker call the API on 127.0.0.1 inside the container,
    while Railway's private network reaches it over IPv6. uvicorn's own "::" bind is
    IPv6-only, so the hosted API needs a dual-stack socket (chat never answered on Railway)."""
    import threading
    import time
    import urllib.request

    import uvicorn

    from yggdress_app.local_runtime import dual_stack_socket, port

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    number = port()
    server = uvicorn.Server(uvicorn.Config(app, host="::", port=number, log_level="error"))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [dual_stack_socket(number)]}, daemon=True
    )
    thread.start()
    try:
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.05)
        for host in ("127.0.0.1", "[::1]"):
            with urllib.request.urlopen(f"http://{host}:{number}/", timeout=5) as reply:
                assert reply.read() == b"ok", host
    finally:
        server.should_exit = True
        thread.join(5)


def test_serve_gives_the_hosted_api_the_dual_stack_socket():
    """Guards the wiring, not just the helper: a plain host="::" start regresses chat."""
    import inspect

    from yggdress_app import local_runtime

    source = inspect.getsource(local_runtime.serve)
    assert "dual_stack_socket(api_port)" in source
    assert 'kwargs={"sockets": sockets}' in source


# ---- Firebase service account from a Railway variable --------------------------------------
INVENTED_ACCOUNT = {
    "type": "service_account",
    "project_id": "invented-project",
    "private_key": "-----BEGIN PRIVATE KEY-----\ninvented\n-----END PRIVATE KEY-----\n",
    "client_email": "invented@invented-project.iam.gserviceaccount.com",
}


def test_the_service_account_variable_becomes_a_private_file_and_its_path(tmp_path):
    env = {hosted.FIREBASE_JSON: json.dumps(INVENTED_ACCOUNT)}
    target = hosted.firebase_account(env, tmp_path)
    assert target == tmp_path / "secrets" / "firebase-service-account.json"
    assert json.loads(target.read_text(encoding="utf-8")) == INVENTED_ACCOUNT
    assert env["FIREBASE_SERVICE_ACCOUNT_FILE"] == str(target)
    assert not target.with_name(target.name + ".partial").exists()
    if os.name != "nt":  # POSIX permissions (the container is Linux)
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
        assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    # rewritten on every start, so a redeploy without a volume still has it
    env2 = {hosted.FIREBASE_JSON: json.dumps({**INVENTED_ACCOUNT, "project_id": "second"})}
    hosted.firebase_account(env2, tmp_path)
    assert json.loads(target.read_text(encoding="utf-8"))["project_id"] == "second"


def test_no_variable_means_no_file_and_no_change(tmp_path):
    env = {"FIREBASE_SERVICE_ACCOUNT_FILE": "/keep/this.json"}
    assert hosted.firebase_account(env, tmp_path) is None
    assert env == {"FIREBASE_SERVICE_ACCOUNT_FILE": "/keep/this.json"}
    assert not (tmp_path / "secrets").exists()


@pytest.mark.parametrize(
    "value",
    ["{not json", json.dumps({"type": "authorized_user", "private_key": "x"}), json.dumps([1])],
)
def test_a_bad_value_is_named_never_echoed_and_nothing_is_written(tmp_path, value):
    secret_bit = "invented-secret-marker"
    env = {hosted.FIREBASE_JSON: value.replace("x", secret_bit)}
    with pytest.raises(SystemExit) as caught:
        hosted.firebase_account(env, tmp_path)
    assert hosted.FIREBASE_JSON in str(caught.value)
    assert secret_bit not in str(caught.value) and "{" not in str(caught.value)
    assert not (tmp_path / "secrets" / "firebase-service-account.json").exists()
    assert "FIREBASE_SERVICE_ACCOUNT_FILE" not in env


def test_the_brain_env_receives_the_written_path(tmp_path):
    env = {**VARIABLES, hosted.FIREBASE_JSON: json.dumps(INVENTED_ACCOUNT)}
    target = hosted.firebase_account(env, tmp_path)
    text = hosted.brain_env(env, tmp_path)
    assert f"FIREBASE_SERVICE_ACCOUNT_FILE='{target}'" in text
    assert hosted.FIREBASE_JSON not in text and "PRIVATE KEY" not in text
