"""Explicit, verified local consolidation. Never overwrite or delete a source.

This is deployment plumbing, not a Brain writer or migration implementation.
Connection strings and detailed verification reports belong in private storage.
"""

import hashlib
import re
import secrets
import subprocess
from contextlib import ExitStack
from pathlib import Path

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from .backup import BackupError, client_environment, database_backup, fingerprints, tool

LAYOUT = "shared-schemas-v1"


class ConsolidationError(RuntimeError):
    pass


def _binary(directory, name):
    path = Path(directory) / name
    return path.with_suffix(".exe") if path.with_suffix(".exe").is_file() else path


def schema_digest(url, namespace, binary_dir):
    """Compare definitions independently of schema owner names and ACLs."""
    raw = tool(
        _binary(binary_dir, "pg_dump"),
        ["--schema-only", "--no-owner", "--no-privileges", "--schema=" + namespace],
        client_environment(url),
    ).decode("utf-8")
    normalized = "\n".join(
        line.rstrip()
        for line in raw.splitlines()
        if line.strip() and not line.startswith(("--", "\\restrict", "\\unrestrict"))
    )
    return hashlib.sha256(normalized.encode()).hexdigest()


def _source_guard(connection, namespace, shared=False):
    """Lock existing tables, reject unsupported contents and ambiguous ownership."""
    connection.execute("SET lock_timeout='5s'")
    namespaces = {
        row[0]
        for row in connection.execute(
            "SELECT nspname FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' "
            "AND nspname<>'information_schema'"
        )
    }
    if namespaces != ({"app", "brain", "public"} if shared else {namespace, "public"}):
        raise ConsolidationError(
            "Source schemas do not match the selected database responsibility."
        )
    if connection.execute(
        "SELECT EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public') OR EXISTS(SELECT 1 FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public') "
        "OR EXISTS(SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
        "WHERE n.nspname='public')"
    ).fetchone()[0]:
        raise ConsolidationError("Public schema objects require an explicit migration design.")
    if connection.execute("SELECT extname FROM pg_extension ORDER BY 1").fetchall() != [
        ("plpgsql",)
    ]:
        raise ConsolidationError("Additional extensions require an explicit migration design.")
    if connection.execute("SELECT count(*) FROM pg_largeobject_metadata").fetchone()[0]:
        raise ConsolidationError("Large objects require an explicit migration design.")
    tables = connection.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname=%s ORDER BY tablename", (namespace,)
    ).fetchall()
    if not tables:
        raise ConsolidationError("A source schema has no tables.")
    connection.execute(
        sql.SQL("LOCK TABLE {} IN SHARE MODE").format(
            sql.SQL(",").join(sql.Identifier(namespace, name) for (name,) in tables)
        )
    )
    # A source must not change shape while it is exported. An unknown external
    # writer/migrator is a reason to stop, not something to terminate silently.
    return namespace_snapshot(fingerprints(connection), namespace)


def namespace_snapshot(snapshot, namespace):
    return {
        "tables": {k: v for k, v in snapshot["tables"].items() if k.startswith(namespace + ".")},
        "sequences": {
            k: v for k, v in snapshot["sequences"].items() if k.startswith(namespace + ".")
        },
        "large_objects": snapshot["large_objects"],
    }


def text_settings(connection):
    row = connection.execute(
        "SELECT pg_encoding_to_char(encoding),datlocprovider,datcollate,datctype,"
        "current_setting('default_text_search_config') "
        "FROM pg_database WHERE datname=current_database()"
    ).fetchone()
    return dict(zip(("encoding", "provider", "collate", "ctype", "text_search"), row, strict=True))


def _combined_snapshot(application, brain):
    if application["large_objects"] or brain["large_objects"]:
        raise ConsolidationError("Large objects are unsupported by this consolidation.")
    for key in ("tables", "sequences"):
        if set(application[key]) & set(brain[key]):
            raise ConsolidationError("Source database objects overlap.")
    return {
        "tables": {**application["tables"], **brain["tables"]},
        "sequences": {**application["sequences"], **brain["sequences"]},
        "large_objects": [],
    }


