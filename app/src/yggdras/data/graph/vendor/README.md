# Vendored files

| File | Source | Version | Integrity | Licence |
|---|---|---|---|---|
| `vis-network-9.1.6.min.js` | `https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js` | 9.1.6 | `sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1`, the hash Graphify 0.9.95 pins | Apache-2.0 or MIT (dual, see the file header) |
| `inter-latin-400-normal.woff2`, `inter-latin-600-normal.woff2` | `https://cdn.jsdelivr.net/npm/@fontsource/inter@5.0.16/files/` | Inter, Fontsource 5.0.16, Latin subset | `sha384-fh/R5bWIGwMIs5kzn3aCWuUjbYvaxfc2SGWUTGTtkedhrySWrY8datYfSK2QcZHL`, `sha384-lI+hrOImxNsIljMZ+LxBmjTPRJCqvHKeOmTiKCfLU1X6p6NCfvF38SRH8pIuu2XO` | SIL Open Font License 1.1, `Inter-LICENSE.txt` |

Used by `viewer.py` so `graph.html` works offline: vis-network draws the map, Inter sets its labels. The viewer checks each file's hash before every copy, and `.gitattributes` keeps git from changing their bytes. Replace a file only deliberately, with its new hash.
