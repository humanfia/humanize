"""The chips of a chat: what it is of, where it works, what answers it and what that may touch.

The web page draws them as a row under the box a chat is typed into (`chips/*.js`), and each
opens a list its value is picked out of. Here they are the same values, by the same names,
picked out of the same lists (:class:`hmz.tui.dropdown.Dropdown`): a new chat's on the New chat
page (`newchat.py`), and those of the chat that is open in the view this module adds --
*Details*, in the context, where its model and effort (`chat.agent`), its permission and what
`$` prefers (`chat.set`) and the environment it works in (`chat.move`) are changed while it
goes on, what it has used is read, and it is renamed, forked, archived or deleted.

Everything is asked of this machine's daemon (:func:`calls`), whose chats they are; nothing is
read off a chat's files. What a view needs of the interface it is opened in -- which chat is on
the screen, going to another -- is a :class:`Desk`, so that a view is written against that and
not against the interface.
"""

# The views are part of the interface, laid out over several files: what one borrows of the
# interface or of its sheets is what would be a private name within one of them.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Final, NamedTuple, cast

from rich.markup import escape
from textual import work
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from hmz.tui import humanfia
from hmz.tui.dropdown import Dropdown, Value, anchor
from hmz.tui.shell import View
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from textual import events
    from textual.app import App
    from textual.geometry import Offset

    from hmz.tui.app import Humanize

__all__ = [
    "DEFAULT",
    "MODES",
    "VIEWS",
    "Asks",
    "Chips",
    "Desk",
    "Heading",
    "Mode",
    "Nous",
    "Place",
    "Start",
    "browsed",
    "calls",
    "desk",
    "effort_name",
    "effort_picked",
    "efforts_offered",
    "env_said",
    "envs_offered",
    "folder_picked",
    "harness_name",
    "mode_of",
    "mode_picked",
    "modes_offered",
    "nous_offered",
    "nous_picked",
    "parted",
    "picked",
    "place_picked",
    "spelled",
]

type Asks = Callable[..., dict[str, Any]]

#: The methods that write nothing, which carry no `idem`.
_READS: Final = frozenset(
    {
        "chat.get",
        "chat.list",
        "chat.harness.get",
        "chat.harness.list",
        "flows.backends",
        "paths.list",
        "runs.usage",
        "runtimes.list",
        "settings.get",
        "workspaces.list",
    }
)


def calls(method: str, **said: Any) -> dict[str, Any]:
    """Asks this machine's daemon one thing, and answers what it said.

    Args:
      method: The method.
      said: What it takes; what is given as None is left out.

    Raises:
      OSError: Where the daemon was not reached or refused it, saying why.
    """
    from hmz.tui.pick import LOCAL_DAEMON, _rpc

    given = {key: value for key, value in said.items() if value is not None}
    try:
        answer = _rpc(LOCAL_DAEMON, method, given, writes=method not in _READS)
    except OSError:
        raise
    except Exception as why:
        # A daemon that would not start, or one of another protocol: not reached, either way.
        raise OSError(str(why)) from why
    return dict(answer or {})


class Start(NamedTuple):
    """A chat to start: its first message, and what each chip says."""

    task: str
    agent: str
    permission: str
    env: str = ""
    worktree: bool = False


@dataclass(frozen=True)
class Desk:
    """What a view of a chat asks of the interface it is opened in.

    Attributes:
      asks: What asks the daemon one thing, as :func:`calls` does.
      workspace: The directory the interface was opened in.
      chat: The chat on the screen, by its id, or "" for none.
      follows: Goes to a chat: its id, and the slot of the host holding it or "" for none.
      clears: Leaves the chat on the screen for a new one, as `/clear` does.
      starts: Starts a chat of this directory, and puts it on the screen.
      says: Puts one line in the log.
    """

    asks: Asks = calls
    workspace: str = ""
    chat: Callable[[], str] = lambda: ""
    follows: Callable[[str, str], None] = lambda _chat, _slot: None
    clears: Callable[[], None] = lambda: None
    starts: Callable[[Start], None] = lambda _start: None
    says: Callable[[str], None] = lambda _said: None


def desk(app: App[None]) -> Desk:
    """The desk of an interface: the terminal interface's own, or one that does nothing."""
    from hmz.tui.app import Humanize

    if not isinstance(app, Humanize):
        return Desk()
    return _humanize(app)


