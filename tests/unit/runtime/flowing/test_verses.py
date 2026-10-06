"""Where flows come from: `verses`, with git stood in for wherever it would run."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from hmz.runtime.flowing import verses
from hmz.runtime.flowing.finding import BUILTIN_AT
from hmz.runtime.flowing.index import kept
from hmz.runtime.flowing.verses import (
    INDEX,
    LOCAL,
    MINE,
    OFFICIAL,
    USER,
    Flowverse,
    add,
    called,
    edited,
    fetch,
    flows,
    flowverses,
    holds,
    named,
    nearest,
    pathed,
    plain,
    remove,
    renamed,
    spelled,
    split,
    standing,
    under,
)
from tests.unit.runtime.flowing.doubles_u10 import cloned, flow_dir, flow_file, settle

THEIRS = "file:///srv/theirs.git"


@pytest.fixture
def project(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    return settle(monkeypatch, tmp_path)


class Git:
    """`clone` and `refresh`, stood in for: a clone is a directory that says where it is from."""

    def __init__(self) -> None:
        self.cloned: list[tuple[str, Path]] = []
        self.refreshed: list[Path] = []
        self.fails = False

    def clone(self, url: str, at: Path) -> None:
        if self.fails:
            raise OSError("fatal: repository not found")
        self.cloned.append((url, at))
        cloned(at, url)

    def refresh(self, at: Path) -> None:
        self.refreshed.append(at)


@pytest.fixture
def git(monkeypatch: pytest.MonkeyPatch, project: Path) -> Git:
    del project
    held = Git()
    monkeypatch.setattr(verses, "clone", held.clone)
    monkeypatch.setattr(verses, "refresh", held.refresh)
    return held


# ------------------------------------------------------------------------------ names


@pytest.mark.parametrize(
    ("said", "expected"),
    [("./x", True), ("/x", True), ("~/x", True), ("x", False), ("@local/x", False)],
)
def test_pathed_tells_a_path_from_a_name(said: str, *, expected: bool) -> None:
    assert pathed(said) is expected


def test_spelled_keeps_a_relative_path_a_path() -> None:
    assert spelled("x") == "x"
    assert spelled(Path("x")) == "./x"
    assert spelled(Path("/a/x")) == "/a/x"


@pytest.mark.parametrize(
    ("verse", "flow", "expected"),
    [
        (OFFICIAL, "aot", "aot"),
        (OFFICIAL, "alice/kernel", "alice/kernel"),
        (LOCAL, "x", "@local/x"),
        ("theirs", "alice/kernel:sub", "@theirs/alice/kernel:sub"),
    ],
)
def test_called_names_a_flow_after_its_flowverse(
    verse: str, flow: str, expected: str
) -> None:
    assert called(verse, flow) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("aot", (OFFICIAL, "aot")),
        ("alice/kernel", (OFFICIAL, "alice/kernel")),
        ("@local/x", (LOCAL, "x")),
        ("@theirs/alice/kernel", ("theirs", "alice/kernel")),
    ],
)
def test_split_reads_a_flows_name(name: str, expected: tuple[str, str]) -> None:
    assert split(name) == expected


@pytest.mark.parametrize(
    "name",
    ["", "@/x", "@local/a/b", "a/b/c", "a//b", ".hidden", "@-bad/x", "@user/a/b"],
)
def test_split_refuses_what_is_no_name(name: str) -> None:
    with pytest.raises(ValueError, match="is not a flow's name"):
        split(name)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://x-access-token:secret@github.com/o/r", "https://***@github.com/o/r"),
        ("https://github.com/o/r", "https://github.com/o/r"),
        ("ssh://git@host/r", "ssh://***@host/r"),
        ("o/r", "o/r"),
    ],
)
def test_plain_takes_what_was_signed_into_a_url_out(url: str, expected: str) -> None:
    assert plain(url) == expected


# ------------------------------------------------------------------------- the places


def test_three_places_are_always_there(project: Path) -> None:
    listed = flowverses()
    assert [one.name for one in listed] == [OFFICIAL, LOCAL, USER]
    official, local, user = listed
    assert (official.url, official.fetched, official.fixed) == (
        verses.OFFICIAL_URL,
        False,
        True,
    )
    assert official.at == under() / OFFICIAL / INDEX
    assert local == Flowverse(LOCAL, "", Path(".hmz/flows"), fetched=True, fixed=True)
    assert user.at == Path(project.parent / "me" / ".hmz" / "flows")
    assert [one.name for one in nearest()] == [LOCAL, USER, OFFICIAL]
    assert set(MINE) == {LOCAL, USER}


def test_places_added_are_listed_between_humanizes_and_yours(project: Path) -> None:
    del project
    cloned(under() / "zeta" / INDEX, "file:///z")
    cloned(under() / "alpha" / INDEX, "file:///a")
    (under() / "bare").mkdir()
    (under() / "-bad").mkdir()
    (under() / LOCAL).mkdir()
    listed = flowverses()
    assert [one.name for one in listed] == [
        OFFICIAL,
        "alpha",
        "bare",
        "zeta",
        LOCAL,
        USER,
    ]
    alpha, bare = listed[1], listed[2]
    assert (alpha.url, alpha.fetched, alpha.fixed) == ("file:///a", True, False)
    assert (bare.url, bare.fetched) == ("", False)
    assert named("alpha") == alpha
    assert named("nothing") is None
    assert [one.name for one in nearest()][:3] == [LOCAL, USER, OFFICIAL]


def test_a_clone_whose_config_will_not_read_has_no_url(project: Path) -> None:
    del project
    at = cloned(under() / "odd" / INDEX, "file:///x")
    (at / ".git" / "config").write_text('[remote "origin"\nurl = %(broken)s\n')
    assert named("odd") == Flowverse("odd", "", at, fetched=True, fixed=False)


def test_holds_says_where_each_place_keeps_its_flows(project: Path) -> None:
    del project
    official, local, user = flowverses()
    assert holds(official) == (BUILTIN_AT, kept(OFFICIAL))
    assert holds(local) == (local.at,)
    assert holds(user) == (user.at,)
    theirs = Flowverse(
        "theirs", THEIRS, under() / "theirs" / INDEX, fetched=True, fixed=False
    )
    assert holds(theirs) == (kept("theirs"),)


def test_flows_lists_what_each_place_has_to_run(project: Path) -> None:
    del project
    local = named(LOCAL)
    assert local is not None
    assert flows(local) == []
    flow_dir(local.at, "b_flow")
    flow_file(local.at, "a_flow")
    flow_file(local.at, "_helper")
    (local.at / "not_a_flow").mkdir()
    assert flows(local) == ["a_flow", "b_flow"]
    installed = kept("theirs")
    flow_dir(installed, "plain")
    flow_dir(installed / "alice", "kernel")
    flow_dir(installed / "Bad_Owner", "x")
    theirs = Flowverse(
        "theirs", THEIRS, under() / "theirs" / INDEX, fetched=True, fixed=False
    )
    assert flows(theirs) == ["alice/kernel", "plain"]


def test_official_lists_the_package_and_what_was_installed_once(project: Path) -> None:
    del project
    official = named(OFFICIAL)
    assert official is not None
    builtin = flows(official)
    assert "chat" in builtin
    flow_dir(kept(OFFICIAL), "chat")
    flow_dir(kept(OFFICIAL), "zz_extra")
    assert flows(official) == sorted([*builtin, "zz_extra"])


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("local/x", "@local/x"),
        ("user/x:sub", "@user/x:sub"),
        ("official/x", "x"),
        ("nowhere/x", "nowhere/x"),
        ("@local/x", "@local/x"),
        ("x", "x"),
        ("local/a/b", "local/a/b"),
        ("./local/x", "./local/x"),
    ],
)
def test_renamed_says_an_old_name_as_names_are_said_now(
    project: Path, name: str, expected: str
) -> None:
    del project
    assert renamed(name) == expected


# ------------------------------------------------------------------- add, fetch, remove


def test_add_clones_an_index_under_the_repositorys_name(git: Git) -> None:
    one = add(f" {THEIRS} ")
    assert one == Flowverse(
        "theirs", THEIRS, under() / "theirs" / INDEX, fetched=True, fixed=False
    )
    assert git.cloned == [(THEIRS, under() / "theirs" / INDEX)]
    assert add(THEIRS, "mine").name == "mine"


@pytest.mark.parametrize(
    ("url", "name", "says"),
    [
        ("  ", "", "no repository"),
        ("https://x/official.git", "", "humanize's own"),
        (THEIRS, LOCAL, "your own flows"),
        (THEIRS, USER, "your own flows"),
        (THEIRS, "../up", "not a flowverse name"),
    ],
)
def test_add_refuses(git: Git, url: str, name: str, says: str) -> None:
    with pytest.raises(ValueError, match=says):
        add(url, name)
    assert git.cloned == []


def test_add_refuses_a_name_taken(git: Git) -> None:
    add(THEIRS)
    with pytest.raises(ValueError, match="already a flowverse"):
        add(THEIRS)


def test_a_failed_add_leaves_nothing_behind(git: Git) -> None:
    git.fails = True
    with pytest.raises(OSError, match="not found"):
        add(THEIRS)
    assert not (under() / "theirs").exists()
    assert named("theirs") is None


def test_fetch_clones_official_the_first_time_and_refreshes_it_after(git: Git) -> None:
    first = fetch(OFFICIAL)
    assert first.fetched
    assert git.cloned == [(verses.OFFICIAL_URL, under() / OFFICIAL / INDEX)]
    fetch(OFFICIAL)
    assert git.refreshed == [under() / OFFICIAL / INDEX]


@pytest.mark.parametrize(
    ("name", "says"),
    [("nothing", "no flowverse"), (LOCAL, "of your own"), ("bare", "no clone")],
)
def test_fetch_refuses(git: Git, name: str, says: str) -> None:
    del git
    (under() / "bare").mkdir(parents=True)
    with pytest.raises(ValueError, match=says):
        fetch(name)


def test_remove_takes_an_index_and_its_flows_away(git: Git) -> None:
    add(THEIRS)
    flow_dir(kept("theirs"), "x")
    assert remove("theirs") is True
    assert not (under() / "theirs").exists()
    assert [one.name for one in under().iterdir()] == []
    assert remove("theirs") is False


def test_remove_refuses_the_places_that_are_always_there(project: Path) -> None:
    del project
    for name in (OFFICIAL, LOCAL, USER):
        with pytest.raises(ValueError, match="always here"):
            remove(name)


# ------------------------------------------------------------------------------- git


class Runs:
    """`subprocess.run`, stood in for: git answering as a test says."""

    def __init__(self) -> None:
        self.asked: list[list[str]] = []
        self.heads: dict[str, str] = {}
        self.status = ""
        self.missing = False
        self.fails = ""

    def __call__(self, argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        self.asked.append(argv)
        if self.missing:
            raise FileNotFoundError("git")
        said = argv[1:]
        if said[0] == "clone":
            if self.fails:
                return subprocess.CompletedProcess(argv, 128, "", self.fails)
            target = Path(said[-1])
            (target / ".git").mkdir(parents=True)
            self.heads[str(target)] = "f" * 40
            return subprocess.CompletedProcess(argv, 0, "", "")
        where, *rest = said[1:]
        if rest == ["rev-parse", "HEAD"]:
            head = self.heads.get(where)
            if head is None:
                return subprocess.CompletedProcess(argv, 128, "", "not a repository")
            return subprocess.CompletedProcess(argv, 0, f"{head}\n", "")
        if rest[0] == "status":
            return subprocess.CompletedProcess(argv, 0, self.status, "")
        return subprocess.CompletedProcess(argv, 0, "", "")


@pytest.fixture
def runs(monkeypatch: pytest.MonkeyPatch) -> Runs:
    held = Runs()
    monkeypatch.setattr(subprocess, "run", held)
    return held


def test_standing_and_edited_ask_git(runs: Runs, tmp_path: Path) -> None:
    runs.heads[str(tmp_path)] = "c" * 40
    assert standing(tmp_path) == "c" * 40
    assert standing(tmp_path / "other") == ""
    assert edited(tmp_path) is False
    runs.status = " M flows/x/1.0.0/flow.yaml\n"
    assert edited(tmp_path) is True
    runs.missing = True
    assert standing(tmp_path) == ""
    assert edited(tmp_path) is False


def test_refresh_fetches_and_resets(runs: Runs, tmp_path: Path) -> None:
    verses.refresh(tmp_path)
    assert [one[3:] for one in runs.asked] == [
        ["fetch", "--depth", "1", "origin", "HEAD"],
        ["reset", "--hard", "FETCH_HEAD"],
    ]


def test_refresh_says_what_git_said(runs: Runs, tmp_path: Path) -> None:
    runs.missing = True
    with pytest.raises(OSError, match="git is not installed"):
        verses.refresh(tmp_path)


def test_clone_moves_a_whole_clone_into_place(runs: Runs, tmp_path: Path) -> None:
    at = tmp_path / "v" / INDEX
    verses.clone("file:///srv/x", at)
    assert (at / ".git").is_dir()
    assert [one.name for one in at.parent.iterdir()] == [INDEX]
    assert runs.asked[0][:4] == ["git", "clone", "--depth", "1"]


def test_clone_clears_what_is_not_a_repository_out_of_the_way(
    runs: Runs, tmp_path: Path
) -> None:
    at = tmp_path / INDEX
    (at / "junk").mkdir(parents=True)
    verses.clone("file:///srv/x", at)
    assert (at / ".git").is_dir()
    assert not (at / "junk").exists()
    assert len(runs.asked) == 2


def test_clone_leaves_a_repository_somebody_else_cloned(
    runs: Runs, tmp_path: Path
) -> None:
    at = tmp_path / INDEX
    (at / "theirs").mkdir(parents=True)
    runs.heads[str(at)] = "b" * 40
    verses.clone("file:///srv/x", at)
    assert (at / "theirs").is_dir()
    assert [one.name for one in tmp_path.iterdir()] == [INDEX]


def test_a_clone_that_fails_leaves_nothing(runs: Runs, tmp_path: Path) -> None:
    runs.fails = "fatal: could not read from remote repository"
    at = tmp_path / INDEX
    with pytest.raises(OSError, match="could not read"):
        verses.clone("file:///srv/x", at)
    assert list(tmp_path.iterdir()) == []
