"""Kimi Code: the app server it serves itself from, where a session is more than its prompts.

``kimi --prompt`` takes a prompt and nothing else. A ``/goal`` written into one is text the model
reads rather than a goal its runtime keeps, there is no flag for swarm mode, the effort an agent
is configured with has nowhere to go, and a turn already running has nowhere to be talked to.
``kimi web`` is the same binary serving the sessions its own browser client drives, and there
all four are things done to the session a turn is submitted to.

Which is the whole answer to why this backend is not driven through its headless mode. 0.42.0
has a real one -- ``kimi -p <prompt> --output-format stream-json`` prints a turn as it happens,
and for a driver that only wanted the words that would be the shorter road. It is not taken
because three of the things this driver is for are not in it. There is no route to a turn that
is already running, so :meth:`KimiCodeCLISession.interject` -- the reason ``steers`` is True
here at all -- would have nothing to write to. There is no per-turn body, so the rung an agent
runs at, its thinking level and its swarm width would have to be the process's own flags,
fixed for the life of a prompt that is one turn long anyway, and ``--plan``/``--yolo``/``--auto``
are the only three of them there are. And a turn that stops -- to ask, or for a tool it wants
approving -- stops against a terminal there, not against an object with an id that something
else can resolve; the daemon holds each on a route of its own -- ``/questions`` and
``/approvals`` -- which is what lets a flow answer or refuse one with nobody at a keyboard.
The server is the only surface in this CLI where a session is a thing
rather than an invocation, so the daemon it is, and the cost of that choice -- one ``kimi web``
per agent, and its argv -- is paid below.
"""

# A session and the agent holding it are two halves of one object declared in one
# file, which is what the underscore keeps out of the package rather than out of them.
# pyright: reportPrivateUsage=false

from __future__ import annotations

import collections
import contextlib
import importlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import weakref
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, cast

from hmz.coganchor.backends import SWARM

from .base import AgentBase, SessionBase
from .config import UNSAID, AgentConfig
from .event import Event, Failed, Question, Usage, say
from .hooks import EVERYWHERE, Moment
from .preload import preloaded
from .watchdog import Watchdog

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping
    from types import ModuleType

    from pydantic import BaseModel
    from websockets.sync.client import ClientConnection

#: What to say when the websocket client a session is told about its own turn over is not
#: in this Python environment. Kimi Code is an extra rather than part of every install, so
#: this is a choice somebody made rather than an install gone wrong, and the way back is
#: named where it is missed.
_EXTRA = (
    "Kimi Code needs the websocket client its app server's notifications ride on, which is "
    "the [kimi] extra and is not installed in this Python environment: uv sync --extra kimi "
    "from a checkout, or pip install 'websockets>=15,<18'"
)

#: The one line `kimi web` prints once it is listening, and the only place the port it took --
#: asked for as 0, so that two flows on one machine cannot collide -- and its token are said.
#:
#: Printed only by a server whose log level is *not* `silent`, which is the whole reason
#: :attr:`KimiCodeCLIAgentConfig.log_level` exists and does not default to the CLI's own
#: default. `kimi web` writes one of two ready outputs: the compact line this reads at any
#: level from `fatal` to `trace`, and a drawn banner -- logo, ANSI colour, the token on a
#: line of its own -- at `silent`. Omitting `--log-level` is `silent`, so the bare command a
#: person runs is the one shape a machine cannot read, and a daemon started without the flag
#: would leave this loop reading banner lines that never match until the agent was collected.
#: Verified against 0.42.0 by starting both.
_LISTENING = re.compile(r"^Kimi server: (\S+)/#token=(\S+)$")

#: What `kimi web --log-level` takes, and the one of them this driver cannot be run at. The
#: level is the daemon's own logging, which nothing here reads -- what it decides for us is
#: the shape of the ready line above, so `silent` is refused where the config arrives rather
#: than hung on where the daemon starts.
LOG_LEVELS = ("fatal", "error", "warn", "info", "debug", "trace", "silent")
_BANNERED = "silent"

#: The levels left once the unreadable one is out, which is what a flow that named something
#: Kimi has never heard of is offered. Listing `silent` there would be offering the refusal
#: below as the way out of the refusal above.
READABLE = tuple(level for level in LOG_LEVELS if level != _BANNERED)

#: The highest port there is, which is as much as this driver can say about one: whether the
#: number is free is the system's answer and it gives it by refusing to bind, not by refusing
#: the config. 0 is the useful end of the range and the default -- it means ask for any.
_PORT_MAX = 65535


@dataclass
class _Running:
    """The turn under way, if one is: which session it is in, and what it is running at.

    Written as the turn opens and cleared when it is over, read by whoever wants to put a word
    in. A prompt sent to a session that is working is queued rather than run, and steering it
    is what moves it into the turn already running instead of leaving it for the next one.
    """

    session: str | None = None
    config: dict[str, Any] = field(default_factory=dict[str, Any])


#: How often a running turn is asked whether it is still running, how long one call may take,
#: and how long a daemon being taken down is given to go before it is left to the system.
_POLL_SECONDS = 1.0
_CALL_SECONDS = 60.0
_STOP_SECONDS = 5.0

#: The one line `kimi fork` prints, which is where the session it cut is named.
_FORKED = re.compile(r"Forked to (\S+)")

#: Event-capable daemons need polling only as recovery while the model is thinking.
_RECOVERY_SECONDS = 10.0

#: The lowest status a refused call carries. Below it is this driver's own number for a
#: daemon that could not be reached or would not finish, which says nothing about the call.
_REFUSED = 400

#: The status a daemon answers with for a route it does not serve. Told apart from every
#: other refusal because it is the one that is not about this session: a route that is not
#: there is holding nothing, where a route that answered 500 is a route holding something
#: nobody can read. The session's own troubles arrive inside a 200 -- `SESSION_NOT_FOUND`
#: is an envelope with a code in it, which `call` raises with its own 1 -- so this catches
#: the build and not the session.
_ABSENT = 404

#: The frames this daemon raises that a reader wakes for at once, and whether each may have
#: left a question or an approval waiting to be answered. REST stays authoritative for what it
#: will say; this only says which of its reads is worth the shared daemon's time now rather
#: than on its own cadence -- and only those two are, because they are the two things a turn
#: stops on. Whether a turn is still running is read a second apart whatever the daemon says,
#: which
#: is the cadence it was read at before there were notifications at all. What a turn has spent
#: is read on that same second, but the figure it reads is the one carried here: the step
#: frame below is the only place 0.42.0 says it at all, which is why this listener counts.
#:
#: A frame under no name here is coalesced instead of woken for: the daemon streams a running
#: command's output and a tool call's arguments a chunk at a time, and a reader woken per
#: chunk would spend the daemon every session of the agent shares on one session's `cat`. A
#: question or an approval raised under a name that is not written down here is therefore
#: found by the ordinary second, which is where it was found before any of this.
_MEANS = {
    "tool.call.started": False,
    "prompt.started": False,
    "goal.updated": False,
    "turn.step.completed": False,
    "event.question.requested": True,
    "event.approval.requested": True,
    "error": True,
}


def _websockets(name: str) -> ModuleType:
    """Loads part of the websocket client only when a kimi session needs one."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as why:
        if why.name != "websockets":
            raise
        raise ModuleNotFoundError(_EXTRA) from why


def _failure() -> type[Exception]:
    """What the websocket client raises, which every read of one here is caught by."""
    module = _websockets("websockets.exceptions")
    return cast("type[Exception]", vars(module)["WebSocketException"])


def _update(socket: ClientConnection, deadline: float) -> dict[str, Any]:
    """Read one bounded event frame, refusing malformed or stalled event streams."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    message = json.loads(socket.recv(timeout=remaining))
    if not isinstance(message, dict):
        raise TypeError("Kimi event frames must be objects")
    return cast("dict[str, Any]", message)


