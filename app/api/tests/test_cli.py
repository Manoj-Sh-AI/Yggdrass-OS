import ast
import os
import secrets
import sys

import pytest

from yggdress_app.cli import main
from yggdress_app.security import valid_hash, verify_password


def test_password_setup_writes_only_a_quoted_hash_and_refuses_overwrite(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    password = secrets.token_urlsafe(24)
    monkeypatch.setattr("yggdress_app.cli.getpass.getpass", lambda _: password)
    monkeypatch.setattr(
        sys, "argv", ["application", "password", "--output", "runtime/password.env"]
    )
    main()
    saved = (tmp_path / "runtime/password.env").read_text()
    assert password not in saved
    if os.name != "nt":
        assert (tmp_path / "runtime/password.env").stat().st_mode & 0o777 == 0o600
    value = saved.strip().split("=", 1)[1]
    assert value.startswith("'") and value.endswith("'")
    hashed = ast.literal_eval(value)
    assert valid_hash(hashed) and verify_password(password, hashed)
    output = capsys.readouterr()
    assert password not in output.out and hashed not in output.out
    with pytest.raises(SystemExit):
        main()
    assert (tmp_path / "runtime/password.env").read_text() == saved
