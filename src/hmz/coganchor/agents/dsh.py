"""DeepSeek Harness, driven through its Python SDK."""

# A session and the agent holding it are two halves of one object declared here.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import contextlib
import importlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Protocol, Self, cast

import yaml

from .base import AgentBase, SessionBase
from .config import AgentConfig
from .event import Event, Failed, Saying, Unrecoverable, Usage, say
from .watchdog import Watchdog

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

    from pydantic import BaseModel

__all__ = ["DshAgent", "DshAgentConfig", "DshSession", "native_ready"]

_EFFORTS = ("max", "high", "low", "off")
_EFFORT_ENV = "HMZ_DSH_EFFORT"
_REQUEST_SECONDS = 180.0

#: How the JSONL session log is written, as `dsh-session-persistence-jsonl` spells it, and
#: which of the two that plugin writes when nothing says. `zstd` is the SDK's own default;
#: humanize asks for `none` so its running tally can read complete rows as they land, which
#: is what :attr:`DshAgentConfig.session_compression` is for.
_COMPRESSIONS = ("none", "zstd")
_SDK_COMPRESSION = "zstd"

#: The two plugins that keep one conversation inside the model's context window, mounted as
#: a pair because `dsh-compaction-basic` injects `tokenMeter` and will not load without it.
#: Neither is in the SDK's own default composition.
_COMPACTION = (
    {"id": "token-meter", "name": "@deepseek-ai/dsh-token-meter"},
    {"id": "compaction-basic", "name": "@deepseek-ai/dsh-compaction-basic"},
)

#: The YAML tag the runtime's composition uses for a value it evaluates as JavaScript. It is
#: the runtime's to evaluate and has no meaning here, so it is carried through the read and
#: the write untouched rather than resolved.
_JS_TAG = "tag:yaml.org,2002:js"
_API_KEY_ENV = "DEEPSEEK_API_KEY"
_BASE_URL_ENV = "DEEPSEEK_BASE_URL"
_REF = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_EXTRA = (
    "DeepSeek Harness is not installed in this Python environment, where it is the [dsh] "
    "extra rather than part of every install: uv sync --extra dsh from a checkout, or pip "
    "install 'deepseek-harness-sdk>=0.1.1rc1,<0.2' 'python-dotenv>=1.2.3'"
)
_KEY_REQUIRED = (
    "DeepSeek Harness only supports API-key login and needs a DeepSeek API key. Save one "
    "in dsh under Settings -> Models; in hmz, set an agent to dsh and press a on its "
    "provider row, "
    "and create a key account; or set DEEPSEEK_API_KEY before starting hmz."
)
_GOAL = "Use create_goal to pursue this objective until it is complete:\n\n{}"

#: Which of a message's streamed pieces are the agent talking, and which of the two it is.
_CHUNKS = {"text-delta": "text", "reasoning-delta": "reasoning"}

#: What the model says when the conversation no longer fits in it. Read from the message
#: because that is where the runtime puts it: a turn refused for length is refused at the
#: same length on the next try, so it is a failure to report rather than one to repeat.
_TOO_LONG = (
    "maximum context length",
    "context length exceeded",
    "context_length_exceeded",
)


class _Subscription(Protocol):
    """The part of an SDK notification subscription used by a turn."""

    def __enter__(self) -> Self: ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...

    def next(self) -> object: ...


class _Client(Protocol):
    """The low-level public SDK calls used to stream one session."""

    def subscribe_session_notifications(self, session_id: str) -> _Subscription: ...

    def session_prompt(
        self,
        session_id: str,
        content_blocks: list[dict[str, Any]],
        *,
        notification_subscription: _Subscription,
    ) -> str: ...


class _Harness(Protocol):
    """A running SDK harness and its low-level client."""

    client: _Client

    def start(self) -> None: ...

    def close(self) -> None: ...


class _ObjectLoader(Protocol):
    """The typed part of PyYAML's loader used by duplicate-key validation."""

    def construct_object(
        self,
        node: yaml.Node,
        deep: bool = False,  # noqa: FBT001, FBT002 -- mirrors PyYAML's method
    ) -> object: ...


@dataclass(frozen=True, kw_only=True)
class DshAgentConfig(AgentConfig):
    """The model and effort every DeepSeek Harness session runs at, and what it composes.

    The two settings here are the two places humanize's runtime composition departs from the
    one the SDK applies to a launch that passes it no config of its own. Each defaults to
    what this backend has always done rather than to the SDK's default, because each is
    something humanize itself reads back afterwards: an install that changes neither gets the
    behaviour it had, and one that sets both to the SDK's values gets the SDK's own
    composition plus the effort, which is the only thing left that humanize must say.

    Attributes:
      compaction: Whether the runtime's own automatic compaction is mounted -- the
        `dsh-token-meter` and `dsh-compaction-basic` pair, at that plugin's own default
        threshold of 0.8 of the context window. Off is the SDK's default composition, which
        has neither; a conversation driven for long enough under it reaches a turn the model
        refuses for length, and a loop that keeps talking to the same conversation never gets
        past that refusal. On, because a flow that drives one conversation is what this
        backend is usually asked for.
      session_compression: How the durable JSONL session log is written, as one of
        :data:`_COMPRESSIONS`. `none`, though the plugin's own default is `zstd`, because
        humanize reads that log itself -- what a turn spent comes off complete rows as they
        land.

        `zstd` is the smaller log and the one the SDK would have written, and what it costs
        is worth saying plainly rather than softly: the plugin keeps the same file name under
        compression, so humanize goes on finding the log and reading it, and every row it
        reads is a zstd frame rather than a line of JSON. Nothing is counted from it -- not
        late, not in whole frames, not at all -- and the interface is still told this
        backend's own reckoning is one it can show. So this is for a run whose cost nobody
        asks this path for, and it is a setting that is quietly wrong for any other.
    """

    compaction: bool = True
    session_compression: str = "none"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.session_compression not in _COMPRESSIONS:
            raise ValueError(
                f"session_compression must be one of {', '.join(_COMPRESSIONS)}, "
                f"not {self.session_compression!r}"
            )


