-- Application-owned conversations. No provider, orchestrator, or Brain writes.
CREATE TABLE app.chat_conversations (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), title text NOT NULL DEFAULT 'New conversation'
 CHECK(length(trim(title)) BETWEEN 1 AND 180), archived boolean NOT NULL DEFAULT false,
 version integer NOT NULL DEFAULT 1 CHECK(version>0),
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX chat_conversation_recent ON app.chat_conversations(archived,updated_at DESC,id);
CREATE TABLE app.chat_messages (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 conversation_id uuid NOT NULL REFERENCES app.chat_conversations(id) ON DELETE CASCADE,
 ordinal bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
 role text NOT NULL CHECK(role IN ('user','assistant')),
 content text NOT NULL DEFAULT '' CHECK(length(content)<=200000),
 version integer NOT NULL DEFAULT 1 CHECK(version>0),
 source_message_id uuid REFERENCES app.chat_messages(id) ON DELETE SET NULL,
 source_version integer, created_at timestamptz NOT NULL DEFAULT now(),
 edited_at timestamptz, deleted_at timestamptz
);
CREATE INDEX chat_message_history ON app.chat_messages(conversation_id,ordinal DESC);
CREATE INDEX chat_message_search ON app.chat_messages USING gin(to_tsvector('simple',content));
CREATE TABLE app.chat_requests (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 conversation_id uuid NOT NULL REFERENCES app.chat_conversations(id) ON DELETE CASCADE,
 user_message_id uuid NOT NULL REFERENCES app.chat_messages(id) ON DELETE CASCADE,
 user_message_version integer NOT NULL, assistant_message_id uuid NOT NULL DEFAULT gen_random_uuid(),
 state text NOT NULL CHECK(state IN ('held','queued','streaming','completed','failed','cancelled')),
 next_sequence integer NOT NULL DEFAULT 0 CHECK(next_sequence>=0),
 error text NOT NULL DEFAULT '', version integer NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX one_live_chat_response ON app.chat_requests(user_message_id)
 WHERE state IN ('queued','streaming');
CREATE INDEX chat_request_pending ON app.chat_requests(state,created_at,id);
CREATE TABLE app.chat_attachments (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
 conversation_id uuid NOT NULL REFERENCES app.chat_conversations(id) ON DELETE CASCADE,
 message_id uuid REFERENCES app.chat_messages(id) ON DELETE CASCADE,
 name text NOT NULL CHECK(length(name) BETWEEN 1 AND 180), media_type text NOT NULL,
 size integer NOT NULL CHECK(size BETWEEN 1 AND 10485760),
 sha256 text NOT NULL CHECK(length(sha256)=64), data bytea NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), CHECK(octet_length(data)=size)
);
CREATE INDEX chat_attachment_message ON app.chat_attachments(message_id);
CREATE TABLE app.receiver_receipts (
 scope text NOT NULL, event_key text NOT NULL CHECK(length(event_key) BETWEEN 1 AND 200),
 fingerprint text NOT NULL, result jsonb NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(scope,event_key)
);