def _humanize(app: Humanize) -> Desk:
    """The desk of the terminal interface: what it offers a view of a chat."""

    def starts(new: Start) -> None:
        app.starts_chat(
            new.task,
            agent=new.agent,
            permission=new.permission,
            worktree=new.worktree,
            env=new.env,
        )

    return Desk(
        calls,
        str(app.hmz.workspace),
        app.chat_followed,
        app.follows_chat,
        app.action_clear,
        starts,
        lambda said: app.show(escape(said)),
    )


# -- an agent, a part at a time -------------------------------------------------------------


class Nous(NamedTuple):
    """An agent as `-a` spells it, taken apart: `cli[@account]/model[:effort]`."""

    cli: str = ""
    account: str = ""
    model: str = ""
    effort: str = ""


_SPEC: Final = re.compile(r"^([^@/]+)(?:@([^/]*))?/(.*)$")

#: What an agent with no effort of its own writes for one.
_AUTO: Final = "auto"


def parted(spec: str) -> Nous:
    """An agent spec taken apart; every part "" for one that spells no agent."""
    said = _SPEC.match(spec or "")
    if said is None:
        return Nous()
    cli, account, rest = said[1], said[2] or "", said[3]
    model, colon, effort = rest.rpartition(":")
    return Nous(cli, account, model, effort) if colon else Nous(cli, account, rest)


def spelled(nous: Nous) -> str:
    """An agent put back together as `-a` spells it, or "" where it names no model.

    Its effort is always written, `auto` for none, as a settings file writes one
    (:func:`hmz.runtime.kept.read_back`): a model whose own name holds a colon
    (`llama3:8b`) is then never read as a model and an effort.
    """
    if not nous.cli or not nous.model:
        return ""
    whose = f"{nous.cli}@{nous.account}" if nous.account else nous.cli
    return f"{whose}/{nous.model}:{nous.effort or _AUTO}"


#: Each harness by its vendor's name for it (`names.js`).
_HARNESSES: Final = {
    "agy": "Antigravity",
    "claude": "Claude Code",
    "codex": "Codex",
    "cursor-agent": "Cursor CLI",
    "dsh": "DeepSeek Harness",
    "grok": "Grok Build",
    "kimi": "Kimi Code",
    "litellm": "LiteLLM",
    "mcode": "MiniMax Code",
    "mimo": "MiMo Code",
    "omp": "Oh My Pi",
    "opencode": "OpenCode",
    "pi": "Pi",
    "qwen": "Qwen Code",
}

#: Every rung of every harness's ladder, by the text the page names it with.
_EFFORTS: Final = {
    "ultra": "Ultra",
    "max": "Max@@effort",
    "xhigh": "Extra high",
    "extra-high": "Extra high",
    "high": "High",
    "medium": "Medium",
    "low": "Low",
    "minimal": "Minimal",
    "none": "None@@effort",
    "off": "Off",
}


def harness_name(cli: str) -> str:
    """A harness by its vendor's name for it: `claude` is `Claude Code`; another, as written."""
    return _HARNESSES.get(cli, cli)


def effort_name(effort: str) -> str:
    """An effort by its name; none, or `auto`, is the model's own: `Default`."""
    if not effort or effort == _AUTO:
        return t("Default")
    return t(_EFFORTS[effort]) if effort in _EFFORTS else effort


#: What marks the row of a harness nobody has asked what it runs: picking it asks.
UNASKED: Final = "?"


type _Held = dict[str, Any]


def _accounts(clis: Mapping[str, Any], cli: str) -> list[_Held]:
    """The accounts of one harness, as `flows.backends` answers them."""
    return cast("list[_Held]", cast("_Held", clis.get(cli) or {}).get("accounts") or [])


def _models(account: _Held | None) -> list[_Held]:
    """The models one account lists."""
    return cast("list[_Held]", (account or {}).get("models") or [])


def _account(accounts: Sequence[_Held], named: str | None) -> _Held | None:
    """The account of a harness that is offered: the one named, else the first that lists."""
    if named is not None:
        return next((one for one in accounts if one.get("name", "") == named), None)
    own = next((one for one in accounts if not one.get("name")), None)
    if own is not None and own.get("models"):
        return own
    return next((one for one in accounts if one.get("models")), own)


async def _clis(asks: Asks) -> _Held:
    """The CLIs installed on the daemon's machine, their accounts and models."""
    said = await asyncio.to_thread(asks, "flows.backends")
    return cast("_Held", said.get("clis") or {})


