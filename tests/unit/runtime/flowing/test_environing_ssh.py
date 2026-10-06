"""A machine reached over ssh, with coganchor's transport and serving half stood in for."""

from __future__ import annotations

import asyncio
import errno
import signal
from pathlib import PurePosixPath

import pytest

from hmz.coganchor import AnchorConfig
from hmz.coganchor.machines import AnchoredConfig
from hmz.flows import (
    EnvBackendKind,
    EnvCommandTimeout,
    EnvConnectionError,
    EnvError,
    EnvFileNotFound,
    EnvPermissionDenied,
    EnvUnavailable,
)
from hmz.runtime.flowing.environing import MachineEnvDriver, Resources
from hmz.runtime.flowing.environing_ssh import PROBE_SCRIPT, SSHMachine, facts_of
from tests.unit.runtime.flowing.doubles_u11 import FakeRemote, reach, same_path, until

# ------------------------------------------------------------------------- what it says


def test_what_a_host_says_about_itself_is_read() -> None:
    facts = facts_of(
        "home=/home/me\nstate=/srv/hmz/./x/..\ncpus=32\nmemkb=2048\n"
        "cuda=1\ngpu=0, GPU-a, 100\ngpu=1, GPU-b, 50\ngit=1\nbash=0\njunk\n"
    )

    assert facts.home == PurePosixPath("/home/me")
    assert facts.state == PurePosixPath("/srv/hmz")
    assert facts.resources == Resources(32, 2048 * 1024, 1, 50 << 20)
    assert dict(facts.tools) == {"git": True, "bash": False}


@pytest.mark.parametrize(
    ("said", "resources", "state"),
    [
        ("home=/h\n", Resources(1, 0, 0, 0), "/h/.hmz"),
        (
            "home=/h\nstate=rel\ncpus=0\nmemory=4096\n",
            Resources(1, 4096, 0, 0),
            "/h/rel",
        ),
        ("home=/h\ncpus=many\nmemkb=x\nmemory=y\n", Resources(1, 0, 0, 0), "/h/.hmz"),
    ],
    ids=["nothing-but-home", "a-mac", "nonsense"],
)
def test_what_a_host_does_not_say_is_the_least_it_could_have(
    said: str, resources: Resources, state: str
) -> None:
    facts = facts_of(said)

    assert facts.resources == resources
    assert facts.state == PurePosixPath(state)
    assert dict(facts.tools) == {}


@pytest.mark.parametrize("said", ["", "home=\n", "home=relative\n", "garbage"])
def test_a_host_that_did_not_say_where_home_is_was_not_reached(said: str) -> None:
    with pytest.raises(EnvConnectionError, match="home"):
        facts_of(said)


def test_the_probe_asks_for_everything_facts_are_read_from() -> None:
    for asked in (
        "home=",
        "state=",
        "cpus=",
        "memkb=",
        "memory=",
        "cuda=",
        "nvidia-smi",
    ):
        assert asked in PROBE_SCRIPT
    assert "for tool in bash git" in PROBE_SCRIPT


# ---------------------------------------------------------------------- before reaching


@pytest.mark.parametrize(
    "host", ["me@box", "box:2222", "me@box.example.com:22", "alias_1"]
)
def test_an_ssh_destination_names_a_machine_without_reaching_it(host: str) -> None:
    machine = SSHMachine(host)

    assert (machine.backend, machine.provider) == (EnvBackendKind.SSH, host)
    assert machine.target == f"ssh://{host}"
    assert machine.identity == f"ssh:{host}"
    assert machine.resources(gpus=True) == Resources()
    assert machine.has("git") is None
    assert not machine.available(PurePosixPath("/w"), seen=True)


@pytest.mark.parametrize("host", ["", "-oProxyCommand=x", "a b", "me@", "box:port"])
def test_what_is_no_ssh_destination_is_refused(host: str) -> None:
    with pytest.raises(EnvUnavailable, match="not an ssh host"):
        SSHMachine(host)


def test_a_saved_runtime_is_named_for_itself_and_reached_by_its_target() -> None:
    machine = SSHMachine("gpu box", "ssh://me@gpu:2222?ProxyJump=bastion")

    assert machine.provider == "gpu box"
    assert machine.target == "ssh://me@gpu:2222?ProxyJump=bastion"
    assert machine.identity == "ssh:me@gpu:2222?ProxyJump=bastion"


@pytest.mark.parametrize(
    ("workdir", "anchor"),
    [
        ("/srv/x", AnchorConfig(target="ssh://box", workspace="/srv/x")),
        ("~/x", AnchorConfig(target="ssh://box", remote_path="~/x")),
    ],
)
def test_an_agent_is_anchored_at_the_host_in_the_workdir(
    workdir: str, anchor: AnchorConfig
) -> None:
    placement = SSHMachine("box").placement(PurePosixPath(workdir))

    assert (placement.backend, placement.provider, placement.workdir) == (
        EnvBackendKind.SSH,
        "box",
        PurePosixPath(workdir),
    )
    assert placement.machine == AnchoredConfig(anchor=anchor)


# --------------------------------------------------------------------------- reaching it


