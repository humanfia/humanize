from __future__ import annotations

import errno
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, BinaryIO

import pytest

import hmz.coganchor.remote
import hmz.coganchor.transport
from hmz.coganchor import AnchorConfig
from hmz.coganchor.machines import Mapped, Ran

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.coganchor.transport import Target

WORKSPACE = "/srv/w"


@dataclass
class Handle:
    closed: list[bool] = field(default_factory=list[bool])
    fails: bool = False

    def close_stdin(self) -> None:
        if self.fails:
            raise OSError("channel gone")
        self.closed.append(True)


@dataclass
class Link:
    channel: object = "channel"
    closed: int = 0

    def close(self) -> None:
        self.closed += 1


@dataclass
class Far:
    """The target, as a `RemoteClient` speaks to it: a dict of files and what runs say."""

    files: dict[str, bytes] = field(default_factory=dict[str, bytes])
    dirs: dict[str, list[Any]] = field(default_factory=dict[str, list[Any]])
    made: list[tuple[str, bool]] = field(default_factory=list[tuple[str, bool]])
    gone: list[str] = field(default_factory=list[str])
    modes: dict[str, int | None] = field(default_factory=dict[str, int | None])
    ran: list[tuple[list[str], str, dict[str, str]]] = field(
        default_factory=list[tuple[list[str], str, dict[str, str]]]
    )
    answer: tuple[list[bytes], dict[str, Any] | None, OSError | None] = (
        [],
        {"exit_code": 0},
        None,
    )
    handle: Handle = field(default_factory=Handle)
    started: list[str | None] = field(default_factory=list[str | None])
    refuses: BaseException | None = None
    closed: int = 0


class Client:
    def __init__(self, far: Far) -> None:
        self.far = far

    def start(self, token: str | None = None) -> dict[str, Any]:
        self.far.started.append(token)
        if self.far.refuses is not None:
            raise self.far.refuses
        return {}

    def close(self) -> None:
        self.far.closed += 1

    def read_file(self, path: str, sink: BinaryIO) -> dict[str, Any]:
        if path not in self.far.files:
            raise FileNotFoundError(errno.ENOENT, "no such file", path)
        sink.write(self.far.files[path])
        return {}

    def write_file(self, path: str, source: BinaryIO, mode: int | None = None) -> None:
        self.far.files[path] = source.read()
        self.far.modes[path] = mode

    def listdir(self, path: str) -> dict[str, Any]:
        if path in self.far.dirs:
            return {"entries": self.far.dirs[path]}
        if path in self.far.files:
            raise NotADirectoryError(errno.ENOTDIR, "not a directory", path)
        raise FileNotFoundError(errno.ENOENT, "no such file", path)

    def mkdir(self, path: str, mode: int = 0o777, *, parents: bool = False) -> None:
        self.far.made.append((path, parents))

    def unlink(self, path: str) -> None:
        self.far.gone.append(path)

    def start_exec(
        self,
        argv: list[str],
        cwd: str,
        env: dict[str, str],
        wrote: Callable[[Any, bytes], None],
        ended: Callable[[dict[str, Any] | None, OSError | None], None],
    ) -> Handle:
        self.far.ran.append((argv, cwd, env))
        said, payload, why = self.far.answer
        for one in said:
            wrote(None, one)
        ended(payload, why)
        return self.far.handle


@dataclass
class Wire:
    far: Far = field(default_factory=Far)
    links: list[Link] = field(default_factory=list[Link])
    connected: list[tuple[str, list[str], str | None]] = field(
        default_factory=list[tuple[str, list[str], str | None]]
    )


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> Wire:
    held = Wire()

    def connect(target: Target, exports: list[str], token: str | None = None) -> Link:
        held.connected.append((target.describe(), exports, token))
        link = Link()
        held.links.append(link)
        return link

    monkeypatch.setattr(hmz.coganchor.transport, "connect", connect)

    def client(_: object) -> Client:
        return Client(held.far)

    monkeypatch.setattr(hmz.coganchor.remote, "RemoteClient", client)
    return held


@pytest.fixture
def mapped(wire: Wire) -> Mapped:
    return Mapped(AnchorConfig(target="ssh://box", workspace=WORKSPACE, token="tok"))


# ------------------------------------------------------------------------------- Ran


@pytest.mark.parametrize(("status", "ok"), [(0, True), (1, False), (130, False)])
def test_a_command_succeeded_when_it_stopped_on_nothing(status: int, ok: bool) -> None:
    ran = Ran(argv=("true",), status=status, output="said")

    assert ran.ok is ok
    assert str(ran) == "said"


# ---------------------------------------------------------------------------- opening


def test_nothing_connects_until_something_is_asked(wire: Wire, mapped: Mapped) -> None:
    assert wire.connected == []

    assert mapped.workspace == WORKSPACE
    assert mapped.workspace == WORKSPACE
    assert wire.connected == [("ssh://box", [WORKSPACE], "tok")]
    assert wire.far.started == ["tok"]


def test_a_handshake_that_failed_lets_go_and_connects_again(
    wire: Wire, mapped: Mapped
) -> None:
    wire.far.refuses = OSError("refused")

    with pytest.raises(OSError, match="refused"):
        mapped.read_text("a")
    assert wire.far.closed == 1
    assert wire.links[0].closed == 1

    wire.far.refuses = None
    wire.far.files[f"{WORKSPACE}/a"] = b"x"
    assert mapped.read_text("a") == "x"
    assert len(wire.connected) == 2


