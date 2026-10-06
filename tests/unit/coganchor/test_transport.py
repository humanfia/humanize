"""Reading a target, and the commands that reach one: no process is started and no socket opened."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from hmz.coganchor import rendezvous, transport
from hmz.coganchor.proto import Channel
from hmz.coganchor.rendezvous import Meeting
from hmz.coganchor.transport import (
    APPLE,
    CONTAINER_CACHE,
    CONTAINER_MIRRORS,
    PYTHON_CANDIDATES,
    REMOTE_CACHE,
    REMOTE_MIRRORS,
    Endpoint,
    Road,
    Target,
    Transport,
    python_command,
    serve_line,
    ssh_flags,
)

# --------------------------------------------------------------------------- targets


@pytest.mark.parametrize(
    ("spec", "target"),
    [
        ("local", Target("local")),
        ("local:/srv/w", Target("local", path="/srv/w")),
        ("ssh://box", Target("ssh", host="box")),
        ("ssh://me@box:2222", Target("ssh", host="me@box", port=2222)),
        ("ssh://[::1]:22", Target("ssh", host="[::1]", port=22)),
        (
            "ssh://box?IdentityFile=/k&F=/cfg",
            Target("ssh", host="box", options=(("IdentityFile", "/k"), ("F", "/cfg"))),
        ),
        (
            "ssh://box?ProxyJump=a%20b",
            Target("ssh", host="box", options=(("ProxyJump", "a b"),)),
        ),
        ("docker://c", Target("docker", host="c")),
        ("docker://c@local", Target("docker", host="c")),
        ("docker://c@context:far", Target("docker", host="c", path="context:far")),
        ("docker://c@tcp://h:2376", Target("docker", host="c", path="tcp://h:2376")),
        (f"{APPLE}://box", Target(APPLE, host="box")),
        ("tcp://h:9", Target("tcp", host="h", port=9)),
        ("tcp://::1:9", Target("tcp", host="::1", port=9)),
        ("peer://t@b:7", Target("peer", host="b", port=7, path="t")),
    ],
)
def test_a_target_reads_as_what_it_names(spec: str, target: Target) -> None:
    assert Target.parse(spec) == target


@pytest.mark.parametrize(
    "spec",
    [
        "local",
        "local:/srv/w",
        "ssh://box",
        "ssh://me@box:2222",
        "ssh://box?IdentityFile=/k/id&F=/cfg",
        "ssh://box?ProxyJump=a%20b",
        "docker://c",
        "docker://c@context:far",
        "docker://c@unix:///var/run/d.sock",
        "docker://c@tcp://h:2376?tls=/certs",
        f"{APPLE}://box",
        "tcp://h:9",
        "peer://t@b:7",
    ],
)
def test_a_target_describes_itself_as_it_was_spelled(spec: str) -> None:
    assert Target.parse(spec).describe() == spec
    assert Target.parse(Target.parse(spec).describe()) == Target.parse(spec)


@pytest.mark.parametrize(
    "spec",
    [
        "",
        "box",
        "http://box",
        "tcp://h",
        "tcp://:9",
        "tcp://h:port",
        "docker://",
        "docker://@local",
        "docker://c@",
        "docker://c@nowhere",
        f"{APPLE}://",
        f"{APPLE}://a@b",
        f"{APPLE}://a/b",
        "peer://b:7",
        "peer://t@b",
        "ssh://box?novalue",
        "ssh://box?Key=",
        "ssh://box?1bad=x",
        'ssh://box?Key=a"b',
        "ssh://box?Key=a%0Ab",
    ],
)
def test_a_misspelled_target_is_refused(spec: str) -> None:
    with pytest.raises(ValueError, match=r"target|endpoint|meeting"):
        Target.parse(spec)


def test_a_peer_target_names_its_meeting() -> None:
    assert Target.parse("peer://t@b:7").meeting == Meeting("t", "b", 7)


def test_a_docker_target_names_its_daemon() -> None:
    assert Target.parse("docker://c@context:far").endpoint == Endpoint(context="far")
    assert Target.parse("docker://c").endpoint == Endpoint()


@pytest.mark.parametrize(
    ("spec", "asked"), [("ssh://box", "meeting"), ("tcp://h:1", "endpoint")]
)
def test_a_target_has_only_its_own_kind_of_detail(spec: str, asked: str) -> None:
    with pytest.raises(ValueError, match="is not a"):
        getattr(Target.parse(spec), asked)


# ------------------------------------------------------------------------- endpoints


@pytest.mark.parametrize(
    ("spec", "endpoint"),
    [
        ("", Endpoint()),
        ("local", Endpoint()),
        ("context:far", Endpoint(context="far")),
        ("unix:///var/run/d.sock", Endpoint(host="unix:///var/run/d.sock")),
        ("tcp://h:2375", Endpoint(host="tcp://h:2375")),
        ("tcp://h:2376?tls=/certs", Endpoint(host="tcp://h:2376", certs="/certs")),
        ("ssh://me@h:22", Endpoint(host="ssh://me@h:22")),
        (
            "ssh://h?IdentityFile=/k",
            Endpoint(host="ssh://h", options=(("IdentityFile", "/k"),)),
        ),
    ],
)
def test_an_endpoint_reads_as_the_daemon_it_names(
    spec: str, endpoint: Endpoint
) -> None:
    assert Endpoint.parse(spec) == endpoint


@pytest.mark.parametrize(
    "spec",
    [
        "context:",
        "unix://relative",
        "tcp://h",
        "tcp://h:2376?tls=relative",
        "ssh://",
        "ssh://h/path",
        "ssh://h?bad",
        "npipe:////./pipe/docker",
    ],
)
def test_a_misspelled_endpoint_is_refused(spec: str) -> None:
    with pytest.raises(ValueError, match="unsupported docker endpoint"):
        Endpoint.parse(spec)


@pytest.mark.parametrize(
    "spec",
    [
        "local",
        "context:far",
        "unix:///s",
        "tcp://h:1",
        "tcp://h:1?tls=/c",
        "ssh://h?Port=2",
    ],
)
def test_an_endpoint_spells_itself_back(spec: str) -> None:
    assert str(Endpoint.parse(spec)) == spec


@pytest.mark.parametrize(
    ("spec", "environ", "here"),
    [
        ("local", None, True),
        ("local", "unix:///other.sock", True),
        ("local", "tcp://far:2375", False),
        ("unix:///s", "tcp://far:2375", True),
        ("tcp://h:1", None, False),
        ("ssh://h", None, False),
        ("context:x", None, False),
    ],
)
def test_an_endpoint_is_here_only_when_it_sees_these_files(
    spec: str, environ: str | None, here: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    if environ is None:
        monkeypatch.delenv("DOCKER_HOST", raising=False)
    else:
        monkeypatch.setenv("DOCKER_HOST", environ)
    assert Endpoint.parse(spec).here is here


def test_the_default_daemon_is_left_to_find_itself() -> None:
    assert Endpoint().docker("ps") == ["docker", "ps"]


def test_another_daemon_is_named_with_the_ambient_settings_taken_off() -> None:
    line = Endpoint.parse("tcp://h:2376?tls=/c").docker("ps", "-a")
    assert line[0] == "env"
    taken = {line[at + 1] for at, word in enumerate(line) if word == "-u"}
    assert {"DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY"} <= taken
    assert line[line.index("docker") :] == [
        "docker",
        "--host",
        "tcp://h:2376",
        "--tlsverify",
        "--tlscacert",
        "/c/ca.pem",
        "--tlscert",
        "/c/cert.pem",
        "--tlskey",
        "/c/key.pem",
        "ps",
        "-a",
    ]


def test_a_context_is_named_as_a_context() -> None:
    line = Endpoint(context="far").docker("ps")
    assert line[line.index("docker") :] == ["docker", "--context", "far", "ps"]


def test_an_ssh_daemon_with_options_is_dialled_through_an_ssh_told_them() -> None:
    line = Endpoint.parse("ssh://h?IdentityFile=/k").docker("ps")
    path = next(word for word in line if word.startswith("PATH="))
    shim = Path(path.removeprefix("PATH=").split(os.pathsep)[0])
    script = (shim / "ssh").read_text()
    assert script.startswith("#!/bin/sh")
    assert "exec ssh -o IdentityFile=/k" in script
    assert os.access(shim / "ssh", os.X_OK)
    assert Endpoint.parse("ssh://h?IdentityFile=/k").docker("ps") == line


# ------------------------------------------------------------------------- ssh flags


@pytest.mark.parametrize(
    ("options", "flags"),
    [
        ((), ()),
        ((("F", "/cfg"),), ("-F", "/cfg")),
        ((("Port", "2"), ("User", "me")), ("-o", "Port=2", "-o", "User=me")),
        ((("ProxyCommand", "nc %h %p"),), ("-o", 'ProxyCommand="nc %h %p"')),
    ],
)
def test_ssh_options_become_flags_in_order(
    options: tuple[tuple[str, str], ...], flags: tuple[str, ...]
) -> None:
    assert ssh_flags(options) == flags


# -------------------------------------------------------------------- python command


def test_finding_python_runs_the_interpreter_found() -> None:
    line = python_command(["-c", "pass"])
    assert line[:2] == ["/bin/sh", "-c"]
    assert line[3:] == ["humanize", "-c", "pass"]
    script = line[2]
    assert all(one in script for one in PYTHON_CANDIDATES)
    assert 'exec "$py" "$@"' in script
    assert "sys.version_info < (3, 12)" in script
    assert "exit 127" in script


def test_running_an_archive_touches_it_first() -> None:
    script = python_command(["serve"], bundle="$HOME/x.pyz")[2]
    assert script.startswith('touch -c "$HOME/x.pyz"')
    assert 'exec "$py" "$HOME/x.pyz" "$@"' in script


def test_settings_are_exported_and_made_before_the_search() -> None:
    script = python_command([], setting=(("HUMANIZE_SHADOW", "$HOME/m"),))[2]
    assert script.startswith(
        'HUMANIZE_SHADOW="$HOME/m"; export HUMANIZE_SHADOW; mkdir -p "$HUMANIZE_SHADOW"'
    )


# ----------------------------------------------------------------------------- roads


def test_a_local_road_runs_a_command_as_it_is() -> None:
    road = Road.to(Target.parse("local"))
    assert road.line(["ls", "a b"]) == ["ls", "a b"]
    assert (road.cache, road.mirrors) == ("", "")


def test_an_ssh_road_quotes_one_line_for_the_far_shell() -> None:
    road = Road.to(Target.parse("ssh://me@box:2201?IdentityFile=/k"))
    prefix = list(road.prefix)
    assert prefix[0] == "ssh"
    assert prefix[-3:] == ["-p", "2201", "me@box"]
    # The target's own options come before humanize's, so that ssh keeps them.
    assert prefix.index("IdentityFile=/k") < prefix.index("-T")
    line = road.line(["ls", "a b", "$HOME"])
    assert line[: len(prefix)] == prefix
    assert shlex.split(line[-1]) == ["exec", "ls", "a b", "$HOME"]
    assert (road.cache, road.mirrors) == (REMOTE_CACHE, REMOTE_MIRRORS)
    assert road.mirror("abc") == f"{REMOTE_MIRRORS}/abc"


@pytest.mark.parametrize(
    ("spec", "prefix"),
    [
        ("docker://c", ["docker", "exec", "-i", "c"]),
        (f"{APPLE}://c", ["container", "exec", "-i", "c"]),
    ],
)
def test_a_container_road_carries_argv_straight_through(
    spec: str, prefix: list[str]
) -> None:
    road = Road.to(Target.parse(spec))
    assert road.line(["ls", "a b"]) == [*prefix, "ls", "a b"]
    assert (road.cache, road.mirrors) == (CONTAINER_CACHE, CONTAINER_MIRRORS)


def test_a_container_on_another_daemon_is_reached_through_it() -> None:
    road = Road.to(Target.parse("docker://c@context:far"))
    assert road.line(["ls"])[-6:] == ["--context", "far", "exec", "-i", "c", "ls"]


@pytest.mark.parametrize("spec", ["tcp://h:1", "peer://t@h:1"])
def test_nothing_is_started_on_the_far_side_of_a_listener(spec: str) -> None:
    with pytest.raises(ValueError, match="nothing is started"):
        Road.to(Target.parse(spec))


def test_humanize_runs_locally_as_this_interpreter() -> None:
    line = Road.to(Target.parse("local")).hmz(["internal", "anchor"])
    assert line[0] == sys.executable
    assert line[-2:] == ["internal", "anchor"]


class Ran:
    """What `subprocess.run` was asked, answering with a status of its own."""

    def __init__(self, code: int = 0, err: bytes = b"") -> None:
        self.code, self.err = code, err
        self.asked: list[tuple[list[str], bytes]] = []

    def __call__(
        self, argv: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[bytes]:
        self.asked.append((argv, kwargs.get("input") or b""))
        return subprocess.CompletedProcess(argv, self.code, b"", self.err)


@pytest.fixture
def archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    held = tmp_path / "humanize.pyz"
    held.write_bytes(b"PK-archive")
    monkeypatch.setattr(transport, "bundled", lambda: (held, "0123456789abcdef"))
    return held


def test_the_archive_is_pushed_once_per_machine(
    archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = Ran()
    monkeypatch.setattr(subprocess, "run", ran)
    road = Road.to(Target.parse("ssh://pushed-once"))
    road.forget()
    where = road.installed()
    assert where == f"{REMOTE_CACHE}/humanize-0123456789abcdef.pyz"
    assert road.installed() == where
    assert len(ran.asked) == 1
    argv, fed = ran.asked[0]
    assert argv[0] == "ssh"
    assert fed == b"PK-archive"
    road.forget()
    road.installed()
    assert len(ran.asked) == 2
    road.forget()


def test_humanize_far_away_runs_the_installed_archive(
    archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", Ran())
    road = Road.to(Target.parse("docker://far-hmz"))
    road.forget()
    line = road.hmz(["internal", "anchor", "serve"], setting=(("A", "/b"),))
    assert line[:4] == ["docker", "exec", "-i", "far-hmz"]
    assert line[-4:] == ["humanize", "internal", "anchor", "serve"]
    assert f"{CONTAINER_CACHE}/humanize-0123456789abcdef.pyz" in line[-5]
    assert 'A="/b"; export A' in line[-5]
    road.forget()


def test_an_archive_that_would_not_install_says_why(
    archive: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", Ran(1, b"disk full\n"))
    road = Road.to(Target.parse("ssh://refuses"))
    road.forget()
    with pytest.raises(
        ConnectionError, match="could not install humanize on ssh://refuses: disk full"
    ):
        road.installed()


def test_an_archive_that_cannot_be_built_is_a_connection_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken() -> tuple[Path, str]:
        raise OSError("read-only")

    monkeypatch.setattr(transport, "bundled", broken)
    with pytest.raises(ConnectionError, match="read-only"):
        Road.to(Target.parse("ssh://unbuildable")).installed()


def test_a_road_runs_a_short_command_with_its_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran = Ran(3)
    monkeypatch.setattr(subprocess, "run", ran)
    done = Road.to(Target.parse("docker://c")).run(["cat"], b"in")
    assert done.returncode == 3
    assert ran.asked == [(["docker", "exec", "-i", "c", "cat"], b"in")]


# -------------------------------------------------------------------- serving lines


@pytest.mark.parametrize(
    ("meeting", "how"),
    [(None, ["--stdio"]), (Meeting("t", "h", 1), ["--peer", "t@h:1"])],
)
def test_the_serving_line_names_its_exports(
    meeting: Meeting | None, how: list[str]
) -> None:
    line = serve_line(Target.parse("local"), ["/a", "/b:/c"], meeting=meeting)
    assert line[0] == sys.executable
    at = line.index("internal")
    assert line[at:] == [
        "internal",
        "anchor",
        "serve",
        *how,
        "--export",
        "/a",
        "--export",
        "/b:/c",
    ]


def test_a_peer_target_is_met_at_its_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    met: list[tuple[Meeting, str]] = []

    class Sock:
        def makefile(self, mode: str) -> Any:
            return None

    def dial(meeting: Meeting, role: str) -> Sock:
        met.append((meeting, role))
        return Sock()

    monkeypatch.setattr(rendezvous, "dial", dial)
    link = transport.connect(Target.parse("peer://t@b:7"), [])
    assert isinstance(link.channel, Channel)
    assert link.process is None
    assert met == [(Meeting("t", "b", 7), rendezvous.ANCHOR)]


class Child:
    def __init__(self, *, stubborn: bool) -> None:
        self.stubborn = stubborn
        self.calls: list[str] = []

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        self.calls.append("terminate")

    def kill(self) -> None:
        self.calls.append("kill")

    def wait(self, timeout: float | None = None) -> int:
        self.calls.append("wait")
        if self.stubborn and timeout is not None:
            raise subprocess.TimeoutExpired("x", timeout)
        return 0


class Closing:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("stubborn", "calls"),
    [(False, ["terminate", "wait"]), (True, ["terminate", "wait", "kill", "wait"])],
)
def test_closing_a_transport_puts_its_process_down(
    stubborn: bool, calls: list[str]
) -> None:
    channel, child = Closing(), Child(stubborn=stubborn)
    Transport(channel, child).close()  # pyright: ignore[reportArgumentType]
    assert channel.closed
    assert child.calls == calls
