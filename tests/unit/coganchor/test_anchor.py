"""The settings a session runs under, and the calls taking one -- the target never reached."""

from __future__ import annotations

import errno
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import anchor, elsewhere, remote, transport
from hmz.coganchor.anchor import (
    UNMIRRORED,
    AnchorConfig,
    NotInstalled,
    Unmirrored,
    check,
    connect,
    drive,
)
from hmz.coganchor.fence import Fence
from hmz.coganchor.places import AFAR, NATIVE_CLI, SUPERVISED
from hmz.coganchor.transport import Target
from tests.unit.coganchor.doubles_u8 import Exec

if TYPE_CHECKING:
    from collections.abc import Callable

# ------------------------------------------------------------------------ the settings


def test_the_defaults_are_this_directory_supervised_here() -> None:
    config = AnchorConfig()
    assert (config.target, config.harness, config.net) == ("local", "local", "local")
    assert config.capabilities == frozenset({SUPERVISED})


@pytest.mark.parametrize(
    ("settings", "capabilities"),
    [
        ({"native": True, "target": "ssh://box"}, {NATIVE_CLI}),
        ({"target": "ssh://box"}, {SUPERVISED}),
        ({"target": "ssh://box", "harness": "same"}, {SUPERVISED, AFAR}),
        ({"harness": "docker://c"}, {SUPERVISED, AFAR}),
        ({"harness": "same"}, {SUPERVISED}),
    ],
)
def test_a_session_says_how_it_is_reached(
    settings: dict[str, Any], capabilities: set[str]
) -> None:
    assert AnchorConfig(**settings).capabilities == capabilities


PATH_BY_PATH = Fence(write=("/w",))
LEVELLED = Fence(write=("/w",), scopes=("all", "read", "read"))
CUT = Fence(write=("/w",), scopes=("all", "read", "read"), online=False)


@pytest.mark.parametrize(
    ("settings", "says"),
    [
        ({"target": "nowhere"}, "unsupported target"),
        ({"harness": "nowhere"}, "unsupported target"),
        ({"native": True, "harness": "ssh://box"}, "native session has no harness"),
        ({"harness": "same", "target": "peer://t@h:1"}, "peer:// target"),
        ({"net": "both"}, "unsupported net"),
        ({"redirects": (("/a", "b"),)}, "unsupported redirect"),
        ({"redirects": (("a", "/b"),)}, "unsupported redirect"),
        ({"hushes": ("",)}, "unsupported hush"),
        ({"hushes": ("A=B",)}, "unsupported hush"),
        ({"projects": (("", "/c"),)}, "unsupported projection"),
        ({"projects": (("A=B", "/c"),)}, "unsupported projection"),
        ({"projects": (("A", "c"),)}, "unsupported projection"),
        ({"carries": (("skills", "s"),)}, "expected an absolute path"),
        ({"carries": (("/skills", ""),)}, "inside the workspace"),
        ({"carries": (("/skills", "/s"),)}, "inside the workspace"),
        ({"carries": (("/skills", "a/../../s"),)}, "inside the workspace"),
        ({"fence": PATH_BY_PATH}, "drawn path by path"),
        ({"fence": LEVELLED, "harness": "ssh://box"}, "cannot hold a harness"),
        ({"fence": CUT, "net": "remote"}, "past it"),
    ],
)
def test_what_the_command_line_refuses_the_settings_refuse(
    settings: dict[str, Any], says: str
) -> None:
    with pytest.raises(ValueError, match=says):
        AnchorConfig(**settings)


@pytest.mark.parametrize(
    "settings",
    [
        {"redirects": (("/a", "/b"),), "hushes": ("OPENAI_API_KEY",)},
        {
            "projects": (("CODEX_HOME", "/c"),),
            "carries": (("/skills", ".claude/skills"),),
        },
        {"fence": Fence(write=("/",))},
        {"fence": LEVELLED},
        {"fence": CUT},
        {"native": True, "target": "ssh://box", "harness": "local"},
        {"harness": "ssh://h", "target": "docker://c"},
    ],
)
def test_what_is_well_written_is_taken(settings: dict[str, Any]) -> None:
    AnchorConfig(**settings)


# ------------------------------------------------------------------------ the command


