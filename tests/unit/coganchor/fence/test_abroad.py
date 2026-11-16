"""A fence said in rules for another machine, and drawn again there around its own paths."""

from __future__ import annotations

import dataclasses
import stat
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.fence import NONE, READ, WRITE, Fence
from hmz.coganchor.fence.abroad import HOME, drawn, installed, ready, told

if TYPE_CHECKING:
    from pathlib import Path

WORK = "/home/someone/work"
HERE = "/home/someone"


RULES = [["/", NONE], ["~", READ], [".", WRITE]]


def fence_of(
    *rules: tuple[str, str],
    online: bool = False,
    write: tuple[str, ...] = (),
) -> Fence:
    return Fence.of(
        rules=rules or [(path, access) for path, access in RULES],
        online=online,
        workdir=WORK,
        home=HERE,
        hosts=["api.example.com"],
        write=write,
    )


def test_told_a_supervised_cli_says_only_the_rules() -> None:
    said = told(fence_of(write=(f"{HERE}/.cli",)), home=HERE, native=False)

    assert said == {"rules": RULES, "online": False}


def test_told_a_supervised_cli_says_its_scratch() -> None:
    fence = dataclasses.replace(fence_of(), tmp="/tmp/hmz-scratch")

    assert told(fence, home=HERE, native=False)["tmp"] == "/tmp/hmz-scratch"


def test_told_a_native_cli_says_its_hosts_and_state_under_the_home() -> None:
    fence = fence_of(write=(f"{HERE}/.cli", f"{HERE}/.cli.json", "/var/elsewhere"))

    said = told(fence, home=f"{HERE}/", native=True)

    assert said["hosts"] == ["api.example.com"]
    assert said["write"] == [f"{HOME}work", f"{HOME}.cli", f"{HOME}.cli.json"]
    assert said["programs"] is True
    assert "listen" not in said
    assert "tmp" not in said


def test_told_a_native_cli_says_its_ports() -> None:
    fence = fence_of().granting(listen=[8123])

    assert told(fence, home=HERE, native=True)["listen"] == [8123]


def test_told_refuses_a_fence_drawn_path_by_path() -> None:
    with pytest.raises(ValueError, match="path by path"):
        told(Fence(read=("/a",)), home=HERE, native=False)


