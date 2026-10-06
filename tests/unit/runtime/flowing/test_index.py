"""What an index lists and installing out of one: `index`, with fetching a release stood in for."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pydantic
import pytest

from hmz.flows import FlowNotFound
from hmz.runtime.flowing import loading
from hmz.runtime.flowing.index import (
    RECORD,
    RESERVED,
    Index,
    Installed,
    Release,
    Update,
    index,
    install,
    installed,
    kept,
    plan,
    reserved,
    satisfies,
    uninstall,
    updates,
)
from hmz.runtime.flowing.verses import INDEX, OFFICIAL, Flowverse, under
from tests.unit.runtime.flowing.doubles_u10 import (
    COMMIT,
    cloned,
    flow_dir,
    flow_file,
    release,
    settle,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

THEIRS = "theirs"


@pytest.fixture
def theirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A fetched flowverse called `theirs`: the clone of its index."""
    settle(monkeypatch, tmp_path)
    return cloned(under() / THEIRS / INDEX, "file:///srv/theirs.git")


# ----------------------------------------------------------------------------- ranges


@pytest.mark.parametrize(
    ("version", "spec", "expected"),
    [
        ("0.1.5", ">=0.1.0,<0.2.0", True),
        ("0.2.0", ">=0.1.0,<0.2.0", False),
        ("1.0.0", "1.0.0", True),
        ("1.0.1", "1.0.0", False),
        ("1.0.1", " != 1.0.0 ", True),
        ("2.0.0-rc.1", ">=1.0.0", True),
    ],
)
def test_satisfies_holds_every_clause(
    version: str, spec: str, *, expected: bool
) -> None:
    assert satisfies(version, spec) is expected


@pytest.mark.parametrize(
    ("version", "spec"), [("x", "1.0.0"), ("1.0.0", ""), ("1.0.0", ">=x")]
)
def test_satisfies_refuses_what_is_no_version(version: str, spec: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 -- both say only that much
        satisfies(version, spec)


# --------------------------------------------------------------------------- releases


def test_a_release_reads_what_a_manifest_says() -> None:
    one = Release.model_validate(
        {
            "name": "kernel",
            "version": "1.0.0",
            "repo": " Alice/Kernel ",
            "commit": COMMIT.upper(),
            "subdir": "/flows/./kernel/",
            "description": None,
            "dependencies": {"alice/base": ">=0.1.0"},
            "later": "ignored",
        }
    )
    assert (one.version, one.repo, one.commit, one.subdir) == (
        "1.0.0",
        "Alice/Kernel",
        COMMIT,
        "flows/kernel",
    )
    assert one.description == ""
    assert (one.listed, one.owned, one.url) == (
        "kernel",
        "alice",
        "https://github.com/Alice/Kernel",
    )
    assert one.model_copy(update={"owner": "alice"}).listed == "alice/kernel"


@pytest.mark.parametrize(
    ("repo", "owned"),
    [
        ("https://github.com/Alice/x", "alice"),
        ("https://github.com/humanfia/../evil/x", "evil"),
        ("https://github.com/humanfia/%2e%2e/evil/x", "evil"),
        ("https://gitlab.com/alice/x", ""),
        ("file:///srv/x", ""),
    ],
)
def test_who_owns_a_release_is_read_as_it_is_fetched(repo: str, owned: str) -> None:
    one = Release(name="x", version="1.0.0", repo=repo, commit=COMMIT)
    assert one.owned == owned
    assert one.url == repo


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "Bad-Name"),
        ("version", "1.0"),
        ("version", 1.0),
        ("repo", "not a repo"),
        ("commit", "abc"),
        ("subdir", "../up"),
        ("subdir", ".hidden"),
        ("dependencies", {"Bad Name": ">=1.0.0"}),
        ("dependencies", {"ok": "whenever"}),
    ],
)
def test_a_release_refuses(field: str, value: object) -> None:
    said: dict[str, object] = {
        "name": "x",
        "version": "1.0.0",
        "repo": "o/r",
        "commit": COMMIT,
    }
    said[field] = value
    with pytest.raises(pydantic.ValidationError):
        Release.model_validate(said)


def releases(*versions: str, flow: str = "x", owner: str = "") -> tuple[Release, ...]:
    return tuple(
        Release(name=flow, version=one, repo="o/r", commit=COMMIT, owner=owner)
        for one in versions
    )