class _Updates:
    """Wake a session reader when its official daemon has something new to read.

    REST remains authoritative for history, questions and goals. A refused subscription or a
    lost connection returns to polling without resubmitting a prompt. It also says when the
    one read a turn can be *stopped* on is due -- whether a question is waiting to be
    answered. One daemon serves every session of its agent, so a reader that asked it
    everything on every wake would be spending the time the other seven are queueing for on
    answers nothing had changed; the rest keep their own second's cadence.

    Spending is the exception, and it is carried here rather than merely announced here: on
    0.42.0 the step frames this listens to are the only place the daemon says what a request
    cost at all, the session route having answered zero since the session opened. So this adds
    each step up as it arrives and :meth:`KimiCodeCLISession._counting` reads the total on its
    own second -- which is the cadence it always read on, with a figure in it now.
    """

    def __init__(
        self, base: str, token: str, session: str, stepped: Counter[str]
    ) -> None:
        """Subscribes to one session of the daemon, falling back to polling if it cannot.

        Args:
          base: Where the daemon is listening.
          token: What it takes to be let in.
          session: The one session of it this listener carries, and the only one it counts.
          stepped: That session's own running total, added to as each step of a turn lands.
            The session's rather than this listener's, because a turn spends what the turns
            before it spent as well: the meter is told the rise across a total, and a total
            that started again at nothing every turn would show a rise only where a turn cost
            more than the one before it.
        """
        # Loaded here rather than where this module is read, so that an install without
        # the `kimi` extra still holds every other backend. Before the try below, because
        # what the client raises is half of what that try catches.
        connect = cast(
            "Callable[..., ClientConnection]",
            vars(_websockets("websockets.sync.client"))["connect"],
        )
        self._failed = _failure()
        self._session = session
        self._stepped = stepped
        self._socket: ClientConnection | None = None
        self._contexts = contextlib.ExitStack()
        self.ended = False
        #: Whether a question may be waiting to be answered. True to begin with and true
        #: again whenever this listener stops carrying events: what is not being told is
        #: asked for, which is the polling this backend ran on before there were
        #: notifications at all.
        self.questioned = True
        try:
            socket = self._contexts.enter_context(
                connect(
                    base.replace("http:", "ws:", 1) + "/ws",
                    additional_headers={"Authorization": f"Bearer {token}"},
                    proxy=None,
                    compression=None,
                    ping_interval=None,
                    open_timeout=1,
                    # A full notification queue can delay its close handshake; REST has
                    # already settled the turn, so disposing this listener needs little grace.
                    close_timeout=0.1,
                )
            )
            self._socket = socket
            socket.send(
                json.dumps(
                    {
                        "type": "subscribe",
                        "id": "hmz",
                        "payload": {"session_ids": [session]},
                    }
                )
            )
            deadline = time.monotonic() + 1
            while True:
                message = _update(socket, deadline)
                if message.get("type") == "ack" and message.get("id") == "hmz":
                    if message.get("code") != 0:
                        self.close()
                    break
        except (OSError, self._failed, ValueError, TypeError):
            self.close()

    def wait(self, *, settled: bool) -> None:
        """Wait for progress, falling back to ordinary polling after a disconnect."""
        socket = self._socket
        if socket is None:
            # Nothing is being told, so everything is asked: this is the plain polling the
            # backend ran on before there were notifications, and it asks the daemon the
            # whole set every time round.
            self.questioned = True
            time.sleep(_POLL_SECONDS)
            return
        # Keep the extra REST read after completion, without its polling delay once the
        # daemon has confirmed that this turn's final events have been published.
        if settled and self.ended:
            return
        started = time.monotonic()
        deadline = started + (_POLL_SECONDS if settled else _RECOVERY_SECONDS)
        told = False  # whether the daemon said anything at all before the deadline
        try:
            while True:
                message = _update(socket, deadline)
                if message.get("type") == "ping":
                    payload = message.get("payload")
                    if not isinstance(payload, dict) or not isinstance(
                        nonce := cast("dict[str, Any]", payload).get("nonce"), str
                    ):
                        self.close()
                        return
                    socket.send(
                        json.dumps({"type": "pong", "payload": {"nonce": nonce}})
                    )
                    continue
                if message.get("session_id") != self._session:
                    continue
                told = True  # a heartbeat says the daemon is there, not that this turn moved
                kind = message.get("type")
                payload = message.get("payload", {})
                if not isinstance(payload, dict):
                    self.close()
                    return
                main = cast("dict[str, Any]", payload).get("agentId", "main") == "main"
                if kind == "turn.step.completed":
                    # Counted here and nowhere else, because this frame is the only place the
                    # daemon says what a request cost. Under this session's total and no
                    # other: one `kimi web` serves every session of its agent and publishes
                    # all of their frames down every socket, so a step is charged to the
                    # session the daemon named on the frame -- which is the one this listener
                    # subscribed to, everything else having been dropped above.
                    #
                    # Every agent of it, though, not only `main`: a swarm's members and a
                    # delegated subagent run inside this session and their requests are this
                    # session's bill. Each step is published once under the agent that took
                    # it, so counting them all is counting them once.
                    self._stepped.update(_spent(cast("dict[str, Any]", payload)))
                if kind in ("assistant.delta", "thinking.delta"):
                    # Preserve the old display cadence during long streaming messages,
                    # coalescing token notifications into at most one history read/second.
                    deadline = min(deadline, started + _POLL_SECONDS)
                elif kind == "turn.started":
                    # An agent beginning is not yet anything to read back: what it goes on
                    # to do is, and that arrives under its own name.
                    if main:
                        self.ended = False
                elif kind == "turn.ended":
                    if main:
                        self.ended = True
                    return
                elif (asks := _MEANS.get(str(kind))) is not None:
                    self.questioned = self.questioned or asks
                    # Progress is worth waking a running turn for. It is not worth cutting
                    # short the grace a stopped one is given: a session reports stopped
                    # before its last words can be read back, and a turn woken out of that
                    # grace by the frame of the turn it is only now starting would answer
                    # with what the daemon had not written down yet. Only `turn.ended`
                    # above ends that wait early, because only it says the words are there.
                    if not settled:
                        return
                else:
                    # Everything else this session is told is progress, whatever the daemon
                    # calls it: a list of the frames worth waking for is a list that goes
                    # stale, and a turn that stopped to ask under a name written down before
                    # the daemon had it must still be read. So it is read back -- at the
                    # cadence a stream of them can afford, which is the one the streamed
                    # text already goes at and the one every read here falls back to.
                    deadline = min(deadline, started + _POLL_SECONDS)
        except TimeoutError:
            # Silence for as long as that is a listener that may have missed something, so
            # the reader goes back to asking the daemon everything. A deadline reached with
            # frames still arriving is not silence: it is the coalescing above, and what
            # those frames meant has already been said.
            if not told:
                self.questioned = True
            return  # Event delivery is never the only way to finish.
        except (OSError, self._failed, ValueError, TypeError):
            self.close()

    def close(self) -> None:
        """Release the subscription, including a partially completed handshake."""
        # Said before the socket goes, so that a reader still in its turn asks the daemon
        # everything from here on rather than trusting a listener that has stopped.
        self.questioned = True
        if self._socket is not None:
            self._socket = None
            with contextlib.suppress(OSError, self._failed):
                self._contexts.close()


#: What the daemon counts a session's spending in, and what each of those is here. Every kind
#: of token counts: what a rate is measuring is the traffic, and a cache read crosses the wire
#: like anything else.
#:
#: This is the session-level aggregate, and on 0.42.0 it is a promise the CLI does not keep.
#: `GET /sessions/<id>` builds its body from one `toWireSession`, and that function writes
#: `usage: emptySessionUsage()` -- four literal zeros -- whatever the session has spent. So the
#: aggregate is read here still, because a build that ever starts keeping the promise should be
#: believed, but it is read as a floor rather than as the truth: see :meth:`_counting`. A
#: backend metered off this alone reports every turn as free, which is not a cosmetic wrong
#: number -- a run allowance is a cap on what the meters say, so a backend that always says
#: nothing is a backend no allowance can hold.
_KINDS = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_read": "cache_read_tokens",
    "cache_write": "cache_creation_tokens",
}

#: The same four kinds as one step of a turn reports them, which is where 0.42.0 actually says
#: what it spent: `turn.step.completed` carries a `usage` object under these names, one frame
#: per request to the model, and a turn is as many of them as the model took.
#:
#: The names differ from the aggregate's and so does one of the meanings, which is the whole
#: trap here. `inputOther` is **not** the input: the CLI's own `inputTotal` is
#: `inputOther + inputCacheRead + inputCacheCreation`, so `inputOther` is the part of the input
#: that no cache served. That is exactly what :data:`hmz.coganchor.agents.event.KINDS` means by
#: `input` -- the kinds there are counted so that adding them up is the whole of what crossed
#: the wire, which they only are if the cached part is not also inside the input -- so the two
#: line up kind for kind and nothing is added or taken away on the way across. The CLI agrees
#: in its own code: its `toSnapshotUsage` fills `input_tokens` from `inputOther` and the two
#: cache names from the two cache fields, which is this table and the one above being the same
#: four numbers under two spellings. Getting it wrong the other way -- reading `inputOther` as
#: the whole input, or adding the caches into it -- would report a turn at several times what
#: it cost, and a wrong number is worse than no number because a wrong number looks right.
_STEPPED = {
    "input": "inputOther",
    "output": "output",
    "cache_read": "inputCacheRead",
    "cache_write": "inputCacheCreation",
}


def _spent(payload: Mapping[str, Any]) -> Counter[str]:
    """What one completed step of a turn says it cost, by the kind this package counts in.

    Args:
      payload: The body of a `turn.step.completed` frame.

    Returns:
      Its four counts, and nothing at all for a step that carried none -- `usage` is optional
      in the daemon's own schema, and a step that does not say is a step that adds nothing
      rather than one that cost nothing.
    """
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return Counter()
    said = cast("dict[str, Any]", usage)
    return Counter(
        {
            kind: tokens
            for kind, named in _STEPPED.items()
            # Nothing below zero. A running total these are added into is a total a turn's
            # spending is the rise across, so one negative count would be this session buying
            # back tokens it had already been charged for -- and the rise it hid would never
            # be reported at all.
            if isinstance(count := said.get(named), (int, float))
            and (tokens := int(count)) > 0
        }
    )


