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
