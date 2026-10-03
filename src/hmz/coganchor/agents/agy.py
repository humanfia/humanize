"""Antigravity CLI held across ordinary turns through its official NDJSON protocol.

Slash commands and shaped turns use finite commands, preserving the CLI's print-mode
behavior. Native cumulative usage follows the conversation across both transports and
process restarts; each result here reports only its own turn's cost.
"""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
import math
import os
import re
import threading
from dataclasses import dataclass, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

from hmz.coganchor import backends

from ._inputs import snapshot
from .base import AgentBase, CommandSessionBase, SessionBase, StreamSessionBase
from .config import UNSAID, AgentConfig, Unserved
from .event import Event, Failed, Saying, Usage

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pydantic import BaseModel

    from hmz.coganchor.fence import Fence

#: What the CLI is installed as. The tarball calls the file `antigravity` and the installer
#: puts it down under this name, which is what a command line reaches for.
_COMMAND = "agy"

#: What a turn is run as at each rung of the ladder, in the CLI's own flags. Read off `agy
#: --help` and the CLI's own wording for its modes, last checked against agy 1.2.2 on
#: 2026-09-15: `--mode plan` is "research and plan without making changes", `--mode
#: accept-edits` is "auto-approve file edits, prompt for commands", and
#: `--dangerously-skip-permissions` is the one where nothing is asked at all.
#:
#: `plan` is not what holds `read-only` to reading, though: agy 1.2 in plan mode writes the
#: file it is asked to. What does is :data:`_READER`, the agent a turn at that rung is started
#: as, whose tools read and do nothing else.
#:
#: The prompting is nobody's to answer here, and that is what makes the two tighter rungs real
#: rungs rather than turns that hang on them: a print-mode run soft-denies the tool it was not
#: permitted to take and names it under `denied_actions` instead of waiting for an answer. So
#: `workspace-write` lands tighter than the word -- its edits go through and its commands are
#: refused -- which is the safe direction for a rung to be wrong in, and it is said here out
#: loud rather than covered up by running the rung above it.
#:
#: `auto` reaches for the same flag as `bypass`, which is the one place this ladder collapses
#: two rungs into one. `auto` is the rung where what the agent asks for is granted, granting is
#: the whole of what that flag does, and agy has no hook seam for anything else to have a say
#: -- so there is nothing between the two to reach for. Given `--mode accept-edits` instead,
#: `auto` would have its commands denied and so be stricter than the `workspace-write` under
#: it, which is a ladder with a rung upside down.
#:
#: The last row is the absence of a rung rather than another one below them. A turn nobody has
#: said anything about is one this driver says nothing about either -- no `--mode`, no
#: `--dangerously-skip-permissions` -- so it runs at whatever `agy --print` runs at when it is
#: started here by hand, which is this CLI's own default approval and the soft-denials its
#: print mode makes in place of the questions it would have asked. Written into the table
#: rather than answered around it, so that every word a config may carry is answered where the
#: flags are; splatting nothing is the whole of what saying nothing takes.
_PERMITTED = {
    "read-only": ("--mode", "plan"),
    "workspace-write": ("--mode", "accept-edits"),
    "auto": ("--dangerously-skip-permissions",),
    "bypass": ("--dangerously-skip-permissions",),
    UNSAID: (),
}

#: The agent a turn at `read-only` is started as (`--agent`): one of humanize's own, whose
#: toolset is the reading tools alone and none of the CLI's built-in ones
#: (`excludeDefaultComponents`), so that nothing it can reach for writes. Put where agy finds
#: its own agents, `agents/` under its home (:func:`_agents`). An `--agent` agy cannot find is
#: run as its default agent without a word, which is every tool there is -- so a turn landing on
#: another machine, where that file is not, is refused rather than started, and the file is
#: written again before every turn that names it rather than trusted to still be there. Checked
#: against agy 1.2.12 on 2026-09-27: its model says it has `view_file`, `grep_search`,
#: `find_by_name`, `list_dir` and `manage_task`.
_READER = "hmz-read-only"

#: The same reader with the web to read as well, for a `read-only` turn told it may search.
_BROWSER = "hmz-read-only-web"

