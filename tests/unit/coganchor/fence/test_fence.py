"""A fence's paths, rules, carve-outs and wire form, and whether this host can hold one.

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
    AUTO,
    BWRAP,
    DARWIN_DEVICES,
    DARWIN_SYSTEM,
    DEVICES,
    LANDLOCK,
    LEVELS,
    LINUX_DEVICES,
    LINUX_SYSTEM,
    NONE,
    READ,
    SYSTEM,
    TEMPORARY,
    WRITE,
    Fence,
    able,
    chosen,
    enforceable,
    landlocked,
    natives,
    needs,
    unheld,
    wrapper,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

HOME = "/home/someone"
WORK = "/home/someone/work"
ELSEWHERE = "/srv/elsewhere/file"

#: The three scopes the old permission had, as the rules they are: `/`, then `~`, then `.`.
NESTED = [
    levels
    for levels in itertools.product(LEVELS, repeat=3)
    if LEVELS.index(levels[0]) >= LEVELS.index(levels[1]) >= LEVELS.index(levels[2])
]

#: What this machine can fence as `coganchor` is asked it: `tests/unit/conftest.py` answers it
#: for every other unit test, and the tests here are about the asking.
_ABLE = fencing.able
_UNHELD = fencing.unheld


@pytest.fixture(autouse=True)
def _asked(monkeypatch: pytest.MonkeyPatch) -> None:
    """`fence.able` and `fence.unheld` as they are, asking `coganchor`, for the tests of that."""
    monkeypatch.setattr(fencing, "able", _ABLE)
    monkeypatch.setattr(fencing, "unheld", _UNHELD)


def scoped(local: str, user: str, system: str) -> list[tuple[str, str]]:
    return [("/", system), ("~", user), (".", local)]


def drawn(*rules: tuple[str, str], online: bool = True) -> Fence:
    return Fence.of(rules=rules, online=online, workdir=WORK, home=HOME)


def test_levels_are_ordered_narrowest_first() -> None:
    assert LEVELS == (NONE, READ, WRITE) == ("none", "read", "write")


def test_the_minimum_is_this_platforms() -> None:
    darwin = sys.platform == "darwin"
    assert (DARWIN_SYSTEM if darwin else LINUX_SYSTEM) == SYSTEM
    assert (DARWIN_DEVICES if darwin else LINUX_DEVICES) == DEVICES


@pytest.mark.parametrize(("local", "user", "system"), NESTED)
def test_each_anchor_grants_its_root_at_its_access(
    local: str, user: str, system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("os.geteuid", lambda: 0)
    fence = drawn(*scoped(local, user, system))

    assert fence.level(f"{WORK}/src/main.py") == local
    assert fence.level(f"{HOME}/.bashrc") == user
    assert fence.level(ELSEWHERE) == system
    assert fence.drawn == tuple(scoped(local, user, system))
    # Rules that nest carve nothing out.
    assert (fence.keep, fence.deny) == ((), ())


@pytest.mark.parametrize("system", [NONE, READ])
def test_a_home_that_may_be_written_writes_whatever_the_user_may_change(
    system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("os.geteuid", lambda: 1000)

    fence = drawn(*scoped(WRITE, WRITE, system))

    assert fence.level(ELSEWHERE) == WRITE
    assert fence.open


def test_a_home_that_may_be_written_leaves_root_the_system_at_its_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("os.geteuid", lambda: 0)

    fence = drawn(*scoped(WRITE, WRITE, READ))

    assert fence.level(ELSEWHERE) == READ
    assert fence.level("/usr/bin/env") == READ
    assert fence.level("/run/user/0/bus") == WRITE
    assert all(fence.allows(one, write=True) for one in TEMPORARY)


def test_a_home_inside_a_workdir_that_may_be_written_is_no_home_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("os.geteuid", lambda: 1000)

    fence = Fence.of(
        rules=scoped(WRITE, READ, READ), online=True, workdir="/w", home="/w/home"
    )

    assert fence.level("/w/home/x") == WRITE
    assert fence.level(ELSEWHERE) == READ
    assert not fence.open


@pytest.mark.parametrize(("local", "user", "system"), NESTED)
def test_a_workdir_that_may_be_written_writes_the_scratch_every_user_has(
    local: str, user: str, system: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("os.geteuid", lambda: 0)
    monkeypatch.setenv("TMPDIR", "/var/folders/xy/T")

    fence = drawn(*scoped(local, user, system))

    for one in (*TEMPORARY, "/var/folders/xy/T/a"):
        assert fence.allows(one, write=True) == (local == WRITE)


def test_a_relative_tmpdir_is_not_granted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TMPDIR", "scratch")

    fence = drawn(*scoped(WRITE, READ, READ))

    assert not fence.allows(f"{Path.cwd()}/scratch", write=True)


@pytest.mark.parametrize(("local", "user", "system"), NESTED)
def test_the_minimum_is_granted_however_little_else_is(
    local: str, user: str, system: str
) -> None:
    fence = drawn(*scoped(local, user, system))

    assert all(fence.allows(one) for one in SYSTEM)
    assert all(fence.allows(one, write=True) for one in DEVICES)
    assert fence.allows(sys.executable)


def test_the_minimum_is_granted_beneath_a_rule_that_denies_its_root() -> None:
    fence = drawn(("/", WRITE), ("/usr", NONE), ("/dev", NONE))

    assert fence.allows("/usr/bin/env")
    assert fence.allows("/dev/null", write=True)
    assert not fence.allows("/dev/disk0")


def test_a_thread_may_be_named_on_linux_however_little_else_is_granted() -> None:
    # As glibc and libcuda's cuInit name a thread they did not start as (issue 276).
    fence = Fence(write=LINUX_DEVICES)

    assert fence.allows("/proc/self/task/4242/comm", write=True)


def test_the_last_rule_that_holds_a_path_decides_it() -> None:
    fence = drawn(
        ("/", READ),
        (".", WRITE),
        ("./secret", NONE),
        ("./ro", READ),
        ("./ro/scratch", WRITE),
        ("~/.ssh", NONE),
    )

    assert fence.level(f"{WORK}/src/main.py") == WRITE
    assert fence.level(f"{WORK}/secret/key") == NONE
    assert fence.level(f"{WORK}/ro/notes") == READ
    assert fence.level(f"{WORK}/ro/scratch/out") == WRITE
    assert fence.level(f"{HOME}/.ssh/id_ed25519") == NONE
    assert fence.level(f"{HOME}/.bashrc") == READ
    assert fence.keep == (f"{WORK}/ro",)
    assert fence.deny == (f"{HOME}/.ssh", f"{WORK}/secret")


def test_a_later_rule_takes_away_every_earlier_one_beneath_it() -> None:
    fence = drawn(("./secret", NONE), (".", WRITE), ("/", READ))

    assert fence.level(f"{WORK}/secret/key") == READ
    assert fence.level(f"{WORK}/src") == READ
    assert (fence.keep, fence.deny) == ((), ())
    assert not fence.allows("/tmp/x", write=True)


@pytest.mark.parametrize(
    "rules",
    [
        [("/", READ), (".", WRITE), ("/tmp", NONE)],
        [("/", READ), ("/tmp", NONE), (".", WRITE)],
    ],
)
def test_a_rule_at_a_temporary_loses_to_it_and_one_beneath_it_wins(
    monkeypatch: pytest.MonkeyPatch, rules: list[tuple[str, str]]
) -> None:
    monkeypatch.setenv("TMPDIR", "/var/folders/xy/T")

    at = drawn(*rules)
    beneath = drawn(*rules, ("/tmp/x", NONE), ("/var/tmp/y", READ))

    # At one depth the wider wins, wherever the rule is said.
    assert at.allows("/tmp/a", write=True)
    assert beneath.allows("/tmp/a", write=True)
    # Beneath it, the deeper decides.
    assert beneath.level("/tmp/x/key") == NONE
    assert beneath.level("/var/tmp/y/z") == READ
    assert beneath.allows("/var/tmp/z", write=True)


def test_a_rule_beneath_a_temporary_as_its_links_lead_is_carved_out_of_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # As a Mac's `/tmp` is `/private/tmp`, which is how a path found beneath it is spelled.
    real = Path(os.path.realpath(tmp_path)) / "private"
    real.mkdir()
    (tmp_path / "tmp").symlink_to(real)
    monkeypatch.setenv("TMPDIR", str(tmp_path / "tmp"))

    fence = drawn(
        ("/", NONE), (f"{real}/kept", READ), (f"{real}/shut", NONE), (".", WRITE)
    )

    assert fence.allows(f"{real}/a", write=True)
    assert fence.level(f"{real}/kept/a") == READ
    assert fence.level(f"{real}/shut/a") == NONE
    assert (fence.keep, fence.deny) == ((f"{real}/kept",), (f"{real}/shut",))


def test_a_rule_beneath_what_a_written_home_brings_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("os.geteuid", lambda: 1000)

    fence = drawn(("/", NONE), ("~", WRITE), ("/opt", NONE), ("/etc", READ))

    assert fence.level("/opt/x") == NONE
    assert fence.level("/etc/hosts") == READ
    assert fence.level(ELSEWHERE) == WRITE
    # At `/` itself the grant is the wider, whatever the rule there says.
    assert drawn(("/", READ), ("~", WRITE)).level(ELSEWHERE) == WRITE


def test_a_rule_for_the_home_takes_the_workdir_beneath_it_with_it() -> None:
    assert drawn(("/", READ), (".", WRITE), ("~", READ)).level(WORK) == READ
    assert drawn(("/", READ), ("~", READ), (".", WRITE)).level(WORK) == WRITE


def test_a_deny_beneath_nothing_granted_carves_nothing() -> None:
    fence = drawn(("~/.ssh", NONE))

    assert fence.deny == ()
    assert fence.level(f"{HOME}/.ssh") == NONE


def test_a_read_rule_beneath_a_denied_one_grants_reading_again() -> None:
    fence = drawn(("/", WRITE), ("~", NONE), ("~/docs", READ))

    assert fence.level(f"{HOME}/docs/a") == READ
    assert fence.level(f"{HOME}/.bashrc") == NONE
    assert f"{HOME}/docs" in fence.read


def test_the_session_directory_is_the_workdir_as_well() -> None:
    fence = Fence.of(
        rules=[(".", WRITE), ("./out", READ)],
        online=True,
        workdir=WORK,
        home=HOME,
        cwd="/srv/session",
    )

    assert fence.allows("/srv/session/x.txt", write=True)
    assert fence.level("/srv/session/out/y") == READ


def test_no_home_leaves_out_every_rule_said_under_it() -> None:
    fence = Fence.of(
        rules=[("~", WRITE), (".", READ)], online=True, workdir=WORK, home=""
    )

    assert fence.level(WORK) == READ
    assert fence.level("/home/someone/x") == NONE


@pytest.mark.parametrize(
    ("said", "held"),
    [
        ("/", "/"),
        ("//a//b/", "/a/b"),
        ("~", "~"),
        ("~/", "~"),
        ("~/a/./b", "~/a/b"),
        (".", "."),
        ("./", "."),
        ("./a//b/", "./a/b"),
    ],
)
def test_a_rules_path_is_held_tidy(said: str, held: str) -> None:
    assert drawn((said, READ)).drawn == ((held, READ),)


@pytest.mark.parametrize(
    "said", ["a", "a/b", "~user", "~user/x", "../x", "./a/../b", ""]
)
def test_a_rules_path_that_is_not_anchored_is_refused(said: str) -> None:
    with pytest.raises(ValueError, match="a rule's path"):
        drawn((said, READ))


def test_an_access_that_is_not_one_is_refused() -> None:
    with pytest.raises(ValueError, match="none, read, write"):
        drawn(("/", "all"))


def test_more_paths_and_hosts_are_granted_over_the_minimum() -> None:
    fence = Fence.of(
        rules=[("/", NONE)],
        online=False,
        workdir=WORK,
        home=HOME,
        hosts=["api.example.com"],
        read=["/opt/cli"],
        write=[Path(HOME, ".cli")],
    )

    assert fence.level("/opt/cli/bin/cli") == READ
    assert fence.level(f"{HOME}/.cli/state.json") == WRITE
    assert fence.hosts == ("api.example.com",)
    assert not fence.online


def test_paths_are_held_absolute_tidy_and_once() -> None:
    fence = Fence(
        read=("/a/../b", "/b", "/c/./d/"),
        write=("/w//x/",),
        keep=("/k/",),
        deny=("/d/./e",),
    )

    assert fence.read == ("/b", "/c/d")
    assert fence.write == ("/w/x",)
    assert fence.keep == ("/k",)
    assert fence.deny == ("/d/e",)


def test_a_relative_path_is_taken_from_the_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert Fence(write=("rel",)).write == (str(Path.cwd() / "rel"),)


def test_a_path_both_read_and_written_is_written() -> None:
    fence = Fence(read=("/a", "/b"), write=("/a",))

    assert fence.read == ("/b",)
    assert fence.write == ("/a",)


def test_a_path_both_kept_and_denied_is_denied() -> None:
    fence = Fence(keep=("/a", "/b"), deny=("/a",))

    assert fence.keep == ("/b",)
    assert fence.deny == ("/a",)


def test_hosts_and_ports_are_held_once_in_order() -> None:
    fence = Fence(hosts=("b", "a", "b"), listen=(9, 8, 9))

    assert fence.hosts == ("b", "a")
    assert fence.listen == (9, 8)


@pytest.mark.parametrize(
    "rules", [(("/", "all"),), (("x", READ),), (("/", READ, "extra"),)]
)
def test_drawn_is_rules_or_none(rules: tuple[tuple[str, ...], ...]) -> None:
    with pytest.raises(ValueError, match="rule"):
        Fence(drawn=rules)  # pyright: ignore[reportArgumentType]


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


@pytest.mark.parametrize(
    ("path", "level"),
    [
        ("/w/x", WRITE),
        ("/w/k", READ),
        ("/w/k/x", READ),
        ("/w/k/g/x", WRITE),
        ("/w/d", NONE),
        ("/w/d/x", NONE),
        ("/w/d/g", READ),
        ("/w/d/g/x", READ),
        ("/w/dx", WRITE),
        ("/w/both", WRITE),
        ("/elsewhere", NONE),
    ],
)
def test_a_carve_out_takes_back_what_the_grants_above_it_gave(
    path: str, level: str
) -> None:
    fence = Fence(
        read=("/w/d/g",),
        write=("/w", "/w/k/g", "/w/both"),
        keep=("/w/k",),
        deny=("/w/d", "/w/both"),
    )

    assert fence.level(path) == level
    assert fence.allows(path) is (level != NONE)
    assert fence.allows(path, write=True) is (level == WRITE)


def test_a_carve_out_holds_against_a_grant_above_it_however_wide() -> None:
    fence = Fence(read=("/",), write=("/", "/w"), keep=("/w/k",), deny=("/w/k/d",))

    assert fence.level("/w/k/x") == READ
    assert fence.level("/w/k/d/x") == NONE
    assert not fence.open


def test_only_the_whole_filesystem_online_with_nothing_carved_is_open() -> None:
    assert Fence(write=("/",)).open
    assert Fence(write=("/",)).everything
    assert not Fence(write=("/",), online=False).open
    assert not Fence(write=("/home",)).open
    assert not Fence(write=("/",), deny=("/x",)).open
    assert not Fence(write=("/",), keep=("/x",)).open
    assert drawn(("/", WRITE)).open
    assert not drawn(("/", WRITE), online=False).open
    assert not drawn(("/", WRITE), ("~/.ssh", NONE)).open


def test_granting_widens_and_leaves_the_original_alone() -> None:
    fence = Fence(read=("/r",), write=("/w",), hosts=("a",), listen=(1,))

    wider = fence.granting(read=["/r2"], write=["/w2/"], hosts=["b"], listen=[2])

    assert wider.read == ("/r", "/r2")
    assert wider.write == ("/w", "/w2")
    assert wider.hosts == ("a", "b")
    assert wider.listen == (1, 2)
    assert fence == Fence(read=("/r",), write=("/w",), hosts=("a",), listen=(1,))
    assert fence.granting() == fence


def test_granting_beneath_a_carve_out_grants_it_and_nothing_else() -> None:
    fence = drawn(("/", READ), ("~", NONE)).granting(write=[f"{HOME}/.cli"])

    assert fence.allows(f"{HOME}/.cli/state", write=True)
    assert not fence.allows(f"{HOME}/.bashrc")


def test_beside_draws_another_directory_as_the_workdir() -> None:
    fence = drawn(("/", READ), (".", WRITE), ("./secret", NONE), ("./ro", READ))

    mirrored = fence.beside("/mirror", home=HOME)

    assert mirrored.level("/mirror/src") == WRITE
    assert mirrored.level("/mirror/secret/key") == NONE
    assert mirrored.level("/mirror/ro/x") == READ
    assert mirrored.level(f"{WORK}/secret") == NONE


def test_beside_narrows_a_directory_under_a_wider_grant() -> None:
    fence = drawn(("/", READ), ("~", WRITE), (".", READ))

    mirrored = fence.beside(f"{HOME}/.cache/mirror", home=HOME)

    assert mirrored.level(f"{HOME}/.cache/mirror/x") == READ
    assert mirrored.level(f"{HOME}/.cache/other") == WRITE


def test_beside_a_fence_drawn_path_by_path_is_that_fence() -> None:
    fence = Fence(write=("/w",))

    assert fence.beside("/mirror", home=HOME) == fence


def test_outward_is_whether_a_rule_writes_past_the_workdir() -> None:
    assert not drawn(("/", READ), (".", WRITE), ("./x", WRITE)).outward
    assert drawn(("/", READ), ("~/x", WRITE)).outward
    assert drawn(("/", WRITE)).outward
    assert not Fence(write=("/",)).outward
    # What a later rule takes away does not write past the workdir.
    assert not drawn(("~", WRITE), ("~", READ), (".", WRITE)).outward
    assert not drawn(("~/x", WRITE), ("/", READ)).outward
    assert drawn(("~/x", WRITE), (".", READ)).outward


def test_writes_is_whether_a_standing_rule_writes_anywhere() -> None:
    assert not drawn(("/", READ)).writes
    assert not drawn(("/", READ), ("./secret", NONE)).writes
    assert drawn(("/", READ), (".", WRITE)).writes
    assert drawn(("/", READ), ("~/x", WRITE)).writes
    # What a later rule takes away writes nothing.
    assert not drawn((".", WRITE), ("/", READ)).writes
    # From another anchor too, where it lands here: the workdir is inside the home.
    assert not drawn(("/", READ), (".", WRITE), ("~", READ)).writes
    assert not drawn(("/", READ), (".", WRITE), (HOME, NONE)).writes
    assert drawn(("/", READ), (".", WRITE), ("~/x", READ)).writes
    assert Fence.of(
        rules=[("/", READ), (".", WRITE), ("~", READ)],
        online=True,
        workdir="/srv/work",
        home=HOME,
    ).writes
    # Drawn path by path: written beyond the devices every program writes.
    assert not Fence(read=("/",), write=DEVICES).writes
    assert Fence(read=("/",), write=(*DEVICES, WORK)).writes


def test_reading_is_the_fence_with_nothing_written_but_the_minimum() -> None:
    fence = drawn(
        ("/", READ), ("~/.ssh", NONE), (".", WRITE), ("./docs", READ), online=False
    ).granting(hosts=("example.com",), listen=(8080,))

    twin = fence.reading()

    assert fence.writes
    assert not twin.writes
    assert twin.drawn == (("/", READ), ("~/.ssh", NONE), (".", READ), ("./docs", READ))
    assert twin.level(f"{WORK}/src/main.py") == READ
    assert twin.level("/tmp/scratch") == READ
    assert twin.level(f"{HOME}/.ssh/id") == NONE
    assert twin.level(ELSEWHERE) == READ
    assert all(twin.level(one) == WRITE for one in DEVICES)
    assert (twin.online, twin.hosts, twin.listen) == (False, ("example.com",), (8080,))


def test_reading_a_fence_that_writes_nothing_changes_nothing() -> None:
    fence = drawn(("/", READ), ("./secret", NONE))

    assert fence.reading() == fence


def test_standing_is_what_no_later_rule_takes_away() -> None:
    fence = drawn(
        ("/", WRITE),
        ("~/a", WRITE),
        ("~", READ),
        ("./b", NONE),
        ("/", READ),
        (".", WRITE),
        ("~/c", NONE),
    )

    assert fence.standing == (("/", READ), (".", WRITE), ("~/c", NONE))


def test_without_the_filesystem_leaves_it_all_writable() -> None:
    fence = drawn(("/", NONE), ("~", READ), ("~/.ssh", NONE), online=False)

    rest = fence.without(filesystem=True)

    assert rest.read == ()
    assert rest.write == ("/",)
    assert (rest.keep, rest.deny) == ((), ())
    assert rest.drawn == (("/", WRITE),)
    assert not rest.online
    assert not rest.open


def test_without_the_network_leaves_it_online() -> None:
    fence = drawn(*scoped(READ, READ, NONE), online=False)

    rest = fence.without(network=True)

    assert rest.online
    assert rest.read == fence.read
    assert rest.drawn == fence.drawn


def test_without_both_fences_nothing() -> None:
    assert drawn(("/", NONE), online=False).without(filesystem=True, network=True).open


def test_without_the_filesystem_keeps_a_path_by_path_fence_ruleless() -> None:
    assert Fence(read=("/r",)).without(filesystem=True).drawn == ()


def test_dumps_reads_back_as_the_same_fence() -> None:
    fence = dataclasses.replace(
        drawn(
            ("/", READ), (".", WRITE), ("./ro", READ), ("~/.ssh", NONE), online=False
        ).granting(hosts=["h"], listen=[8080]),
        tmp="/tmp/scratch",
    )

    assert fence.keep
    assert fence.deny
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
        '{"keep": "/k"}',
        '{"deny": [null]}',
        '{"hosts": [null]}',
        '{"drawn": "all"}',
        '{"drawn": [["/"]]}',
        '{"drawn": [["/", 1]]}',
        '{"drawn": [["/", "all"]]}',
        '{"drawn": [["x", "read"]]}',
        '{"listen": [true]}',
        '{"listen": ["80"]}',
        '{"listen": 80}',
        '{"online": "yes"}',
        '{"tmp": 3}',
    ],
)
def test_loads_refuses_what_is_not_a_fence(said: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 -- every refusal is one
        Fence.loads(said)


def test_wrapper_runs_coganchor_with_the_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(binary, "here", lambda: Path("/opt/coganchor"))
    fence = drawn(*scoped(READ, NONE, NONE))

    command = wrapper(fence)

    assert command[:3] == ["/opt/coganchor", "internal", "fence"]
    assert Fence.loads(command[3].removeprefix("--policy=")) == fence
    assert command[4:] == ["--sandbox=auto", "--"]


def test_wrapper_passes_the_backend_the_settings_choose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(binary, "here", lambda: Path("/opt/coganchor"))
    _settings("sandbox: {backend: bwrap}")

    assert wrapper(Fence())[4] == "--sandbox=bwrap"


def _settings(said: str) -> None:
    """This machine's settings file, holding what is said."""
    where = Path(os.environ["HUMANIZE_HOME"], "settings.yaml")
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(said, encoding="utf-8")


