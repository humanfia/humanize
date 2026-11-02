"""Other machines' daemons from the terminal: the daemons page, `/epics @<name>`, and `m`.

The other machine is this one under a home of its own, reached by the stand-in `ssh` of
`doubles_ssh`, running this `hmz web` there as the real one would run the one installed.
"""

from __future__ import annotations

import os
import shutil
import tarfile
import threading
from functools import partial
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml
from textual.widgets import OptionList

from hmz import home
from hmz.coganchor.machines import sshconfig
from hmz.daemon import link
from hmz.runtime import Hmz
from hmz.runtime.epic import Epic
from hmz.tui import Humanize, pick
from hmz.tui.afar import Afar
from hmz.tui.pick import (
    Acts,
    Batching,
    Daemoning,
    Epics,
    Exporting,
    RemoteEpics,
    Starting,
)
from hmz.tui.settings import Adjusts
from tests.integration.doubles_ssh import Host, faked
from tests.integration.doubles_tui import (
    MODEL,
    PATIENCE,
    SIZE,
    leaves,
    on,
    onto,
    opened,
    picks,
    screen,
    shows,
    stand_in,
    typed,
)

if TYPE_CHECKING:
    from textual.pilot import Pilot


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, asking: None) -> Host:
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
    return found


async def _menu(pilot: Pilot[None], row: str = "") -> Acts:
    """Walks on to one row of the sheet on top, or stays, and opens its menu with `m`."""
    if row:
        await onto(pilot, row)
    await pilot.press("m")
    return await on(pilot, Acts)


async def test_a_daemon_is_added_and_its_epics_listed_and_exported(
    host: Host, tmp_path: Path
) -> None:
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings daemons")
        await on(pilot, Adjusts)
        await shows(pilot, "Local", "no other daemons yet")
        pilot.app.save_screenshot("daemons-empty.svg", str(tmp_path))

        await pilot.click("#act-add")
        await on(pilot, Daemoning)
        await pilot.press(*"box", "enter")
        await pilot.press(*"box.example", "enter")
        await pilot.click("#act-done")
        await on(pilot, Adjusts)
        await shows(pilot, "box saved", "box.example")

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
    Hmz().daemons.write("box", {"host": "box.example"})
    Hmz().settings.detailing(on=True)
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings daemons")
        await on(pilot, Adjusts)
        await shows(pilot, "box.example")

        await pilot.click("#act-batch")
        await on(pilot, Batching)
        await shows(pilot, "general", "fallback", "runtimes", "backup", "box")
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


async def test_an_epic_is_started_on_another_daemon_and_followed_here(
    host: Host,
) -> None:
    Hmz().daemons.write("box", {"host": "box.example"})
    project = host.home / "project"
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/epics @box")
        await on(pilot, RemoteEpics)
        await shows(pilot, "tidy the far project")

        await pilot.press("n")
        await on(pilot, Starting)
        await pilot.press(*str(project), "enter")
        await pilot.press(*"hello", "enter")
        await pilot.press(*f"assistant=claude/{MODEL}:high", "enter")
        await pilot.click("#act-done")
        await on(pilot, Afar)
        await shows(pilot, "❯ hello", "heard hello", "waiting for you")

        await pilot.press(*"again", "enter")
        await shows(pilot, "❯ again", "heard again")
        await pilot.press("escape")
        await on(pilot, RemoteEpics)
        await shows(pilot, "· chat")

        # Followed again from its own menu, while a host there holds it: the newest.
        listing = pilot.app.screen.query_one("#choices", OptionList)
        await _menu(pilot, str(listing.options[0].id).removeprefix("="))
        await onto(pilot, "follow")
        await pilot.press("enter")
        await on(pilot, Afar)
        await shows(pilot, "heard again")
        await pilot.press("escape")
        await on(pilot, RemoteEpics)


