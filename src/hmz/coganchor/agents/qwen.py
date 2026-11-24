"""Qwen Code: one official CLI process held across ordinary conversation turns.

Its command line says everything an agent is configured with except how hard to think -- the
model, the session to carry on, what it may do without being asked. Its stream-json input
keeps the CLI initialized between turns. Shaped turns still use a command of their own:
Qwen refuses `--json-schema` with persistent stream-json input. What it writes on stdout with
`--output-format stream-json` is a protocol rather than the agent talking: one JSON object a
line, the session it opened and the answer it ended on among them.

How hard it thinks is the one setting with no flag. It is a setting of the CLI's own
`settings.json`, so each process is started in a virtual home (:mod:`hmz.coganchor.homes`)
whose `settings.json` is a copy of the user's with the run's own settings merged in: the
effort, the hook table, the server carrying the flow's callbacks. Two agents of one flow may
think at two efforts, and neither is a reason to change what the person who started the flow
has configured -- their own file is never written, and the system layers are left to the
machine. Beside those goes what a turn nobody is watching defaults to, said only where their
own settings say nothing of it.

Everything else here is Qwen Code's own answer rather than one of ours. Where it is not --
that defaults layer, the compile cache, the partial stream -- there is a field of
:class:`QwenCodeAgentConfig` saying so, which is what a flow asks about beforehand, so that
an install which configures nothing runs the CLI as the CLI runs itself.

Its own caps are not among them. `--max-wall-time`, `--max-tool-calls` and
`--max-session-turns` are counted over the *run*, and a run here is a process held open
across every turn of a conversation -- so a cap set on the agent would be spent by the turns
before the one it was meant for, and the tenth round would be cut off for what the first
round did. Which is the very thing :class:`~hmz.coganchor.agents.config.Budget` is held off
the meter to avoid, so nothing here is routed through them.

In a chat, a line goes down the same stream-json input as any other turn's, and that input is
read as Qwen Code's own prompt reads it: each user message is a run of its non-interactive loop,
which dispatches a `/` command before the model sees anything and reads every `@path` into the
turn. So both are passed (:meth:`QwenCodeSession.natives`), the `/` commands being the ones the
`system` record opening each turn lists as its `slash_commands` -- its built-ins allowed
headless, its file commands, its skills and its MCP prompts -- and hence known once a turn has
been taken. `!` is not: its shell mode is a key of the interactive prompt, and the
non-interactive loop sends a line opening with it to the model as words. Nor is anything a
built-in would answer with a dialog; those are not among the commands listed headless.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from hmz import machine
from hmz.coganchor.homes import merged, merger

from ._inputs import snapshot
from .base import AgentBase, CommandSessionBase, SessionBase, StreamSessionBase
from .config import AgentConfig
from .event import Event, Failed, Question, Unrecoverable, Usage
from .hooks import WAITING, Gate, Moment
from .native import NativeCommand
from .preload import preloaded

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pydantic import BaseModel

    from .tools import Toolbox

#: What the CLI is installed as.
_COMMAND = "qwen"

#: The user-level settings file under its home, which a process is started with a copy of in
#: its virtual home, the run's own settings merged in -- the key
#: `hmz.coganchor.backends` names as this CLI's hook seam being one of them.
_SETTINGS = "settings.json"

#: The variables that move the two system layers, which are the machine's and are only read
#: here: a file one of them names is watched like any other settings file.
_SYSTEM = "QWEN_CODE_SYSTEM_SETTINGS_PATH"
_DEFAULTS = "QWEN_CODE_SYSTEM_DEFAULTS_PATH"

#: Where the system layer is when neither variable moves it, by platform, the system defaults
#: beside it: what an administrator sets, read here before a process is started under it.
_MACHINE = {
    "darwin": "/Library/Application Support/QwenCode",
    "win32": "C:\\ProgramData\\qwen-code",
}
_ETC = "/etc/qwen-code"
_MACHINE_DEFAULTS = "system-defaults.json"

#: The variable that moves the user's trusted folders, and the file under their Qwen home
#: otherwise: which folders folder trust, where it is on, lets Qwen Code run above `default`.
_TRUSTED = "QWEN_CODE_TRUSTED_FOLDERS_PATH"
_TRUSTS = "trustedFolders.json"

#: What the server carrying a flow's own callbacks is called among the CLI's MCP servers.
_SERVER = "humanize"

#: What a turn hmz drives defaults to, and the two places Qwen Code itself says otherwise:
#: `general.preventSystemSleep` is on unless it is told, and `general.enableAutoUpdate` is
#: read as on unless it is told `false`. So both of these are Humanize's answer rather than
#: the CLI's, and `QwenCodeAgentConfig.headless_defaults` is where an install takes them back.
#:
#: Neither is about the work, and both are about there being nobody at a terminal: one keeps
#: the machine awake while a person watches an answer arrive -- a `systemd-inhibit` and a
#: `sleep infinity` per model response and per tool call, per session -- and the other would
#: fetch and install a new CLI under a conversation the running one opened, so that a flow
#: three turns in is suddenly talking to a version whose protocol, flags and settings schema
#: nothing here was read against. An unattended turn has nobody to notice either, which is
#: why this is the one place the default is Humanize's and not the CLI's.
#:
#: Said in the virtual home's `settings.json` only where the user's own says nothing of
#: either, so a person who has configured either still gets what they configured.
_HEADLESS = {"general": {"preventSystemSleep": False, "enableAutoUpdate": False}}

#: The format a `settings.json` written here from nothing is in, so that Qwen Code has
#: nothing to migrate in it. One copied from the user's keeps the version theirs is at, and
#: Qwen Code migrates the copy -- which is the virtual home's, and goes with it.
#:
#: Four is the version Qwen Code is at -- `SETTINGS_VERSION = 4`, against which its own
#: `needsMigration` answers no and leaves the file alone. It is worth pinning only for as
#: long as that is true: the number it is at is the only number that means "nothing to do",
#: and one it has moved past is a file it opens every start to migrate. Five it already
#: knows and migrates *down* from, so the pin is checked against the installed CLI rather
#: than assumed to keep.
_VERSION = {"$version": 4}

#: Where V8 keeps what it compiled the CLI's bundle into, so the next process to start reads
#: bytecode rather than compiling the whole bundle again. One directory for the machine, in
#: Humanize's directory for it rather than the home several machines may share: an entry is
#: keyed by the file, its bytes and the Node version, so two flows, two agents and two
#: installed versions share it without reading each other's. Node makes it if it is not there,
#: and a missing or unreadable entry is a compile rather than a failure.
#:
#: Node itself writes nothing unless this is set, so a cache is Humanize's choice and not the
#: runtime's: `QwenCodeAgentConfig.compile_cache` is where an install declines the directory
#: and takes the compile back.
_COMPILED = "NODE_COMPILE_CACHE"
_CACHE = ("compiled", "qwen")

#: What Qwen Code is run at under a fence, as `--approval-mode`: `yolo`, where it asks about
#: nothing but a question for its user, so that the fence holds the grant and what Qwen Code
#: is told is only which of its tools it is started with (:data:`_WRITERS`).
#:
#: Its own ladder does have modes that would hold a grant almost outright -- `plan` for an
#: agent that may change nothing, `auto-edit` for one that edits and asks before it runs, and
#: `auto`, where a model of its own decides. Each of them works by *asking*, and a model
#: deciding is one this protocol does not let near an agent's actions. Run with a prompt for
#: input, Qwen Code knows nobody is there and turns every such ask into a refusal the tool
#: call ends on; run with `stream-json`, it puts each to this driver as a `can_use_tool`
#: control request, and gives up on it a minute later. Every one is answered here
#: (:meth:`QwenCodeSession._answer`), but a mode that asks is still not a way to hold a grant.
#:
#: Written only where there is a fence. An agent driven by hand carries none and is run with
#: no flag at all -- left at whatever `qwen` itself is run at -- since there is no mode for
#: saying nothing: `--approval-mode ""` is a word Qwen Code reads as a mode spelled wrong
#: rather than as a flag withdrawn.
_APPROVAL = "yolo"

#: What it is run at instead in a folder its folder trust has not trusted, which Qwen Code
#: allows nothing above but `plan`: `default`, which asks about every tool that changes
#: something, each request granted as it is asked. Read off the machine before the process
#: is started (:func:`_distrusted`) rather than found out from the turn: Qwen Code moves such
#: a folder down to it whatever it is told.
_DISTRUSTED = "default"

#: The tools Qwen Code's headless `default` refuses outright unless an allow rule names them,
#: named in one so that a turn with nobody to ask -- a shaped turn, whose input is not the
#: protocol -- is granted them too. An allow rule is the grant made before the asking, and
#: a tool withheld stays withheld: Qwen Code reads a deny over an allow.
_ALLOWED = ("run_shell_command", "monitor", "edit", "write_file")

#: The one tool that asks its user something rather than asking leave to run, which `yolo`
#: still puts to the protocol: its answers go back on the same reply as a grant would.
_QUESTION = "ask_user_question"

#: The tools withheld from an agent whose fence writes nothing, by the names Qwen Code calls
#: them: the four that write a file. `save_memory` among them, since what it writes is a
#: `QWEN.md` -- the user's own, which every later session of theirs reads as instructions, at
#: its global scope, and which the fence may well refuse only after the model has decided it
#: remembered something.
#:
#: The shell is kept -- `run_shell_command` reads as much as it writes, a `git log` or a test
#: run being most of what an agent that may change nothing is for, and a write it attempts is
#: refused by the fence around the process rather than by anything Qwen Code is told. So is
#: `monitor`, which runs a command in the background and streams its output back to the
#: model: a shell held open rather than a writer, governed by the same fence the shell is, and
#: no more able than the shell to change what the fence keeps unwritten. Qwen Code's own
#: refusing modes deny it beside the shell, which is the company it keeps here too.
#:
#: Nothing at all is withheld for a fence that writes somewhere -- every tool, the fence
#: deciding where its writes land -- or for an agent with no fence, which is said nothing.
_WRITERS = ("edit", "notebook_edit", "save_memory", "write_file")

#: The two that reach the web, by the names Qwen Code calls them, taken away for an agent
#: told not to search it, whatever its fence lets it write: the network alone decides the web.
#: Told so, rather than left unsaid: an agent nobody has been asked about carries None here
#: and not False, and silence is not a no -- it leaves both tools where `qwen` leaves them.
#:
#: And taken away for an agent whose fence cuts the network, whatever it was told about the
#: web: `web_search` is not a request of the CLI's own but a search agent DashScope runs, on
#: the very host a cut network still lets through for the model, so the proxy would pass it.
_WEB_TOOLS = ("web_search", "web_fetch")

#: What Qwen Code answers with when the request behind the turn never landed: the provider's
#: own error, as the whole of the agent's text, inside a `result` record that says the turn
#: succeeded and an exit status of zero. A loop handed that as an answer would be running on
#: an error message as the work of the turn before it -- and a 401 that reads as a landed turn
#: is an account nothing ever falls back from. The whole of the answer and not a mention of
#: one: an agent that wrote about an API error would have written something else beside it.
_REFUSED = re.compile(r"^\[API Error:(?P<said>.*)\]$", re.DOTALL)

#: What Qwen Code says of a turn held to `--json-schema` whose model wrote its answer out as
#: text rather than handing it to the `structured_output` tool the flag adds. The words are
#: still the answer, and whether they are the shape is for whoever asked to check -- which
#: Humanize does of every shaped turn -- so this one refusal is not a failed turn: a model
#: that answers `{"total": 42}` in prose has answered, and refusing it is refusing the shape
#: for the channel it came down.
_UNSHAPED = "Model produced plain text instead of calling the structured_output tool"

#: What each kind of thing said reads as. `assistant` carries the agent talking and the tools
#: it reached for in the one message; `result` is the turn's own answer and is read for what
#: it cost rather than shown twice.
_SAYS = {"text": "text", "thinking": "reasoning"}

#: And the same two as they are being written, for a turn run with `--include-partial-messages`:
#: Qwen Code puts each fragment in a `stream_event` of its own, under the field its kind of
#: delta is named for. A message arrives whole only once the model has finished it, so
#: without these a turn is silent from the moment it starts thinking to the moment the whole
#: of that thought and the answer after it land together. With them the words arrive as they
#: are written, and the finished message is then read for its tools and its count alone --
#: the same words twice being worse than late words.
_DELTAS = {"text_delta": ("text", "text"), "thinking_delta": ("reasoning", "thinking")}

#: What each kind of token is called in the counts Qwen Code states, and what each of them
#: is here. Humanize's own names rather than the CLI's, as everywhere else a kind is
#: counted: the prices are per kind, so a usage written down under a spelling nothing else
#: knows is a lump nobody can put a figure on -- which is what these were until this table.
#: The cached counts sit beside the input rather than inside it, so the four added up are the
#: whole of what crossed the wire.
#:
#: Its thinking is not a kind of its own. Qwen Code states no count for it on the protocol
#: read here, and what it does state has the thinking inside it -- a turn asked to think at
#: length and answer in one word came back with `output_tokens: 926` -- so a kind for it would
#: be a column of noughts at best and the same tokens counted twice at worst.
_KINDS = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cache_read_input_tokens",
    "cache_write": "cache_creation_input_tokens",
}

#: How many milliseconds a second is, for the one field of Qwen Code's that is counted in
#: them: it took the `timeout` of Claude Code's hook table and not the unit under it.
_A_SECOND = 1000


def _managed(
    effort: str,
    gate: Gate | None = None,
    toolbox: Toolbox | None = None,
) -> dict[str, Any]:
    """What the run itself says in the `settings.json` of its virtual home, over the user's.

    Qwen Code has no flag for how hard to think, nor for a hook table or an MCP server of one
    run's: each is a setting of its own `settings.json`. So they are merged into the user
    level of the virtual home each process is started in (:func:`_merged`), which is a copy of
    the user's own -- and theirs is never written. The user level rather than the system one,
    which is the machine's and is left to it: a system setting of theirs still outranks this.

    Args:
      effort: How hard the turn is to think, as Qwen Code words it.
      gate: Where this agent's moments are served, or None for a turn with nowhere to serve
        them -- and one serving nothing writes no table either.
      toolbox: The flow's own callbacks this agent is offering, or None for none.

    Returns:
      The settings, as a fragment of the file.
    """
    # The rung, where there is one. An agent at none writes no `model` section at all, so
    # Qwen Code reads its own settings for it and the model thinks at whatever that account
    # gives it -- `reasoningEffort: ""` is a value it would read as a rung spelled wrong.
    said: dict[str, Any] = {}
    if effort:
        said["model"] = {"reasoningEffort": effort}
    table = gate.table(WAITING * _A_SECOND) if gate is not None else {}
    if table:
        # Milliseconds, which is the unit Qwen Code reads this number in -- the same spelling
        # Claude Code gave the field, and not the same unit behind it. And the switch that
        # turns every hook off with them, said only here, with a table to carry: it is one
        # setting for the whole of them, so a person who has it on has a flow whose gate
        # quietly does nothing -- and a run with no table to serve has nothing to insist on,
        # so it says nothing and leaves their answer alone.
        said |= {"hooks": table, "disableAllHooks": False}
    if toolbox is not None:
        # The flow's own callbacks, as the one way Qwen Code takes a tool it was not shipped
        # with: a stdio server in `mcpServers`, beside the servers the person has configured
        # rather than in place of them -- bar one of theirs of the same name, which this one
        # stands in for while the run lasts. Trusted, so that reaching for a callback of the
        # flow's is not a confirmation nobody is there to give. What their own settings say
        # of servers in general -- `mcp.allowed`, folder trust -- still holds over this one.
        argv = toolbox.command()
        said["mcpServers"] = {
            _SERVER: {"command": argv[0], "args": argv[1:], "trust": True}
        }
    return said


@merger
def _merged(home: Path, given: dict[str, Any]) -> None:
    """Merges what the run says into a virtual home's copy of the user's `settings.json`.

    What the run says wins for its own entries -- the effort, the `humanize` server, the
    switch that would turn its hooks off -- and nothing of the user's is dropped: their hooks
    stay, the run's after them at each moment, and so do their servers. What a turn nobody is
    watching defaults to (:data:`_HEADLESS`) is said only where their file says nothing of it.

    Args:
      home: The virtual home, whose copy is not there for a user with no file of their own.
      given: `managed`, what the run says, as :func:`_managed` made it; and `headless`,
        whether to say what an unwatched turn defaults to at all.

    Raises:
      Unrecoverable: If the user's file is there and is not a JSON object -- Qwen Code takes
        comments in it, which this cannot keep. Refused rather than written over: a turn run
        against half of somebody's settings is a turn run against settings they never wrote.
    """
    at, managed = home / _SETTINGS, cast("dict[str, Any]", given["managed"])
    try:
        raw: object = json.loads(at.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raw = dict(_VERSION)
    except (OSError, UnicodeError, ValueError) as unread:
        said = (
            f"{_COMMAND}: the user's settings.json cannot be read as plain JSON ({unread}),"
            " so the run's own settings cannot be merged into a copy of it: take its"
            " comments out"
        )
        raise Unrecoverable(1, [_COMMAND], "", said) from unread
    if not isinstance(raw, dict):
        said = f"{_COMMAND}: the user's settings.json is not a JSON object"
        raise Unrecoverable(1, [_COMMAND], "", said)
    held = cast("dict[str, Any]", raw)
    for key, value in managed.items():
        theirs = held.get(key)
        if key == "hooks" and isinstance(theirs, dict):
            ours = cast("dict[str, list[Any]]", value)
            hooks = cast("dict[str, Any]", theirs)
            held[key] = hooks | {
                moment: [*_listed(hooks.get(moment)), *table]
                for moment, table in ours.items()
            }
        elif isinstance(value, dict) and isinstance(theirs, dict):
            held[key] = cast("dict[str, Any]", theirs) | cast("dict[str, Any]", value)
        else:
            held[key] = value
    for key, value in _HEADLESS.items() if given["headless"] else ():
        theirs = held.get(key)
        kept = cast("dict[str, Any]", theirs) if isinstance(theirs, dict) else {}
        held[key] = value | kept
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(json.dumps(held, indent=2) + "\n", encoding="utf-8")


def _listed(said: object) -> list[Any]:
    """A moment's entries of a hook table, or none for anything that is not a list of them."""
    return list(cast("list[Any]", said)) if isinstance(said, list) else []


