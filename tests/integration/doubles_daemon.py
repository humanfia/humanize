"""What the daemon's integration tests share: flows that drive no agent, and ways to wait.

Each test has a temporary directory, and so a machine daemon, of its own (`tests/conftest.py`),
so a daemon started here is never one another test reaches. What is started is taken down by
:func:`hosting`, however the test ended.
"""

from __future__ import annotations

import contextlib
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING, Any

from hmz import daemon
from hmz.daemon import where

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

    import pytest

    from hmz.daemon import Link

#: How long a test waits for something another process is doing.
PATIENCE = 30.0

#: Waits for a file `go` before printing, writing to a descriptor and ending.
SAYS = """
import asyncio
import os
from pathlib import Path

from hmz.flows import AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=AgentCollection, envs=Envs, params=FlowParams, name="says")
async def says(task, *, agents, envs, params, ctx):
    while not Path("go").exists():
        await asyncio.sleep(0.02)
    print(f"{task} printed")
    os.write(2, f"{task} said straight to a descriptor\\n".encode())
"""

#: Asks two people outside the run one after the other, and writes down what each said.
ASKS = """
import json
from pathlib import Path

from hmz.flows import AgentCollection, EnvCollection, FlowParams, LocalEnv, Outworlder, flow


class Agents(AgentCollection):
    planner: Outworlder
    reviewer: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, name="asks")
async def asks(task, *, agents, envs, params, ctx):
    planner = await agents["planner"].spawn()
    reviewer = await agents["reviewer"].spawn()
    plan = await agents["planner"].run(f"plan {task}?", session=planner)
    review = await agents["reviewer"].run(f"is {plan!r} good?", session=reviewer)
    Path("result.json").write_text(json.dumps({"plan": plan, "review": review}))
"""

#: Runs until it is stopped.
WAITS = """
import asyncio

from hmz.flows import AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=AgentCollection, envs=Envs, params=FlowParams, name="waits")
async def waits(task, *, agents, envs, params, ctx):
    while True:
        await asyncio.sleep(0.05)
"""

#: Shows the reviewer where it stands, asks for a `Review` whole beside a diff, and writes it down.
REVIEWS = """
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from hmz.flows import (
    AgentCollection,
    Diff,
    EnvCollection,
    FlowParams,
    LocalEnv,
    Outworlder,
    Table,
    flow,
)


class Review(BaseModel):
    verdict: Literal["approve", "reject"]
    notes: str = ""


class Agents(AgentCollection):
    reviewer: Outworlder


class Envs(EnvCollection):
    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, name="reviews")
async def reviews(task, *, agents, envs, params, ctx):
    reviewer = await agents["reviewer"].spawn()
    await agents["reviewer"].show(
        [Table(columns=("step", "state"), rows=(("lint", "passed"),), title="checks")],
        session=reviewer,
    )
    review = await agents["reviewer"].run(
        f"review {task}",
        session=reviewer,
        output_schema=Review,
        context=[Diff(patch="--- a/x\\n+++ b/x\\n@@ -1 +1 @@\\n-old\\n+new\\n")],
    )
    Path("result.json").write_text(review.model_dump_json())
"""

#: A frontend in a process of its own: claims one role and answers what it is asked for it.
ANSWERS = """
import sys

from hmz.sdk import Daemons

role = sys.argv[1]
with Daemons().here().link(name=role, replay=False) as link:
    link.claim(role)
    print("claimed", flush=True)
    for said in link:
        if said["type"] == "pending":
            for one in said["pending"]:
                if one["role"] == role and one["owner"] == link.client:
                    link.answer(one["question"], f"{role} says yes")
        if said["type"] == "ended":
            break
"""


def until(what: Callable[[], object], seconds: float = PATIENCE) -> bool:
    """Whether `what` came true within `seconds`, looked at every few milliseconds."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if what():
            return True
        time.sleep(0.02)
    return bool(what())


def written(workspace: Path, name: str, source: str) -> None:
    """Lays one flow out in `workspace`, where a run started by that name finds it."""
    at = workspace / name
    at.mkdir(exist_ok=True)
    (at / "__init__.py").write_text(source)


def project(
    under: Path, monkeypatch: pytest.MonkeyPatch, name: str = "project"
) -> Path:
    """A workspace of the test's own, stood in."""
    at = under / name
    at.mkdir()
    monkeypatch.chdir(at)
    return at


