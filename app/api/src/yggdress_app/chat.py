"""Persistent conversation UI and a private response receiver. No model calls."""

import hashlib
import re
from typing import Literal
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from psycopg.types.json import Jsonb
from pydantic import ConfigDict, Field, ValidationError, model_validator
from starlette.concurrency import run_in_threadpool

from .chat_catalog import Selection, load_catalog, public_catalog, validate_selection
from .planning_models import Model
from .receivers import receiver_access

CHAT_LOCK = 719218403
MAX_FILE = 10 * 1024 * 1024
ATTACHMENT_FIELDS = "id,conversation_id,message_id,name,media_type,size,sha256,created_at"


class ChatCommand(Model):
    key: UUID
    operation: Literal[
        "conversation.create",
        "conversation.rename",
        "conversation.route",
        "conversation.archive",
        "conversation.delete",
        "message.send",
        "message.edit",
        "message.delete",
        "message.resend",
        "request.cancel",
        "attachment.remove",
    ]
    id: UUID | None = None
    version: int | None = Field(default=None, ge=1, strict=True)
    data: dict = Field(default_factory=dict)


class Title(Model):
    title: str = Field(min_length=1, max_length=180)


class Archive(Model):
    archived: bool


class Message(Model):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    content: str = Field(default="", max_length=50000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)
    deliver: bool = False

    @model_validator(mode="after")
    def nonempty(self):
        if not self.content.strip() and not self.attachment_ids:
            raise ValueError("Write a message or attach a file.")
        if len(set(self.attachment_ids)) != len(self.attachment_ids):
            raise ValueError("An attachment can appear only once.")
        return self


class Edit(Model):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    content: str = Field(min_length=1, max_length=50000)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.content.strip():
            raise ValueError("Write a message before saving your edit.")
        return self


class ResponseEvent(Model):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    event_key: str = Field(min_length=1, max_length=200)
    request_id: UUID
    sequence: int = Field(ge=0, strict=True)
    kind: Literal["delta", "complete", "error", "cancelled"]
    text: str = Field(default="", max_length=20000)

    @model_validator(mode="after")
    def valid_event(self):
        if self.kind == "delta" and not self.text:
            raise ValueError("A delta must contain text.")
        if self.kind in ("complete", "cancelled") and self.text:
            raise ValueError("Send text as delta events before a terminal event.")
        return self


def row(db, table, identifier, version=None):
    # Table names are private constants at call sites, never request fields.
    result = db.execute(
        f"SELECT * FROM app.{table} WHERE id=%s FOR UPDATE", (identifier,)
    ).fetchone()
    if not result:
        raise HTTPException(404, "This conversation item no longer exists.")
    if version is not None and result["version"] != version:
        raise HTTPException(409, "This conversation changed. Refresh before applying your edit.")
    return result


def touch(db, conversation_id):
    return db.execute(
        "UPDATE app.chat_conversations SET version=version+1,updated_at=clock_timestamp() WHERE id=%s RETURNING *",
        (conversation_id,),
    ).fetchone()


def receipt(db, key, fingerprint):
    saved = db.execute("SELECT * FROM app.planning_commands WHERE id=%s", (key,)).fetchone()
    if saved and saved["fingerprint"] != fingerprint:
        raise HTTPException(409, "This retry key belongs to a different change.")
    return saved["result"] if saved else None


def new_request(db, message, configured, deliver, catalog, selection=None):
    choice = selection or message
    configured = validate_selection(catalog, choice["agent_id"], choice["model_id"], configured)
    state = "queued" if configured and deliver else "held"
    return db.execute(
        "INSERT INTO app.chat_requests(conversation_id,user_message_id,user_message_version,state,agent_id,model_id) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *",
        (
            message["conversation_id"],
            message["id"],
            message["version"],
            state,
            choice["agent_id"],
            choice["model_id"],
        ),
    ).fetchone()


def cancel_message_requests(db, message_id):
    db.execute(
        "UPDATE app.chat_requests SET state='cancelled',version=version+1,updated_at=clock_timestamp() WHERE user_message_id=%s AND state IN ('held','queued','streaming')",
        (message_id,),
    )


