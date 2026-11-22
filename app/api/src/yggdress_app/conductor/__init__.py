"""The conductor: the chat's orchestrator. It answers small requests itself and, for
bigger ones, plans, runs independent steps in parallel worker threads, verifies each
against a pass/fail check, and composes the answer. One module per job:

- state: the run state schema streamed to the client (single source of truth)
- log: the durable, seq-numbered event log a client replays to reconnect
"""
