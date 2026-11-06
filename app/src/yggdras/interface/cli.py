"""The `yggdras` command.

    yggdras ask "<question>" [--brain REPO] [--flat ROOT] [--model M] [--skills DIR]
    yggdras mcp [--brain REPO] [--flat ROOT] [--model M] [--skills DIR]

Prints Lia's answer, its citations, the cost and the latency, and writes a trace to
local-data/traces/. Reads the brain only.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from yggdras import config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yggdras")
    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="ask Lia a question")
    ask.add_argument("question")
    ask.add_argument("--brain", type=Path, help="brain repo (default: YGGDRAS_BRAIN)")
    ask.add_argument("--flat", type=Path, help="a flat demo brain root instead of a library")
    ask.add_argument("--model", default=config.lia_model())
    ask.add_argument("--skills", type=Path, help="skills folder (default: <brain>/skills/lia)")
    sub.add_parser("mcp", help="run Lia as a read-only MCP server (stdio)", add_help=False)
    if argv is None:
        argv = sys.argv[1:]
    if argv[:1] == ["mcp"]:
        from yggdras.interface.mcp_server import main as mcp_main

        return mcp_main(argv[1:])
    args = parser.parse_args(argv)

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
    config.load_env_file()
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
        mark = "ok" if c["ok"] else f"FAILED ({c['reason']})"
        print(f"- [[{c['slug']}]] {c['quote'][:90]} … {mark}")
    print(
        f"\n${result['cost_usd']:.4f} · {result['latency_ms'] / 1000:.1f} s · "
        f"notes opened: {', '.join(result['opened']) or 'none'}"
    )
    write_trace(result, config.local_data() / "traces")
    return 0


if __name__ == "__main__":
    sys.exit(main())
