import hmac
import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from uuid import uuid4

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from .agent_api import agent_router
from .agent_store import AgentStore
from .background import background_routers
from .brain import MockBrain, UnavailableBrain
from .chat import MAX_FILE, chat_routers
from .config import Settings
from .connections import connections_router
from .database import Database
from .graph_proxy import existing_graph, graph_router
from .handoffs import handoff_routers
from .notes_proxy import NotesError, NotesProxy, notes_router
from .planning import LOCK, execute_task, history, planning_router
from .planning_models import ExecutionInput
from .security import token_hash, verify_password
from .temporal import temporal_router
from .work_graph import work_graph_router
from .workflow import workflow_routers

COOKIE = "yggdress_session"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=1024)


class RoutineCommand(StrictModel):
    type: Literal["start", "progress", "complete"]
    percent: int | None = Field(default=None, ge=0, le=100, strict=True)


class TaskCreate(StrictModel):
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=10000)
    area: str = Field(min_length=1, max_length=100)
    date: date


class TaskUpdate(StrictModel):
    done: bool = Field(strict=True)
    version: int | None = Field(default=None, ge=1, strict=True)


class NoteCreate(StrictModel):
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=1000)
    content: str = Field(default="", max_length=100000)
    shelfId: str
    tags: list[str] = Field(default_factory=list, max_length=50)


class NoteReplace(StrictModel):
    version: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=1000)
    content: str = Field(max_length=100000)
    tags: list[str] = Field(default_factory=list, max_length=50)


class Version(StrictModel):
    version: str = Field(min_length=1, max_length=200)


class DeleteConfirm(Version):
    token: str = Field(min_length=1, max_length=200)
    confirmed: bool = Field(strict=True)