#: The agent a turn that may not reach the web is started as at every other rung. agy has no
#: flag or setting that takes a tool away, and no fence around its process holds its web
#: tools: from inside one whose proxy refuses every host but its model API's, `read_url_content`
#: still fetched the page, the fetch being made at the far end of that API rather than here. So
#: they are taken away the one way agy offers, an agent whose `tools` are its default ones less
#: those two -- a `tools` list is the whole of the toolset even with the CLI's own prompt kept.
#: Checked against agy 1.2.12 on 2026-09-29, whose default agent's model names `view_file`,
#: `run_command`, `manage_task`, `send_message`, `schedule`, `invoke_subagent`,
#: `define_subagent`, `manage_subagents`, `write_to_file`, `replace_file_content`,
#: `generate_image`, `read_url_content`, `search_web` and `ask_question`. The subagent tools and
#: the two that start work later or elsewhere go with the web's: what they start is not this
#: agent, and need not be without the web.
_OFFLINE = "hmz-offline"

#: The tools that reach the web: a page fetched, and a search.
_WEB = "read_url_content, search_web"

#: The tools that read this machine, which every agent of humanize's has.
_READS = "view_file, grep_search, find_by_name, list_dir"

#: The rest of its default tools that stay this agent's own work: its commands, its edits, its
#: task list, its images and its questions.
_WORKS = (
    "run_command, write_to_file, replace_file_content, manage_task, generate_image, "
    "ask_question"
)

#: Each agent of humanize's, as the file agy reads it out of.
_DEFINED = {
    _READER: f"""---
name: {_READER}
description: Reads, and changes nothing.
tools: [{_READS}]
excludeDefaultComponents: true
subagent: false
---
# Reader

You may read files and search them. You have no way of changing anything: no tool here writes
a file or runs a command. When asked to change something, say that you cannot.
""",
    _BROWSER: f"""---
name: {_BROWSER}
description: Reads, the web included, and changes nothing.
tools: [{_READS}, {_WEB}]
excludeDefaultComponents: true
subagent: false
---
# Reader

You may read files and search them, and read and search the web. You have no way of changing
anything: no tool here writes a file or runs a command. When asked to change something, say
that you cannot.
""",
    _OFFLINE: f"""---
name: {_OFFLINE}
description: Works on this machine, without the web.
tools: [{_READS}, {_WORKS}]
subagent: false
---
# Offline

You have no tool that reaches the web, and the commands you run cannot reach it either.
""",
}


def _defined(config: AgentConfig) -> str | None:
    """Which of humanize's agents a turn at this config is started as, if any.

    Args:
      config: What the agent is configured with.

    Returns:
      :data:`_READER` at `read-only`, or :data:`_BROWSER` there where web search was turned on
      and the agent is not fenced off the network; :data:`_OFFLINE` at any other rung where it
      was turned off or the agent is fenced off the network, whose web tools no fence can hold;
      and None -- the CLI's own default agent -- otherwise.
    """
    offline = config.web_search is False or (
        config.fence is not None and not config.fence.online
    )
    if config.permission == "read-only":
        return _BROWSER if config.web_search and not offline else _READER
    return _OFFLINE if offline else None


def _agents(native: Path) -> None:
    """Puts humanize's agents where agy finds them, as they are to be found.

    Under agy's own home, beside the skills a flow mounts there, rather than in a directory
    added to the turn with `--add-dir`: agy runs the agent's commands in the first of its
    workspace roots by name, so a directory of humanize's added beside the session's took its
    place whenever it sorted first -- checked against agy 1.2.12 on 2026-09-29, where `pwd`
    answered `~/.hmz/agy`. Its home is also the one place every fence already lets it
    read. Each is written whole wherever it is not already exactly as :data:`_DEFINED` says --
    through a file beside it, so that a turn starting while another process or thread writes it
    reads one or the other.

    Args:
      native: agy's own home, as :func:`_home` finds it.
    """
    for name, text in _DEFINED.items():
        defined = native / "agents" / f"{name}.md"
        try:
            if defined.read_text(encoding="utf-8") == text:
                continue
        except OSError:
            pass
        defined.parent.mkdir(parents=True, exist_ok=True)
        beside = defined.with_name(
            f".{defined.name}.{os.getpid()}.{threading.get_ident()}"
        )
        beside.write_text(text, encoding="utf-8")
        beside.replace(defined)


def _home(environment: dict[str, str], args: tuple[str, ...] = ()) -> Path:
    """Agy's own home: `~/.gemini/antigravity-cli`, or where `--app_data_dir` moves it.

    Args:
      environment: What the turn runs under, whose `HOME` it is under.
      args: What the account adds to the command line, which may name that flag.

    Returns:
      The directory.
    """
    home = Path(environment.get("HOME") or Path.home())
    directory = "antigravity-cli"
    for index, argument in enumerate(args):
        name, separator, value = argument.partition("=")
        if name != "--app_data_dir":
            continue
        if not separator and index + 1 < len(args):
            value = args[index + 1]
        # A flag with nothing after it names nothing. Left as it was rather than taken as
        # "": an empty data directory is `~/.gemini` itself, which is the whole of that home
        # walked and read every turn instead of the one directory under it.
        if value:
            directory = value
    return (home / ".gemini" / directory).resolve()


