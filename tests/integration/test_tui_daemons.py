"""Other machines' daemons from the terminal: the daemons page, `/epics @<name>`, and `m`.

The other machine is this one under a home of its own: reached over `stdio:ssh` by the
stand-in `ssh` of `doubles_ssh`, whose `hmz daemon connect --stdio` starts that home's daemon
as the real one would start the one installed there; or over `tcp`, `hmz daemon serve` under a
home of its own, paired from the code `hmz daemon pair` makes.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import threading
from functools import partial
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

import pytest
import yaml
from textual.widgets import OptionList

from hmz import home
from hmz.coganchor.machines import sshconfig
from hmz.daemon import link, where
from hmz.runtime import Hmz
from hmz.runtime.epic import Epic
from hmz.tui import Humanize, pick
from hmz.tui.pick import (
    Acts,
    Batching,
    Daemoning,
    Devices,
    Epics,
    Exporting,
    RemoteEpics,
    Revokes,
    Starting,
)
from hmz.tui.settings import Adjusts
from tests.integration.doubles_daemon import ASKS
from tests.integration.doubles_ssh import Host, faked
from tests.integration.doubles_tui import (
    OWN,
    PATIENCE,
    RUNS,
    SIZE,
    leaves,
    on,
    onto,
    opened,
    own_flow,
    picks,
    screen,
    shows,
    stand_in,
    typed,
    until,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from textual.pilot import Pilot

#: Every epic here is held by a daemon of the test's own, in this process.
pytestmark = [
    pytest.mark.usefixtures("daemon"),
    pytest.mark.filterwarnings("ignore:.*use of fork.*:DeprecationWarning"),
]


@pytest.fixture
def host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None
) -> Iterator[Host]:
    """The stand-in `claude` here, and another machine `ssh` reaches, holding one epic."""
    del asking
    stand_in(tmp_path, monkeypatch)
    far = tmp_path / "far"
    far.mkdir()
    found = faked(far, monkeypatch)
    here = os.environ["HUMANIZE_HOME"]
    # Written there as a run there writes it: under that machine's own home.
    monkeypatch.setenv("HUMANIZE_HOME", str(found.humanize))
    project = found.home / "project"
    project.mkdir()
    with Epic("ralph", "tidy the far project", project):
        pass
    monkeypatch.setenv("HUMANIZE_HOME", here)
    yield found
    # The daemon `hmz daemon connect --stdio` started there, which outlives its client.
    pid = where.held(found.tmp / f"humanize-{os.getuid()}").get("pid")
    if isinstance(pid, int):
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)


async def _menu(pilot: Pilot[None], row: str = "") -> Acts:
    """Walks on to one row of the sheet on top, or stays, and opens its menu with `m`."""
    if row:
        await onto(pilot, row)
    await pilot.press("m")
    return await on(pilot, Acts)


async def _adds(pilot: Pilot[None], name: str) -> None:
    """Opens the form that adds a daemon, and names it."""
    await pilot.click("#act-add")
    await on(pilot, Daemoning)
    await pilot.press(*name, "enter")


async def test_a_daemon_is_added_and_its_epics_listed_and_exported(
    host: Host, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # And one started there in no folder, in a directory that machine made for it alone.
    made = host.tmp.resolve() / f"humanize-{os.getuid()}" / "nofolder" / "tmpab12cd34"
    made.mkdir(parents=True)
    with monkeypatch.context() as there:
        there.setenv("HUMANIZE_HOME", str(host.humanize))
        with Epic("ralph", "nowhere at all", made):
            pass
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings daemons")
        await on(pilot, Adjusts)
        await shows(pilot, "Local", "no other daemons yet")
        pilot.app.save_screenshot("daemons-empty.svg", str(tmp_path))

        await _adds(pilot, "box")
        await picks(pilot, "mode", "Custom")
        await onto(pilot, "host")
        await pilot.press(*"box.example", "enter")
        await pilot.click("#act-done")
        await on(pilot, Adjusts)
        await shows(pilot, "box saved", "stdio:ssh://box.example · idle")

        # Its menu, on `m`: reaching it now.
        await _menu(pilot, "box")
        await onto(pilot, "connect")
        await pilot.press("enter")
        await on(pilot, Adjusts)
        await shows(pilot, f"up, hmz {version('hmz')}")
        pilot.app.save_screenshot("daemons-up.svg", str(tmp_path))
        await leaves(pilot)

        # Its epics, by `@<name>`.
        await typed(pilot, "/epics @box")
        await on(pilot, RemoteEpics)
        await shows(pilot, "Epics on box", "tidy the far project", "ralph")
        # Said to be of no folder, never by the directory made for it (Section 17.3.1.1).
        said = await shows(pilot, "no folder · nowhere at all")
        assert "tmpab12cd34" not in said
        pilot.app.save_screenshot("epics-box.svg", str(tmp_path))

        # And one brought here from its menu.
        await _menu(pilot)
        await shows(pilot, "export", "upload", "copy name")
        pilot.app.save_screenshot("epic-menu.svg", str(tmp_path))
        await onto(pilot, "export")
        await pilot.press("enter")
        await on(pilot, Exporting)
        out = tmp_path / "out"
        await pilot.press(*f"{out}/", "enter")
        await pilot.click("#act-done")
        await on(pilot, RemoteEpics)
        await shows(pilot, ".hmzepic")
        (bundle,) = out.iterdir()
        with tarfile.open(bundle) as archive:
            assert any(name.endswith("epic.jsonl") for name in archive.getnames())

        # Back to this machine's, from the list's own button.
        await pilot.click("#act-daemon")
        await onto(pilot, "local")
        await pilot.press("enter")
        await on(pilot, Epics)
        await leaves(pilot)

    assert [one["name"] for one in Hmz().daemons.all()] == ["box"]


async def test_epics_of_no_such_daemon_are_refused(host: Host) -> None:
    del host
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/epics @nowhere")
        await shows(pilot, "/epics takes a daemon as @<name>: choose @local")


async def test_settings_are_batch_applied_to_another_daemon(host: Host) -> None:
    Hmz().daemons.write("box", {"routes": ["stdio:ssh://box.example"]})
    Hmz().settings.detailing(on=True)
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings daemons")
        await on(pilot, Adjusts)
        await shows(pilot, "box")

        await pilot.click("#act-batch")
        await on(pilot, Batching)
        await shows(pilot, "general", "nous", "runtimes", "backup", "box")
        await picks(pilot, "daemon:box", "on")
        await pilot.click("#act-done")
        await on(pilot, Adjusts)
        await shows(pilot, "box: applied")

    here = os.environ["HUMANIZE_HOME"]
    os.environ["HUMANIZE_HOME"] = str(host.humanize)
    try:
        assert Hmz().settings.details
    finally:
        os.environ["HUMANIZE_HOME"] = here


async def test_an_epic_is_started_on_another_daemon_and_steered_here(
    host: Host, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    Hmz().daemons.write("box", {"routes": ["stdio:ssh://box.example"]})
    project = host.home / "project"
    own_flow(project, ASKS)
    # Set up there as that directory last ran it: under that machine's own home.
    here = os.environ["HUMANIZE_HOME"]
    monkeypatch.setenv("HUMANIZE_HOME", str(host.humanize))
    Hmz(project).settings.remember(OWN, {}, budget={"cost": 1.0})
    monkeypatch.setenv("HUMANIZE_HOME", here)
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/epics @box")
        await on(pilot, RemoteEpics)
        await shows(pilot, "tidy the far project")

        await pilot.press("n")
        await on(pilot, Starting)
        await pilot.press(*str(project), "enter")
        await onto(pilot, "flow")
        await pilot.press(*OWN, "enter")
        await pilot.press(*"the far plan", "enter")
        await pilot.click("#act-done")
        # Followed on the interface's own screen, as an epic of this machine is.
        await until(pilot, lambda: len(pilot.app.screen_stack) == 1, "the epic")
        await shows(pilot, "@box", "plan the far plan?")
        pilot.app.save_screenshot("followed-box.svg", str(tmp_path))

        # Left going there, asking still, and followed again from its own menu.
        await pilot.press("escape")
        await on(pilot, RemoteEpics)
        listing = pilot.app.screen.query_one("#choices", OptionList)
        await _menu(pilot, str(listing.options[0].id).removeprefix("="))
        await onto(pilot, "follow")
        await pilot.press("enter")
        await until(pilot, lambda: len(pilot.app.screen_stack) == 1, "the epic")
        await shows(pilot, "@box", "plan the far plan?")

        # Steered from here: each question answered, as an epic of this machine is.
        await typed(pilot, "a plan")
        await shows(pilot, "is 'a plan' good?")
        await typed(pilot, "it is")
        await until(pilot, (project / "result.json").exists, "the epic to end")
        await pilot.press("escape")
        await on(pilot, RemoteEpics)
        await leaves(pilot)
        await until(pilot, lambda: "@box" not in screen(pilot.app), "this machine's")

    assert json.loads((project / "result.json").read_text()) == {
        "plan": "a plan",
        "review": "it is",
    }


async def test_a_chat_followed_on_another_daemon_is_not_this_directorys(
    host: Host,
) -> None:
    Hmz().daemons.write("box", {"routes": ["stdio:ssh://box.example"]})
    project = host.home / "project"

    def starts() -> dict[str, Any]:
        with pick.remotes().client("box") as client:
            return client.call(
                "chat.start",
                {"workspace": str(project), "agent": RUNS, "task": "hi far"},
                idem="abc123abc123",
                seconds=PATIENCE,
            )

    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        made = await asyncio.to_thread(starts)
        await typed(pilot, "/epics @box")
        await on(pilot, RemoteEpics)
        await shows(pilot, "hi far")
        # A chat going there is no epic of that daemon, and is listed as a chat to follow.
        await shows(pilot, " · chat")
        await _menu(pilot, str(made["chat"]))
        assert "export" not in screen(pilot.app)
        await onto(pilot, "follow")
        await pilot.press("enter")
        await until(pilot, lambda: len(pilot.app.screen_stack) == 1, "the chat")
        await shows(pilot, "@box", "heard hi far")
        await typed(pilot, "more far")
        await shows(pilot, "heard more far")

        # Left going there: a line typed back here is this directory's own chat's.
        await pilot.press("escape")
        await on(pilot, RemoteEpics)
        await leaves(pilot)
        await until(pilot, lambda: "@box" not in screen(pilot.app), "this machine's")
        await typed(pilot, "hello local")
        await shows(pilot, "heard hello local")
        assert "is not a chat of" not in screen(pilot.app)


async def test_chat_while_another_daemons_epic_is_followed_is_this_machines(
    host: Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    Hmz().daemons.write("box", {"routes": ["stdio:ssh://box.example"]})
    project = host.home / "project"
    own_flow(project, ASKS)
    here = os.environ["HUMANIZE_HOME"]
    monkeypatch.setenv("HUMANIZE_HOME", str(host.humanize))
    Hmz(project).settings.remember(OWN, {}, budget={"cost": 1.0})
    monkeypatch.setenv("HUMANIZE_HOME", here)

    def held() -> list[str]:
        with pick.remotes().client("box") as client:
            listed = client.call("hosts.list", {}, seconds=PATIENCE)
        return [str(one["slot"]) for one in listed["held"]]

    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "hello local chat")
        await shows(pilot, "heard hello local chat")
        await typed(pilot, "/epics @box")
        await on(pilot, RemoteEpics)
        await pilot.press("n")
        await on(pilot, Starting)
        await pilot.press(*str(project), "enter")
        await onto(pilot, "flow")
        await pilot.press(*OWN, "enter")
        await pilot.press(*"the far plan", "enter")
        await pilot.click("#act-done")
        await until(pilot, lambda: len(pilot.app.screen_stack) == 1, "the epic")
        await shows(pilot, "@box", "plan the far plan?")

        # A line typed there once it has ended is no word to this machine's chat.
        await typed(pilot, "a plan")
        await shows(pilot, "is 'a plan' good?")
        await typed(pilot, "it is")
        await until(pilot, (project / "result.json").exists, "the epic to end")
        await shows(pilot, "the flow is done")
        await typed(pilot, "not from there")
        # Nor the start of a chat there: what `n` on that daemon's list starts is an epic.
        await shows(pilot, "start an epic on box with n on /epics @box")
        assert "start a chat on" not in screen(pilot.app)

        # The chat of this frontend is this machine's: back on its own host, here.
        await typed(pilot, "/chat")
        await until(pilot, lambda: "@box" not in screen(pilot.app), "this machine's")
        await shows(pilot, "heard hello local chat")
        await typed(pilot, "are you there")
        await shows(pilot, "heard are you there")
        assert "no chat is going here" not in screen(pilot.app)
        assert not [slot for slot in await asyncio.to_thread(held) if slot]


class _Gated:
    """Another daemon, holding each answer but the list's until it is let go."""

    def __init__(self) -> None:
        self.gates: dict[str, threading.Event] = {}

    def gate(self, method: str) -> threading.Event:
        return self.gates.setdefault(method, threading.Event())

    def client(self, _daemon: str) -> Self:
        return self

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_args: object) -> None:
        pass

    def call(self, method: str, *_args: Any, **_kwargs: Any) -> object:
        # The list is read by both: its epics and, beside them, its chats.
        if method not in {"runs.list", "chat.list"}:
            self.gate(method).wait(PATIENCE)
        return {
            "workspaces.list": {"here": "", "workspaces": [{"path": "/w"}]},
            "runs.get": {"task": "tidy the whole far project"},
            "runs.backup": {"queued": ["s3"]},
        }.get(
            method,
            {
                "runs": [
                    {
                        "name": "e1",
                        "flow": "ralph",
                        "task": "tidy the far project",
                        "workspace": "/w",
                        "sessions": 1,
                        "how": "done",
                        "held": True,
                        "slot": "",
                    }
                ],
                "total": 1,
            },
        )

    def close(self) -> None:
        for one in self.gates.values():
            one.set()


