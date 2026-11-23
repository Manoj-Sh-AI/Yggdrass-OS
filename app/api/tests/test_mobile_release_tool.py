"""The mobile release tool never offers an APK signed with the public debug key."""

import importlib.util
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "mobile" / "scripts" / "mobile-release.py"


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("mobile_release", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_debug_key_is_refused(tool):
    with pytest.raises(SystemExit, match="public debug key"):
        tool.check_signers([tool.PUBLIC_DEBUG_SIGNER])


def test_unsigned_apk_is_refused(tool):
    with pytest.raises(SystemExit, match="no verifiable signature"):
        tool.check_signers([])


def test_owner_key_is_accepted(tool):
    tool.check_signers(["ab" * 32])


def test_reads_signer_of_built_apk_in_a_path_with_spaces(tool):
    # The repo lives under ".../Yggdrass OS/..."; a shell wrapper split that path.
    apk = tool.ROOT / "android/app/build/outputs/apk/release/app-release.apk"
    tools = tool.ROOT / ".cache/android-tools"
    if not apk.is_file() or not list(tools.glob("sdk/build-tools/*/lib/apksigner.jar")):
        pytest.skip("No local Android build to inspect.")
    signers = tool.apk_signers(apk)
    assert signers and all(len(s) == 64 for s in signers)