def old_chat(workspace: Path, task: str, **began: Any) -> Path:
    """A chat as an earlier hmz wrote one down: an epic of the workspace's, of kind `chat`.

    Args:
      workspace: The workspace it was had in.
      task: Its first message.
      began: What its `began` says besides -- `kind="chat"` where none is given, or
        `flow="chat"` for the one a still earlier hmz wrote, which said no kind.

    Returns:
      The epic's directory, holding its record and the one session it kept.
    """
    import json

    from hmz.runtime.epic import JOURNAL, SESSIONS, under

    at = under(workspace) / f"20250101T000000.{len(task):03d}Z-0ldc4a"
    (at / SESSIONS / "claude").mkdir(parents=True)
    lines: list[dict[str, Any]] = [
        {
            "event": "began",
            "at": "2025-01-01T00:00:00.000Z",
            "task": task,
            "workspace": str(workspace.resolve()),
            "agents": [
                {
                    "agent": "assistant",
                    "backend": "claude",
                    "model": "claude-haiku-4-5",
                    "effort": "",
                    "provider": "",
                    "name": "NeiKos496",
                }
            ],
            **(began or {"kind": "chat"}),
        },
        {
            "event": "opened",
            "at": "2025-01-01T00:00:01.000Z",
            "agent": "NeiKos496",
            "backend": "claude",
            "session": "old",
            "where": f"{SESSIONS}/claude",
        },
        {"event": "ended", "at": "2025-01-01T00:00:02.000Z", "how": "stopped"},
    ]
    (at / JOURNAL).write_text("".join(json.dumps(one) + "\n" for one in lines))
    return at


def folds(seconds: float, monkeypatch: pytest.MonkeyPatch) -> None:
    """Has every host from here on fold a chat nobody reads `seconds` after its turn.

    One held in this process is told here. A host process is a fresh interpreter, which
    inherits no attribute set here: it is told through a `sitecustomize` on `PYTHONPATH`, which
    every process started from here inherits and which sets the fold in a host process alone.
    """
    import tempfile
    from pathlib import Path

    from hmz.runtime.doing import hosting

    monkeypatch.setattr(hosting, "FOLD", seconds)
    at = Path(tempfile.mkdtemp(prefix="folds-"))
    (at / "sitecustomize.py").write_text(
        "import sys\n"
        "if 'hmz.daemon.detached' in sys.orig_argv:\n"
        "    from hmz.runtime.doing import hosting\n"
        f"    hosting.FOLD = {seconds!r}\n"
    )
    monkeypatch.setenv("PYTHONPATH", str(at))


#: A chat standing in for :class:`hmz.runtime.chatting.Chat`: every message answered `you said:
#: <it>`, in a record it writes as a chat does -- carried on in the one it is given -- with a
#: native catalogue of `/compact` and `!`.
CHAT = """
from hmz.coganchor.agents.native import NativeCommand
from hmz.runtime import chatting
from hmz.runtime.epic import Drove, Epic


class StandIn(chatting.Chat):
    def __init__(self, spec, *, person):
        super().__init__(spec, person=person)
        self._at = None

    @property
    def at(self):
        return self._at

    def prefers(self, prefer):
        self._prefer = prefer

    def natives(self):
        return [
            NativeCommand("/", "compact", "compacts the conversation", "call"),
            NativeCommand("!", "", "runs a shell command", "emulate"),
        ]

    async def run(self, *, opened=None, started=None):
        carried = self.spec.resume
        backend, _, model = self.spec.agent.partition("/")
        with Epic(
            "",
            self.spec.task,
            self.spec.workspace,
            kind="chat",
            agents=[Drove("assistant", backend, model.partition(":")[0], "")],
            picked_up=carried,
            reopened=carried is not None,
        ) as epic:
            self._at = epic.path
            if started is not None:
                started(epic.path)
            said = self.spec.task
            while said:
                said = await self.person.next(f"you said: {said}")
        return chatting.ChatEnd(epic.path, "stopped")


chatting.Chat = StandIn
"""