async def test_what_is_asked_of_another_daemon_is_said_while_it_is_under_way(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None
) -> None:
    del asking
    stand_in(tmp_path, monkeypatch)
    held = _Gated()
    monkeypatch.setattr(pick, "remotes", lambda: held)
    following = threading.Event()

    def remote(*_args: object) -> object:
        following.wait(PATIENCE)
        raise OSError("box went away")

    monkeypatch.setattr(link, "remote", remote)
    Hmz().daemons.write("box", {"routes": ["stdio:ssh://box.example"]})
    try:
        async with Humanize().run_test(size=SIZE) as pilot:
            await opened(pilot)
            await typed(pilot, "/epics @box")
            await on(pilot, RemoteEpics)
            await shows(pilot, "tidy the far project")

            await pilot.press("n")
            await shows(pilot, "reaching box…")
            held.gate("workspaces.list").set()
            await on(pilot, Starting)
            await shows(pilot, "/w")
            await pilot.press("escape")
            await on(pilot, RemoteEpics)
            assert "reaching box…" not in screen(pilot.app)

            await _menu(pilot, "e1")
            await onto(pilot, "copy-task")
            await pilot.press("enter")
            await shows(pilot, "fetching the task…")
            held.gate("runs.get").set()
            await shows(pilot, "task copied")

            await _menu(pilot, "e1")
            await onto(pilot, "upload")
            await pilot.press("enter")
            await shows(pilot, "backing e1 up…")
            held.gate("runs.backup").set()
            await shows(pilot, "backing e1 up to s3")

            # Followed on the interface's own screen, which says why it could not be.
            await _menu(pilot, "e1")
            await onto(pilot, "follow")
            await pilot.press("enter")
            await shows(pilot, "following /w on box")
            following.set()
            await shows(pilot, "hmz: box went away")
            await until(
                pilot, lambda: "@box" not in screen(pilot.app), "this machine's"
            )
    finally:
        held.close()
        following.set()