def test_the_command_is_humanize_anchoring_the_agent() -> None:
    line = AnchorConfig(target="ssh://box").command(["claude", "-p"])
    assert line[:5] == [sys.executable, "-Pm", "hmz", "internal", "anchor"]
    assert "--target=ssh://box" in line
    assert line[-2:] == ["claude", "-p"]


@pytest.mark.parametrize(
    ("asked", "settled"),
    [
        ({"swaps": [("/a", "/b")]}, {"redirects": (("/x", "/y"), ("/a", "/b"))}),
        ({"private": ["KEY"]}, {"private": ("OLD", "KEY")}),
        ({"chdir": "/w/sub"}, {"chdir": "/w/sub"}),
    ],
)
def test_one_turn_adds_to_the_settings_what_it_is_given(
    asked: dict[str, Any], settled: dict[str, Any]
) -> None:
    config = AnchorConfig(redirects=(("/x", "/y"),), private=("OLD",), chdir="/w")
    assert config.command(["a"], **asked) == replace(config, **settled).command(["a"])


def test_a_swap_that_is_not_two_paths_is_refused() -> None:
    with pytest.raises(ValueError, match="unsupported redirect"):
        AnchorConfig().command(["a"], swaps=[("/a", "relative")])


def test_a_harness_elsewhere_is_spawned_through_the_machine_it_runs_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def installed(road: transport.Road) -> str:
        return "/cache/h.pyz"

    monkeypatch.setattr(transport.Road, "installed", installed)
    line = AnchorConfig(harness="same", target="ssh://box").command(["claude"])
    assert line[0] == "ssh"
    assert line[-2] == "box"
    assert line[-1].endswith("claude")


# -------------------------------------------------------------------------- the mount


def test_the_workspace_defaults_to_this_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    target, workspace, export = AnchorConfig().mount()
    assert target == Target("local")
    assert Path(workspace).resolve() == tmp_path.resolve()
    assert export == workspace


@pytest.mark.parametrize(
    ("settings", "export"),
    [
        ({"target": "local:/real"}, "/w:/real"),
        ({"target": "local:/real", "remote_path": "/other"}, "/w:/other"),
        ({"target": "ssh://box"}, "/w"),
        ({"target": "ssh://box", "remote_path": "/srv/w"}, "/w:/srv/w"),
        ({"target": "peer://ticket@h:1"}, "/w"),
    ],
)
def test_the_export_names_where_the_work_really_is(
    settings: dict[str, Any], export: str
) -> None:
    _, workspace, said = AnchorConfig(workspace="/w", **settings).mount()
    assert workspace == "/w"
    assert said == export


def test_the_errors_of_its_own_are_os_errors_of_their_kind() -> None:
    assert issubclass(NotInstalled, FileNotFoundError)
    assert issubclass(Unmirrored, OSError)
    assert UNMIRRORED.startswith("cannot keep")


# ------------------------------------------------------------------- a target reached


class Client:
    """Answers as a target would: `run` says what each short command exits with."""

    def __init__(self, run: Callable[[Exec], None]) -> None:
        self.run = run
        self.info: dict[str, Any] = {}
        self.ran: list[Exec] = []
        self.closed = False
        self.token: str | None = None

    def start(self, token: str | None = None) -> dict[str, Any]:
        self.token = token
        self.info = {"version": 1, "hostname": "far", "pid": 7}
        return self.info

    def listdir(self, path: str) -> dict[str, Any]:
        return {"entries": [{"name": "a"}, {"name": "b"}]}

    def start_exec(
        self,
        argv: list[str],
        cwd: str,
        env: dict[str, str],
        on_output: Any,
        on_exit: Any,
        **options: Any,
    ) -> Exec:
        held = Exec(argv, cwd, env, on_output, on_exit, options)
        self.ran.append(held)
        self.run(held)
        return held

    def rmdir(self, path: str) -> None:
        raise OSError(errno.ENOTEMPTY, "not empty")

    def close(self) -> None:
        self.closed = True