#: How long the CLI's own print-mode clock is given, in seconds, for a turn nobody has said
#: anything about. Its own default is five minutes, and since 1.1.28 a turn that reaches that
#: clock does not fail: agy says `print timeout after <duration> with turn in progress;
#: returning partial output` on stderr, hands back the part of the answer it has and exits
#: successfully. Half an answer arriving as a whole one is the failure nothing downstream can
#: see, and five minutes is well inside what an unattended turn takes.
#:
#: So the clock is left to the two a turn already runs under here, both of which end the
#: process rather than truncating what it was saying: the watchdog's silence window, which
#: :mod:`hmz.coganchor.backends` writes down per backend and which every word the turn says
#: pats, and whatever :class:`hmz.coganchor.agents.config.Budget` the turn was given. The
#: CLI's flag insists on a duration, so this is a day -- one set past any turn either of those
#: would still be waiting on, rather than a way of writing "no clock of its own at all".
_WAITS = 86400.0

#: The longest one that can be written down as a duration rather than spelled in exponents,
#: which is what a float wide enough to need one would reach the command line as. A century is
#: past anything anybody means, so the bound costs nobody a setting and buys a refusal said
#: where the number was chosen instead of one said by a process that would not start.
_LONGEST = 100 * 365 * 86400.0

#: What a step says it is doing, as the one line a row of a transcript has room for.
_THINKING = "THINKING"

#: What each kind of token is called in the counts Antigravity states, and what each of
#: them is here. Humanize's own names rather than the CLI's, as everywhere else a kind is
#: counted: the prices are per kind, so a usage written down under a spelling nothing else
#: knows is a lump nobody can put a figure on -- which is what these were until this table.
#: The thinking is counted beside the output rather than inside it, as its model family
#: counts it, so it is a kind of its own.
_KINDS = {
    "input": "input_tokens",
    "output": "output_tokens",
    "reasoning": "thinking_tokens",
    "cache_read": "cache_read_tokens",
}

#: How a local command is written: one name, under a plugin's where it has one. A first word
#: carrying a directory of its own is a path rather than a name, which is the whole of the
#: difference the CLI itself can see -- so `/tmp` alone still reads as a command here, and
#: reads as one to the CLI too, which is the transport that has somewhere to say so.
_COMMANDED = re.compile(r"/[\w.-]+(?::[\w.-]+)*")


def _commanded(prompt: str) -> bool:
    """Whether this prompt is one of the CLI's own commands rather than work for the agent.

    Args:
      prompt: The input prompt for this turn.

    Returns:
      Whether to take it through the finite print transport, which is where the CLI expands
      its own commands. False for a prompt whose first word is a path -- `/tmp/build.log has
      the failure in it` is a task, and ending the process a conversation is held open on to
      run it as a command costs a cold start for nothing.
    """
    first = prompt.split(maxsplit=1)[:1]
    return bool(first) and _COMMANDED.fullmatch(first[0]) is not None


def _carried(model: str) -> bool:
    """Whether this model's own name already says how hard it thinks.

    Antigravity writes an effort into a model's id -- `gemini-3.7-flash-high` is that model at
    that effort -- and `agy models` lists those ids, which is what an agent of this backend is
    configured with. It also takes the effort beside the name, as `--effort`, and it is exact
    about which of the two a model wants: a name carrying a rung refuses the flag with `--model
    <name> conflicts with --effort=<rung>`, a name carrying none but having variants refuses to
    run without it with `--model <name> requires --effort (available: ...)`, and a model with no
    variants at all refuses it with `--effort is not supported for model <name>`. All three
    checked against agy 1.2.2 on 2026-09-15.

    So there are two ways of saying one thing rather than a choice between them, and which one
    is right is the model's to say. This reads the name; :meth:`AntigravityCLISession._turn`
    sends the flag when the name has not already answered. The ladder itself is read off the
    one place it is written down rather than spelled again here, which is the same place
    :mod:`hmz.coganchor.models` reads it to tell a listed id's rung from its model.

    Which leaves the third case, the model with no variants at all, reading from the outside
    exactly like a base name whose variants are chosen with the flag -- the CLI lists both
    without a rung on the end, and nothing here can tell them apart before asking. It is asked
    the same way, and one that takes none says so by name. That is the failure worth having:
    the alternative is withholding a flag the common case requires, and an effort a flow chose
    being silently no effort at all is what this codebase calls a setting that lies.

    Args:
      model: The model the agent is configured with, as `agy models` lists it.

    Returns:
      Whether its name ends in one of the rungs this backend has.
    """
    profile = backends.named(_COMMAND)
    efforts = profile.efforts if profile is not None else ()
    return any(model.endswith(f"-{rung}") for rung in efforts)


