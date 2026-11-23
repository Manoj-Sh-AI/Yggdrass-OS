# Connector and skill catalog pages

Date: 2026-11-18. Owner choices: connectors "list + on/off", skills "list + read",
phone "native pages", phone access "read only".

Web (and so the desktop window) gets `/connectors` and `/skills`; the phone gets two native
screens under More. Both use the same API.

- **Connectors** use the existing `GET/POST /v1/yggdras/connectors`. Adding a connector
  stays an edit of the local `connectors.json`, so no secret or command is typed into a page.
- **Skills** get new read-only routes: `GET /v1/yggdras/skills` (frontmatter cards) and
  `GET /v1/yggdras/skills/{name}` (instructions). Skills are reviewed code and change
  through pull requests. The detail route reads the file directly, so browsing does not
  count as a task loading the skill.
- **Phone rights.** Phone sessions stay blocked from `/v1/brain/*` and `/v1/yggdras/*`
  except these three GETs. Switching a connector changes what Yggdras can do, so like
  approving a card it stays on the laptop (planning/lia-and-connector.md: the phone may ask
  and offer, never approve). The phone shows the switch state, disabled.
- Each page shows how the two meet: a connector lists the skills whose domains unlock its
  tools, and a skill lists the connectors in its domains.
