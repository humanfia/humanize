"""The pictures of `docs/user/runtimes.md`: saved runtimes, in the app, the terminal and a line.

Two servers and a docker daemon are saved and checked; one server is edited on its form, with
the server it falls back to and where the agent's CLI runs; hosts are read from the person's
ssh config and brought in; a directory of the server is browsed for; the runtimes are opened in
the terminal interface, where the docker daemon is asked what it has; and a flow whose role
names a server that does not answer lands on the
one it falls back to. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_user_runtimes.py`.

No machine but this one is reached. The servers are the stand-in `ssh` of the anchor tests
(`tests/integration/doubles_anchor.py`), which runs what it is told here, under a home of its
own, and the docker daemon is that module's stand-in `docker`, which answers `docker info`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, Any

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
    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-runtimes"

#: The server the work is put on, the one it falls back to, and the project's directory there.
_HOST = "gpu-box"
_SPARE = "build-1"
_THERE = "~/shop"

#: The docker daemon's runtime, and the image its containers are started from.
_DOCKER = "sandbox"
_IMAGE = "shop-dev:latest"

_TASK = "Add a discount code to checkout"

#: `ssh -G`, which reads the person's own config and reaches nothing, answered for the
#: made-up hosts: the real `ssh` would read the config of whoever runs the suite. A host named
#: in `FAKE_DOWN` does not answer, as one switched off does not. Anything else is the anchor
#: tests' stand-in, which runs it here.
_SSH = """#!{python}
import os, sys
HOSTS = {{"gpu-box": "10.0.0.12", "build-1": "10.0.0.20", "staging": "10.0.0.31"}}
if "-G" in sys.argv[1:]:
    print("hostname " + HOSTS.get(sys.argv[-1], sys.argv[-1]))
    print("user alex")
    print("port 22")
    sys.exit(0)
down = os.environ.get("FAKE_DOWN", "")
if down and down in sys.argv[1:]:
    sys.stderr.write(
        "ssh: connect to host " + HOSTS[down] + " port 22: Operation timed out\\n"
    )
    sys.exit(255)
os.execv({far!r}, [{far!r}, *sys.argv[1:]])
"""

_CONFIG = """Host gpu-box
  HostName 10.0.0.12
  User alex

Host build-1
  HostName 10.0.0.20
  User alex

Host staging
  HostName 10.0.0.31
  User alex
"""

#: What the agent does when told the task, and says.
_WORK = {
    "text": (
        "Checkout takes a discount code now: WELCOME10 is 10% off. The tests pass."
    ),
    "tools": [
        {
            "name": "Bash",
            "input": {"command": "pytest -q"},
            "result": "3 passed in 0.14s",
            "takes": 0.3,
        },
    ],
}

#: A flow of one agent, working in an environment its person chooses.
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
    workspace: LocalEnv
    box: Box


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
    """The servers and the docker daemon: stand-ins on `PATH`, and the servers' own home."""
    base = world.home.parent
    made = fakes(base / "far", monkeypatch)
    home = base / "home" / "alex"
    shutil.copytree(
        world.workspace,
        home / "shop",
        ignore=shutil.ignore_patterns(".git", ".hmz", "__pycache__"),
    )
    _git(home / "shop", "init", "-q", "-b", "main")
    _git(home / "shop", "add", "-A")
    _git(home / "shop", "commit", "-q", "-m", "Start the shop")
    for name in ("datasets", "notebooks", "shop-staging"):
        (home / name).mkdir()
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
    # A machine is given `coganchor` once a process: these are new machines each scene.
    for host in (_HOST, _SPARE):
        Road.to(Target.parse(f"ssh://{host}")).forget()
    return made