class _Held:
    """Another daemon's interface, holding each answer but the list until it is let go."""

    def __init__(self) -> None:
        self.gates: dict[str, threading.Event] = {}

    def gate(self, path: str) -> threading.Event:
        return self.gates.setdefault(path, threading.Event())

    def asked(self, _daemon: str, path: str, *_args: Any, **_kwargs: Any) -> object:
        if not path.startswith("/api/runs?"):
            self.gate(path).wait(PATIENCE)
        return {
            "/api/held": {"here": "/w"},
            "/api/runs/e1": {"task": "tidy the whole far project"},
            "/api/runs/e1/backup": {"queued": ["s3"]},
        }.get(
            path,
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
    held = _Held()
    monkeypatch.setattr(pick, "remotes", lambda: held)
    following = threading.Event()

    def remote(*_args: object) -> object:
        following.wait(PATIENCE)
        raise OSError("box went away")

    monkeypatch.setattr(link, "remote", remote)
    Hmz().daemons.write("box", {"host": "box.example"})
    try:
        async with Humanize().run_test(size=SIZE) as pilot:
            await opened(pilot)
            await typed(pilot, "/epics @box")
            await on(pilot, RemoteEpics)
            await shows(pilot, "tidy the far project")

            await pilot.press("n")
            await shows(pilot, "reaching box…")
            held.gate("/api/held").set()
            await on(pilot, Starting)
            await pilot.press("escape")
            await on(pilot, RemoteEpics)
            assert "reaching box…" not in screen(pilot.app)

            await _menu(pilot, "e1")
            await onto(pilot, "copy-task")
            await pilot.press("enter")
            await shows(pilot, "fetching the task…")
            held.gate("/api/runs/e1").set()
            await shows(pilot, "task copied")

            await _menu(pilot, "e1")
            await onto(pilot, "upload")
            await pilot.press("enter")
            await shows(pilot, "backing e1 up…")
            held.gate("/api/runs/e1/backup").set()
            await shows(pilot, "backing e1 up to s3")

            await _menu(pilot, "e1")
            await onto(pilot, "follow")
            await pilot.press("enter")
            await shows(pilot, "following /w on box…")
            following.set()
            await shows(pilot, "box went away")
    finally:
        held.close()
        following.set()


#: A secret an EasyTier daemon may be written with: 16 bytes and more.
_SECRET = "a secret of sixteen bytes or more"


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


async def _adds(pilot: Pilot[None], name: str) -> None:
    """Opens the form that adds a daemon, and names it."""
    await pilot.click("#act-add")
    await on(pilot, Daemoning)
    await pilot.press(*name, "enter")


async def test_a_daemon_is_added_in_each_mode(ssh_config: None, tmp_path: Path) -> None:
    del ssh_config
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings daemons")
        await on(pilot, Adjusts)

        # SSH, SSH Config: a Host of the ssh config, and nothing else.
        await _adds(pilot, "cfg")
        await picks(pilot, "mode", "SSH Config")
        await shows(pilot, "a Host of your ssh config")
        await picks(pilot, "alias", "gpu")
        pilot.app.save_screenshot("daemon-ssh-config.svg", str(tmp_path))
        await pilot.click("#act-done")
        await on(pilot, Adjusts)
        await shows(pilot, "cfg saved", "SSH Config · gpu")

        # SSH, Custom, its fields filled from a host of the ssh config.
        await _adds(pilot, "kept")
        await picks(pilot, "import", "gpu")
        await shows(pilot, "gpu.example", "2222")
        pilot.app.save_screenshot("daemon-custom.svg", str(tmp_path))
        await pilot.click("#act-done")
        await on(pilot, Adjusts)
        await shows(pilot, "kept saved", "Custom · me@gpu.example:2222")

        # P2P, EasyTier: a secret too short is refused before it is written.
        await _adds(pilot, "far")
        await picks(pilot, "kind", "P2P")
        await shows(pilot, "EasyTier", "shared EasyTier nodes")
        await onto(pilot, "secret")
        await pilot.press(*"too short", "enter")
        await onto(pilot, "peers")
        await pilot.press(
            *"tcp://node.example:11010, udp://node.example:11010", "enter"
        )
        await pilot.click("#act-done")
        await shows(pilot, "A secret must be at least 16 bytes.")
        assert "too short" not in screen(pilot.app)
        assert "far" not in _written()
        await onto(pilot, "secret")
        await pilot.press(*["backspace"] * len("too short"), *_SECRET, "enter")
        assert _SECRET not in screen(pilot.app)
        pilot.app.save_screenshot("daemon-easytier.svg", str(tmp_path))
        await pilot.click("#act-done")
        await on(pilot, Adjusts)
        await shows(pilot, "far saved", "P2P · EasyTier")
        pilot.app.save_screenshot("daemons-modes.svg", str(tmp_path))

    written = _written()
    assert written["cfg"]["alias"] == "gpu"
    assert not written["cfg"]["host"]
    assert written["kept"]["host"] == "gpu.example"
    assert (written["kept"]["user"], written["kept"]["port"]) == ("me", 2222)
    assert not written["kept"]["alias"]
    assert written["far"]["via"] == "easytier"
    assert written["far"]["secret"] == _SECRET
    assert written["far"]["peers"] == [
        "tcp://node.example:11010",
        "udp://node.example:11010",
    ]


async def test_an_easytier_daemon_edited_keeps_its_secret(ssh_config: None) -> None:
    del ssh_config
    Hmz().daemons.write(
        "far",
        {"via": "easytier", "secret": _SECRET, "peers": ["tcp://node.example:11010"]},
    )
    async with Humanize().run_test(size=SIZE) as pilot:
        await opened(pilot)
        await typed(pilot, "/settings daemons")
        await on(pilot, Adjusts)
        await shows(pilot, "P2P · EasyTier")

        # Opened in its own mode, its secret never shown, and left blank.
        await _menu(pilot, "far")
        await onto(pilot, "edit")
        await pilot.press("enter")
        await on(pilot, Daemoning)
        await shows(pilot, "EasyTier", "leave blank to keep current value")
        assert _SECRET not in screen(pilot.app)
        await onto(pilot, "peers")
        await pilot.press(*", wss://other.example:443", "enter")
        await pilot.click("#act-done")
        await on(pilot, Adjusts)
        await shows(pilot, "far saved")

    far = _written()["far"]
    assert far["via"] == "easytier"
    assert far["secret"] == _SECRET
    assert far["peers"] == ["tcp://node.example:11010", "wss://other.example:443"]