#: What each kind of block a message is written in reads as. A block of a kind that is not here
#: is not shown: an image is not a line of a transcript.
_BLOCKS = {"text": "text", "thinking": "reasoning", "tool_use": "tool"}

#: The blocks whose words go on arriving after the block does, which is what makes the last of
#: them half a sentence rather than a thing to show. A tool block is named the moment it is
#: there and grows no further, so a turn that reaches for one says so as it reaches.
_GROWS = ("text", "thinking")

#: The two lists the daemon holds a stopped turn against, in the order a poll reads them.
#: Both take the same `status=pending` querystring and both answer with their pending items
#: under `items`, which is the whole of what :meth:`KimiCodeCLISession._held` needs to know.
_HELD = ("questions", "approvals")

#: What the daemon calls its approval list, and what an answer to one of them is. The route
#: each turn that stops for a tool stops on: GET it with the `status=pending` its querystring
#: schema requires and every unresolved approval of that session comes back under `items`,
#: each one naming the tool (`tool_name`), the one line the CLI would have shown a person
#: (`action`), the call itself (`tool_input_display`) and the id an answer goes back to
#: (`approval_id`). The answer is a POST to that id, and its body is `decision` and three
#: optional fields: `scope`, `feedback` and `selected_label`. `approved`, `rejected` and
#: `cancelled` are the three decisions there are -- the first lets the tool run, and either of
#: the others hands the model back a line saying the tool was not run, with whatever `feedback`
#: said appended to it as the reason. Which is a turn that carries on having been refused
#: rather than one that ends. Read off kap-server's own `routes/approvals.ts` and
#: `protocol/approval.ts` in the 0.42.0 bundle.
#:
#: `scope` is the one optional field with teeth, and it is left off deliberately. `session`
#: there writes the approval down as a rule the session keeps, so every later call matching it
#: is approved by the daemon without ever reaching this route -- which would be a hook hung on
#: `PERMISSION_REQUEST` seeing the first `Bash` of a turn and none of the twenty after it. An
#: approval answered here is answered once, for the call that raised it. `selected_label` is
#: the one field this driver has nothing to put in: it names which of the options a plan
#: review offered was taken, and a plan review is a thing shown to a person.
#:
#: Read off the bundle and then asked of a real one -- a 0.42.0 `kimi web` started here with
#: no model configured, which is enough to open a session and read the route if not to run a
#: turn. It answers the filtered path `{"code": 0, "data": {"items": []}}`, the bare path
#: `40001 status: Invalid input: expected "pending"`, an id it does not know `40404 approval
#: nope not found`, and a decision it does not take `40001 decision: Invalid option: expected
#: one of "approved"|"rejected"|"cancelled"`. Every one of those inside a 200, which is the
#: thing the querystring dance below turns on: a route this daemon serves refuses in its
#: envelope and never with a status of its own, so a status is the build answering and not
#: the session.
_ANSWERS = ("approved", "rejected")

#: How each rung of the ladder is set on a Kimi session. The daemon takes one of `manual`,
#: `yolo` and `auto`, and plan mode beside it, and the two are said together because neither
#: means much alone.
#:
#: The names mislead, so here is 0.42.0's own ladder. Kimi calls them Always Ask (`manual`),
#: Ask When Needed (`yolo`) and Never Ask (`auto`), loosest last -- `yolo` is the middle rung
#: and not the top one the word suggests. What decides it is the order its permission policies
#: are consulted in, the first to answer winning: the one that approves everything on `auto`
#: is consulted fourth, ahead of every policy that would ask, while the one that approves
#: everything on `yolo` is consulted tenth, behind them. So a `yolo` turn still stops to ask
#: before a Bash command the parser rates dangerous *or cannot parse at all*, before a
#: sensitive file, before a path under `.git`, and -- in plan mode -- before the `ExitPlanMode`
#: the model is told to end a plan with. `manual` adds no policy of its own at all: it is the
#: absence of the other two, so what survives it is the list of tools approved by default --
#: `Read`, `Grep`, `Glob`, `WebSearch`, `FetchURL`, `Agent`, `Skill`, `AskUserQuestion` and
#: the plan and todo tools -- plus a `Write` or `Edit` inside a git worktree's own workspace.
#: Bash asks, every time.
#:
#: Each of those is an approval and not a question, and until this driver read `/approvals`
#: that made all three of the tighter modes unreachable: a turn stopped on one stayed busy
#: with nothing on the route the poll was reading, and ended as the watchdog's stall. That is
#: what :meth:`KimiCodeCLISession._approved` buys back, so the table below is the ladder
#: rather than one rung written four times.
#:
#: What each row is, then, and why:
#:
#: `read-only` is `manual` with plan mode on. Plan mode is the hard half -- it vetoes `Write`,
#: `Edit`, `TaskStop` and the two cron tools outright, with no approval offered and nothing to
#: answer -- and `manual` is the half that catches what plan mode does not. Bash is the one
#: that matters: Kimi's own plan-mode reminder tells the model "Use Bash only when needed;
#: Bash follows the normal permission mode and rules", so at `auto` a rung named read-only
#: would run a command that writes a file. At `manual` that command is an approval instead --
#: and an approval this driver answers `rejected`, because this rung is not in
#: :data:`_GRANTED`. That is what makes the name true with no hook hung at all: the write is
#: refused by the rung itself, and a flow that wants the write allowed asks for a looser rung
#: rather than for a hook -- a hook can refuse what would have been granted, and there is
#: nothing here for it to widen. The same goes for the `ExitPlanMode` the model is told to end
#: a plan with: gated at every mode but `auto`, so at this rung the agent cannot quietly leave
#: the rung either.
#:
#: `auto` is `yolo`, for the reason humanize's `auto` exists: the agent may ask for more than
#: it has, and the asking is granted. That is `yolo` exactly -- the dangerous command, the
#: sensitive file, the path under `.git`, each one asked for and each one answered -- and it
#: is the same row Codex's table writes as `on-request`.
#:
#: `workspace-write` and `bypass` are `auto`, which is the mode where nothing is asked. There
#: is no sandbox in this CLI, so `workspace-write` cannot be the fenced thing it is on Codex;
#: what it can be is the rung that changes the workspace without stopping, and that is `auto`.
#: `bypass` means nothing asked and nothing checked, which is what `auto` is.
#:
#: The one thing `auto` costs is the question. It denies `AskUserQuestion` outright -- "Make a
#: reasonable decision and continue without asking the user" -- so a turn at either of those
#: two rungs does not stop to ask a person, and `NOTIFICATION` does not fire there. At
#: `read-only` and `auto` it does: `AskUserQuestion` is approved by default under both `manual`
#: and `yolo`, and `/questions` has always been read.
#:
#: What would make `read-only` bite harder still is a rung that cannot reach for `Bash` at
#: all: no call to refuse is a fence, where an approval answered is a gate somebody has to
#: hold. It is not the `tools` key of this body, which is the thing to say plainly because
#: this file said the opposite. `sessionAgentConfigSchema` does declare `tools`, so a body
#: carrying one is taken with a 200 -- and `applySessionAgentConfig` then reads `model`,
#: `thinking`, `permission_mode`, `plan_mode`, `swarm_mode`, `tower_mode` and the two goal
#: keys, and nothing else. The allow-list is accepted and dropped, and an agent sent one
#: keeps all of its tools. What the daemon really takes is `disabled_tools`, on the *prompt*
#: body rather than this one, which `setSessionDisabledTools` applies to the session. Both
#: checked against 0.42.0, the first of them live. Which is somebody else's change to make
#: and is being made: it is a lever on the prompt, and this table sets the session.
_PERMITTED = {
    "read-only": {"permission_mode": "manual", "plan_mode": True},
    "workspace-write": {"permission_mode": "auto", "plan_mode": False},
    "auto": {"permission_mode": "yolo", "plan_mode": False},
    "bypass": {"permission_mode": "auto", "plan_mode": False},
    # An agent nobody wrote a rung for: neither key is sent, and the session runs at whatever
    # `kimi web` would have run it at on its own. Which is this file's own rule about defaults
    # applied to the one setting that had been breaking it -- an install that configures
    # nothing behaves as the bare CLI does. 0.42.0 reads `default_permission_mode` out of the
    # install's config as it bootstraps a session and leaves the mode at `manual` where there
    # is none, so what an install that says nothing gets is Always Ask, the same as the person
    # who starts `kimi web` at a terminal and answers it from the browser.
    #
    # Nobody is at the browser here, which is why this row used to be the one that wedged: the
    # first tool call of such a turn stopped the session somewhere the poll could not move it,
    # and the watchdog ended it as a stall a quarter of an hour later. It no longer does.
    # `manual` is a rung this driver can answer now, and saying nothing lands on it the same
    # way `read-only` does -- the approval is read, a hook gets it, and the turn goes on. On
    # `rejected`, where no hook said otherwise: what humanize was told about this agent is
    # nothing, and nothing is not a yes. See :data:`_GRANTED`.
    UNSAID: {},
}

