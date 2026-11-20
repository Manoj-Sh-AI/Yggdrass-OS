# Connector directory: apps connected by signing in

Date: 2026-11-18. Owner choices:
- At least the 20 most useful apps.
- Google is reached through its official remote MCP servers.
- Privacy: "tools only, nothing auto-saved".

Amends `connector-skill-catalogs.md`: the Connectors page was an empty list of a local file.

**What.** A reviewed, built-in directory (`app/api/src/yggdress_app/connector_directory.py`)
of 21 apps reachable through their vendors' hosted MCP servers, plus a Microsoft 365 card
that says plainly it is not available yet. Each app is connected by signing in from the
laptop. File entries in `connectors.json` still work and show as "Your own".

**How apps were chosen.** Every URL was checked on 2026-11-18 with a read-only GET of its
OAuth metadata (RFC 9728 / RFC 8414). No personal data was sent.
- **One click** (the server allows dynamic client registration): Notion, Jira & Confluence
  (Atlassian), Airtable, Todoist, Linear, ClickUp, monday.com, Dropbox, Figma, Canva,
  Miro and Zapier.
- **Needs Manoj's own OAuth app** (ID and secret from `.env`, by variable name): Gmail,
  Google Calendar, Google Drive, Google Docs, Google Sheets, Slack, Asana, Box and GitHub.
  Google also needs enrollment in its Workspace Developer Preview Program.
- **Not available:** Microsoft has no official hosted server. Zapier can bridge Outlook
  meanwhile.

**Sign-in.** `connector_auth.py` follows the MCP authorization spec: discovery, then
registration or the env client, then PKCE S256 and the `resource` parameter. Each `state`
is one-time and expires after 10 minutes. The browser returns to
`/api/backend/connectors/callback`, which shows a plain page. No session cookie is needed
there, because the sign-in often finishes in the system browser.

**Tokens.** Tokens are kept in a Fernet-encrypted vault under
`%LOCALAPPDATA%/Yggdras/connectors` (`YGGDRESS_CONNECTOR_STORE`). They are never in
OneDrive, the repo, the database, a response or a log. Disconnecting revokes the token at
the app when the app supports it. The vault's key file sits beside the vault, so this
protects against copying the vault alone, not against someone with the laptop account.
That is the same trust boundary as `runtime.json`.

**Tools.** On connect, the app's `tools/list` is read once and cached in the vault.
Tools register under the app's skill domain and stay locked until a skill in that domain
loads.
- Tools marked read-only run during a task. Any other tool becomes an approval card, and
  an approved card calls the app.
- Results go back only to the task in progress. The run log keeps tool names, never
  content (tested).
- Gmail is requested with read and compose scopes only. Google's server has no send tool.

**Limits on purpose.**
- Connecting, disconnecting and switching stay on the laptop. The phone reads the directory.
- Most apps' domains (documents, files, projects, code, design, automation…) have no skill
  yet, so those apps connect but Yggdras won't call them until a reviewed skill names
  their domain. Gmail (email) and Google Calendar (calendar) are already used by
  existing skills.

**Why the official MCP SDK.** It implements the Streamable HTTP protocol and keeps up
with the spec. A real local MCP server in the tests covers it end to end.

**Logos (added the same day, at Manoj's request).** Each card shows the app's logo so it is
recognisable at a glance.
- **Source.** Logos come from Simple Icons 16.38 (CC0). They are bundled locally: SVG paths
  on the web in `app/web/src/lib/app-logos.ts`, and 96 px PNGs on the phone in
  `app/mobile/assets/app-logos`. The page never loads a logo from another site.
- **Letter tiles.** Slack, Canva, monday.com and Microsoft asked Simple Icons to remove
  their marks, so those four get a letter tile in the brand colour instead of a copied logo.
- **Trademarks.** Brand names and logos belong to their owners. They are used only to
  identify each app.
