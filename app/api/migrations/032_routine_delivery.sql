-- Capabilities belong to one signed-in device. Signing out revokes its pending actions.
CREATE TABLE app.web_push_subscriptions (
    id uuid PRIMARY KEY, endpoint text UNIQUE NOT NULL, keys jsonb NOT NULL,
    session_hash text NOT NULL REFERENCES app.sessions(token_hash) ON DELETE CASCADE
);
CREATE TABLE app.web_push_deliveries (
    id uuid PRIMARY KEY, subscription uuid NOT NULL REFERENCES app.web_push_subscriptions ON DELETE CASCADE,
    dedupe_key text NOT NULL, kind text NOT NULL, escalation_id uuid,
    expires_at timestamptz NOT NULL, status text NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending','sending','accepted','failed','expired')),
    UNIQUE(subscription, dedupe_key)
);
CREATE INDEX web_push_due ON app.web_push_deliveries(expires_at) WHERE status IN ('pending','sending');
CREATE TABLE app.web_push_tokens (
    digest text PRIMARY KEY, delivery uuid UNIQUE NOT NULL REFERENCES app.web_push_deliveries ON DELETE CASCADE,
    used_at timestamptz
);
CREATE TABLE app.routine_voice_bindings (
    call_id uuid PRIMARY KEY REFERENCES app.calls ON DELETE CASCADE, escalation_id uuid NOT NULL,
    summary text NOT NULL, context text NOT NULL, capability_digest text, expires_at timestamptz,
    lookup_used boolean NOT NULL DEFAULT false, applied_action text
);
