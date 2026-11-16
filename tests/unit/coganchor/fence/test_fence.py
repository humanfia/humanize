"""A fence's paths, levels and wire form, and whether this host can hold one.

Read off objects in this process: nothing is spawned and no wall is put up. Whether the host
can fence is asked of `coganchor internal able`, which a stand-in for running it answers.
"""

from __future__ import annotations

import dataclasses
import itertools
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import binary
from hmz.coganchor import fence as fencing
from hmz.coganchor.fence import (
    ALL,
    DARWIN_DEVICES,
    DARWIN_SYSTEM,
    DEVICES,
    LEVELS,
    LINUX_DEVICES,
    LINUX_SYSTEM,
    NONE,
    READ,
    SYSTEM,
    TEMPORARY,
    Fence,
    able,
    enforceable,
    landlocked,
    wrapper,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

HOME = "/home/someone"
WORK = "/home/someone/work"
ELSEWHERE = "/srv/elsewhere/file"

NESTED = [
    levels
    for levels in itertools.product(LEVELS, repeat=3)
    if LEVELS.index(levels[0]) >= LEVELS.index(levels[1]) >= LEVELS.index(levels[2])
]


def drawn(local: str, user: str, system: str, *, online: bool = True) -> Fence:
    return Fence.of(
        local=local, user=user, system=system, online=online, workdir=WORK, home=HOME
    )


def level(fence: Fence, path: str) -> str:
    if fence.allows(path, write=True):
        return ALL
    return READ if fence.allows(path) else NONE


def test_levels_are_ordered_narrowest_first() -> None:
    assert LEVELS == (NONE, READ, ALL) == ("none", "read", "all")


def test_the_minimum_is_this_platforms() -> None:
    darwin = sys.platform == "darwin"
    assert (DARWIN_SYSTEM if darwin else LINUX_SYSTEM) == SYSTEM
    assert (DARWIN_DEVICES if darwin else LINUX_DEVICES) == DEVICES


@pytest.mark.parametrize(("local", "user", "system"), NESTED)
def test_each_scope_grants_its_root_at_its_level(
    local: str, user: str, system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("os.geteuid", lambda: 0)
    fence = drawn(local, user, system)

    assert level(fence, f"{WORK}/src/main.py") == local
    assert level(fence, f"{HOME}/.bashrc") == user
    assert level(fence, ELSEWHERE) == system
    assert fence.scopes == (local, user, system)


@pytest.mark.parametrize("system", [NONE, READ])
def test_a_user_scope_of_all_writes_whatever_the_user_may_change(
    system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("os.geteuid", lambda: 1000)

    fence = drawn(ALL, ALL, system)

    assert level(fence, ELSEWHERE) == ALL
    assert fence.open


def test_a_user_scope_of_all_leaves_root_the_system_at_its_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("os.geteuid", lambda: 0)

    fence = drawn(ALL, ALL, READ)

    assert level(fence, ELSEWHERE) == READ
    assert level(fence, "/usr/bin/env") == READ
    assert level(fence, "/run/user/0/bus") == ALL
    assert all(fence.allows(one, write=True) for one in TEMPORARY)


@pytest.mark.parametrize(("local", "user", "system"), NESTED)
def test_a_local_scope_of_all_writes_the_scratch_every_user_has(
    local: str, user: str, system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("os.geteuid", lambda: 0)
    monkeypatch.setenv("TMPDIR", "/var/folders/xy/T")

    fence = drawn(local, user, system)

    for one in (*TEMPORARY, "/var/folders/xy/T/a"):
        assert fence.allows(one, write=True) == (local == ALL)


def test_a_relative_tmpdir_is_not_granted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMPDIR", "scratch")

    fence = drawn(ALL, READ, READ)

    assert not fence.allows(f"{Path.cwd()}/scratch", write=True)


@pytest.mark.parametrize(("local", "user", "system"), NESTED)
def test_the_minimum_is_granted_however_little_else_is(
    local: str, user: str, system: str
) -> None:
    fence = drawn(local, user, system)

    assert all(fence.allows(one) for one in SYSTEM)
    assert all(fence.allows(one, write=True) for one in DEVICES)
    assert fence.allows(sys.executable)


def test_a_thread_may_be_named_on_linux_however_little_else_is_granted() -> None:
    # As glibc and libcuda's cuInit name a thread they did not start as (issue 276).
    fence = Fence(write=LINUX_DEVICES)

    assert fence.allows("/proc/self/task/4242/comm", write=True)


@pytest.mark.parametrize(
    ("local", "user", "system"),
    [(READ, ALL, NONE), (NONE, READ, NONE), (ALL, NONE, READ), (NONE, NONE, ALL)],
)
def test_scopes_that_do_not_nest_are_refused(
    local: str, user: str, system: str
) -> None:
    with pytest.raises(ValueError, match="nest"):
        drawn(local, user, system)


def test_a_level_that_is_not_one_is_refused() -> None:
    with pytest.raises(ValueError, match="none, read, all"):
        drawn("write", NONE, NONE)


def test_the_session_directory_is_granted_as_the_workdir_is() -> None:
    fence = Fence.of(
        local=ALL,
        user=NONE,
        system=NONE,
        online=True,
        workdir=WORK,
        home=HOME,
        cwd="/srv/session",
    )

    assert fence.allows("/srv/session/out.txt", write=True)


def test_more_paths_and_hosts_are_granted_over_the_minimum() -> None:
    fence = Fence.of(
        local=NONE,
        user=NONE,
        system=NONE,
        online=False,
        workdir=WORK,
        home=HOME,
        hosts=["api.example.com"],
        read=["/opt/cli"],
        write=[Path(HOME, ".cli")],
    )

    assert level(fence, "/opt/cli/bin/cli") == READ
    assert level(fence, f"{HOME}/.cli/state.json") == ALL
    assert fence.hosts == ("api.example.com",)
    assert not fence.online


def test_paths_are_held_absolute_tidy_and_once() -> None:
    fence = Fence(read=("/a/../b", "/b", "/c/./d/"), write=("/w//x/",))

    assert fence.read == ("/b", "/c/d")
    assert fence.write == ("/w/x",)


def test_a_relative_path_is_taken_from_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert Fence(write=("rel",)).write == (str(Path.cwd() / "rel"),)


def test_a_path_both_read_and_written_is_written() -> None:
    fence = Fence(read=("/a", "/b"), write=("/a",))

    assert fence.read == ("/b",)
    assert fence.write == ("/a",)


def test_hosts_and_ports_are_held_once_in_order() -> None:
    fence = Fence(hosts=("b", "a", "b"), listen=(9, 8, 9))

    assert fence.hosts == ("b", "a")
    assert fence.listen == (9, 8)


@pytest.mark.parametrize(
    "scopes", [(ALL, READ), (ALL, READ, NONE, NONE), (ALL, READ, "write")]
)
def test_scopes_are_three_levels_or_none(scopes: tuple[str, ...]) -> None:
    with pytest.raises(ValueError, match="scopes"):
        Fence(scopes=scopes)


@pytest.mark.parametrize(
    ("path", "write", "allowed"),
    [
        ("/a/b", False, True),
        ("/a/b/c/d", False, True),
        ("/a/bc", False, False),
        ("/a", False, False),
        ("/a/b/../c", False, False),
        ("/r/x", False, True),
        ("/r/x", True, False),
        ("/a/b/x", True, True),
    ],
)
def test_allows_holds_a_path_to_the_roots_beneath_which_it_is(
    path: str, write: bool, allowed: bool
) -> None:
    fence = Fence(read=("/r",), write=("/a/b",))

    assert fence.allows(path, write=write) is allowed


def test_only_the_whole_filesystem_online_is_open() -> None:
    assert Fence(write=("/",)).open
    assert Fence(write=("/",)).everything
    assert not Fence(write=("/",), online=False).open
    assert not Fence(write=("/home",)).open
    assert drawn(ALL, ALL, ALL).open
    assert not drawn(ALL, ALL, ALL, online=False).open


def test_granting_widens_and_leaves_the_original_alone() -> None:
    fence = Fence(read=("/r",), write=("/w",), hosts=("a",), listen=(1,))

    wider = fence.granting(read=["/r2"], write=["/w2/"], hosts=["b"], listen=[2])

    assert wider.read == ("/r", "/r2")
    assert wider.write == ("/w", "/w2")
    assert wider.hosts == ("a", "b")
    assert wider.listen == (1, 2)
    assert fence == Fence(read=("/r",), write=("/w",), hosts=("a",), listen=(1,))
    assert fence.granting() == fence


def test_without_the_filesystem_leaves_it_all_writable() -> None:
    fence = drawn(READ, READ, NONE, online=False)

    rest = fence.without(filesystem=True)

    assert rest.read == ()
    assert rest.write == ("/",)
    assert rest.scopes == (ALL, ALL, ALL)
    assert not rest.online
    assert not rest.open


def test_without_the_network_leaves_it_online() -> None:
    fence = drawn(READ, READ, NONE, online=False)

    rest = fence.without(network=True)

    assert rest.online
    assert rest.read == fence.read
    assert rest.scopes == fence.scopes


def test_without_both_fences_nothing() -> None:
    assert (
        drawn(NONE, NONE, NONE, online=False)
        .without(filesystem=True, network=True)
        .open
    )


def test_without_the_filesystem_keeps_a_path_by_path_fence_levelless() -> None:
    assert Fence(read=("/r",)).without(filesystem=True).scopes == ()


def test_dumps_reads_back_as_the_same_fence() -> None:
    fence = dataclasses.replace(
        drawn(ALL, READ, NONE, online=False).granting(hosts=["h"], listen=[8080]),
        tmp="/tmp/scratch",
    )

    assert Fence.loads(fence.dumps()) == fence


def test_loads_fills_what_was_left_unsaid() -> None:
    assert Fence.loads("{}") == Fence()


@pytest.mark.parametrize(
    "said",
    [
        "not json",
        "[]",
        '{"bogus": 1}',
        '{"read": "/a"}',
        '{"write": [1]}',
        '{"hosts": [null]}',
        '{"scopes": "all"}',
        '{"listen": [true]}',
        '{"listen": ["80"]}',
        '{"listen": 80}',
        '{"online": "yes"}',
        '{"tmp": 3}',
        '{"scopes": ["all", "read"]}',
    ],
)
def test_loads_refuses_what_is_not_a_fence(said: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 -- every refusal is one
        Fence.loads(said)


def test_wrapper_runs_coganchor_with_the_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(binary, "here", lambda: Path("/opt/coganchor"))
    fence = drawn(READ, NONE, NONE)

    command = wrapper(fence)

    assert command[:3] == ["/opt/coganchor", "internal", "fence"]
    assert Fence.loads(command[3].removeprefix("--policy=")) == fence
    assert command[4:] == ["--"]


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[list[str]]]:
    """`coganchor internal able` asked afresh, of a build at `/opt/coganchor`."""
    held: list[list[str]] = []
    monkeypatch.setattr(binary, "found", lambda: Path("/opt/coganchor"))
    able.cache_clear()
    yield held
    able.cache_clear()


def answering(
    monkeypatch: pytest.MonkeyPatch,
    asked: list[list[str]],
    said: bytes,
    status: int = 0,
) -> None:
    """Has running a program answer with `said` on its stdout and `status`."""

    def run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[bytes]:
        asked.append(argv)
        return subprocess.CompletedProcess(argv, status, said, b"")

    monkeypatch.setattr(subprocess, "run", run)


@pytest.mark.parametrize(
    ("said", "held"),
    [
        (b'{"fs":true,"net":true}', (True, True)),
        (b'{"fs":true,"net":false}', (True, False)),
        (b'{"fs":false,"net":false}', (False, False)),
    ],
)
def test_what_this_machine_can_fence_is_what_coganchor_says(
    monkeypatch: pytest.MonkeyPatch,
    asked: list[list[str]],
    said: bytes,
    held: tuple[bool, bool],
) -> None:
    answering(monkeypatch, asked, said)

    assert able() == held
    assert enforceable(net=False) is held[0]
    assert enforceable(net=True) is held[1]
    assert asked == [["/opt/coganchor", "internal", "able"]]


@pytest.mark.parametrize(
    ("said", "status"),
    [(b'{"fs":true,"net":true}', 1), (b"not json", 0), (b"[true]", 0)],
)
def test_a_coganchor_that_cannot_say_is_a_machine_that_cannot_fence_until_it_can(
    monkeypatch: pytest.MonkeyPatch, asked: list[list[str]], said: bytes, status: int
) -> None:
    answering(monkeypatch, asked, said, status)

    with pytest.raises(OSError, match="internal able"):
        able()
    assert not enforceable(net=False)
    answering(monkeypatch, asked, b'{"fs":true,"net":false}')
    assert enforceable(net=False)
    assert len(asked) == 3


def test_a_machine_with_no_coganchor_cannot_fence(
    monkeypatch: pytest.MonkeyPatch, asked: list[list[str]]
) -> None:
    answering(monkeypatch, asked, b'{"fs":true,"net":true}')
    monkeypatch.setattr(binary, "found", lambda: None)

    assert not enforceable(net=False)
    with pytest.raises(FileNotFoundError, match="no coganchor is built"):
        able()
    assert asked == []


@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_landlocked_is_what_linux_can_fence(
    monkeypatch: pytest.MonkeyPatch, asked: list[list[str]], platform: str
) -> None:
    answering(monkeypatch, asked, b'{"fs":true,"net":false}')
    monkeypatch.setattr(sys, "platform", platform)

    assert landlocked(net=False) is (platform == "linux")
    assert not landlocked(net=True)


@pytest.fixture
def reachable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A directory no temporary directory holds, as a home would be."""
    monkeypatch.setattr(fencing, "TEMPORARY", ())
    monkeypatch.setenv("TMPDIR", str(tmp_path / "elsewhere"))
    return tmp_path.resolve()


def _closed(reached: tuple[int | None, str]) -> str:
    fd, at = reached
    if fd is not None:
        os.close(fd)
    return at


def test_reach_refuses_a_link_where_a_fenced_program_could_have_made_it(
    reachable: Path,
) -> None:
    state, home = reachable / "state", reachable / "home"
    state.mkdir()
    home.mkdir()
    (state / "scratch").symlink_to(home)
    fence = dataclasses.replace(Fence(write=(str(state),)), tmp=str(state / "scratch"))

    with pytest.raises(ValueError, match="it is a link where a fenced program could"):
        fence.reach(str(state / "scratch"), make=True)


def test_reach_refuses_a_link_on_the_way_in_a_written_directory(
    reachable: Path,
) -> None:
    work, home = reachable / "work", reachable / "home"
    work.mkdir()
    home.mkdir()
    (work / "state").symlink_to(home)
    fence = Fence(write=(str(work), str(work / "state" / "own")))

    with pytest.raises(ValueError, match=r"it leads through .*/work/state, a link"):
        fence.reach(str(work / "state" / "own"), make=True)
    assert not (home / "own").exists()


def test_reach_follows_a_link_in_a_directory_no_fence_writes(reachable: Path) -> None:
    home, kept = reachable / "home", reachable / "kept"
    home.mkdir()
    kept.mkdir()
    (home / ".claude").symlink_to(kept)

    at = _closed(Fence(write=(str(home / ".claude"),)).reach(str(home / ".claude")))

    assert at == str(kept)


def test_reach_follows_every_link_for_a_fence_that_writes_everything(
    reachable: Path,
) -> None:
    (reachable / "kept").mkdir()
    (reachable / "link").symlink_to(reachable / "kept")

    at = _closed(Fence(write=(os.sep, str(reachable))).reach(str(reachable / "link")))

    assert at == str(reachable / "kept")


def test_reach_makes_what_is_missing_as_the_users_own(reachable: Path) -> None:
    made = reachable / "a" / "b"

    at = _closed(Fence().reach(str(made), make=True))

    assert at == str(made)
    assert made.is_dir()
    assert stat.S_IMODE(made.stat().st_mode) == 0o700
