-- 0002: a note in any number of areas (note_areas), aliases in written order (ord), and a
-- chunk's parent (notes.parent_slug).

-- Every note has exactly one primary area, equal to notes.area_code, and any number of
-- secondary areas in written order (ord: 0 for the primary, then 1, 2, ...).
CREATE TABLE brain.note_areas (
    slug       text NOT NULL REFERENCES brain.notes (slug) ON DELETE CASCADE,
    area_code  text NOT NULL REFERENCES brain.areas (area_code) ON DELETE RESTRICT,
    is_primary boolean NOT NULL,
    ord        integer NOT NULL,
    PRIMARY KEY (slug, area_code)
);
CREATE UNIQUE INDEX note_areas_one_primary_idx ON brain.note_areas (slug) WHERE is_primary;
CREATE INDEX note_areas_area_code_idx ON brain.note_areas (area_code);

INSERT INTO brain.note_areas (slug, area_code, is_primary, ord)
    SELECT slug, area_code, true, 0 FROM brain.notes;
INSERT INTO brain.note_areas (slug, area_code, is_primary, ord)
    SELECT slug, also_area, false, 1 FROM brain.notes
    WHERE also_area IS NOT NULL AND also_area <> area_code;
ALTER TABLE brain.notes DROP COLUMN also_area;

-- Checked at commit, so a note and its areas can be written in one transaction.
CREATE FUNCTION brain.check_primary_area() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    s text := CASE WHEN TG_OP = 'DELETE' THEN OLD.slug ELSE NEW.slug END;
    primaries integer;
    primary_code text;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM brain.notes WHERE slug = s) THEN
        RETURN NULL;  -- the note itself is gone
    END IF;
    SELECT count(*), min(area_code) INTO primaries, primary_code
        FROM brain.note_areas WHERE slug = s AND is_primary;
    IF primaries <> 1 THEN
        RAISE EXCEPTION 'note % has % primary areas; it needs exactly one', s, primaries
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    IF primary_code <> (SELECT area_code FROM brain.notes WHERE slug = s) THEN
        RAISE EXCEPTION 'note %: primary area % is not notes.area_code', s, primary_code
            USING ERRCODE = 'integrity_constraint_violation';
    END IF;
    RETURN NULL;
END $$;

CREATE CONSTRAINT TRIGGER notes_one_primary_area
    AFTER INSERT OR UPDATE OF area_code ON brain.notes
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION brain.check_primary_area();
CREATE CONSTRAINT TRIGGER note_areas_one_primary_area
    AFTER INSERT OR UPDATE OR DELETE ON brain.note_areas
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION brain.check_primary_area();

-- Aliases in the order they are written.
ALTER TABLE brain.aliases ADD COLUMN ord integer NOT NULL DEFAULT 0;
ALTER TABLE brain.aliases ALTER COLUMN ord DROP DEFAULT;

-- A chunk's parent source. Deferred, so chunks and parents load in any order.
ALTER TABLE brain.notes
    ADD COLUMN parent_slug text
        CONSTRAINT notes_parent_slug_fkey REFERENCES brain.notes (slug)
        ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT notes_parent_not_self CHECK (parent_slug <> slug);
