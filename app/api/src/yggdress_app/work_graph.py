"""Bounded, typed operational graph; never synthesizes Brain relationships."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg import sql

TABLES = {
    "note": "note_refs",
    "task": "tasks",
    "event": "calendar_events",
    "goal": "planning_goals",
    "project": "projects",
    "routine": "routine_templates",
    "block": "execution_blocks",
    "session": "execution_sessions",
    "background_run": "background_runs",
    "date_item": "calendar_date_items",
    "availability": "availability_windows",
}


def nodes(db, identities):
    result = []
    for kind, table in TABLES.items():
        ids = [
            UUID(value.partition(":")[2]) for value in identities if value.startswith(kind + ":")
        ]
        if not ids:
            continue
        rows = db.execute(
            sql.SQL("SELECT * FROM app.{} WHERE id=ANY(%s)").format(sql.Identifier(table)), (ids,)
        ).fetchall()
        lifecycles = {}
        if kind == "note":
            lifecycles = {
                row["note_ref_id"]: row["lifecycle"]
                for row in db.execute(
                    "SELECT note_ref_id,lifecycle FROM app.workflow_sources WHERE note_ref_id=ANY(%s)",
                    (ids,),
                ).fetchall()
            }
        for row in rows:
            title = (
                row.get("title")
                or row.get("observed_title")
                or row.get("label")
                or ("Focus session" if kind == "session" else "Execution block")
            )
            item = {
                "id": kind + ":" + str(row["id"]),
                "kind": kind,
                "title": title,
                "status": row.get("state")
                or ("removed" if row.get("cancelled") else "complete" if row.get("done") else ""),
                "version": row.get("version"),
            }
            if kind == "note":
                item["slug"] = row["external_id"]
                item["status"] = lifecycles.get(row["id"], "")
            if row.get("starts_at"):
                item["starts_at"] = row["starts_at"]
            if row.get("starts_on"):
                item["starts_on"] = row["starts_on"]
            result.append(item)
    return result


def work_graph_router(database, session):
    router = APIRouter(prefix="/v1/application/work-graph", dependencies=[Depends(session)])

    @router.get("/roots")
    def roots(
        query: str = Query(default="", max_length=180), limit: int = Query(default=40, ge=1, le=100)
    ):
        with database.connect() as db:
            rows = db.execute(
                "SELECT 'note:'||id AS id,observed_title AS title,'note' AS kind FROM app.note_refs WHERE position(lower(%s) in lower(observed_title))>0 UNION ALL SELECT 'task:'||id,title,'task' FROM app.tasks WHERE position(lower(%s) in lower(title))>0 UNION ALL SELECT 'event:'||id,title,'event' FROM app.calendar_events WHERE NOT cancelled AND position(lower(%s) in lower(title))>0 ORDER BY title,id LIMIT %s",
                (query, query, query, limit + 1),
            ).fetchall()
            return {"roots": rows[:limit], "truncated": len(rows) > limit}

    @router.get("")
    def graph(
        root: str = Query(pattern=r"^[a-z_]+:[a-fA-F0-9-]{36}$"),
        depth: int = Query(default=1, ge=1, le=2),
        limit: int = Query(default=80, ge=2, le=150),
        include_completed: bool = False,
    ):
        kind, _, raw = root.partition(":")
        if kind not in TABLES:
            raise HTTPException(422, "Unknown application graph kind.")
        try:
            root = kind + ":" + str(UUID(raw))
        except ValueError:
            raise HTTPException(422, "Invalid graph identity.") from None
        with database.connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            if not nodes(db, [root]):
                raise HTTPException(404, "Graph item not found.")
            seen = {root}
            frontier = {root}
            edges = {}
            truncated = False
            for _ in range(depth):
                found = db.execute(
                    "SELECT DISTINCT source,target,relation FROM app.operational_edges WHERE source=ANY(%s) OR target=ANY(%s) ORDER BY source,target,relation LIMIT %s",
                    (sorted(frontier), sorted(frontier), limit * 4 + 1),
                ).fetchall()
                truncated = truncated or len(found) > limit * 4
                next_frontier = set()
                for edge in found[: limit * 4]:
                    new = {edge["source"], edge["target"]} - seen
                    if len(seen) + len(new) > limit:
                        truncated = True
                        continue
                    seen.update(new)
                    next_frontier.update(new)
                    edges[(edge["source"], edge["target"], edge["relation"])] = edge
                    if len(edges) >= limit * 4:
                        truncated = True
                        break
                frontier = next_frontier
                if not frontier:
                    break
            values = nodes(db, sorted(seen))
            if not include_completed:
                values = [
                    v
                    for v in values
                    if v["id"] == root
                    or v["status"]
                    not in (
                        "done",
                        "complete",
                        "completed",
                        "skipped",
                        "removed",
                        "succeeded",
                        "cancelled",
                    )
                ]
            retained = {v["id"] for v in values}
            return {
                "nodes": values,
                "edges": [
                    e for e in edges.values() if e["source"] in retained and e["target"] in retained
                ],
                "root": root,
                "truncated": truncated,
                "limit": limit,
            }

    return router
