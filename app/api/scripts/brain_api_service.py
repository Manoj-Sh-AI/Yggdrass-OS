"""Run the existing Brain HTTP service; no replacement Brain or application writes.

Run with the Brain project's Python environment. Credentials stay in its private
environment file. This launcher does not load the Markdown Brain or start Lia agents.
"""

import argparse
import sys
from pathlib import Path
from threading import Event


def main():
    parser = argparse.ArgumentParser(description="Existing PostgreSQL Brain API service")
    parser.add_argument("--brain-project", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()
    source = args.brain_project.resolve() / "app" / "src"
    if not (source / "yggdras" / "interface" / "mcp_server.py").is_file():
        parser.error("The selected project does not contain the existing Brain API.")
    if not 1 <= args.port <= 65535:
        parser.error("Use a valid local service port.")
    sys.path.insert(0, str(source))
    from yggdras import config
    from yggdras.interface import note_server
    from yggdras.interface.mcp_server import start_api
    from yggdras.processing.lia.library import RowLibrary

    config.load_env_file(args.brain_project.resolve() / ".env")
    if config.brain_source() != "rows":
        parser.error("Database mode is not enabled; no service was started.")
    api = start_api()
    if api is None:
        parser.error("The private Brain API credentials are not configured.")
    # Startup verifies the existing database-backed reader, without changing data.
    api.read("search", "")
    server = note_server.start(
        lambda: RowLibrary(api.writes.store.snapshot()),
        args.port,
        config.brain_view(),
        api,
    )
    if server is None:
        parser.error("The Brain port is already occupied; its service was not replaced.")
    print(f"Brain API ready on loopback port {args.port}; source=rows.", flush=True)
    try:
        Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - startup errors must not expose private DSNs
        # A database exception can include a connection string: print only the error's
        # type and where it happened, never its message.
        import traceback

        frames = traceback.extract_tb(exc.__traceback__)[-3:]
        where = " <- ".join(
            f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in reversed(frames)
        )
        print(
            f"Brain API startup failed: {type(exc).__name__} at {where}",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)