class DshAgent(AgentBase):
    """A DeepSeek Harness agent using the bundled SDK runtime."""

    #: The official goal service keeps the session working until its objective is complete.
    pursues: ClassVar[bool] = True

    #: What it counts. Its reasoning is already inside the output on the dsh contract, so
    #: it is not a kind of its own here.
    counts: ClassVar[frozenset[str]] = frozenset(
        {"input", "output", "cache_read", "cache_write"}
    )

    def __init__(self, config: DshAgentConfig, *, name: str | None = None) -> None:
        super().__init__(config, name=name)

    def _serves(self, config: AgentConfig) -> None:
        """Refuses a rung this SDK cannot enforce, wherever the config arrives.

        Where the config arrives rather than where the first turn runs, because what an agent
        may do is the flow's: a flow that declares a reviewer which may not write is refused
        this backend before the run starts, rather than an hour into one by a turn that could
        never have run at that rung.

        Args:
          config: What its turns are to run at.

        Raises:
          ValueError: If it was allowed anything other than everything. Not humanize's
            composition making a choice -- read against the runtime bundled with
            `deepseek-harness-sdk` 0.1.1rc1, there is no composition of what ships that would
            confine these turns honestly.

            The SDK's own default composition, the `runtime/cordis.yml` it injects as
            `$DSH_CORDIS_CONFIG` for a launch that passes none, mounts `dsh-bash-local` and
            `dsh-fs-local` -- the unconfined executors -- and none of `dsh-sandbox-*`,
            `dsh-user-approval` or `dsh-permission-presets`. So bypass is what a bare SDK
            session already runs at, and humanize composing the same pair is agreeing with the
            harness rather than loosening it.

            What settles it is the bundle rather than the default: the runtime executable
            carries `dsh-fs-sandbox`, `dsh-sandbox-local` and `dsh-sandbox-policy`, but no
            confining *shell* executor at all. `dsh-bash-sandbox` is named in the workspace's
            dependency lists and in `dsh-fs-sandbox`'s own documentation, and is not among the
            packages built into `dsh-jsonrpc-agent-pkg-*`; the only bundled `ctx.shell` is
            `dsh-bash-local`, whose `sandboxMode` is undefined. A rung composed from what does
            ship would fence `write_file` and leave `bash` able to write anywhere -- a rung
            that lies, which is worse than one refused.

            Put to the runtime rather than reasoned about, because the whole refusal turns on
            it: a composition naming `dsh-bash-sandbox` is refused at plugin load with
            `Cannot find package '@deepseek-ai/dsh-bash-sandbox'`, while the same composition
            with only the filesystem half swapped loads happily -- which is exactly the rung
            that would lie, and exactly why it is not offered.

            Two smaller confirmations of the same fact. `dsh-permission-presets` refuses to
            load over an unconfined executor and says so in those words ("the mounted bash
            executor does not confine (no sandboxMode)"), so mounting it is not unwise but
            fatal. And `auto` has nobody to ask even if it were composable: `ctx.approval`
            would have to be answered over the SDK's JSON-RPC request channel, which this
            driver does not serve, and the runtime fails an unanswered approval closed as
            `unavailable`.

            Left uncertain deliberately: were `dsh-bash-sandbox` bundled, `read-only` and
            `workspace-write` would both be reachable through `dsh-sandbox-policy`'s `mode`,
            and this refusal should narrow to `auto` alone -- but only on a host where
            `dsh-sandbox-local` finds a runner, since it fails closed with `SANDBOX_UNAVAILABLE`
            where there is neither bwrap nor a Landlock-enforcing kernel.
        """
        super()._serves(config)
        if config.permission != "bypass":
            raise ValueError(
                "the dsh runtime bundles no confining bash executor, so no rung below "
                "bypass can be enforced; permission must be 'bypass'"
            )

    def new(self, cwd: str | os.PathLike[str] | None = None) -> DshSession:
        """Opens an SDK session, which stays unopened until its first turn."""
        return DshSession(self, cwd)


