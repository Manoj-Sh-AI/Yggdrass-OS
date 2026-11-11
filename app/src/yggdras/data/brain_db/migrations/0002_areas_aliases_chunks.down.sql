-- Roll back 0002. A note keeps its first secondary area as also_area; further ones, alias
-- order and chunk parents are lost (reload from the markdown to get them back).

ALTER TABLE brain.notes DROP CONSTRAINT IF EXISTS notes_parent_not_self;
ALTER TABLE brain.notes DROP COLUMN IF EXISTS parent_slug;
ALTER TABLE brain.aliases DROP COLUMN IF EXISTS ord;

ALTER TABLE brain.notes ADD COLUMN also_area text
    REFERENCES brain.areas (area_code) ON DELETE RESTRICT;
UPDATE brain.notes n SET also_area = (
    SELECT a.area_code FROM brain.note_areas a
    WHERE a.slug = n.slug AND NOT a.is_primary ORDER BY a.ord LIMIT 1
);

DROP TRIGGER notes_one_primary_area ON brain.notes;
DROP TABLE brain.note_areas;
DROP FUNCTION brain.check_primary_area();