def test_an_index_finds_the_release_to_install() -> None:
    listed = Index(
        THEIRS,
        releases("1.0.0", "1.1.0", "2.0.0-rc.1")
        + releases("0.1.0", flow="y", owner="al"),
    )
    assert listed.flows() == ["al/y", "x"]
    assert [one.version for one in listed.versions("x")] == [
        "2.0.0-rc.1",
        "1.1.0",
        "1.0.0",
    ]
    newest = listed.newest("x")
    assert newest is not None
    assert newest.version == "1.1.0"
    within = listed.newest("x", "<1.1.0")
    assert within is not None
    assert within.version == "1.0.0"
    assert listed.newest("x", ">=3.0.0") is None
    assert listed.newest("nothing") is None
    found = listed.release("al/y", "0.1.0")
    assert found is not None
    assert found.owner == "al"
    assert listed.release("x", "9.9.9") is None
    only = Index(THEIRS, releases("2.0.0-rc.1"))
    prerelease = only.newest("x")
    assert prerelease is not None
    assert prerelease.version == "2.0.0-rc.1"


# ----------------------------------------------------------------------------- reading


def test_reserved_holds_the_packages_own_names() -> None:
    assert reserved() >= RESERVED
    assert "chat" in reserved()


def test_reading_an_index(theirs: Path) -> None:
    release(theirs, "x", "1.0.0")
    release(theirs, "x", "1.1.0")
    release(theirs, "kernel", "0.1.0", owner="alice")
    listed = index(THEIRS)
    assert listed.verse == THEIRS
    assert [(one.listed, one.version) for one in listed.releases] == [
        ("alice/kernel", "0.1.0"),
        ("x", "1.1.0"),
        ("x", "1.0.0"),
    ]
    assert listed.skipped == ()
    named = Flowverse(
        THEIRS, "file:///srv/theirs.git", theirs, fetched=True, fixed=False
    )
    assert index(named) == listed


SKIPS: list[tuple[Callable[[Path], object], str]] = [
    (lambda at: release(at, "x", "1.0.0", name="y"), "is not the directory"),
    (lambda at: release(at, "x", "1.0.0", version="1.0.1"), "is not the directory"),
    (lambda at: release(at, "x", "1.0.0", commit="nope"), "commit"),
    (lambda at: release(at, "chat", "1.0.0"), "built into humanize"),
    (lambda at: release(at, "x", "1.0.0", owner="alice", repo="bob/x"), "bob's"),
    (lambda at: (at / "flows" / "Not_A_User" / "x").mkdir(parents=True), "neither"),
    (
        lambda at: (at / "flows" / "humanfia" / "x").mkdir(parents=True),
        "listed bare",
    ),
    (
        lambda at: release(at, "x", "1.0.0").write_text(": : :"),
        "unreadable",
    ),
    (lambda at: release(at, "x", "1.0.0").write_text("- a list"), "not a mapping"),
    (lambda at: release(at, "x", "1.0.0").unlink(), "no flow.yaml"),
]


@pytest.mark.parametrize(("write", "says"), SKIPS)
def test_reading_an_index_skips_what_does_not_read(
    theirs: Path, write: Callable[[Path], object], says: str
) -> None:
    write(theirs)
    release(theirs, "fine", "1.0.0")
    listed = index(THEIRS)
    assert [one.listed for one in listed.releases] == ["fine"]
    (skipped,) = listed.skipped
    assert says in skipped.why