class DshSession(SessionBase):
    """One durable DeepSeek Harness conversation."""

    def __init__(
        self, agent: DshAgent, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        super().__init__(agent, cwd)
        self._harness: _Harness | None = None
        self._runtime_effort: str | None = None
        self._attempt_id: str | None = None
        self._reaper: weakref.finalize[..., Any] | None = None
        #: The composition the live runtime was started from, so that an agent reconfigured
        #: mid-session is noticed as one whose runtime was built the old way.
        self._runtime_composition: str | None = None
        #: Where the composition the live runtime was started from is written, for as long
        #: as that runtime is up. Its own finalizer removes it if this session is dropped
        #: without ever being shut.
        self._composition: tempfile.TemporaryDirectory[str] | None = None

    @property
    def named(self) -> str | None:
        """The durable id, including the one whose opening turn is still running."""
        return super().named or self._attempt_id

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        """Runs one SDK turn and maps its session notifications as they arrive."""
        del schema  # SessionBase has already put unsupported shapes in the prompt.
        self._validate()
        session_id = self._id or f"session-{uuid.uuid4().hex}"
        self._attempt_id = session_id
        answer = ""
        costing = Usage()
        reason: Mapping[str, Any] | None = None
        # The chunks arrive a token at a time and are gathered into the answers they are
        # pieces of, one answer per step of the turn: a paragraph is worth one row of a
        # transcript rather than one row a word.
        saying = Saying()
        anchored = self._agent.anchor is not None

        try:
            self._require_key(session_id)
            harness = self._running()
            with harness.client.subscribe_session_notifications(
                session_id
            ) as subscribed:
                message_id = harness.client.session_prompt(
                    session_id,
                    [{"type": "text", "text": prompt}],
                    notification_subscription=subscribed,
                )
                received = False
                # Under a clock: `next` blocks on the SDK's own subscription, and a
                # runtime that has stopped publishing without stopping never wakes it.
                # No process is named -- what holds this turn is a runtime inside this
                # interpreter -- so the watchdog closes it through `_lets_go`, which is
                # what makes the subscription give up.
                with Watchdog(self) as watch:
                    while True:
                        method, payload = _notification(subscribed.next())
                        watch.saw()  # anything at all: the runtime is answering
                        if not received:
                            if not _receipt(method, payload, session_id, message_id):
                                continue
                            received = True
                        if (
                            method == "session.event"
                            and payload.get("sessionId") == session_id
                        ):
                            event = _mapping(payload.get("event"))
                            data = _mapping(event.get("data"))
                            kind = event.get("type")
                            if kind == "assistant/chunk":
                                chunk = _mapping(data.get("chunk"))
                                block = str(chunk.get("type") or "")
                                event_kind = _CHUNKS.get(block)
                                text = chunk.get("text")
                                if (
                                    event_kind is not None
                                    and isinstance(text, str)
                                    and text
                                ):
                                    saying.delta(event_kind, text, _answer(data))
                            elif kind == "assistant/message":
                                message = _mapping(data.get("message"))
                                content = message.get("content", data.get("content"))
                                whole = _whole(content)
                                for block_kind, said in whole.items():
                                    # The chunks put back together, plus whatever arrived in
                                    # no chunk at all -- the runtime hands both over the same
                                    # way.
                                    saying.whole(block_kind, said, _answer(data))
                                answer = whole.get("text", "")
                                for said_event in saying.ended(_answer(data)):
                                    with watch.held():
                                        yield self._shows(said_event)
                                usage = _usage(data.get("usage"))
                                if usage.total:
                                    self._spends(usage)
                                    costing = costing + usage
                            elif kind == "tool/call":
                                # What it said before reaching for something is what says why
                                # it reached, so the answer so far goes out ahead of the call.
                                # The one being streamed, rather than whichever step this call
                                # names: a call that named none would otherwise flush an
                                # answer nobody is writing, and the words would come out after
                                # the call.
                                for said_event in saying.upto():
                                    with watch.held():
                                        yield self._shows(said_event)
                                name = str(data.get("name") or "tool")
                                about = str(data.get("arguments") or "")
                                with watch.held():
                                    yield self._shows(
                                        Event(
                                            kind="tool",
                                            text=f"{name} {about}".rstrip(),
                                        )
                                    )
                            elif kind == "turn/end":
                                reason = _mapping(data.get("reason"))
                        elif (
                            method == "session.status"
                            and payload.get("sessionId") == session_id
                            and payload.get("status") == "idle"
                        ):
                            break

            # A runtime that fell idle without closing its last message still said what it
            # said, and words held back for a boundary that never came would be swallowed.
            for said_event in saying.rest():
                yield self._shows(said_event)
            _require_completed(session_id, answer, reason)
            self._adopt(session_id)
            tokens = int(costing.total)
            result = Event(
                kind="result",
                text=answer,
                tokens={self._agent.config.model: tokens} if tokens else {},
                spent=costing,
            )
            if not self._agent._watchers:
                say(result.text, sys.stdout)
            yield result
        except subprocess.CalledProcessError as refused:
            self._failing(refused)
            yield self._shows(Event(kind="failed", text=_diagnostic(refused)))
            raise
        except (ModuleNotFoundError, ValueError):
            self._shut()
            raise
        except Exception as why:
            # What it had said before it fell over, which is how far the turn got and is what
            # the refusal is reported with. Gathered rather than yielded piece by piece, so a
            # turn that failed mid-sentence would otherwise carry none of it.
            for said_event in saying.rest():
                if said_event.kind == "text":
                    answer = answer or said_event.text
                yield self._shows(said_event)
            refused = _refusal(session_id, answer, str(why))
            self._failing(why)
            yield self._shows(Event(kind="failed", text=_diagnostic(refused)))
            raise refused from why
        finally:
            self._attempt_id = None
            if anchored:
                # Coganchor reconciles the mirror when the supervised process exits.
                self._shut()

    def _failing(self, why: BaseException) -> None:
        """Lets go of the runtime behind a failed turn, where the turn is what went wrong.

        Only where it is: a turn refused by the model, or one that ran out of the time it
        was given, leaves a runtime that is up and a conversation that is whole, and closing
        it is what makes the next turn on this session impossible -- the id has been adopted,
        the runtime that holds it has gone, and every turn from then on is an id collision.
        Which was one failure at the context window turning into a flow that never finished.

        Args:
          why: What the turn failed with.
        """
        if _runtime_gone(why):
            self._shut()

    def _shows(self, event: Event) -> Event:
        """Shows an event on an unwatched run and returns it for the stream."""
        if not self._agent._watchers:
            say(event.text, sys.stderr)
        return event

    def _pursue(self, objective: str) -> str:
        """Runs the objective through Harness's persisted same-session goal service."""
        return self(_GOAL.format(objective))

    def interject(self, text: str) -> None:
        """Says nothing to a turn already running: the SDK can only queue another behind it.

        Written out though the base refuses already, and in the same words: this is the one
        backend here whose SDK looks like it could be talked to -- it holds a session open
        and takes prompts on it -- so the reason it cannot belongs where somebody about to
        add it will read it, rather than in a tracker.

        Args:
          text: What would have been said.

        Raises:
          NotImplementedError: Always. `session/prompt` is the runtime's `followup`, which
            leaves the word in the `next-turn` inbox -- the prompts awaiting individual turns
            -- so it is answered on its own once this turn is over rather than put into it.
            The runtime's `steer`, which does reach the turn under way, is not on the SDK's
            JSON-RPC surface: the server answers `initialize`, `session/prompt` and
            `shutdown` and refuses every other method. A flow told a turn queued behind was a
            word put in would be watching the wrong turn for it.
        """
        SessionBase.interject(self, text)

    def _validate(self) -> None:
        """Refuses settings the SDK cannot faithfully apply.

        The effort alone: a turn may be told to think harder while it is running, so this is
        the moment that one is read. What the agent may do is settled where the config is,
        which is `DshAgent._serves` -- and cannot have changed since.
        """
        if self.effort not in _EFFORTS:
            expected = ", ".join(_EFFORTS)
            raise ValueError(
                f"unsupported dsh effort {self.effort!r}; expected {expected}"
            )

    def _require_key(self, session_id: str) -> None:
        """Refuses an explicitly selected account that cannot authenticate dsh."""
        provider = self._agent.provider
        if provider is None:
            return
        key = provider.env.get(_API_KEY_ENV, "")
        if provider.way != "key" or not key.strip():
            raise Failed(1, ["dsh", session_id], output="", stderr=_KEY_REQUIRED)

    def _running(self) -> _Harness:
        """Returns a runtime initialized for this session's current effort and composition."""
        effort = self.effort
        composition = _composed(cast("DshAgentConfig", self._agent.config))
        # The account and the composition as well as the effort. A runtime is started with
        # one account's environment and its credential paths, and with one composition read
        # once at boot, and none of the three changes under one already up -- so an agent
        # reconfigured mid-session, or one told `disable_goals` after its first turn, has to
        # be given a runtime that was built the new way rather than quietly left on the old
        # one. The conversation survives it: the session is resumed by the id it already has.
        if self._harness is not None and (
            self._runtime_effort != effort
            or self._runtime_composition != composition
            or self.elsewhere()
        ):
            self._shut()
        if self._harness is not None:
            return self._harness

        harness_type = _harness_type()
        where = self._workspace()
        launch = self._agent.spawned(list(_runtime_args()), self.cwd)
        hushed = sorted(self._agent.hushed())
        if hushed:
            env = shutil.which("env")
            if env is None:
                raise FileNotFoundError(
                    "env is required to isolate dsh provider credentials"
                )
            launch = [env, *(part for name in hushed for part in ("-u", name)), *launch]
        environment = (
            _native_dsh_environment(Path(where))
            if self._agent.provider is None
            else dict(self._agent.environment())
        )
        environment[_EFFORT_ENV] = effort
        cordis = self._cordis(composition)
        harness = harness_type(
            # The SDK's own default for this one; passed rather than left out so that the
            # provider a turn runs under is named where a reader looks for it.
            provider="deepseek-official",
            model=self._agent.config.model,
            cwd=where,
            runtime_cwd=where,
            # Not the SDK's default, which leaves `$DSH_SESSION_ROOT` unset and lets the
            # composition fall back to `./.sessions` in the workspace -- a repository the
            # agent is working in would collect the logs of every run against it. Under the
            # dsh home instead, which `$DSH_HOME` moves and which is where `backends.py`
            # reads the trajectory of a session back from.
            session_root=str(_dsh_home() / "sessions"),
            cordis=cordis,
            env=environment,
            # Which is also why `cordis` above is never left out: the SDK injects its own
            # default config only for a launch it resolved the arguments of itself, and this
            # one is resolved here -- the bundled runtime wrapped in whatever `spawned` puts
            # in front of it, and in `env -u` where credentials have to be dropped.
            launch_args_override=tuple(launch),
            # humanize's, not the SDK's: `request_timeout_seconds` defaults to None there,
            # which is every JSON-RPC request waiting for as long as it takes. It bounds the
            # acknowledgement rather than the turn -- `session/prompt` answers with the
            # message id as soon as the prompt is in the inbox -- so what it catches is a
            # runtime that came up and never answered. The turn itself is the watchdog's.
            request_timeout_seconds=_REQUEST_SECONDS,
        )
        try:
            harness.start()
        except Exception:
            with contextlib.suppress(Exception):
                harness.close()
            # The composition belonged to a runtime that never came up, and the next try
            # writes its own. Taken away here rather than left for the garbage collector,
            # which would reclaim it at a moment nobody chose and warn about it on the way.
            self._forget()
            raise
        self._harness = harness
        self._runtime_effort = effort
        self._runtime_composition = composition
        self._as = self._agent.node().name
        self._reaper = weakref.finalize(self, harness.close)
        return harness

    def _cordis(self, composition: str) -> str:
        """Writes one composition out and says where it landed.

        Written per runtime rather than shipped, because it is the SDK's own default
        composition with this agent's settings applied to it: two agents of one flow may ask
        for different ones, and neither is a file in this repository to drift from the
        harness.

        Args:
          composition: The YAML to write, as `_composed` built it.

        Returns:
          The path to point `$DSH_CORDIS_CONFIG` at, which stands as long as the runtime
          reading it does.
        """
        self._forget()
        self._composition = tempfile.TemporaryDirectory(prefix="hmz-dsh-")
        written = Path(self._composition.name) / "cordis.yml"
        written.write_text(composition, encoding="utf-8")
        return str(written)

    def _forget(self) -> None:
        """Takes away the composition of a runtime that is no longer reading it."""
        composition, self._composition = self._composition, None
        if composition is not None:
            with contextlib.suppress(Exception):
                composition.cleanup()

    def _shut(self) -> None:
        """Closes this session's SDK runtime without ending the conversation."""
        harness, self._harness = self._harness, None
        self._runtime_effort = None
        self._runtime_composition = None
        if self._reaper is not None:
            self._reaper.detach()
            self._reaper = None
        if harness is not None:
            with contextlib.suppress(Exception):
                harness.close()
        # After the runtime rather than before it: the composition is the file that runtime
        # was started from, and a reload while it is still up would read it again.
        self._forget()


def _harness_type() -> Callable[..., _Harness]:
    """Loads the SDK only when a dsh turn needs it."""
    try:
        module = importlib.import_module("deepseek_harness")
    except ModuleNotFoundError as why:
        if why.name != "deepseek_harness":
            raise
        raise ModuleNotFoundError(_EXTRA) from why
    return cast("Callable[..., _Harness]", vars(module)["DeepSeekHarness"])


def _runtime_args() -> tuple[str, ...]:
    """Resolves the executable bundled with the SDK."""
    try:
        module = importlib.import_module("deepseek_harness_runtime")
    except ModuleNotFoundError as why:
        if why.name != "deepseek_harness_runtime":
            raise
        raise ModuleNotFoundError(_EXTRA) from why
    resolve = cast(
        "Callable[[], tuple[str, ...]]",
        vars(module)["resolve_bundled_launch_args"],
    )
    return resolve()


def _dsh_home() -> Path:
    """Where dsh keeps durable sessions for SDK turns."""
    return (
        Path(os.environ.get("DSH_HOME") or Path.home() / ".dsh").expanduser().absolute()
    )


class _UniqueSafeLoader(yaml.SafeLoader):
    """A safe YAML loader that refuses silently shadowed duplicate keys."""


def _unique_mapping(
    loader: yaml.SafeLoader, node: yaml.MappingNode, *, deep: bool = False
) -> dict[object, object]:
    """Constructs one mapping while rejecting duplicate or unhashable keys."""
    loader.flatten_mapping(node)
    construct = cast("_ObjectLoader", loader).construct_object
    held: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = construct(key_node, deep)
        try:
            duplicate = key in held
        except TypeError as why:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from why
        if duplicate:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found a duplicate key",
                key_node.start_mark,
            )
        held[key] = construct(value_node, deep)
    return held


_UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


class _Js(str):
    """One `!!js` value of the runtime's composition, carried through unevaluated.

    The runtime evaluates these as JavaScript against its own process environment, which is
    how the SDK's default composition says "`$DSH_SESSION_ROOT`, or `./.sessions`". Nothing
    here can or should evaluate one, so it is read as the text it was written as and written
    back under the same tag.
    """

    __slots__ = ()


class _CordisLoader(yaml.SafeLoader):
    """A safe loader that reads the runtime's composition without evaluating it."""


class _CordisDumper(yaml.SafeDumper):
    """A safe dumper that writes `!!js` values back as the runtime wrote them."""


def _represent_js(dumper: yaml.SafeDumper, value: _Js) -> yaml.ScalarNode:
    """Writes one `!!js` value back under the tag it was read from.

    The node is built rather than asked for: `represent_scalar` would also register the
    result for aliasing, which a string subclass is never eligible for anyway, and its stub
    types the value it takes as unknown.

    Args:
      dumper: The dumper asking, which has nothing to add to a scalar of this kind.
      value: The expression, as it was written.

    Returns:
      The tagged scalar to emit.
    """
    del dumper
    return yaml.ScalarNode(_JS_TAG, str(value))


_CordisLoader.add_constructor(
    _JS_TAG,
    lambda loader, node: _Js(loader.construct_scalar(cast("yaml.ScalarNode", node))),
)
_CordisDumper.add_representer(_Js, _represent_js)


