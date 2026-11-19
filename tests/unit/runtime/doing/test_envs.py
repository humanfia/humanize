"""`hosts.env.*` carried out on the envs of a run, over drivers that stand in for envs."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.flows import (
    EnvCommandTimeout,
    EnvFileNotFound,
    FilesEnvMixin,
    ShellEnvMixin,
)
from hmz.runtime.doing.envs import NO_FLOW, EnvRefusal, answered, carried, listed

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from pathlib import Path

_ALL = frozenset({FilesEnvMixin, ShellEnvMixin})


@dataclass(eq=False)
class Driver:
    """An env, as far as these read one: files in a dict, and one command's answer."""

    workdir: str = "/w"
    backend: str = "ssh"
    capabilities: frozenset[type] = _ALL
    files: dict[str, bytes] = field(default_factory=dict[str, bytes])
    ran: tuple[int, str, str] | BaseException = (0, "", "")
    asked: list[tuple[list[str], float]] = field(default_factory=list[Any])
    #: Where each path is with every link followed, as its machine says it.
    links: dict[str, str] = field(default_factory=dict[str, str])
    #: Where the workdir is on its machine, as `pwd` says it there and with every link followed.
    where: tuple[str, str] | None = None

    async def read(self, path: str) -> bytes:
        if path not in self.files:
            raise EnvFileNotFound(path)
        return self.files[path]

    async def write(self, path: str, data: bytes) -> None:
        self.files[path] = data

    async def exec(self, argv: list[str], *, timeout: float) -> tuple[int, str, str]:  # noqa: ASYNC109 -- the driver's own
        if len(argv) > 2 and "readlink" in argv[2]:
            relative = argv[-1]
            real = self.links.get(relative, f"{self.workdir}/{relative}")
            return 0, f"{self.workdir}\n{real}\n", ""
        if self.where and len(argv) > 2 and argv[2].startswith("pwd"):
            return 0, "".join(f"{one}\n" for one in self.where), ""
        self.asked.append((argv, timeout))
        if isinstance(self.ran, BaseException):
            raise self.ran
        return self.ran


def _does(method: str, driver: Driver, **said: Any) -> dict[str, Any]:
    envs = cast("Mapping[str, Any]", {"box": driver})
    return asyncio.run(carried(f"hosts.env.{method}", envs, {"env": "box", **said}))


def _refused(method: str, driver: Driver, **said: Any) -> tuple[int, str]:
    with pytest.raises(EnvRefusal) as refused:
        _does(method, driver, **said)
    return refused.value.code, refused.value.why


def test_each_env_is_listed_with_its_kind_workdir_and_what_it_offers() -> None:
    envs = {
        "box": Driver(),
        "bare": Driver(workdir="/b", backend="docker", capabilities=frozenset()),
    }

    assert listed(cast("Mapping[str, Any]", envs)) == [
        {
            "name": "box",
            "kind": "ssh",
            "workdir": "/w",
            "can": ["read", "write", "exec", "grep"],
        },
        {"name": "bare", "kind": "docker", "workdir": "/b", "can": []},
    ]


def test_a_file_is_read_a_window_at_a_time_as_utf8() -> None:
    driver = Driver(files={"a/b.txt": "héllo".encode()})

    assert _does("read", driver, path="a/b.txt") == {
        "text": "héllo",
        "size": 6,
        "eof": True,
    }
    assert _does("read", driver, path="./a/../a/b.txt", offset=1, length=1) == {
        "text": "\N{REPLACEMENT CHARACTER}",
        "size": 6,
        "eof": False,
    }
    assert _does("read", driver, path="/w/a/b.txt", offset=3)["text"] == "llo"


def test_a_file_that_is_not_there_is_not_found() -> None:
    assert _refused("read", Driver(), path="gone") == (
        404,
        "There is no file gone in box.",
    )


@pytest.mark.parametrize("path", ["..", "../x", "a/../../x", "/etc/passwd", "/wx"])
def test_a_path_out_of_the_workdir_is_refused(path: str) -> None:
    assert _refused("read", Driver(), path=path) == (
        400,
        f"{path} is outside the env box.",
    )


