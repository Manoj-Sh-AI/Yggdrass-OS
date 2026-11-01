"""Settings from environment variables, read in one place (see .env.example)."""

import os


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def hard_description_rules() -> bool:
    """A23's description rules block the build when on; when off they are lint warnings.

    Off until the description rewrite commit lands (planning/maps-design.md, section 12).
    """
    return _flag("YGGDRAS_HARD_DESCRIPTION_RULES")