def _sdk_composition() -> list[dict[str, Any]]:
    """The composition the SDK itself applies when it is passed none.

    Read off the installed runtime rather than copied into this repository, so that what an
    install with no options set hands the runtime is the harness's own default by
    construction instead of by a pinned file somebody has to keep in step with it.

    Returns:
      The bundled `runtime/cordis.yml`, one mapping per mounted plugin.

    Raises:
      ModuleNotFoundError: If the bundled runtime is not installed.
    """
    try:
        module = importlib.import_module("deepseek_harness_runtime")
    except ModuleNotFoundError as why:
        if why.name != "deepseek_harness_runtime":
            raise
        raise ModuleNotFoundError(_EXTRA) from why
    default = cast("Callable[[], Path]", vars(module)["bundled_default_config_path"])()
    loaded = yaml.load(default.read_text(encoding="utf-8"), Loader=_CordisLoader)  # noqa: S506
    return cast("list[dict[str, Any]]", loaded)


def _plugin(composed: list[dict[str, Any]], plugin_id: str) -> dict[str, Any]:
    """The config mapping of one mounted plugin, added if the default left it empty.

    Args:
      composed: The composition being built.
      plugin_id: The `id` the SDK's default composition gives that plugin.

    Returns:
      Its `config` mapping, to be written into in place.

    Raises:
      KeyError: If the SDK's default composition no longer mounts it, which is a version
        this driver has not been read against rather than something to paper over.
    """
    for entry in composed:
        if entry.get("id") == plugin_id:
            return cast("dict[str, Any]", entry.setdefault("config", {}))
    raise KeyError(
        f"the bundled dsh composition no longer mounts {plugin_id!r}; "
        "this driver has been read against 0.1.1rc1"
    )


