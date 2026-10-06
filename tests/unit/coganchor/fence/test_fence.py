"""A fence's paths, levels and wire form, and whether this host can hold one.

Read off objects in this process: nothing is spawned and no wall is put up. Whether the host
can fence is asked of collaborators replaced by stand-ins.
"""

from __future__ import annotations

import dataclasses
import itertools
import sys
import types
from pathlib import Path

import pytest

import hmz.coganchor
from hmz.coganchor import fence as fencing
from hmz.coganchor.darwin import seatbelt
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
    Fence,
    enforceable,
    landlocked,
    wrapper,
)
from hmz.coganchor.linux import landlock

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
    local: str, user: str, system: str
) -> None:
    fence = drawn(local, user, system)

    assert level(fence, f"{WORK}/src/main.py") == local
    assert level(fence, f"{HOME}/.bashrc") == user
    assert level(fence, ELSEWHERE) == system
    assert fence.scopes == (local, user, system)


@pytest.mark.parametrize(("local", "user", "system"), NESTED)
def test_the_minimum_is_granted_however_little_else_is(
    local: str, user: str, system: str
) -> None:
    fence = drawn(local, user, system)

    assert all(fence.allows(one) for one in SYSTEM)
    assert all(fence.allows(one, write=True) for one in DEVICES)
    assert fence.allows(sys.executable)


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


def test_wrapper_runs_the_fence_command_with_the_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hmz.coganchor, "__loader__", None)
    fence = drawn(READ, NONE, NONE)

    command = wrapper(fence)

    assert command[:5] == [sys.executable, "-Pm", "hmz", "internal", "fence"]
    assert command[-1] == "--"
    policy = command[5].removeprefix("--policy=")
    assert Fence.loads(policy) == fence


def test_wrapper_runs_from_the_archive_humanize_was_loaded_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        hmz.coganchor, "__loader__", types.SimpleNamespace(archive="/opt/hmz.pyz")
    )

    command = wrapper(Fence())

    assert command[:4] == [sys.executable, "/opt/hmz.pyz", "internal", "fence"]


def stand_in(
    monkeypatch: pytest.MonkeyPatch, *, notifiable: bool, supervisable: bool
) -> None:
    """Puts stand-ins for the socket filter and the loopback supervisor in their place."""
    monkeypatch.setitem(
        sys.modules,
        "hmz.coganchor.linux.seccomp",
        types.SimpleNamespace(notifiable=lambda: notifiable),
    )
    monkeypatch.setitem(
        sys.modules,
        "hmz.coganchor.fence.loopback",
        types.SimpleNamespace(supervisable=lambda: supervisable),
    )


@pytest.mark.parametrize("net", [False, True])
def test_landlocked_needs_landlock(monkeypatch: pytest.MonkeyPatch, net: bool) -> None:
    asked: list[bool] = []

    def available(*, net: bool = False) -> bool:
        asked.append(net)
        return False

    monkeypatch.setattr(landlock, "available", available)

    assert not landlocked(net=net)
    assert asked == [net]


def test_landlocked_needs_nothing_more_for_the_filesystem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(landlock, "available", lambda *, net=False: True)
    stand_in(monkeypatch, notifiable=False, supervisable=False)

    assert landlocked(net=False)


@pytest.mark.parametrize(
    ("notifiable", "supervisable", "held"),
    [(True, True, True), (False, True, False), (True, False, False)],
)
def test_landlocked_needs_seccomp_and_a_supervisor_for_the_network(
    monkeypatch: pytest.MonkeyPatch, notifiable: bool, supervisable: bool, held: bool
) -> None:
    monkeypatch.setattr(landlock, "available", lambda *, net=False: True)
    stand_in(monkeypatch, notifiable=notifiable, supervisable=supervisable)

    assert landlocked(net=True) is held


def test_landlocked_says_no_where_seccomp_cannot_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(landlock, "available", lambda *, net=False: True)
    # A module set to None in `sys.modules` is one that cannot be imported.
    monkeypatch.setitem(sys.modules, "hmz.coganchor.linux.seccomp", None)

    assert not landlocked(net=True)


@pytest.mark.skipif(sys.platform != "darwin", reason="Seatbelt is a Mac's")
@pytest.mark.parametrize("able", [True, False])
def test_enforceable_on_a_mac_is_seatbelt(
    monkeypatch: pytest.MonkeyPatch, able: bool
) -> None:
    def landlocked(*, net: bool) -> bool:
        return not able

    monkeypatch.setattr(seatbelt, "available", lambda: able)
    monkeypatch.setattr(fencing, "landlocked", landlocked)

    assert enforceable(net=True) is able


@pytest.mark.skipif(sys.platform == "darwin", reason="Landlock is Linux's")
@pytest.mark.parametrize("net", [False, True])
def test_enforceable_elsewhere_is_landlock(
    monkeypatch: pytest.MonkeyPatch, net: bool
) -> None:
    def landlocked(*, net: bool) -> bool:
        return net

    monkeypatch.setattr(fencing, "landlocked", landlocked)

    assert enforceable(net=net) is net