def _home(environment: dict[str, str], cwd: Path) -> Path:
    """The user's own Qwen home, where their settings and trusted folders are kept."""
    theirs = Path(environment.get("HOME") or Path.home())
    return cwd / Path(environment.get("QWEN_HOME") or theirs / ".qwen").expanduser()


def _loaded(at: Path) -> dict[str, Any]:
    """One settings file as Qwen Code reads it, comments and all, or nothing for none."""
    import json5

    try:
        raw: object = json5.loads(at.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return {}
    return cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}


def _layers(
    environment: dict[str, str], cwd: Path
) -> list[tuple[Path, dict[str, Any]]]:
    """The settings Qwen Code merges that a repository cannot touch, the one that wins first.

    The system layer, the user's, then the system defaults -- read only, as everything of the
    machine's and the user's is here. The workspace's own is not among them: Qwen Code reads
    a folder's trust before it reads that folder's settings at all.

    Args:
      environment: What the process is started with.
      cwd: Where it is started.

    Returns:
      Each file and what it says, `{}` for one that is not there.
    """
    machine = Path(_MACHINE.get(sys.platform, _ETC))
    system = cwd / Path(environment.get(_SYSTEM) or machine / _SETTINGS).expanduser()
    defaults = (
        cwd
        / Path(
            environment.get(_DEFAULTS) or system.parent / _MACHINE_DEFAULTS
        ).expanduser()
    )
    return [
        (at, _loaded(at))
        for at in (system, _home(environment, cwd) / _SETTINGS, defaults)
    ]