def _saved(world: World, *, workdir: str = _THERE) -> None:
    """Saves the two servers, the first falling back to the second, and the docker daemon."""
    listed = world.call("runtimes.import", names=[_HOST, _SPARE])
    for one in listed["runtimes"]:
        fields: dict[str, Any] = {
            key: value
            for key, value in one.items()
            if key not in ("backend", "name", "made")
        }
        fields["workdir"] = workdir
        if one["name"] == _HOST:
            fields["fallback"] = [f"ssh:{_SPARE}"]
        world.call(
            "runtimes.set", backend="ssh", name=one["name"], fields=fields, replace=True
        )
    world.call("runtimes.set", backend="docker", name=_DOCKER, fields={"image": _IMAGE})


def _top(page: Page, selector: str) -> None:
    """Scrolls the settings to one of its panels, inside the dialog."""
    page.locator(selector).evaluate("(one) => one.scrollIntoView({ block: 'start' })")
    page.wait_for_timeout(400)


def _box(page: Page) -> Locator:
    """The box of a new chat, once the agent it would start is on offer under it."""
    expect(page.get_by_role("button", name=re.compile("Nous: .*Haiku"))).to_be_visible()
    return page.get_by_role("textbox", name="First message")


def _settings(page: Page) -> None:
    go(page, "/new/chat")
    _box(page)
    go(page, "/settings/runtimes")


def test_the_runtimes_are_listed_and_checked(world: World, far: Fakes) -> None:
    _saved(world)
    with world.page(desktop=True) as page:
        _settings(page)
        rows = page.locator("[data-hmz=runtime]")
        expect(rows).to_have_count(3)
        reel = shots.Reel(f"{_PAGE}-check", clip="[data-hmz=runtimes]")
        for at in range(3):
            check = rows.nth(at).get_by_role("button", name="Check")
            reel.web(page, hold=1.0 if at else 1.6, pointer=check, click=True)
            check.click()
            expect(rows.nth(at)).to_contain_text("cpu")
        reel.web(page, hold=4, poster=True)
        reel.save()
        # The whole window is what the page opens on: a still near the most one may be.
        shots.web(page, f"{_PAGE}-list", window="desktop", most=shots.REEL)


def test_a_runtime_is_edited_on_its_form(world: World, far: Fakes) -> None:
    _saved(world)
    with world.page(desktop=True) as page:
        _settings(page)
        row = page.locator("[data-hmz=runtime]", has_text=_HOST)
        row.get_by_role("button", name="Edit").click()
        expect(page.get_by_role("heading", name=f"Edit {_HOST}")).to_be_visible()
        page.wait_for_timeout(800)
        # The end of the form: where it works, what it falls back to, where the CLI runs.
        _top(page, "label[for=runtime-options]")
        shots.web(page, f"{_PAGE}-form", window="desktop")


def test_a_docker_runtime_is_written(world: World, far: Fakes) -> None:
    _saved(world)
    with world.page(desktop=True) as page:
        _settings(page)
        expect(page.locator("[data-hmz=runtime]")).to_have_count(3)
        page.locator("#runtime-backend").select_option("docker")
        page.locator("#runtime-name").fill("shared-box")
        page.locator("#runtime-container").fill("shop-dev")
        _top(page, "[data-hmz=write-runtime]")
        shots.web(page, f"{_PAGE}-docker", window="desktop")


def test_hosts_are_brought_in_from_the_ssh_config(world: World, far: Fakes) -> None:
    world.call("runtimes.import", names=[_HOST])
    with world.page(desktop=True) as page:
        _settings(page)
        expect(page.locator("[data-hmz=runtime]")).to_have_count(1)
        _top(page, "[data-hmz=import-runtimes]")
        reel = shots.Reel(f"{_PAGE}-import", window="desktop")
        read = page.get_by_role("button", name="Read SSH config")
        reel.web(page, hold=1.4, pointer=read, click=True)
        read.click()
        tick = page.locator("label.check", has_text=_SPARE).locator("input")
        expect(tick).to_be_visible()
        page.locator("[data-hmz=import-runtimes]").evaluate(
            "(one) => one.scrollIntoView({ block: 'end' })"
        )
        page.wait_for_timeout(400)
        reel.web(page, hold=1.3, pointer=tick, click=True)
        tick.check()
        bring = page.get_by_role("button", name="Import", exact=True)
        reel.web(page, hold=1.2, pointer=bring, click=True)
        bring.click()
        expect(page.locator("[data-hmz=runtime]")).to_have_count(2)
        page.get_by_role("button", name="Read SSH config").click()
        expect(page.locator("label.check", has_text=_SPARE)).to_contain_text("saved")
        _top(page, "[data-hmz=runtimes]")
        reel.web(page, hold=3.5, poster=True)
        reel.save()


