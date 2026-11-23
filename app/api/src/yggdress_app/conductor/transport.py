"""HTTP for the conductor: assistant-ui's Assistant Transport protocol [cited].

- POST /v1/assistant            commands (add-message, regenerate, cancel-run,
                                 answer-approval); streams
- POST /v1/assistant/resume-state?conversation=ID   {state, runId} of an unfinished run, or 204
- POST /v1/assistant/resume     {runId: "<run>@<seq>"}; streams the rest of that run
- GET  /v1/assistant/threads/{conversation_id}      the thread state to render on load

Client state: {"conversationId": str|None, "messages": [Message]} where a message is
{"id", "role": "user", "text"} or {"id", "role": "assistant", "text", "seq", "run"}.
An assistant message answered more than once ("Try again") also has
"branches": [{"id", "seq", "run"}, ...], the first answer first; the client shows one
and a `< 2/3 >` picker. A streamed run is mirrored from the event log into
assistant-stream's state under its path (["messages", i, "run"] or
["messages", i, "branches", k, "run"]), so the client applies exactly the logged ops.
"""

from __future__ import annotations

import asyncio
import copy
import re
from typing import Any

from assistant_stream import RunController, create_run
from assistant_stream.serialization import AssistantTransportResponse
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from .log import Op, RunNotFound, apply, run_uuid
from .orchestrator import Conductor
from .page import parse as parse_page
from .policy import PolicySettings
from .state import RunState

# Short waits: a waiting thread is released quickly when a client goes away.
TAIL_WAIT_SECONDS = 2.0
STOP_TAILING = frozenset({"completed", "failed", "cancelled", "interrupted"})


def settled(run: dict[str, Any]) -> bool:
    """Nothing more will happen without Manoj: the run ended, or it is waiting and every
    step still in progress is waiting on one of his approval cards (parallel steps that
    are still working keep the stream open)."""
    if run.get("status") in STOP_TAILING:
        return True
    if run.get("status") != "waiting":
        return False
    steps = (run.get("plan") or {}).get("steps") or []
    working = {s["id"] for s in steps if s.get("status") == "in_progress"}
    awaiting = {
        t.get("step_id") for t in run.get("tools", []) if t.get("state") == "approval-requested"
    }
    return working <= awaiting


class Command(BaseModel):
    model_config = ConfigDict(extra="allow")
    type: str


class AssistantRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    commands: list[Command] = Field(default_factory=list, max_length=20)
    state: dict[str, Any] | None = None
    conversationId: str | None = None
    model: str = ""


class ResumeRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    runId: str = Field(max_length=100)


def empty_thread(conversation_id: str | None = None) -> dict[str, Any]:
    return {"conversationId": conversation_id, "messages": []}


def valid_id(value: Any, status: int = 422) -> str:
    try:
        return run_uuid(str(value))
    except (ValueError, TypeError, AttributeError) as error:
        raise HTTPException(status, "That id is not valid.") from error


IMAGE_DATA = re.compile(r"^data:(image/(?:png|jpeg|webp|gif));base64,([A-Za-z0-9+/=]+)$")
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def message_parts(command: Command) -> tuple[str, list[dict[str, Any]]]:
    """The text of an add-message command and its images as model image blocks.
    Text attachments arrive as text parts (assistant-ui's text adapter)."""
    message = (command.model_extra or {}).get("message") or {}
    parts = message.get("parts") or []
    if not isinstance(parts, list):
        raise HTTPException(422, "The message is malformed.")
    text = "\n".join(
        p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text"
    ).strip()
    images = []
    for part in parts:
        if not isinstance(part, dict) or part.get("type") != "image":
            continue
        match = IMAGE_DATA.match(str(part.get("image", "")))
        if not match or len(match.group(2)) * 3 // 4 > MAX_IMAGE_BYTES:
            raise HTTPException(422, "Images must be PNG, JPEG, WebP or GIF, up to 5 MB.")
        images.append({"type": "image", "source": {"type": "base64",
                       "media_type": match.group(1), "data": match.group(2)}})  # fmt: skip
    if len(images) > MAX_IMAGES:
        raise HTTPException(422, f"Attach up to {MAX_IMAGES} images.")
    if images and not text:
        text = "(image attached)"
    if not text or len(text) > 100_000:
        raise HTTPException(422, "Write a message (up to 100,000 characters).")
    return text, images


