"""The pictures of `docs/tutorials/work-on-a-server.md`: work on a server, or in a container.

A server is imported from the person's ssh config, checked, and a chat started on it; its
files, changes and terminal are opened beside the chat; a docker daemon is saved as a runtime
too; and a flow with a role for another machine is started on the server, from the app's form
and from the command line. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_tutorials_work_on_a_server.py`.

No machine but this one is reached. The server `gpu-box` is the stand-in `ssh` of the anchor
tests (`tests/integration/doubles_anchor.py`), which runs what it is told here, under a home
of its own: Humanize ships its `coganchor` there and works through it as over a real ssh. The
docker daemon is that module's stand-in `docker`, which answers `docker info`. A stand-in
container is this Mac, which is not the Linux a container is, so no picture is of work inside
one: the page says that part in words.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import uuid
from typing import TYPE_CHECKING

import pytest
from playwright.sync_api import expect

from hmz.coganchor.transport import Road, Target
from tests.integration.doubles_anchor import fakes
from tests.integration.doubles_tui import shows
from tests.system.docs import shots
from tests.system.docs.conftest import AGENT, MODEL
from tests.system.web.doubles_browser import go

if TYPE_CHECKING:
    from pathlib import Path

    from playwright.sync_api import Locator, Page

    from tests.integration.doubles_anchor import Fakes
    from tests.integration.doubles_web import Session
    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "tutorials-work-on-a-server"

#: The server, as the person's ssh config names it, and the project's directory on it.
_HOST = "gpu-box"
_THERE = "~/shop"
_ENV = f"ssh@{_HOST}/{_THERE}"

#: The docker daemon's runtime, and the image its containers are started from.
_DOCKER = "sandbox"
_IMAGE = "shop-dev:latest"

_TASK = "Add a discount code to checkout"

#: `ssh -G`, which reads the person's own config and reaches nothing, answered for the
#: made-up hosts: the real `ssh` would read the config of whoever runs the suite. Anything
#: else is the anchor tests' stand-in, which runs it here.
_SSH = """#!{python}
import os, sys
HOSTS = {{"gpu-box": "10.0.0.12", "build-1": "10.0.0.20"}}
if "-G" in sys.argv[1:]:
    print("hostname " + HOSTS.get(sys.argv[-1], sys.argv[-1]))
    print("user alex")
    print("port 22")
    sys.exit(0)
os.execv({far!r}, [{far!r}, *sys.argv[1:]])
"""

_CONFIG = """Host gpu-box
  HostName 10.0.0.12
  User alex

Host build-1
  HostName 10.0.0.20
  User alex
"""

#: The prompt of a shell on the server: the one it would have, not this machine's.
_PROMPT = "PROMPT='alex@gpu-box:~/shop$ '\nPS1='alex@gpu-box:~/shop$ '\n"

_CHECKOUT = '''"""Paying for a cart."""

from shop.cart import total

CODES = {"WELCOME10": 10}


def charge(items: dict[str, int], code: str = "") -> int:
    """What is charged for a cart, in cents, less what a code takes off."""
    owed = total(items)
    return owed - owed * CODES.get(code, 0) // 100
'''

#: What the agent does when told the task: reads, edits, tests, and says so.
_WORK = {
    "text": (
        "Checkout takes a discount code now: charge() looks the code up and takes its"
        " discount off the total. WELCOME10 is 10% off. The tests pass."
    ),
    "tools": [
        {
            "name": "Read",
            "input": {"file_path": "shop/checkout.py"},
            "result": "def charge(items): ...",
            "takes": 0.2,
        },
        {
            "name": "Edit",
            "input": {"file_path": "shop/checkout.py"},
            "result": "edited",
            "takes": 0.2,
        },
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "3 passed in 0.14s",
            "takes": 0.3,
        },
    ],
    "writes": {"shop/checkout.py": _CHECKOUT},
}

#: The flow the page writes: one agent, working in an environment its person chooses.
_ON_BOX = '''"""One agent does the task in an environment you choose."""

from hmz.flows import (
    Agent,
    AgentCollection,
    Env,
    EnvCollection,
    FlowContext,
    FlowParams,
    LocalEnv,
    ShellEnvMixin,
    flow,
)


class Box(Env, ShellEnvMixin):
    """Another machine, and a shell on it."""


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    workspace: LocalEnv  # the folder the epic starts in
    box: Box  # wherever you say


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def on_box(
    task: str, *, agents: Agents, envs: Envs, params: FlowParams, ctx: FlowContext
) -> None:
    """One agent does the task in an environment you choose."""
    builder = agents["builder"]
    session = await builder.spawn()
    await builder.run(task, session=session, env=envs["box"])
'''


def _git(at: Path, *argv: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Alex Kim", "-c", "user.email=alex@example.com", *argv],
        cwd=at,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def far(world: World, monkeypatch: pytest.MonkeyPatch) -> Fakes:
    """The server and the docker daemon: stand-ins on `PATH`, and the server's own home.

    The home holds the project as the person's machine has it, a git repository of its own,
    and nothing of Humanize's: what is there after a scene is what Humanize brought.
    """
    base = world.home.parent
    made = fakes(base / "far", monkeypatch)
    home = base / _HOST / "alex"
    shutil.copytree(
        world.workspace,
        home / "shop",
        ignore=shutil.ignore_patterns(".git", ".hmz", "__pycache__"),
    )
    _git(home / "shop", "init", "-q", "-b", "main")
    _git(home / "shop", "add", "-A")
    _git(home / "shop", "commit", "-q", "-m", "Start the shop")
    for name in (".zshrc", ".bashrc", ".bash_profile", ".profile"):
        (home / name).write_text(_PROMPT)
    monkeypatch.setenv("FAKE_HOME", str(home))
    real = made.bin / "ssh-far"
    (made.bin / "ssh").rename(real)
    (made.bin / "ssh").write_text(_SSH.format(python=sys.executable, far=str(real)))
    (made.bin / "ssh").chmod(0o755)
    made.answer(
        "info", json.dumps({"ServerVersion": "27.3.1", "NCPU": 8, "MemTotal": 16 << 30})
    )
    (world.home / ".ssh").mkdir()
    (world.home / ".ssh" / "config").write_text(_CONFIG)
    # A machine is given `coganchor` once a process: this one is a new machine each scene.
    Road.to(Target.parse(f"ssh://{_HOST}")).forget()
    return made


def _saved(world: World) -> None:
    """Saves both runtimes as the page's steps leave them."""
    world.call("runtimes.import", names=[_HOST])
    world.call("runtimes.set", backend="docker", name=_DOCKER, fields={"image": _IMAGE})


