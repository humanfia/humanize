"""The skills a flow brings: `skills`, with git clones stood in for by directories."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from hmz import machine
from hmz.runtime.flowing import verses
from hmz.runtime.flowing.index import RECORD, Installed
from hmz.runtime.flowing.skills import (
    CARD,
    SKILLS,
    brought,
    cached,
    fetched,
    named,
    packed,
    remote,
    under,
)

if TYPE_CHECKING:
    from pathlib import Path

URL = "https://example.com/acme/skills.git"


def skill(at: Path, name: str) -> Path:
    one = at / SKILLS / name
    one.mkdir(parents=True)
    (one / CARD).write_text(f"# {name}\n")
    return one


class Git:
    """Clones and refreshes, stood in for: a clone is a repository with the skills given."""

    def __init__(self) -> None:
        self.repos: dict[str, list[str]] = {}
        self.cloned: list[str] = []
        self.refreshed: list[Path] = []
        self.down = False

    def clone(self, url: str, at: Path) -> None:
        if url not in self.repos:
            raise OSError(f"no repository at {url}")
        self.cloned.append(url)
        (at / ".git").mkdir(parents=True)
        for name in self.repos[url]:
            skill(at, name)

    def refresh(self, at: Path) -> None:
        if self.down:
            raise OSError("network down")
        self.refreshed.append(at)


@pytest.fixture
def git(monkeypatch: pytest.MonkeyPatch) -> Git:
    held = Git()
    monkeypatch.setattr(verses, "clone", held.clone)
    monkeypatch.setattr(verses, "refresh", held.refresh)
    return held


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        ("deep-research", False),
        ("https://github.com/x/y", True),
        ("x/y#one", True),
        ("git@github.com:x/y", False),
    ],
)
def test_remote_tells_a_repository_from_a_skill_of_the_flow(
    said: str, *, expected: bool
) -> None:
    assert remote(said) is expected


def test_fetched_skills_are_kept_in_this_machines_own_place() -> None:
    assert under() == machine() / SKILLS


def test_cached_names_a_clone_after_its_repository_and_the_whole_url() -> None:
    at = cached(URL)
    assert at.parent == under()
    assert at.name.startswith("acme-skills-")
    assert at == cached(URL)
    assert cached("https://other.example/acme/skills.git") != at
    assert cached("https://x/../..//").parent == under()
    assert cached("https://x/!!/$$").name.count("-") == 0


def test_a_flow_brings_its_own_skills_in_order(tmp_path: Path) -> None:
    skill(tmp_path, "b")
    skill(tmp_path, "a")
    (tmp_path / SKILLS / "not-a-skill").mkdir()
    found = brought(tmp_path)
    assert [(one.name, one.at, one.whose) for one in found] == [
        ("a", tmp_path / SKILLS / "a", "this flow"),
        ("b", tmp_path / SKILLS / "b", "this flow"),
    ]


def test_a_flow_with_no_directory_brings_nothing_of_its_own(git: Git) -> None:
    del git
    assert brought("") == []


def test_a_named_repository_is_cloned_and_every_skill_in_it_brought(
    tmp_path: Path, git: Git
) -> None:
    git.repos[URL] = ["x", "y"]
    found = brought(tmp_path, [URL])
    assert [(one.name, one.whose) for one in found] == [("x", URL), ("y", URL)]
    assert all(one.at.is_relative_to(cached(URL)) for one in found)
    assert git.cloned == [URL]


def test_one_skill_of_a_repository_can_be_asked_for(tmp_path: Path, git: Git) -> None:
    git.repos[URL] = ["x", "y"]
    found = brought(tmp_path, [f"{URL}#y"])
    assert [one.name for one in found] == ["y"]


def test_the_flows_own_skill_wins_a_name(tmp_path: Path, git: Git) -> None:
    skill(tmp_path, "x")
    git.repos[URL] = ["x", "y"]
    assert [(one.name, one.whose) for one in brought(tmp_path, [URL])] == [
        ("x", "this flow"),
        ("y", URL),
    ]
    git.cloned.clear()
    assert [one.name for one in brought(tmp_path, [f"{URL}#x"])] == ["x"]
    assert git.cloned == []


def test_a_skill_the_repository_lacks_is_said_at_once(tmp_path: Path, git: Git) -> None:
    git.repos[URL] = ["x", "y"]
    with pytest.raises(OSError, match="holds no skill called 'z'; it holds x, y"):
        brought(tmp_path, [f"{URL}#z"])


def test_a_repository_that_cannot_be_fetched_is_said_at_once(
    tmp_path: Path, git: Git
) -> None:
    del git
    with pytest.raises(OSError, match="no repository"):
        brought(tmp_path, [URL])


def test_an_empty_url_is_skipped(tmp_path: Path, git: Git) -> None:
    assert brought(tmp_path, ["#x", " "]) == []
    assert git.cloned == []


def test_a_clone_fetched_before_is_refreshed_and_kept_when_that_fails(
    git: Git,
) -> None:
    git.repos[URL] = ["x"]
    at = fetched(URL)
    assert at == cached(URL)
    assert fetched(URL) == at
    git.down = True
    assert fetched(URL) == at
    assert git.cloned == [URL]
    assert git.refreshed == [at]


def test_what_an_install_fetched_is_read_from_the_flow(
    tmp_path: Path, git: Git
) -> None:
    skill(tmp_path, "own")
    skill(tmp_path, "theirs")
    record = Installed(
        verse="v",
        name="f",
        version="1.0.0",
        commit="c",
        repo="r",
        skills={URL: ["theirs"]},
    )
    (tmp_path / RECORD).write_text(record.model_dump_json())
    found = brought(tmp_path, [URL])
    assert [(one.name, one.whose) for one in found] == [
        ("own", "this flow"),
        ("theirs", URL),
    ]
    assert git.cloned == []


def test_named_reads_what_roles_name_off_the_source(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "class R:\n"
        f"    _skills = ('{URL}#x', 'local-one')\n"
        "class S:\n"
        f"    _skills: tuple[str, ...] = ('{URL}', '{URL}#x')\n"
        "    other = ('https://not/skills',)\n"
        "_skills = ('https://top/level',)\n"
    )
    (tmp_path / "b.py").write_text("this is not python(")
    (tmp_path / "c.py").write_text("class T:\n    _skills: tuple[str, ...]\n")
    assert named(tmp_path) == [f"{URL}#x", URL]


def test_packed_copies_what_roles_name_into_the_flow(tmp_path: Path, git: Git) -> None:
    git.repos[URL] = ["x", "y"]
    skill(tmp_path, "y")
    (tmp_path / "__init__.py").write_text(f"class R:\n    _skills = ('{URL}',)\n")
    assert packed(tmp_path) == {URL: ["x"]}
    assert (tmp_path / SKILLS / "x" / CARD).is_file()


def test_packed_is_nothing_for_a_flow_naming_no_repository(tmp_path: Path) -> None:
    (tmp_path / "__init__.py").write_text("x = 1\n")
    assert packed(tmp_path) == {}