def nous_offered(
    clis: Mapping[str, Any], chosen: Nous, *, only: bool = False
) -> list[Value]:
    """Every model the harnesses here are known to run, a group a harness.

    Args:
      clis: The CLIs here, as `flows.backends` answers them.
      chosen: What is picked.
      only: Whether only the harness and account picked are offered: a chat that is open
        keeps both (Section 8.3.18 of [CORE]).

    Returns:
      A value a model, answering with its spec without an effort; and, for a harness that
      lists none, one that asks it where nobody has (its value begins with :data:`UNASKED`)
      or a line saying it lists none.
    """
    names = [chosen.cli] if only else list(clis)
    if chosen.cli and chosen.cli not in names:
        names.append(chosen.cli)
    offered: list[Value] = []
    for cli in names:
        mine = cli == chosen.cli
        held = _account(_accounts(clis, cli), chosen.account if mine else None)
        account = (
            str(held.get("name") or "") if held else chosen.account if mine else ""
        )
        listed = [str(one.get("name") or "") for one in _models(held)]
        if mine and chosen.model and chosen.model not in listed:
            # One nobody listed is kept as a row of its harness, as `-a` takes one.
            listed.append(chosen.model)
        group = harness_name(cli)
        offered += [
            Value(
                spelled(Nous(cli, account, model)),
                model,
                f"@{account}" if account else "",
                group,
            )
            for model in listed
        ]
        if listed:
            continue
        if held is not None and not held.get("asked"):
            offered.append(
                Value(f"{UNASKED}{cli}@{account}", t("Not asked yet"), "", group)
            )
        else:
            offered.append(Value("", t("No models listed"), "", group, inert=True))
    return offered


def efforts_offered(clis: Mapping[str, Any], chosen: Nous) -> list[Value]:
    """The efforts the model picked takes, the model's own first."""
    held = _account(_accounts(clis, chosen.cli), chosen.account)
    found = next(
        (one for one in _models(held) if one.get("name") == chosen.model), None
    )
    efforts = cast("list[str]", (found or {}).get("efforts") or [])
    return [
        Value(_AUTO, t("Default")),
        *(Value(str(one), effort_name(str(one))) for one in efforts),
    ]


# -- what a chat may touch ------------------------------------------------------------------


class Mode(NamedTuple):
    """One permission a chat's assistant can be held to (Section 8.3.9 of [CORE])."""

    value: str
    label: str
    about: str


#: The permission of a chat nobody gave another.
DEFAULT: Final = "workspace-write"

#: The permissions a chat is offered, narrowest first, as the daemon names and holds them.
MODES: Final = (
    Mode("read-only", "Read only", "Reads and runs commands, changes no file"),
    Mode("workspace-write", "Edit this folder", "Changes files in this folder only"),
    Mode("danger-full-access", "Full access", "Changes files anywhere on this machine"),
)


def mode_of(permission: str) -> Mode:
    """The mode a permission names, or the default's for one that names none."""
    return next(
        (one for one in MODES if one.value == permission),
        next(one for one in MODES if one.value == DEFAULT),
    )


def modes_offered() -> list[Value]:
    """The permissions as a list offers them, and under them why none asks before acting."""
    return [
        *(Value(one.value, t(one.label), t(one.about)) for one in MODES),
        Value(
            "",
            t(
                "The assistant acts without asking first. "
                "What it may touch is what holds it."
            ),
            inert=True,
        ),
    ]


def _prefers_offered() -> list[Value]:
    """What `$<name>` means where it names a skill and a flow (Section 8.9.10 of [CORE])."""
    return [
        Value("native", t("Use the skill"), t("The skill your CLI has by that name")),
        Value("flow", t("Start the flow"), t("The flow by that name")),
    ]


# -- where a chat works ---------------------------------------------------------------------


class Place(NamedTuple):
    """Where a new chat works: this computer, a new worktree of the folder, or a runtime."""

    env: str = ""
    """The env as `-e` writes one, or "" for the folder itself on this computer."""
    worktree: bool = False
    """Whether it works in a new git worktree of the folder."""


#: What picking a new worktree answers with, which is no env.
WORKTREE: Final = "worktree"
#: What picking this computer answers with.
LOCAL: Final = "local"

#: Each backend by what the page calls a runtime of it.
_KINDS: Final = {
    "ssh": "SSH host",
    "docker": "Docker container",
    "swarm": "Docker swarm",
    "apple-container": "Apple container",
    "slurm": "Slurm cluster",
}