def _composed(config: DshAgentConfig) -> str:
    """The composition one agent's runtime is started with, as YAML.

    The SDK's own default, plus only what humanize has to say over it. What it has to say
    unconditionally is the effort: the runtime takes a reasoning level as plugin config and
    nothing else on the SDK's surface carries one, so it is smuggled in as a `!!js` read of
    an environment variable this driver sets per runtime. That is the one deviation with no
    option in front of it, because an agent always has an effort and `backends.py` declares
    the ladder it may be set to.

    Args:
      config: The agent's settings, whose `goals`, `compaction` and `session_compression` are
        the three things that move.

    Returns:
      The composition to write out and point `$DSH_CORDIS_CONFIG` at.
    """
    composed = _sdk_composition()
    # Read rather than evaluated here: the runtime resolves it, and an unset variable leaves
    # `reasoningEffort` undefined, which is the adapter sending no reasoning level at all.
    _plugin(composed, "llm-deepseek")["reasoningEffort"] = _Js(
        f"process.env.{_EFFORT_ENV}"
    )
    # The goal service, the `create_goal` tool and the same-session round driver, which the
    # spine mounts only for a `goals` that is present and not false -- so an agent told to
    # have none is one whose composition does not carry them, rather than one that carries
    # them and is asked not to reach. `pursues` is this backend having the feature at all;
    # this is the agent in front of us being allowed it.
    # Written and removed rather than only written, so that neither setting is expressed as
    # an absence this driver assumes the meaning of. The pin admits any 0.1.x, and a release
    # that started mounting `goals` or spelling `compression` in the bundled file would
    # otherwise hand an agent that asked for neither exactly what it asked against.
    core = _plugin(composed, "agent-core")
    if config.goals:
        core["goals"] = {}
    else:
        core.pop("goals", None)
    sessions = _plugin(composed, "sessions")
    if config.session_compression != _SDK_COMPRESSION:
        sessions["compression"] = config.session_compression
    else:
        sessions.pop("compression", None)
    if config.compaction:
        # Appended rather than placed: cordis pends each plugin on the services it injects,
        # so where in the file a plugin is written makes no difference to what it gets.
        composed.extend(dict(plugin) for plugin in _COMPACTION)
    return yaml.dump(
        composed, Dumper=_CordisDumper, sort_keys=False, default_flow_style=False
    )