async def test_another_daemons_epics_left_while_they_are_read_have_nothing_to_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None
) -> None:
    del asking
    stand_in(tmp_path, monkeypatch)

    class Slow(_Gated):
        """Another daemon, holding the list as well until it is let go."""

        def call(self, method: str, *args: Any, **kwargs: Any) -> object:
            self.gate("asked").set()
            self.gate("left").wait(PATIENCE)
            return super().call(method, *args, **kwargs)

    held = Slow()
    monkeypatch.setattr(pick, "remotes", lambda: held)
    Hmz().daemons.write("box", {"routes": ["stdio:ssh://box.example"]})

    def emptied(sheet: RemoteEpics) -> None:
        """Lets the list go once the sheet is taken apart, and not yet taken off."""
        if sheet.query("#about"):
            asyncio.get_running_loop().call_soon(emptied, sheet)
        else:
            held.gate("left").set()

    try:
        async with Humanize().run_test(size=SIZE) as pilot:
            await opened(pilot)
            await typed(pilot, "/epics @box")
            sheet = await on(pilot, RemoteEpics)
            await until(pilot, held.gate("asked").is_set, "the list to be asked for")
            # A sheet closed loses what it draws on before it is off the interface: the
            # list read by then has nothing to be put up on, and nothing comes of it.
            emptied(sheet)
            await pilot.press("escape")
            await until(pilot, held.gate("left").is_set, "the sheet to be taken apart")
            await until(pilot, lambda: not sheet.workers, "the read to end")
            await until(pilot, lambda: len(pilot.app.screen_stack) == 1, "the prompt")
    finally:
        held.close()


