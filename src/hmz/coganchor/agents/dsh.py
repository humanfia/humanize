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

from hmz.coganchor import backends

from .base import AgentBase, SessionBase
from .config import AgentConfig
from .event import Event, Failed, Saying, Unrecoverable, Usage, say
from .watchdog import Watchdog

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

    from pydantic import BaseModel

    from hmz.coganchor.fence import Fence

__all__ = ["DshAgent", "DshAgentConfig", "DshSession", "native_ready"]

_REQUEST_SECONDS = 180.0

#: The profile the runtime is started under: the SDK's own, which is `dsh-base` -- the
#: harness's whole default composition -- with the JSON-RPC server put in front of it. What
#: humanize has to say over it is said in one patch file of its own (:func:`_composed`),
#: handed to the runtime after the profile's own layers, so that an agent which asks for
#: nothing is started from exactly the composition a bare SDK session is.
_PROFILE = "sdk"
_PATCH = "humanize.patch.yml"

#: The permission preset `dsh-base` reads for its sandbox policy and its approval policy,
#: and the one preset this driver can start a runtime at (see :attr:`DshAgent.rungs`).
_PERMISSION_ENV = "DSH_PERMISSION_MODE"
_UNCONFINED = "danger-full-access"

#: Where the runtime keeps its profiles and sessions, which the SDK never assumes.
_HOME_ENV = "DSH_HOME"

#: How the JSONL session log is written, as `dsh-session-persistence-jsonl` spells it, and
#: which of the two that plugin writes when nothing says. `zstd` is the SDK's own default;
#: humanize asks for `none` so its running tally can read complete rows as they land, which
#: is what :attr:`DshAgentConfig.session_compression` is for.
_COMPRESSIONS = ("none", "zstd")
_SDK_COMPRESSION = "zstd"
_SESSIONS = "session-persistence-jsonl"

#: The rows of `dsh-base` that are the goal service: the domain, the same-session round
#: driver, the `/goal` command and the `create_goal` tool. All four or none.
_GOALS = ("goal", "goal-round-driver", "command-goal", "tool-goal")

#: The rows of `dsh-base` that keep one conversation inside the model's context window: the
#: automatic compactor and the `/compact` command over it. Not the token meter it reads, which
#: the tool-result pruner reads too: unmounted, the pruner waits for it forever and the plugin
#: tree never finishes loading.
_COMPACTION = ("compaction-basic", "command-compact")

#: The rows of `dsh-base` one turn reaches the web through, and the whole of how this backend
#: is told whether it may: what an agent may reach for is what its composition mounts.
#:
#: `web` is the seam a provider registers into and the tool calls; `web-search-deepseek` is
#: the search provider, which reuses `DEEPSEEK_API_KEY` against DeepSeek's own
#: Anthropic-shaped endpoint (`DEEPSEEK_SEARCH_BASE_URL`, which is why `backends.py` lists it
#: among this backend's ambient variables); `web-fetch-http` is the fetch provider; and
#: `tool-web` is what puts `web_search` and `web_fetch` in front of the model.
_WEB = ("web", "web-search-deepseek", "web-fetch-http", "tool-web")
_SEARCH = "web-search-deepseek"

#: The YAML tag the runtime's composition uses for a value it evaluates as JavaScript. It is
#: the runtime's to evaluate and has no meaning here, so it is written under that tag rather
#: than resolved.
_JS_TAG = "tag:yaml.org,2002:js"
_API_KEY_ENV = "DEEPSEEK_API_KEY"

#: Where the packed runtime copies a native module to before loading it, read by the `pkg`
#: bootstrap it is built with; `~/.cache` when unset.
_NATIVE_CACHE_ENV = "PKG_NATIVE_CACHE_PATH"
_BASE_URL_ENV = "DEEPSEEK_BASE_URL"

#: The route the stock adapter owns, and the one a turn under DeepSeek's own key runs on.
_DEEPSEEK = "deepseek-official"

#: Which protocol an `openai-gateway` account said its endpoint speaks, as pi-ai names it.
_GATEWAY_API_ENV = "DSH_GATEWAY_API"