def native_ready(where: str | os.PathLike[str]) -> bool:
    """Whether dsh's local account can authenticate a turn in one workspace.

    Args:
      where: The workspace whose dotenv layer a local turn would read.

    Returns:
      Whether the same native configuration a turn uses resolves to a nonblank API key.
      Invalid or unavailable configuration is not ready rather than an error at a prompt.
    """
    try:
        environment = _native_dsh_environment(Path(where))
    except (ModuleNotFoundError, ValueError):
        return False
    return bool(environment[_API_KEY_ENV].strip())


def _native_dsh_environment(where: Path) -> dict[str, str]:
    """Resolves the settings and credential layers used by an installed dsh."""
    home = _dsh_home()
    settings = _yaml_mapping(home / "settings.yaml", "settings")
    raw_section = settings.get("llm-deepseek", {})
    if not isinstance(raw_section, dict):
        raise ValueError(  # noqa: TRY004 -- all configuration errors share one API
            f"dsh settings at {home / 'settings.yaml'} must give "
            '"llm-deepseek" a mapping'
        )
    section = cast("dict[object, object]", raw_section)
    raw_ref = section.get("apiKeyEnv", _API_KEY_ENV)
    if not isinstance(raw_ref, str) or _REF.fullmatch(raw_ref) is None:
        raise ValueError(
            f"dsh settings at {home / 'settings.yaml'} have an invalid "
            '"llm-deepseek.apiKeyEnv"'
        )

    credentials = _credentials(home / ".credentials.yaml")
    project_env = _dotenv(where / ".env")
    user_env = {} if home == where else _dotenv(home / ".env")
    key = _nonempty(os.environ, raw_ref)
    if key is None:
        key = credentials.get(raw_ref)
    if key is None:
        key = _nonempty(project_env, raw_ref)
    if key is None:
        key = _nonempty(user_env, raw_ref)

    environment = {_API_KEY_ENV: key or ""}
    if "baseURL" in section:
        base_url = section["baseURL"]
        if not isinstance(base_url, str):
            raise ValueError(
                f"dsh settings at {home / 'settings.yaml'} must give "
                '"llm-deepseek.baseURL" a string'
            )
        environment[_BASE_URL_ENV] = base_url
    else:
        base_url = _layered(os.environ, project_env, user_env, name=_BASE_URL_ENV)
        if base_url is not None:
            environment[_BASE_URL_ENV] = base_url
    return environment


def _yaml_mapping(path: Path, kind: str) -> dict[object, object]:
    """Reads one optional YAML mapping without echoing its possibly secret source."""
    try:
        source = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except (OSError, UnicodeError):
        raise ValueError(f"dsh could not read {kind} at {path}") from None
    try:
        loaded = yaml.load(source, Loader=_UniqueSafeLoader)  # noqa: S506
    except yaml.YAMLError as why:
        mark = getattr(why, "problem_mark", None)
        location = (
            f" at line {mark.line + 1}, column {mark.column + 1}"
            if mark is not None
            else ""
        )
        raise ValueError(f"dsh {kind} at {path} is invalid YAML{location}") from None
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(  # noqa: TRY004 -- all configuration errors share one API
            f"dsh {kind} at {path} must be a mapping"
        )
    return cast("dict[object, object]", loaded)


def _credentials(path: Path) -> dict[str, str]:
    """Reads dsh's owner-only credential mapping and validates every entry."""
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        return {}
    except OSError:
        raise ValueError(f"dsh could not inspect credentials at {path}") from None
    if os.name != "nt" and mode & 0o077:
        raise ValueError(
            f"dsh credentials at {path} are readable beyond their owner; "
            f'run "chmod 600 {path}" before starting again'
        )
    raw = _yaml_mapping(path, "credentials")
    credentials: dict[str, str] = {}
    for ref, value in raw.items():
        if not isinstance(ref, str) or _REF.fullmatch(ref) is None:
            raise ValueError(
                f"dsh credentials at {path} contain an invalid credential reference"
            )
        if not isinstance(value, str):
            raise ValueError(  # noqa: TRY004 -- all configuration errors share one API
                f'dsh credentials at {path} must give "{ref}" a string value'
            )
        if not value:
            raise ValueError(
                f'dsh credentials at {path} give "{ref}" an empty value; '
                "remove the entry instead"
            )
        credentials[ref] = value
    return credentials


def _dotenv(path: Path) -> dict[str, str]:
    """Reads one optional dotenv layer without interpolation or process mutation."""
    try:
        source = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, UnicodeError):
        return {}
    try:
        from dotenv import dotenv_values
    except ModuleNotFoundError as why:
        if why.name != "dotenv":
            raise
        raise ModuleNotFoundError(_EXTRA) from why
    values = dotenv_values(stream=io.StringIO(source), interpolate=False)
    return {name: value for name, value in values.items() if value is not None}


def _nonempty(values: Mapping[str, str], name: str) -> str | None:
    """Returns a present nonempty credential value from one layer."""
    value = values.get(name)
    return value or None


def _layered(*layers: Mapping[str, str], name: str) -> str | None:
    """Returns the first layer's value for a setting, including an empty one."""
    return next((layer[name] for layer in layers if name in layer), None)


def _notification(notification: object) -> tuple[str, Mapping[str, Any]]:
    """Reads one SDK notification without importing its optional model type."""
    method = getattr(notification, "method", "")
    payload = getattr(notification, "payload", {})
    return str(method), _mapping(payload)