def test_a_directory_of_the_server_is_browsed_for(world: World, far: Fakes) -> None:
    world.call("runtimes.import", names=[_HOST])
    with world.page(desktop=True) as page:
        go(page, "/new/chat")
        _box(page)
        chip = page.locator("[data-hmz=environment]")
        chip.click()
        there = page.get_by_role("menuitemradio", name=_HOST)
        expect(there).to_be_visible()
        there.click()
        form = page.locator("[data-hmz=env-dir-form]")
        expect(form).to_be_visible()
        form.locator("[data-hmz=path-browse]").click()
        panel = form.locator("[data-hmz=path-panel]")
        expect(panel.locator("[data-name=shop]")).to_be_visible()
        page.wait_for_timeout(500)
        shots.web(page, f"{_PAGE}-browse", window="desktop")


async def test_the_runtimes_in_the_terminal_interface(world: World, far: Fakes) -> None:
    _saved(world)
    async with world.tui((100, 26)) as (app, pilot):
        await shows(pilot, MODEL)
        reel = shots.Reel(f"{_PAGE}-tui")
        await pilot.press(*"/settings runtimes", "enter")
        await shows(pilot, _HOST, _DOCKER)
        await pilot.pause(0.5)
        reel.tui(app, hold=2.2, keys="/settings runtimes")
        await pilot.press("down")
        await pilot.pause(0.3)
        reel.tui(app, hold=0.9, keys="down", cut=True)
        await pilot.press("enter")
        await shows(pilot, "check")
        await pilot.pause(0.5)
        reel.tui(app, hold=3.5, keys="enter", poster=True)
        reel.save()


def test_a_role_lands_on_the_runtime_fallen_back_to(
    world: World, far: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    _saved(world)
    flow = world.workspace / ".hmz" / "flows" / "on_box"
    flow.mkdir(parents=True)
    (flow / "__init__.py").write_text(_ON_BOX)
    world.says({"discount": {**_WORK, "after": 0.8}})
    monkeypatch.setenv("FAKE_DOWN", _HOST)
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
            f"box=ssh@{_HOST}",
            "-p",
            "budget.output_tokens=20000",
            _TASK,
        ],
        rows=14,
    )
    reel.save()


async def test_a_docker_runtime_is_detected_in_the_terminal_interface(
    world: World, far: Fakes
) -> None:
    _saved(world)
    async with world.tui((100, 30)) as (app, pilot):
        await shows(pilot, MODEL)
        await pilot.press(*"/settings runtimes", "enter")
        await shows(pilot, _HOST, _DOCKER)
        await pilot.press("down", "down", "enter")
        await shows(pilot, "check")
        await pilot.press("enter")
        await shows(pilot, f"Edit docker/{_DOCKER}", "Detect")
        await pilot.pause(0.5)
        reel = shots.Reel(f"{_PAGE}-detect")
        reel.tui(app, hold=1.8)
        await pilot.press("tab")
        await shows(pilot, "detect host resources and fill them in")
        await pilot.pause(0.3)
        reel.tui(app, hold=1.6, keys="tab", cut=True)
        await pilot.press("enter")
        await shows(pilot, "auto-filled")
        await pilot.pause(0.5)
        reel.tui(app, hold=4, keys="enter", poster=True)
        reel.save()