def _setting(
    layers: list[tuple[Path, dict[str, Any]]], *keys: str
) -> tuple[Path, object] | None:
    """The file that decides one setting, and what it says, or None where none says it."""
    for at, held in layers:
        if (said := _under(held, keys)) is not None:
            return at, said
    return None


def _under(said: object, keys: tuple[str, ...]) -> object:
    """What one file says under a path of keys, or None where it says nothing there."""
    for key in keys:
        said = (
            cast("dict[str, object]", said).get(key) if isinstance(said, dict) else None
        )
    return said


def _unhooked(
    layers: list[tuple[Path, dict[str, Any]]], cwd: Path, *, trusted: bool
) -> Path | None:
    """The file that turns every hook off over the run's own `false`, or None for none.

    The system layer, and the workspace's under it where Qwen Code reads that at all, which
    is in a folder it trusts: both outrank the user layer the run's own settings are in.

    Args:
      layers: What :func:`_layers` read.
      cwd: Where the process is started.
      trusted: Whether Qwen Code trusts `cwd`.

    Returns:
      The file, or None where hooks stay on.
    """
    ranked = layers[:1]
    if trusted:
        workspace = cwd / ".qwen" / _SETTINGS
        ranked.append((workspace, _loaded(workspace)))
    said = _setting(ranked, "disableAllHooks")
    return said[0] if said is not None and said[1] is True else None