def _mapping(value: object) -> Mapping[str, Any]:
    """Returns a wire object as a mapping, or an empty one for another JSON value."""
    return cast("Mapping[str, Any]", value) if isinstance(value, dict) else {}


def _answer(data: Mapping[str, Any]) -> str:
    """Which of a turn's answers a chunk or a message belongs to.

    A turn is several steps and each of them says something, so the pieces are gathered by the
    step they are pieces of: a runtime part way through the next answer must not have the last
    one's words put back on the end of it.

    Args:
      data: The event's payload, as read.

    Returns:
      The pair naming it, as one name.
    """
    return f"{data.get('turn')}/{data.get('step')}"


def _whole(content: object) -> dict[str, str]:
    """One finished message, as the whole of each kind of thing it said.

    Args:
      content: The message's blocks, as read.

    Returns:
      What it said and what it thought, each in one piece and each only where it said any.
    """
    blocks = cast("list[object]", content) if isinstance(content, list) else []
    said: dict[str, str] = {}
    for raw in blocks:
        block = _mapping(raw)
        kind = str(block.get("type") or "")
        text = block.get("text")
        if kind in ("text", "reasoning") and isinstance(text, str):
            said[kind] = said.get(kind, "") + text
    return said


def _receipt(
    method: str,
    payload: Mapping[str, Any],
    session_id: str,
    message_id: str,
) -> bool:
    """Whether a notification says this prompt entered the session inbox."""
    if method != "session.event" or payload.get("sessionId") != session_id:
        return False
    event = _mapping(payload.get("event"))
    if event.get("type") != "agent/inbox/spliced":
        return False
    inserted = _mapping(event.get("data")).get("inserted")
    if not isinstance(inserted, list):
        return False
    return any(
        _mapping(message).get("id") == message_id
        for message in cast("list[object]", inserted)
    )


def _usage(value: object) -> Usage:
    """Maps dsh's disjoint token counts onto humanize's common names."""
    raw = _mapping(value)
    kinds = {
        "input": _tokens(raw.get("inputTokens")),
        "output": _tokens(raw.get("outputTokens")),
    }
    for source, name in (
        ("cacheReadTokens", "cache_read"),
        ("cacheWriteTokens", "cache_write"),
    ):
        if source in raw:
            kinds[name] = _tokens(raw.get(source))
    # reasoningTokens is already part of outputTokens on the dsh contract.
    return Usage(kinds)


def _tokens(value: object) -> float:
    """Returns a non-negative numeric token count from the wire."""
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else 0.0
    )


def _failed(
    session_id: str, answer: str, reason: Mapping[str, Any] | None
) -> subprocess.CalledProcessError:
    """Turns a non-completed dsh turn end into the common turn failure, of its own kind."""
    held = reason or {}
    error = _mapping(held.get("error") or held.get("failure"))
    if error.get("code") == "MISSING_CREDENTIAL":
        why = _KEY_REQUIRED
    else:
        detail = error.get("message")
        why = str(detail) if isinstance(detail, str) and detail else json.dumps(held)
    return _refusal(
        session_id, answer, f"DeepSeek Harness turn did not complete: {why}"
    )


def _runtime_gone(why: BaseException) -> bool:
    """Whether a failed turn took its runtime with it, or left one the next turn may use.

    Args:
      why: What the turn failed with.

    Returns:
      Whether nothing is left running to carry the conversation on in. The transport closing
      is the one failure that says so: the runtime is a process, and a turn the model refused
      or a request that ran out of time is a turn that failed inside a process still up.
    """
    try:
        errors = importlib.import_module("deepseek_harness.errors")
    except ModuleNotFoundError:
        # No SDK to have started a runtime with, so there is nothing to keep.
        return True
    closed = cast("type[BaseException]", vars(errors)["TransportClosedError"])
    return isinstance(why, closed)


def _refusal(session_id: str, answer: str, said: str) -> Failed:
    """One turn's failure, as the kind of failure it is.

    Args:
      session_id: The conversation it was taken in.
      answer: What the turn had said before it stopped.
      said: What went wrong, as it is to be read.

    Returns:
      An `Unrecoverable` where another try is the same failure again -- a conversation that
      no longer fits the model it is being sent to is that long on the next try, and a
      durable id the runtime refuses as a collision is refused as one every time -- and an
      ordinary `Failed` otherwise, which an account's retries and the chain behind it are
      free to take again.
    """
    read = said.lower()
    terminal = any(one in read for one in _TOO_LONG) or "id collision" in read
    kind = Unrecoverable if terminal else Failed
    return kind(1, ["dsh", session_id], output=answer, stderr=said)


def _diagnostic(refused: subprocess.CalledProcessError) -> str:
    """Returns the useful words from a common turn failure without its traceback."""
    for value in (refused.stderr, refused.output):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(refused)


def _require_completed(
    session_id: str, answer: str, reason: Mapping[str, Any] | None
) -> None:
    """Raises the common failure unless the dsh turn completed."""
    if reason is None or reason.get("kind") != "completed":
        raise _failed(session_id, answer, reason)