def verify_boundaries(admin_url, application_url, migration_url, brain_url):
    """Read-only verification of schema access, ownership and role membership."""
    destination = conninfo_to_dict(admin_url)
    for value in (application_url, migration_url, brain_url):
        connection = conninfo_to_dict(value)
        if any(destination.get(k) != connection.get(k) for k in ("host", "port", "dbname")):
            raise ConsolidationError(
                "Service connections must use the same database server and name."
            )
    roles = {
        "application": conninfo_to_dict(application_url)["user"],
        "migration": conninfo_to_dict(migration_url)["user"],
        "brain": conninfo_to_dict(brain_url)["user"],
    }
    if len(set(roles.values())) != 3:
        raise ConsolidationError("Each responsibility requires a distinct database role.")
    with psycopg.connect(admin_url) as admin:
        for label, role in roles.items():
            flags = admin.execute(
                "SELECT rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls "
                "FROM pg_roles WHERE rolname=%s",
                (role,),
            ).fetchone()
            if flags is None or any(flags):
                raise ConsolidationError("A service role has administrative privileges.")
            if admin.execute(
                "SELECT count(*) FROM pg_auth_members WHERE member="
                "(SELECT oid FROM pg_roles WHERE rolname=%s)",
                (role,),
            ).fetchone()[0]:
                raise ConsolidationError("A service role inherits other roles.")
            own, other = ("brain", "app") if label == "brain" else ("app", "brain")
            if not admin.execute(
                "SELECT has_schema_privilege(%s,%s,'USAGE') "
                "AND NOT has_schema_privilege(%s,%s,'USAGE') "
                "AND NOT has_schema_privilege(%s,%s,'CREATE')",
                (role, own, role, other, role, other),
            ).fetchone()[0]:
                raise ConsolidationError("Cross-schema access is not isolated.")
            if admin.execute(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname=%s AND c.relkind IN ('r','p','v','m','S') AND "
                "(has_table_privilege(%s,c.oid,'SELECT') OR "
                "has_table_privilege(%s,c.oid,'INSERT') OR has_table_privilege(%s,c.oid,'UPDATE') "
                "OR has_table_privilege(%s,c.oid,'DELETE'))",
                (other, role, role, role, role),
            ).fetchone()[0]:
                raise ConsolidationError("A service role has access to the other schema's objects.")
            if admin.execute(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
                "WHERE n.nspname=%s AND has_function_privilege(%s,p.oid,'EXECUTE')",
                (other, role),
            ).fetchone()[0]:
                raise ConsolidationError("A service role can execute the other schema's functions.")
    for url in (application_url, migration_url, brain_url):
        with psycopg.connect(url, connect_timeout=5) as db:
            if db.info.dbname != conninfo_to_dict(admin_url)["dbname"]:
                raise ConsolidationError("Service connections do not share one database.")
            if db.execute("SELECT has_database_privilege(current_database(),'CREATE')").fetchone()[
                0
            ]:
                raise ConsolidationError(
                    "Service roles must not create arbitrary database schemas."
                )
    return True


def copy_runtime_grants(source, target, role):
    """Preserve installed ACLs, independent of uninstalled checkout migrations."""
    objects = source.execute(
        "SELECT c.relkind,c.relname,a.privilege_type,a.is_grantable "
        "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "CROSS JOIN LATERAL aclexplode(c.relacl) a "
        "WHERE n.nspname='app' AND c.relkind IN ('r','p','v','m','S') "
        "AND a.grantee=(SELECT oid FROM pg_roles WHERE rolname=%s)",
        (role,),
    ).fetchall()
    allowed = {
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
        "TRUNCATE",
        "REFERENCES",
        "TRIGGER",
        "USAGE",
        "MAINTAIN",
    }
    for kind, name, privilege, grantable in objects:
        if grantable or privilege not in allowed:
            raise ConsolidationError("Unexpected runtime privileges require review.")
        target.execute(
            sql.SQL("GRANT {} ON {} {} TO {}").format(
                sql.SQL(privilege),
                sql.SQL("SEQUENCE" if kind == "S" else "TABLE"),
                sql.Identifier("app", name),
                sql.Identifier(role),
            )
        )
    columns = source.execute(
        "SELECT c.relname,t.attname,a.privilege_type,a.is_grantable "
        "FROM pg_attribute t JOIN pg_class c ON c.oid=t.attrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "CROSS JOIN LATERAL aclexplode(t.attacl) a WHERE n.nspname='app' "
        "AND t.attnum>0 AND NOT t.attisdropped "
        "AND a.grantee=(SELECT oid FROM pg_roles WHERE rolname=%s)",
        (role,),
    ).fetchall()
    for table, column, privilege, grantable in columns:
        if grantable or privilege not in allowed:
            raise ConsolidationError("Unexpected column privileges require review.")
        target.execute(
            sql.SQL("GRANT {} ({}) ON TABLE {} TO {}").format(
                sql.SQL(privilege),
                sql.Identifier(column),
                sql.Identifier("app", table),
                sql.Identifier(role),
            )
        )
    target.execute(sql.SQL("GRANT USAGE ON SCHEMA app TO {}").format(sql.Identifier(role)))


