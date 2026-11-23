"""The brain in PostgreSQL (schema `brain`): a derived, rebuildable copy of the markdown brain.

Markdown stays the source of truth (D1); the database is local only (D13). Nothing here reads
or writes for Lia yet: this package holds the schema, its migrations, the loader and the map
rendering.
"""