#: The ways in that reach somebody else's endpoint, each as the `@deepseek-ai/dsh-llm-pi-ai`
#: route a turn under it runs on and the wire protocol that route is told, written as the
#: `!!js` expression the runtime evaluates for it -- None for a route that already knows its
#: own. None of them is the stock DeepSeek adapter, which speaks
#: DeepSeek's own dialect of chat completions (see the dsh profile in `backends.py` for what
#: it sends): pi-ai is the harness's generic client, and its hand-declared routes take
#: exactly `openai-completions`, `openai-responses` and `anthropic-messages`. So:
#:
#: - `openai-gateway` reads which of the first two out of the account, which asked;
#: - `anthropic-gateway` is the third, said here because the way is the answer;
#: - `gemini-gateway` is pi-ai's `google` catalogue route with its base URL moved, which is
#:   the one way pi-ai reaches Gemini's own protocol -- `google-generative-ai` is not a
#:   protocol a hand-declared route may name, and a catalogue route keeps the one its
#:   catalogue speaks. Named `google` for that reason and no other: the key is still the
#:   account's, sent as `x-goog-api-key` over a `GEMINI_API_KEY` in the same environment.
#:
#: Every route is `gateway` but that one, which is a name no catalogue ships -- a catalogue
#: route of the same name would hand the route its own protocol and models as defaults.
_GATEWAYS: dict[str, tuple[str, str | None]] = {
    "openai-gateway": ("gateway", f"process.env.{_GATEWAY_API_ENV}"),
    "anthropic-gateway": ("gateway", "'anthropic-messages'"),
    "gemini-gateway": ("google", None),
}