def test_drawn_grants_the_rules_around_the_targets_own_paths(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    said = told(
        fence_of(write=(f"{HERE}/.cli",)).granting(listen=[8123]),
        home=HERE,
        native=True,
    )

    fence = drawn(said, workdirs=["/srv/work"], home=str(home))

    assert fence.allows("/srv/work/a.py", write=True)
    # Drawn as the home rather than asked of a path in it, `tmp_path` being under /tmp,
    # which a workdir that may be written writes.
    assert str(home) in fence.read
    assert str(home) not in fence.write
    assert fence.allows(home / ".cli" / "state", write=True)
    assert not fence.online
    assert fence.hosts == ("api.example.com",)
    assert fence.listen == (8123,)
    assert fence.drawn == tuple((path, access) for path, access in RULES)


def test_drawn_carves_out_around_the_targets_own_paths(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    said = told(
        fence_of(("/", READ), (".", WRITE), ("./secret", NONE), ("~/.ssh", NONE)),
        home=HERE,
        native=False,
    )

    fence = drawn(said, workdirs=["/srv/work", "/srv/more"], home=str(home))

    assert fence.allows("/srv/work/a.py", write=True)
    assert not fence.allows("/srv/work/secret/key")
    assert fence.allows("/srv/more/a.py", write=True)
    assert not fence.allows("/srv/more/secret/key")
    assert not fence.allows(home / ".ssh" / "id")
    assert fence.allows(home / ".bashrc")


@pytest.mark.parametrize("home", ["/", "missing", ""])
def test_drawn_without_a_home_keeps_nothing_under_one(
    tmp_path: Path, home: str
) -> None:
    where = str(tmp_path / home) if home == "missing" else home
    said = {"rules": RULES, "write": [f"{HOME}.cli"]}

    fence = drawn(said, workdirs=["/srv/work"], home=where)

    assert fence.allows("/srv/work/a", write=True)
    assert not any(one.endswith(".cli") for one in fence.write)


@pytest.mark.parametrize(
    ("local", "write", "read"),
    [(WRITE, True, True), (READ, False, True), (NONE, False, False)],
)
def test_drawn_grants_every_workdir_as_the_first(
    local: str, write: bool, read: bool
) -> None:
    said = {"rules": [[".", local]]}

    fence = drawn(said, workdirs=["/srv/one", "/srv/two"], home="/")

    assert fence.allows("/srv/two/x", write=True) is write
    assert fence.allows("/srv/two/x") is read


def test_drawn_keeps_the_scratch_and_more_paths() -> None:
    said = {
        "rules": [],
        "tmp": "/tmp//scratch/",
        "write": ["/var/state"],
    }

    fence = drawn(
        said, workdirs=["/srv/w"], home="/", read=["/opt/r"], write=["/opt/w"]
    )

    assert fence.tmp == "/tmp/scratch"
    assert fence.allows("/opt/r/x")
    assert not fence.allows("/opt/r/x", write=True)
    assert fence.allows("/opt/w/x", write=True)
    assert fence.allows("/var/state/x", write=True)


LEVELS: dict[str, Any] = {"rules": [["/", NONE]]}


@pytest.mark.parametrize(
    "said",
    [
        {},
        {"rules": "/"},
        {"rules": [["/"]]},
        {"rules": [["/", 1]]},
        {"rules": [["/", "all"]]},
        {"rules": [["relative", READ]]},
        {**LEVELS, "online": "yes"},
        {**LEVELS, "hosts": "api.example.com"},
        {**LEVELS, "hosts": [1]},
        {**LEVELS, "tmp": "relative"},
        {**LEVELS, "tmp": "/"},
        {**LEVELS, "tmp": "/tmp/../etc"},
        {**LEVELS, "tmp": 3},
        {**LEVELS, "write": ["relative"]},
        {**LEVELS, "write": [f"{HOME}../escape"]},
        {**LEVELS, "write": "/one"},
        {**LEVELS, "listen": [0]},
        {**LEVELS, "listen": [65536]},
        {**LEVELS, "listen": [True]},
        {**LEVELS, "listen": ["80"]},
        {**LEVELS, "listen": 80},
    ],
)
def test_drawn_refuses_what_is_not_a_fence(said: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match=r"fence|rule"):
        drawn(said, workdirs=["/srv/w"], home="/")


def test_drawn_refuses_no_workdir() -> None:
    with pytest.raises(ValueError, match="workdir"):
        drawn(LEVELS, workdirs=[], home="/")


def test_ready_makes_the_directories_under_the_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "outside"
    fence = Fence(
        write=(
            str(home / ".cli"),
            str(home / "deep" / "state"),
            str(home / ".cli.json"),
            str(outside),
        )
    )

    ready(fence, str(home))

    assert (home / ".cli").is_dir()
    assert stat.S_IMODE((home / ".cli").stat().st_mode) == 0o700
    assert (home / "deep" / "state").is_dir()
    assert not (home / ".cli.json").exists()
    assert not outside.exists()


def test_ready_leaves_what_is_there(tmp_path: Path) -> None:
    there = tmp_path / ".cli"
    there.write_text("a file")

    ready(Fence(write=(str(there),)), str(tmp_path))

    assert there.read_text() == "a file"


def executable(path: Path, said: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(said)
    path.chmod(0o755)
    return path


def test_installed_is_nothing_for_a_program_not_there(tmp_path: Path) -> None:
    assert installed("no-such-program", path=str(tmp_path)) == []
    assert installed(str(tmp_path / "no-such-program")) == []


def test_installed_is_the_program_its_directory_and_its_interpreter(
    tmp_path: Path,
) -> None:
    root = tmp_path.resolve()
    tool = executable(root / "tools" / "tool", "#!/usr/bin/env interp -u\n")
    interp = executable(root / "runtime" / "interp")
    path = f"{tool.parent}:{interp.parent}"

    held = installed("tool", path=path)

    assert held == [
        str(tool),
        str(tool),
        str(tool.parent),
        str(interp),
        str(interp),
        str(interp.parent),
    ]


def test_installed_is_the_install_root_of_a_bin_beside_a_lib(tmp_path: Path) -> None:
    root = tmp_path.resolve() / "prefix"
    tool = executable(root / "bin" / "tool")
    (root / "lib").mkdir()

    assert installed(str(tool)) == [str(tool), str(tool), str(root)]


@pytest.mark.parametrize(
    ("package", "inside"), [("@scope/pkg", "dist/cli.js"), ("pkg", "cli.js")]
)
def test_installed_is_the_package_of_a_node_program(
    tmp_path: Path, package: str, inside: str
) -> None:
    modules = tmp_path.resolve() / "lib" / "node_modules"
    real = executable(modules / package / inside, "#!/bin/sh\n")
    link = tmp_path.resolve() / "bin" / "cli"
    link.parent.mkdir()
    link.symlink_to(real)

    held = installed(str(link))

    assert held[:3] == [str(link), str(real), str(modules / package)]
