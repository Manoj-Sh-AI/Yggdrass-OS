"""Adapter to Claude-owned Lia. No Brain writes, traces, temp notes or engine edits.

Run with the existing Brain environment's Python. JSON travels over stdin/stdout;
credentials are loaded privately by the existing config module, never arguments.
"""

import argparse
import contextlib
import io
import json
import sys
from dataclasses import replace
from pathlib import Path

STAGE = "configuration"


def main():
    global STAGE
    parser = argparse.ArgumentParser()
    parser.add_argument("--brain-project", type=Path, required=True)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--skills", type=Path)
    args = parser.parse_args()
    source = args.brain_project.resolve() / "app/src"
    sys.path.insert(0, str(source))
    from yggdras import config

    config.load_env_file(args.brain_project / ".env")
    STAGE = "model_metadata"
    from yggdras.processing.lia.models import PRICES

    brain = config.brain_repo()
    skills = args.skills or (brain / "skills/lia" if brain else None)
    STAGE = "row_backed_skill_configuration"
    if config.brain_source() != "rows" or not skills or not skills.is_dir():
        raise ValueError("The existing row-backed Lia configuration is unavailable.")
    if args.inspect:
        from yggdras.interface.writing import row_store
        from yggdras.processing.lia.library import RowLibrary
        from yggdras.processing.lia.skills import load_library

        load_library(skills)
        library = RowLibrary(row_store().snapshot())
        library.maps()
        library.manual()
        print(
            json.dumps(
                {"ready": True, "default_model": config.lia_model(), "models": sorted(PRICES)}
            )
        )
        return
    raw = sys.stdin.buffer.read(240001)
    if len(raw) > 240000:
        raise ValueError("The Lia context exceeds its input limit.")
    request = json.loads(raw)
    if (
        set(request) - {"question", "context", "model"}
        or not 0 < len(request.get("question", "")) <= 12000
        or len(request.get("context", "")) > 30000
    ):
        raise ValueError("Invalid Lia request.")
    from yggdras.interface.mcp_server import LiaService
    from yggdras.interface.writing import row_store
    from yggdras.processing.lia.models import AnthropicClient, Budget

    budget = Budget(stop_at=1.0)
    # Preserve Lia's own retrieval, effort selection, support checks and model client.
    service = LiaService(
        (brain or args.brain_project) / "library",
        skills,
        lambda model: AnthropicClient(model, budget=budget),
        model=config.lia_model(),
        rows=row_store(),
        cite_url="/notes?note={slug}#cite={block}",
    )
    selected = request.get("model", "default")
    if selected != "default":
        if selected not in PRICES:
            raise ValueError("This model is not supported by the existing Lia service.")
        service.config = replace(service.config, model=selected, complex_model=selected)
    # Call her existing read workflow directly; the MCP wrapper adds prompt markup
    # and trace file writes which are unnecessary at this application boundary.
    result = service.lia().ask(request["question"], context=request.get("context", ""))
    print(json.dumps({"answer": result["answer"], "cost_usd": result.get("cost_usd", 0)}))


if __name__ == "__main__":
    try:
        # Libraries must not mix their diagnostics with the machine response.
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()):
            main()
        sys.stdout.write(output.getvalue())
    except Exception as error:  # noqa: BLE001 -- private engine errors can contain credentials
        print(
            json.dumps(
                {
                    "error": "The existing Lia service could not complete this request.",
                    "stage": STAGE,
                    "category": type(error).__name__,
                }
            )
        )
        sys.exit(1)
