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


def write_side(library, root: Path, flat: bool, client_factory, note_url: str | None = None):
    """Lia's writing side over the brain at *root*, or None if it isn't in a git repo."""
    from yggdras.data.brain.write_path import WritePath
    from yggdras.processing.lia.write import WriteSide

    repo = repo_of(root, flat)
    if repo is None:
        return None
    wp = WritePath(repo, root, config.local_data() / "locks", flat=flat)
    return WriteSide(client_factory(config.lia_model()), library, wp, store(), note_url)


def trace(card, folder: Path | None = None) -> Path:
    """One JSON trace per request, in local-data/traces/ (git-ignored)."""
    import json
    import time

    folder = folder or config.local_data() / "traces"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"tell-{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 10**6}.json"
    path.write_text(json.dumps(card.trace, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