class Link:
    def __init__(self) -> None:
        self.channel = object()
        self.closed = False
        self.asked: tuple[Target, list[str], str | None] | None = None

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def reached(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Callable[[Exec], None]], tuple[Client, Link]]:
    def reach(run: Callable[[Exec], None]) -> tuple[Client, Link]:
        client, link = Client(run), Link()

        def connected(
            target: Target, exports: list[str], token: str | None = None
        ) -> Link:
            link.asked = (target, exports, token)
            return link

        monkeypatch.setattr(transport, "connect", connected)

        def opened(channel: object) -> Client:
            return client

        monkeypatch.setattr(remote, "RemoteClient", opened)
        return client, link

    return reach


def nothing_there(held: Exec) -> None:
    held.answer(code=127)


def test_checking_a_target_asks_it_what_it_is(
    reached: Callable[[Callable[[Exec], None]], tuple[Client, Link]],
) -> None:
    client, link = reached(nothing_there)
    said = check(AnchorConfig(target="ssh://box", workspace="/w", token="tok"))
    assert said == {
        "version": 1,
        "hostname": "far",
        "pid": 7,
        "target": "ssh://box",
        "workspace": "/w",
        "entries": 2,
    }
    assert link.asked == (Target("ssh", host="box"), ["/w"], "tok")
    assert client.token == "tok"
    assert client.closed
    assert link.closed
    assert client.ran == []


def test_driving_nothing_is_refused(
    reached: Callable[[Callable[[Exec], None]], tuple[Client, Link]],
) -> None:
    _, link = reached(nothing_there)
    with pytest.raises(ValueError, match="no agent given"):
        drive([], AnchorConfig(native=True, target="ssh://box", workspace="/w"))
    assert link.asked is None


def test_driving_from_outside_the_workspace_is_refused(
    reached: Callable[[Callable[[Exec], None]], tuple[Client, Link]],
) -> None:
    _, link = reached(nothing_there)
    config = AnchorConfig(native=True, target="ssh://box", workspace="/w", chdir="/w2")
    with pytest.raises(ValueError, match="is not inside"):
        drive(["claude"], config)
    assert link.asked is None


def test_a_cli_the_target_has_not_got_is_not_installed_and_says_how_to_fix_it(
    reached: Callable[[Callable[[Exec], None]], tuple[Client, Link]],
) -> None:
    client, link = reached(nothing_there)
    config = AnchorConfig(
        native=True, target="ssh://box", workspace="/w", installs="npm i -g claude"
    )
    with pytest.raises(NotInstalled) as raised:
        drive(["/opt/bin/claude", "-p"], config)
    assert raised.value.errno == errno.ENOENT
    assert "is not installed on ssh://box" in str(raised.value)
    assert "npm i -g claude" in str(raised.value)
    # Looked for as named, then by its last component, from the workspace.
    assert [one.argv[-1] for one in client.ran] == ["/opt/bin/claude", "claude"]
    assert {one.cwd for one in client.ran} == {"/w"}
    assert all(one.closed for one in client.ran)
    assert client.closed
    assert link.closed


def test_a_target_that_cannot_be_asked_fails_the_turn(
    reached: Callable[[Callable[[Exec], None]], tuple[Client, Link]],
) -> None:
    def torn(held: Exec) -> None:
        held.answer(error=ConnectionResetError(errno.EPIPE, "gone"))

    reached(torn)
    config = AnchorConfig(native=True, target="ssh://box", workspace="/w")
    with pytest.raises(ConnectionResetError):
        drive(["claude"], config)


def test_a_native_session_is_driven(monkeypatch: pytest.MonkeyPatch) -> None:
    driven: list[tuple[list[str], AnchorConfig]] = []

    def drives(command: list[str], config: AnchorConfig) -> int:
        driven.append((command, config))
        return 5

    monkeypatch.setattr(anchor, "drive", drives)
    config = AnchorConfig(native=True, target="ssh://box")
    assert connect(["claude"], config) == 5
    assert driven == [(["claude"], config)]


def test_a_harness_elsewhere_is_one_process_carrying_its_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[list[str]] = []

    def call(argv: list[str]) -> int:
        called.append(argv)
        return 3

    def afar(config: AnchorConfig, argv: list[str]) -> list[str]:
        return ["far", *argv]

    monkeypatch.setattr(elsewhere, "afar", afar)
    monkeypatch.setattr(subprocess, "call", call)
    assert connect(["claude"], AnchorConfig(harness="ssh://box")) == 3
    assert called == [["far", "claude"]]
