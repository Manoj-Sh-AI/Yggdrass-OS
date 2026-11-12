"""Building Lia's writing side for the connector and the CLI (one place, one set of rules)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from yggdras import config


def repo_of(root: Path, flat: bool = False) -> Path | None:
    """The brain's own git repo, or None. Only the folder right above `library/` (or, for a
    flat brain, the brain folder or the one above it) counts: a repo further up, such as a
    home folder kept in git, never receives Lia's commits."""
    out = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if out.returncode != 0 or not out.stdout.strip():
        return None
    top = Path(out.stdout.strip()).resolve()
    allowed = {root.resolve().parent} | ({root.resolve()} if flat else set())
    return top if top in allowed else None


def store():
    from yggdras.data.brain.pending import Store

    return Store(config.local_data() / "yggdras.db")


def write_side(library, root: Path, flat: bool, client_factory, note_url: str | None = None,
               kind: str = "write"):  # fmt: skip
    """Lia's writing side over the brain at *root* (kind "write" for requests, "ingest" for
    uploads), or None if the brain isn't in its own git repo."""
    from yggdras.data.brain.write_path import WritePath
    from yggdras.processing.lia.ingest import IngestSide
    from yggdras.processing.lia.write import WriteSide

    repo = repo_of(root, flat)
    if repo is None:
        return None
    # The note server's viewer copy (local-data/viewer) is re-rendered after every write, so
    # "show in graph" shows new notes on refresh. (A flat demo brain has no copy there.)
    viewers = () if flat else (config.local_data() / "viewer",)
    wp = WritePath(repo, root, config.local_data() / "locks", flat=flat, viewer_dirs=viewers)
    side = IngestSide if kind == "ingest" else WriteSide
    return side(client_factory(config.lia_model()), library, wp, store(), note_url)


def row_store():
    """The brain in rows (D44), on the local PostgreSQL in BRAIN_DATABASE_URL."""
    from yggdras.data.brain_db import db
    from yggdras.data.brain_db.store import RowStore

    return RowStore(db.connect, viewer_dirs=(config.brain_view(),), raw_root=config.brain_raw())


def row_write_side(library, rows, client_factory, note_url: str | None = None,
                   kind: str = "write"):  # fmt: skip
    """Lia's writing side on the rows: the same sides, the row store as their write path."""
    from yggdras.processing.lia.ingest import IngestSide
    from yggdras.processing.lia.write import WriteSide

    side = IngestSide if kind == "ingest" else WriteSide
    return side(client_factory(config.lia_model()), library, rows, store(), note_url)


# ---------------------------------------------------------------- uploads (D37)

CONTENT_CAP = 100_000  # bytes sent as text through the chat model (Claude Desktop)
PATH_CAP = 5 * 1024 * 1024  # bytes read from a file on this computer (Claude Code, CLI)


class UploadError(ValueError):
    """An upload Lia won't take: shown to Manoj as it is."""


def read_upload(filename: str = "", content: str = "", path: str = "") -> tuple[str, bytes]:
    """The upload's name and bytes, from a local *path* (≤ 5 MB) or its *content* (≤ 100 KB).
    Markdown only, UTF-8 text."""
    from yggdras.data.brain.chunk import is_markdown

    if path.strip():
        p = Path(path.strip().strip('"')).expanduser()
        if not p.is_file():
            raise UploadError(f"There is no file at {p}.")
        name = filename.strip() or p.name
        if not is_markdown(p.name):
            raise UploadError(f"{p.name} is not a markdown file; Lia files .md files for now.")
        if p.stat().st_size > PATH_CAP:
            raise UploadError(f"{p.name} is over 5 MB; Lia files files up to 5 MB.")
        data = p.read_bytes()
    elif content:
        name = filename.strip()
        if not name:
            raise UploadError("Give the file's name with its content.")
        data = content.encode("utf-8")
        if len(data) > CONTENT_CAP:
            raise UploadError(
                f"{name} is {len(data) // 1000} KB; sent as text, Lia takes up to 100 KB. Pass "
                "the file's path on this computer instead (up to 5 MB)."
            )
    else:
        raise UploadError("Pass the file's path, or its name and content.")
    if not is_markdown(name):
        raise UploadError(f"{name} is not a markdown file; Lia files .md files for now.")
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UploadError(f"{name} is not UTF-8 text.") from None
    return name, data


def trace(card, folder: Path | None = None) -> Path:
    """One JSON trace per request, in local-data/traces/ (git-ignored)."""
    import json
    import time

    folder = folder or config.local_data() / "traces"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"tell-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 10**6}.json"
    path.write_text(json.dumps(card.trace, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