def run_path(messages: list[dict[str, Any]], run_id: str) -> list | None:
    """Where a run lives in the client state: a message of its own or a branch."""
    for i, message in enumerate(messages):
        if message.get("id") == run_id:
            return ["messages", i, "run"]
        for k, branch in enumerate(message.get("branches") or []):
            if branch.get("id") == run_id:
                return ["messages", i, "branches", k, "run"]
    return None


def put(state: dict[str, Any], path: list, value: Any) -> None:
    node: Any = state
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


def add_branch(messages: list[dict[str, Any]], root_id: str, run: RunState) -> list | None:
    """Append a new answer to the root's group; the path of its run, or None."""
    for i, message in enumerate(messages):
        if message.get("id") == root_id and message.get("role") == "assistant":
            branches = message.get("branches") or [
                {"id": root_id, "seq": message.get("seq", 0), "run": message.get("run")}
            ]
            branches.append({"id": run.run_id, "seq": 0, "run": run.model_dump(mode="json")})
            message["branches"] = branches
            return ["messages", i, "branches", len(branches) - 1, "run"]
    return None


def assistant_message(state: RunState, seq: int) -> dict[str, Any]:
    return {"id": state.run_id, "role": "assistant", "text": "", "seq": seq,
            "run": state.model_dump(mode="json")}  # fmt: skip


class Mirror:
    """Relays logged ops into a RunController's state under a path prefix, keeping a
    local copy so a list append is sent as a whole-list set (assistant-stream's proxy
    is not relied on to grow lists)."""

    def __init__(self, controller: RunController, prefix: list, run: dict[str, Any]):
        self.controller, self.prefix, self.local = controller, prefix, copy.deepcopy(run)

    def relay(self, op: Op) -> None:
        *parents, last = op.path
        node: Any = self.local
        for key in parents:
            node = node[key]
        grows_list = op.op == "set" and isinstance(node, list) and last == len(node)
        apply(self.local, op)
        if op.op == "append-text":
            self.controller.append_state_text([*self.prefix, *op.path], op.value)
            return
        if grows_list:
            self._set([*self.prefix, *parents], copy.deepcopy(node))
        else:
            self._set([*self.prefix, *op.path], copy.deepcopy(op.value))

    def _set(self, path: list, value: Any) -> None:
        target = self.controller.state
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value


async def tail(controller: RunController, conductor: Conductor, run_id: str, after: int,
               prefix: list, run: dict[str, Any]) -> None:  # fmt: skip
    """Stream a run's events after `after` until it stops or the client goes away.
    A client leaving never stops the run; it keeps executing server-side."""
    mirror = Mirror(controller, prefix, run)
    log = conductor.log
    seq = after
    while not controller.is_cancelled:
        events = await asyncio.to_thread(log.events, run_id, seq)
        for seq, op in events:
            mirror.relay(op)
        if events:
            controller.flush()
            continue
        if settled(mirror.local):
            return
        await asyncio.to_thread(log.bus.wait, run_id, seq, TAIL_WAIT_SECONDS)