async def test_a_host_reached_says_what_it_has_and_where_home_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = reach(monkeypatch)
    machine = SSHMachine("box")

    await asyncio.gather(machine.probe(), machine.probe(), machine.state())

    assert remote.connects == 1, "one connection however many ask at once"
    assert machine.resources(gpus=False) == Resources(16, 1 << 30, 2, 16384 << 20)
    assert (machine.has("git"), machine.has("bash"), machine.has("rsync")) == (
        True,
        False,
        None,
    )
    assert machine.available(PurePosixPath("/w"), seen=True)
    assert not machine.available(PurePosixPath("/w"), seen=None)
    assert await machine.state() == PurePosixPath("/home/me/.hmz")
    assert await machine.absolute(PurePosixPath("~/x")) == PurePosixPath("/home/me/x")
    assert await machine.absolute(PurePosixPath("/x")) == PurePosixPath("/x")
    anchor = AnchorConfig(target="ssh://box", workspace="/home/me/x")
    assert machine.placement(PurePosixPath("~/x")).machine == AnchoredConfig(
        anchor=anchor
    )


@pytest.mark.parametrize(
    ("refused", "kind"),
    [
        (ValueError("bad target"), EnvUnavailable),
        (OSError("ssh: Could not resolve hostname box"), EnvUnavailable),
        (OSError("Connection refused"), EnvConnectionError),
    ],
    ids=["no-target", "no-such-host", "unreachable"],
)
async def test_a_host_that_cannot_be_reached_says_why(
    monkeypatch: pytest.MonkeyPatch, refused: Exception, kind: type[EnvError]
) -> None:
    reach(monkeypatch, refused=refused)
    machine = SSHMachine("box")

    with pytest.raises(kind, match="box"):
        await machine.probe()
    assert not machine.available(PurePosixPath("/w"), seen=True)


async def test_a_host_that_will_not_say_where_home_is_was_not_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = reach(monkeypatch, FakeRemote(probe="nothing\n"))

    with pytest.raises(EnvConnectionError, match="could not reach box over ssh"):
        await SSHMachine("box").probe()
    assert remote.closes == 1, "the connection that answered nothing was let go of"


# ------------------------------------------------------------------------- over a driver


async def _driver(
    monkeypatch: pytest.MonkeyPatch, remote: FakeRemote
) -> MachineEnvDriver:
    reach(monkeypatch, remote)
    driver = MachineEnvDriver(SSHMachine("box"), PurePosixPath("/work"))
    await driver.probe()
    return driver


async def test_a_command_runs_there_and_says_what_it_wrote_apart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = FakeRemote(answer=lambda argv, cwd: (3, "out\n", "err\n"))
    driver = await _driver(monkeypatch, remote)

    said = await driver.exec(["make"], timeout=0)

    assert said == (3, "out\n", "err\n")
    assert remote.commands == [(["make"], "/work")]
    assert driver.available


async def test_a_command_past_its_timeout_is_killed_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = FakeRemote(answer=lambda argv, cwd: None)
    driver = await _driver(monkeypatch, remote)

    with pytest.raises(EnvCommandTimeout):
        await driver.exec(["sleep", "1000"], timeout=0.01)

    (killed,) = remote.execs
    assert killed.signals == [signal.SIGKILL]


async def test_a_command_the_host_could_not_start_in_its_workdir_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from hmz.coganchor import proto
    from hmz.coganchor.proto import RemoteOSError

    monkeypatch.setattr(proto, "path_key", same_path)
    gone = RemoteOSError(errno.ENOENT, "No such file or directory", "/work")
    driver = await _driver(monkeypatch, FakeRemote(answer=lambda argv, cwd: gone))

    with pytest.raises(EnvUnavailable, match="/work"):
        await driver.exec(["true"], timeout=0)
    assert not driver.available


async def test_a_lost_connection_is_one_to_make_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = FakeRemote(
        answer=lambda argv, cwd: ConnectionResetError(errno.ECONNRESET, "x")
    )
    driver = await _driver(monkeypatch, remote)

    with pytest.raises(EnvConnectionError):
        await driver.exec(["true"], timeout=0)
    remote.answer = lambda argv, cwd: (0, "back", "")

    assert await driver.exec(["true"], timeout=0) == (0, "back", "")
    assert remote.connects == 2


async def test_files_are_read_and_written_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = FakeRemote()
    driver = await _driver(monkeypatch, remote)

    await driver.write("a.txt", b"hello")
    await driver.write("~/b.txt", b"home")

    assert remote.files == {"/work/a.txt": b"hello", "/home/me/b.txt": b"home"}
    assert await driver.read("a.txt") == b"hello"
    with pytest.raises(EnvFileNotFound, match="on box"):
        await driver.read("missing")
    with pytest.raises(EnvPermissionDenied):
        await driver.write("/readonly/x", b"")
    assert driver.available, "an error the host sent back is not a broken connection"


async def test_a_subdirectory_is_made_there(monkeypatch: pytest.MonkeyPatch) -> None:
    remote = FakeRemote()
    driver = await _driver(monkeypatch, remote)

    sub = await driver.derive_subdir("x/y")

    assert "/work/x/y" in remote.dirs
    assert sub.workdir == PurePosixPath("/work/x/y")


async def test_a_workdir_not_on_the_host_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reach(monkeypatch)
    driver = MachineEnvDriver(SSHMachine("box"), PurePosixPath("/nowhere"))

    with pytest.raises(EnvUnavailable, match="/nowhere"):
        await driver.probe()
    assert not driver.available


async def test_closing_lets_go_of_the_connection_and_kills_what_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    remote = FakeRemote(answer=lambda argv, cwd: None)
    driver = await _driver(monkeypatch, remote)
    running = asyncio.ensure_future(driver.exec(["serve"], timeout=0))
    await until(lambda: bool(remote.commands))

    await driver.close()

    with pytest.raises(EnvError, match="closed"):
        await running
    assert remote.closes == 1
    assert [one.signals for one in remote.execs] == [[signal.SIGKILL]]
    assert not driver.available