#: Which ways in an account a turn runs under may have been made by: all of dsh's own, read
#: off its profile rather than written down again here. Every way `backends.py` declares for
#: this backend asks for `DEEPSEEK_API_KEY` -- the key on its own, or a gateway's URL and the
#: key that endpoint takes -- so every one of them can authenticate a turn, and a way it does
#: not declare is an account made for something else: variables of somebody's own, or a login
#: belonging to a CLI this is not. Derived rather than listed so that a way added to the
#: profile is one a turn accepts without this file being touched.
_WAYS = frozenset(
    way.name for one in backends.PROFILES if one.name == "dsh" for way in one.ways
)
_REF = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_EXTRA = (
    "DeepSeek Harness is not installed in this Python environment, where it is the [dsh] "
    "extra rather than part of every install: uv sync --extra dsh from a checkout, or pip "
    f"install '{backends.DSH_SDK}' 'python-dotenv>=1.2.3'"
)
_KEY_REQUIRED = (
    "DeepSeek Harness signs in with a key rather than a login and needs a DeepSeek API "
    "key. Save one in dsh under Settings -> Models; in hmz, type /settings accounts and "
    "add a dsh account by key -- or by openai-gateway, anthropic-gateway or "
    "gemini-gateway, which is a key and the endpoint to send it to -- then choose it on "
    "the agent's account row; or set DEEPSEEK_API_KEY "
    "before starting hmz."
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

    The two settings here are two of the places humanize's runtime composition may depart
    from the SDK's own `sdk` profile. An install that sets both to the SDK's values gets that
    profile with nothing of humanize's over it but what an account or a flow says.

    Attributes:
      compaction: Whether the runtime's own automatic compaction is mounted --
        `dsh-compaction-basic` and `/compact`, at that plugin's own default threshold of 0.8
        of the context window. On is the SDK's default; off unmounts both, and a
        conversation driven for long enough under it reaches a turn the model refuses for
        length, which a loop that keeps talking to the same conversation never gets past.
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

    #: `bypass` and nothing below it, which is what
    #: :meth:`~hmz.coganchor.agents.base.AgentBase._serves` refuses a config for. Refused where
    #: the config arrives rather than where the first turn runs, because what an agent may do
    #: is the flow's: a flow declaring a reviewer that may not write is refused this backend
    #: before the run starts, rather than an hour into one by a turn that could never have run.
    #:
    #: The `sdk` profile does carry a confining shell now -- `dsh-base` mounts
    #: `dsh-bash-sandbox` under `dsh-sandbox-policy` and `dsh-permission-presets`, at
    #: `workspace-write` -- but every one of its presets below `danger-full-access` asks
    #: `dsh-user-approval` before it lets a command past the sandbox, and nobody here can
    #: answer: the SDK's JSON-RPC surface is `initialize`, `session/prompt` and `shutdown`,
    #: and an approval nobody answers fails closed. So a runtime is started at
    #: `danger-full-access` (:data:`_UNCONFINED`), where the policy is `never` and the sandbox
    #: confines nothing, and that is `bypass` -- the rung this backend has always taken. A
    #: narrower one is a matter of putting `read-only` and `workspace-write` to the runtime on
    #: every platform it ships for, not of composing them here.
    #:
    #: Which is also why the silence above the ladder is taken, as the base class takes it
    #: everywhere: the silence asks for nothing to be said about what the agent may do, and
    #: this driver says the one thing it can.
    #:
    #: None of which leaves a flow's permission unenforced, because a flow's permission is not
    #: held by the rung. It is held by the fence (:attr:`AgentConfig.fence`), and dsh enforces
    #: none of a fence itself: :meth:`~AgentBase.natively` is left as the base class has it,
    #: and the whole fence is put around the runtime the SDK launches -- the runtime's own
    #: file and web tools and every shell it starts alike. So a flow at `local=read` runs here
    #: at `bypass` inside a fence whose workdir is readable and not writable, which is a
    #: read-only agent in fact rather than in name.
    rungs: ClassVar[tuple[str, ...]] = ("bypass",)

    #: What it counts. Its reasoning is already inside the output on the dsh contract, so
    #: it is not a kind of its own here.
    counts: ClassVar[frozenset[str]] = frozenset(
        {"input", "output", "cache_read", "cache_write"}
    )

    def __init__(self, config: DshAgentConfig, *, name: str | None = None) -> None:
        super().__init__(config, name=name)

    def new(self, cwd: str | os.PathLike[str] | None = None) -> DshSession:
        """Opens an SDK session, which stays unopened until its first turn."""
        return DshSession(self, cwd)


class DshSession(SessionBase):
    """One durable DeepSeek Harness conversation."""

    #: The SDK's runtime holds the turn, and nothing reaches into it to stop one.
    cuts_transport: ClassVar[bool] = True

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

    def _require_key(self, session_id: str) -> None:
        """Refuses an explicitly selected account that cannot authenticate dsh."""
        provider = self._agent.provider
        if provider is None:
            return
        key = provider.env.get(_API_KEY_ENV, "")
        if provider.way not in _WAYS:
            # Said apart from a missing key, because the account may well hold one: an
            # account made by `gateway`, which these ways were once one of, is not carried
            # over to whichever of them it meant, and the way is what to make again.
            said = f"The account {provider.name!r} was made by {provider.way!r}, which dsh "
            raise Failed(
                1,
                ["dsh", session_id],
                output="",
                stderr=f"{said}does not offer. {_KEY_REQUIRED}",
            )
        if not key.strip():
            raise Failed(1, ["dsh", session_id], output="", stderr=_KEY_REQUIRED)

    def _running(self) -> _Harness:
        """Returns a runtime initialized for this session's current effort and composition."""
        effort = self.effort
        way = self._agent.provider.way if self._agent.provider is not None else None
        composition = _composed(cast("DshAgentConfig", self._agent.config), way)
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
        # Where the runtime's process is started, which is where it works -- but for an
        # anchored one, which works in a mirror the anchor makes once it is running and
        # starts it in: the anchor is started wherever there is a directory to start it in.
        started = where if self._agent.anchor is None else _nearest(where)
        # An account is the whole of what a turn under it runs on: its key, and the endpoint
        # to send that key to where the account was made by a gateway way. The layers an
        # installed dsh reads -- its `settings.yaml`, its credential store, the project's
        # `.env` -- are consulted only where there is no account, since under one they are
        # this machine's opinion about somebody else's credentials: a `baseURL` saved by the
        # dsh Models page would otherwise route an account's key to whichever endpoint this
        # machine happens to be pointed at, and the account's own would never be read at all.
        if self._agent.provider is None:
            environment = _native_dsh_environment(Path(where))
        else:
            environment = dict(self._agent.environment())
        # The one preset this driver can start a runtime at (see `DshAgent.rungs`), said
        # rather than left to the profile, whose own default is `workspace-write` behind an
        # approval nobody here could give.
        environment[_PERMISSION_ENV] = _UNCONFINED
        # And, for an agent held to a fence, where the runtime unpacks its native modules.
        # The runtime is a Node program packed into one executable, which cannot load a
        # native module out of itself: it copies each -- `node-pty`, which the shell executor
        # is built on -- to `~/.cache/pkg` first and loads the copy. Under any fence that
        # keeps the home from being written, which the default one does, that copy fails and
        # the runtime never comes up; and a cache there that the agent could write would be
        # code every later dsh run on this machine loads. So a fenced runtime unpacks into the
        # fence's own scratch directory instead, which is the agent's and goes with it.
        fence = self._agent.fenced()
        if fence is not None:
            environment[_NATIVE_CACHE_ENV] = fence.tmp
        kept = self._agent.kept()
        assert kept is not None  # noqa: S101 -- dsh's home is always known
        # The dsh home the runtime keeps its profile and its sessions under, which the SDK
        # requires said and never takes to be `~/.dsh` on its own: this agent's, laid out as
        # the dsh home is -- the run's own directory, and the dsh home -- which `$DSH_HOME`
        # moves -- for an agent no run drives and where this process was told to keep none.
        # The profile keeps its sessions in `sessions` under it, where the running tally
        # reads them back from.
        environment[_HOME_ENV] = str(kept)
        # And what this machine left lying about that the account did not answer for, taken
        # away on the way in. Less what is being set above: `hushed()` already leaves out
        # what the account named, and a variable this driver is about to hand the runtime is
        # one it must not unset a moment later -- `env -u` strips the name from what it execs
        # with, so unsetting and setting the same one is setting nothing. Read here rather
        # than before the environment for exactly that reason.
        hushed = sorted(self._agent.hushed() - environment.keys())
        env = shutil.which("env") if hushed else None
        if hushed and env is None:
            raise FileNotFoundError(
                "env is required to isolate dsh provider credentials"
            )
        written = self._cordis(composition, fence)
        harness: _Harness | None = None
        try:
            # The bundled runtime under the SDK's own profile with humanize's patch over it,
            # wrapped in whatever `spawned` puts in front of it and in `env -u` where
            # credentials have to be dropped. Resolved here rather than by the SDK, which
            # resolves a launch only as the bare runtime -- so the profile, the patch and the
            # home it would have added are added here too.
            launch = self._agent.spawned(
                [
                    *_runtime_args(),
                    "--profile",
                    _PROFILE,
                    "--patch",
                    str(Path(written.name) / _PATCH),
                ],
                self.cwd,
            )
            if env is not None:
                launch = [
                    env,
                    *(part for name in hushed for part in ("-u", name)),
                    *launch,
                ]
            harness = harness_type(
                # The adapter route the turn runs on, which names a route the composition
                # registers rather than a place -- the server refuses the handshake for a
                # name nothing registered. The SDK's own default for DeepSeek's key, which
                # `@deepseek-ai/dsh-llm-deepseek` owns; the pi-ai route `_composed` declared
                # for a gateway's. Where either sends its requests is carried in the
                # environment rather than here.
                provider=_GATEWAYS.get(way or "", (_DEEPSEEK, None))[0],
                model=self._agent.config.model,
                # The rung, where there is one and the route takes one. An agent at no rung
                # leaves the adapter at its own default, and so does a gateway's: a model
                # pi-ai is handed by name is one it says takes no reasoning level at all, and
                # the handshake refuses a level the route has no word for.
                reasoning_effort=(effort or None) if way not in _GATEWAYS else None,
                cwd=where,
                runtime_cwd=started,
                env=environment,
                _launch_args=tuple(launch),
                # humanize's, not the SDK's: `request_timeout_seconds` defaults to None there,
                # which is every JSON-RPC request waiting for as long as it takes. It bounds the
                # acknowledgement rather than the turn -- `session/prompt` answers with the
                # message id as soon as the prompt is in the inbox -- so what it catches is a
                # runtime that came up and never answered. The turn itself is the watchdog's.
                # The handshake gets the same, over the SDK's thirty seconds: a runtime starting
                # in a fresh home lays its profile out first.
                request_timeout_seconds=_REQUEST_SECONDS,
                initialize_timeout_seconds=_REQUEST_SECONDS,
            )
            harness.start()
        except Exception:
            if harness is not None:
                with contextlib.suppress(Exception):
                    harness.close()
            # The composition belonged to a runtime that never came up, and the next try
            # writes its own. Taken away here rather than left for the garbage collector,
            # which would reclaim it at a moment nobody chose and warn about it on the way.
            with contextlib.suppress(Exception):
                written.cleanup()
            raise
        # The two together, and only once the runtime is up: a cut puts down whatever runtime
        # this session holds from a thread of its own, and one that found a composition here
        # with no runtime beside it yet would take away the file this one is starting from.
        self._harness, self._composition = harness, written
        self._runtime_effort = effort
        self._runtime_composition = composition
        self._as = self._agent.node().name
        self._reaper = weakref.finalize(self, harness.close)
        return harness

    @staticmethod
    def _cordis(
        composition: str, fence: Fence | None = None
    ) -> tempfile.TemporaryDirectory[str]:
        """Writes one patch out, as :data:`_PATCH` in a directory of its own.

        Written per runtime rather than shipped, because it is this agent's settings: two
        agents of one flow may ask for different ones.

        Written into the fence's own scratch directory where the agent is held to one, rather
        than the system's: the runtime reads this file from inside the fence, which grants
        its `tmp` and not the rest of `/tmp` -- so a composition written beside everybody
        else's would be one the runtime it was written for could not open, under
        `system=none`, and one it could open only for reading everybody else's under the
        default `system=read`.

        Args:
          composition: The patch to write, as `_composed` built it.
          fence: What the agent is held to, as :meth:`AgentBase.fenced` widens it, or None
            for an agent held to nothing.

        Returns:
          The directory, which stands as long as the runtime reading it does.
        """
        written = tempfile.TemporaryDirectory(
            prefix="hmz-dsh-", dir=fence.tmp if fence is not None else None
        )
        (Path(written.name) / _PATCH).write_text(composition, encoding="utf-8")
        return written

    def _shut(self) -> None:
        """Closes this session's SDK runtime without ending the conversation."""
        # Both let go of at once, before the runtime is closed: closing it takes its time,
        # and the next turn may have started a runtime of its own from a composition of its
        # own by the time it has -- which is not this one's to take away.
        harness, self._harness = self._harness, None
        composition, self._composition = self._composition, None
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
        if composition is not None:
            with contextlib.suppress(Exception):
                composition.cleanup()


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


def _nearest(path: str) -> str:
    """The nearest directory there is at or above a path."""
    at = Path(path)
    while not at.is_dir() and at != at.parent:
        at = at.parent
    return str(at)


def _dsh_home() -> Path:
    """Where dsh keeps durable sessions for SDK turns."""
    return (
        Path(os.environ.get(_HOME_ENV) or Path.home() / ".dsh").expanduser().absolute()
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
    """One `!!js` value of a patch, which the runtime evaluates and nothing here does.

    The runtime evaluates these as JavaScript as it boots, against its own process
    environment -- which is how a patch says "the gateway's URL, as this runtime was handed
    it" without the URL being written into a file.
    """

    __slots__ = ()


class _CordisDumper(yaml.SafeDumper):
    """A safe dumper that writes `!!js` values under the tag the runtime evaluates."""


def _represent_js(dumper: yaml.SafeDumper, value: _Js) -> yaml.ScalarNode:
    """Writes one `!!js` value under its tag.

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


_CordisDumper.add_representer(_Js, _represent_js)


def _composed(config: DshAgentConfig, way: str | None = None) -> str:
    """What one agent's runtime is told over the SDK's own profile, as a patch.

    Only what humanize has to say: a row of `dsh-base` addressed by its id, either switched
    off or given the whole of a `config` of its own -- a patch replaces a row's config rather
    than merging into it, so each one here restates every key it keeps. An agent whose
    settings are all the SDK's own is told nothing, and runs on exactly the profile a bare
    SDK session does.

    Args:
      config: The agent's settings, whose `goals`, `compaction`, `session_compression`,
        `web_search` and -- under a gateway -- `model` are the things that move.
      way: The way the account a turn runs under was made by, or None for no account.

    Returns:
      The patch to write out and hand the runtime with `--patch`, as YAML.
    """
    rows: list[dict[str, Any]] = []

    def off(*ids: str) -> None:
        rows.extend({"id": one, "disabled": True} for one in ids)

    # The goal service, which an agent told to have none is composed without -- rather than
    # composed with and asked not to reach for. `pursues` is this backend having the feature
    # at all; this is the agent in front of us being allowed it.
    if not config.goals:
        off(*_GOALS)
    if not config.compaction:
        off(*_COMPACTION)
    if config.session_compression != _SDK_COMPRESSION:
        rows.append(
            {
                "id": _SESSIONS,
                # The root restated as `dsh-base` writes it, under the home the runtime is
                # handed, since this row's config is replaced whole.
                "config": {
                    "root": _Js("dshHomePath('sessions')"),
                    "compression": config.session_compression,
                },
            }
        )
    # Under an account, without the dsh home's own `settings.yaml`, whose `llm-deepseek` and
    # `llm-pi-ai` sections override the adapters' config as the runtime boots: a `baseURL`
    # saved by the dsh Models page would otherwise send the account's key wherever this
    # machine is pointed. The account is the whole of what a turn under it runs on.
    if way is not None:
        off("settings")
    # The account's gateway, where it was made by one: one route of pi-ai's adapter, which
    # `dsh-base` mounts with none, reading the account's URL and key the way the stock adapter
    # does. Its one model is the agent's own, written in because a route nobody's catalogue
    # describes serves exactly the models it lists.
    gateway = _GATEWAYS.get(way or "")
    if gateway is not None:
        route, api = gateway
        profile: dict[str, Any] = {
            "apiKeyEnv": _API_KEY_ENV,
            "baseURL": _Js(f"process.env.{_BASE_URL_ENV}"),
            "models": [{"id": config.model}],
        }
        if api is not None:
            profile["api"] = _Js(api)
        rows.append({"id": "llm-pi-ai", "config": {"providers": {route: profile}}})
    # The web, which `dsh-base` mounts: off is said by unmounting all four, and an agent
    # nobody was asked about keeps what the SDK gives it. `is False` rather than a truth
    # test, because nobody-said and off are two answers rather than one.
    #
    # And under a gateway, the web less its search: `dsh-web-search-deepseek` asks a DeepSeek
    # model for a DeepSeek server tool over DeepSeek's Anthropic-shaped endpoint, none of
    # which is at the other end of somebody else's. Left in, `web_search` would be a tool the
    # model is shown and every call of fails, so the seam is told to fetch alone and
    # `dsh-tool-web` not to offer search. What the agent keeps is `web_fetch`, which is plain
    # HTTP from this machine.
    if config.web_search is False:
        off(*_WEB)
    elif gateway is not None:
        off(_SEARCH)
        rows.append({"id": "web", "config": {"fetchProvider": "http"}})
        rows.append({"id": "tool-web", "config": {"search": False}})
    return yaml.dump(
        rows, Dumper=_CordisDumper, sort_keys=False, default_flow_style=False
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
