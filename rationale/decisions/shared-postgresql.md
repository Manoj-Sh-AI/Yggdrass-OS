# Shared database, separate schema ownership

The owner selected one database before deployment. Separate databases were an
implementation isolation choice; logical separation is the architectural boundary.
Existing schema-qualified SQL permits co-location without changing Lia's engine.

Use a new local database containing `app` and `brain`, separate schema-owner roles,
and a restricted application runtime role. Retain the prior databases as rollback
sources. Application upgrades continue to own only `app`; administrative backup
operations may read the complete database.

Tradeoff: simpler eventual single-project hosting and one database connection
location, with shared capacity and outage scope. Role grants, default privileges,
schema checks and restoration tests replace physical database isolation. The new
copy temporarily consumes additional local disk. No database is deleted by this
operation, and a local merge does not establish Supabase compatibility by itself.
