"""What Manoj is looking at, sent by the side chat (UI brief Phase E). The server is the
authority, never the client: the payload is validated, capped, and anything marked
restricted is reduced to its id again here, whatever the client sent. Only ids, labels
and a few whitelisted scalar fields reach the model; records are re-read by tools
under the session's own permissions.

Resolving "this" is a rule, not a prompt instruction (brief E): the selection, else the
focused item, else the only visible item, else the model must ask which one.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_VISIBLE = 25
FIELD_KEYS = frozenset({"starts", "ends", "due", "status", "area"})
RESTRICTED_LABEL = "Sensitive note"


class Ref(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: Literal["task", "doc", "view", "selection", "file", "event"]
    id: str = Field(min_length=1, max_length=200)
    label: str = Field(default="", max_length=200)
    origin: Literal["ambient", "mention", "selection"] = "ambient"
    sensitivity: Literal["normal", "restricted"] = "normal"
    fields: dict[str, str | int | float | bool] = Field(default_factory=dict)

    def safe(self) -> Ref:
        if self.sensitivity == "restricted":
            return Ref(kind=self.kind, id=self.id, label=RESTRICTED_LABEL, origin=self.origin,
                       sensitivity="restricted")  # fmt: skip
        fields = {
            k: (v[:80] if isinstance(v, str) else v)
            for k, v in self.fields.items()
            if k in FIELD_KEYS
        }
        return self.model_copy(update={"fields": fields})


class Selection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = Field(default="", max_length=2000)
    refs: list[Ref] = Field(default_factory=list, max_length=MAX_VISIBLE)


class PageContext(BaseModel):
    model_config = ConfigDict(extra="ignore")
    route: str = Field(default="", max_length=300)
    surface: str = Field(default="page", max_length=60)
    focus: Ref | None = None
    visible: list[Ref] = Field(default_factory=list)
    selection: Selection | None = None
    capabilities: list[str] = Field(default_factory=list, max_length=30)


def parse(raw: object) -> PageContext | None:
    """A page context made safe, or None when absent or malformed (a bad context never
    blocks the message; it is simply not used)."""
    if not isinstance(raw, dict):
        return None
    try:
        page = PageContext.model_validate(raw)
    except ValidationError:
        return None
    restricted = page.selection is not None and any(
        r.sensitivity == "restricted" for r in page.selection.refs
    )
    return page.model_copy(update={
        "focus": page.focus.safe() if page.focus else None,
        "visible": [r.safe() for r in page.visible[:MAX_VISIBLE]],
        "selection": None if page.selection is None else Selection(
            text="" if restricted else page.selection.text,
            refs=[r.safe() for r in page.selection.refs]),
    })  # fmt: skip


def this(page: PageContext) -> Ref | None:
    """The referent of "this": selection, else focus, else the only visible item."""
    if page.selection and page.selection.refs:
        return page.selection.refs[0]
    if page.focus and page.focus.kind != "view":
        return page.focus
    if len(page.visible) == 1:
        return page.visible[0]
    return None


def _line(ref: Ref) -> str:
    extra = ", ".join(f"{k}={v}" for k, v in ref.fields.items())
    hidden = " (sensitive: content not shared)" if ref.sensitivity == "restricted" else ""
    return f"- {ref.kind} {ref.id}: {ref.label}{hidden}{f' [{extra}]' if extra else ''}"


def describe(page: PageContext) -> str:
    """The system-prompt note for this request: what is on screen, and the rule for
    "this". Ids and labels only."""
    target = this(page)
    lines = [f"Manoj is looking at {page.surface} ({page.route})."]
    if page.focus:
        lines.append(f"In focus: {_line(page.focus)[2:]}")
    if page.selection and page.selection.text:
        lines.append(f"Selected text: {page.selection.text!r}")
    if page.visible:
        lines.append("Also on screen:")
        lines.extend(_line(r) for r in page.visible if not page.focus or r.id != page.focus.id)
    lines.append(
        f'"This" means {target.kind} {target.id} ({target.label}).' if target
        else 'If he says "this" or "that", ask which item he means; do not guess.'
    )  # fmt: skip
    lines.append("Never act on a sensitive item's content; ask him to open it first.")
    return "\n".join(lines)