def mutate(db, command, configured, catalog):
    operation, data = command.operation, command.data
    if operation == "conversation.create":
        title = Title.model_validate(data or {"title": "New conversation"}).title
        return {
            "conversation": db.execute(
                "INSERT INTO app.chat_conversations(title) VALUES (%s) RETURNING *", (title,)
            ).fetchone()
        }
    if operation.startswith("conversation."):
        if command.version is None:
            raise HTTPException(422, "The current conversation version is required.")
        conversation = row(db, "chat_conversations", command.id, command.version)
        if operation == "conversation.delete":
            if data:
                raise HTTPException(422, "Unexpected delete fields.")
            db.execute("DELETE FROM app.chat_conversations WHERE id=%s", (command.id,))
            return {"deleted": True, "id": command.id}
        if operation == "conversation.route":
            selection = Selection.model_validate(data)
            validate_selection(catalog, selection.agent_id, selection.model_id, configured)
            if conversation["archived"]:
                raise HTTPException(
                    409, "Restore the conversation before changing its destination."
                )
            db.execute(
                "UPDATE app.chat_conversations SET agent_id=%s,model_id=%s WHERE id=%s",
                (selection.agent_id, selection.model_id, command.id),
            )
        elif operation == "conversation.rename":
            db.execute(
                "UPDATE app.chat_conversations SET title=%s WHERE id=%s",
                (Title.model_validate(data).title, command.id),
            )
        else:
            archived = Archive.model_validate(data).archived
            db.execute(
                "UPDATE app.chat_conversations SET archived=%s WHERE id=%s", (archived, command.id)
            )
            if archived:
                db.execute(
                    "UPDATE app.chat_requests SET state='cancelled',version=version+1,updated_at=clock_timestamp() WHERE conversation_id=%s AND state IN ('held','queued','streaming')",
                    (command.id,),
                )
        return {"conversation": touch(db, conversation["id"])}
    if operation == "message.send":
        body = Message.model_validate(data)
        conversation = row(db, "chat_conversations", command.id)
        if conversation["archived"]:
            raise HTTPException(409, "Restore this conversation before adding a message.")
        for identifier in body.attachment_ids:
            attached = row(db, "chat_attachments", identifier)
            if attached["conversation_id"] != command.id or attached["message_id"] is not None:
                raise HTTPException(409, "Choose an unattached file from this conversation.")
        first = not db.execute(
            "SELECT 1 FROM app.chat_messages WHERE conversation_id=%s LIMIT 1", (command.id,)
        ).fetchone()
        message = db.execute(
            "INSERT INTO app.chat_messages(conversation_id,role,content,agent_id,model_id) VALUES (%s,'user',%s,%s,%s) RETURNING *",
            (command.id, body.content, conversation["agent_id"], conversation["model_id"]),
        ).fetchone()
        for identifier in body.attachment_ids:
            db.execute(
                "UPDATE app.chat_attachments SET message_id=%s WHERE id=%s",
                (message["id"], identifier),
            )
        request = new_request(db, message, configured, body.deliver, catalog)
        if first and conversation["title"] == "New conversation":
            db.execute(
                "UPDATE app.chat_conversations SET title=%s WHERE id=%s",
                (
                    (
                        body.content.strip().splitlines()[0][:80]
                        if body.content.strip()
                        else "Files and images"
                    ),
                    command.id,
                ),
            )
        return {"conversation": touch(db, command.id), "message": message, "request": request}
    if operation == "attachment.remove":
        attachment = row(db, "chat_attachments", command.id)
        if attachment["message_id"] is not None:
            raise HTTPException(409, "Sent attachments belong to their message history.")
        if data:
            raise HTTPException(422, "Unexpected attachment fields.")
        db.execute("DELETE FROM app.chat_attachments WHERE id=%s", (command.id,))
        return {"deleted": True}
    if operation == "request.cancel":
        if data:
            raise HTTPException(422, "Unexpected cancel fields.")
        if command.version is None:
            raise HTTPException(422, "The response request version is required.")
        request = row(db, "chat_requests", command.id, command.version)
        if request["state"] not in ("queued", "streaming", "held"):
            raise HTTPException(409, "This response request has already finished.")
        result = db.execute(
            "UPDATE app.chat_requests SET state='cancelled',version=version+1,updated_at=clock_timestamp() WHERE id=%s RETURNING *",
            (command.id,),
        ).fetchone()
        return {"request": result}
    if command.version is None:
        raise HTTPException(422, "The current message version is required.")
    message = row(db, "chat_messages", command.id, command.version)
    if message["role"] != "user" or message["deleted_at"]:
        raise HTTPException(409, "Only your current messages can be changed or resent.")
    if operation == "message.resend":
        destination = row(db, "chat_conversations", message["conversation_id"])
        if destination["archived"]:
            raise HTTPException(409, "Restore this conversation before resending messages.")
        if data:
            raise HTTPException(422, "Unexpected resend fields.")
        if not validate_selection(
            catalog, destination["agent_id"], destination["model_id"], configured
        ):
            raise HTTPException(
                503, "Yggdras responses are not connected yet. Your message is saved."
            )
        if db.execute(
            "SELECT 1 FROM app.chat_requests WHERE user_message_id=%s AND state IN ('queued','streaming')",
            (message["id"],),
        ).fetchone():
            raise HTTPException(409, "A response is already queued or running for this message.")
        cancel_message_requests(db, message["id"])
        return {"request": new_request(db, message, configured, True, catalog, destination)}
    cancel_message_requests(db, message["id"])
    if operation == "message.edit":
        content = Edit.model_validate(data).content
        updated = db.execute(
            "UPDATE app.chat_messages SET content=%s,version=version+1,edited_at=clock_timestamp() WHERE id=%s RETURNING *",
            (content, message["id"]),
        ).fetchone()
    else:
        if data:
            raise HTTPException(422, "Unexpected delete fields.")
        db.execute("DELETE FROM app.chat_attachments WHERE message_id=%s", (message["id"],))
        updated = db.execute(
            "UPDATE app.chat_messages SET content='',version=version+1,deleted_at=clock_timestamp() WHERE id=%s RETURNING *",
            (message["id"],),
        ).fetchone()
    return {"conversation": touch(db, message["conversation_id"]), "message": updated}