def test_official_lists_bare_only_humanfias_own(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settle(monkeypatch, tmp_path)
    at = cloned(under() / OFFICIAL / INDEX, "https://github.com/humanfia/flowverse")
    release(at, "ours", "1.0.0")
    release(at, "stranger", "1.0.0", repo="someone/stranger")
    listed = index(OFFICIAL)
    assert [one.listed for one in listed.releases] == ["ours"]
    assert "only humanfia's" in listed.skipped[0].why


def test_an_index_not_fetched_lists_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    settle(monkeypatch, tmp_path)
    assert index(OFFICIAL) == Index(OFFICIAL)
    assert index("local") == Index("local")
    assert index("nowhere") == Index("nowhere")


# ---------------------------------------------------------------- installing, planned


def record(name: str, version: str, owner: str = "", **said: object) -> Installed:
    """Writes the record of a flow installed out of `theirs`, as an install leaves it."""
    one = Installed.model_validate(
        {
            "verse": THEIRS,
            "name": name,
            "version": version,
            "commit": COMMIT,
            "repo": "o/r",
            "owner": owner,
            **said,
        }
    )
    at = kept(THEIRS) / one.listed
    at.mkdir(parents=True, exist_ok=True)
    (at / RECORD).write_text(one.model_dump_json())
    return one


def test_installed_reads_the_records(theirs: Path) -> None:
    del theirs
    plain = record("x", "1.0.0")
    owned = record("kernel", "0.1.0", owner="alice")
    (kept(THEIRS) / "by_hand").mkdir()
    record("liar", "1.0.0").model_dump_json()
    (kept(THEIRS) / "liar" / RECORD).write_text(
        plain.model_copy(update={"name": "other"}).model_dump_json()
    )
    (kept(THEIRS) / "bad").mkdir()
    (kept(THEIRS) / "bad" / RECORD).write_text("{not json")
    assert installed(THEIRS) == [owned, plain]
    assert installed() == [owned, plain]
    assert (plain.called, owned.called) == ("@theirs/x", "@theirs/alice/kernel")
    assert owned.at == kept(THEIRS) / "alice" / "kernel"


def test_updates_offer_what_is_newer(theirs: Path) -> None:
    release(theirs, "x", "1.0.0")
    release(theirs, "x", "1.2.0")
    release(theirs, "x", "2.0.0-rc.1")
    release(theirs, "y", "1.0.0-rc.1")
    release(theirs, "y", "1.0.0-rc.2")
    release(theirs, "z", "1.0.0")
    x = record("x", "1.0.0")
    y = record("y", "1.0.0-rc.1")
    record("z", "1.0.0")
    assert updates() == [Update(x, "1.2.0"), Update(y, "1.0.0-rc.2")]


def test_plan_puts_what_a_release_needs_first(theirs: Path) -> None:
    release(
        theirs, "app", "1.0.0", dependencies={"lib": ">=1.0.0", "alice/base": "0.1.0"}
    )
    release(theirs, "lib", "1.0.0", dependencies={"alice/base": ">=0.1.0"})
    release(theirs, "lib", "1.5.0", dependencies={"alice/base": ">=0.1.0"})
    release(theirs, "base", "0.1.0", owner="alice")
    assert [(one.listed, one.version) for one in plan(THEIRS, "app")] == [
        ("alice/base", "0.1.0"),
        ("lib", "1.5.0"),
        ("app", "1.0.0"),
    ]
    assert [one.listed for one in plan(THEIRS, "lib", "1.0.0")] == ["alice/base", "lib"]


def test_plan_leaves_out_what_is_installed_and_takes_the_range(theirs: Path) -> None:
    release(theirs, "app", "1.0.0", dependencies={"lib": ">=1.0.0"})
    release(theirs, "lib", "1.5.0")
    record("lib", "1.0.0")
    assert [one.listed for one in plan(THEIRS, "app")] == ["app"]


PLANS: list[tuple[list[tuple[str, str, dict[str, Any]]], tuple[str, ...], str]] = [
    ([], ("nowhere", "x"), "no flowverse called"),
    ([], ("local", "x"), "your own flows"),
    ([], (OFFICIAL, "x"), "not been fetched"),
    ([], (THEIRS, "x"), "lists no flow called x"),
    ([("x", "1.0.0", {})], (THEIRS, "x", "2.0.0"), "no release 2.0.0 of x"),
    (
        [("x", "1.0.0", {"dependencies": {"x": ">=1.0.0"}})],
        (THEIRS, "x"),
        "needs itself",
    ),
    (
        [
            ("a", "1.0.0", {"dependencies": {"b": ">=1.0.0"}}),
            ("b", "1.0.0", {"dependencies": {"a": ">=1.0.0"}}),
        ],
        (THEIRS, "a"),
        "needs itself, through a -> b -> a",
    ),
    (
        [("a", "1.0.0", {"dependencies": {"b": ">=2.0.0"}}), ("b", "1.0.0", {})],
        (THEIRS, "a"),
        "no release of it in that range",
    ),
    (
        [
            ("a", "1.0.0", {"dependencies": {"b": ">=1.0.0", "c": ">=2.0.0"}}),
            ("b", "1.0.0", {"dependencies": {"c": "<1.5.0"}}),
            ("c", "1.0.0", {}),
            ("c", "2.0.0", {}),
        ],
        (THEIRS, "a"),
        "is what the rest of this install needs",
    ),
]


@pytest.mark.parametrize(("setup", "asked", "says"), PLANS)
def test_plan_refuses(
    theirs: Path,
    setup: list[tuple[str, str, dict[str, Any]]],
    asked: tuple[str, ...],
    says: str,
) -> None:
    for flow, version, said in setup:
        release(theirs, flow, version, **said)
    with pytest.raises(ValueError, match=says):
        plan(*asked)


def test_plan_refuses_to_break_what_is_installed(theirs: Path) -> None:
    release(theirs, "lib", "2.0.0")
    record("app", "1.0.0", dependencies={"lib": "<2.0.0"})
    with pytest.raises(ValueError, match="would break it"):
        plan(THEIRS, "lib")


def test_plan_refuses_a_flow_where_a_user_of_its_name_is(theirs: Path) -> None:
    release(theirs, "alice", "1.0.0")
    record("kernel", "0.1.0", owner="alice")
    with pytest.raises(ValueError, match="uninstall alice/kernel first"):
        plan(THEIRS, "alice")


# ------------------------------------------------------------------ installing, done


@pytest.fixture
def checkout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[tuple[str, str]]:
    """A release's repository, fetched: `loading.pinned` answering with a directory here."""
    fetched: list[tuple[str, str]] = []
    at = tmp_path / "checkout"
    at.mkdir()

    def pinned(url: str, rev: str | None) -> Path:
        if url.endswith("/gone"):
            raise FlowNotFound(f"{url} could not be fetched")
        fetched.append((url, rev or ""))
        return at

    monkeypatch.setattr(loading, "pinned", pinned)
    return fetched


def test_install_copies_a_release_into_place_with_its_record(
    theirs: Path, checkout: list[tuple[str, str]], tmp_path: Path
) -> None:
    entry = flow_dir(tmp_path / "checkout" / "flows", "x")
    (entry.parent / "__pycache__").mkdir()
    release(theirs, "x", "1.0.0", subdir="flows/x", ref="v1.0.0")
    (done,) = install(THEIRS, "x")
    assert (done.name, done.version, done.ref, done.subdir) == (
        "x",
        "1.0.0",
        "v1.0.0",
        "flows/x",
    )
    assert checkout == [("https://github.com/humanfia/x", COMMIT)]
    at = kept(THEIRS) / "x"
    assert (at / "__init__.py").read_text() == entry.read_text()
    assert not (at / "__pycache__").exists()
    assert installed(THEIRS) == [done]
    assert install(THEIRS, "x") == [done]
    assert len(checkout) == 1
    assert sorted(one.name for one in kept(THEIRS).iterdir()) == ["x"]


def test_install_makes_a_one_file_flow_a_directory(
    theirs: Path, checkout: list[tuple[str, str]], tmp_path: Path
) -> None:
    del checkout
    flow_file(tmp_path / "checkout", "x")
    release(theirs, "x", "1.0.0")
    release(theirs, "x", "1.1.0")
    install(THEIRS, "x", "1.0.0")
    (done,) = install(THEIRS, "x")
    assert done.version == "1.1.0"
    assert (kept(THEIRS) / "x" / "__init__.py").is_file()
    assert [one.version for one in installed(THEIRS)] == ["1.1.0"]


@pytest.mark.parametrize(
    ("said", "raised", "says"),
    [
        ({}, ValueError, "has no flow in its root"),
        ({"repo": "https://github.com/o/gone"}, OSError, "could not be fetched"),
    ],
)
def test_install_refuses(
    theirs: Path,
    checkout: list[tuple[str, str]],
    said: dict[str, Any],
    raised: type[Exception],
    says: str,
) -> None:
    del checkout
    release(theirs, "x", "1.0.0", **said)
    with pytest.raises(raised, match=says):
        install(THEIRS, "x")
    assert installed(THEIRS) == []


def test_uninstall_takes_a_flow_away(theirs: Path) -> None:
    del theirs
    record("x", "1.0.0")
    record("kernel", "0.1.0", owner="alice")
    assert uninstall(THEIRS, "x") is True
    assert uninstall(THEIRS, "x") is False
    assert uninstall(THEIRS, "alice/kernel") is True
    assert not (kept(THEIRS) / "alice").exists()
    assert uninstall(THEIRS, "nothing") is False


def test_uninstall_refuses_what_another_flow_needs(theirs: Path) -> None:
    del theirs
    record("lib", "1.0.0")
    record("app", "1.0.0", dependencies={"lib": ">=1.0.0"})
    with pytest.raises(ValueError, match="@theirs/app needs lib"):
        uninstall(THEIRS, "lib")


def test_a_record_whose_release_is_not_semver_is_not_an_install(theirs: Path) -> None:
    del theirs
    with pytest.raises(pydantic.ValidationError):
        Installed(verse=THEIRS, name="x", version="one", commit=COMMIT, repo="o/r")
    good = record("x", "1.0.0")
    (good.at / RECORD).write_text(good.model_dump_json().replace("1.0.0", "one"))
    assert installed(THEIRS) == []
    assert uninstall(THEIRS, "x") is False
