"""What Ai-chan reaches for: hmz's methods, each a tool and a command over her one session.

Every tool is a thin call of one or two methods of `protocol/daemon.md` over the session her
conversation holds to the daemon, through its scoped link (Section 14.6.2 of core.md): the
daemon holds each call to her reach, and a call it refuses is the tool failing, which she reads
and her turn goes on (Section 14.6.3). The same calls are put on her PATH as the command line
`hmz-ai`, for a harness she would rather run them from her shell in.

The tools are the role's, declared once; which conversation a call is of is the flow call it
runs as, so each conversation's session is kept here under its flow call while it lasts.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import pydantic

from hmz.flows import FakeCli, FakeCommand, FakeTool

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable, Generator

    from hmz.sdk import Client

__all__ = ["CLI", "TOOLS", "Link", "linked"]

#: The most of one answer she reads back, in characters: a transcript can be far longer than
#: anything a turn could hold, and what is cut says so.
MOST = 200_000

#: A mapping, as a tool is given one and as a command line is typed one: JSON text.
type Mapping = dict[str, Any] | pydantic.Json[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class Link:
    """One conversation's session to the daemon, and the workspace a call names by default.

    Attributes:
      client: The session, over the conversation's scoped link.
      workspace: The workspace of her scope, or "" for the scope `daemon`.
    """

    client: Client
    workspace: str


#: Each conversation's link, by the flow call it is.
_LINKS: dict[int, Link] = {}


@contextlib.contextmanager
def linked(ctx: object, link: Link) -> Generator[None]:
    """Keeps a conversation's link for the tools its agent calls while the block runs."""
    _LINKS[id(ctx)] = link
    try:
        yield
    finally:
        _LINKS.pop(id(ctx), None)


def _link() -> Link:
    """The link of the conversation a tool is called in.

    Raises:
      RuntimeError: Outside every conversation.
    """
    from hmz.runtime.flowing.engine import current

    found = _LINKS.get(id(current()))
    if found is None:
        raise RuntimeError("Ai-chan has no session to the daemon here")
    return found


async def _call(
    method: str, params: dict[str, Any] | None = None, *, whole: bool = False
) -> Any:
    """Calls one method over the link: what was not given (None) left out, unless `whole`."""
    link = _link()
    given = {
        key: value
        for key, value in (params or {}).items()
        if whole or value is not None
    }
    return await asyncio.to_thread(link.client.call, method, given)


def _where(workspace: str | None) -> str | None:
    """The workspace a call names: the one given, else her scope's, else none."""
    return workspace or _link().workspace or None


@contextlib.asynccontextmanager
async def _attached(workspace: str | None, slot: str) -> AsyncGenerator[str]:
    """Attached to a host, as one frontend, for the calls of the block: its `sub`."""
    attached = await _call(
        "epic.attach", {"workspace": _where(workspace), "slot": slot, "replay": False}
    )
    sub: str = attached["sub"]
    try:
        yield sub
    finally:
        # Letting go closes every side conversation it opened with it.
        with contextlib.suppress(Exception):
            await _call("epic.detach", {"sub": sub})


async def _on_host(
    workspace: str | None, slot: str, method: str, params: dict[str, Any]
) -> Any:
    """Calls one method of an epic, attached to its host for the call."""
    async with _attached(workspace, slot) as sub:
        return await _call(method, {"sub": sub, **params})


def _said(value: object) -> str:
    """An answer as she reads it: JSON, cut where it is longer than she could read."""
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) <= MOST:
        return text
    return f"{text[:MOST]}\n... cut: {len(text) - MOST} more characters"


# ------------------------------------------------------------------------- what they take


