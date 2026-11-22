import pytest

from yggdress_app.side_effects import side_effects_allowed
from yggdress_app.voice import FcmPusher, PushNotConfigured


@pytest.mark.parametrize(("name", "allowed"), [("", True), ("production", True),
                                                ("staging", False), ("pr-12", False)])  # fmt: skip
def test_side_effects_only_in_production(monkeypatch, name, allowed):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", name)
    assert side_effects_allowed() is allowed


def test_a_non_production_environment_cannot_push(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "invented")
    monkeypatch.setenv("FIREBASE_SERVICE_ACCOUNT_FILE", "invented.json")
    with pytest.raises(PushNotConfigured, match="outside production"):
        FcmPusher()