def _last(path: str) -> str:
    """The last name of a path, or the path where it has none."""
    return path.rstrip("/").rpartition("/")[2] or path


def env_said(env: str, *, worktree: bool = False) -> str:
    """Where a chat works, as its chip says it.

    Args:
      env: The env as `-e` writes one: `local/<directory>`, `ssh@box/<directory>`; "" for
        the folder itself.
      worktree: Whether it is a new worktree of the folder.
    """
    if worktree:
        return t("New worktree")
    backend, _, rest = env.partition("/")
    if backend in ("", LOCAL):
        there = _last(rest)
        return (
            t("{name}, {dir}", name=t("This computer"), dir=there)
            if there
            else t("This computer")
        )
    return env


def _machine(env: str) -> str:
    """The machine an env is on, without the directory there: `This computer`, `ssh@box`."""
    backend = env.partition("/")[0]
    return t("This computer") if backend in ("", LOCAL) else backend


def envs_offered(
    runtimes: Sequence[Mapping[str, Any]], folder: str, *, worktree: str | None = None
) -> list[Value]:
    """Where a chat can work, as the Environment chip lists it.

    Args:
      runtimes: The runtimes saved, as `runtimes.list` answers them.
      folder: The folder the chat is of.
      worktree: "" where a new worktree is on offer, why not where it is not, and None for
        a chat that is open, which is offered none.
    """
    offered = [
        Value(LOCAL, t("This computer"), t("In the folder {name}", name=_last(folder)))
    ]
    if worktree is not None:
        offered.append(
            Value(
                WORKTREE,
                t("New worktree"),
                worktree or t("A copy under git, so the folder is left as it is"),
                inert=bool(worktree),
            )
        )
    for one in runtimes:
        backend, name = str(one.get("backend") or ""), str(one.get("name") or "")
        if not backend:
            continue
        kind = t(_KINDS[backend]) if backend in _KINDS else backend
        offered.append(
            Value(
                f"{backend}@{name}" if name else backend,
                name or kind,
                kind if name else "",
                t("Runtimes"),
            )
        )
    return offered


async def picked(
    app: App[None], title: str, values: Sequence[Value], current: str, at: Offset | None
) -> str | None:
    """Drops a list of values, and answers the one picked or None for none."""
    return await app.push_screen_wait(Dropdown(title, values, current, at=at))


#: What picking the directory listed answers with.
_HERE: Final = "="
#: What picking to browse answers with.
_BROWSE: Final = "…"


async def browsed(
    app: App[None],
    asks: Asks,
    start: str,
    *,
    env: str = "",
    at: Offset | None = None,
) -> str | None:
    """Walks the directories of the daemon's machine, or of a runtime's, to pick one.

    Args:
      app: The interface the lists are dropped on.
      asks: What asks the daemon one thing.
      start: The directory to open on.
      env: The runtime whose directories are walked, as `-e` writes one with no directory,
        or "" for the daemon's own machine.
      at: Where the lists are dropped.

    Returns:
      The directory picked, whole, or None for none.

    Raises:
      OSError: Where a directory could not be listed, saying why.
    """
    here = start
    while True:
        said = await asyncio.to_thread(asks, "paths.list", at=here, env=env or None)
        whole = str(said.get("whole") or here)
        values = [Value(_HERE, t("Use this directory"), whole)]
        if up := str(said.get("up") or ""):
            values.append(Value(up, "..", t("Up")))
        values += [
            Value(f"{whole.rstrip('/')}/{one['name']}", f"{one['name']}/")
            for one in cast("list[dict[str, Any]]", said.get("entries") or [])
            if one.get("dir")
        ]
        took = await picked(app, str(said.get("at") or whole), values, "", at)
        if took is None:
            return None
        if took == _HERE:
            return whole
        here = took


async def folder_picked(
    app: App[None], asks: Asks, current: str, *, at: Offset | None = None
) -> str | None:
    """Picks the folder a chat is of: one the daemon knows, or one browsed to.

    Returns:
      The folder, or None for none picked.

    Raises:
      OSError: Where the daemon could not be asked, saying why.
    """
    said = await asyncio.to_thread(asks, "workspaces.list", here=current)
    values = [
        Value(str(one["path"]), str(one.get("name") or one["path"]), str(one["path"]))
        for one in cast("list[dict[str, Any]]", said.get("workspaces") or [])
        if one.get("there", True)
    ]
    values.append(Value(_BROWSE, t("Open folder…")))
    took = await picked(app, t("Folder"), values, current, at)
    if took == _BROWSE:
        return await browsed(app, asks, current or "~", at=at)
    return took