def chat_routers(database, session, tokens=None, catalog=None):
    catalog = load_catalog(catalog)
    access, configured = receiver_access("chat", tokens)
    owner = APIRouter(prefix="/v1/chat", dependencies=[Depends(session)])
    receiver = APIRouter(prefix="/v1/receivers/chat", dependencies=[Depends(access)])

    @owner.get("/capabilities")
    def capabilities():
        return {
            "receiver_configured": configured,
            "automatic_replay": False,
            "max_attachment_bytes": MAX_FILE,
            "voice": False,
            "catalog": public_catalog(catalog, configured),
        }

    @owner.post("/commands")
    def commands(command: ChatCommand):
        fingerprint = hashlib.sha256(
            ("chat:" + command.model_dump_json(exclude={"key"})).encode()
        ).hexdigest()
        with database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (CHAT_LOCK,))
            previous = receipt(db, command.key, fingerprint)
            if previous is not None:
                return previous
            try:
                result = jsonable_encoder(mutate(db, command, configured, catalog))
            except ValidationError as error:
                raise HTTPException(
                    422, "; ".join(item["msg"] for item in error.errors())
                ) from None
            db.execute(
                "INSERT INTO app.planning_commands(id,fingerprint,result) VALUES (%s,%s,%s)",
                (command.key, fingerprint, Jsonb(result)),
            )
            return result

    @owner.get("/conversations")
    def conversations(
        q: str = Query(default="", max_length=200),
        archived: bool = False,
        before: str | None = None,
        limit: int = Query(default=40, ge=1, le=100),
    ):
        # Cursor is a timestamp+UUID tuple encoded as two comma-separated fields.
        cursor = None
        if before:
            from datetime import datetime

            try:
                stamp, identifier = before.split(",", 1)
                cursor = (datetime.fromisoformat(stamp), UUID(identifier))
                if cursor[0].tzinfo is None:
                    raise ValueError
            except (ValueError, TypeError):
                raise HTTPException(422, "Invalid conversation cursor.") from None
        with database.connect() as db:
            rows = db.execute(
                "SELECT c.* FROM app.chat_conversations c WHERE c.archived=%s AND (%s='' OR c.title ILIKE %s OR EXISTS(SELECT 1 FROM app.chat_messages m WHERE m.conversation_id=c.id AND m.deleted_at IS NULL AND to_tsvector('simple',m.content) @@ websearch_to_tsquery('simple',%s))) AND (%s::timestamptz IS NULL OR (c.updated_at,c.id)<(%s::timestamptz,%s::uuid)) ORDER BY c.updated_at DESC,c.id DESC LIMIT %s",
                (
                    archived,
                    q,
                    "%" + q + "%",
                    q,
                    cursor[0] if cursor else None,
                    cursor[0] if cursor else None,
                    cursor[1] if cursor else None,
                    limit + 1,
                ),
            ).fetchall()
            items = rows[:limit]
            return {
                "conversations": items,
                "next": f"{items[-1]['updated_at'].isoformat()},{items[-1]['id']}"
                if len(rows) > limit
                else None,
            }

    @owner.get("/conversations/{identifier}")
    def messages(
        identifier: UUID,
        before: int | None = Query(default=None, ge=1),
        limit: int = Query(default=60, ge=1, le=100),
    ):
        with database.connect() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            conversation = db.execute(
                "SELECT * FROM app.chat_conversations WHERE id=%s", (identifier,)
            ).fetchone()
            if not conversation:
                raise HTTPException(404, "Conversation not found.")
            rows = db.execute(
                "SELECT * FROM app.chat_messages WHERE conversation_id=%s AND (%s::bigint IS NULL OR ordinal<%s) ORDER BY ordinal DESC LIMIT %s",
                (identifier, before, before, limit + 1),
            ).fetchall()
            items = list(reversed(rows[:limit]))
            identifiers = [item["id"] for item in items]
            attachments = db.execute(
                f"SELECT {ATTACHMENT_FIELDS} FROM app.chat_attachments WHERE conversation_id=%s AND (message_id=ANY(%s) OR message_id IS NULL) ORDER BY created_at,id",
                (identifier, identifiers),
            ).fetchall()
            requests = db.execute(
                "SELECT * FROM app.chat_requests WHERE conversation_id=%s AND user_message_id=ANY(%s) ORDER BY created_at,id",
                (identifier, identifiers),
            ).fetchall()
            return {
                "conversation": conversation,
                "messages": items,
                "attachments": attachments,
                "requests": requests,
                "next_before": items[0]["ordinal"] if len(rows) > limit else None,
            }

    @owner.get("/conversations/{identifier}/export")
    def export(identifier: UUID):
        with database.connect() as db:
            conversation = db.execute(
                "SELECT * FROM app.chat_conversations WHERE id=%s", (identifier,)
            ).fetchone()
            if not conversation:
                raise HTTPException(404, "Conversation not found.")
            messages = db.execute(
                "SELECT * FROM app.chat_messages WHERE conversation_id=%s ORDER BY ordinal LIMIT 10001",
                (identifier,),
            ).fetchall()
            if len(messages) > 10000:
                raise HTTPException(
                    413, "Export this long conversation in pages through the history API."
                )
            files = db.execute(
                f"SELECT {ATTACHMENT_FIELDS} FROM app.chat_attachments WHERE conversation_id=%s",
                (identifier,),
            ).fetchall()
            return {
                "format": "yggdras.conversation.v1",
                "conversation": conversation,
                "messages": messages,
                "attachments": files,
            }

    @owner.post("/attachments")
    async def upload(
        request: Request,
        conversation_id: UUID,
        name: str = Query(min_length=1, max_length=180),
        upload_id: UUID | None = None,
    ):
        content = bytearray()
        async for chunk in request.stream():
            content.extend(chunk)
            if len(content) > MAX_FILE:
                raise HTTPException(413, "Each file must be 10 MB or smaller.")
        if not content:
            raise HTTPException(422, "Choose a file with content.")
        safe_name = re.sub(
            r"[\x00-\x1f\x7f]", "", name.replace("\\", "/").rsplit("/", 1)[-1]
        ).strip()
        if not safe_name:
            raise HTTPException(422, "Choose a valid filename.")
        raw = bytes(content)
        digest = hashlib.sha256(raw).hexdigest()
        media_type = "application/octet-stream"
        if raw.startswith(b"\x89PNG\r\n\x1a\n"):
            media_type = "image/png"
        elif raw.startswith(b"\xff\xd8\xff"):
            media_type = "image/jpeg"
        elif raw.startswith((b"GIF87a", b"GIF89a")):
            media_type = "image/gif"
        elif raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
            media_type = "image/webp"

        def save():
            with database.connect() as db:
                conversation = row(db, "chat_conversations", conversation_id)
                if upload_id:
                    existing = db.execute(
                        f"SELECT {ATTACHMENT_FIELDS} FROM app.chat_attachments WHERE id=%s",
                        (upload_id,),
                    ).fetchone()
                    if existing:
                        if (
                            existing["conversation_id"] != conversation_id
                            or existing["sha256"] != digest
                            or existing["name"] != safe_name
                        ):
                            raise HTTPException(409, "This upload key belongs to a different file.")
                        return existing
                if conversation["archived"]:
                    raise HTTPException(409, "Restore this conversation before attaching files.")
                if (
                    db.execute(
                        "SELECT count(*) AS n FROM app.chat_attachments WHERE conversation_id=%s AND message_id IS NULL",
                        (conversation_id,),
                    ).fetchone()["n"]
                    >= 5
                ):
                    raise HTTPException(
                        422, "Send or remove the five existing draft attachments first."
                    )
                return db.execute(
                    f"INSERT INTO app.chat_attachments(id,conversation_id,name,media_type,size,sha256,data) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING {ATTACHMENT_FIELDS}",
                    (
                        upload_id or uuid4(),
                        conversation_id,
                        safe_name,
                        media_type,
                        len(raw),
                        digest,
                        raw,
                    ),
                ).fetchone()

        return await run_in_threadpool(save)

    def download(db, identifier):
        attachment = db.execute(
            "SELECT name,media_type,data FROM app.chat_attachments WHERE id=%s", (identifier,)
        ).fetchone()
        if not attachment:
            raise HTTPException(404, "Attachment not found.")
        return Response(
            bytes(attachment["data"]),
            media_type=attachment["media_type"],
            headers={
                "Content-Disposition": "attachment; filename*=UTF-8''"
                + quote(attachment["name"], safe=""),
                "Content-Security-Policy": "sandbox; default-src 'none'",
                "Cache-Control": "no-store",
            },
        )

    @owner.get("/attachments/{identifier}")
    def attachment(identifier: UUID):
        with database.connect() as db:
            return download(db, identifier)

    @receiver.get("/pending")
    def pending(limit: int = Query(default=10, ge=1, le=40)):
        with database.connect() as db:
            return {
                "requests": db.execute(
                    "SELECT r.*,m.content FROM app.chat_requests r JOIN app.chat_messages m ON m.id=r.user_message_id WHERE r.state='queued' AND m.deleted_at IS NULL AND m.version=r.user_message_version ORDER BY r.created_at,r.id LIMIT %s",
                    (limit,),
                ).fetchall()
            }

    @receiver.get("/requests/{identifier}")
    def provider_context(identifier: UUID):
        with database.connect() as db:
            request = row(db, "chat_requests", identifier)
            if request["state"] == "held":
                raise HTTPException(
                    409, "This saved message has not been submitted for processing."
                )
            messages = db.execute(
                "SELECT * FROM app.chat_messages WHERE conversation_id=%s AND deleted_at IS NULL AND ordinal<=(SELECT ordinal FROM app.chat_messages WHERE id=%s) ORDER BY ordinal DESC LIMIT 60",
                (request["conversation_id"], request["user_message_id"]),
            ).fetchall()
            files = db.execute(
                f"SELECT {ATTACHMENT_FIELDS} FROM app.chat_attachments WHERE message_id=ANY(%s)",
                ([message["id"] for message in messages],),
            ).fetchall()
            return {"request": request, "messages": list(reversed(messages)), "attachments": files}

    @receiver.get("/requests/{request_id}/attachments/{identifier}")
    def provider_attachment(request_id: UUID, identifier: UUID):
        with database.connect() as db:
            request = row(db, "chat_requests", request_id)
            file = db.execute(
                "SELECT conversation_id,message_id FROM app.chat_attachments WHERE id=%s",
                (identifier,),
            ).fetchone()
            if (
                request["state"] == "held"
                or not file
                or file["conversation_id"] != request["conversation_id"]
                or file["message_id"] is None
                or not db.execute(
                    "SELECT 1 FROM app.chat_messages m WHERE m.id=%s AND m.deleted_at IS NULL AND m.ordinal<=(SELECT ordinal FROM app.chat_messages WHERE id=%s)",
                    (file["message_id"], request["user_message_id"]),
                ).fetchone()
            ):
                raise HTTPException(
                    404, "This attachment is not available to this response request."
                )
            return download(db, identifier)

    @receiver.post("/events")
    def receive(event: ResponseEvent):
        fingerprint = hashlib.sha256(event.model_dump_json().encode()).hexdigest()
        with database.connect() as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (CHAT_LOCK,))
            previous = db.execute(
                "SELECT * FROM app.receiver_receipts WHERE scope='chat' AND event_key=%s",
                (event.event_key,),
            ).fetchone()
            if previous:
                if previous["fingerprint"] != fingerprint:
                    raise HTTPException(409, "This response event key was already used.")
                return previous["result"]
            request = row(db, "chat_requests", event.request_id)
            message = row(db, "chat_messages", request["user_message_id"])
            if (
                request["state"] not in ("queued", "streaming")
                or message["deleted_at"]
                or message["version"] != request["user_message_version"]
            ):
                raise HTTPException(409, "This response request is no longer current.")
            if event.sequence != request["next_sequence"]:
                raise HTTPException(409, "Response events must arrive in sequence.")
            if event.kind == "delta":
                existing = db.execute(
                    "SELECT * FROM app.chat_messages WHERE id=%s",
                    (request["assistant_message_id"],),
                ).fetchone()
                if len((existing["content"] if existing else "") + event.text) > 200000:
                    raise HTTPException(413, "This response exceeds the message limit.")
                db.execute(
                    "INSERT INTO app.chat_messages(id,conversation_id,role,content,source_message_id,source_version,agent_id,model_id) VALUES (%s,%s,'assistant',%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET content=app.chat_messages.content||EXCLUDED.content,version=app.chat_messages.version+1",
                    (
                        request["assistant_message_id"],
                        request["conversation_id"],
                        event.text,
                        message["id"],
                        message["version"],
                        request["agent_id"],
                        request["model_id"],
                    ),
                )
                state, error = "streaming", ""
            else:
                if event.kind == "complete" and event.text:
                    raise HTTPException(
                        422, "Send response text as delta events before completion."
                    )
                if (
                    event.kind == "complete"
                    and not db.execute(
                        "SELECT 1 FROM app.chat_messages WHERE id=%s",
                        (request["assistant_message_id"],),
                    ).fetchone()
                ):
                    raise HTTPException(422, "A completed response must contain a message.")
                state = {"complete": "completed", "error": "failed", "cancelled": "cancelled"}[
                    event.kind
                ]
                error = event.text if event.kind == "error" else ""
            updated = db.execute(
                "UPDATE app.chat_requests SET state=%s,error=%s,next_sequence=next_sequence+1,version=version+1,updated_at=clock_timestamp() WHERE id=%s RETURNING *",
                (state, error, request["id"]),
            ).fetchone()
            touch(db, request["conversation_id"])
            result = jsonable_encoder({"request": updated})
            db.execute(
                "INSERT INTO app.receiver_receipts(scope,event_key,fingerprint,result) VALUES ('chat',%s,%s,%s)",
                (event.event_key, fingerprint, Jsonb(result)),
            )
            return result

    return owner, receiver