def conductor_router(conductor: Conductor, session) -> APIRouter:
    router = APIRouter(prefix="/v1/assistant", dependencies=[Depends(session)])

    @router.post("")
    async def assistant(body: AssistantRequest):
        state = body.state if isinstance(body.state, dict) else empty_thread()
        if not isinstance(state.get("messages"), list):
            state["messages"] = []
        start_text, images, answered, again = None, [], None, None
        for command in body.commands:
            extra = command.model_extra or {}
            if command.type == "add-message":
                start_text, images = message_parts(command)
            elif command.type == "regenerate":
                again = valid_id(extra.get("runId"))
            elif command.type == "cancel-run":
                conductor.cancel(valid_id(extra.get("runId")))
            elif command.type == "answer-approval":
                run_id = valid_id(extra.get("runId"))
                _, before = await asyncio.to_thread(conductor.log.snapshot, run_id)
                if await asyncio.to_thread(conductor.answer_approval, {**extra, "runId": run_id}):
                    answered = (run_id, before)
        if again and start_text is None:
            return await regenerate(conductor, state, again, body.model)
        if start_text is None and answered:
            return continue_after_answer(conductor, state, *answered)
        if start_text is None:
            return Response(status_code=204)
        conversation = body.conversationId or state.get("conversationId")
        conversation = valid_id(conversation) if conversation else None
        page = parse_page((body.model_extra or {}).get("pageContext"))
        run = await asyncio.to_thread(
            conductor.start, start_text, conversation, body.model, images, page
        )

        async def stream(controller: RunController):
            controller.state["conversationId"] = run.conversation_id
            messages = list(state["messages"])
            messages.append({"id": f"user-{run.run_id}", "role": "user", "text": start_text})
            messages.append(assistant_message(run, 0))
            controller.state["messages"] = messages
            prefix = ["messages", len(messages) - 1, "run"]
            await tail(controller, conductor, run.run_id, 0, prefix, messages[-1]["run"])

        return AssistantTransportResponse(create_run(stream, state=state))

    @router.post("/resume-state")
    async def resume_state(conversation: str = Query(min_length=1, max_length=64)):
        thread = await asyncio.to_thread(thread_state, conductor, valid_id(conversation))
        for message in reversed(thread["messages"]):
            for holder in [*(message.get("branches") or [])[::-1], message]:
                run = holder.get("run")
                if run and run["status"] == "running":
                    return {"state": thread, "runId": f"{run['run_id']}@{holder['seq']}"}
        return Response(status_code=204)

    @router.post("/resume")
    async def resume(body: ResumeRequest):
        run_text, _, seq_text = body.runId.partition("@")
        run_id = valid_id(run_text, 404)
        if not seq_text.isdigit():
            raise HTTPException(404, "That run is not available.")
        seq = int(seq_text)
        try:
            thread, path, base = await asyncio.to_thread(resume_point, conductor, run_id, seq)
        except RunNotFound as error:
            raise HTTPException(404, "That run is not available.") from error

        async def stream(controller: RunController):
            await tail(controller, conductor, run_id, seq, path, base)

        # The server-side state starts as the client has it: the run as of `seq`.
        return AssistantTransportResponse(create_run(stream, state=thread))

    @router.get("/policy")
    async def get_policy():
        settings = await asyncio.to_thread(conductor.policy_store.get)
        return {"denyRules": settings.deny_rules, "autoPolicy": settings.auto_policy}

    @router.put("/policy")
    async def put_policy(body: PolicyBody):
        settings = PolicySettings(deny_rules=body.denyRules, auto_policy=body.autoPolicy)
        await asyncio.to_thread(conductor.policy_store.put, settings)
        return {"denyRules": settings.deny_rules, "autoPolicy": settings.auto_policy}

    @router.get("/threads/{conversation_id}")
    async def thread(conversation_id: str):
        return await asyncio.to_thread(thread_state, conductor, valid_id(conversation_id, 404))

    return router


class PolicyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    denyRules: str = Field(default="", max_length=4000)
    autoPolicy: str = Field(default="", max_length=4000)