async def _in_repository(asks: Asks, folder: str) -> bool:
    """Whether a folder is under git: it, or a directory over it, holds `.git`."""
    here = folder
    for _ in range(64):
        said = await asyncio.to_thread(
            asks, "paths.list", at=here, files=True, hidden=True
        )
        if any(one.get("name") == ".git" for one in said.get("entries") or ()):
            return True
        here = str(said.get("up") or "")
        if not here:
            return False
    return False


async def place_picked(
    app: App[None],
    asks: Asks,
    folder: str,
    current: Place,
    *,
    fresh: bool = True,
    at: Offset | None = None,
) -> Place | None:
    """Picks where a chat works: this computer, a new worktree, or a runtime and a directory.

    Args:
      app: The interface the lists are dropped on.
      asks: What asks the daemon one thing.
      folder: The folder the chat is of.
      current: Where it works now.
      fresh: Whether the chat is yet to start, which alone is offered a new worktree.
      at: Where the lists are dropped.

    Returns:
      Where, or None for nothing picked.

    Raises:
      OSError: Where the daemon could not be asked, saying why.
    """
    said = await asyncio.to_thread(asks, "runtimes.list")
    why: str | None = None
    if fresh:
        under = False
        try:
            under = await _in_repository(asks, folder)
        except Exception:  # noqa: BLE001 -- unread, whatever went wrong
            under = True  # unread, the daemon says so itself as the chat starts
        why = "" if under else t("This folder is not a git repository")
    backend = current.env.partition("/")[0]
    now = WORKTREE if current.worktree else backend or LOCAL
    values = envs_offered(
        cast("list[dict[str, Any]]", said.get("runtimes") or []), folder, worktree=why
    )
    took = await picked(app, t("Environment"), values, now, at)
    if took is None:
        return None
    if took == WORKTREE:
        return Place(worktree=True)
    if took == LOCAL:
        return Place()
    # In a runtime, the directory picked there; one not picked is the runtime's own.
    try:
        there = await browsed(app, asks, "~", env=took, at=at)
    except Exception:  # noqa: BLE001 -- a machine whose directories cannot be listed
        there = None
    return Place(f"{took}/{there.lstrip('/')}" if there else took)


async def nous_picked(
    app: App[None],
    asks: Asks,
    spec: str,
    *,
    only: bool = False,
    at: Offset | None = None,
) -> str | None:
    """Picks the model that answers a chat, asking a harness what it runs where nobody has.

    Args:
      app: The interface the lists are dropped on.
      asks: What asks the daemon one thing.
      spec: The agent picked now.
      only: Whether only its own harness and account are offered.
      at: Where the list is dropped.

    Returns:
      The agent as `-a` spells it, keeping the effort where the model picked takes it, or
      None for none picked.

    Raises:
      OSError: Where the daemon could not be asked, saying why.
    """
    chosen = parted(spec)
    while True:
        clis = await _clis(asks)
        values = nous_offered(clis, chosen, only=only)
        if not values:
            values = [
                Value("", t("No harness is installed on this daemon."), inert=True)
            ]
        took = await picked(
            app, t("Model"), values, spelled(chosen._replace(effort="")), at
        )
        if not took:
            return None
        if not took.startswith(UNASKED):
            nous = parted(took)
            keeps = any(
                one.value == chosen.effort for one in efforts_offered(clis, nous)
            )
            return spelled(nous._replace(effort=chosen.effort if keeps else ""))
        cli, _, account = took.removeprefix(UNASKED).partition("@")
        await asyncio.to_thread(asks, "accounts.models", cli=cli, name=account)


async def effort_picked(
    app: App[None], asks: Asks, spec: str, *, at: Offset | None = None
) -> str | None:
    """Picks the effort of the model picked, and answers the agent with it, or None.

    Raises:
      OSError: Where the daemon could not be asked, saying why.
    """
    nous = parted(spec)
    clis = await _clis(asks)
    effort = await picked(
        app, t("Effort"), efforts_offered(clis, nous), nous.effort or _AUTO, at
    )
    return spelled(nous._replace(effort=effort)) if effort else None


async def mode_picked(
    app: App[None], current: str, *, at: Offset | None = None
) -> str | None:
    """Picks what a chat's assistant may touch, and answers the permission, or None."""
    return (
        await picked(app, t("Permissions"), modes_offered(), mode_of(current).value, at)
        or None
    )