#: The permission modes in which what the agent reaches for is granted rather than asked
#: about, which is the whole of what decides whether this driver may answer an approval yes.
#: `auto` approves before any policy can ask, so an approval under it is one Kimi did not
#: raise; `yolo` is the mode whose bargain is that the agent asks and is granted. `manual` is
#: neither: it withholds approval for everything but the reads, and an approval arriving
#: under it is the session doing exactly what the rung told it to.
_GRANTS = ("auto", "yolo")

#: The rungs at which an approval this driver reads is answered yes. Derived from the table
#: above rather than written beside it, so that a row whose mode moves takes its answer with
#: it and the two cannot drift apart.
#:
#: Two rows are out, and for one reason said two ways. `read-only` is `manual`: its whole
#: meaning is that the agent may look at anything and change nothing, and at `manual` the
#: reads are the part the daemon approves by itself -- so every approval that reaches this
#: driver at that rung is, by construction, a tool that is not a read. Answering those yes
#: would make the rung name a thing it does not do: plan mode already refuses the edits, and
#: the Bash that plan mode lets through is precisely what the approval is for. The silence is
#: out because it names no mode at all: an agent nobody wrote a rung for bootstraps at
#: `manual`, and granting there would be humanize handing out, one call at a time, the `yolo`
#: that an agent declared at `auto` gets by asking for it.
#:
#: Refusing is not the same as leaving it: the daemon holds the tool until somebody resolves
#: it either way, so saying nothing would be the fifteen-minute stall this reading exists to
#: remove. `rejected` hands the model a line saying the tool was not run, with the reason --
#: so a turn at a withholding rung is one the agent is told no by and works around, which is
#: an outcome a flow can read.
_GRANTED = frozenset(
    rung
    for rung, settings in _PERMITTED.items()
    if settings.get("permission_mode") in _GRANTS
)


class _AppServer:
    """A `kimi web` daemon of our own, and the calls one turn of a session is made of."""

    def __init__(self, argv: list[str], env: Mapping[str, str] | None = None) -> None:
        """Starts the daemon and waits for it to say where it is listening.

        Args:
          argv: The command that starts it, already wrapped for wherever its work is to land.
          env: The whole environment to start it in, which is this process's own less what the
            agent's provider hushes and plus what it sets, or None to inherit this one. The
            daemon is the agent's, so its account is the agent's too.

        Raises:
          subprocess.CalledProcessError: If it stops without ever saying, which would leave a
            flow waiting on a server that is not there. Reported as a failed turn, because it
            is the turn that starts it that has nowhere to run.
        """
        self._argv = argv
        self._stopping = threading.Lock()
        self._stopped = False
        self._proc = subprocess.Popen(
            argv,
            # Its log is nobody's to read; what is wanted from it is the one line below.
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            encoding="utf-8",
            errors="replace",
            env=dict(env) if env else None,
            start_new_session=os.name != "nt",
        )
        assert self._proc.stdout is not None  # noqa: S101
        for line in self._proc.stdout:
            if (listening := _LISTENING.match(line.strip())) is not None:
                self._base = f"{listening[1]}/api/v1"
                self._token = listening[2]
                break
        else:
            raise Failed(
                self._proc.wait(), argv, "", f"{argv[0]} stopped without listening"
            )
        # A pipe nobody drains stops the daemon writing to it, so the rest of the log is read
        # and dropped rather than left to fill.
        threading.Thread(
            target=collections.deque, args=(self._proc.stdout, 0), daemon=True
        ).start()

    def call(self, method: str, path: str, body: Any = None) -> Any:
        """Makes one call to the daemon.

        Args:
          method: The HTTP method to make it with.
          path: The path under the daemon's API root.
          body: What to send as JSON, or None to send nothing.

        Returns:
          What the daemon answered with, unwrapped from its envelope.

        Raises:
          subprocess.CalledProcessError: If it refuses the call or cannot be reached, which is
            a failed turn however it failed -- reported the way every other backend reports one,
            so that a flow catches turns rather than transports.
        """
        # The address is the one this process just watched its own server announce, so the
        # scheme is http and the host is loopback whatever the audit rule fears.
        request = urllib.request.Request(  # noqa: S310
            self._base + path,
            data=None if body is None else json.dumps(body).encode(),
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=_CALL_SECONDS) as response:  # noqa: S310
                said: dict[str, Any] = json.load(response)
        except urllib.error.HTTPError as refused:
            raise Failed(
                refused.code, self._argv, "", refused.read().decode(errors="replace")
            ) from refused
        except OSError as unreachable:  # a daemon that died, or a call that timed out
            raise Failed(1, self._argv, "", str(unreachable)) from unreachable
        # A refusal arrives inside a 200: a word steered into a turn that has already ended
        # comes back as `{"code": 40402, "msg": ...}` with the status still OK. Read as an
        # answer, that is a word which never landed reading as one that did.
        if said.get("code"):
            raise Failed(
                1, self._argv, "", f"{path}: {said.get('msg') or said['code']}"
            )
        return said.get("data")

    def stop(self) -> None:
        """Takes the daemon and its children down, leaving its sessions on disk."""
        with self._stopping:
            if self._stopped:
                return
            self._stopped = True
            if os.name == "nt":
                if self._proc.poll() is None:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=_STOP_SECONDS)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
                self._proc.wait()
                return

            # Provider wrappers and Kimi share this dedicated group. Taking down the group
            # prevents a stopped flow from leaving either wrapper or daemon behind.
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self._proc.pid, signal.SIGTERM)
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._proc.wait(timeout=_STOP_SECONDS)
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self._proc.pid, signal.SIGKILL)
            self._proc.wait()


@dataclass(frozen=True, kw_only=True)
class KimiCodeCLIAgentConfig(AgentConfig):
    """What Kimi Code is configured with: a model, an effort saying width too, and a daemon.

    The daemon fields are here because of a rule this repository holds every backend to: the
    default of an option is the harness's own default, so that an install which sets nothing
    behaves as the bare CLI does, and anything humanize puts on top is a field somebody can
    take back off. Three of the four below break that rule on purpose, and say which way.
    ``kimi web`` is written for a person who runs one of them at a terminal and wants a
    browser; this driver runs one per agent, unattended, and reads its first line. Left at the
    CLI's own defaults, two agents would collide on port 58627, eight would open eight browser
    windows, and none of them would print an address a machine can read. So the defaults here
    are the unattended ones, the departure is named in each attribute, and a flow that wants
    the CLI's behaviour back can have it -- except at ``silent``, which is the one setting that
    would leave the daemon unreachable rather than merely different.

    Attributes:
      effort: How hard to think, in Kimi's own wording, optionally prefixed `swarm` to run
        every turn as a fleet of subagents rather than as one agent -- `max` and `swarmmax` are
        the same thinking at either width.
      port: What to bind the daemon to. 0, not the CLI's 58627, and this is the one departure
        that is not a preference: one daemon per agent means a flow with two Kimi agents
        starts two, and a fixed port makes the second one fail to bind. 0 asks the system for
        a free one and the ready line says which it got. Setting it -- for a flow that means
        to reach the same daemon from outside, say -- is taking on both of the ways that can
        go wrong: that nothing else on the machine wants that port, and that this agent never
        starts a second daemon. It starts one whenever its account changes, and lets go of the
        old one rather than stopping it, so an agent that falls back on a fixed port tries to
        bind a port its own predecessor is still holding and fails the turn that asked.
      open_browser: Whether to open the web UI as the daemon comes up. False, where the CLI
        opens one, because a flow running unattended has no browser to open and a run on a
        headless machine would be asking `xdg-open` to do something about it. True is for
        watching a flow work: the UI is a real client of the same session the turns go to.
      log_level: How loudly the daemon logs, out of :data:`READABLE`. `error`, where the CLI
        logs nothing, and this is the departure that is load-bearing rather than merely
        sensible: at `silent` -- which is what omitting the flag means -- `kimi web` draws its
        ready output as a banner instead of printing the one line :data:`_LISTENING` reads, and
        a daemon whose address cannot be read is a daemon no turn can be submitted to. `error`
        is the quietest level that still prints the line, so it buys the address at the least
        noise. Raise it to watch the daemon; `silent` is refused.
      web_title: What the web UI calls itself in a browser tab, or None for the CLI's own
        `<workspace dir> | Kimi Code`. Worth having only because there is one daemon per agent:
        opened side by side, eight agents on one project are eight identical tabs, and the
        agent's name in the title is what tells them apart.
    """

    port: int = 0
    open_browser: bool = False
    log_level: str = "error"
    web_title: str | None = None

    def __post_init__(self) -> None:
        """Checks the daemon settings, where a flow can still be told which one it got wrong.

        Raises:
          ValueError: If the port is not one, if the log level is not one Kimi takes, or if it
            is `silent` -- which the daemon accepts and this driver cannot read back.
        """
        super().__post_init__()
        if not 0 <= self.port <= _PORT_MAX:
            raise ValueError(f"port must be between 0 and {_PORT_MAX}, not {self.port}")
        if self.log_level == _BANNERED:
            raise ValueError(
                f"log_level {_BANNERED!r} makes `kimi web` draw its ready banner instead of "
                "printing the line this driver reads its address from"
            )
        if self.log_level not in READABLE:
            raise ValueError(
                f"log_level must be one of {', '.join(READABLE)}, "
                f"not {self.log_level!r}"
            )
        if self.web_title is not None and not self.web_title.strip():
            raise ValueError("web_title must say something, or be None for Kimi's own")