def test_closing_lets_go_once_however_often_it_is_asked(
    wire: Wire, mapped: Mapped
) -> None:
    with mapped as held:
        assert held.workspace == WORKSPACE
    mapped.close()

    assert wire.far.closed == 1
    assert wire.links[0].closed == 1


def test_closing_what_never_opened_does_nothing(wire: Wire, mapped: Mapped) -> None:
    mapped.close()

    assert wire.connected == []


# ------------------------------------------------------------------------------ files


def test_a_relative_path_is_under_the_workspace_and_an_absolute_one_is_itself(
    wire: Wire, mapped: Mapped
) -> None:
    wire.far.files[f"{WORKSPACE}/src/a.py"] = b"print()\n"
    wire.far.files["/etc/hosts"] = "hé".encode()

    assert mapped.read_text("src/../src/a.py") == "print()\n"
    assert mapped.read_bytes("/etc/hosts") == "hé".encode()
    assert mapped.read_text("/etc/hosts", encoding="latin-1") == "hÃ©"


def test_a_file_that_is_not_there_cannot_be_read(wire: Wire, mapped: Mapped) -> None:
    with pytest.raises(FileNotFoundError):
        mapped.read_text("missing")


def test_a_file_written_lands_on_the_machine_with_its_mode(
    wire: Wire, mapped: Mapped
) -> None:
    mapped.write_text("out.txt", "hi", mode=0o600)
    mapped.write_bytes("/tmp/raw", b"\x00")

    assert wire.far.files == {f"{WORKSPACE}/out.txt": b"hi", "/tmp/raw": b"\x00"}
    assert wire.far.modes == {f"{WORKSPACE}/out.txt": 0o600, "/tmp/raw": None}


def test_a_listing_is_the_names_in_it(wire: Wire, mapped: Mapped) -> None:
    wire.far.dirs[WORKSPACE] = [{"name": "a"}, "b", {"other": "c"}]
    wire.far.dirs[f"{WORKSPACE}/sub"] = []

    assert mapped.listdir() == ["a", "b", "{'other': 'c'}"]
    assert list(mapped) == ["a", "b", "{'other': 'c'}"]
    assert mapped.listdir("sub") == []


@pytest.mark.parametrize(
    ("path", "there"),
    [("dir", True), ("file", True), ("missing", False)],
)
def test_something_is_there_unless_the_machine_says_nothing_is(
    wire: Wire, mapped: Mapped, path: str, there: bool
) -> None:
    wire.far.dirs[f"{WORKSPACE}/dir"] = []
    wire.far.files[f"{WORKSPACE}/file"] = b""

    assert mapped.exists(path) is there


def test_a_machine_that_cannot_be_reached_is_not_an_answer(
    wire: Wire, mapped: Mapped
) -> None:
    wire.far.refuses = OSError("down")

    with pytest.raises(OSError, match="down"):
        mapped.exists("anything")


def test_directories_are_made_and_files_taken_away(wire: Wire, mapped: Mapped) -> None:
    mapped.mkdir("a/b")
    mapped.mkdir("/abs", parents=False)
    mapped.remove("old")

    assert wire.far.made == [(f"{WORKSPACE}/a/b", True), ("/abs", False)]
    assert wire.far.gone == [f"{WORKSPACE}/old"]


# -------------------------------------------------------------------------------- run


def test_a_command_is_run_in_the_workspace_with_nothing_inherited(
    wire: Wire, mapped: Mapped
) -> None:
    wire.far.answer = ([b"out ", b"err\n"], {"exit_code": 3}, None)

    ran = mapped.run("git status --short")

    assert ran == Ran(argv=("git", "status", "--short"), status=3, output="out err\n")
    assert wire.far.ran == [(["git", "status", "--short"], WORKSPACE, {})]
    assert wire.far.handle.closed == [True]


def test_a_command_runs_where_and_with_what_it_was_told(
    wire: Wire, mapped: Mapped
) -> None:
    mapped.run(["ls", "-l"], cwd="sub", env={"A": "1"})

    assert wire.far.ran == [(["ls", "-l"], f"{WORKSPACE}/sub", {"A": "1"})]


@pytest.mark.parametrize(
    ("payload", "status"),
    [({"signal": 9}, 137), ({}, 128), (None, 1)],
)
def test_a_command_that_did_not_say_how_it_ended_did_not_succeed(
    wire: Wire, mapped: Mapped, payload: dict[str, Any] | None, status: int
) -> None:
    wire.far.answer = ([], payload, None)

    assert mapped.run(["x"]).status == status


def test_a_command_that_could_not_be_started_raises(wire: Wire, mapped: Mapped) -> None:
    wire.far.answer = ([], None, OSError("no such program"))

    with pytest.raises(OSError, match="no such program"):
        mapped.run(["nope"])


def test_a_channel_that_died_before_stdin_closed_is_left_to_say_so(
    wire: Wire, mapped: Mapped
) -> None:
    wire.far.handle.fails = True

    assert mapped.run(["true"]).ok


@pytest.mark.parametrize("argv", ["", "   ", []])
def test_a_command_is_at_least_a_program(
    wire: Wire, mapped: Mapped, argv: str | list[str]
) -> None:
    with pytest.raises(ValueError, match="at least a program"):
        mapped.run(argv)


def test_output_that_is_not_text_is_replaced_rather_than_raised(
    wire: Wire, mapped: Mapped
) -> None:
    wire.far.answer = ([b"\xff\xfe ok"], {"exit_code": 0}, None)

    assert mapped.run(["cat"]).output.endswith(" ok")
