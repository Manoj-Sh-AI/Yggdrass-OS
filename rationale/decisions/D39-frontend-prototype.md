# D39 — isolated browser prototype

Approved by Manoj in chat on 2026-11-08.

Keep Next.js in `app/web`, independent from the existing Python package. Use a typed async repository backed by versioned localStorage and synthetic content. This trades server durability and multi-device sync for speed, simplicity and safe isolation from real memory. Keep domain concepts compatible with the Markdown brain. Revisit when the prototype's connected capture/search slice is approved.

Use Open-Meteo only for location weather, with explicit opt-in geolocation. Do not send notes or task content. Keep scenery assets local, derive 24 variants from a master, select one current image, and crossfade after preload. This trades asset volume for consistent mood and predictable rendering. Live weather is optional; manual scenes and clock fallback work offline.

Vercel configuration is provided; deployment and real authentication are outside this local delivery. Simulated Lia must always be labeled.
