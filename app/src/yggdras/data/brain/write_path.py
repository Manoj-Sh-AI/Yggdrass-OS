"""The one write path (D22 as amended, D36): every change to the brain goes through it.

    check → lint → lock → clean? → write → log → rebuild the maps → one commit → result

- the checker and lint (checker.py); a hard problem refuses the change, nothing written;
- one write at a time (a lock file in local-data);
- refused when the folders Lia writes (the library and the archive) hold uncommitted changes
  made by hand: they are listed, never stashed or overwritten (generated maps excepted);
- one git commit per request, with a clear message; Lia never pushes;
- the maps are rebuilt and committed with the change, so the brain is never left dirty;
- after the commit (and after every Undo) the viewer's page is re-rendered: the brain's own
  generated/graph.html (git-ignored) and the note server's copy, so a new note shows up on
  the next page refresh. Best effort: a viewer failure never undoes a write;
- on any error mid-write, the files are put back as they were.

Undo is a `git revert` of that commit, as a new commit. If a later commit touched the same
notes, Undo stops and lists them instead of forcing.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from yggdras.data.brain import repo as git_repo
from yggdras.data.brain.checker import Checker, Issue
from yggdras.data.brain.ops import Change
from yggdras.data.graph import structural as st

LOG = "00-manual/log.md"


@dataclass
class Outcome:
    """written: committed (sha); refused: the checker said no; blocked: not written for
    another reason (hand edits, a later commit, the lock)."""

    status: str
    message: str = ""
    sha: str = ""
    issues: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    dirty: list[str] = field(default_factory=list)
    later: list[str] = field(default_factory=list)
    viewer_error: str = ""  # the viewer couldn't be re-rendered (the write itself stands)


class WritePath:
    def __init__(
        self,
        repo: Path,
        root: Path,
        lock_dir: Path,
        flat: bool = False,
        today: str | None = None,
        viewer_dirs: tuple[Path, ...] = (),
    ):
        self.repo, self.root, self.flat = repo.resolve(), root.resolve(), flat
        # Where the graph viewer's page lives: the library's own generated/ folder, plus any
        # copy a note server serves (local-data/viewer).
        self.viewer_dirs = tuple(viewer_dirs) + (() if flat else (st.generated_dir(self.repo),))
        self.lock_dir = lock_dir
        self.today = today or dt.date.today().isoformat()
        self.root_rel = self.root.relative_to(self.repo).as_posix()
        self.checker = Checker(self.root, flat)

    # ---------------------------------------------------------------- paths

    def repo_path(self, lib_rel: str) -> str:
        return (PurePosixPath(self.root_rel) / lib_rel).as_posix()

    def archive_path(self, lib_rel: str) -> str:
        return (PurePosixPath("archive") / self.root_rel / lib_rel).as_posix()

    @property
    def generated(self) -> str:
        return (PurePosixPath(self.root_rel) / st.GENERATED).as_posix()

    def _dirty(self) -> list[str]:
        return git_repo.dirty(self.repo, [self.root_rel, "archive"], [self.generated])

    # ---------------------------------------------------------------- check and apply

    def check(self, change: Change):
        return self.checker.check({**change.notes, **{p: None for p in change.archive}})

    def apply(self, change: Change, approved_by: str, request: str = "") -> Outcome:
        verdict = self.check(change)
        if not verdict.ok:
            return Outcome(
                "refused",
                "the checker refused the change",
                issues=verdict.hard,
                warnings=verdict.warnings,
            )
        try:
            with git_repo.write_lock(self.lock_dir):
                dirty = self._dirty()
                if dirty:
                    return Outcome(
                        "blocked",
                        "the brain has uncommitted changes made by hand; commit or undo them first",
                        dirty=dirty,
                    )
                sha = self._write(change, approved_by, request)
        except git_repo.Busy as exc:
            return Outcome("blocked", str(exc))
        out = Outcome("written", f"committed {sha[:7]}", sha=sha, warnings=verdict.warnings)
        out.viewer_error = self.render_viewers()
        return out

    def render_viewers(self) -> str:
        """Re-render the graph viewer in every viewer folder from the notes as they are now.
        Returns "" or what went wrong; never raises (the viewer is a nicety)."""
        if not self.viewer_dirs:
            return ""
        try:
            from yggdras.data.graph import viewer

            graph = st.build_map(self.root, None if self.flat else st.mapped_shelves())
            for folder in dict.fromkeys(self.viewer_dirs):
                viewer.render(graph, self.root, folder)
        except Exception as exc:  # noqa: BLE001
            return f"{type(exc).__name__}: {exc}"
        return ""

    def _write(self, change: Change, approved_by: str, request: str) -> str:
        touched: list[str] = []
        # Every file this write may touch, byte for byte, so a failure puts each one back
        # exactly (None: it didn't exist). Independent of git's line-ending settings.
        snap: dict[Path, bytes | None] = {}

        def keep(path: Path) -> None:
            if path not in snap:
                snap[path] = path.read_bytes() if path.is_file() else None

        generated = self.repo / self.generated
        for path in [*generated.glob("*"), self.root / LOG]:
            keep(path)
        try:
            for lib_rel, text in change.archive.items():
                target = self.repo / self.archive_path(lib_rel)
                keep(target)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8", newline="\n")
                touched.append(self.archive_path(lib_rel))
            for lib_rel, text in change.notes.items():
                path = self.root / lib_rel
                keep(path)
                touched.append(self.repo_path(lib_rel))
                if text is None:
                    path.unlink(missing_ok=True)
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8", newline="\n")
            touched += self._log([f"{e} (asked by Manoj via {approved_by})" for e in change.log])
            touched += self._rebuild()
            return git_repo.commit(self.repo, touched, self._message(change, approved_by, request))
        except Exception:
            self._restore(snap, generated)
            raise

    @staticmethod
    def _restore(snap: dict[Path, bytes | None], generated: Path) -> None:
        """Put every file back as it was: a failed write leaves nothing behind."""
        for path in generated.glob("*"):
            if path not in snap:
                path.unlink(missing_ok=True)  # a map file the failed rebuild created
        for path, data in snap.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)

    def _log(self, entries: list[str]) -> list[str]:
        """One line per operation in the library's log (a flat brain has none)."""
        log = self.root / LOG
        if self.flat or not log.is_file() or not entries:
            return []
        text = log.read_text(encoding="utf-8")
        lines = "".join(f"- {self.today} {e}\n" for e in entries)
        log.write_text(
            text + ("" if text.endswith("\n") else "\n") + lines, encoding="utf-8", newline="\n"
        )
        return [self.repo_path(LOG)]

    def _rebuild(self) -> list[str]:
        """Rebuild the library's maps; return the tracked generated files (to stage)."""
        if self.flat:
            return []
        from yggdras.data.maps.build import run as write_maps

        graph = st.build_map(self.root, st.mapped_shelves())
        st._write(st.generated_dir(self.repo) / st.MAP_FILE, st.render(graph))
        write_maps(self.repo, graph=graph)
        tracked = git_repo.git(self.repo, "ls-files", "--", self.generated)
        return [p for p in tracked.splitlines() if p.strip()]  # staged whether changed or not

    def _message(self, change: Change, approved_by: str, request: str) -> str:
        body = "\n".join(f"- {line}" for line in change.lines)
        ask = " ".join(request.split())
        return (
            f"lia: {change.title}\n\n{body}\n\n"
            + (f"Request: {ask[:300]}\n" if ask else "")
            + f"Approved-by: Manoj via {approved_by}\n"
        )

    # ---------------------------------------------------------------- undo

    def undo(self, sha: str, approved_by: str) -> Outcome:
        try:
            full = git_repo.git(self.repo, "rev-parse", "--verify", f"{sha}^{{commit}}").strip()
        except git_repo.RepoError:
            return Outcome("blocked", f"no commit {sha}")
        title = git_repo.subject(self.repo, full)
        if not title.startswith("lia: ") or title.startswith("lia: undo "):
            return Outcome("blocked", "only Lia's own changes can be undone this way")
        try:
            with git_repo.write_lock(self.lock_dir):
                dirty = self._dirty()
                if dirty:
                    return Outcome(
                        "blocked", "the brain has uncommitted changes made by hand", dirty=dirty
                    )
                notes = [
                    p
                    for p in git_repo.changed_files(self.repo, full)
                    if not p.startswith(self.generated) and p != self.repo_path(LOG)
                ]
                later = git_repo.later_commits(self.repo, full, notes)
                if later:
                    return Outcome(
                        "blocked",
                        "later changes touched the same notes; undo those first, or edit by hand",
                        later=later,
                    )
                return self._revert(full, title, approved_by)
        except git_repo.Busy as exc:
            return Outcome("blocked", str(exc))

    def _revert(self, full: str, title: str, approved_by: str) -> Outcome:
        log = self.repo_path(LOG)
        try:
            git_repo.git(self.repo, "revert", "--no-commit", full)
        except git_repo.RepoError as exc:
            git_repo.git(self.repo, "revert", "--abort", check=False)
            return Outcome("blocked", f"the change can't be reverted cleanly: {exc}")
        try:
            # The log stays append-only: keep the original line, add an "undone" line.
            if (self.repo / log).is_file() and not self.flat:
                git_repo.git(self.repo, "checkout", "HEAD", "--", log)
                what = title.removeprefix("lia: ")
                self._log([f"undone {what} ({full[:7]}, asked by Manoj via {approved_by})"])
            # The revert staged its own files; add only the log and the tracked maps.
            extra = [log] if (self.repo / log).is_file() and not self.flat else []
            extra += self._rebuild()
            if extra:
                git_repo.git(self.repo, "add", "--", *extra)
            git_repo.git(
                self.repo,
                "commit",
                "-q",
                "-m",
                f"lia: undo {full[:7]} ({title.removeprefix('lia: ')})\n\n"
                f"Approved-by: Manoj via {approved_by}\n",
            )
        except Exception:
            # Back to before the revert; hand edits elsewhere in the repo are left alone.
            git_repo.git(self.repo, "revert", "--abort", check=False)
            raise
        out = Outcome("written", f"undid {full[:7]}", sha=git_repo.head(self.repo))
        out.viewer_error = self.render_viewers()
        return out
