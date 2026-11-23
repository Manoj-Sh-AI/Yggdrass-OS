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

The original local databases have different libc defaults: the application uses
`C`; Brain uses `English_India.1252`, both with UTF-8 and English text search. A
shared database has one default. Preserve Brain's default to protect its existing
text-processing behavior; application text ordering/case matching now follows that
default too. Application capture/completion/reload is tested with Unicode text in
the combined database. Do not rewrite Brain columns or algorithms to hide the
difference. Linux/Supabase locale compatibility still requires its own parity check.

The first combined copy was detected as having the application's default. Correct
that by copying the current combined records into a fresh database with Brain's
defaults, retaining any intervening saves and the prior combined database. This
uses the same backup, schema/row fingerprint, permission and cutover checks.