def _distrusted(
    layers: list[tuple[Path, dict[str, Any]]], environment: dict[str, str], cwd: Path
) -> Path | None:
    """The file that turns folder trust on, where `cwd` is not a folder it trusts.

    Qwen Code runs such a folder at `default` or `plan` whatever it is told. A folder is
    trusted only by a rule of the user's trusted folders: the deepest rule over it decides,
    `TRUST_PARENT` speaking for the folder it names the parent of, and a distrust wins a tie.

    Args:
      layers: What :func:`_layers` read.
      environment: What the process is started with.
      cwd: Where it is started.

    Returns:
      The file, or None for a folder Qwen Code will run above `default`.
    """
    said = _setting(layers, "security", "folderTrust", "enabled")
    if said is None or said[1] is not True:
        return None
    at = Path(environment.get(_TRUSTED) or _home(environment, cwd) / _TRUSTS)
    where = _variants(str(cwd))
    deepest, trusted = -1, False
    for named, level in _loaded(cwd / at.expanduser()).items():
        if level == "TRUST_PARENT":
            # The folder it names the parent of, a trailing separator not being a folder.
            root = os.path.dirname(named.rstrip(os.sep + (os.altsep or "")) or named)  # noqa: PTH120
            says = True
        elif level in ("TRUST_FOLDER", "DO_NOT_TRUST"):
            root, says = named, level == "TRUST_FOLDER"
        else:
            continue
        for over in _variants(root):
            depth = len(Path(over).parts) - 1
            if any(Path(one).is_relative_to(over) for one in where) and (
                depth > deepest or (depth == deepest and not says)
            ):
                deepest, trusted = depth, says
    return None if trusted else said[0]


def _variants(path: str) -> set[str]:
    """One path as it is spelled and as it resolves, either of which a rule may name."""
    return {
        os.path.normcase(os.path.abspath(path)),  # noqa: PTH100 -- a spelling, not a Path
        os.path.normcase(os.path.realpath(path)),
    }


def _asked(config: AgentConfig, named: str, *, default: bool) -> bool:
    """Whether one of Qwen Code's own options is on for this agent.

    Read off the config by name rather than off :class:`QwenCodeAgentConfig`, because an agent
    written as the common :class:`AgentConfig` is still driven here: what it gets is the
    option's own default, which is what an install that has said nothing is entitled to.

    Args:
      config: The agent's configuration, whichever class it was written as.
      named: The field to read.
      default: What the answer is for a config that has no such field.

    Returns:
      Whether it is on.
    """
    return bool(getattr(config, named, default))