def test_a_link_out_of_a_workdir_on_this_machine_is_refused(tmp_path: Path) -> None:
    (tmp_path / "w").mkdir()
    (tmp_path / "w" / "out").symlink_to(tmp_path)
    driver = Driver(workdir=str(tmp_path / "w"), backend="local")

    assert _refused("write", driver, path="out/x", text="") == (
        400,
        "out/x is outside the env box.",
    )


def test_a_link_out_of_a_workdir_elsewhere_is_refused_as_its_machine_follows_it() -> (
    None
):
    driver = Driver(links={"out/x": "/etc/x"})

    assert _refused("read", driver, path="out/x") == (
        400,
        "out/x is outside the env box.",
    )


def test_a_number_out_of_its_range_is_refused() -> None:
    envs = cast("Mapping[str, Any]", {"box": Driver()})
    said = {"do": "hosts.env.grep", "env": "box", "pattern": "x", "limit": 0}

    with pytest.raises(EnvRefusal) as refused:
        asyncio.run(carried("hosts.env.grep", envs, said))

    assert (refused.value.code, refused.value.why) == (
        -32602,
        "hosts.env.grep takes limit as an integer from 1 to 2000.",
    )


def test_a_file_is_written_whole_and_its_size_said() -> None:
    driver = Driver()

    assert _does("write", driver, path="n/é.txt", text="é\n") == {"size": 3}
    assert driver.files == {"n/é.txt": "é\n".encode()}


@pytest.mark.parametrize("workdir", ["/w", "~/w"])
@pytest.mark.parametrize("path", ["~/x", "a/../~/x"])
def test_a_path_under_a_tilde_is_one_in_the_workdir_not_in_the_home(
    workdir: str, path: str
) -> None:
    # A driver reads a path that begins `~` from its machine's home: it is given none that does
    # but under the workdir's own.
    driver = Driver(workdir=workdir)

    assert _does("write", driver, path=path, text="x") == {"size": 1}
    assert driver.files == {f"{workdir}/~/x": b"x"}
    assert _does("read", driver, path=path)["text"] == "x"


@pytest.mark.parametrize("path", ["/home/u/w/a/b.txt", "/real/u/w/a/../a/b.txt"])
def test_an_absolute_path_in_a_workdir_under_the_home_is_one_in_it(path: str) -> None:
    # The workdir is said as `~/w`; where that is, only its machine knows.
    driver = Driver(
        workdir="~/w", where=("/home/u/w", "/real/u/w"), files={"a/b.txt": b"in"}
    )

    assert _does("read", driver, path=path)["text"] == "in"
    assert _does("write", driver, path=path, text="new") == {"size": 3}
    assert driver.files == {"a/b.txt": b"new"}
    driver.ran = (0, "", "1\n")
    _does("grep", driver, pattern="x", path="/home/u/w/a")
    assert driver.asked[-1][0][-2] == "a"


@pytest.mark.parametrize("path", ["/home/u/wx", "/home/u", "/home/u/w/../x", "/etc"])
def test_an_absolute_path_out_of_a_workdir_under_the_home_is_refused(path: str) -> None:
    driver = Driver(workdir="~/w", where=("/home/u/w", "/real/u/w"))

    assert _refused("read", driver, path=path) == (
        400,
        f"{path} is outside the env box.",
    )


def test_a_command_says_its_status_and_the_last_of_what_it_wrote() -> None:
    driver = Driver(ran=(3, "x" * (2 << 20), "oops\n"))

    ran = _does("exec", driver, argv=["make"], seconds=5)

    assert (ran["code"], len(ran["stdout"]), ran["stderr"]) == (3, 1 << 20, "oops\n")
    assert driver.asked == [(["make"], 5)]
    assert _does("exec", Driver(), argv=["true"]) == {
        "code": 0,
        "stdout": "",
        "stderr": "",
    }


def test_a_command_past_its_time_has_no_status() -> None:
    driver = Driver(ran=EnvCommandTimeout("slow"))

    assert _does("exec", driver, argv=["sleep", "9"]) == {
        "code": None,
        "stdout": "",
        "stderr": "",
    }
    assert driver.asked[0][1] == 120