def _settled(config: AgentConfig) -> AntigravityCLIAgentConfig:
    """This backend's own settings, off a config that may not be one of its own.

    An agent of this backend is ordinarily made with the class
    :data:`hmz.coganchor.agents.DRIVEN` names beside its driver, which carries all four. One
    made with the common :class:`AgentConfig` -- a caller that named no backend, a record
    written before there was anything to name -- carries none of them, and what a turn of it
    runs as is the defaults rather than an attribute that is not there.

    Args:
      config: What the agent was configured with.

    Returns:
      It, where it is already this backend's own, and otherwise one carrying every common
      setting it was configured with and the defaults for the four. Every one of them rather
      than the handful a turn is built out of today: a field copied by name is a field the
      next reader of this finds at its default without anything saying so.
    """
    if isinstance(config, AntigravityCLIAgentConfig):
        return config
    return AntigravityCLIAgentConfig(
        **{one.name: getattr(config, one.name) for one in fields(AgentConfig)}
    )


def _native(
    cwd: Path, environment: dict[str, str], args: tuple[str, ...] = ()
) -> bytes | None:
    """Fingerprints native customizations, including inherited external skill roots.

    Runtime databases, caches and logs are not configuration inputs. Missing roots are
    included so installing a new native skill between turns restarts the held process.
    """
    home = Path(environment.get("HOME") or Path.home())
    extra: list[Path] = []
    for index, argument in enumerate(args):
        name, separator, value = argument.partition("=")
        if name != "--add-dir":
            continue
        if not separator and index + 1 < len(args):
            value = args[index + 1]
        if value:
            extra.append(cwd / Path(value).expanduser())
    native = _home(environment, args)
    roots = {home / ".gemini/config", native}
    ancestors = (cwd, *cwd.parents, *extra)
    roots.update(parent / ".agents" for parent in ancestors)
    roots.update(parent / ".agent" for parent in ancestors)
    paths = {
        parent / name
        for parent in (*ancestors, home / ".gemini")
        for name in ("AGENTS.md", "GEMINI.md")
    }
    files = ("settings.json", "config.json", "mcp_config.json", "hooks.json")
    directories = ("skills", "plugins", "agents", "rules", "workflows")
    for root in roots:
        paths.update(root / name for name in (*files, *directories))
    paths.add(native / "builtin")
    pending = [
        root / name for root in roots for name in ("skills.json", "plugins.json")
    ]
    seen: set[Path] = set()
    repository = next(
        (parent for parent in ancestors if (parent / ".git").exists()), cwd
    )
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        paths.add(path)
        try:
            raw: object = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, UnicodeError, ValueError):
            return None
        if not isinstance(raw, dict):
            return None
        config = cast("dict[str, Any]", raw)
        for kind in ("entries", "inherits"):
            entries = config.get(kind, [])
            if not isinstance(entries, list):
                return None
            for entry in cast("list[object]", entries):
                if not isinstance(entry, dict):
                    return None
                value = cast("dict[str, Any]", entry).get("path")
                if not isinstance(value, str):
                    return None
                target = repository / Path(value).expanduser()
                paths.add(target)
                if kind == "inherits":
                    pending.append(target)
    return snapshot(paths)


