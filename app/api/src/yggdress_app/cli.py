"""Application-only commands. Never imports the memory package or reads its config."""

import argparse
import getpass
import os
from pathlib import Path

from .database import Database
from .security import password_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["password", "migrate", "serve"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--port", type=int, default=8100)
    args = parser.parse_args()
    if args.command == "password":
        value = getpass.getpass("Personal password (12+ characters): ")
        if value != getpass.getpass("Confirm password: "):
            parser.error("Passwords did not match.")
        hashed = password_hash(value)
        if not args.output or not args.output.resolve().is_relative_to(
            Path.cwd().resolve() / "runtime"
        ):
            parser.error("Choose an ignored output under app/api/runtime/.")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if args.output.exists():
            parser.error("Output already exists; choose a new file for password rotation.")
        descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            # Single quotes preserve scrypt's dollar separators in dotenv loaders.
            file.write("YGGDRESS_PASSWORD_HASH='" + hashed + "'\n")
        print(
            "Password hash saved privately. Configure it in the backend environment; never commit it."
        )
    elif args.command == "migrate":
        url = os.environ.get("YGGDRESS_MIGRATION_DATABASE_URL")
        if not url:
            parser.error("Set a separate application migration connection privately.")
        Database(url).migrate()
        print("Application migrations applied.")
    else:
        import uvicorn

        from .application import create_app

        uvicorn.run(create_app(), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
