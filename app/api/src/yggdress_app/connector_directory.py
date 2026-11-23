"""The built-in connector directory: apps Manoj can connect with one sign-in.

Reviewed code, like the skills: it ships with the application and changes through pull
requests. Every URL here was checked on 2026-11-18 with a read-only GET of the server's
OAuth metadata (rationale/decisions/connector-directory.md).

Auth kinds:
- `dcr`: the server lets Yggdras register itself (dynamic client registration). One click.
- `client`: the vendor needs an OAuth app Manoj creates once; its ID and secret come from
  the environment, by the variable NAMES listed here (never values in code).
- `unavailable`: no official hosted MCP server exists yet; the card says so.

`domain` is the skill domain whose skills unlock the app's tools (tool_gate.py). Writes
always stop at an approval card, whatever the domain.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class App:
    id: str
    title: str
    group: str
    description: str
    domain: str
    url: str = ""
    auth: str = "dcr"  # dcr | client | unavailable
    scopes: tuple[str, ...] = ()
    client_env: tuple[str, ...] = ()  # (CLIENT_ID name, CLIENT_SECRET name)
    extra: dict = field(default_factory=dict)  # extra authorize parameters
    setup: str = ""  # one line on what Manoj must do first


GOOGLE_ENV = ("YGGDRAS_GOOGLE_CLIENT_ID", "YGGDRAS_GOOGLE_CLIENT_SECRET")
GOOGLE_SETUP = (
    "Join Google's Workspace Developer Preview Program, enable this app's API and its MCP API "
    "in a Google Cloud project, and create a Desktop OAuth client marked for AI agents."
)
GOOGLE_EXTRA = {"access_type": "offline", "prompt": "consent"}


def _client(prefix: str) -> tuple[str, str]:
    return (f"YGGDRAS_{prefix}_CLIENT_ID", f"YGGDRAS_{prefix}_CLIENT_SECRET")


def _google(id_, title, description, domain, host, scopes) -> App:
    return App(id_, title, "Google", description, domain, f"https://{host}.googleapis.com/mcp/v1",
               "client", scopes, GOOGLE_ENV, GOOGLE_EXTRA, GOOGLE_SETUP)  # fmt: skip


APPS: tuple[App, ...] = (
    _google(
        "gmail",
        "Gmail",
        "Search and read mail, labels and drafts. It cannot send.",
        "email",
        "gmailmcp",
        (
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.compose",
        ),
    ),
    _google(
        "google-calendar",
        "Google Calendar",
        "Read your calendars, find free time, and propose events.",
        "calendar",
        "calendarmcp",
        ("https://www.googleapis.com/auth/calendar",),
    ),
    _google(
        "google-drive",
        "Google Drive",
        "Search and read files in your Drive.",
        "files",
        "drivemcp",
        ("https://www.googleapis.com/auth/drive.readonly",),
    ),
    _google(
        "google-docs",
        "Google Docs",
        "Read and edit your documents.",
        "documents",
        "docsmcp",
        (
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive.readonly",
        ),
    ),
    _google(
        "google-sheets",
        "Google Sheets",
        "Read and update your spreadsheets.",
        "spreadsheets",
        "sheetsmcp",
        (
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ),
    ),
    App(
        "notion",
        "Notion",
        "Notes & docs",
        "Search, read and update pages and databases.",
        "documents",
        "https://mcp.notion.com/mcp",
    ),
    App(
        "atlassian",
        "Jira & Confluence",
        "Notes & docs",
        "Issues, projects and team pages from your Atlassian sites.",
        "projects",
        "https://mcp.atlassian.com/v2/mcp",
    ),
    App(
        "airtable",
        "Airtable",
        "Notes & docs",
        "Read and update your bases and records.",
        "spreadsheets",
        "https://mcp.airtable.com/mcp",
    ),
    App(
        "todoist",
        "Todoist",
        "Tasks & projects",
        "Your tasks, projects and due dates.",
        "tasks-external",
        "https://ai.todoist.net/mcp",
    ),
    App(
        "linear",
        "Linear",
        "Tasks & projects",
        "Issues, cycles and projects.",
        "projects",
        "https://mcp.linear.app/mcp",
    ),
    App(
        "clickup",
        "ClickUp",
        "Tasks & projects",
        "Tasks, lists and docs.",
        "projects",
        "https://mcp.clickup.com/mcp",
    ),
    App(
        "monday",
        "monday.com",
        "Tasks & projects",
        "Boards, items and updates.",
        "projects",
        "https://mcp.monday.com/mcp",
    ),
    App(
        "asana",
        "Asana",
        "Tasks & projects",
        "Tasks, projects and goals.",
        "projects",
        "https://mcp.asana.com/v2/mcp",
        "client",
        (),
        _client("ASANA"),
        setup="Create an Asana OAuth app with the redirect address shown below.",
    ),
    App(
        "slack",
        "Slack",
        "Messages",
        "Search channels and messages; drafts need approval.",
        "messages",
        "https://mcp.slack.com/mcp",
        "client",
        ("search:read.public", "channels:history", "users:read"),
        _client("SLACK"),
        setup="Create a Slack app with the redirect address shown below.",
    ),
    App(
        "dropbox",
        "Dropbox",
        "Files",
        "Search and read your files.",
        "files",
        "https://mcp.dropbox.com/mcp",
    ),
    App(
        "box",
        "Box",
        "Files",
        "Search and read your files.",
        "files",
        "https://mcp.box.com",
        "client",
        (),
        _client("BOX"),
        setup="Create a Box OAuth app with the redirect address shown below.",
    ),
    App(
        "github",
        "GitHub",
        "Code",
        "Repositories, issues and pull requests.",
        "code",
        "https://api.githubcopilot.com/mcp/",
        "client",
        ("repo", "read:user"),
        _client("GITHUB"),
        setup="Create a GitHub OAuth app with the redirect address shown below.",
    ),
    App(
        "figma",
        "Figma",
        "Design",
        "Read designs and their structure.",
        "design",
        "https://mcp.figma.com/mcp",
    ),
    App(
        "canva",
        "Canva",
        "Design",
        "Find and create designs.",
        "design",
        "https://mcp.canva.com/mcp",
    ),
    App(
        "miro", "Miro", "Design", "Read and add to your boards.", "design", "https://mcp.miro.com/"
    ),
    App(
        "zapier",
        "Zapier",
        "Automation",
        "Reach thousands more apps through your Zapier actions, Outlook included.",
        "automation",
        "https://mcp.zapier.com/api/mcp/mcp",
    ),
    App(
        "microsoft-365",
        "Microsoft 365",
        "Microsoft",
        "Outlook mail and calendar, OneDrive and Teams. Microsoft has no official hosted MCP "
        "server yet; Zapier can bridge Outlook meanwhile.",
        "email",
        auth="unavailable",
    ),
)

BY_ID = {app.id: app for app in APPS}
GROUPS = tuple(dict.fromkeys(app.group for app in APPS))
