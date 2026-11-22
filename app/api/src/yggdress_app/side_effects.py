"""Outward side effects (push notifications, email, calls) happen only in production or
on the laptop, never in a Railway preview or staging environment
(planning/agentic-engineering.md item 36)."""

import os


def side_effects_allowed() -> bool:
    environment = os.environ.get("RAILWAY_ENVIRONMENT_NAME", "").strip().lower()
    return environment in ("", "production")