class AntigravityCLISession(StreamSessionBase):
    """An Antigravity conversation, resumed by the id its first turn reported.

    The id is minted by `agy` as the conversation opens and named on the line the stream opens
    with, so it is read back out of the turn that opened it and given to every turn after --
    it takes no id of its own choosing.
    """

    #: What it writes on stdout is the turn as events rather than the agent talking.
    protocol: ClassVar[bool] = True

    #: `--json-schema` is a setting of the run: the answer comes back under `structured_output`
    #: rather than being asked for in the prompt.
    shapes: ClassVar[bool] = True

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session that has run no turn yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        #: What the agent answered with, and what went wrong with it if anything did.
        self._said = ""
        self._failed: str | None = None
        #: The deltas it answers in, gathered into the answers they are pieces of: a step
        #: says its words a token at a time, and a paragraph is worth one row rather than
        #: one row a word.
        self._saying = Saying()
        #: What the turn now running has cost, which it reports once, at the end.
        self._costing = Usage()
        self._previous = Usage()
        self._announced: str | None = None
        self._launched: tuple[object, ...] | None = None
        self._requested: tuple[object, ...] = ()

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Keeps ordinary turns warm and preserves print-only command behavior."""
        with self._lock:
            try:
                # A commanded prompt goes down the finite transport because that is where the
                # CLI expands its own commands -- so an agent told not to expand them has
                # nothing to go there for, and the process it is already holding serves.
                expands = not _settled(self._agent.config).disable_slash_commands
                if schema is not None or (expands and _commanded(prompt)):
                    self._shut()
                    yield from CommandSessionBase._stream(  # noqa: SLF001 -- shared transport
                        cast("CommandSessionBase", self), prompt, schema=schema
                    )
                else:
                    self._requested = self._settings()
                    yield from super()._stream(prompt)
            except BaseException:
                self._shut()
                if self._id is None:
                    self._previous = Usage()
                raise

    def _command(self) -> list[str]:
        """Starts the official stream driver without a finite --print prompt."""
        argv, _ = self._turn("")
        return [*argv[:-2], "--input-format", "stream-json"]

    def _settings(self) -> tuple[object, ...]:
        """Remembers the configuration and resources read when the CLI starts."""
        environment = self._environ() or dict(os.environ)
        provider = self._agent.node()
        if _defined(_settled(self._agent.config)) is not None:
            # Before the fingerprint rather than only where the turn is built, so that
            # writing them the first time is not a change the next turn restarts for.
            _agents(_home(environment, provider.args))
        native = _native(Path(self.cwd), environment, provider.args)
        # The account is here and its credential files are not: what a provider points the
        # CLI's own paths at is read as the turn goes rather than settled when it starts, so
        # a token refreshing on its own schedule must not end the conversation's process.
        # An account that actually moved is `elsewhere`, which restarts on its own.
        return (
            self._agent.config,
            self.effort,
            self._carrying(),
            self._tools,
            environment,
            provider,
            native if native is not None else object(),
        )

    def _stale(self) -> bool:
        """Restarts before changed native or flow inputs can become stale."""
        return self._launched is not None and self._launched != self._requested

    def _restarted(self) -> None:
        """Records process inputs; native usage survives --conversation resumes."""
        self._launched = self._requested

    def _write(self, text: str, ticket: str = "") -> str:
        """Encodes one prompt in Antigravity's event-tagged NDJSON format."""
        del ticket
        return json.dumps({"event": "user", "message": {"content": text}}) + "\n"

    def interject(self, text: str) -> None:
        """Keeps steering unsupported: the native protocol has no receipt ticket."""
        SessionBase.interject(self, text)

    def _read(self, line: str) -> Iterator[Event]:
        """Reads one native event and commits its conversation only on success."""
        try:
            raw: object = json.loads(line)
        except ValueError:
            return
        if not isinstance(raw, dict):
            return
        said = cast("dict[str, Any]", raw)
        yield from self._record(said)
        if named := said.get("conversation_id"):
            self._announced = str(named)
        if said.get("event") == "result":
            result = self._result(line)
            if self._id is None:
                self._adopt(self._announced or self._read_session_id(line))
            yield result

    def _turn(self, prompt: str) -> tuple[list[str], str | None]:
        """Builds the `agy -p` one turn is.

        Args:
          prompt: The input prompt for this turn.

        Returns:
          The command, and None because the prompt is inside it: Antigravity CLI reads no
          prompt off stdin.
        """
        self._said, self._failed = "", None
        self._costing, self._saying = Usage(), Saying()
        self._announced = None
        config = _settled(self._agent.config)
        argv = [
            _COMMAND,
            "--output-format",
            "stream-json",
            "--model",
            config.model,
            # Its own clock is five minutes and a turn that reaches it comes back short and
            # successful, so what it is set to is `_WAITS` rather than left where it was.
            # Spelled out to the millisecond: a float written as it repr's itself reaches a
            # wide enough value in exponents, which is not a duration anything can parse.
            "--print-timeout",
            f"{config.print_timeout:.3f}s",
            *_PERMITTED[config.permission],
        ]
        # How hard to think is said one of two ways here and the model chooses which: a name
        # that already carries the rung refuses the flag, and one that does not requires it.
        # An agent with no effort at all is left to be told so by the CLI, which names the
        # rungs that model takes -- a flag carrying nothing would be answered with less.
        if not _carried(config.model) and self.effort:
            argv += ["--effort", self.effort]
        if (defined := _defined(config)) is not None:
            _agents(_home(self._environ() or dict(os.environ), self._agent.node().args))
            argv += ["--agent", defined]
        if config.add_workspace or self._agent.anchor is not None:
            # Project selection can replace the CLI's initial cwd with a scratch directory.
            # Keep this session's workspace explicit, beside any provider-supplied roots --
            # and as the CLI will find it, which for an anchored turn is the mirror rather
            # than the path on the machine the work lands on. Which is why an anchored turn
            # is pinned whatever the agent says: the mirror is the only directory whose files
            # reach the target, and a turn left to find a project of its own would be one
            # whose edits land nowhere anybody is watching.
            argv += ["--add-dir", self._workspace()]
        if config.sandbox:
            argv.append("--sandbox")
        if config.disable_slash_commands:
            argv.append("--disable-slash-commands")
        if (schema := self._shaping) is not None:
            argv += ["--json-schema", json.dumps(schema.model_json_schema())]
        if self._id is not None:
            argv += ["--conversation", self._id]
        # Its flags are Go's, which take the next word whatever it starts with, so a prompt
        # opening with a dash is still a prompt.
        return [*argv, "--print", prompt], None

    def _reads(self, line: str, *, error: bool) -> Iterator[Event]:
        """Reads one line Antigravity CLI wrote, as the things it says the agent did.

        Args:
          line: The line, as written.
          error: Whether it came from stderr, which is its own log rather than the turn --
            kept for a failed turn's diagnostic and shown nowhere.

        Yields:
          What it said, which is nothing for a line saying nothing worth showing.
        """
        if error:
            return
        try:
            raw: object = json.loads(line)
        except ValueError:
            return
        if isinstance(raw, dict):
            yield from self._record(cast("dict[str, Any]", raw))

    def _record(self, said: dict[str, Any]) -> Iterator[Event]:
        """Shares native event parsing between persistent and finite transports."""
        kind = str(said.get("event") or "")
        # The payload sits under a key of the event's own name rather than beside it.
        told = cast("dict[str, Any]", said.get(kind) or {})
        if kind == "step_update":
            yield from self._step(told)
        elif kind == "result":
            # The turn is over, so the last step's words are whole: nothing follows them to
            # close them, and words held back for a boundary that never came are words lost.
            yield from self._saying.rest()
            self._said = str(told.get("response") or "")
            if self._shaping is not None and "structured_output" in told:
                # Display text includes rejected finish calls and native tool metadata.
                # Only the final structured value is the answer to the requested schema.
                self._said = json.dumps(told["structured_output"])
            cumulative = self._cost(cast("dict[str, Any]", told.get("usage") or {}))
            self._costing = self._delta(cumulative)
            # Local commands such as /help report zeros, without resetting the resumed
            # conversation's cumulative usage. Omitted counters retain their baseline.
            self._previous = Usage({**self._previous, **cumulative})
            # It says how the run ended in a word rather than only in its exit status, and a
            # run that was cancelled or refused is not a turn that landed.
            status = str(told.get("status") or "")
            if failed := str(told.get("error") or ""):
                self._failed = failed
            elif status and status != "SUCCESS":
                self._failed = status

    def _delta(self, cumulative: Usage) -> Usage:
        """This turn's own cost, out of a counter kept for the whole conversation.

        Args:
          cumulative: What the conversation has spent by the end of this turn, as read.

        Returns:
          What this turn spent. A counter that went backwards is a count that started again
          -- a restarted process, an account this turn fell back to -- and the whole of it is
          this turn's: read as a smaller difference, or clamped to nothing, a turn would be
          charged as free. Started again once is started again for every kind at once, since
          it is the count that restarted rather than one column of it: deciding a column at a
          time would charge the kinds that happened to pass their old total as differences.
        """
        restarted = any(
            value < self._previous.get(name, 0.0) for name, value in cumulative.items()
        )
        return Usage(
            {
                name: value if restarted else value - self._previous.get(name, 0.0)
                for name, value in cumulative.items()
            }
        )

    def _step(self, told: dict[str, Any]) -> Iterator[Event]:
        """Reads one step of the turn, which is a piece of an answer or a tool going by.

        Args:
          told: The `step_update` payload, as read.

        Yields:
          What that step said, which is nothing for one that only moved a state along.
        """
        if words := str(told.get("text_delta") or ""):
            kind = (
                "reasoning" if str(told.get("step_type") or "") == _THINKING else "text"
            )
            self._saying.delta(kind, words)
            return
        # A tool is shown as it starts rather than once per state it passes through.
        named = str(told.get("tool_name") or "")
        if named and str(told.get("state") or "") != "DONE":
            # What it said before reaching for something is what says why it reached.
            yield from self._saying.upto()
            about: dict[str, Any] = told.get("tool_info") or {}
            first = next(
                (
                    str(value)
                    for value in about.values()
                    if isinstance(value, str) and value.strip()
                ),
                "",
            )
            yield Event(kind="tool", text=f"{named} {first}".strip()[:120])

    def _cost(self, counted: dict[str, Any]) -> Usage:
        """What the turn cost, by the kind each token went on.

        Args:
          counted: The `usage`, as read.

        Returns:
          What it spent.
        """
        return Usage(
            {
                kind: float(counted.get(named) or 0)
                for kind, named in _KINDS.items()
                if counted.get(named)
            }
        )

    def _result(self, transcript: str) -> Event:
        """The turn's answer, and what it cost, out of the lines it wrote.

        Args:
          transcript: The whole of stdout, already read line by line.

        Returns:
          The `result` the turn ends on.

        Raises:
          subprocess.CalledProcessError: If the turn failed, which it says in a word of its own
            as well as in its exit status.
        """
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
        """Reads back the conversation it opened, which the line it opens with names.

        Args:
          transcript: Everything the turn printed.

        Returns:
          The conversation's id.

        Raises:
          ValueError: If nothing the turn wrote names one, which is a turn that landed
            somewhere nobody can find again.
        """
        for line in transcript.splitlines():
            try:
                said: object = json.loads(line)
            except ValueError:
                continue
            if not isinstance(said, dict):
                continue
            held = cast("dict[str, Any]", said)
            # Named at the top of the line it opens with, and again inside the one it ends on.
            named = held.get("conversation_id") or cast(
                "dict[str, Any]", held.get("result") or {}
            ).get("conversation_id")
            if named:
                return str(named)
        raise ValueError(f"{_COMMAND} named no conversation")


