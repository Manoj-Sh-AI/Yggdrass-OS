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


def notes_port() -> int:
    """The note server's port for footnote links (YGGDRAS_NOTES_PORT), on 127.0.0.1 only."""
    return int(os.environ.get("YGGDRAS_NOTES_PORT", "8765"))


def owner_names() -> tuple[str, ...]:
    """The brain owner's names (YGGDRAS_OWNER_NAMES, comma-separated), for Lia's voice check:
    her own sentences say "you", never these. Kept out of the code (D23)."""
    raw = os.environ.get("YGGDRAS_OWNER_NAMES", "")
    return tuple(n.strip() for n in raw.split(",") if n.strip())


def local_data():
    """Personal outputs (traces, real-brain results): git-ignored, never committed."""
    from pathlib import Path

    return Path(
        os.environ.get("YGGDRAS_LOCAL_DATA", Path(__file__).resolve().parents[3] / "local-data")
    )


def load_env_file(path=None) -> None:
    """Read KEY=value lines from a .env file into the environment (existing values win).

    Default: YGGDRAS_ENV_FILE, else the code repo's .env. Values are never printed or logged.
    """
    from pathlib import Path

    path = Path(
        path or os.environ.get("YGGDRAS_ENV_FILE") or Path(__file__).resolve().parents[3] / ".env"
    )
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        key = key.strip()
        if sep and key and not key.startswith("#") and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def brain_source() -> str:
    """Where Lia reads and writes (D44): "markdown" (the files, today's default) or "rows"
    (the local PostgreSQL in BRAIN_DATABASE_URL). Switched only after the parity gate."""
    value = os.environ.get("YGGDRAS_BRAIN_SOURCE", "markdown").strip().lower()
    if value not in ("markdown", "rows"):
        raise ValueError("YGGDRAS_BRAIN_SOURCE must be 'markdown' or 'rows'")
    return value


def brain_view():
    """The graph viewer built from the rows (local-data/brain-view), served at /graph."""
    return local_data() / "brain-view"


def brain_raw():
    """Raw uploads under the rows path stay files (D44): local-data/brain-raw/raw/<name>."""
    return local_data() / "brain-raw"