class _Model(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")


def _workspace() -> Any:
    return pydantic.Field(
        default=None,
        description="The workspace, as a whole path; your scope's where left out.",
    )


def _slot() -> Any:
    return pydantic.Field(
        default="",
        description="The host's slot: \"\" for the workspace's own, chat:<hex>, exec:<hex>.",
    )


class Nothing(_Model):
    """What a tool that takes nothing takes."""


class Listing(_Model):
    """Which epics to list."""

    workspace: str | None = _workspace()
    status: str | None = pydantic.Field(
        default=None, description="Only of this status."
    )
    flow: str | None = pydantic.Field(default=None, description="Only of this flow.")
    q: str | None = pydantic.Field(
        default=None, description="Only those matching this."
    )
    offset: int | None = pydantic.Field(
        default=None, ge=0, description="Skip this many."
    )
    limit: int = pydantic.Field(
        default=20, ge=1, le=200, description="At most this many."
    )


class Named(_Model):
    """One epic, by its epic name."""

    name: str = pydantic.Field(description="The epic's name, as epics_list says it.")


class Spending(_Model):
    """Whose spending, over how long."""

    days: int | None = pydantic.Field(
        default=None, ge=1, le=365, description="Days back."
    )
    workspace: str | None = _workspace()


class Asking(_Model):
    """A side question of one session of the epic on a host."""

    workspace: str | None = _workspace()
    slot: str = _slot()
    key: str = pydantic.Field(
        description="The session, <agent>/<n>, as epic_view says it."
    )
    question: str = pydantic.Field(description="What to ask it.")
    fork: bool = pydantic.Field(
        default=True, description="Ask a fork of it, which remembers what it was told."
    )


class Saying(_Model):
    """A line said to the epic on a host."""

    workspace: str | None = _workspace()
    slot: str = _slot()
    text: str = pydantic.Field(description="What to say.")
    to: str = pydantic.Field(
        default="", description='Whom: "" for the run, or outworlder:<role>.'
    )


class Answering(_Model):
    """An answer to a question the epic on a host waits on."""

    workspace: str | None = _workspace()
    slot: str = _slot()
    question: str = pydantic.Field(default="", description="The question's id.")
    text: str = pydantic.Field(description="The answer.")


class Starting(_Model):
    """An epic to start."""

    workspace: str | None = _workspace()
    slot: str = pydantic.Field(
        default="exec:", description='The host: "exec:" for a new one of its own.'
    )
    flow: str = pydantic.Field(description="The flow, as `hmz exec -f` names it.")
    task: str = pydantic.Field(default="", description="What it is asked to do.")
    agents: Mapping = pydantic.Field(
        default_factory=dict[str, Any], description="Agent spec by role."
    )
    envs: Mapping = pydantic.Field(
        default_factory=dict[str, Any], description="Environment spec by role."
    )
    params: Mapping | None = pydantic.Field(default=None, description="Its params.")
    budget: Mapping | None = pydantic.Field(
        default=None, description="Its budget: cost, duration, output_tokens."
    )


class Stopping(_Model):
    """The epic on a host to stop."""

    workspace: str | None = _workspace()
    slot: str = _slot()
    force: bool = pydantic.Field(
        default=False, description="Close the sessions of an epic already stopping."
    )


class Host(_Model):
    """A host, whose epic's envs are meant."""

    workspace: str | None = _workspace()
    slot: str = _slot()


class Reading(Host):
    """A file of an env to read."""

    env: str = pydantic.Field(description="The env's role, as env_list says it.")
    path: str = pydantic.Field(description="The file, relative to the env's workdir.")
    offset: int | None = pydantic.Field(default=None, ge=0, description="From byte.")
    length: int | None = pydantic.Field(
        default=None, ge=1, description="At most bytes."
    )


class Writing(Host):
    """A file of an env to write, whole."""

    env: str = pydantic.Field(description="The env's role.")
    path: str = pydantic.Field(description="The file, relative to the env's workdir.")
    text: str = pydantic.Field(description="What it holds.")


class Running(Host):
    """A command to run in an env's workdir."""

    env: str = pydantic.Field(description="The env's role.")
    argv: list[str] = pydantic.Field(description="The program and its arguments.")
    seconds: int | None = pydantic.Field(
        default=None, ge=1, le=3600, description="Killed after this long."
    )


class Searching(Host):
    """What to search an env's files for."""

    env: str = pydantic.Field(description="The env's role.")
    pattern: str = pydantic.Field(description="A POSIX extended regular expression.")
    path: str | None = pydantic.Field(default=None, description="Under this path.")
    limit: int | None = pydantic.Field(default=None, ge=1, le=2000, description="Most.")


class Settings(_Model):
    """Whose settings."""

    workspace: str | None = _workspace()


class Setting(_Model):
    """Settings to write."""

    values: Mapping = pydantic.Field(
        description='The settings.set params to write, e.g. {"ai_chan": "claude"}.'
    )


class Nous(_Model):
    """A nous to write, whole."""

    name: str = pydantic.Field(description="Its name.")
    values: Mapping = pydantic.Field(
        default_factory=dict[str, Any],
        description="The rest of nous.set: graph, then, tries, policy, timeout.",
    )


class Methods(_Model):
    """Which methods to list."""

    prefix: str = pydantic.Field(default="", description="Only those starting so.")


class Calling(_Model):
    """One method to call."""

    method: str = pydantic.Field(description="The method, as hmz_methods lists it.")
    params: Mapping = pydantic.Field(
        default_factory=dict[str, Any], description="Its params, by name."
    )


# ---------------------------------------------------------------------------- the calls


async def overview() -> str:
    """Every host going and every workspace."""
    running = await _call("hosts.running")
    workspaces = await _call("workspaces.list")
    return _said({"running": running, "workspaces": workspaces})


async def epics_list(said: Listing) -> str:
    """The epics written down."""
    return _said(
        await _call(
            "runs.list", said.model_dump() | {"workspace": _where(said.workspace)}
        )
    )


async def epic_view(said: Named) -> str:
    """One epic."""
    return _said(await _call("runs.get", {"name": said.name}))


async def transcript_read(said: Named) -> str:
    """An epic's transcripts."""
    return _said(await _call("runs.trace", {"name": said.name}))


async def trace_read(said: Named) -> str:
    """An epic's timeline."""
    return _said(await _call("runs.timeline", {"name": said.name}))


async def usage(said: Spending) -> str:
    """What epics spent."""
    return _said(
        await _call(
            "runs.usage", {"days": said.days, "workspace": _where(said.workspace)}
        )
    )


async def ask_session(said: Asking) -> str:
    """A side question of one session: a side conversation opened on it, and asked."""
    async with _attached(said.workspace, said.slot) as sub:
        opened = await _call(
            "epic.aside", {"sub": sub, "key": said.key, "fork": said.fork}
        )
        answered = await _call(
            "epic.aside", {"sub": sub, "side": opened["side"], "prompt": said.question}
        )
    return _said(answered.get("answer", ""))


async def say(said: Saying) -> str:
    """A line said to an epic."""
    return _said(
        await _on_host(
            said.workspace, said.slot, "epic.say", {"text": said.text, "to": said.to}
        )
    )


async def answer(said: Answering) -> str:
    """An answer to a question an epic waits on."""
    return _said(
        await _on_host(
            said.workspace,
            said.slot,
            "epic.answer",
            {"question": said.question, "text": said.text},
        )
    )


async def start(said: Starting) -> str:
    """An epic started."""
    given = said.model_dump(
        include={"flow", "task", "agents", "envs", "params", "budget"}
    )
    return _said(await _on_host(said.workspace, said.slot, "epic.start", given))


async def stop(said: Stopping) -> str:
    """An epic stopped, or forced."""
    method = "epic.force" if said.force else "epic.stop"
    return _said(await _on_host(said.workspace, said.slot, method, {}))


def _host(said: Host) -> dict[str, Any]:
    """A call of `hosts.env.*`: what was said, the workspace filled in."""
    return said.model_dump() | {"workspace": _where(said.workspace)}


async def env_list(said: Host) -> str:
    """The envs of the epic on a host."""
    return _said(await _call("hosts.env.list", _host(said)))


async def env_read(said: Reading) -> str:
    """A file of an env."""
    return _said(await _call("hosts.env.read", _host(said)))


async def env_write(said: Writing) -> str:
    """A file of an env, written whole."""
    return _said(await _call("hosts.env.write", _host(said)))


async def env_exec(said: Running) -> str:
    """A command run in an env."""
    return _said(await _call("hosts.env.exec", _host(said)))


async def env_grep(said: Searching) -> str:
    """An env's files searched."""
    return _said(await _call("hosts.env.grep", _host(said)))


async def settings_get(said: Settings) -> str:
    """The settings."""
    return _said(await _call("settings.get", {"workspace": _where(said.workspace)}))


async def settings_set(said: Setting) -> str:
    """Settings written."""
    return _said(await _call("settings.set", said.values, whole=True))


async def nous_list() -> str:
    """Every nous."""
    return _said(await _call("nous.list"))


async def nous_set(said: Nous) -> str:
    """A nous written, whole."""
    return _said(
        await _call("nous.set", {**said.values, "name": said.name}, whole=True)
    )


async def hmz_methods(said: Methods) -> str:
    """The methods there are to call, from the daemon's own OpenRPC document."""
    document = await _call("rpc.discover")
    listed: list[dict[str, Any]] = []
    methods: list[dict[str, Any]] = document.get("methods", [])
    for one in methods:
        reach: dict[str, Any] = one.get("x-hmz-reach") or {}
        if not str(one.get("name", "")).startswith(said.prefix) or (
            reach.get("scope") == "never"
        ):
            continue
        listed.append(
            {
                "method": one["name"],
                "summary": one.get("summary", ""),
                "writes": one.get("x-hmz-writes", False),
                "reach": reach,
                "params": {
                    param["name"]: param.get("schema", {})
                    | ({"required": True} if param.get("required") else {})
                    for param in one.get("params", [])
                },
            }
        )
    return _said(listed)


async def hmz_call(said: Calling) -> str:
    """Any method her reach allows."""
    return _said(await _call(said.method, said.params, whole=True))


#: Each call: its name, what it is for, what runs it, and what it takes.
_CALLS: tuple[
    tuple[str, str, Callable[..., Awaitable[str]], type[_Model] | None], ...
] = (
    (
        "overview",
        "Every host going and every workspace: where to start looking.",
        overview,
        None,
    ),
    (
        "epics_list",
        "The epics written down, newest first, filtered.",
        epics_list,
        Listing,
    ),
    (
        "epic_view",
        "One epic: its flow, task, state, agents and sessions.",
        epic_view,
        Named,
    ),
    (
        "transcript_read",
        "An epic's transcripts, every session's.",
        transcript_read,
        Named,
    ),
    ("trace_read", "An epic's timeline of flow calls and turns.", trace_read, Named),
    ("usage", "What epics spent, by day and by flow.", usage, Spending),
    (
        "ask_session",
        "Asks one session of the epic on a host a side question; the epic never sees it.",
        ask_session,
        Asking,
    ),
    ("say", "Says a line to the epic going on a host.", say, Saying),
    ("answer", "Answers a question the epic on a host waits on.", answer, Answering),
    ("start", "Starts an epic on a host.", start, Starting),
    ("stop", "Stops the epic going on a host, or forces one stopping.", stop, Stopping),
    ("env_list", "The envs of the epic going on a host.", env_list, Host),
    ("env_read", "Reads a file of an env of the epic on a host.", env_read, Reading),
    (
        "env_write",
        "Writes a file of an env of the epic on a host, whole.",
        env_write,
        Writing,
    ),
    ("env_exec", "Runs a command in an env of the epic on a host.", env_exec, Running),
    (
        "env_grep",
        "Searches the files of an env of the epic on a host.",
        env_grep,
        Searching,
    ),
    (
        "settings_get",
        "The settings of the machine and of a workspace.",
        settings_get,
        Settings,
    ),
    ("settings_set", "Writes settings.", settings_set, Setting),
    ("nous_list", "Every nous.", nous_list, None),
    ("nous_set", "Writes a nous, whole.", nous_set, Nous),
    (
        "hmz_methods",
        (
            "Every daemon method there is to call with hmz_call: what each takes, and "
            "whether it writes."
        ),
        hmz_methods,
        Methods,
    ),
    (
        "hmz_call",
        (
            "Calls any daemon method your reach allows, by name, with its params; a "
            "refusal says why."
        ),
        hmz_call,
        Calling,
    ),
)

#: Her tools.
TOOLS = tuple(FakeTool(name, about, call, takes) for name, about, call, takes in _CALLS)

#: The same calls as a command line on her PATH: `hmz-ai <call> --<param> ...`, a mapping
#: typed as JSON.
CLI = FakeCli(
    "hmz-ai",
    "Operates hmz, as Ai-chan's tools do.",
    tuple(
        FakeCommand(name.replace("_", "-"), about, call, takes)
        for name, about, call, takes in _CALLS
    ),
)