@dataclass(frozen=True, kw_only=True)
class AntigravityCLIAgentConfig(AgentConfig):
    """What Antigravity CLI is configured with: the common settings, and the four it adds.

    The model is written as `agy models` lists it, which is a slug of its own -- and for most
    of them the effort is part of that slug, `gemini-3.7-flash-low` being that model at that
    effort. The common `effort` is sent as `--effort` for a model whose name has not already
    said it, and withheld for one whose name has: see :func:`_carried`.

    The four here are the rest of what this CLI takes that nothing else does. Each defaults to
    what a turn of it already ran as, so an agent nobody has configured behaves exactly as it
    did before there was anything to configure.

    Four of its flags are deliberately not here. `--project` and `--new-project` choose the
    project whose directory `add_workspace` exists to stop replacing the session's, so a field
    for them would be a field for undoing the one above it. `--agent` picks a custom agent
    definition, which is a system prompt and a toolset chosen behind the flow's back -- the one
    humanize picks itself is the one that holds a `read-only` turn to reading. `--log-file`
    moves the log a failed turn's real reason is read out of, and what reads it --
    :func:`hmz.coganchor.backends.journalled` -- finds the newest under this backend's home
    rather than being told a path per turn, so naming one would move the log away from the
    only thing that looks at it.

    Attributes:
      add_workspace: Whether the session's own directory is pinned as a workspace root with
        `--add-dir`. On, and imposed rather than the CLI's own doing: agy resolves a project
        for the session and can put its initial working directory somewhere else entirely, so
        a turn that was not told would be a turn reading a scratch directory. Off is the bare
        CLI's behaviour, for whoever wants the project it would have chosen -- and is not
        taken for an agent whose turns land on another machine, where that root is the mirror
        the work is read and written through and letting the CLI pick another would be edits
        that never reach the target.
      print_timeout: How long the CLI's own print-mode clock runs, in seconds. Defaults to
        :data:`_WAITS` rather than to the CLI's five minutes, because a turn that reaches that
        clock comes back as a short answer that reads exactly like a whole one.
      disable_slash_commands: Whether the CLI is told not to expand its own commands and
        skills in print mode, so that a prompt opening with `/deploy` reaches the model as the
        words it is. Off, which is the CLI's own default. Turning it on also turns off the
        routing that sends a commanded prompt down the finite transport, there being no
        expansion left there to want.
      sandbox: Whether the turn runs under the CLI's own sandbox, which restricts what its
        terminal may do. Off, which is the CLI's own default, and orthogonal to `permission`:
        the rung says what the agent is allowed to ask for, and this says what the machine
        will carry out. Not what a `fence` is held with, and no stand-in for one: see
        :meth:`AntigravityCLIAgent.natively`.

    Raises:
      ValueError: If the print timeout is not a finite positive number of seconds. What that
        turns into on the command line is a duration, and a value with no digits to write --
        an infinity, a not-a-number, a count of seconds too large to spell without an exponent
        -- would be a turn that failed at the process rather than at the config that named it.
    """

    add_workspace: bool = True
    print_timeout: float = _WAITS
    disable_slash_commands: bool = False
    sandbox: bool = False

    def __post_init__(self) -> None:
        super().__post_init__()
        if (
            not math.isfinite(self.print_timeout)
            or not 0 < self.print_timeout < _LONGEST
        ):
            raise ValueError(
                f"print_timeout must be a positive number of seconds under "
                f"{_LONGEST:.0f}, not {self.print_timeout!r}"
            )