class QwenCodeSession(StreamSessionBase):
    """A Qwen Code conversation, named where it is opened and resumed by that name after.

    `--session-id` is what names it, and a fresh one per attempt is what makes that safe:
    Qwen Code refuses an id that is already a session of this project, active or archived,
    and ends the run before the turn rather than joining it. So an opening turn is given an
    id nothing has been called yet and every turn after resumes that one -- and an opening
    turn that failed is retried under another, rather than colliding forever with the session
    its own first attempt may have left behind.

    Chosen rather than read back off the stream, which is what it was: an id the CLI minted
    for itself is one nothing out here knows until a turn has landed, and what the stream says
    is then a confirmation of the name rather than the only place it exists.
    """

    #: What it writes on stdout is the turn as events rather than the agent talking.
    protocol: ClassVar[bool] = True

    #: `--json-schema` is a setting of the run: the turn is held to the shape by a tool of the
    #: CLI's own making rather than by being asked for it in the prompt.
    shapes: ClassVar[bool] = True

    #: `mcpServers` in the settings file the run is already pointed at, so a flow's own
    #: callbacks reach this turn without anything of the person at this machine's being
    #: written.
    takes_tools: ClassVar[bool] = True

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session that has run no turn yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        #: What the agent has said so far in the turn now running, and what it answered with.
        #: The answer is the `result` record rather than the last thing said: a turn that ends
        #: on a tool has still answered.
        self._said = ""
        self._failed: str | None = None
        #: The last thing the agent wrote in the turn now running, whole, which is the answer
        #: a shaped turn gave where it wrote rather than handed it to its tool.
        self._written = ""
        #: Whether that is what the turn now running answered with, which Qwen Code exits
        #: nonzero for.
        self._unshaped = False
        #: What the turn now running has cost, and which parts of it have been shown -- one
        #: message is said once, and a stream that repeats it would show it twice.
        self._costing = Usage()
        #: Terminal summaries replay the conversation's totals even after a process restart.
        self._total = Usage()
        self._shown: set[str] = set()
        self._announced: str | None = None
        #: What this process was told to call the conversation it is opening, or None for one
        #: resuming a conversation that has a name already. Kept rather than spent on the
        #: command line, so that a turn which landed without a record naming its session is
        #: still a turn whose session can be named: the id was ours before it was the CLI's.
        self._minted: str | None = None
        self._launched: tuple[object, ...] | None = None
        self._requested: tuple[object, ...] = ()
        #: Whether this turn has had any of its words off the partial stream. Read where the
        #: finished message is: that message repeats every fragment of itself, so a turn that
        #: has been reading them takes the tools and the count from it and leaves the words.
        #: Watched rather than assumed from the option, because the option is what the next
        #: process is started with and this is what the one now talking was.
        self._fragmented = False
        #: Whether the settings file this turn is run against holds a hook table. Written
        #: where that file is built and read where a moment is about to be said off the
        #: stream: a gate outlives the hook that asked for it, so a turn that was not given a
        #: table has to go on saying the moment itself rather than leaving it to a CLI that
        #: was never told to ask.
        self._tabled = False
        #: The `/` commands the CLI said it serves headless, as the last `system` record
        #: opening a turn listed them: none until a turn has been taken.
        self._commands: tuple[str, ...] = ()
        #: What the process is run at under a fence: :data:`_APPROVAL`, or what the machine's
        #: settings leave it (:meth:`_policy`).
        self._mode = _APPROVAL

    def natives(self) -> list[NativeCommand]:
        """What a chat's line may open with here: the CLI's own `/` commands, and `@`.

        Both passed: the stream-json input runs each message through the same dispatch the
        CLI's own prompt does (see the module). The commands are the ones the `system` record
        opening the last turn listed, so a session that has taken no turn yet has only `@`.

        Returns:
          A `/` entry per command the CLI listed, then `@`.
        """
        return [
            *(
                NativeCommand("/", name, f"Qwen Code's /{name}", "pass")
                for name in self._commands
            ),
            NativeCommand("@", "", "A file or directory, read into the turn", "pass"),
        ]

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Keeps plain turns warm, and resumes shaped turns in a command of their own."""
        with self._lock:
            instead = self._policy()
        if instead:
            yield Event(kind="notice", text=instead)
        if schema is not None:
            with self._lock:
                self._shut()
                # The finite command transport checks the process's exit status after its
                # result too. Reuse it on this same session state: a helper session would
                # register a second conversation and count its opening twice.
                yield from CommandSessionBase._stream(  # noqa: SLF001 -- shared turn transport
                    cast("CommandSessionBase", self), prompt, schema=schema
                )
            return
        with self._lock:
            self._requested = self._settings()
            try:
                yield from super()._stream(prompt)
            except BaseException:
                self._shut()
                raise

    def _policy(self) -> str:
        """Reads what the machine's settings leave this agent, before a process is started.

        Read off the files Qwen Code itself merges, without a turn: a hook table the system
        layer turns off is a flow that could not refuse a tool before it runs, and a folder
        folder trust has not trusted is one Qwen Code runs at `default` whatever it is told,
        so it is told :data:`_DISTRUSTED` outright and every request it asks is granted
        (:meth:`_answer`). Not for an anchored turn, whose files are another machine's: what
        it asks is granted there all the same, and what it runs at is said by its `init`.

        Returns:
          What to say about the mode it runs at instead, the first time for the agent, or "".

        Raises:
          Unrecoverable: If a pre-tool-use hook is hung and the system layer turns hooks off.
        """
        self._mode = _APPROVAL
        if self._agent.anchor is not None:
            return ""
        environment = self._environ() or dict(os.environ)
        cwd = Path(self.cwd)
        layers = _layers(environment, cwd)
        distrusted = _distrusted(layers, environment, cwd)
        if (
            self._agent.hooks.hooked(Moment.PRE_TOOL_USE)
            and (at := _unhooked(layers, cwd, trusted=distrusted is None)) is not None
        ):
            said = (
                f"{_COMMAND}: {at} sets disableAllHooks, which outranks the run's own"
                " settings, so no hook of this flow's could refuse a tool before it runs"
            )
            raise Unrecoverable(1, [_COMMAND], "", said)
        if self._agent.config.fence is None or distrusted is None:
            return ""
        self._mode = _DISTRUSTED
        return self._shifted(
            self._mode,
            f"{distrusted} turns folder trust on and {cwd} is not a trusted folder",
        )

    def _shifted(self, mode: str, why: str) -> str:
        """What to say of an agent run at `mode` rather than `yolo`, once an agent and mode."""
        agent = self._agent
        if isinstance(agent, QwenCodeAgent) and not agent.moved(mode):
            return ""
        return f"{_COMMAND}: {why}, so it runs at {mode}, where what it asks is granted"

    def _command(self) -> list[str]:
        """Builds the official NDJSON command with the current turn configuration."""
        argv, _ = self._turn("")
        return [*argv, "--input-format", "stream-json"]

    def _settings(self) -> tuple[object, ...]:
        """The settings and flow resources the process reads when it starts.

        The names of the callbacks in front of the agent among them: Qwen Code lists what an
        MCP server has when it starts it and holds that list for the life of the process, so
        a flow offering another between two turns is answered by a process that was told.
        And what the run says in its virtual home's settings (:meth:`_managing`): a hook hung
        or taken down moves the table, and a moved table is a process started again under it.
        """
        environment = self._environ() or dict(os.environ)
        native = self._native(environment)
        return (
            self._agent.config,
            self._mode,
            self.effort,
            self._carrying(),
            self._agent.toolbox.names(),
            environment,
            json.dumps(self._managing(), sort_keys=True),
            native if native is not None else object(),
        )

    def _native(self, environment: dict[str, str]) -> bytes | None:
        """Snapshots native settings and skills without modifying the CLI's own files.

        Settings with syntax this reader cannot interpret still reach Qwen unchanged; their
        processes restart between turns so undiscovered custom skill paths cannot go stale.
        """
        cwd = Path(self.cwd)
        theirs = Path(environment.get("HOME") or Path.home())
        qwen = _home(environment, cwd)
        # The user's own home rather than the virtual one a process is started in, which is
        # made of it: its `settings.json` is a copy of theirs, and the rest links to theirs.
        # And a system layer the machine names, which is the machine's and is watched as any
        # other settings file is; one it does not name is where Qwen Code keeps it, untouched.
        settings = {qwen / _SETTINGS, cwd / ".qwen" / _SETTINGS}
        settings.update(
            cwd / Path(named).expanduser()
            for named in (environment.get(_SYSTEM), environment.get(_DEFAULTS))
            if named
        )
        paths = set(settings)
        roots = (cwd, *cwd.parents, theirs)
        for root in roots:
            paths.update(root / name for name in ("QWEN.md", "AGENTS.md", ".env"))
            paths.update(root / name / "skills" for name in (".qwen", ".agents"))
        paths.update(
            qwen / name
            for name in (
                "skills",
                "commands",
                "agents",
                "extensions",
                "QWEN.md",
                ".env",
            )
        )
        for path in settings:
            try:
                raw: object = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                continue
            except (OSError, UnicodeError, ValueError):
                return None
            if not isinstance(raw, dict):
                return None
            data = cast("dict[str, Any]", raw)
            skills = data.get("skills")
            if isinstance(skills, dict):
                directories = cast("dict[str, Any]", skills).get("directories", [])
                if isinstance(directories, list):
                    paths.update(
                        cwd / Path(value).expanduser()
                        for value in cast("list[object]", directories)
                        if isinstance(value, str)
                    )
            context = data.get("context")
            if isinstance(context, dict):
                names = cast("dict[str, Any]", context).get("fileName", [])
                names = [names] if isinstance(names, str) else names
                if isinstance(names, list):
                    paths.update(
                        root / name
                        for root in roots
                        for name in cast("list[object]", names)
                        if isinstance(name, str)
                    )
        return snapshot(paths)

    def _asking(self, moment: Moment) -> bool:
        """Whether the Qwen Code running this conversation was pointed at a table of its own.

        What the file the process was started against holds rather than what is hung now: a
        hook hung after it started is one this process will never stop to ask about, and the
        moment has to go on being read off this turn's own stream until the turn after has
        started one that was told.

        Args:
          moment: The moment.

        Returns:
          True where this process asks about it and waits to be told.
        """
        return self._tabled and super()._asking(moment)

    def _stale(self) -> bool:
        """Restarts before settings or mounted flow resources change."""
        return self._launched is not None and self._launched != self._requested

    def _restarted(self) -> None:
        """Records what the newly started process was actually given."""
        self._launched = self._requested

    def _write(self, text: str, ticket: str = "") -> str:
        """Encodes the direct-mode user message Qwen queues as one complete turn."""
        del ticket
        return (
            json.dumps({"type": "user", "message": {"role": "user", "content": text}})
            + "\n"
        )

    def interject(self, text: str) -> None:
        """Keeps existing steering behavior until Qwen can acknowledge delivery."""
        SessionBase.interject(self, text)

    def _read(self, line: str) -> Iterator[Event]:
        """Finishes a persistent turn when Qwen writes its result record."""
        try:
            raw: object = json.loads(line)
        except ValueError:
            return
        if not isinstance(raw, dict):
            return
        said = cast("dict[str, Any]", raw)
        if said.get("type") == "control_request":
            # Qwen Code waits on the answer, and gives the tool up a minute later.
            self._answer(said)
            return
        yield from self._record(said)
        if named := said.get("session_id"):
            self._announced = str(named)
        if said.get("type") == "result":
            result = self._result(line)
            if self._id is None:
                self._adopt(
                    self._announced or self._minted or self._read_session_id(line)
                )
            yield result

    def _answer(self, said: dict[str, Any]) -> None:
        """Answers one control request of Qwen Code's: a tool it asks leave for is granted.

        Whatever mode it runs at, what it still asks about is granted -- the fence holds the
        grant, and what the machine's own settings deny Qwen Code refuses before it asks. A
        question for its user is put to whoever answers for this agent, by number, as Qwen
        Code reads its answers; one nobody answers is refused rather than left waiting.

        Args:
          said: The `control_request`, as read.
        """
        asked = cast("dict[str, Any]", said.get("request") or {})
        if asked.get("subtype") != "can_use_tool":
            self._reply(said, None)
            return
        answer: dict[str, Any] = {"behavior": "allow"}
        called = cast("dict[str, Any]", asked.get("input") or {})
        if asked.get("tool_name") == _QUESTION:
            answers: dict[str, str] = {}
            for index, raw in enumerate(
                cast("list[Any]", called.get("questions") or [])
            ):
                question = cast("dict[str, Any]", raw) if isinstance(raw, dict) else {}
                offered = tuple(
                    str(cast("dict[str, Any]", option)["label"])
                    for option in cast("list[Any]", question.get("options") or [])
                    if isinstance(option, dict)
                    and cast("dict[str, Any]", option).get("label")
                )
                wanted = str(question.get("question") or question.get("header") or "")
                got = self._agent.asked(Question(text=wanted, options=offered))
                if got is None:
                    self._reply(
                        said, {"behavior": "deny", "message": "nobody answered"}
                    )
                    return
                answers[str(index)] = got
            answer["updatedInput"] = {**called, "answers": answers}
        self._reply(said, answer)

    def _reply(self, said: dict[str, Any], answer: dict[str, Any] | None) -> None:
        """Writes one answer back to Qwen Code, or an error for a request not served here."""
        named = said.get("request_id")
        response: dict[str, Any] = (
            {"subtype": "success", "request_id": named, "response": answer}
            if answer is not None
            else {"subtype": "error", "request_id": named, "error": "not served here"}
        )
        self._send(
            json.dumps({"type": "control_response", "response": response}) + "\n"
        )

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds the `qwen` one turn is, and hands it the prompt on stdin.

        On stdin rather than as an argument: a prompt is a paragraph and may open with a dash,
        neither of which belongs on a command line. Qwen Code takes what is on stdin as the
        prompt when it is given none of its own, which is what makes the turn headless -- and
        which is now the only way to say it, `-p/--prompt` having been deprecated in favour of
        the positional a paragraph cannot safely be.

        Args:
          prompt: The input prompt for this turn.

        Returns:
          The command and the prompt to write to it.
        """
        self._said, self._failed, self._shown = "", None, set()
        self._written, self._unshaped = "", False
        self._costing = Usage()
        self._fragmented = False
        if self._id is None:
            # A failed opening turn did not adopt its conversation; retrying opens another.
            self._total = Usage()
        self._announced = None
        argv = [
            _COMMAND,
            "--output-format",
            "stream-json",
            "--model",
            self._agent.config.model,
        ]
        fence = self._agent.config.fence
        if fence is not None:
            # Everything the fence leaves is approved without being asked: a flow watches its
            # agent rather than gating it. And where there is no fence, no flag: an agent
            # driven by hand is started with neither and runs at whatever `qwen` runs at.
            argv += ["--approval-mode", self._mode]
            if self._mode == _DISTRUSTED:
                argv += ["--allowed-tools", ",".join(_ALLOWED)]
        if _asked(self._agent.config, "partial_messages", default=False):
            # Off in the CLI and off here, because it is a different stream to read rather
            # than more of the same one, and an install that says nothing gets what `qwen`
            # itself does. On, the words arrive as the model writes them.
            argv += ["--include-partial-messages"]
        withheld: list[str] = []
        if fence is not None and not fence.writes:
            withheld += _WRITERS
        if self._agent.config.web_search is False or (
            fence is not None and not fence.online
        ):
            # Decided by the network alone, whatever the fence lets the agent write.
            withheld += _WEB_TOOLS
        if withheld:
            argv += ["--exclude-tools", ",".join(withheld)]
        if (schema := self._shaping) is not None:
            # The shape as the CLI takes it: a JSON literal on the command line, which it
            # holds the last message to rather than asking the model to keep to.
            argv += ["--json-schema", json.dumps(schema.model_json_schema())]
        argv += self._holding()
        return argv, prompt

    def _holding(self) -> list[str]:
        """Which conversation this process is to be holding: this one, a fork, or a new one.

        Three ways in, and the flag says which. A session with an id resumes it. A fork has no
        id of its own yet and the id of the one it was cut from: `--fork-session` is `--resume`
        told to mint a new id rather than write on into the one it was handed, which is what
        makes Qwen carry those turns into a session of its own. Anything else is a conversation
        that does not exist yet, and is named here.

        Returns:
          The flags, to go on the command line as they are.
        """
        self._minted = None
        if self._id is not None:
            return ["--resume", self._id]
        if self._forked_from is not None:
            return ["--resume", self._forked_from, "--fork-session"]
        # A fresh id per attempt: Qwen Code refuses an id that is already a session of this
        # project, and an opening turn that failed may still have left it holding the one it
        # was given -- retrying under that id would collide with itself forever.
        self._minted = str(uuid.uuid4())
        return ["--session-id", self._minted]

    def _environment(self) -> dict[str, str]:
        """What the turn runs with: the provider's, where Node caches the CLI, and the preload.

        Where the CLI's compiled bundle is kept between processes, unless whoever started the
        flow has said where themselves: a session a turn is a Node process a turn, and eight
        of them starting at once compile the same bundle eight times.

        And the preload, for an agent something is listening to: Qwen Code is a Node program, so
        what a turn of it actually runs, reads, writes and opens can be read from inside the process
        it runs in. :mod:`hmz.coganchor.agents.preload` is what decides whether one is wanted.

        What it is to think at, its hook table and the flow's callbacks are not variables: they
        are in its virtual home's `settings.json` (:meth:`_merges`).
        """
        held = dict(super()._environment())
        # Whoever said where, said it: the provider's own variables are in `held` and the
        # flow's are in this process's environment, and either outranks a cache of ours.
        # And not for an anchored turn: it runs on another machine, where a path named from
        # this one is a directory that is either absent there or somebody else's.
        if _asked(self._agent.config, "compile_cache", default=True) and not (
            held.get(_COMPILED)
            or os.environ.get(_COMPILED)
            or self._agent.anchor is not None
        ):
            # A machine directory that is not this user's alone is a cache unmade, not a turn
            # refused: the compile it would have saved is all that is lost.
            with contextlib.suppress(OSError):
                held[_COMPILED] = str(machine().joinpath(*_CACHE))
        return preloaded(self._agent, held)

    def _managing(self) -> dict[str, Any]:
        """What the run says in its virtual home's `settings.json`, as :func:`_managed` makes it.

        The hook table only where it can be served: a `PreToolUse` read off the stream this
        session reads arrives after Qwen Code has announced the tool and is about to run it,
        and Qwen Code's own table is the one place it stops and waits to be told. Not for an
        anchored turn, whose `qwen` runs on another machine and could not reach the socket the
        relay carries the moment to -- and not for an agent with nothing hung on that moment:
        a table is a program the CLI starts and waits for before every tool it runs, so
        writing one for hooks that are not there is a relay spawned per file read, one after
        another, for nobody.
        """
        gate = (
            self._agent.hooks.gate()
            if self._agent.anchor is None
            and self._agent.hooks.hooked(Moment.PRE_TOOL_USE)
            else None
        )
        self._tabled = gate is not None and gate.serving
        box = self._agent.toolbox
        return _managed(self.effort, gate, box if box.offered() else None)

    def _merges(self) -> tuple[tuple[str, str], ...]:
        """What :meth:`_managing` says, merged into the virtual home's copy of `settings.json`.

        The home is the user's own as :mod:`hmz.coganchor.homes` builds it -- a copy of their
        `settings.json`, links to everything else, the flow's skills beside theirs -- wherever
        the CLI runs, a harness's own machine among them (:func:`_merged`).
        """
        return (
            merged(
                _merged, {"managed": self._managing(), "headless": self._headless()}
            ),
        )

    def _headless(self) -> bool:
        """Whether this turn is given the layer saying what an unwatched turn defaults to."""
        return _asked(self._agent.config, "headless_defaults", default=True)

    def _reads(self, line: str, *, error: bool) -> Iterator[Event]:
        """Reads one record Qwen Code wrote, as the things it says the agent did.

        Args:
          line: The line, as written.
          error: Whether it came from stderr, which is the CLI's own log rather than the turn
            -- kept for a failed turn's diagnostic and shown nowhere.

        Yields:
          What it said, which is nothing for a record saying nothing worth showing.
        """
        if error:
            return
        try:
            said: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            return  # not ours: the odd plain line among the JSON
        yield from self._record(said)

    def _record(self, said: dict[str, Any]) -> Iterator[Event]:
        """Maps the records shared by the finite and persistent protocols."""
        if self._id is None and (named := said.get("session_id")):
            # Named on every record it writes: the run's from the first of them, whose log it
            # is whether or not the turn lands.
            self._tells(str(named))
        kind = str(said.get("type") or "")
        if kind == "system" and said.get("subtype") == "init":
            running = str(said.get("permission_mode") or "")
            if (
                self._agent.config.fence is not None
                and running
                and running != self._mode
                # Moved there by something read beforehand did not see: an IDE's trust, say.
                and (
                    instead := self._shifted(
                        running, f"it moved itself off {self._mode}"
                    )
                )
            ):
                yield Event(kind="notice", text=instead)
            listed = said.get("slash_commands")
            if isinstance(listed, list):
                # Replaced whole rather than added to: what a turn opens on is what the CLI
                # serves now, a command file removed since being one it no longer does.
                self._commands = tuple(
                    one
                    for one in cast("list[object]", listed)
                    if isinstance(one, str) and one
                )
        elif kind == "assistant":
            yield from self._message(cast("dict[str, Any]", said.get("message") or {}))
        elif kind == "stream_event":
            yield from self._fragment(cast("dict[str, Any]", said.get("event") or {}))
        elif kind == "result":
            # The turn's own answer, which is what it ends on. Held rather than shown: the
            # agent already said these words as it said them.
            self._said = str(said.get("result") or "")
            total = self._cost(cast("dict[str, Any]", said.get("usage") or {}))
            # The terminal record summarizes prior requests, including resumed history.
            # Message counters are authoritative, even when explicitly zero. Only a kind
            # absent from them needs the summary's increment as a fallback.
            missing: dict[str, float] = {}
            for name, tokens in total.items():
                if name not in self._costing:
                    previous = self._total.get(name, 0.0)
                    missing[name] = tokens - previous if tokens >= previous else tokens
            self._costing = self._costing + Usage(missing)
            # Errors also settle the counters: their cost belongs to that failed turn.
            self._total = Usage({**self._total, **total})
            if said.get("is_error"):
                failed: dict[str, Any] = said.get("error") or {}
                message = str(failed.get("message") or "")
                if message.startswith(_UNSHAPED) and self._written.strip():
                    self._said, self._unshaped = self._written, True
                else:
                    self._failed = message or json.dumps(said)

    def _message(self, message: dict[str, Any]) -> Iterator[Event]:
        """Reads one message the model produced, which is text and tools together.

        Args:
          message: The `message` of an `assistant` record, as read.

        Yields:
          What it said and what it reached for, each part once.
        """
        marked = str(message.get("id") or "")
        # A message said twice is the stream repeating itself rather than the agent saying it
        # again -- but only an id tells them apart, so one that names itself with nothing is
        # shown rather than taken for the last one.
        if marked:
            if marked in self._shown:
                return
            self._shown.add(marked)
        # What the turn answered with is the last message's words, so an earlier message's --
        # narration ahead of a tool, say -- is not left standing for a later one with none.
        self._written = ""
        # Counted once where it is reported: each message carries one request's usage.
        self._costing = self._costing + self._cost(
            cast("dict[str, Any]", message.get("usage") or {})
        )
        for one in cast("list[Any]", message.get("content") or []):
            if not isinstance(one, dict):
                continue
            part = cast("dict[str, Any]", one)
            kind = str(part.get("type") or "")
            if kind == "tool_use":
                yield Event(kind="tool", text=_called(part))
            elif (says := _SAYS.get(kind)) is not None:
                words = str(part.get("text") or part.get("thinking") or "")
                if says == "text" and words.strip():
                    self._written = words
                # Said already, a fragment at a time, for a turn reading the partial stream:
                # the finished message repeats every word of it, and the whole point of
                # reading them early was to read them once.
                if words.strip() and not self._fragmented:
                    yield Event(kind=says, text=words)

    def _fragment(self, event: dict[str, Any]) -> Iterator[Event]:
        """Reads one fragment of a message still being written, for a turn that asked.

        Only the words: what the model reaches for arrives whole in the message that follows,
        with the arguments it reached with, and a tool announced twice is a transcript with
        the same call in it twice.

        Args:
          event: The `event` of a `stream_event` record, as read.

        Yields:
          What was written, which is nothing for a fragment carrying no words.
        """
        if str(event.get("type") or "") != "content_block_delta":
            return
        delta = cast("dict[str, Any]", event.get("delta") or {})
        said = _DELTAS.get(str(delta.get("type") or ""))
        if said is None:
            return
        kind, field = said
        if words := str(delta.get(field) or ""):
            self._fragmented = True
            yield Event(kind=kind, text=words)

    def _cost(self, counted: dict[str, Any]) -> Usage:
        """What one request cost, by the kind each token went on.

        Every kind counts: what a rate is measuring is the traffic, and a cache read crosses
        the wire like anything else.

        Args:
          counted: A `usage`, as read.

        Returns:
          What it spent.
        """
        return Usage(
            {
                kind: float(counted.get(named) or 0)
                for kind, named in _KINDS.items()
                if counted.get(named) is not None
            }
        )

    def _excused(self) -> bool:
        """Whether the turn exited nonzero only for a shape it wrote out rather than handed over."""
        return self._unshaped

    def _result(self, transcript: str) -> Event:
        """The turn's answer, and what it cost, out of the records it wrote.

        Args:
          transcript: The whole of stdout, already read record by record.

        Returns:
          The `result` the turn ends on.

        Raises:
            subprocess.CalledProcessError: If the turn failed. Qwen Code says so in its own
              records as well as in its exit status -- a model that refused comes back as an
              exit of zero -- and a loop fed that as an answer would be running on it as the
              work of the turn. Sometimes it says so in neither: a request the provider
              answered 401 or 429 comes back as a `result` marked a success whose whole text
              is the error, which is read here as the failure it is.
        """
        refused = _REFUSED.match(self._said.strip())
        if self._failed is None and refused is not None:
            self._failed = refused["said"].strip()
        if self._failed is not None:
            raise Failed(1, [_COMMAND], self._said, self._failed)
        if not transcript.strip():
            raise Failed(1, [_COMMAND], "", f"{_COMMAND} said nothing at all")
        spent = int(self._costing.total)
        return Event(
            kind="result",
            text=self._said.strip(),
            tokens={self._agent.config.model: spent} if spent > 0 else {},
            spent=self._costing,
        )

    def _read_session_id(self, transcript: str) -> str:
        """Reads back the session Qwen Code opened, which every record of the turn names.

        Args:
          transcript: Everything the turn printed.

        Returns:
          The session's id.

        Raises:
          ValueError: If nothing the turn wrote names one, which is a turn that landed
            somewhere nobody can find again.
        """
        for line in transcript.splitlines():
            try:
                said: object = json.loads(line)
            except ValueError:
                continue
            if isinstance(said, dict) and (
                named := cast("dict[str, Any]", said).get("session_id")
            ):
                return str(named)
        raise ValueError(f"{_COMMAND} named no session")