def _heard(session: Session, sub: str, kind: str) -> int:
    with session.heard:
        return sum(
            1
            for method, said in session.told
            if method == "epic.event"
            and said["sub"] == sub
            and said["message"].get("type") == kind
        )


def _chat(world: World, env: str, message: str) -> str:
    """Holds a chat whose agent works in an environment, and leaves its host running."""
    here = str(world.workspace)
    with world.session() as session:
        started = session.call(
            "chat.start",
            workspace=here,
            slot="chat:",
            agent=AGENT,
            task=message,
            env=env,
            idem=uuid.uuid4().hex,
        )
        sub = session.call("epic.attach", workspace=here, slot=started["slot"])["sub"]
        world._until(session, lambda: _heard(session, sub, "asked") >= 1)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
        session.call("epic.detach", sub=sub)
        return str(started["chat"])


def _top(page: Page, selector: str) -> None:
    """Scrolls the settings to one of its panels, inside the dialog."""
    page.locator(selector).evaluate("(one) => one.scrollIntoView({ block: 'start' })")
    page.wait_for_timeout(300)


def _box(page: Page) -> Locator:
    """The box of a new chat, once the agent it would start is on offer under it."""
    expect(page.get_by_role("button", name=re.compile("Nous: .*Haiku"))).to_be_visible()
    return page.get_by_role("textbox", name="First message")


def test_a_server_is_imported_from_the_ssh_config_and_checked(
    world: World, far: Fakes
) -> None:
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        _box(page)
        go(page, "/settings/runtimes")
        expect(page.get_by_text("No other runtime yet.")).to_be_visible()
        reel = shots.Reel(f"{_PAGE}-import", window="desktop")
        reel.web(page, hold=1.6)
        _top(page, "[data-hmz=import-runtimes]")
        read = page.get_by_role("button", name="Read SSH config")
        reel.web(page, hold=1.2, pointer=read, click=True)
        read.click()
        tick = page.locator("label.check", has_text=_HOST).locator("input")
        expect(tick).to_be_visible()
        reel.web(page, hold=1.2, pointer=tick, click=True)
        tick.check()
        bring = page.get_by_role("button", name="Import", exact=True)
        reel.web(page, hold=1.0, pointer=bring, click=True)
        bring.click()
        row = page.locator("[data-hmz=runtime]", has_text=_HOST)
        expect(row).to_be_visible()
        _top(page, "[data-hmz=runtimes]")
        check = row.get_by_role("button", name="Check")
        reel.web(page, hold=1.4, pointer=check, click=True)
        check.click()
        expect(row).to_contain_text("cpu")
        reel.web(page, hold=4, poster=True)
        reel.save()


def test_a_chat_is_started_on_the_server(world: World, far: Fakes) -> None:
    world.call("runtimes.import", names=[_HOST])
    world.says({"discount": {**_WORK, "after": 1.5}})
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        box = _box(page)
        reel = shots.Reel(f"{_PAGE}-chat", window="desktop")
        chip = page.locator("[data-hmz=environment]")
        reel.web(page, hold=1.3, pointer=chip, click=True)
        chip.click()
        there = page.get_by_role("menuitemradio", name=_HOST)
        expect(there).to_be_visible()
        reel.web(page, hold=1.3, pointer=there, click=True)
        there.click()
        directory = page.locator("[data-hmz=env-dir]")
        expect(directory).to_be_visible()
        reel.web(page, hold=0.8)
        reel.type(page, directory, _THERE, per=2)
        use = page.locator("[data-hmz=env-dir-pick]")
        reel.web(page, hold=0.9, pointer=use, click=True)
        use.click()
        expect(chip).to_contain_text(_HOST)
        reel.web(page, hold=1.2, pointer=box, click=True)
        reel.type(page, box, _TASK, per=11)
        box.press("Enter")
        page.wait_for_url(re.compile(r".*#/chats/[^/?]+$"))
        expect(page.get_by_role("log")).to_contain_text("WELCOME10")
        expect(page.get_by_role("button", name="Send")).to_be_visible()
        reel.web(page, hold=4, poster=True)
        reel.save()