def chats(seconds: float, monkeypatch: pytest.MonkeyPatch) -> None:
    """Has every chat from here on be :data:`CHAT`'s, folding `seconds` after its turn.

    In this process and, as :func:`folds` tells them, in every daemon and host process started
    from here: the chat runner itself is another unit's, and what is tested here is the host
    and the daemon around it.
    """
    import tempfile
    from pathlib import Path

    from hmz.runtime import chatting
    from hmz.runtime.doing import hosting

    at = Path(tempfile.mkdtemp(prefix="chats-"))
    (at / "standin_chat.py").write_text(CHAT)
    monkeypatch.setattr(chatting, "Chat", _standin(at))
    monkeypatch.setattr(hosting, "FOLD", seconds)
    (at / "sitecustomize.py").write_text(
        "import sys\n"
        "if 'hmz.daemon.detached' in sys.orig_argv:\n"
        "    from hmz.runtime.doing import hosting\n"
        f"    hosting.FOLD = {seconds!r}\n"
        "    import standin_chat\n"
    )
    monkeypatch.setenv("PYTHONPATH", str(at))


def _standin(at: Path) -> Any:
    """The stand-in chat class written at `at`, loaded without leaving it set in."""
    import importlib.util

    from hmz.runtime import chatting

    held = chatting.Chat
    found = importlib.util.spec_from_file_location(
        "standin_chat", at / "standin_chat.py"
    )
    assert found is not None
    assert found.loader is not None
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    standin = chatting.Chat
    chatting.Chat = held
    return standin


def _ends(pid: int) -> None:
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGKILL)


@contextlib.contextmanager
def hosting() -> Generator[None]:
    """Takes down every host and this machine's daemon once the block ends, however it ends."""
    try:
        yield
    finally:
        for one in daemon.daemons():
            if one.protocol and one.alive:
                one.kill(seconds=5)
        with contextlib.suppress(OSError):
            pid = where.held(where.at()).get("pid")
            if isinstance(pid, int) and pid != os.getpid() and where.alive(pid):
                _ends(pid)


class Heard:
    """Everything one link was told, in order, readable while more arrives."""

    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def __call__(self, message: dict[str, Any]) -> None:
        with self._lock:
            self.messages.append(message)

    def of(self, kind: str) -> list[dict[str, Any]]:
        """Every message of one type so far."""
        with self._lock:
            return [one for one in self.messages if one.get("type") == kind]


def replayed(link: Link) -> list[str]:
    """The type of everything `link` was told before it was told it is live."""
    told: list[str] = []
    for one in link:
        if one["type"] == "live":
            return told
        told.append(one["type"])
    raise AssertionError("let go before it was live")


@contextlib.contextmanager
def answering(*roles: str) -> Generator[list[subprocess.Popen[str]]]:
    """A frontend of its own for each of `roles`, once each holds its role; ended afterwards."""
    started: list[subprocess.Popen[str]] = []
    try:
        for role in roles:
            process = subprocess.Popen(
                [sys.executable, "-c", ANSWERS, role],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            started.append(process)
            assert process.stdout is not None
            if process.stdout.readline().strip() != "claimed":
                process.kill()
                raise AssertionError(process.communicate()[1])
        yield started
    finally:
        for process in started:
            if process.poll() is None:
                process.kill()
            process.communicate()


@contextlib.contextmanager
def standing(at: Path, said: dict[str, Any]) -> Generator[None]:
    """A daemon of another Humanize at `at`: a note saying `said`, and a socket that closes.

    In this process, and gone again once the block ends.
    """
    at.mkdir(parents=True, exist_ok=True)
    listening = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    with where.reached(at) as reaching:
        listening.bind(reaching)
    listening.listen(8)
    where.wrote(at, {"pid": os.getpid(), "started": "2026-01-01T00:00:00Z", **said})

    def closes() -> None:
        while True:
            try:
                one, _ = listening.accept()
            except OSError:
                return
            one.close()

    threading.Thread(target=closes, daemon=True, name="older-daemon").start()
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            listening.shutdown(socket.SHUT_RDWR)
        listening.close()
        for name in (where.SOCKET, where.RECORD):
            with contextlib.suppress(OSError):
                (at / name).unlink()