@pytest.mark.parametrize(
    ("said", "chose"),
    [
        ("", AUTO),
        ("sandbox: bwrap", AUTO),
        ("sandbox: {backend: 3}", AUTO),
        ("sandbox: {backend: firejail}", AUTO),
        ("sandbox: {backend: landlock}", LANDLOCK),
        ("sandbox: {backend: bwrap}", BWRAP),
    ],
)
def test_chosen_reads_anything_else_as_auto(said: str, chose: str) -> None:
    _settings(said)

    assert chosen() == chose


@pytest.mark.parametrize(
    ("said", "named"),
    [
        ("", set[str]()),
        ("sandbox: {native: codex}", set[str]()),
        ("sandbox: {native: [codex, 3, grok]}", {"codex", "grok"}),
    ],
)
def test_natives_are_the_kinds_the_settings_name(said: str, named: set[str]) -> None:
    _settings(said)

    assert natives() == named


@pytest.mark.parametrize(
    ("said", "net", "wanted", "unwanted"),
    [
        ("", False, ("Landlock (Linux 5.13", "bubblewrap"), ()),
        ("", True, ("Landlock ABI 4", "network namespace"), ()),
        ("sandbox: {backend: landlock}", True, ("Landlock ABI 4",), ("bubblewrap",)),
        ("sandbox: {backend: bwrap}", False, ("bubblewrap",), ("Landlock",)),
    ],
)
def test_needs_names_what_the_chosen_backend_needs(
    monkeypatch: pytest.MonkeyPatch,
    said: str,
    net: bool,
    wanted: tuple[str, ...],
    unwanted: tuple[str, ...],
) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(binary, "found", lambda: Path("/opt/coganchor"))
    _settings(said)

    told = needs(net=net)

    assert all(one in told for one in wanted)
    assert not any(one in told for one in unwanted)