def continue_after_answer(conductor: Conductor, state: dict, run_id: str, before: int):
    """After Manoj answers an approval card, stream the rest of that run. The client's
    copy may be behind (parallel steps kept writing), so the run is rebuilt exactly as of
    `before` and replaces it; the stream then continues from there."""
    path = run_path(state.get("messages") or [], run_id)
    if path is None:
        return Response(status_code=204)

    async def stream(controller: RunController):
        base = await asyncio.to_thread(rebuild, conductor, run_id, before)
        put(controller.state, path, copy.deepcopy(base))
        await tail(controller, conductor, run_id, before, path, base)

    return AssistantTransportResponse(create_run(stream, state=state))


async def regenerate(conductor: Conductor, state: dict, run_id: str, model: str):
    """Try again on an answer: a sibling run, streamed into the root's branches."""
    try:
        run = await asyncio.to_thread(conductor.branch, run_id, model)
    except RunNotFound as error:
        raise HTTPException(404, "That answer is not available.") from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error

    async def stream(controller: RunController):
        messages = copy.deepcopy(state.get("messages") or [])
        path = add_branch(messages, run.branch_of or run_id, run)
        if path is None:  # the client's copy lacks the root: send the whole thread
            thread = await asyncio.to_thread(thread_state, conductor, run.conversation_id or "")
            messages = thread["messages"]
            path = run_path(messages, run.run_id)
        controller.state["conversationId"] = run.conversation_id
        controller.state["messages"] = messages
        node: Any = {"messages": messages}  # the plain copy: the controller's is a proxy
        for key in path[:-1]:
            node = node[key]
        await tail(controller, conductor, run.run_id, 0, path, node[path[-1]])

    return AssistantTransportResponse(create_run(stream, state=state))


def rebuild(conductor: Conductor, run_id: str, seq: int) -> dict[str, Any]:
    """The run as it was after `seq` (start state + the first `seq` ops)."""
    state, _ = conductor.log.snapshot(run_id)
    start = RunState(
        run_id=state.run_id, conversation_id=state.conversation_id, model=state.model
    ).model_dump(mode="json")
    for _, op in conductor.log.events(run_id, 0, limit=seq) if seq else []:
        apply(start, op)
    return start


def resume_point(conductor: Conductor, run_id: str, seq: int) -> tuple[dict, list, dict]:
    state, _ = conductor.log.snapshot(run_id)
    thread = thread_state(conductor, state.conversation_id)
    base = rebuild(conductor, run_id, seq)
    path = run_path(thread["messages"], run_id)
    if path is None:
        raise RunNotFound(run_id)
    put(thread, path, copy.deepcopy(base))
    put(thread, [*path[:-1], "seq"], seq)
    return thread, path, base


def thread_state(conductor: Conductor, conversation_id: str) -> dict[str, Any]:
    """The whole conversation as client state: plain chat messages (the previous chat,
    the phone) and one user + assistant pair per conductor run, merged by time."""
    requests = conductor.log.requests_for(conversation_id)
    timeline: list[tuple[Any, int, list[dict[str, Any]]]] = []
    for message in conductor.history.plain_messages(conversation_id):
        plain = {"id": message["id"], "role": message["role"], "text": message["content"]}
        timeline.append((message["at"], 0, [plain]))
    answers: dict[str, dict[str, Any]] = {}
    for state, seq in conductor.log.runs_for(conversation_id):  # a group's first comes first
        if state.branch_of and state.branch_of in answers:
            group = answers[state.branch_of]
            group.setdefault(
                "branches", [{"id": group["id"], "seq": group["seq"], "run": group["run"]}]
            )
            group["branches"].append(
                {"id": state.run_id, "seq": seq, "run": state.model_dump(mode="json")}
            )
            continue
        request, at = requests[state.run_id]
        user = {"id": f"user-{state.run_id}", "role": "user", "text": request}
        answers[state.run_id] = assistant_message(state, seq)
        timeline.append((at, 1, [user, answers[state.run_id]]))
    timeline.sort(key=lambda item: (item[0], item[1]))
    return {
        "conversationId": conversation_id,
        "messages": [m for _, _, group in timeline for m in group],
    }