def test_a_command_needs_an_argv() -> None:
    assert _refused("exec", Driver(), argv=[]) == (
        400,
        "hosts.env.exec runs a command: give argv.",
    )


def test_a_search_says_each_line_found_and_whether_there_were_more() -> None:
    long = "y" * 500
    driver = Driver(
        ran=(0, f"./a.txt\x002:world\nsub/b:c\x0010:{long}\n./z\x001:z\n", "0\n")
    )

    found = _does("grep", driver, pattern="w.r", path="./", limit=2)

    assert found == {
        "matches": [
            {"path": "a.txt", "line": 2, "text": "world"},
            {"path": "sub/b:c", "line": 10, "text": "y" * 400},
        ],
        "more": True,
    }
    argv, _ = driver.asked[0]
    assert argv[-3:] == ["w.r", ".", "3"]


def test_a_pattern_grep_cannot_read_is_refused() -> None:
    driver = Driver(ran=(0, "", "grep: Unmatched ( or \\(\n2\n"))

    assert _refused("grep", driver, pattern="(") == (400, "grep: Unmatched ( or \\(")


def test_a_search_finding_nothing_is_no_refusal_whatever_else_was_said() -> None:
    driver = Driver(ran=(0, "", "Welcome to the box\n1\n"))

    assert _does("grep", driver, pattern="x") == {"matches": [], "more": False}


def test_an_env_the_epic_has_not_is_not_found() -> None:
    with pytest.raises(EnvRefusal) as refused:
        asyncio.run(carried("hosts.env.read", {}, {"env": "nope", "path": "a"}))

    assert (refused.value.code, refused.value.why) == (404, "The epic has no env nope.")


@pytest.mark.parametrize(
    ("method", "what"),
    [
        ("read", "read files"),
        ("write", "write files"),
        ("exec", "run commands"),
        ("grep", "search files"),
    ],
)
def test_an_env_that_cannot_do_what_is_asked_says_so(method: str, what: str) -> None:
    driver = Driver(capabilities=frozenset())

    assert _refused(method, driver, path="a", text="", argv=["x"], pattern="x") == (
        409,
        f"The env box cannot {what}.",
    )


@dataclass(frozen=True)
class Held:
    role: str
    driver: Any
    parent: str | None = None


@dataclass
class Holds:
    loop: asyncio.AbstractEventLoop
    held: tuple[Held, ...]

    def env_roles(self) -> dict[str, Any]:
        roles: dict[str, Any] = {}
        for one in self.held:
            if one.parent is None:
                roles.setdefault(one.role, one.driver)
        return roles


@pytest.fixture
def loop() -> Iterator[asyncio.AbstractEventLoop]:
    """A loop going on a thread of its own, as a run's is."""
    going = asyncio.new_event_loop()
    thread = threading.Thread(target=going.run_forever, daemon=True)
    thread.start()
    try:
        yield going
    finally:
        going.call_soon_threadsafe(going.stop)
        thread.join()
        going.close()


def test_what_a_run_holds_at_its_root_is_asked_on_its_loop(
    loop: asyncio.AbstractEventLoop,
) -> None:
    box = Driver(files={"a": b"hi"})
    holds = Holds(
        loop,
        (
            Held("box", box),
            Held("box", Driver(workdir="/w/.t"), parent="ssh@h/w"),
            Held("workspace", Driver(backend="local", workdir="/here")),
        ),
    )

    envs = answered(cast("Any", holds), {"do": "hosts.env.list"})["envs"]
    assert [(one["name"], one["workdir"]) for one in envs] == [
        ("box", "/w"),
        ("workspace", "/here"),
    ]
    assert answered(
        cast("Any", holds), {"do": "hosts.env.read", "env": "box", "path": "a"}
    ) == {"text": "hi", "size": 2, "eof": True}


def test_a_run_whose_loop_has_closed_has_no_env_open() -> None:
    closed = asyncio.new_event_loop()
    closed.close()
    holds = Holds(closed, (Held("box", Driver()),))

    with pytest.raises(EnvRefusal) as refused:
        answered(
            cast("Any", holds), {"do": "hosts.env.read", "env": "box", "path": "a"}
        )

    assert (refused.value.code, refused.value.why) == (409, NO_FLOW)