class AntigravityCLIAgent(AgentBase):
    """Antigravity CLI, driven through its own persistent stream-json protocol."""

    #: What it counts, read off the same table its driver reads a usage with, so that what
    #: a run is told this backend reports is what its driver actually parses.
    counts: ClassVar[frozenset[str]] = frozenset(_KINDS)

    def _serves(self, config: AgentConfig) -> None:
        """Refuses a rung one of this CLI's own settings would quietly undo.

        Here rather than in the config, because what an agent may do is the flow's: a flow
        declaring a reviewer that may not write settles that rung onto whatever agent it was
        handed, which is a `reconfigure` rather than a config anybody wrote out. A refusal
        raised where the config is built would come out of that settling as something the
        flow layer does not answer for; raised here, it is the refusal every other backend's
        is, said before the first turn and in the flow's own words.

        Args:
          config: What its turns are to run at.

        Raises:
          Unserved: If slash command expansion is off at `read-only`. agy answers that
            pairing with `--mode plan has no effect while slash command expansion is
            disabled` and goes on running, which is an agent that may write under a rung
            saying it may not -- and a rung that lies is worse than one that is refused. Only
            `plan`: the CLI names that mode alone, and `--mode accept-edits` is unaffected.
            And a turn started as one of humanize's agents -- at `read-only`, or kept off the
            web -- on another machine, where that agent is not to be found and agy would run
            its default agent in its place.
        """
        super()._serves(config)
        if _settled(config).disable_slash_commands and config.permission == "read-only":
            raise Unserved(
                f"{_COMMAND} cannot run at read-only with disable_slash_commands: "
                f"its plan mode has no effect while expansion is off"
            )
        if config.machine is not None and _defined(config) is not None:
            raise Unserved(
                f"{_COMMAND} cannot run at read-only or off the web on another machine: "
                "what holds it there is an agent of humanize's that is a file on this one"
            )

    def natively(self, fence: Fence) -> Fence:
        """None of the fence, which is put around agy from outside in full.

        agy has a sandbox of its own, `--sandbox`, and it holds no part of a fence. It is
        `exebox`, a jail agy builds out of a user namespace, a network namespace with its own
        loopback and a seccomp user-notify filter -- and it is a *terminal* sandbox, in its
        own words: it holds the commands the agent runs and nothing else. Its own file tools
        run in the CLI's process, outside it, and write wherever that process may: checked
        against agy 1.2.12 on 2026-09-29, where a turn under `--sandbox` wrote a file in the
        home directory with `write_to_file`. Nor does it start on a machine that restricts
        unprivileged user namespaces, which is Ubuntu's default: its server dies bringing that
        loopback up (`bringLoopbackUp: ioctl SIOCSIFFLAGS: operation not permitted`) and every
        command the agent runs fails with it. The hosts a sandboxed command may reach and the
        commands it may run outside are the desktop app's settings (`sandbox_allow_network`,
        `sandbox_system_allowlist`), which the CLI takes no flag or file for.

        What the fence cannot hold, agy is told instead: its web tools, which fetch at the far
        end of its model API, are taken off an agent fenced off the network (:func:`_defined`).

        Args:
          fence: The fence this agent is held to.

        Returns:
          `fence` itself.
        """
        return fence

    def new(self, cwd: str | os.PathLike[str] | None = None) -> AntigravityCLISession:
        """Opens a new Antigravity conversation, in the directory it is given or in this one."""
        return AntigravityCLISession(self, cwd)
