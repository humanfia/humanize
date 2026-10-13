"""`hmz web`: an epic ending, and each turn of a chat done, said as notices."""

from __future__ import annotations

import contextlib
import http.client
import json
import time
from typing import TYPE_CHECKING, Any

import pytest

from tests.integration.doubles_core import AGENT, install, write_flow
from tests.integration.doubles_web import PATIENCE, Browser, served

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from pathlib import Path

#: A flow of one turn of the stand-in, which ends done.
_ONCE = '''
from hmz.flows import (
    Agent, AgentCollection, EnvCollection, FlowContext, FlowParams, LocalEnv, flow,
)


class Agents(AgentCollection):
    """The one."""

    solo: Agent


class Envs(EnvCollection):
    """Where it works."""

    workspace: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def once(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> str:
    """One turn, and done."""
    one = agents["solo"]
    return await one.run(task, session=await one.spawn(), env=envs["workspace"])
'''


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The stand-in `claude` alone on PATH, and a project to serve the runs of."""
    return install(tmp_path, monkeypatch)


@contextlib.contextmanager
def _follows(
    browser: Browser, last: str = ""
) -> Generator[Callable[[], tuple[str, dict[str, Any]]]]:
    """Listens to the notices' stream as a page does: each notice, by its id."""
    connection = http.client.HTTPConnection(
        "127.0.0.1", browser.site.port, timeout=PATIENCE
    )
    headers = {"Host": f"127.0.0.1:{browser.site.port}", "Cookie": browser.cookie}
    if last:
        headers["Last-Event-ID"] = last
    connection.request("GET", "/api/notices/stream", headers=headers)
    stream = connection.getresponse()

    def next_notice() -> tuple[str, dict[str, Any]]:
        ident = event = ""
        while True:
            line = stream.readline().decode().rstrip("\n")
            if line.startswith("id: "):
                ident = line[len("id: ") :]
            elif line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: ") and event == "notice":
                return ident, json.loads(line[len("data: ") :])

    try:
        yield next_notice
    finally:
        connection.close()


def _until(
    next_notice: Callable[[], tuple[str, dict[str, Any]]], kind: str
) -> tuple[str, dict[str, Any]]:
    ending = time.monotonic() + PATIENCE
    while time.monotonic() < ending:
        ident, notice = next_notice()
        if notice["kind"] == kind:
            return ident, notice
    raise AssertionError(f"no {kind} notice came")


def test_each_chat_turn_done_and_an_epic_ending_are_notices(project: Path) -> None:
    write_flow(project / ".hmz" / "flows", "once", _ONCE)
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        assert browser.get("/api/notices").json() == {"notices": [], "last": 0}

        with _follows(browser) as heard:
            chat = {
                "flow": "chat",
                "task": "hello there",
                "agents": {"assistant": AGENT},
            }
            assert browser.post("/api/held/start", chat).status == 200
            _, turned = _until(heard, "done")
            assert (turned["workspace"], turned["flow"]) == (str(project), "chat")
            assert (turned["task"], turned["role"]) == ("hello there", "human")
            assert turned["text"] == "did: hello there"
            assert turned["epic"]

            # Each turn of it done is a notice of its own.
            assert browser.post("/api/held/say", {"text": "and again"}).status == 200
            _, again = _until(heard, "done")
            assert (again["epic"], again["text"]) == (turned["epic"], "did: and again")

            # And the chat left is none.
            stopped_at = str(browser.get("/api/notices").json()["last"])
            assert browser.post("/api/held/stop").status == 200
            started = browser.post(
                "/api/held/start",
                {
                    "flow": "@local/once",
                    "task": "do it",
                    "agents": {"solo": AGENT},
                    "budget": {"cost": 5},
                },
            )
            assert started.status == 200, started.json()
            _, done = _until(heard, "done")
            assert (done["flow"], done["task"], done["text"]) == (
                "@local/once",
                "do it",
                "",
            )
            assert done["epic"] != turned["epic"]

        kept = browser.get("/api/notices").json()
        assert [(one["kind"], one["flow"]) for one in kept["notices"]] == [
            ("done", "chat"),
            ("done", "chat"),
            ("done", "@local/once"),
        ]
        assert kept["last"] == kept["notices"][-1]["id"]
        after = browser.get(f"/api/notices?after={stopped_at}").json()["notices"]
        assert [one["flow"] for one in after] == ["@local/once"]
        assert browser.get("/api/notices?after=soon").status == 400
        # Carried on from the last one heard, a stream hears what came after it.
        with _follows(browser, stopped_at) as heard:
            assert heard()[1]["flow"] == "@local/once"
