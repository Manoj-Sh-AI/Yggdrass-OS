# Vendored files

| File | Source | Version | Integrity | Licence |
|---|---|---|---|---|
| `vis-network-9.1.6.min.js` | `https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js` | 9.1.6 | `sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1`, the hash Graphify 0.9.95 pins | Apache-2.0 or MIT (dual, see the file header) |
| `three-0.185.1.cjs` | `https://unpkg.com/three@0.185.1/build/three.cjs` | 0.185.1 (the last release with a full CommonJS build; 3d-force-graph needs ≥ 0.179) | `sha384-cYcCosS5mKaWwc2fiRx4UsDXJr/hCkAPQXX04gEuEueyFAzkbkqkyP85vR9nyKF4` | MIT, `three-LICENSE.txt` |
| `3d-force-graph-1.80.1.min.js` | `https://unpkg.com/3d-force-graph@1.80.1/dist/3d-force-graph.min.js` | 1.80.1 | `sha384-i98VDQKdpyVrtyuFn0fjUWJBLBmxnqHqOANcvYe9HLJUgT2wPixa4ZkLd7Dh3VEk` | MIT, `3d-force-graph-LICENSE.txt` |
| `inter-latin-400-normal.woff2`, `inter-latin-600-normal.woff2` | `https://cdn.jsdelivr.net/npm/@fontsource/inter@5.0.16/files/` | Inter, Fontsource 5.0.16, Latin subset | `sha384-fh/R5bWIGwMIs5kzn3aCWuUjbYvaxfc2SGWUTGTtkedhrySWrY8datYfSK2QcZHL`, `sha384-lI+hrOImxNsIljMZ+LxBmjTPRJCqvHKeOmTiKCfLU1X6p6NCfvF38SRH8pIuu2XO` | SIL Open Font License 1.1, `Inter-LICENSE.txt` |

Used by `viewer.py` so `graph.html` works offline: vis-network draws the 2D map; three.js and 3d-force-graph draw the 3D view, loaded only when 3D is chosen (three's CommonJS build is wrapped at copy time so it sets `window.THREE`, which 3d-force-graph then uses); Inter sets the labels. The viewer checks each file's hash before every copy, and `.gitattributes` keeps git from changing their bytes. Replace a file only deliberately, with its new hash.