class Heading(Static):
    """What a page is headed: its title in capitals over a heavy rule, as a zone's is."""

    DEFAULT_CSS = """
    Heading { height: 2; color: $primary; text-style: bold; }
    """

    def __init__(self, title: str) -> None:
        """Holds the title, which is drawn once the page is as wide as it is.

        Args:
          title: It, already in the language spoken.
        """
        super().__init__()
        self._title = title

    def on_resize(self, event: events.Resize) -> None:
        """Rules the title across however wide the page is now."""
        self.update(
            f" {escape(self._title.upper())}\n{humanfia.RULE * event.size.width}"
        )


# -- the chips of the chat that is open ------------------------------------------------------

#: How often the chat is read again, in seconds: as often as the page reads one.
_EVERY: Final = 4.0
#: How many days of the folder's usage are read: the shortest range the Usage page offers.
_DAYS: Final = 7
#: How wide a chip's name is drawn, so that the values line up.
_NAMED: Final = 14

_MODEL, _EFFORT, _PERMISSION, _PREFER, _ENV = (
    "model",
    "effort",
    "permission",
    "prefer",
    "env",
)
_RENAME, _FORK, _ARCHIVE, _DELETE = "rename", "fork", "archive", "delete"


class Chips(OptionList):
    """The chat that is open: its chips, what it has used, and what is done to it.

    A row a chip, its name then its value, and enter on one drops the list it is changed
    from; under them what the chat and its folder have used, and under that Rename, Fork,
    Archive and Delete. Read again every few seconds, so that it says how the chat stands
    now, whoever changed it.
    """

    DEFAULT_CSS = """
    Chips, Chips:focus { height: 1fr; padding: 1 0 0 0; border: none;
                         background: $surface; }
    Chips > .option-list--option { padding: 0 1; }
    Chips > .option-list--option-disabled { color: $foreground; }
    /* The chip being changed stays the pink plane while its list is dropped over it. */
    Chips.-changing > .option-list--option-highlighted {
        background: $accent; color: $background; text-style: bold;
    }
    """

    #: The keys it takes, as the hint line says them.
    KEYS: ClassVar = (("↑↓", "Move"), ("enter", "Choose"))

    def __init__(self, at: Desk) -> None:
        """Opens on the chat on the screen, which is asked for as it mounts.

        Args:
          at: The interface it is opened in.
        """
        super().__init__()
        self._desk = at
        #: The chat as `chat.get` last answered it, or None for none on the screen.
        self._row: dict[str, Any] | None = None
        #: What its folder has used lately, as `runs.usage` answers it.
        self._used: dict[str, Any] = {}
        #: The chip being changed: the row under the cursor, which is the one thing drawn
        #: pink, and nothing else is changed until it has been.
        self._changing = ""
        #: What became of the last thing done, already markup, or "".
        self._said = f"[$text-muted]{t('Reading…')}[/]"
        #: Whether what is said is of the chat not having been read, which reading it unsays.
        self._unread = True
        #: Whether a reading is on its way, which the next one waits for.
        self._reading = False
        self._ticks = 0

    def on_mount(self) -> None:
        """Reads the chat, and goes on reading it."""
        self._fill()
        self._reads()
        self.set_interval(_EVERY, self._ticked)

    @work(group="chips-reads", exclusive=True)
    async def _reads(self) -> None:
        """Reads the chat on the screen, and now and then what its folder has used."""
        name = self._desk.chat()
        if not name:
            self._row, self._said = None, ""
            self._fill()
            return
        self._reading = True
        try:
            self._row = await asyncio.to_thread(self._desk.asks, "chat.get", chat=name)
            if not self._ticks % 8:
                self._used = await asyncio.to_thread(
                    self._desk.asks,
                    "runs.usage",
                    days=_DAYS,
                    workspace=str(self._row.get("workspace") or "") or None,
                )
            self._ticks += 1
            if self._unread:
                # Read now: what was said of not reading it is no longer so.
                self._said, self._unread = "", False
        except Exception as why:  # noqa: BLE001 -- a refusal, or no daemon: said either way
            self._said, self._unread = f"[$error]{escape(str(why))}[/]", True
            if self._row is not None and self._row.get("id") != name:
                # Another chat's, which nothing is to be done to from here.
                self._row = None
        finally:
            self._reading = False
        self._fill()

    def _ticked(self) -> None:
        """Reads again, unless the last reading is still on its way."""
        if not self._reading:
            self._reads()

    def _chip(self, key: str, name: str, value: str) -> Option:
        """One chip as its row says it: its name, quietly, then its value."""
        return Option(f"[$text-muted]{t(name).ljust(_NAMED)}[/]{escape(value)}", id=key)

    @staticmethod
    def _head(text: str) -> Option:
        return Option(
            f"[b $text-muted]{humanfia.SQUARE} {escape(text.upper())}[/]", disabled=True
        )

    @staticmethod
    def _line(markup: str = "") -> Option:
        return Option(markup, disabled=True)

    def _rows(self) -> list[Option]:
        """Every row: the chat, its chips, what it has used, what is done to it."""
        row = self._row
        if row is None:
            return [self._line(self._said or f"[$text-muted]{t('No chat here')}[/]")]
        nous = parted(str(row.get("agent") or ""))
        spent = cast("dict[str, Any]", row.get("spent") or {})
        whole = cast("dict[str, Any]", self._used.get("whole") or {})
        prefer = str(row.get("prefer") or "")
        asking = row.get("state") == "asking"
        rows = [
            self._line(
                f"[b]{escape(' '.join(str(row.get('title') or '').split()))}[/]"
            ),
            self._line(
                f"[$warning]{humanfia.POINT} {t('Waiting for you')}[/]"
                if asking
                else f"[$error]{t('The chat failed')}[/]"
                if row.get("state") == "failed"
                else f"[$text-muted]{escape(str(row.get('id') or ''))}[/]"
            ),
            self._line(),
            # Its harness and its account are the chat's for good (Section 8.3.18 of [CORE]).
            self._figure("Harness", harness_name(nous.cli)),
            self._figure("Account", nous.account or t("Local")),
            self._chip(_MODEL, "Model", nous.model),
            self._chip(_EFFORT, "Effort", effort_name(nous.effort)),
            self._chip(
                _PERMISSION,
                "Permissions",
                t(mode_of(str(row.get("permission") or "")).label),
            ),
            self._chip(
                _PREFER,
                "Skill or flow",
                t("Start the flow")
                if prefer == "flow"
                else t("Use the skill")
                if prefer == "native"
                else t("Default"),
            ),
            self._chip(_ENV, "Environment", _machine(str(row.get("env") or ""))),
            self._figure("Directory", _last(str(row.get("workdir") or ""))),
            self._line(),
            self._head(t("Usage")),
        ]
        if spent.get("money") or spent.get("tokens"):
            rows += [
                self._figure("Spent", str(spent.get("money") or "—")),
                self._figure("Output tokens", str(spent.get("tokens") or "—")),
                self._figure("Time working", str(spent.get("worked") or "—")),
            ]
        else:
            rows.append(self._line(f"[$text-muted]{t('Nothing used yet')}[/]"))
        if whole:
            rows.append(self._figure("Last 7 days", str(whole.get("money") or "$0.00")))
        rows += [
            self._line(),
            self._head(t("Actions")),
            Option(t("Rename…"), id=_RENAME),
            Option(t("Fork"), id=_FORK),
            Option(t("Archive"), id=_ARCHIVE),
            Option(t("Delete chat"), id=_DELETE),
        ]
        if self._said:
            rows += [self._line(), self._line(self._said)]
        return rows

    def _figure(self, name: str, value: str) -> Option:
        return self._line(f"[$text-muted]{t(name).ljust(_NAMED)}[/]{escape(value)}")

    def _fill(self) -> None:
        """Draws the rows again, the cursor kept on the row it was on."""
        at = self.highlighted
        was = self.get_option_at_index(at).id if at is not None else None
        self.clear_options()
        rows = self._rows()
        self.add_options(rows)
        ids = [one.id for one in rows]
        first = next((n for n, one in enumerate(rows) if not one.disabled), None)
        self.highlighted = ids.index(was) if was and was in ids else first

    async def _asked(self, method: str, **said: Any) -> dict[str, Any] | None:
        """Asks the daemon off the screen's thread; None, having said why, where refused."""
        try:
            answer = await asyncio.to_thread(self._desk.asks, method, **said)
        except Exception as why:  # noqa: BLE001 -- a refusal, or no daemon: said either way
            self._said = f"[$error]{escape(str(why))}[/]"
            self._fill()
            return None
        self._said = ""
        return answer

    async def _held(self, row: Mapping[str, Any]) -> str | None:
        """The slot of the host holding the chat, having one take it up where none does.

        `chat.set` and `chat.move` are asked of a host. A chat that has folded away is
        carried on with nothing said (Section 4.25.1.9 of [DAEMON]): its host then stands
        by, and the interface goes to it.
        """
        if slot := str(row.get("slot") or ""):
            return slot
        made = await self._asked(
            "chat.start",
            workspace=str(row.get("workspace") or ""),
            resume=str(row.get("id") or ""),
            task="",
        )
        if made is None:
            return None
        slot = str(made.get("slot") or "")
        self._desk.follows(str(row.get("id") or ""), slot)
        return slot

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Changes the chip picked, or does what the action picked does."""
        event.stop()
        if self._row is not None and event.option.id and not self._changing:
            self._does(str(event.option.id), dict(self._row))

    @work(group="chips-does", exclusive=True)
    async def _does(self, key: str, row: dict[str, Any]) -> None:
        """Changes one chip, or does one thing to the chat, then reads it again."""
        self._changing = key
        self.add_class("-changing")
        try:
            await self._changes(key, row)
        except Exception as why:  # noqa: BLE001 -- a refusal, or no daemon: said either way
            self._said = f"[$error]{escape(str(why))}[/]"
        finally:
            self._changing = ""
            self.remove_class("-changing")
            self._fill()
        self._reads()

    async def _changes(self, key: str, row: dict[str, Any]) -> None:
        app = cast("App[None]", self.app)  # pyright: ignore[reportUnknownMemberType]
        asks, at = self._desk.asks, anchor(self)
        name = str(row.get("id") or "")
        workspace = str(row.get("workspace") or "")
        nous = parted(str(row.get("agent") or ""))
        if key == _MODEL:
            spec = await nous_picked(app, asks, spelled(nous), only=True, at=at)
            if spec and spec != spelled(nous):
                await self._asked("chat.agent", chat=name, agent=spec)
        elif key == _EFFORT:
            spec = await effort_picked(app, asks, spelled(nous), at=at)
            if spec and spec != spelled(nous):
                await self._asked("chat.agent", chat=name, agent=spec)
        elif key in (_PERMISSION, _PREFER):
            now = str(row.get(key) or "")
            if key == _PERMISSION:
                now = mode_of(now).value
                took = await mode_picked(app, now, at=at)
            else:
                took = await picked(
                    app, t("Skill or flow"), _prefers_offered(), now, at
                )
            if took and took != now and (slot := await self._held(row)):
                await self._asked(
                    "chat.set", workspace=workspace, slot=slot, **{key: took}
                )
        elif key == _ENV:
            now = Place(str(row.get("env") or ""))
            place = await place_picked(app, asks, workspace, now, fresh=False, at=at)
            # This computer picked for a chat on this computer is nothing picked: it stays
            # in the directory it works in, a worktree included.
            stays = place is None or (
                place.env == now.env
                or (not place.env and now.env.partition("/")[0] in ("", LOCAL))
            )
            if place is not None and not stays and (slot := await self._held(row)):
                # This computer is the folder itself, written as `-e` writes a directory.
                env = place.env or f"{LOCAL}/{workspace.lstrip('/')}"
                await self._asked("chat.move", workspace=workspace, slot=slot, env=env)
        elif key == _RENAME:
            from hmz.tui.chats import Renames

            title = await app.push_screen_wait(Renames(str(row.get("title") or "")))
            if title:
                await self._asked("chat.rename", chat=name, title=title)
        elif key == _FORK:
            made = await self._asked("chat.fork", chat=name)
            if made is not None:
                # A fork just made is on no host, and is carried on by the next line.
                self._desk.follows(str(made.get("chat") or ""), "")
        elif key == _ARCHIVE:
            if await self._asked("chat.archive", chat=name) is not None:
                self._row = None
                self._desk.clears()
        elif key == _DELETE:
            from hmz.tui.chats import Deletes

            titled = " ".join(str(row.get("title") or "").split()) or name
            sure = await app.push_screen_wait(Deletes(titled))
            if (
                sure == "yes"
                and await self._asked("chat.delete", chat=name) is not None
            ):
                self._row = None
                self._desk.clears()


def _made(app: App[None]) -> Chips:
    return Chips(desk(app))


VIEWS = (
    View(
        "chips",
        "context",
        "Details",
        _made,
        key="ctrl+g",
        hint="Details",
        keys=Chips.KEYS,
    ),
)