class KimiCodeCLISession(SessionBase):
    """A Kimi Code conversation, held by the app server and named by it as it opens.

    The id is the server's, handed out before the turn rather than read back out of a resume
    hint, so a second agent working alongside cannot be resumed by mistake.
    """

    _agent: KimiCodeCLIAgent  # every turn is submitted to the server this agent holds

    #: A prompt sent to a session the daemon is already working is queued behind as a turn of
    #: its own; steering moves it into the turn that is running, which is what makes it a word
    #: put in rather than one waiting.
    steers: ClassVar[bool] = True

    def __init__(
        self, agent: AgentBase, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        """Initializes a session running nothing yet.

        Args:
          agent: The agent whose config every turn of this session runs at.
          cwd: The directory this conversation works in, as for `SessionBase`.
        """
        super().__init__(agent, cwd)
        #: The turn under way, which is what a word put in is steered into.
        self._running = _Running()
        #: What this session has cost so far, by kind, as the daemon counts it: a running
        #: total for the whole conversation, so what one turn cost is the rise across it.
        self._counted: Counter[str] = Counter()
        #: The same total as the daemon's own step frames have added it up, kept beside the
        #: aggregate rather than instead of it because the two are read together. For the
        #: whole conversation and not for one turn of it, for the reason above: the meter is
        #: told a rise, and a total that started again at nothing each turn would report a
        #: rise only where a turn cost more than the turn before it did.
        self._stepped: Counter[str] = Counter()
        #: What the daemon was last told this session runs at, so a turn at the same
        #: settings does not tell it again -- and which daemon was told it. Both, because a
        #: profile is state that daemon holds rather than a fact about the session: an agent
        #: that fell back, or whose daemon the watchdog put down, is served by one that was
        #: never told, and a cache that outlived the thing it describes would leave that
        #: turn running at the CLI's own settings instead of at this agent's.
        self._profile: dict[str, Any] = {}
        self._profiled: _AppServer | None = None
        #: How this daemon takes each of the two pending lists. Its own querystring says
        #: `status` is required on both, and a build that never had it refuses the same
        #: thing; whichever answered is kept rather than found again every poll. Kept per
        #: route rather than once for the daemon, because what the flip costs is not the
        #: same on both: the unfiltered question list is the one that need not leave out
        #: what has been answered already, so a hiccup on the approvals route moving the
        #: question route onto it would have the flow answer an answered question again.
        self._filter: dict[str, str] = dict.fromkeys(_HELD, "?status=pending")
        #: Which of :data:`_HELD` this daemon turned out not to serve, so that a build
        #: without one of them is asked once rather than twice a second forever. Both
        #: spellings of a route answering 404 is the build saying it has no such route,
        #: and a build does not grow one while a turn is running.
        self._unserved: set[str] = set()
        #: Every approval this session has already answered. The list the daemon holds is
        #: its unresolved ones, so on 0.42.0 an answered approval is gone from it by the
        #: time it is read again -- but nothing on the wire says so. An approval carries no
        #: `status`: `toWireApproval` gives an id, the tool, the action, the call and two
        #: timestamps, and the filtering is the server's own `findAll({resolved: false})`.
        #: So a build that listed a resolved one anyway -- or a bare-path fallback onto a
        #: list that does not leave them out -- would have this driver answer it a second
        #: time, and a second answer is refused (`approval X already resolved`) every
        #: second until the turn dies of it. Remembered here instead, which also keeps
        #: `PERMISSION_REQUEST` at one firing per tool call rather than one per poll.
        self._answered: set[str] = set()

    @property
    def named(self) -> str | None:
        """The session the daemon holds, which it names as the turn opens it."""
        return self._id or self._running.session

    def interject(self, text: str) -> None:
        """Puts a word into the turn already running, rather than into the next one.

        A prompt sent to a session that is working is queued, and would be answered as a turn
        of its own once this one ended. Steering moves it into the turn that is running, which
        is what makes it a word put in rather than a turn queued behind.

        Args:
          text: What to say to the agent.

        Raises:
          RuntimeError: If no turn is running, so there is none to steer it into.
          subprocess.CalledProcessError: If the daemon refuses either call.
        """
        running = self._running
        if running.session is None:
            raise RuntimeError("no turn is running to be talked to")
        # Named by its own words: Kimi mints a fresh id for a steered prompt, so the id it
        # answers with is not the one it took, and the words are what both ends have.
        self.steering(text, ticket=text)
        server = self._agent.server
        queued = server.call(
            "POST",
            f"/sessions/{running.session}/prompts",
            {"content": [{"type": "text", "text": text}], **running.config},
        )
        try:
            server.call(
                "POST",
                f"/sessions/{running.session}/prompts:steer",
                {"prompt_ids": [queued["prompt_id"]]},
            )
        except BaseException:
            self.unsteered(text)  # nothing is coming back for a word that never went in
            raise

    def _stream(
        self,
        prompt: str,
        *,
        schema: type[BaseModel] | None = None,  # noqa: ARG002
    ) -> Iterator[Event]:
        """Sends one turn, opening the session on the first call and resuming it after.

        The daemon answers a turn whole, but it writes the turn down as it goes: what the
        agent said is read back as it is written, which is what makes the turn watchable.

        A shape is not a setting of a turn here -- the daemon takes a prompt and nothing
        else about the answer -- so a turn asked for one has already been asked in the
        prompt, which is what :attr:`SessionBase.shapes` says of this backend.
        """
        yield from self._submit(prompt, goal=False)

    def _held(self, session: str, what: str) -> list[Any]:
        """Whatever the daemon is holding on one of the two routes a turn stops against.

        The same reading for both: a filtered list whose spelling the daemon decides, and a
        body that is either the list or the list under `items`.

        Args:
          session: The session the turn is running in.
          what: Which of :data:`_HELD` to read.

        Returns:
          What is waiting there, which is nothing at all where the turn has not stopped.

        Raises:
          subprocess.CalledProcessError: If the daemon will not say either way.
        """
        if what in self._unserved:
            return []
        server = self._agent.server
        route = f"/sessions/{session}/{what}"
        try:
            held = server.call("GET", route + self._filter[what])
        except subprocess.CalledProcessError as refusal:
            # This daemon's querystring is `{status: "pending"}` and it refuses the bare
            # path; one that has never heard of that filter refuses the other. Which way
            # round it is, is the daemon's business -- but a turn waiting on an answer
            # cannot be left holding a refusal, so the one is asked and then the other.
            other = "" if self._filter[what] else "?status=pending"
            try:
                held = server.call("GET", route + other)
            except subprocess.CalledProcessError as missing:
                # Neither spelling, and at least one of them for want of the route rather
                # than of an answer: this daemon does not serve it. Which is nothing held
                # rather than something unreadable -- a build old enough to have no
                # approvals route raises no approvals either, and failing its turns over a
                # list it was never going to fill would be this reading costing what it
                # exists to save. Written down rather than found again: one `kimi web`
                # serves every session of its agent, and two refused calls a second on a
                # route it will never grow is the shared daemon paying for a reading that
                # cannot answer. Said once, and asked no more for the life of the session.
                if _ABSENT in (refusal.returncode, missing.returncode):
                    self._unserved.add(what)
                    return []
                raise
            # Which one answered is kept, so that a poll a second is not a refusal a second
            # on the daemon every session of the agent shares -- but only where the daemon
            # refused with a status of its own, which a connection that dropped or a call
            # that timed out never carries. A daemon that takes both spellings would
            # otherwise be moved, by one hiccup, onto a list that need not leave out what
            # has been answered already, and put an answered question again every second --
            # which is not merely noisier than a wasted call but unrecoverable, since the
            # flow has already acted on the first answer.
            if refusal.returncode >= _REFUSED:
                self._filter[what] = other
        return (
            cast("list[Any]", cast("dict[str, Any]", held).get("items") or [])
            if isinstance(held, dict)
            else cast("list[Any]", held or [])
        )

    def _approved(self, session: str) -> None:
        """Answers whatever the turn has stopped to have approved, and lets a hook refuse it.

        The other of the two things a turn stops on, and the one that used to stop it for
        good: the daemon holds an approval until it is resolved, and a poll that read only
        `/questions` left the session busy against a route nothing was answering. Every mode
        but `auto` raises them, which is what makes the rungs above a ladder rather than one
        setting written four times.

        Answered yes at the rungs that mean granting -- :data:`_GRANTED` -- because nobody is
        at a prompt there and the rung has already said what the agent may do. Answered no at
        the two that do not: `read-only`, where every approval that gets this far is by
        construction a tool that is not a read, and the silence, where nothing said what this
        agent may do and so nothing said yes.

        Put to `PERMISSION_REQUEST` first either way, because this is the moment the backend
        actually waits on and so the one place a hook here can stop an agent doing something --
        and because a flow that hung one at a withholding rung asked to be the one deciding.
        A refusal, the hook's or the rung's, is `rejected` with the reason, which the daemon
        hands the model as a line saying the tool was not run: the turn goes on, having been
        refused, rather than ending or hanging.

        Once apiece, by the id the daemon gave it: an approval answered a second time is
        refused rather than resolved, and a refusal a second is a working turn dying inside
        the recovery window for having done its job twice.

        Args:
          session: The session the turn is running in.

        Raises:
          subprocess.CalledProcessError: If the daemon will not say either way, for the same
            reason a question that cannot be read is a turn that never ends.
        """
        for raw in self._held(session, _HELD[1]):
            pending = cast("dict[str, Any]", raw)
            if not (approval := pending.get("approval_id")):
                continue  # not an approval, whatever else the daemon answered with
            if (named := str(approval)) in self._answered:
                continue  # answered already, and the daemon takes one answer
            self._answered.add(named)
            asking = self._fire(
                Moment.PERMISSION_REQUEST,
                tool=str(pending.get("tool_name") or ""),
                about=str(pending.get("action") or ""),
                called=pending,
            )
            allowed, refused = _ANSWERS
            if asking.refused:
                answer = {
                    "decision": refused,
                    "feedback": asking.because or "refused by a hook",
                }
            elif (rung := self._agent.config.permission) in _GRANTED:
                answer = {"decision": allowed}
            else:
                answer = {
                    "decision": refused,
                    "feedback": f"this agent runs at {rung}, which withholds approval"
                    if rung
                    else "nothing said what this agent may do",
                }
            self._agent.server.call(
                "POST", f"/sessions/{session}/approvals/{named}", answer
            )

    def _asked(self, session: str) -> None:
        """Answers whatever the turn has stopped to ask, if it has stopped to ask anything.

        The daemon holds a question until it is answered and the turn waits on it, so a poll
        that only read messages would read a session that never moves again. An answer is
        matched to one of the options where it names one, since a question that offered them
        need not take anything else; a question nobody is there to answer is skipped, which
        the tool reads as an answer and carries on from.

        Args:
          session: The session the turn is running in.

        Raises:
          subprocess.CalledProcessError: If the daemon will not say either way. A turn that
            has stopped to ask and cannot be asked never moves again, so a turn whose caller
            keeps getting this fails rather than polling on forever; one that gets it once
            carries on, because a hiccup is not a daemon that has stopped answering.
        """
        for raw in self._held(session, _HELD[0]):
            pending = cast("dict[str, Any]", raw)
            if not pending.get("question_id"):
                continue  # not a question, whatever else the daemon answered with
            answers: dict[str, dict[str, Any]] = {}
            for asked in cast("list[Any]", pending.get("questions") or []):
                question = cast("dict[str, Any]", asked)
                offers: list[Any] = question.get("options") or []
                options = {
                    str(cast("dict[str, Any]", option).get("label", "")).lower(): cast(
                        "dict[str, Any]", option
                    ).get("id")
                    for option in offers
                    if isinstance(option, dict)
                }
                said = self._agent.asked(
                    Question(
                        text=str(
                            question.get("question") or question.get("header") or ""
                        ),
                        options=tuple(
                            str(cast("dict[str, Any]", option)["label"])
                            for option in offers
                            if isinstance(option, dict)
                            and cast("dict[str, Any]", option).get("label")
                        ),
                    )
                )
                if said is None:
                    answers[str(question["id"])] = {"kind": "skipped"}
                elif (chosen := options.get(said.strip().lower())) is not None:
                    answers[str(question["id"])] = {
                        "kind": "single",
                        "option_id": chosen,
                    }
                else:
                    answers[str(question["id"])] = {"kind": "other", "text": said}
            self._agent.server.call(
                "POST",
                f"/sessions/{session}/questions/{pending['question_id']}",
                {"answers": answers},
            )

    def _lets_go(self) -> None:
        """Takes down the daemon, which is what a wedged turn here is waiting on.

        The agent's rather than this session's: one daemon serves every conversation with it,
        so there is nothing of this one's own to put down, and every other turn on this agent
        goes with it. The sessions survive: the next turn starts another daemon and resumes
        this one by the id it already has.
        """
        self._agent._down()

    def _counting(self, server: _AppServer, session: str) -> Usage:
        """What this session has spent since the last time it was asked.

        The daemon counts the whole conversation, so what has been spent since is the rise
        across it. Told to the meters as it is read, which is what a rate taken while the turn
        is still running is made of.

        Two reckonings of the same conversation, and the larger of the two kind by kind. The
        aggregate the session route answers with is one of them, and on 0.42.0 it is four
        zeros forever (see :data:`_KINDS`); what its steps have said they cost is the other,
        and on a build whose aggregate works the aggregate is the larger, being the whole
        session's life rather than only the part of it this driver listened to. So the larger
        is the most that can be accounted for either way -- and taking it that way round is
        what stops an aggregate that is only ever zero from erasing counts that are real.
        Larger is also what keeps the reading rising, which is what a rise across it can be
        read from at all: a total that fell would be a turn's spending quietly dropped.

        Args:
          server: The daemon holding the session.
          session: The session to ask about.

        Returns:
          The rise since the last reading, by kind, which is nothing at all where it has not
          moved.

        Raises:
          subprocess.CalledProcessError: If the daemon will not say, which is not a failed
            turn: what a run costs is worth nothing at the price of the run.
        """
        held = server.call("GET", f"/sessions/{session}")
        usage: dict[str, Any] = (
            cast("dict[str, Any]", held).get("usage") or {}
            if isinstance(held, dict)
            else {}
        )
        counted = Counter(
            {
                kind: tokens
                for kind, named in _KINDS.items()
                if (tokens := max(int(usage.get(named) or 0), self._stepped[kind])) > 0
            }
        )
        risen = Usage(
            {
                kind: tokens
                for kind in set(counted) | set(self._counted)
                if (tokens := counted[kind] - self._counted[kind]) > 0
            }
        )
        self._counted = counted
        self._spends(risen)
        return risen

    def _pursue(self, objective: str) -> str:
        """Runs the turn under a goal of Kimi's own, which its runtime steers until it is met.

        The objective is the prompt as well as the goal, which is what ``/goal`` does: the
        agent is told what to do, and the runtime is told what it is for.

        Returns:
          The agent's response once the goal is done with, stripped.
        """
        said = ""
        for event in self._submit(objective, goal=True):
            # Told to whoever is watching, since a goal does not run through `stream`: it is
            # one prompt and as many turns of the model as the objective takes.
            self._agent._heard(event)
            if event.kind == "result":
                said = event.text
        return said.strip()

    def _fork(self, whence: str) -> str:
        """Cuts a second conversation from one the daemon is holding, as `kimi fork` does.

        The CLI's own command rather than the daemon's route for it: `POST /sessions/<id>
        ::fork` is dispatched to a manager that knows none of the workspaces the sessions are
        actually in, and refuses every one of them as a session that does not exist. The
        command is the same engine doing the same thing from the outside, and it says which
        session it made on the one line it prints -- which is the whole of what is read back.

        Run as this agent's account and in this conversation's directory, so that a fork is
        cut where the conversation is and out of the store that account writes.

        Args:
          whence: The conversation to cut from, by the id the daemon gave it.

        Returns:
          The new session's id, which is this session's from here on.

        Raises:
          subprocess.CalledProcessError: If the fork will not run, will not answer, or runs
            and names no session -- which leaves this session unopened, so the next turn
            tries again.
        """
        argv = self._agent.spawned(
            ["kimi", "fork", whence, "--yes", "--cwd", self._workspace()], self.cwd
        )
        try:
            ran = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                check=False,
                env=self._environ(),
                # The same ceiling every call to this backend is under: a fork is one read
                # and one write of a conversation, and a flow waiting forever on one is a
                # flow that has stopped.
                timeout=_CALL_SECONDS,
            )
        except subprocess.TimeoutExpired as slow:
            raise Failed(
                1, argv, "", f"kimi fork took longer than {_CALL_SECONDS:.0f}s"
            ) from slow
        found = _FORKED.search(ran.stdout)
        if ran.returncode != 0 or found is None:
            raise Failed(
                ran.returncode or 1,
                argv,
                ran.stdout,
                ran.stderr.strip() or "kimi fork named no session",
            )
        return found.group(1)

    def _submit(self, prompt: str, *, goal: bool) -> Iterator[Event]:
        """Runs one turn, saying what the agent says as it says it.

        A goal-driven turn is many turns of the model, and it is over when the session falls
        idle rather than when the first of them ends. The session is asked whether it is still
        running before its messages are read, so that nothing said between the two is missed.

        Args:
          prompt: The input prompt for this turn, which is the objective as well when it is
            a goal the session is being set.
          goal: Whether to set the prompt as the session's goal before sending it.

        Yields:
          What the agent said, in the order it said it, and the answer it ended on.

        Raises:
          subprocess.CalledProcessError: If the daemon refuses any of the calls a turn is made
            of, leaving the session unopened so that the next call retries the turn.
        """
        effort = self.effort
        turn: dict[str, Any] = {
            "model": self._agent.config.model,
            # The rung where there is one, and the width beside it. An agent at no rung sends
            # neither: Kimi then runs the model at its own thinking level, where a `thinking`
            # of "" is a level it has no word for. A fleet is a width rather than a rung, so
            # it is asked for only where a rung said so.
            **({"thinking": effort.removeprefix(SWARM)} if effort else {}),
            "swarm_mode": effort.startswith(SWARM),
            # What it may do without being asked, where a rung said. An agent at no rung
            # sends neither key and is left wherever this install's own `kimi web` leaves it,
            # which is what a config written before there was a rung to write comes back off
            # the disk as too.
            **_PERMITTED.get(self._agent.config.permission, _PERMITTED[UNSAID]),
        }
        updates: _Updates | None = None
        with self._lock:  # a conversation is a sequence: one turn at a time
            # A turn that failed is as over as one that landed: neither leaves
            # anything for a word to be steered into.
            try:
                server = self._agent.server
                # A session of its own per attempt while this one is unopened: an opening turn that
                # failed leaves the daemon holding a conversation nothing landed in, and resuming
                # that one would be resuming a turn that never happened.
                if (session := self._id) is None:
                    # A fork cuts its conversation from the one it came from rather than
                    # starting one; anything else starts one here.
                    session = (
                        self._fork(self._forked_from)
                        if self._forked_from is not None
                        else server.call(
                            "POST",
                            "/sessions",
                            {"metadata": {"cwd": self._workspace()}},
                        )["id"]
                    )
                    # A session of its own is a session set nothing yet.
                    self._profile, self._profiled = {}, None
                # The settings are the session's rather than the turn's, which is the whole
                # reason there is a server here -- so a second turn at the same settings is
                # a session that already has them. Said again only when it would say
                # something different, because one daemon serves every session of its agent
                # and a call that changes nothing is a call the others wait behind. A goal
                # is the exception: it is something the runtime is set going on rather than
                # a setting it holds, and the same objective again is asking for it again.
                profile = turn | ({"goal_objective": prompt} if goal else {})
                if goal or profile != self._profile or server is not self._profiled:
                    server.call(
                        "POST",
                        f"/sessions/{session}/profile",
                        {"agent_config": profile},
                    )
                    self._profile, self._profiled = profile, server
                updates = _Updates(server._base, server._token, session, self._stepped)
                # Said before the prompt goes in, so that a word put in has a session to be
                # steered into from the moment there is a turn to interrupt.
                self._running = _Running(session=session, config=turn)
                since = server.call(
                    "POST",
                    f"/sessions/{session}/prompts",
                    {"content": [{"type": "text", "text": prompt}], **turn},
                )["user_message_id"]
                answer = ""
                shown: dict[
                    str, int
                ] = {}  # how much of each message has been passed on
                settled = False
                refused = 0.0  # since when the daemon has not answered about questions
                # Whether anything at all has been seen of this turn: the session working,
                # the daemon saying the turn ended, or a word of it written down. Until one
                # of them a session that is not busy is a session that has not started --
                # the daemon takes a prompt before it runs it -- and a turn read back there
                # would answer with what had not been said. A daemon that says none of the
                # three for a whole recovery window has said all it is going to.
                stirred = False
                opened = time.monotonic()
                costing = Usage()  # what this turn has come to, added up as it goes
                # When each of the two readings that are not made every time round was last
                # made, so that a turn told nothing still makes them at the cadence it made
                # them at before there were notifications at all. What the daemon says brings
                # one forward; nothing the daemon says can put one off. One `kimi web` serves
                # every session of its agent from one thread, so a reading skipped here is
                # not this turn going faster -- it is the other seven not queueing behind it.
                read_at = {"asked": 0.0, "counted": 0.0}

                def due(what: str, *, told: bool = False) -> bool:
                    if not told and time.monotonic() - read_at[what] < _POLL_SECONDS:
                        return False
                    read_at[what] = time.monotonic()
                    return True

                # Under a clock. Nothing here blocks forever on its own -- every call the
                # daemon takes is bounded -- but a session that answers `busy` and never says
                # another word is a turn that polls until somebody stops it, which is the same
                # hang read off a different pipe. So the clock is patted by what the agent
                # says rather than by the daemon answering, and looks at the daemon's own
                # process before believing anything is wrong.
                with Watchdog(self, riding=lambda: server._proc) as watch:
                    while True:
                        # First of all: a turn that has stopped -- to ask, or to have a tool
                        # approved -- waits on the answer, so a poll that only read messages
                        # would be reading a session that has stopped moving. Asked at once
                        # when the daemon has said there may be
                        # something to answer, and a second apart when it has not: one daemon
                        # serves every session of the agent, and asking it per notification what
                        # it has already said it has none of is the one cost here that buys
                        # nothing. Taken off the book before the reading rather than after, so
                        # that a question raised while it runs is a question read next time
                        # round rather than one this turn waits on forever. One refusal is a
                        # hiccup on a daemon eight sessions are queueing on, not a turn to throw
                        # minutes of work away over: it is carried on from and asked again on
                        # the same second. A daemon that has refused it for a whole recovery
                        # window has stopped answering it, and a question nobody can read is a
                        # turn that never ends -- so that one is a failed turn.
                        if due("asked", told=updates.questioned):
                            updates.questioned = False
                            # Both of them, every time, and neither behind the other: a
                            # question and an approval are separate routes a turn can be
                            # stopped on, and a daemon refusing one of them for a while
                            # must not leave the other unread. So each is asked, and a
                            # refusal is carried until both have been.
                            stopped: subprocess.CalledProcessError | None = None
                            for reading in (self._asked, self._approved):
                                try:
                                    reading(session)
                                except subprocess.CalledProcessError as refusal:
                                    stopped = stopped or refusal
                            if stopped is None:
                                refused = 0.0
                            else:
                                refused = refused or time.monotonic()
                                if time.monotonic() - refused >= _RECOVERY_SECONDS:
                                    raise stopped
                        # Whether it is still working, which is the reading a turn ends on --
                        # and the one read here that is made every time round, because it is
                        # also what paces the round. A session read as stopped is a wait of a
                        # second below rather than another notification, so a reader that put
                        # this on a cadence of its own would spend that second reading the
                        # history over and over instead of waiting the frames out. Measured, and
                        # written down in `bench/cli-concurrency/REJECTED.md`.
                        busy = server.call("GET", f"/sessions/{session}/status")["busy"]
                        # What it has come to so far, asked for each time round rather than once
                        # at the end: a turn is minutes long, and a rate that only moved when one
                        # ended would stand still for all of them. A daemon that will not say is
                        # not a failed turn. A second apart and no faster, whatever the daemon
                        # says has landed: a meter is not something a turn waits on, and what a
                        # skipped reading would have added is still in the total, which is read
                        # once more as the turn settles.
                        if due("counted"):
                            with contextlib.suppress(subprocess.CalledProcessError):
                                costing = costing + self._counting(server, session)
                        if goal and not busy:
                            # A goal runs through the quiet between its turns: Kimi starts
                            # the next one itself once the session falls still, so a session
                            # that has stopped is a goal that has stopped only when the goal
                            # is no longer being pursued.
                            pursued = server.call("GET", f"/sessions/{session}/goal")
                            busy = pursued is not None and pursued["status"] == "active"
                        said = server.call(
                            "GET", f"/sessions/{session}/messages?after_id={since}"
                        )["items"]
                        stirred = (
                            stirred
                            or busy
                            or updates.ended
                            or bool(said)
                            or time.monotonic() - opened >= _RECOVERY_SECONDS
                        )
                        # A message is readable while it is still being written, so the turn
                        # is read again from its own first message every poll rather than
                        # once: a message put aside as seen would be the one the agent had
                        # only started saying. Newest first, and a turn reads forwards; what
                        # has been passed on is not passed on twice.
                        #
                        # And a message readable while it is being written grows its last
                        # block in place, so a block of words at the end of the newest one is
                        # half a sentence until something follows it: shown as it stands it is
                        # a paragraph broken across as many parts as the turn was polled, with
                        # the rest of it never shown at all, the array having grown no longer.
                        # So that one waits for the block after it, or for the turn to be over.
                        # Only that one: every earlier block is finished, and a tool block is
                        # whole the moment it is there -- a turn that reached for something
                        # says so as it reaches.
                        writing = (
                            ""
                            if settled
                            else next(
                                (
                                    str(one["id"])
                                    for one in said
                                    if one["role"] == "assistant"
                                ),
                                "",
                            )
                        )
                        for message in reversed(said):
                            if message["role"] != "assistant":
                                # A word put into the turn, spliced into the conversation at the
                                # step that takes it in: that splice is the agent saying it has
                                # it, and is the only thing here that is not the agent talking.
                                # Read as one, it would show your own words back as the agent's.
                                if message["id"] not in shown:
                                    shown[message["id"]] = len(message["content"])
                                    words = "".join(
                                        block.get("text") or ""
                                        for block in message["content"]
                                        if block.get("type") == "text"
                                    )
                                    if self.took(words) is not None:
                                        watch.saw()
                                        with watch.held():
                                            yield Event(kind="took", text=words)
                                continue
                            content = message["content"]
                            ready = len(content) - (
                                1
                                if content
                                and message["id"] == writing
                                and str(content[-1].get("type")) in _GROWS
                                else 0
                            )
                            for block in content[shown.get(message["id"], 0) : ready]:
                                kind = _BLOCKS.get(str(block.get("type")))
                                # A tool is named by what it is; everything else is what it says,
                                # which a block keeps under its own name -- text under `text`.
                                words = str(
                                    (
                                        block.get("tool_name")
                                        if kind == "tool"
                                        else block.get(str(block.get("type")))
                                    )
                                    or ""
                                )
                                if kind is None or not words.strip():
                                    continue
                                if not self._agent._watchers:
                                    # On stderr, where every other backend puts its progress:
                                    # a turn nobody can watch is a flow that reads as hung for
                                    # as long as the turn takes. Something watching the agent
                                    # shows the turn itself, and would be showing it twice.
                                    say(words, sys.stderr)
                                watch.saw()
                                with watch.held():  # a pause of ours is not its silence
                                    yield Event(kind=kind, text=words)
                            shown[message["id"]] = ready
                        # And the answer is taken fresh each time, so that it is what the
                        # agent ended up saying rather than what it had said when it was
                        # first readable.
                        for message in (
                            said
                        ):  # newest first: the last thing said that has any words
                            text = "".join(
                                block["text"]
                                for block in message["content"]
                                if block["type"] == "text"
                            )
                            if message["role"] == "assistant" and text:
                                answer = text
                                break
                        if stirred and settled and not busy:
                            # Taken note of before it is passed on: a turn that landed is a session
                            # this agent opened, whether or not there is anywhere left to say so.
                            self._adopt(session)
                            if not self._agent._watchers:
                                # Where the CLI would have put the response. Something watching
                                # the agent has had it already, as the turn said it.
                                say(answer, sys.stdout)
                            # What the turn cost: the daemon counts the whole session, so what
                            # this turn spent is the rise across it, added up as the turn went.
                            # Asked once more here and never at the cost of the answer -- a turn
                            # that landed has landed, whatever the daemon then says it came to.
                            with contextlib.suppress(subprocess.CalledProcessError):
                                costing = costing + self._counting(server, session)
                            spent = (
                                {self._agent.config.model: int(costing.total)}
                                if costing.total > 0
                                else {}
                            )
                            yield Event(
                                kind="result",
                                text=answer.strip(),
                                tokens=spent,
                                spent=costing,
                            )
                            return
                        # A session says it has stopped before the last thing it said can be read
                        # back, so what it said is read once more after it stops rather than at the
                        # moment it does -- otherwise a turn returns everything but its answer.
                        # And a session that has not started yet is a session that is not busy
                        # too: the daemon takes a prompt before it runs it, so one still reading
                        # is not a turn that is over. It takes two of them, a wait apart, and a
                        # turn that has stirred, for what is read back to be this turn rather
                        # than the moment before it.
                        settled = not busy
                        updates.wait(settled=settled)

            finally:
                if updates is not None:
                    updates.close()
                self._running = _Running()