@pytest.fixture
def ssh_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> None:
    """The stand-in `claude` here, and an ssh config in the test's own home naming two hosts."""
    del asking
    if shutil.which("ssh") is None:
        pytest.skip("needs ssh -G")
    stand_in(tmp_path, monkeypatch)
    at = Path.home() / ".ssh" / "config"
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(
        "Host gpu\n  HostName gpu.example\n  User me\n  Port 2222\n"
        "Host box\n  HostName box.example\n"
    )
    # `ssh -G` reads the home of the account, not `HOME`: told the test's config instead.
    monkeypatch.setattr(
        sshconfig, "resolve", partial(sshconfig.resolve, flags=("-F", str(at)))
    )


def _written() -> dict[str, dict[str, Any]]:
    """Each daemon as the settings file holds it, by name."""
    held = yaml.safe_load((home() / "settings.yaml").read_text())
    return {one.pop("name"): one for one in held["daemons"]}


async def test_a_daemon_is_added_in_each_mode(ssh_config: None, tmp_path: Path) -> None:
    del ssh_config
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings daemons")
        await on(pilot, Adjusts)

        # A pairing code that is none is refused, and nothing is written.
        await _adds(pilot, "lab")
        await shows(pilot, "Pairing code", "as hmz daemon pair printed it there")
        await pilot.press(*"hmz-pair:nope", "enter")
        await pilot.click("#act-done")
        await on(pilot, Adjusts)
        await shows(pilot, "not a pairing code")

        # SSH Config: a Host of the ssh config, and nothing else.
        await _adds(pilot, "cfg")
        await picks(pilot, "mode", "SSH Config")
        await shows(pilot, "a Host of your ssh config")
        await picks(pilot, "alias", "gpu")
        pilot.app.save_screenshot("daemon-ssh-config.svg", str(tmp_path))
        await pilot.click("#act-done")
        await on(pilot, Adjusts)
        await shows(pilot, "cfg saved", "stdio:ssh://gpu ·")

        # Custom, its fields filled from a host of the ssh config.
        await _adds(pilot, "kept")
        await picks(pilot, "mode", "Custom")
        await picks(pilot, "import", "gpu")
        await shows(pilot, "gpu.example", "2222")
        pilot.app.save_screenshot("daemon-custom.svg", str(tmp_path))
        await pilot.click("#act-done")
        await on(pilot, Adjusts)
        await shows(pilot, "kept saved", "stdio:ssh://me@gpu.example:2222")

        # Routes, in order: an untrusted one first needs the id a pairing code gives.
        await _adds(pilot, "far")
        await picks(pilot, "mode", "Routes")
        await onto(pilot, "routes")
        await pilot.press(*"tcp://10.0.0.1:41817, stdio:ssh://box", "enter")
        await pilot.click("#act-done")
        await on(pilot, Adjusts)
        await shows(pilot, "needs the id of the daemon it reaches")
        await _adds(pilot, "far")
        await picks(pilot, "mode", "Routes")
        await onto(pilot, "routes")
        await pilot.press(*"stdio:ssh://box, tcp://10.0.0.1:41817", "enter")
        await pilot.click("#act-done")
        await on(pilot, Adjusts)
        await shows(pilot, "far saved")
        pilot.app.save_screenshot("daemons-modes.svg", str(tmp_path))

    written = _written()
    assert "lab" not in written
    assert written["cfg"] == {"id": "", "routes": ["stdio:ssh://gpu"]}
    assert written["kept"]["routes"][0].startswith("stdio:ssh://me@gpu.example:2222")
    assert written["far"]["routes"] == ["stdio:ssh://box", "tcp://10.0.0.1:41817"]