def prepare(
    application_admin,
    application_runtime,
    brain_source,
    binary_dir,
    archive,
    name,
    shared_source=False,
    destination_text_settings=None,
):
    """Create a verified combined copy. Does not activate services or delete databases.

    Caller must stop application workers and external Brain writers first. Table
    locks additionally reject/wait for concurrent DML while exporting. The archive
    must be private and new. On failure keep the partial destination for inspection.
    """
    if not re.fullmatch(r"yggdras_unified_[a-z0-9_]{1,35}", name):
        raise ConsolidationError("Use a new, explicitly named consolidation destination.")
    if conninfo_to_dict(application_admin)["dbname"] == name:
        raise ConsolidationError("The destination must not be a source database.")
    with psycopg.connect(application_admin, connect_timeout=10) as admin:
        if admin.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
            raise ConsolidationError("Destination already exists; it was not changed.")
    archive = Path(archive)
    archive.mkdir(parents=True, exist_ok=False)
    with ExitStack() as stack:
        app = stack.enter_context(psycopg.connect(application_admin, connect_timeout=10))
        brain = stack.enter_context(psycopg.connect(brain_source, connect_timeout=10))
        app_before = _source_guard(app, "app", shared_source)
        brain_before = _source_guard(brain, "brain", shared_source)
        app_text, brain_text = text_settings(app), text_settings(brain)
        desired_text = destination_text_settings or brain_text
        if desired_text["provider"] != "c" or app_text["encoding"] != desired_text["encoding"]:
            raise ConsolidationError(
                "Database locale/encoding requires a supported libc migration."
            )
        if app_text["text_search"] != desired_text["text_search"]:
            raise ConsolidationError("Text-search defaults differ and require an explicit design.")
        if app.execute(
            "SELECT EXISTS(SELECT 1 FROM app.agent_runs WHERE state='running') "
            "OR EXISTS(SELECT 1 FROM app.chat_requests WHERE state IN ('queued','streaming'))"
        ).fetchone()[0]:
            raise ConsolidationError(
                "Finish or explicitly cancel submitted requests before copying."
            )
        expected = _combined_snapshot(app_before, brain_before)
        app_schema = schema_digest(application_admin, "app", binary_dir)
        brain_schema = schema_digest(brain_source, "brain", binary_dir)
        reports = {}
        for label, source in (("application", application_admin), ("brain", brain_source)):
            workspace = archive / (label + "-restore-check")
            workspace.mkdir()
            reports[label] = database_backup(
                source, archive / (label + ".dump"), Path(binary_dir), workspace
            )
        if (
            namespace_snapshot(reports["application"]["snapshot"], "app") != app_before
            or namespace_snapshot(reports["brain"]["snapshot"], "brain") != brain_before
        ):
            raise ConsolidationError("A source changed while preparing its backup.")
        suffix = secrets.token_hex(5)
        owners = {"app": "ygg_app_owner_" + suffix, "brain": "ygg_brain_" + suffix}
        passwords = {namespace: secrets.token_urlsafe(40) for namespace in owners}
        target_admin = make_conninfo(application_admin, dbname=name)
        urls = {
            namespace: make_conninfo(target_admin, user=role, password=passwords[namespace])
            for namespace, role in owners.items()
        }
        with psycopg.connect(application_admin, autocommit=True) as admin:
            if admin.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                raise ConsolidationError("Destination already exists; it was not changed.")
            for namespace, role in owners.items():
                admin.execute(
                    sql.SQL(
                        "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB "
                        "NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS"
                    ).format(sql.Identifier(role), sql.Literal(passwords[namespace]))
                )
            admin.execute(
                sql.SQL(
                    "CREATE DATABASE {} TEMPLATE template0 LOCALE_PROVIDER libc "
                    "ENCODING {} LC_COLLATE {} LC_CTYPE {}"
                ).format(
                    sql.Identifier(name),
                    sql.Literal(desired_text["encoding"]),
                    sql.Literal(desired_text["collate"]),
                    sql.Literal(desired_text["ctype"]),
                )
            )
            admin.execute(
                sql.SQL("ALTER DATABASE {} SET default_text_search_config TO {}").format(
                    sql.Identifier(name), sql.Literal(desired_text["text_search"])
                )
            )
        runtime = make_conninfo(application_runtime, dbname=name)
        runtime_role = conninfo_to_dict(runtime)["user"]
        with psycopg.connect(target_admin) as admin:
            if text_settings(admin) != desired_text:
                raise ConsolidationError(
                    "Destination text settings differ from the Brain baseline."
                )
            admin.execute(
                sql.SQL("REVOKE ALL ON DATABASE {} FROM PUBLIC").format(sql.Identifier(name))
            )
            admin.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
            for role in (*owners.values(), runtime_role):
                admin.execute(
                    sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                        sql.Identifier(name), sql.Identifier(role)
                    )
                )
            for role in owners.values():
                admin.execute(
                    sql.SQL("GRANT CREATE ON DATABASE {} TO {}").format(
                        sql.Identifier(name), sql.Identifier(role)
                    )
                )
            # pg_restore's schema filter selects objects within the schema, but
            # does not reliably include the namespace entry itself.
            for namespace, role in owners.items():
                admin.execute(
                    sql.SQL("CREATE SCHEMA {} AUTHORIZATION {}").format(
                        sql.Identifier(namespace), sql.Identifier(role)
                    )
                )
        for namespace, label in (("app", "application"), ("brain", "brain")):
            args = [
                str(_binary(binary_dir, "pg_restore")),
                "--no-owner",
                "--no-privileges",
                "--single-transaction",
                "--exit-on-error",
                "--schema=" + namespace,
                "--dbname",
                name,
                str(archive / (label + ".dump")),
            ]
            restored = subprocess.run(
                args,
                check=False,
                env=client_environment(urls[namespace]),
                capture_output=True,
                timeout=300,
            )
            if restored.returncode:
                (archive / (namespace + "-restore-error.log")).write_bytes(restored.stderr)
                raise BackupError("Schema restore failed; details remain in the private archive.")
        with psycopg.connect(target_admin) as admin:
            for namespace, role in owners.items():
                identifier = sql.Identifier(namespace)
                admin.execute(sql.SQL("REVOKE ALL ON SCHEMA {} FROM PUBLIC").format(identifier))
                admin.execute(
                    sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {} FROM PUBLIC").format(identifier)
                )
                admin.execute(
                    sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA {} FROM PUBLIC").format(
                        identifier
                    )
                )
                admin.execute(
                    sql.SQL("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA {} FROM PUBLIC").format(
                        identifier
                    )
                )
                admin.execute(
                    sql.SQL("REVOKE CREATE ON DATABASE {} FROM {}").format(
                        sql.Identifier(name), sql.Identifier(role)
                    )
                )
                # Function EXECUTE is granted globally by PostgreSQL's default;
                # a schema-local REVOKE cannot remove that global default.
                admin.execute(
                    sql.SQL(
                        "ALTER DEFAULT PRIVILEGES FOR ROLE {} "
                        "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
                    ).format(sql.Identifier(role))
                )
                for kind in ("TABLES", "SEQUENCES"):
                    admin.execute(
                        sql.SQL(
                            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA {} "
                            "REVOKE ALL ON " + kind + " FROM PUBLIC"
                        ).format(sql.Identifier(role), identifier)
                    )
            copy_runtime_grants(app, admin, runtime_role)
            admin.execute(
                sql.SQL("GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA app TO {}").format(
                    sql.Identifier(runtime_role)
                )
            )
            actual = fingerprints(admin)
        if actual != expected:
            raise ConsolidationError("Combined database differs from the source snapshots.")
        if (
            schema_digest(target_admin, "app", binary_dir) != app_schema
            or schema_digest(target_admin, "brain", binary_dir) != brain_schema
        ):
            raise ConsolidationError("Combined schema definitions differ from their sources.")
        verify_boundaries(target_admin, runtime, urls["app"], urls["brain"])
        work = archive / "combined-restore-check"
        work.mkdir()
        reports["combined"] = database_backup(
            target_admin, archive / "combined.dump", Path(binary_dir), work
        )
        if reports["combined"]["snapshot"] != expected:
            raise BackupError("Combined backup did not preserve the source snapshots.")
        if (
            namespace_snapshot(fingerprints(app), "app") != app_before
            or namespace_snapshot(fingerprints(brain), "brain") != brain_before
        ):
            raise ConsolidationError("Source records changed during consolidation.")
        return {
            "storage_layout": LAYOUT,
            "admin_url": target_admin,
            "database_url": runtime,
            "migration_url": urls["app"],
            "brain_url": urls["brain"],
            "report": {
                "source_backups_verified": True,
                "combined_backup_verified": True,
                "schema_definitions_preserved": True,
                "source_records_preserved": True,
                "role_boundaries_verified": True,
                "schema_hashes": {"app": app_schema, "brain": brain_schema},
                "text_settings": desired_text,
                "original_application_text_settings": app_text,
                "snapshot": expected,
                "archive": str(archive),
                "activated": False,
            },
        }


def migration_connection(config):
    """Shared layouts require a schema-only migrator, never the cluster admin."""
    if config.get("storage_layout") != LAYOUT:
        return config["admin_url"]
    value = config.get("migration_url")
    if not value:
        raise ConsolidationError("Shared storage requires an application-only migration role.")
    source, target = conninfo_to_dict(config["admin_url"]), conninfo_to_dict(value)
    if any(source.get(k) != target.get(k) for k in ("host", "port", "dbname")) or source.get(
        "user"
    ) == target.get("user"):
        raise ConsolidationError(
            "Application migrations require a separate role in the same database."
        )
    return value


def brain_snapshot(snapshot):
    return {
        key: {name: value for name, value in snapshot[key].items() if name.startswith("brain.")}
        for key in ("tables", "sequences")
    }
