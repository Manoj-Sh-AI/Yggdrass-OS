"""The backup's schema check compares statements, not pg_dump's id-based order."""

from yggdress_app.backup import schema_statements

SOURCE = r"""--
-- PostgreSQL database dump
--
\restrict abc
CREATE TABLE app.links (
    id uuid NOT NULL
);
CREATE TABLE app.notifications (
    id uuid NOT NULL
);
CREATE FUNCTION app.f() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  PERFORM 1;
  RETURN NEW;
END;
$$;
\unrestrict abc
"""


def test_the_same_schema_in_a_different_order_matches():
    reordered = r"""\restrict xyz
CREATE TABLE app.notifications (
    id uuid NOT NULL
);
CREATE FUNCTION app.f() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  PERFORM 1;
  RETURN NEW;
END;
$$;
CREATE TABLE app.links (
    id uuid NOT NULL
);
"""
    assert schema_statements(SOURCE) == schema_statements(reordered)


def test_a_real_difference_is_still_caught():
    changed = SOURCE.replace("app.links (\n    id uuid NOT NULL", "app.links (\n    id uuid")
    assert schema_statements(SOURCE) != schema_statements(changed)


def test_lines_inside_a_function_body_are_not_shuffled_into_a_match():
    """Reordering lines inside one function must not pass: the body is one statement."""
    swapped = SOURCE.replace("  PERFORM 1;\n  RETURN NEW;", "  RETURN NEW;\n  PERFORM 1;")
    assert schema_statements(SOURCE) != schema_statements(swapped)