@pytest.mark.parametrize("platform", ["darwin", "linux"])
def test_needs_names_coganchor_where_none_is_built_here(
    monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    monkeypatch.setattr("sys.platform", platform)
    monkeypatch.setattr(binary, "found", lambda: None)

    told = needs(net=False)

    # Not a sandbox this process is in, nor a kernel's lack: the program is not here.
    assert "a coganchor built for this machine" in told
    assert "HUMANIZE_COGANCHOR" in told
    assert "Seatbelt" not in told
    assert "Landlock" not in told


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

    assert able(AUTO) == held
    assert enforceable(net=False) is held[0]
    assert enforceable(net=True) is held[1]
    assert asked == [["/opt/coganchor", "internal", "able", "--sandbox=auto"]]


def test_enforceable_asks_of_the_backend_the_settings_choose_and_landlocked_of_landlock(
    monkeypatch: pytest.MonkeyPatch, asked: list[list[str]]
) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    _settings("sandbox: {backend: bwrap}")
    answering(monkeypatch, asked, b'{"fs":true,"net":true}')

    assert enforceable(net=True)
    assert landlocked(net=True)
    assert [one[-1] for one in asked] == ["--sandbox=bwrap", "--sandbox=landlock"]


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


def test_what_a_fence_carves_out_is_held_where_coganchor_says_it_is(
    monkeypatch: pytest.MonkeyPatch, asked: list[list[str]]
) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    carved = Fence(write=("/w",), deny=("/w/secret",))
    why = "[Errno 13] Permission denied: '/w'"
    answering(
        monkeypatch, asked, b'{"fs":true,"net":true,"unheld":"%s"}' % why.encode()
    )

    assert unheld(carved) == why
    assert asked == [
        [
            "/opt/coganchor",
            "internal",
            "able",
            f"--policy={carved.dumps()}",
            "--sandbox=auto",
        ]
    ]
    answering(monkeypatch, asked, b'{"fs":true,"net":true,"unheld":null}')
    assert unheld(carved) is None
    # Nothing carved out, or a Mac, which carves out with Seatbelt: nothing is asked.
    assert unheld(Fence(write=("/w",))) is None
    monkeypatch.setattr("sys.platform", "darwin")
    assert unheld(carved) is None
    assert len(asked) == 2


def test_a_coganchor_that_cannot_say_holds_no_carve_out(
    monkeypatch: pytest.MonkeyPatch, asked: list[list[str]]
) -> None:
    monkeypatch.setattr("sys.platform", "linux")
    answering(monkeypatch, asked, b"not json")

    assert "internal able" in str(unheld(Fence(write=("/w",), keep=("/w/ro",))))


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


def test_reach_follows_no_link_into_what_a_fence_of_everything_carves_out(
    reachable: Path,
) -> None:
    (reachable / "kept").mkdir()
    (reachable / "link").symlink_to(reachable / "kept")
    fence = Fence(write=(os.sep, str(reachable)), deny=(str(reachable / "kept"),))

    with pytest.raises(ValueError, match="carved out of this fence"):
        fence.reach(str(reachable / "link"))


def test_reach_follows_a_link_elsewhere_for_a_fence_of_everything_carved(
    reachable: Path,
) -> None:
    (reachable / "kept").mkdir()
    (reachable / "link").symlink_to(reachable / "kept")
    fence = Fence(write=(os.sep,), deny=(str(reachable / "other"),))

    assert _closed(fence.reach(str(reachable / "link"))) == str(reachable / "kept")


def test_reach_makes_what_is_missing_as_the_users_own(reachable: Path) -> None:
    made = reachable / "a" / "b"

    at = _closed(Fence().reach(str(made), make=True))

    assert at == str(made)
    assert made.is_dir()
    assert stat.S_IMODE(made.stat().st_mode) == 0o700


def test_a_mac_reads_the_developer_tools_its_xcrun_shims_load() -> None:
    """A Mac's `/usr/bin` shims load `libxcrun.dylib` from the chosen developer directory."""
    assert {
        "/private/var/db/xcode_select_link",
        "/Library/Developer/CommandLineTools",
        "/Library/Preferences/com.apple.dt.Xcode.plist",
        "/Applications/Xcode.app",
    } <= set(DARWIN_SYSTEM)
    assert not {"/Library", "/Applications"} & set(DARWIN_SYSTEM)


@pytest.mark.parametrize(
    ("platform", "chosen", "read"),
    [
        ("darwin", "/Applications/Xcode-beta.app/Contents/Developer", True),
        ("linux", "/Applications/Xcode-beta.app/Contents/Developer", False),
        ("darwin", None, False),
    ],
    ids=["mac-elsewhere", "linux", "mac-none-chosen"],
)
def test_the_developer_directory_xcode_select_chose_is_read_on_a_mac(
    monkeypatch: pytest.MonkeyPatch, platform: str, chosen: str | None, read: bool
) -> None:
    real = os.path.realpath

    def resolving(path: str, *, strict: bool = False) -> str:
        if path != "/private/var/db/xcode_select_link":
            return real(path, strict=strict)
        if chosen is None:
            raise FileNotFoundError(path)
        return chosen

    monkeypatch.setattr("sys.platform", platform)
    monkeypatch.setattr("os.path.realpath", resolving)

    fence = drawn((".", READ))

    beta = "/Applications/Xcode-beta.app/Contents/Developer/usr/lib/libxcrun.dylib"
    shared = "/Applications/Xcode-beta.app/Contents/SharedFrameworks"
    assert fence.allows(beta) == fence.allows(shared) == read
    assert not fence.allows(beta, write=True)