def _called(part: dict[str, Any]) -> str:
    """One tool call as the one line a row of a transcript has room for.

    Args:
      part: The `tool_use` block, as read.

    Returns:
      What it reached for and what with.
    """
    given: dict[str, Any] = part.get("input") or {}
    about = next(
        (
            str(value)
            for value in given.values()
            if isinstance(value, str) and value.strip()
        ),
        "",
    )
    return f"{part.get('name') or 'tool'} {about}".strip()[:120]


@dataclass(frozen=True, kw_only=True)
class QwenCodeAgentConfig(AgentConfig):
    """What Qwen Code is configured with: the common model and effort, and its own three.

    The model is written as Qwen Code writes it, which is the id its endpoint serves -- it is
    an OpenAI-compatible client, so what it runs is what the account behind it offers.

    The three below are every place this driver settles something Qwen Code would otherwise
    have settled for itself, so that an install which sets none of them can read what it is
    getting instead of finding out. Two of them default to Humanize's answer rather than the
    CLI's, and say why; the third is the CLI's own.

    Attributes:
      headless_defaults: Whether to write the layer Qwen Code reads under everyone, saying
        that a turn nobody is watching neither holds the machine awake nor updates the CLI
        under itself. On, which is the one place this driver's default is not the bare CLI's:
        Qwen Code keeps the machine awake and checks for a new version to install, both of
        which are right for a person at a terminal and neither of which an unattended turn
        has anybody to notice -- an update landing mid-flow puts a CLI whose flags, protocol
        and settings schema nothing here was read against under a conversation already open.
        Off leaves the layer unwritten and Qwen Code's own answer standing. Either way a
        person who has configured either, at any layer of their own, still wins.
      compile_cache: Whether to point Node at one directory for what it compiled the CLI's
        bundle into. On, which is again Humanize's answer and not Node's -- Node caches
        nothing unless it is told where -- because a session here is a Node process a turn,
        and eight starting at once compile the same megabytes eight times. Off takes the
        compile back. A `NODE_COMPILE_CACHE` the flow or the provider already set wins over
        this either way, and an anchored turn is never given one: it runs where a path named
        from here is absent or somebody else's.
      partial_messages: Whether the turn's words arrive as the model writes them, which is
        `--include-partial-messages`. Off, as it is in the CLI: a message otherwise arrives
        whole and only once it is finished, so a turn is silent from the moment it starts
        thinking until that thought and the answer after it land together. On for a flow
        showing a turn to somebody while it runs; the finished message is then read for its
        tools and its count alone, so nothing is said twice.
    """

    headless_defaults: bool = True
    compile_cache: bool = True
    partial_messages: bool = False


class QwenCodeAgent(AgentBase):
    """Qwen Code, driven through its own command line, one run per turn."""

    #: What it counts, read off the same table its driver reads a usage with, so that what
    #: a run is told this backend reports is what its driver actually parses.
    counts: ClassVar[frozenset[str]] = frozenset(_KINDS)

    def __init__(self, config: AgentConfig, *, name: str | None = None) -> None:
        """Initializes an agent that has said nothing yet of the mode it runs at.

        Args:
          config: The model and effort every session of this agent runs at.
          name: What to call this agent, defaulting to one nothing else answers to.
        """
        super().__init__(config, name=name)
        self._modes: set[str] = set()
        self._noting = threading.Lock()

    def moved(self, mode: str) -> bool:
        """Notes that this agent runs at `mode` rather than `yolo`.

        Args:
          mode: What it runs at.

        Returns:
          Whether this is the first anybody has heard of it, and so something to say.
        """
        with self._noting:
            if mode in self._modes:
                return False
            self._modes.add(mode)
            return True

    def new(self, cwd: str | os.PathLike[str] | None = None) -> QwenCodeSession:
        """Opens a new Qwen Code session, in the directory it is given or in this one."""
        return QwenCodeSession(self, cwd)
