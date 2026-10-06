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
    """A workspace of the test's own, stood in, with runs allowed apart from the terminal."""
    at = under / name
    at.mkdir()
    monkeypatch.chdir(at)
    monkeypatch.delenv("HUMANIZE_DAEMON", raising=False)
    return at


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
    """A daemon of another humanize at `at`: a note saying `said`, and a socket that closes.

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
