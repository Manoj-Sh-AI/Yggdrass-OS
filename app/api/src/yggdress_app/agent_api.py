"""Owner-visible agent status and exact proposal decisions, not model credentials."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field

from .agent_tools import Proposal
from .planning_models import Model


class AgentDecision(Model):
    key: UUID
    id: UUID
    version: int = Field(ge=1, strict=True)
    decision: Literal["accept", "dismiss"]


def agent_router(store, session, enabled=False, issue=""):
    router = APIRouter(prefix="/v1/application/agents", dependencies=[Depends(session)])

    @router.get("/status")
    def status():
        with store.database.connect() as db:
            runs = db.execute(
                "SELECT id,agent_id,model_id,state,error,created_at,finished_at FROM app.agent_runs ORDER BY created_at DESC,id DESC LIMIT 20"
            ).fetchall()
        return {
            "enabled": enabled,
            "automatic_replay": False,
            "runs": runs,
            "connection_issue": issue,
        }

    @router.get("/reviews")
    def reviews(limit: int = Query(default=30, ge=1, le=100)):
        with store.database.connect() as db:
            rows = db.execute(
                "SELECT id,version,agent_id,payload,created_at FROM app.agent_proposals WHERE state='pending' ORDER BY created_at,id LIMIT %s",
                (limit + 1,),
            ).fetchall()
        for row in rows[:limit]:
            try:
                current = store.tools.inspect(Proposal.model_validate(row["payload"]))
                row["current"] = (
                    {
                        key: value
                        for key, value in (current or {}).items()
                        if key in row["payload"]["data"]
                        or key
                        in (
                            "id",
                            "title",
                            "version",
                            "objective",
                            "state",
                            "due_date",
                            "deadline_at",
                            "starts_at",
                            "ends_at",
                            "starts_on",
                            "ends_before",
                            "timezone",
                            "cancelled",
                        )
                    }
                    if current is not None
                    else None
                )
                row["blocked"] = ""
            except HTTPException as error:
                row["current"], row["blocked"] = None, error.detail
        return {"reviews": rows[:limit], "truncated": len(rows) > limit}

    @router.post("/reviews/resolve")
    def resolve(command: AgentDecision):
        return store.resolve(command)

    return router
