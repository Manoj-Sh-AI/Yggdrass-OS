-- Remember intent independently from a future provider connection. No model calls.
ALTER TABLE app.chat_conversations ADD COLUMN agent_id text NOT NULL DEFAULT 'yggdras';
ALTER TABLE app.chat_conversations ADD COLUMN model_id text NOT NULL DEFAULT 'default';
ALTER TABLE app.chat_messages ADD COLUMN agent_id text NOT NULL DEFAULT 'yggdras';
ALTER TABLE app.chat_messages ADD COLUMN model_id text NOT NULL DEFAULT 'default';
ALTER TABLE app.chat_requests ADD COLUMN agent_id text NOT NULL DEFAULT 'yggdras';
ALTER TABLE app.chat_requests ADD COLUMN model_id text NOT NULL DEFAULT 'default';