async def test_a_daemon_edited_opens_in_its_mode(ssh_config: None) -> None:
    del ssh_config
    Hmz().daemons.write("box", {"routes": ["stdio:ssh://me@box.example:2200"]})
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings daemons")
        await on(pilot, Adjusts)
        await shows(pilot, "stdio:ssh://me@box.example:2200")

        await _menu(pilot, "box")
        await onto(pilot, "edit")
        await pilot.press("enter")
        await on(pilot, Daemoning)
        await shows(pilot, "Custom", "box.example", "2200")
        await onto(pilot, "port")
        await pilot.press(*["backspace"] * 4, *"2222", "enter")
        await pilot.click("#act-done")
        await on(pilot, Adjusts)
        await shows(pilot, "box saved", "stdio:ssh://me@box.example:2222")

    assert _written()["box"] == {
        "id": "",
        "routes": ["stdio:ssh://me@box.example:2222"],
    }


@pytest.fixture
def served(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None
) -> Iterator[str]:
    """The stand-in `claude` here, and `hmz daemon serve` under a home of its own on loopback.

    Yields:
      A pairing code it made.
    """
    del asking
    stand_in(tmp_path, monkeypatch)
    there = dict(
        os.environ,
        HUMANIZE_HOME=str(tmp_path / "served"),
        # Short, as a socket's path under it must be.
        TMPDIR=tempfile.mkdtemp(prefix="s", dir=os.environ["TMPDIR"]),
    )
    serving = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "hmz",
            "daemon",
            "serve",
            "--listen",
            "tcp://127.0.0.1:0",
        ],
        env=there,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert serving.stdout is not None
        assert "listening on tcp://" in serving.stdout.readline()
        yield subprocess.run(
            [sys.executable, "-m", "hmz", "daemon", "pair"],
            env=there,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()[0]
    finally:
        serving.terminate()
        serving.wait(10)


async def test_a_daemon_is_paired_from_its_code_and_a_device_revoked(
    served: str,
) -> None:
    code = served
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings daemons")
        await on(pilot, Adjusts)

        await _adds(pilot, "lab")
        await pilot.press(*code, "enter")
        await pilot.click("#act-done")
        await on(pilot, Adjusts)
        await shows(pilot, "lab saved", "tcp://127.0.0.1:")

        await _menu(pilot, "lab")
        await onto(pilot, "connect")
        await pilot.press("enter")
        await on(pilot, Adjusts)
        await shows(pilot, f"up, hmz {version('hmz')}")

        # Another device paired from a code it makes, then this one's pairing revoked.
        await _menu(pilot, "lab")
        await onto(pilot, "pair")
        await pilot.press("enter")
        await on(pilot, Adjusts)
        await shows(pilot, "copied:", "hmz-pair:")

        await _menu(pilot, "lab")
        await onto(pilot, "devices")
        await pilot.press("enter")
        await on(pilot, Devices)
        await pilot.press("enter")
        await on(pilot, Revokes)
        await pilot.press("enter")
        await on(pilot, Adjusts)
        await shows(pilot, " revoked")

    (lab,) = Hmz().daemons.all()
    assert lab["id"]
