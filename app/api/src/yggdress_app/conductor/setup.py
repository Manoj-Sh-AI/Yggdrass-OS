"""Builds the conductor from the environment (one place, like the rest of config)."""

from __future__ import annotations

import logging
import os

import psycopg

from .catalog import build_toolbox
from .history import ChatHistory
from .log import RunLog
from .models import FakeModels, ModelError
from .orchestrator import Conductor
from .policy import Policy, PolicyStore

LOG = logging.getLogger(__name__)


class NoModels:
    """No model key configured: every run fails with a plain explanation."""

    def stream(self, **_):
        raise ModelError("No model key is configured for the chat (ANTHROPIC_API_KEY).")
        yield  # pragma: no cover

    def structured(self, **_):
        raise ModelError("No model key is configured for the chat (ANTHROPIC_API_KEY).")


def build_models():
    if os.environ.get("YGGDRAS_FAKE_MODEL") == "1":  # local previews: no spend
        return FakeModels()
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return NoModels()
    from .models import AnthropicModels

    return AnthropicModels(key)


def build_conductor(database, notes=None) -> Conductor:
    models = build_models()
    store = PolicyStore(database)
    conductor = Conductor(
        RunLog(database),
        models,
        ChatHistory(database),
        toolbox=build_toolbox(database, notes),
        policy=Policy(models, store.get),
        policy_store=store,
    )
    try:
        stopped = conductor.log.interrupt_stale()
        if stopped:
            LOG.info("Marked %d stale runs interrupted.", len(stopped))
    except psycopg.Error:
        LOG.warning("Could not check for stale runs at start-up.", exc_info=True)
    return conductor
