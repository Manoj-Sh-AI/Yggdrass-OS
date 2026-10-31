# Vendored files

| File | Source | Version | Integrity | Licence |
|---|---|---|---|---|
| `vis-network-9.1.6.min.js` | `https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js` | 9.1.6 | `sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1`, the hash Graphify 0.9.95 pins | Apache-2.0 or MIT (dual, see the file header) |

Used by `viewer.py` so Graphify's `graph.html` works offline. The viewer checks the hash before every copy, and `.gitattributes` keeps git from changing its line endings. Replace it only together with a Graphify upgrade (D32).