class KimiCodeCLIAgent(AgentBase):
    """Kimi Code, driven through an app server of its own so a whole session is settable.

    Every moment a turn passes through, and one more: the daemon holds the tool it is about
    to run on `/approvals` until somebody resolves it, and that is the one place a hook here
    can say no to something and have the agent hear it.
    """

    #: Said of the backend and not of the rung, by the rule this repository settles the
    #: question with: a backend that holds a tool until its client answers is a backend where
    #: this moment is real. Kimi holds it -- `/approvals` keeps the call, the turn waits, and
    #: a `rejected` is a line the model reads -- so the moment is declared, once, for the
    #: class. What a given rung does with it is a fact about the run, the way a turn that
    #: calls no tool is a run in which `PRE_TOOL_USE` never arrives. :class:`Unhooked` is for
    #: a hook hung where the backend could never have answered it, which is not this.
    #:
    #: Being exact about what a hook here buys, rung by rung, because the grant gate narrowed
    #: it. At `workspace-write` and `bypass` -- Kimi's `auto`, which approves before any
    #: policy can ask -- no approval is raised and the hook never fires. At `auto`, Kimi's
    #: `yolo`, it is the whole decision: the dangerous command, the sensitive file and the
    #: `.git` path are asked about, and :data:`_GRANTED` says yes where the hook says
    #: nothing. At `read-only` and at no rung at all the answer was already no, so what a
    #: hook there gets is the sight of the tool and the chance to say why -- not the casting
    #: vote. It cannot turn that no into a yes, and should not be able to: a
    #: :class:`~hmz.coganchor.agents.hooks.Verdict` can refuse or say nothing, and a hook that
    #: only watches must never be the thing that widens a rung.
    #:
    #: So one rung of the five is where this changes an outcome. Declared for all of them
    #: anyway, because the rung is the thing that moves: a place may narrow one after the
    #: agent is built, and the rung an agent comes at is a default rather than a fact about
    #: this backend. A capability that went false and true as a setting moved under it would
    #: be a worse promise than one that is occasionally generous -- what this is read for is
    #: refusing a flow before its first turn, and a promise that changes between the reading
    #: and the turn refuses nothing.
    moments: ClassVar[frozenset[Moment]] = EVERYWHERE | {Moment.PERMISSION_REQUEST}

    #: Kimi keeps itself going toward an objective, which is what `pursue` reaches for.
    pursues: ClassVar[bool] = True

    #: What it counts, read off the same table its driver reads a usage with, so that
    #: what a run is told this backend reports is what its driver actually parses.
    counts: ClassVar[frozenset[str]] = frozenset(_KINDS)

    def __init__(self, config: AgentConfig, *, name: str | None = None) -> None:
        """Initializes an agent whose server is not running yet.

        Args:
          config: The model and effort every session of this agent runs at.
          name: What to call this agent, defaulting to one nothing else answers to.
        """
        super().__init__(config, name=name)
        self._server: _AppServer | None = None
        #: Which account the daemon up now was started as: an agent that has fallen back
        #: starts another rather than going on submitting turns as somebody else.
        self._server_as = ""
        self._serving = threading.Lock()

    def environment(self) -> Mapping[str, str]:
        """What this agent's daemon is started with, plus the preload where one is wanted.

        On the agent rather than on a session because the daemon is the agent's: one process holds
        every conversation with it, so there is one runtime to load anything into and it is started
        once, with this. :mod:`hmz.coganchor.agents.preload` is what decides whether one is wanted
        -- Kimi Code is a Node program, so what a turn of it runs, reads, writes and opens can be
        read from inside the process taking it.

        Started once is also the whole of the catch: the question is asked where the daemon is
        started, so a hook hung after that gets nothing from this backend for as long as the
        agent lives. A backend that is a process a turn asks it again every turn.

        Returns:
          The provider's own variables, and the preload beside them for an agent something is
          listening to.
        """
        return preloaded(self, super().environment())

    @property
    def server(self) -> _AppServer:
        """The daemon this agent's turns are submitted to, started the first time it is asked for.

        One per agent rather than one per session, so that a flow dropping a session a turn
        does not start a server a turn; it is taken down when the agent is collected, or at
        exit for one held to the end. An anchored agent starts it through coganchor, which
        leaves the server here, holding the conversation, and its work on the target -- the
        same split the CLI ran under.
        """
        with (
            self._serving
        ):  # two sessions of one agent share the server rather than start two
            if self._server is not None and self._server_as != self.node().name:
                # Started as an account this agent has since left. Let go of rather than
                # taken down: a turn on another thread may still be talking to it, and its
                # own finalizer stops it when the agent is collected either way.
                self._server, self._server_as = None, ""
            if self._server is None:
                # Read off the config with defaults beside them, because an agent may be
                # given the common `AgentConfig` rather than Kimi's own: a flow that never
                # asked for any of this gets the daemon this driver has always started.
                # `--no-open` and the level are written out rather than left off, since
                # what the CLI does when they are missing is a browser and a banner.
                argv = ["kimi", "web"]
                if not getattr(self.config, "open_browser", False):
                    argv.append("--no-open")
                argv += [
                    "--port",
                    str(getattr(self.config, "port", 0)),
                    "--log-level",
                    getattr(self.config, "log_level", "error"),
                ]
                if title := getattr(self.config, "web_title", None):
                    argv += ["--web-title", title]
                # Read before the environment is built out of it: a fallback landing
                # between the two reads would name the account this server is *not* signed
                # into, and a server that believes it is already elsewhere is one nothing ever
                # starts again.
                account = self.node().name
                self._server = _AppServer(self.spawned(argv), self._environ())
                self._server_as = account
                # Held by the finalizer alone, which is what takes the daemon down: when the
                # agent is collected, and at exit for one held to the end.
                weakref.finalize(self, self._server.stop)
            return self._server

    def stop(self) -> None:
        """Takes no further turn, and takes down the server the turn under way is waiting on."""
        super().stop()
        self._down()

    def _down(self) -> None:
        """Takes down the daemon this agent holds, if it is holding one."""
        with self._serving:
            server, self._server, self._server_as = self._server, None, ""
        if server is not None:
            server.stop()

    def new(self, cwd: str | os.PathLike[str] | None = None) -> KimiCodeCLISession:
        """Opens a new Kimi session, in the directory it is given or in this one."""
        return KimiCodeCLISession(self, cwd)
