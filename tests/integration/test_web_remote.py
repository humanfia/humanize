"""A daemon on another machine, reached over ssh and answered through this interface.

The other machine is this one under a home of its own, reached by the stand-in `ssh` of
`doubles_ssh`, running this `hmz web` there as the real one would run the one installed.
"""

from __future__ import annotations

import contextlib
import http.client
import os
import re
import signal
import socket
import subprocess
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz.web.remote import Remotes

from .doubles_ssh import Host, faked, written
from .doubles_web import PATIENCE, Answer, Browser, served

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.web.site import Site


@pytest.fixture
def host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Host:
    """The other machine, written down as `box`, with this version of `hmz`."""
    found = faked(tmp_path, monkeypatch)
    _THERE[:] = [found.home]
    written(
        {
            "name": "box",
            "host": "box.example",
            "user": "me",
            "options": [["Compression", "yes"]],
        }
    )
    return found


#: The other machine's home, for what its interface said when it never came up.
_THERE: list[Path] = []


def _processes() -> str:
    """What runs of the stand-in's, and the stack of each interface there that never listened."""
    listed = subprocess.run(
        ["ps", "-axo", "pid,ppid,etime,command"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    mine = [line for line in listed.splitlines() if re.search(r"ssh|hmz|\bsh\b", line)]
    for line in mine:
        pid, ppid, *_ = line.split()
        if int(ppid) == os.getpid() and "faulthandler -m hmz web" in line:
            with contextlib.suppress(OSError):
                os.kill(int(pid), signal.SIGABRT)
    time.sleep(1)
    said = [
        (home / "web.err").read_text() for home in _THERE if (home / "web.err").exists()
    ]
    return "\n".join([*mine, *said])


def _stands(remotes: Remotes, name: str, *states: str) -> dict[str, str]:
    """How a daemon stands, once it stands as one of `states`."""
    ending = time.monotonic() + PATIENCE
    while (said := remotes.state(name))["state"] not in states:
        assert time.monotonic() < ending, (
            f"{name} never came to {states}: {said}\n{_processes()}"
        )
        time.sleep(0.05)
    return said


def _asked(browser: Browser, path: str) -> Answer:
    """What the interface answers a read with, once the daemon is reached."""
    ending = time.monotonic() + PATIENCE
    while (answer := browser.get(path)).status == 503:
        assert time.monotonic() < ending, f"{answer.body!r}\n{_processes()}"
        time.sleep(0.1)
    return answer


def _gone(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def test_a_page_reads_and_writes_a_daemon_on_another_machine(host: Host) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        listed = _asked(browser, "/d/box/api/workspaces")
        assert listed.status == 200, listed.body
        assert str(host.home) in str(listed.json())
        state = browser.get("/api/daemons/box/state").json()
        assert state == {"state": "up", "detail": "", "version": "0.0.0"}
        # Written there, and not here.
        kept = host.home / "project"
        kept.mkdir()
        wrote = browser.post("/d/box/api/workspaces", {"workspace": str(kept)})
        assert wrote.status == 200, wrote.body
        assert wrote.json()["kept"] == str(kept)
        assert str(kept) in (host.humanize / "settings.yaml").read_text()
        # A file sent there a piece at a time, refused there for what it is.
        sent = browser.sends(
            "/d/box/api/runs/import", b"not an epic" * 1000, "x.hmzepic"
        )
        assert sent.status not in (502, 503), sent.body
        assert "error" in sent.json()
        # Its runs, as a page reads them.
        assert _asked(browser, "/d/box/api/runs").status == 200
        # And what it was told: nothing asked of anybody, the host's own options first.
        told = host.told()[0]
        assert told.index("Compression=yes") < told.index("BatchMode=yes")
        assert told.index("BatchMode=yes") < told.index("BatchMode=no")
        assert "me@box.example" in told


def test_local_is_this_machine_by_either_path(host: Host) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        assert (
            browser.get("/d/local/api/workspaces").json()
            == browser.get("/api/workspaces").json()
        )
        assert browser.get("/api/daemons/local/state").json()["state"] == "up"
        assert browser.get("/d/nobody/api/runs").status == 404
        assert browser.get("/api/daemons/nobody/state").status == 404
        assert not host.pids()


def test_only_the_page_let_in_reaches_another_machine(host: Host) -> None:
    with served() as site:
        browser = Browser(site)
        assert browser.get("/d/box/api/runs").status == 401
        browser.signs_in()
        assert (
            browser.get("/d/box/api/runs", **{"Sec-Fetch-Site": "cross-site"}).status
            == 403
        )
        assert (
            browser.post(
                "/d/box/api/workspaces", {}, Origin="http://elsewhere.example"
            ).status
            == 403
        )
        assert not host.pids()


def test_a_stream_of_events_comes_through_as_it_comes(host: Host) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        _asked(browser, "/d/box/api/runs")
        connection = http.client.HTTPConnection(
            "127.0.0.1", site.port, timeout=PATIENCE
        )
        try:
            connection.request(
                "GET",
                "/d/box/api/held/stream",
                headers={"Host": f"127.0.0.1:{site.port}", "Cookie": browser.cookie},
            )
            stream = connection.getresponse()
            assert stream.status == 200
            assert stream.getheader("Content-Type", "").startswith("text/event-stream")
            assert stream.getheader("Set-Cookie") is None
            events: list[str] = []
            while not events:
                line = stream.readline().decode()
                assert line, "the stream ended before any event"
                if line.startswith("event: "):
                    events.append(line.removeprefix("event: ").strip())
        finally:
            connection.close()


def test_a_daemon_that_cannot_be_reached_says_why(
    host: Host, monkeypatch: pytest.MonkeyPatch
) -> None:
    del host
    written({"name": "gone", "host": "unreachable.example"})
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        connected = browser.post("/api/daemons/gone/connect")
        assert connected.status == 200
        remotes = _remotes(site)
        said = _stands(remotes, "gone", "failed")
        assert "Could not resolve hostname" in said["detail"]
        refused = browser.get("/d/gone/api/runs")
        assert refused.status == 503
        assert refused.json()["state"] == "failed"


def test_closing_stops_and_reaps_every_process_started(host: Host) -> None:
    remotes = Remotes()
    remotes.connect("box")
    _stands(remotes, "box", "up")
    port, key = remotes.reached("box")
    assert key
    pids = host.pids()
    # The probe, the interface there, the forward.
    assert len(pids) == 3
    forward = host.told()[-1]
    assert "ControlPath=none" in forward
    assert any(word.startswith(f"127.0.0.1:{port}:127.0.0.1:") for word in forward)
    remotes.close()
    assert all(_gone(pid) for pid in pids)
    assert remotes.state("box")["state"] == "idle"
    with socket.socket() as again:
        assert again.connect_ex(("127.0.0.1", port)) != 0


def test_another_version_there_is_replaced_with_this_one(host: Host) -> None:
    host.installs("1.0.0")
    remotes = Remotes(version="1.2.3")
    try:
        remotes.connect("box")
        said = _stands(remotes, "box", "up", "failed")
        assert said == {"state": "up", "detail": "", "version": "1.2.3"}
        assert host.installed().split() == [
            "tool",
            "install",
            "--force",
            "--python",
            ">=3.12",
            "hmz==1.2.3",
        ]
    finally:
        remotes.close()


def test_one_missing_there_is_installed(host: Host) -> None:
    host.installs(None)
    remotes = Remotes(version="1.2.3")
    try:
        remotes.connect("box")
        assert _stands(remotes, "box", "up", "failed")["version"] == "1.2.3"
    finally:
        remotes.close()


def test_one_running_epics_there_is_left_alone(host: Host) -> None:
    host.installs("1.0.0")
    host.runs_epics()
    remotes = Remotes(version="1.2.3")
    try:
        remotes.connect("box")
        said = _stands(remotes, "box", "up", "failed")
        assert said["state"] == "up"
        assert said["version"] == "1.0.0"
        assert "running epics" in said["detail"]
        assert not host.installed()
    finally:
        remotes.close()


def test_a_development_build_installs_nothing(host: Host) -> None:
    host.installs(None)
    remotes = Remotes(version="0.0.0")
    try:
        remotes.connect("box")
        said = _stands(remotes, "box", "failed")
        assert said["detail"] == "hmz is not installed on box."
        assert not host.installed()
    finally:
        remotes.close()


def test_a_daemon_no_longer_written_down_is_let_go(host: Host) -> None:
    with served() as site:
        browser = Browser(site)
        browser.signs_in()
        assert _asked(browser, "/d/box/api/runs").status == 200
        pids = host.pids()
        written({"name": "other", "host": "other.example"})
        assert browser.get("/d/box/api/runs").status == 404
        assert browser.get("/api/daemons/box/state").status == 404
        ending = time.monotonic() + PATIENCE
        while not all(_gone(pid) for pid in pids):
            assert time.monotonic() < ending, "what reached it was never stopped"
            time.sleep(0.05)


def _remotes(site: Site) -> Any:
    assert site.remotes is not None
    return site.remotes
