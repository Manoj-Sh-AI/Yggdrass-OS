"""The conductor's view of the existing chat tables. Finished turns are saved there, so
conversation history, search, export and the phone keep working unchanged."""

from __future__ import annotations

HISTORY_TURNS = 20  # messages of context sent to the model


class ChatHistory:
    def __init__(self, database):
        self.database = database

    def ensure_conversation(self, conversation_id: str | None, first_text: str, model: str) -> str:
        with self.database.connect() as db:
            if conversation_id:
                row = db.execute(
                    "SELECT id FROM app.chat_conversations WHERE id=%s", (conversation_id,)
                ).fetchone()
                if row:
                    return str(row["id"])
            title = " ".join(first_text.split())[:80] or "New conversation"
            row = db.execute(
                """INSERT INTO app.chat_conversations(title,model_id) VALUES (%s,%s)
                   RETURNING id""",
                (title, model),
            ).fetchone()
            return str(row["id"])

    def recent(self, conversation_id: str, limit: int = HISTORY_TURNS) -> list[dict[str, str]]:
        """The last messages as model turns, oldest first, adjacent same-role merged."""
        with self.database.connect() as db:
            rows = db.execute(
                """SELECT role,content FROM app.chat_messages
                   WHERE conversation_id=%s AND deleted_at IS NULL AND content<>''
                   ORDER BY ordinal DESC LIMIT %s""",
                (conversation_id, limit),
            ).fetchall()
        turns: list[dict[str, str]] = []
        for row in reversed(rows):
            if turns and turns[-1]["role"] == row["role"]:
                turns[-1]["content"] += "\n\n" + row["content"]
            else:
                turns.append({"role": row["role"], "content": row["content"]})
        while turns and turns[0]["role"] != "user":  # the API needs a user turn first
            turns.pop(0)
        return turns

    def save_user(self, conversation_id: str, text: str, model: str) -> str:
        with self.database.connect() as db:
            row = db.execute(
                """INSERT INTO app.chat_messages(conversation_id,role,content,model_id,agent_id)
                   VALUES (%s,'user',%s,%s,'conductor') RETURNING id""",
                (conversation_id, text, model),
            ).fetchone()
            db.execute(
                "UPDATE app.chat_conversations SET updated_at=now() WHERE id=%s",
                (conversation_id,),
            )
        return str(row["id"])

    def save_assistant(self, conversation_id: str, text: str, source_id: str, model: str) -> None:
        if not text:
            return
        with self.database.connect() as db:
            db.execute(
                """INSERT INTO app.chat_messages
                   (conversation_id,role,content,source_message_id,source_version,model_id,agent_id)
                   VALUES (%s,'assistant',%s,%s,1,%s,'conductor')""",
                (conversation_id, text, source_id, model),
            )
            db.execute(
                "UPDATE app.chat_conversations SET updated_at=now() WHERE id=%s",
                (conversation_id,),
            )

    def plain_messages(self, conversation_id: str) -> list[dict[str, str]]:
        """Messages not written by the conductor (the previous chat, the phone), with
        their time, to merge with the conductor's runs."""
        with self.database.connect() as db:
            rows = db.execute(
                """SELECT id,role,content,created_at FROM app.chat_messages
                   WHERE conversation_id=%s AND deleted_at IS NULL AND agent_id<>'conductor'
                   ORDER BY ordinal""",
                (conversation_id,),
            ).fetchall()
        return [
            {"id": str(r["id"]), "role": r["role"], "content": r["content"], "at": r["created_at"]}
            for r in rows
        ]
