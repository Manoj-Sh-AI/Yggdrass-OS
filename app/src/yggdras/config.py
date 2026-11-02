"""Settings from environment variables, read in one place (see .env.example)."""

import os


def hard_description_rules() -> bool:
    """A23's description rules block the build; on by default since the rewrite commit.

    Set YGGDRAS_HARD_DESCRIPTION_RULES=0 to turn them back into lint warnings.
    """
    return os.environ.get("YGGDRAS_HARD_DESCRIPTION_RULES", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def brain_repo():
    """The brain repo Lia reads (YGGDRAS_BRAIN), or None."""
    from pathlib import Path

    value = os.environ.get("YGGDRAS_BRAIN", "").strip()
    return Path(value) if value else None


def lia_model() -> str:
    """Lia's model (D27): a setting, chosen by eval results, accuracy first."""
    return os.environ.get("YGGDRAS_LIA_MODEL", "claude-haiku-5-5").strip()


def local_data():
    """Personal outputs (traces, real-brain results): git-ignored, never committed."""
    from pathlib import Path

    return Path(
        os.environ.get("YGGDRAS_LOCAL_DATA", Path(__file__).resolve().parents[3] / "local-data")
    )
