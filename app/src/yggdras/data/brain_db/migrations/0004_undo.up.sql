-- 0004: the app's undo records (Manoj, 2026-11-12). One row per write made through the API:
-- the change it saved (payload.request_id), and whether its Undo was used. remove-fact and
-- unlink get a row too, so an Undo of them can say plainly that they are permanent.

CREATE TABLE brain.undo (
    undo_id    uuid PRIMARY KEY,
    operation  text NOT NULL CHECK (operation IN
                   ('add-note', 'add-fact', 'replace-fact', 'link', 'remove-fact', 'unlink')),
    payload    jsonb NOT NULL,
    used       boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);
