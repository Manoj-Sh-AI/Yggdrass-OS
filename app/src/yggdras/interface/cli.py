"""The `yggdras` command.

    yggdras ask "<question>" [--brain REPO] [--flat ROOT] [--model M] [--skills DIR]
    yggdras tell "<change request>" [--brain REPO] [--flat ROOT]
    yggdras ingest <file.md> [--instruction "<what to do>"] [--brain REPO] [--flat ROOT]
    yggdras confirm <preview id> | cancel <preview id> | undo <commit> | pending
    yggdras restore <archived note: slug or name>
    yggdras mcp [--brain REPO] [--flat ROOT] [--model M] [--skills DIR]

ask prints Lia's answer, its citations, the cost and the latency. tell passes a change
request to Lia (D36): adding is written at once, changing or removing becomes a preview that
confirm writes. Typing confirm, cancel or undo in a terminal is Manoj's own act, so no card
token is needed here. Every request leaves a trace in local-data/traces/.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from yggdras import config


def _brain_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--brain", type=Path, help="brain repo (default: YGGDRAS_BRAIN)")
    p.add_argument("--flat", type=Path, help="a flat demo brain root instead of a library")


def _root(args) -> tuple[Path | None, bool]:
    if args.flat:
        return args.flat, True
    brain = args.brain or config.brain_repo()
    return (brain / "library" if brain else None), False


def _writer(args):
    from yggdras.interface import writing
    from yggdras.processing.lia.library import Library
    from yggdras.processing.lia.models import AnthropicClient

    root, flat = _root(args)
    if root is None:
        print("no brain: pass --brain or set YGGDRAS_BRAIN", file=sys.stderr)
        return None
    side = writing.write_side(Library(root, flat=flat), root, flat, AnthropicClient)
    if side is None:
        print("writing is off: this brain is not in a git repository", file=sys.stderr)
    return side


def _print_card(card) -> int:
    print(card.text)
    if card.cost_usd:
        print(f"\n${card.cost_usd:.4f}")
    return 0 if card.kind in ("summary", "preview", "message", "question") else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yggdras")
    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="ask Lia a question")
    ask.add_argument("question")
    _brain_args(ask)
    ask.add_argument("--model", default=config.lia_model())
    ask.add_argument("--skills", type=Path, help="skills folder (default: <brain>/skills/lia)")
    tell = sub.add_parser("tell", help="ask Lia to change your notes")
    tell.add_argument("request")
    _brain_args(tell)
    ingest = sub.add_parser("ingest", help="give Lia a markdown file to file (up to 5 MB)")
    ingest.add_argument("path")
    ingest.add_argument("--instruction", default="")
    _brain_args(ingest)
    for name, what in (("confirm", "write a preview"), ("cancel", "drop a preview")):
        p = sub.add_parser(name, help=what)
        p.add_argument("id")
        _brain_args(p)
    restore = sub.add_parser("restore", help="bring back an archived note (slug or name)")
    restore.add_argument("note")
    _brain_args(restore)
    undo = sub.add_parser("undo", help="undo one of Lia's changes")
    undo.add_argument("sha")
    _brain_args(undo)
    sub.add_parser("pending", help="list previews waiting for your confirm")
    sub.add_parser("mcp", help="run Lia as an MCP server (stdio)", add_help=False)
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["mcp"]:
        from yggdras.interface.mcp_server import main as mcp_main

        return mcp_main(argv[1:])
    args = parser.parse_args(argv)
    config.load_env_file()
    if args.command == "pending":
        return _pending()
    if args.command == "ingest":
        return _ingest(args)
    if args.command in ("tell", "confirm", "cancel", "undo", "restore"):
        side = _writer(args)
        if side is None:
            return 2
        if args.command == "tell":
            from yggdras.interface import writing

            card = side.tell(args.request, app="cli")
            writing.trace(card)
            return _print_card(card)
        if args.command == "confirm":
            return _print_card(side.confirm(args.id, None, "cli"))
        if args.command == "cancel":
            return _print_card(side.cancel(args.id, None))
        if args.command == "restore":
            return _print_card(side.restore(args.note, "cli"))
        return _print_card(side.undo(args.sha, None, "cli"))
    return _ask(args)


def _ingest(args) -> int:
    from yggdras.interface import writing
    from yggdras.processing.lia.library import Library
    from yggdras.processing.lia.models import AnthropicClient

    try:
        name, data = writing.read_upload(path=args.path)
    except writing.UploadError as exc:
        print(exc, file=sys.stderr)
        return 2
    root, flat = _root(args)
    if root is None:
        print("no brain: pass --brain or set YGGDRAS_BRAIN", file=sys.stderr)
        return 2
    side = writing.write_side(Library(root, flat=flat), root, flat, AnthropicClient, kind="ingest")
    if side is None:
        print("writing is off: this brain is not in a git repository", file=sys.stderr)
        return 2
    card = side.ingest(name, data, args.instruction, "cli")
    writing.trace(card)
    return _print_card(card)


def _pending() -> int:
    from yggdras.interface import writing

    items = writing.store().open_items()
    for p in items:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(p.created))
        print(f"{p.id}  {when}  {p.request[:70]}")
    if not items:
        print("Nothing is waiting for your confirm.")
    return 0


def _ask(args) -> int:
    from yggdras.processing.lia.lia import LiaConfig, default_lia, write_trace
    from yggdras.processing.lia.library import Library
    from yggdras.processing.lia.models import AnthropicClient

    brain = args.brain or config.brain_repo()
    if args.flat:
        library = Library(args.flat, flat=True)
    elif brain:
        library = Library(brain / "library")
    else:
        print("no brain: pass --brain or set YGGDRAS_BRAIN", file=sys.stderr)
        return 2
    skills_dir = args.skills or (brain / "skills" / "lia" if brain else None)
    if not skills_dir:
        print("no skills folder: pass --skills", file=sys.stderr)
        return 2
    lia = default_lia(
        library,
        skills_dir,
        AnthropicClient,
        LiaConfig(model=args.model, owner_names=config.owner_names()),
    )
    result = lia.ask(args.question, qid=f"ask-{int(time.time())}")
    print(result["answer"])
    print()
    for c in result["citations"]:
        print(f"- [[{c['slug']}]] {c.get('shown', '')[:90]}")
    print(
        f"\n${result['cost_usd']:.4f} · {result['latency_ms'] / 1000:.1f} s · "
        f"notes opened: {', '.join(result['opened']) or 'none'}"
    )
    write_trace(result, config.local_data() / "traces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
