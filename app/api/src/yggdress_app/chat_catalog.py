"""Server-owned selection metadata; never credentials, tools, agents or models."""

import json
import os

from fastapi import HTTPException
from pydantic import Field

from .planning_models import Model


class Choice(Model):
    id: str = Field(pattern=r"^[a-zA-Z0-9_.:-]{1,100}$")
    name: str = Field(min_length=1, max_length=100)
    enabled: bool = False


class AgentChoice(Choice):
    models: list[str] = Field(default_factory=lambda: ["default"], min_length=1, max_length=100)


class Catalog(Model):
    agents: list[AgentChoice] = Field(min_length=1, max_length=50)
    models: list[Choice] = Field(min_length=1, max_length=100)


class Selection(Model):
    agent_id: str = Field(min_length=1, max_length=100)
    model_id: str = Field(min_length=1, max_length=100)


def load_catalog(value=None):
    value = (
        value
        or json.loads(os.environ.get("YGGDRESS_CHAT_CATALOG_JSON", "null"))
        or {
            "agents": [
                {"id": "yggdras", "name": "Yggdras", "enabled": True},
                {"id": "lia", "name": "Lia"},
            ],
            "models": [{"id": "default", "name": "Provider default", "enabled": True}],
        }
    )
    catalog = Catalog.model_validate(value)
    agent_ids = [v.id for v in catalog.agents]
    model_ids = [v.id for v in catalog.models]
    if (
        len(set(agent_ids)) != len(agent_ids)
        or len(set(model_ids)) != len(model_ids)
        or "yggdras" not in agent_ids
        or "default" not in model_ids
        or any(model not in model_ids for a in catalog.agents for model in a.models)
    ):
        raise ValueError("The chat metadata catalog has duplicate or missing identities.")
    return catalog


def validate_selection(catalog, agent_id, model_id, connected):
    agent = next((item for item in catalog.agents if item.id == agent_id), None)
    model = next((item for item in catalog.models if item.id == model_id), None)
    if not agent or not model or model_id not in agent.models:
        raise HTTPException(422, "Choose a listed agent and one of its supported models.")
    return bool(connected and agent.enabled and model.enabled)


def public_catalog(catalog, connected):
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "available": bool(connected and a.enabled),
                "models": a.models,
            }
            for a in catalog.agents
        ],
        "models": [
            {"id": m.id, "name": m.name, "available": bool(connected and m.enabled)}
            for m in catalog.models
        ],
    }