def test_its_files_changes_and_terminal_are_the_servers(
    world: World, far: Fakes
) -> None:
    world.call("runtimes.import", names=[_HOST])
    world.says({"discount": _WORK})
    chat = _chat(world, _ENV, _TASK)
    with world.page(desktop=True) as page:
        go(page, f"/chats/{chat}")
        expect(page.get_by_role("log")).to_contain_text("WELCOME10")

        page.get_by_role("button", name="Files").click()
        page.get_by_role("treeitem", name="shop", exact=True).click()
        page.get_by_role("treeitem", name="checkout.py").click()
        expect(page.get_by_text("CODES").first).to_be_visible()
        page.wait_for_timeout(600)
        shots.web(page, f"{_PAGE}-files", window="desktop")

        page.get_by_role("button", name="Changes").click()
        changed = page.locator("[data-hmz=change][data-path='shop/checkout.py']")
        changed.click()
        expect(page.get_by_text("WELCOME10").last).to_be_visible()
        page.wait_for_timeout(1000)
        shots.web(page, f"{_PAGE}-changes", window="desktop")

        # A terminal drawn by WebGL is not printed, so no picture would hold it: with none
        # to start, the page draws it itself, as it does in a browser that has no WebGL.
        page.evaluate(
            """() => {
                const was = HTMLCanvasElement.prototype.getContext
                HTMLCanvasElement.prototype.getContext = function (kind, ...more) {
                    return /webgl/.test(kind) ? null : was.call(this, kind, ...more)
                }
            }"""
        )
        page.get_by_role("button", name="Terminal").click()
        panel = page.locator("[data-hmz=terminal]")
        expect(panel.locator("[data-hmz=term-tab]")).to_have_count(1)
        page.wait_for_timeout(1500)
        page.locator("[data-hmz=term-host]:visible").click()
        page.keyboard.type("git status --short", delay=20)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1500)
        # Its cursor blinks while it is typed into: left, it stands still.
        page.evaluate("() => document.activeElement.blur()")
        page.wait_for_timeout(800)
        shots.web(page, f"{_PAGE}-terminal", window="desktop")


def test_a_docker_daemon_is_saved_as_a_runtime(world: World, far: Fakes) -> None:
    world.call("runtimes.import", names=[_HOST])
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        _box(page)
        go(page, "/settings/runtimes")
        expect(page.locator("[data-hmz=runtime]")).to_have_count(1)
        page.locator("#runtime-backend").select_option("docker")
        page.locator("#runtime-name").fill(_DOCKER)
        page.locator("#runtime-image").fill(_IMAGE)
        _top(page, "[data-hmz=write-runtime]")
        shots.web(page, f"{_PAGE}-docker", window="desktop")
        page.get_by_role("button", name="Add", exact=True).last.click()
        rows = page.locator("[data-hmz=runtime]")
        expect(rows).to_have_count(2)
        for at in range(2):
            rows.nth(at).get_by_role("button", name="Check").click()
            expect(rows.nth(at)).to_contain_text("cpu")
        shots.web(page, f"{_PAGE}-runtimes", clip="[data-hmz=runtimes]")


def test_a_flow_with_a_role_for_another_machine_is_started_there(
    world: World, far: Fakes
) -> None:
    _saved(world)
    flow = world.workspace / ".hmz" / "flows" / "on_box"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_ON_BOX)
    world.says({"discount": {**_WORK, "after": 0.8}})
    with world.page(desktop=True) as page:
        go(page, "/new?flow=%40local%2Fon_box")
        row = page.locator("[data-hmz=env][data-role=box]")
        expect(row).to_be_visible()
        row.locator("[data-hmz=pick-backend]").select_option("ssh")
        expect(row.locator("[data-hmz=pick-runtime]")).to_have_value(_HOST)
        row.locator("[data-hmz=pick-dir-there]").fill(_THERE)
        expect(page.get_by_text("Asking…")).to_have_count(0)
        shots.web(page, f"{_PAGE}-epic", window="desktop")

    reel = shots.Reel(f"{_PAGE}-exec")
    reel.cli(
        [
            "hmz",
            "exec",
            "-f",
            "@local/on_box",
            "-a",
            f"builder={AGENT}",
            "-e",
            f"box={_ENV}",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        rows=11,
    )
    reel.save()


async def test_the_runtimes_in_the_terminal_interface(world: World, far: Fakes) -> None:
    _saved(world)
    async with world.tui((100, 26)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*"/settings runtimes", "enter")
        await shows(pilot, _HOST, _DOCKER)
        await pilot.pause(0.5)
        shots.tui(app, f"{_PAGE}-tui")