def create_app(
    settings: Settings | None = None,
    brain=None,
    notes=None,
    graph=None,
    receiver_tokens=None,
    chat_catalog=None,
    agents_enabled=False,
    agents_ready=None,
    agent_issue="",
):
    settings = settings or Settings.environment()
    settings.validate()
    database = Database(settings.database_url)
    brain = brain or (MockBrain() if settings.brain_mode == "mock" else UnavailableBrain())
    api = FastAPI(title="Yggdress application API", docs_url=None, redoc_url=None, openapi_url=None)
    api.state.database, api.state.brain = database, brain
    notes = notes or NotesProxy()
    api.state.notes_proxy = notes
    store = AgentStore(database)
    api.state.agent_store = store
    fingerprint = token_hash(settings.password_hash)

    @api.middleware("http")
    async def limits_and_headers(request, call_next):
        length = request.headers.get("content-length", "0")
        limit = (
            MAX_FILE
            if request.url.path == "/v1/chat/attachments" and request.method == "POST"
            else 250000
        )
        if not length.isdigit() or int(length) > limit:
            return JSONResponse({"detail": "Request too large."}, status_code=413)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @api.exception_handler(psycopg.Error)
    async def database_error(_request, _error):
        if isinstance(_error, psycopg.IntegrityError):
            return JSONResponse(
                {"detail": "A related planning item changed or is invalid. Refresh and try again."},
                status_code=409,
            )
        return JSONResponse(
            {"detail": "Application database unavailable. Try again later."}, status_code=503
        )

    @api.exception_handler(RequestValidationError)
    async def validation_error(_request, error):
        return JSONResponse(
            {
                "detail": "Invalid request fields.",
                "fields": [list(e["loc"]) for e in error.errors()],
            },
            status_code=422,
        )

    @api.exception_handler(NotesError)
    async def notes_error(_request, error):
        return JSONResponse(
            {"detail": error.message, "code": error.code, **error.extra}, status_code=error.status
        )

    def origin(request: Request):
        if request.headers.get("origin") != settings.origin.rstrip("/"):
            raise HTTPException(403, "This request must come from your application origin.")

    def session(request: Request):
        token = request.cookies.get(COOKIE, "")
        if not token or len(token) > 200:
            raise HTTPException(401, "Sign in to continue.")
        with database.connect() as db:
            found = db.execute(
                "SELECT csrf FROM app.sessions WHERE token_hash=%s AND expires_at>now() AND password_fingerprint=%s",
                (token_hash(token), fingerprint),
            ).fetchone()
        if not found:
            raise HTTPException(401, "Your session expired. Sign in again.")
        if request.method not in ("GET", "HEAD"):
            origin(request)
            if not hmac.compare_digest(request.headers.get("x-yggdress-csrf", ""), found["csrf"]):
                raise HTTPException(403, "Reload the application before making this change.")
        return found

    authenticated = Depends(session)
    api.include_router(planning_router(database, session))
    api.include_router(notes_router(notes, session, observer=store if agents_enabled else None))
    api.include_router(
        agent_router(
            store, session, agents_enabled if agents_ready is None else agents_ready, agent_issue
        )
    )
    api.include_router(connections_router(database, notes, session))
    api.include_router(temporal_router(database, session))
    for router in (
        *workflow_routers(database, notes, session, receiver_tokens),
        *background_routers(database, session, receiver_tokens),
    ):
        api.include_router(router)
    api.include_router(work_graph_router(database, session))
    for router in handoff_routers(database, notes, receiver_tokens):
        api.include_router(router)
    for router in chat_routers(database, session, receiver_tokens, chat_catalog):
        api.include_router(router)
    api.include_router(graph_router(graph or existing_graph(notes), session))

    @api.get("/health")
    def health():
        return {"status": "ok", "service": "application"}

    @api.post("/v1/auth/login")
    def login(body: Login, request: Request, response: Response):
        origin(request)
        if request.headers.get("x-yggdress-login") != "1":
            raise HTTPException(403, "Use the application sign-in form.")
        now = datetime.now(UTC)
        with database.connect() as db:
            guard = db.execute("SELECT * FROM app.login_guard WHERE id=1 FOR UPDATE").fetchone()
            if guard["locked_until"] and guard["locked_until"] > now:
                raise HTTPException(429, "Too many sign-in attempts. Try again in 15 minutes.")
            failures = (
                guard["failures"] if now - guard["window_start"] < timedelta(minutes=15) else 0
            )
            correct = verify_password(body.password, settings.password_hash)
            if not correct:
                failures += 1
                db.execute(
                    "UPDATE app.login_guard SET failures=%s,window_start=%s,locked_until=%s WHERE id=1",
                    (
                        failures,
                        guard["window_start"] if failures > 1 else now,
                        now + timedelta(minutes=15) if failures >= 5 else None,
                    ),
                )
            else:
                db.execute(
                    "UPDATE app.login_guard SET failures=0,window_start=%s,locked_until=NULL WHERE id=1",
                    (now,),
                )
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                old = request.cookies.get(COOKIE)
                if old:
                    db.execute("DELETE FROM app.sessions WHERE token_hash=%s", (token_hash(old),))
                db.execute("DELETE FROM app.sessions WHERE expires_at<now()")
                db.execute(
                    "INSERT INTO app.sessions(token_hash,csrf,password_fingerprint,expires_at) VALUES (%s,%s,%s,%s)",
                    (token_hash(token), csrf, fingerprint, now + timedelta(hours=8)),
                )
        if not correct:
            raise HTTPException(401, "Incorrect password.")
        response.set_cookie(
            COOKIE,
            token,
            max_age=28800,
            httponly=True,
            secure=not settings.local_http,
            samesite="strict",
            path="/",
        )
        return {"authenticated": True, "csrf": csrf}

    @api.get("/v1/auth/session")
    def current_session(auth=authenticated):
        return {"authenticated": True, "csrf": auth["csrf"]}

    @api.post("/v1/auth/logout")
    def logout(request: Request, response: Response, _=authenticated):
        with database.connect() as db:
            db.execute(
                "DELETE FROM app.sessions WHERE token_hash=%s",
                (token_hash(request.cookies[COOKIE]),),
            )
        response.delete_cookie(
            COOKIE, path="/", secure=not settings.local_http, httponly=True, samesite="strict"
        )
        return {"authenticated": False}

    @api.get("/v1/application/tasks")
    def tasks(_=authenticated):
        with database.connect() as db:
            rows = db.execute(
                "SELECT id,title,description,area,COALESCE(due_date::text,'') AS date,done,version,note_ref AS \"noteId\" FROM app.tasks WHERE state<>'skipped' ORDER BY created_at,id"
            ).fetchall()
        return {"tasks": rows, "source": "postgresql"}

    @api.post("/v1/application/tasks", status_code=201)
    def create_task(body: TaskCreate, _=authenticated):
        with database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            row = db.execute(
                "INSERT INTO app.tasks(id,title,objective,description,area,due_date) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id,title,description,area,due_date AS date,done",
                (uuid4(), body.title, body.title, body.description, body.area, body.date),
            ).fetchone()
            history(db, row["id"], "task.create", {"source": "quick capture"})
        return {"task": row}

    @api.patch("/v1/application/tasks/{task_id}")
    def update_task(task_id: str, body: TaskUpdate, _=authenticated):
        from uuid import UUID

        try:
            identifier = UUID(task_id)
        except ValueError:
            raise HTTPException(404, "Task not found.") from None
        with database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            row = db.execute(
                "SELECT * FROM app.tasks WHERE id=%s FOR UPDATE",
                (identifier,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "Task not found.")
            if body.version is not None and body.version != row["version"]:
                raise HTTPException(
                    409, "This task changed in another view. Refresh before applying this change."
                )
            row = execute_task(
                db, row, ExecutionInput(action="complete" if body.done else "reopen")
            )
            row["date"] = row.pop("due_date")
        return {"task": row}

    def routine(db):
        row = db.execute(
            "SELECT * FROM app.routines WHERE id='sample-reading' FOR UPDATE"
        ).fetchone()
        if row is None:
            db.execute(
                "INSERT INTO app.routines(id,title,description,goal,scheduled_date,window_start,window_end,timezone,expected_minutes) VALUES ('sample-reading','A little space to learn','A synthetic reading routine.','Read one chapter and capture three takeaways.',CURRENT_DATE,'18:00','18:30','Europe/Berlin',30) ON CONFLICT DO NOTHING"
            )
            row = db.execute(
                "SELECT * FROM app.routines WHERE id='sample-reading' FOR UPDATE"
            ).fetchone()
        history = db.execute(
            "SELECT percent,at FROM app.routine_progress WHERE routine_id=%s ORDER BY id",
            (row["id"],),
        ).fetchall()
        iso = lambda v: v.isoformat() if v else None
        return {
            "version": 1,
            "definition": {
                "id": row["id"],
                "title": row["title"],
                "description": row["description"],
                "goal": row["goal"],
                "scheduledDate": str(row["scheduled_date"]),
                "windowStart": str(row["window_start"])[:5],
                "windowEnd": str(row["window_end"])[:5],
                "timezone": row["timezone"],
                "expectedMinutes": row["expected_minutes"],
            },
            "execution": {
                "status": row["status"],
                "progress": row["progress"],
                "startedAt": iso(row["started_at"]),
                "completedAt": iso(row["completed_at"]),
                "updatedAt": iso(row["updated_at"]),
                "progressHistory": [{"percent": p["percent"], "at": iso(p["at"])} for p in history],
            },
        }

    @api.get("/v1/application/routine")
    def read_routine(_=authenticated):
        with database.connect() as db:
            return routine(db)

    @api.post("/v1/application/routine/actions")
    def routine_action(body: RoutineCommand, _=authenticated):
        with database.connect() as db:
            current = routine(db)["execution"]
            if body.type == "start":
                if current["status"] == "not_started":
                    db.execute(
                        "UPDATE app.routines SET status='in_progress',started_at=now(),updated_at=now() WHERE id='sample-reading'"
                    )
            elif current["status"] != "in_progress":
                raise HTTPException(
                    409, "Start the routine first; completed routines cannot be changed."
                )
            elif body.type == "progress":
                if body.percent is None:
                    raise HTTPException(422, "A whole-number progress percentage is required.")
                db.execute(
                    "UPDATE app.routines SET progress=%s,updated_at=now() WHERE id='sample-reading'",
                    (body.percent,),
                )
                db.execute(
                    "INSERT INTO app.routine_progress(routine_id,percent,at) VALUES ('sample-reading',%s,now())",
                    (body.percent,),
                )
            else:
                db.execute(
                    "UPDATE app.routines SET status='completed',progress=100,completed_at=now(),updated_at=now() WHERE id='sample-reading'"
                )
                if current["progress"] != 100:
                    db.execute(
                        "INSERT INTO app.routine_progress(routine_id,percent,at) VALUES ('sample-reading',100,now())"
                    )
            return routine(db)

    @api.get("/v1/brain/tree")
    def tree(_=authenticated):
        return brain.tree()

    @api.get("/v1/brain/notes")
    def notes(_=authenticated):
        return brain.list_notes()

    @api.get("/v1/brain/notes/{note_id}")
    def note(note_id: str, _=authenticated):
        return brain.get(note_id)

    @api.post("/v1/brain/notes", status_code=201)
    def create_note(body: NoteCreate, _=authenticated):
        return brain.create(body.model_dump())

    @api.put("/v1/brain/notes/{note_id}")
    def replace_note(note_id: str, body: NoteReplace, _=authenticated):
        return brain.replace(note_id, body.version, body.model_dump(exclude={"version"}))

    @api.post("/v1/brain/notes/{note_id}/delete-preview")
    def delete_preview(note_id: str, body: Version, _=authenticated):
        return brain.preview_delete(note_id, body.version)

    @api.post("/v1/brain/notes/{note_id}/delete-confirm")
    def delete_confirm(note_id: str, body: DeleteConfirm, _=authenticated):
        return brain.confirm_delete(note_id, body.version, body.token, body.confirmed)

    return api
