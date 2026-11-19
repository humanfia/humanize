"""Reading a target, and the commands that reach one: no process is started and no socket opened."""

from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

import pytest

from hmz.coganchor import binary, transport
from hmz.coganchor.rendezvous import Meeting
from hmz.coganchor.transport import (
    APPLE,
    CONTAINER_CACHE,
    CONTAINER_MIRRORS,
    REMOTE_CACHE,
    REMOTE_MIRRORS,
    SLURM,
    Endpoint,
    Road,
    Target,
    Transport,
    awaiting,
    coganchor_command,
    idling,
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
        (
            "docker://c?user=1000",
            Target("docker", host="c", options=(("user", "1000"),)),
        ),
        (
            "docker://c?user=1000:100&env=A=b%20c&exec=/w&exec=64@context:far",
            Target(
                "docker",
                host="c",
                path="context:far",
                options=(
                    ("user", "1000:100"),
                    ("env", "A=b c"),
                    ("exec", "/w"),
                    ("exec", "64"),
                ),
            ),
        ),
        (
            "docker://c?env=MAIL=a%40b&env=EMPTY=@local",
            Target(
                "docker", host="c", options=(("env", "MAIL=a@b"), ("env", "EMPTY="))
            ),
        ),
        (f"{APPLE}://box", Target(APPLE, host="box")),
        (f"{SLURM}://42", Target(SLURM, host="42")),
        (
            f"{SLURM}://42?python=/opt/py%20b",
            Target(SLURM, host="42", path="/opt/py b"),
        ),
        (f"{SLURM}://42?python=~/py", Target(SLURM, host="42", path="~/py")),
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
        "docker://c?user=1000:100&env=A=b%20c&exec=/w&exec=64@context:far",
        "docker://c?env=MAIL=a%40b&exec=a%2Bb%26c@ssh://me@h?IdentityFile=/k",
        f"{APPLE}://box",
        f"{SLURM}://42",
        f"{SLURM}://42?python=/opt/py%20b",
        f"{SLURM}://42?python=~/py",
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
        "docker://c?novalue",
        "docker://c?shell=/bin/sh",
        "docker://c?user=me",
        "docker://c?user=",
        "docker://c?user=1:x",
        "docker://c?user=1&user=2",
        "docker://c?env=A",
        "docker://c?env=1A=x",
        "docker://c?env=A=a%0Ab",
        "docker://c?exec=",
        "docker://c?exec=a%00b",
        f"{APPLE}://",
        f"{APPLE}://a@b",
        f"{APPLE}://a/b",
        f"{SLURM}://",
        f"{SLURM}://job",
        f"{SLURM}://42@n1",
        f"{SLURM}://42?python=py",
        f"{SLURM}://42?other=/x",
        f"{SLURM}://42?python=/a&python=/b",
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
    assert Target.parse("docker://c?user=1@context:far").endpoint == Endpoint(
        context="far"
    )


def test_a_docker_option_that_is_not_one_is_named() -> None:
    with pytest.raises(ValueError, match="user='me' is not a docker exec option"):
        Target.parse("docker://c?user=me")


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


# ----------------------------------------------------------------- the coganchor line


def test_settings_are_exported_and_made_before_the_program_runs() -> None:
    script = coganchor_command(
        ["anchor"], "$HOME/c", setting=(("HUMANIZE_SHADOW", "$HOME/m"),)
    )[2]
    assert script.startswith(
        'HUMANIZE_SHADOW="$HOME/m"; export HUMANIZE_SHADOW; mkdir -p "$HUMANIZE_SHADOW"'
    )
    assert "[ -O" not in script


def test_directories_owned_are_checked_and_closed_before_the_settings() -> None:
    script = coganchor_command(
        ["anchor"],
        "/tmp/c-7/coganchor-x",
        setting=(("HUMANIZE_SHADOW", "/tmp/m-7/abc"),),
        owned=("/tmp/c-7", "/tmp/m-7"),
    )[2]
    assert script.startswith('mkdir -p "/tmp/c-7" && [ -d "/tmp/c-7" ]')
    for path in ("/tmp/c-7", "/tmp/m-7"):
        assert (
            f'[ ! -L "{path}" ] && [ -O "{path}" ] && chmod 700 "{path}" ||' in script
        )
        assert (
            f'echo "Humanize: {path} is not a directory this user owns" >&2' in script
        )
    assert (
        script.index('[ -O "/tmp/c-7" ]')
        < script.index('[ -O "/tmp/m-7" ]')
        < script.index("HUMANIZE_SHADOW=")
        < script.index("touch -c")
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
    # The target's own options come before Humanize's, so that ssh keeps them.
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
    assert not road.owned


def test_a_container_road_runs_as_its_user_with_its_variables_under_its_wrapper() -> (
    None
):
    road = Road.to(
        Target.parse("docker://c?user=1000:100&env=A=b%20c&exec=/w&exec=64@context:far")
    )
    assert road.line(["ls", "a b"])[-14:] == [
        "docker",
        "--context",
        "far",
        "exec",
        "-i",
        "-u",
        "1000:100",
        "-e",
        "A=b c",
        "c",
        "/w",
        "64",
        "ls",
        "a b",
    ]
    assert (road.cache, road.mirrors) == (
        f"{CONTAINER_CACHE}-1000",
        f"{CONTAINER_MIRRORS}-1000",
    )
    assert road.owned
    assert road.mirror("abc") == f"{CONTAINER_MIRRORS}-1000/abc"


def test_a_container_road_naming_no_user_keeps_the_containers_directories() -> None:
    road = Road.to(Target.parse("docker://c?env=A=1&exec=/w"))
    assert road.line(["ls"]) == ["docker", "exec", "-i", "-e", "A=1", "c", "/w", "ls"]
    assert (road.cache, road.mirrors) == (CONTAINER_CACHE, CONTAINER_MIRRORS)
    assert not road.owned


def test_a_slurm_road_is_a_step_of_the_job_carrying_argv_straight_through() -> None:
    road = Road.to(Target.parse(f"{SLURM}://42?python=/opt/py"))
    line = road.line(["ls", "a b"])
    assert line[:3] == ["srun", "--jobid=42", "--overlap"]
    assert "--export=HOME,USER" in line
    assert "--chdir=/" in line
    assert line[-2:] == ["ls", "a b"]
    assert (road.cache, road.mirrors) == (REMOTE_CACHE, REMOTE_MIRRORS)
    assert "/opt/py" not in line


def test_a_container_on_another_daemon_is_reached_through_it() -> None:
    road = Road.to(Target.parse("docker://c@context:far"))
    assert road.line(["ls"])[-6:] == ["--context", "far", "exec", "-i", "c", "ls"]


@pytest.mark.parametrize("spec", ["tcp://h:1", "peer://t@h:1"])
def test_nothing_is_started_on_the_far_side_of_a_listener(spec: str) -> None:
    with pytest.raises(ValueError, match="nothing is started"):
        Road.to(Target.parse(spec))


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


def test_a_road_runs_a_short_command_with_its_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran = Ran(3)
    monkeypatch.setattr(subprocess, "run", ran)
    done = Road.to(Target.parse("docker://c")).run(["cat"], b"in")
    assert done.returncode == 3
    assert ran.asked == [(["docker", "exec", "-i", "c", "cat"], b"in")]


class Uname(Ran):
    """`subprocess.run`, with the target answering `uname -sm` as `said`."""

    def __init__(self, said: bytes = b"Linux x86_64\n", code: int = 0) -> None:
        super().__init__(code)
        self.said = said

    def __call__(
        self, argv: list[str], **kwargs: Any
    ) -> subprocess.CompletedProcess[bytes]:
        done = super().__call__(argv, **kwargs)
        if "exec uname -sm" in argv[-1]:
            return subprocess.CompletedProcess(argv, 0, self.said, b"")
        return done


@pytest.fixture
def build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """`coganchor` chosen, on a machine that is Linux on x86-64 as the targets below are."""
    import platform

    program = tmp_path / "coganchor"
    program.write_bytes(b"\x7fELF coganchor")
    monkeypatch.setenv(binary.VARIABLE, str(program))
    monkeypatch.setenv(binary.BINARIES, "")
    monkeypatch.delenv(binary.BINARIES)
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    return program


def _named(program: Path) -> str:
    return f"coganchor-{hashlib.sha256(program.read_bytes()).hexdigest()[:16]}"


# -------------------------------------------------------------------- serving lines


@pytest.mark.parametrize(
    ("meeting", "how"),
    [(None, ["--stdio"]), (Meeting("t", "h", 1), ["--peer", "t@h:1"])],
)
def test_the_serving_line_names_its_exports(
    build: Path, meeting: Meeting | None, how: list[str]
) -> None:
    line = serve_line(Target.parse("local"), ["/a", "/b:/c"], meeting=meeting)
    assert line == [str(build), "anchor", *how, "--export", "/a", "--export", "/b:/c"]


def test_a_peer_target_is_met_by_coganchor_and_not_by_this_process() -> None:
    with pytest.raises(ConnectionError, match="a meeting for one session"):
        transport.connect(Target.parse("peer://t@b:7"), [])


def test_an_ipv6_listener_is_dialled_without_the_brackets_it_is_spelled_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dialled: list[tuple[str, int]] = []

    def refused(address: tuple[str, int], **_: Any) -> Any:
        dialled.append(address)
        raise ConnectionRefusedError("nothing listens in a unit test")

    monkeypatch.setattr("socket.create_connection", refused)
    target = Target.parse("tcp://[::1]:7000")
    with pytest.raises(ConnectionRefusedError):
        transport.connect(target, [])
    assert dialled == [("::1", 7000)]
    assert target.describe() == "tcp://[::1]:7000"


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


# ----------------------------------------------------------------------- coganchor


def test_coganchor_is_shipped_once_per_machine_named_by_its_digest(
    build: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = Uname()
    monkeypatch.setattr(subprocess, "run", ran)
    road = Road.to(Target.parse("docker://shipped-once"))
    road.forget()

    line = road.hmz(["internal", "anchor", "serve", "--stdio", "--export", "/w"])

    name = _named(build)
    (probe, _), (install, fed) = ran.asked
    assert probe == [
        "docker",
        "exec",
        "-i",
        "shipped-once",
        "/bin/sh",
        "-c",
        "exec uname -sm",
    ]
    assert fed == build.read_bytes()
    script = install[-1]
    assert f'c="{CONTAINER_CACHE}"' in script
    assert f'p="$c/{name}"' in script
    assert 't="$p.$$"' in script
    assert f"-eq {len(fed)} ]" in script
    assert 'chmod 700 "$t"' in script
    assert '-name "coganchor-*" -o -name "humanize-*.pyz*"' in script
    assert "-mtime +13" in script
    assert line[:4] == ["docker", "exec", "-i", "shipped-once"]
    assert line[-5:] == ["coganchor", "anchor", "--stdio", "--export", "/w"]
    assert f'exec "{CONTAINER_CACHE}/{name}" "$@"' in line[-6]
    assert f'touch -c "{CONTAINER_CACHE}/{name}"' in line[-6]

    road.hmz(["internal", "anchor", "serve", "--stdio"])
    assert len(ran.asked) == 2
    road.forget()
    road.shipped()
    assert len(ran.asked) == 4
    road.forget()


def test_a_harness_elsewhere_runs_coganchor_cog_with_its_settings(
    build: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", Uname())
    road = Road.to(Target.parse("ssh://cog-far"))
    road.forget()

    line = road.hmz(
        ["internal", "anchor", "--target=local", "claude"],
        setting=(("HUMANIZE_SHADOW", f"{REMOTE_MIRRORS}/m"),),
    )

    said = shlex.split(line[-1])
    assert said[:3] == ["exec", "/bin/sh", "-c"]
    assert said[4:] == ["coganchor", "cog", "--target=local", "claude"]
    assert f'HUMANIZE_SHADOW="{REMOTE_MIRRORS}/m"; export HUMANIZE_SHADOW' in said[3]
    assert f'"{REMOTE_CACHE}/{_named(build)}"' in said[3]
    road.forget()


def test_each_user_of_a_container_is_shipped_coganchor_into_their_own_directory(
    build: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = Uname()
    monkeypatch.setattr(subprocess, "run", ran)
    road = Road.to(Target.parse("docker://owned-box?user=1000"))
    road.forget()

    line = road.hmz(["internal", "anchor", "serve", "--stdio"])

    install = ran.asked[1][0]
    assert install[:6] == ["docker", "exec", "-i", "-u", "1000", "owned-box"]
    assert f'[ -O "{CONTAINER_CACHE}-1000" ]' in install[-1]
    assert f'[ -O "{CONTAINER_CACHE}-1000" ]' in line[-4]
    assert CONTAINER_MIRRORS not in line[-4]
    name = _named(build)
    assert road.shipped() == f"{CONTAINER_CACHE}-1000/{name}"
    other = Road.to(Target.parse("docker://owned-box?user=1001:1001"))
    assert other.shipped() == f"{CONTAINER_CACHE}-1001/{name}"
    asked = len(ran.asked)
    # A container replaced is replaced for every user a target of it named.
    Road.to(Target.parse("docker://owned-box")).forget()
    road.shipped()
    other.shipped()
    assert len(ran.asked) == asked + 4
    mirror = road.mirror("abc")
    harness = road.hmz(["internal", "anchor"], setting=(("HUMANIZE_SHADOW", mirror),))
    assert f'[ -O "{CONTAINER_CACHE}-1000" ]' in harness[-3]
    assert f'[ -O "{CONTAINER_MIRRORS}-1000" ]' in harness[-3]
    road.forget()


def test_a_machine_nothing_is_built_for_is_refused_by_name(
    build: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran = Uname(b"Linux riscv64\n")
    monkeypatch.setattr(subprocess, "run", ran)
    road = Road.to(Target.parse("ssh://unbuilt"))
    road.forget()

    with pytest.raises(
        ConnectionError, match="no coganchor is built for Linux riscv64"
    ):
        road.hmz(["internal", "anchor", "serve", "--stdio"])
    assert len(ran.asked) == 1
    road.forget()


def test_a_machine_that_cannot_be_asked_what_it_is_says_why(
    build: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", Ran(255, b"Connection refused\n"))
    road = Road.to(Target.parse("ssh://unasked"))
    road.forget()

    with pytest.raises(ConnectionError, match=r"ssh://unasked.*Connection refused"):
        road.shipped()


def test_coganchor_that_would_not_install_says_why(
    build: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Full(Uname):
        def __call__(
            self, argv: list[str], **kwargs: Any
        ) -> subprocess.CompletedProcess[bytes]:
            done = super().__call__(argv, **kwargs)
            if kwargs.get("input"):
                return subprocess.CompletedProcess(argv, 1, b"", b"disk full\n")
            return done

    monkeypatch.setattr(subprocess, "run", Full())
    road = Road.to(Target.parse("ssh://full"))
    road.forget()

    with pytest.raises(
        ConnectionError, match="could not install Humanize on ssh://full: disk full"
    ):
        road.shipped()
    road.forget()


def test_a_slurm_road_ignores_its_python_where_coganchor_runs(
    build: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(subprocess, "run", Uname())
    road = Road.to(Target.parse(f"{SLURM}://4343?python=/opt/py"))
    road.forget()

    line = road.hmz(["internal", "anchor", "serve", "--stdio"])

    assert line[:2] == ["srun", "--jobid=4343"]
    assert "/opt/py" not in " ".join(line)
    assert line[-2:] == ["anchor", "--stdio"]
    road.forget()


def test_coganchor_runs_locally_as_this_machines_build(build: Path) -> None:
    line = serve_line(Target.parse("local"), ["/a"])

    assert line == [str(build), "anchor", "--stdio", "--export", "/a"]
    assert os.environ[binary.BINARIES] == str(binary.shelf())


def test_coganchor_refuses_a_line_it_does_not_carry_out(build: Path) -> None:
    with pytest.raises(ValueError, match="hmz internal hook"):
        Road.to(Target.parse("local")).hmz(["internal", "hook"])
    with pytest.raises(ValueError, match="hmz web"):
        Road.to(Target.parse("local")).hmz(["web"])


def test_coganchor_line_touches_and_runs_the_program() -> None:
    line = coganchor_command(
        ["anchor", "--stdio"], "$HOME/c/coganchor-x", setting=(("A", "/b"),)
    )

    assert line[:2] == ["/bin/sh", "-c"]
    assert line[3:] == ["coganchor", "anchor", "--stdio"]
    assert line[2].index('A="/b"') < line[2].index('touch -c "$HOME/c/coganchor-x"')
    assert line[2].endswith('exec "$HOME/c/coganchor-x" "$@"')


def test_a_container_idles_without_python() -> None:
    assert idling() == ["/bin/sh", "-c", "exec sleep 2147483647"]


def test_a_job_waits_for_the_build_its_node_asks_for(
    build: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    other = tmp_path / "aarch64"
    other.write_bytes(b"another")

    def packaged(system: str, machine: str) -> Path | None:
        return other if binary.named(system, machine) == "linux-aarch64" else None

    monkeypatch.setattr(binary, "packaged", packaged)

    script = awaiting(REMOTE_CACHE)

    assert (
        f'"Linux x86_64"|"Linux amd64") p="{REMOTE_CACHE}/{_named(build)}";;' in script
    )
    assert (
        f'"Linux aarch64"|"Linux arm64") p="{REMOTE_CACHE}/{_named(other)}";;'
    ) in script
    assert "Darwin" not in script
    assert script.endswith('while [ ! -f "$p" ]; do sleep 1; done')
