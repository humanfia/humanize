"""What a flowverse's index lists, and what installing out of one comes to, with no git at all.

An index is a directory of YAML, `flows/<flow>/<version>/flow.yaml`, so reading one is reading
files a test can write under its own directory and hand over as a flowverse that says it was
fetched. What is checked here is everything that is decided before a repository is reached:
which manifests are releases and why the rest are not, which versions a range takes, which
release is the one to install when nobody said, what an install comes to once what it needs is
counted -- in what order, and what it refuses -- and which installed flows have something newer.
The records an installed flow carries are files too, so what is installed and taking one away
are here as well. Fetching a release is the integration tier's.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import pytest

from hmz import home
from hmz.runtime.flowing import finding
from hmz.runtime.flowing import index as indexing
from hmz.runtime.flowing.finding import BUILTIN_AT, offered
from hmz.runtime.flowing.index import (
    RECORD,
    RELEASE,
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
    split,
    uninstall,
    updates,
)
from hmz.runtime.flowing.verses import FLOWS, LOCAL, OFFICIAL, USER, Flowverse
from tests.flows.indexes import listed, manifest, release

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

#: A commit, written out in full, which is the one way a manifest may name one.
SHA = "0123456789abcdef0123456789abcdef01234567"

#: Where every release here says it lives. Nothing here fetches it.
REPO = "file:///nowhere/flows"

#: What every manifest here says unless a test says otherwise.
BASE: Mapping[str, object] = release("loop", "0.1.0", REPO, SHA)


@pytest.fixture
def verse(tmp_path: Path) -> Flowverse:
    """An index, as a directory a test writes manifests into and calls fetched."""
    return Flowverse(
        name="theirs",
        url="file:///somewhere/index",
        at=tmp_path / "theirs",
        fetched=True,
        fixed=False,
    )


def _read(
    verse: Flowverse, said: object, flow: str = "loop", version: str = "0.1.0"
) -> Release | str:
    """One manifest written where it says, and what reading the index made of it.

    Returns:
      The release, or why it was skipped.
    """
    manifest(verse.at, flow, version, said)
    read = index(verse)
    assert len(read.releases) + len(read.skipped) == 1
    if read.releases:
        return read.releases[0]
    return read.skipped[0].why


def _release(
    name: str, version: str, needs: Mapping[str, str] | None = None
) -> Release:
    return Release(
        name=name,
        version=version,
        repo=REPO,
        commit=SHA,
        dependencies=dict(needs or {}),
    )


def _installed(
    name: str,
    version: str,
    needs: Mapping[str, str] | None = None,
    verse: str = "theirs",
) -> Installed:
    return Installed(
        verse=verse,
        name=name,
        version=version,
        commit=SHA,
        repo=REPO,
        dependencies=dict(needs or {}),
    )


def _recorded(one: Installed, at: Path | None = None) -> Path:
    """Writes an installed flow's directory and its record, as an install leaves them."""
    where = at or one.at
    where.mkdir(parents=True, exist_ok=True)
    (where / "__init__.py").write_text("", encoding="utf-8")
    (where / RECORD).write_text(one.model_dump_json(), encoding="utf-8")
    return where


def _planning(
    monkeypatch: pytest.MonkeyPatch,
    releases: Sequence[Release],
    held: Sequence[Installed] = (),
) -> None:
    """Has an install see this index and these installs, rather than a clone and a home."""

    def lists(verse: str) -> Index:
        return Index(verse, tuple(releases))

    def holding(verse: str = "") -> list[Installed]:
        return [one for one in held if not verse or one.verse == verse]

    monkeypatch.setattr(indexing, "_index_of", lists)
    monkeypatch.setattr(indexing, "installed", holding)


def _exactly(said: str) -> str:
    """A pattern matching what was said and nothing more, as `pytest.raises` takes one."""
    return f"^{re.escape(said)}$"


def _named(planned: Sequence[Release]) -> list[str]:
    return [f"{one.name} {one.version}" for one in planned]


# ------------------------------------------------------------------- reading a manifest


def test_a_manifest_that_says_what_a_release_is_is_listed(verse: Flowverse) -> None:
    said = _read(
        verse,
        release(
            "loop",
            "0.1.0",
            REPO,
            SHA,
            description="Goes round.",
            ref="v0.1.0",
            subdir="loop",
            license="MIT",
            dependencies={"helper": ">=0.1.0,<0.2.0"},
        ),
    )

    assert said == Release(
        name="loop",
        version="0.1.0",
        description="Goes round.",
        repo=REPO,
        ref="v0.1.0",
        commit=SHA,
        subdir="loop",
        license="MIT",
        dependencies={"helper": ">=0.1.0,<0.2.0"},
    )


def test_what_a_manifest_leaves_out_is_nothing_rather_than_a_reason_to_skip_it(
    verse: Flowverse,
) -> None:
    """Four things every release says; the rest it may leave to whoever reads the code."""
    said = _read(verse, BASE)

    assert isinstance(said, Release)
    assert (said.description, said.ref, said.subdir, said.license) == ("", "", "", "")
    assert said.dependencies == {}


@pytest.mark.parametrize("key", ["name", "version", "repo", "commit"])
def test_a_manifest_missing_one_of_the_four_things_every_release_says_is_skipped(
    verse: Flowverse, key: str
) -> None:
    said = _read(verse, {k: v for k, v in BASE.items() if k != key})

    assert said == f"{key}: Field required"


@pytest.mark.parametrize(
    ("key", "value", "why"),
    [
        ("name", "Loop", "is not a flow name"),
        ("name", "1loop", "is not a flow name"),
        ("name", "lo-op", "is not a flow name"),
        ("name", "", "is not a flow name"),
        ("version", "1.0", "is not SemVer"),
        ("version", "v0.1.0", "is not SemVer"),
        ("version", "latest", "is not SemVer"),
        ("version", 1.0, "'1.0' is not SemVer"),
        ("repo", "nowhere", "neither owner/repo nor a URL"),
        ("repo", "ftp://host/x", "neither owner/repo nor a URL"),
        ("repo", "/a/path/on/somebody/s/machine", "neither owner/repo nor a URL"),
        ("repo", "owner/repo/more", "neither owner/repo nor a URL"),
        ("commit", "0123456", "40 hex"),
        ("commit", "g" * 40, "40 hex"),
        ("commit", "a" * 41, "40 hex"),
        ("commit", "main", "40 hex"),
        ("subdir", "../up", "not a directory inside the repository"),
        ("subdir", "a/../../b", "not a directory inside the repository"),
        ("subdir", ".hidden", "not a directory inside the repository"),
        ("dependencies", {"Helper": ">=0.1.0"}, "is not a flow name"),
        ("dependencies", {"helper": "^0.1.0"}, "is not a version range"),
        ("dependencies", {"helper": "~0.1"}, "is not a version range"),
        ("dependencies", {"helper": ""}, "is not a version range"),
        ("dependencies", {"helper": ">=0.1.0,"}, "is not a version range"),
        ("dependencies", {"helper": ">=0.1"}, "is not a version range"),
        ("dependencies", {"helper": 1}, "valid string"),
        ("dependencies", ["helper"], "valid dictionary"),
    ],
)
def test_a_field_written_wrong_skips_the_release_and_says_which(
    verse: Flowverse, key: str, value: object, why: str
) -> None:
    """One bad file in somebody's index is a line in a list, not a reason to read none of it."""
    said = _read(verse, {**BASE, key: value})

    assert isinstance(said, str)
    assert said.startswith(key)
    assert why in said


def test_a_commit_is_read_in_lower_case_and_a_repository_without_the_space_around_it(
    verse: Flowverse,
) -> None:
    said = _read(verse, {**BASE, "commit": f" {SHA.upper()} ", "repo": " owner/repo "})

    assert isinstance(said, Release)
    assert said.commit == SHA
    assert said.repo == "owner/repo"


@pytest.mark.parametrize(
    ("written", "read"),
    [
        ("", ""),
        (".", ""),
        ("/", ""),
        ("loop", "loop"),
        ("/flows/loop/", "flows/loop"),
        ("./flows/loop", "flows/loop"),
        ("a_b/c-d.e", "a_b/c-d.e"),
    ],
)
def test_a_directory_is_read_as_the_one_path_inside_the_repository_it_names(
    verse: Flowverse, written: str, read: str
) -> None:
    said = _read(verse, {**BASE, "subdir": written})

    assert isinstance(said, Release)
    assert said.subdir == read


def test_a_range_is_kept_as_it_was_written(verse: Flowverse) -> None:
    """Spaces and all: it is shown to whoever reads what a flow needs, and read when checked."""
    said = _read(verse, {**BASE, "dependencies": {"helper": ">= 0.1.0, < 0.2.0"}})

    assert isinstance(said, Release)
    assert said.dependencies == {"helper": ">= 0.1.0, < 0.2.0"}
    assert satisfies("0.1.9", said.dependencies["helper"])


def test_keys_nobody_here_knows_are_let_through_unread(verse: Flowverse) -> None:
    """So that an index written for a later humanize still lists for this one."""
    said = _read(
        verse,
        {
            **BASE,
            "homepage": "https://example.invalid/loop",
            "maintainers": ["somebody"],
            "future": {"nested": 1},
        },
    )

    assert isinstance(said, Release)
    assert set(said.model_dump()) == {
        "name",
        "version",
        "description",
        "repo",
        "ref",
        "commit",
        "subdir",
        "license",
        "dependencies",
    }


@pytest.mark.parametrize(
    "written", ["- name\n- version\n", "just some words\n", "42\n", ""]
)
def test_a_manifest_that_is_not_a_mapping_is_skipped(
    verse: Flowverse, written: str
) -> None:
    assert _read(verse, written) == "not a mapping of keys to values"


def test_a_manifest_that_is_not_yaml_is_skipped_with_what_the_parser_said(
    verse: Flowverse,
) -> None:
    said = _read(verse, "name: [never closed\n")

    assert isinstance(said, str)
    assert said.startswith("unreadable: ")
    assert "\n" not in said  # the first line of it, for a list one line a release


def test_a_version_directory_with_no_manifest_in_it_is_skipped(
    verse: Flowverse,
) -> None:
    (verse.at / FLOWS / "loop" / "0.1.0").mkdir(parents=True)

    read = index(verse)

    assert read.releases == ()
    assert [(one.at, one.why) for one in read.skipped] == [
        (verse.at / FLOWS / "loop" / "0.1.0" / RELEASE, f"no {RELEASE} in it")
    ]


def test_a_manifest_naming_another_flow_than_its_directory_is_skipped(
    verse: Flowverse,
) -> None:
    """Or two directories could each say they were the same release of one flow."""
    said = _read(verse, {**BASE, "name": "other"})

    assert said == "name other is not the directory it is in, loop"


def test_a_manifest_naming_another_version_than_its_directory_is_skipped(
    verse: Flowverse,
) -> None:
    said = _read(verse, {**BASE, "version": "0.2.0"})

    assert said == "version 0.2.0 is not the directory it is in, 0.1.0"


@pytest.mark.parametrize("name", sorted(RESERVED))
def test_an_index_may_not_offer_a_flow_under_one_of_humanize_s_own_names(
    verse: Flowverse, name: str
) -> None:
    """`chat` is the same flow on every machine, whatever anybody has fetched."""
    said = _read(verse, {**BASE, "name": name}, flow=name)

    assert said == f"{name} is built into humanize; nothing may be installed over it"


def test_every_flow_in_the_package_is_a_name_nothing_may_be_installed_over() -> None:
    """Whatever the package holds today, and the names it is to hold, both."""
    assert set(offered(BUILTIN_AT)) <= reserved()
    assert reserved() >= RESERVED


def test_a_flow_the_package_holds_is_reserved_whether_or_not_it_is_written_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, verse: Flowverse
) -> None:
    """The list is what the package is to hold; the package is what it holds now."""
    package = tmp_path / "package"
    (package / "brand_new").mkdir(parents=True)
    (package / "brand_new" / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(finding, "BUILTIN_AT", package)

    assert "brand_new" in reserved()
    assert _read(verse, {**BASE, "name": "brand_new"}, flow="brand_new") == (
        "brand_new is built into humanize; nothing may be installed over it"
    )


def test_only_the_directories_of_the_flows_directory_are_read(
    verse: Flowverse,
) -> None:
    """An index is a repository, with a README, a CI and a git directory of its own beside."""
    listed(verse.at, BASE)
    (verse.at / FLOWS / "README.md").write_text("# what is here\n", encoding="utf-8")
    manifest(verse.at / FLOWS / ".github", "ci", "0.1.0", BASE)
    manifest(verse.at, ".draft", "0.1.0", BASE)
    (verse.at / FLOWS / "loop" / ".0.2.0").mkdir()
    # And nothing outside `flows/`, however much like a manifest it looks.
    elsewhere = verse.at / "loop" / "0.3.0" / RELEASE
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_text(json.dumps({**BASE, "version": "0.3.0"}), encoding="utf-8")

    read = index(verse)

    assert _named(read.releases) == ["loop 0.1.0"]
    assert read.skipped == ()


# ------------------------------------------------------------------- reading an index


def test_an_index_lists_its_flows_alphabetically_and_each_one_s_releases_newest_first(
    verse: Flowverse,
) -> None:
    """By SemVer, which is not the order the directories sort in."""
    listed(
        verse.at,
        *(
            release(name, version, REPO, SHA)
            for name, version in [
                ("loop", "0.9.0"),
                ("loop", "0.10.0"),
                ("loop", "1.0.0-rc.1"),
                ("loop", "1.0.0"),
                ("loop", "0.2.0"),
                ("alpha", "0.1.0"),
            ]
        ),
    )

    read = index(verse)

    assert read.verse == "theirs"
    assert read.flows() == ["alpha", "loop"]
    assert _named(read.releases) == [
        "alpha 0.1.0",
        "loop 1.0.0",
        "loop 1.0.0-rc.1",
        "loop 0.10.0",
        "loop 0.9.0",
        "loop 0.2.0",
    ]
    assert [one.version for one in read.versions("loop")] == [
        "1.0.0",
        "1.0.0-rc.1",
        "0.10.0",
        "0.9.0",
        "0.2.0",
    ]
    assert read.versions("nothing") == []


def test_one_release_is_found_by_its_version(verse: Flowverse) -> None:
    listed(verse.at, BASE, {**BASE, "version": "0.2.0"})
    read = index(verse)

    found = read.release("loop", "0.2.0")

    assert found is not None
    assert found.version == "0.2.0"
    assert read.release("loop", "9.9.9") is None
    assert read.release("nothing", "0.1.0") is None


def test_an_index_is_read_by_the_name_it_is_listed_under(
    verse: Flowverse, monkeypatch: pytest.MonkeyPatch
) -> None:
    listed(verse.at, BASE)

    def named(name: str) -> Flowverse | None:
        return verse if name == verse.name else None

    monkeypatch.setattr(indexing, "named", named)

    assert _named(index("theirs").releases) == ["loop 0.1.0"]
    assert index("nobodys") == Index("nobodys")


@pytest.mark.parametrize(
    ("url", "fetched"),
    [("file:///somewhere/index", False), ("", True)],
    ids=["not fetched", "not an index"],
)
def test_a_place_that_is_not_an_index_as_it_stands_lists_nothing(
    tmp_path: Path, url: str, fetched: bool
) -> None:
    """One never fetched, and a directory of somebody's own flows, which is not an index."""
    listed(tmp_path / "there", BASE)
    one = Flowverse(
        name="there", url=url, at=tmp_path / "there", fetched=fetched, fixed=False
    )

    assert index(one) == Index("there")


@pytest.mark.parametrize("name", [OFFICIAL, LOCAL, USER, "nobodys"])
def test_the_places_always_there_list_nothing_until_an_index_is_fetched(
    name: str,
) -> None:
    """Humanize's own before it is fetched, and the two directories your own flows live in."""
    assert index(name) == Index(name)


def test_a_release_on_github_is_fetched_from_github_and_any_other_from_where_it_says() -> (
    None
):
    on_github = Release(name="loop", version="0.1.0", repo="owner/repo", commit=SHA)

    assert on_github.url == "https://github.com/owner/repo"
    assert _release("loop", "0.1.0").url == REPO
    assert str(_release("loop", "1.2.3-rc.1").semver) == "1.2.3-rc.1"


# ------------------------------------------------------------------- ranges


@pytest.mark.parametrize(
    ("version", "spec", "taken"),
    [
        ("0.1.5", ">=0.1.0,<0.2.0", True),
        ("0.1.0", ">=0.1.0,<0.2.0", True),
        ("0.2.0", ">=0.1.0,<0.2.0", False),
        ("0.0.9", ">=0.1.0,<0.2.0", False),
        ("1.0.0", "1.0.0", True),
        ("1.0.1", "1.0.0", False),
        ("1.0.0", "==1.0.0", True),
        ("1.0.0", "!=1.0.0", False),
        ("1.0.1", "!=1.0.0", True),
        ("2.0.0", ">1.0.0", True),
        ("1.0.0", "<=1.0.0", True),
        ("1.0.0", " >= 1.0.0 , < 2.0.0 ", True),
        # A prerelease comes before the release it is a candidate for.
        ("1.0.0-rc.1", "<1.0.0", True),
        ("1.0.0-rc.1", ">=1.0.0", False),
        ("1.0.0-rc.2", ">1.0.0-rc.1", True),
    ],
)
def test_a_range_takes_a_version_when_every_one_of_its_clauses_does(
    version: str, spec: str, taken: bool
) -> None:
    assert satisfies(version, spec) is taken


@pytest.mark.parametrize(
    "spec", ["", " ", ",", ">=0.1.0,", "^0.1.0", "~0.1.0", ">=0.1", "=>0.1.0", "latest"]
)
def test_what_is_not_a_range_is_refused(spec: str) -> None:
    with pytest.raises(ValueError, match="is not a version range"):
        satisfies("0.1.0", spec)


def test_what_is_not_a_version_is_refused() -> None:
    with pytest.raises(ValueError, match="not valid SemVer"):
        satisfies("0.1", ">=0.1.0")


# ------------------------------------------------------------------- the one to install


def test_the_release_to_install_is_the_newest_that_is_not_a_prerelease() -> None:
    """A release that says it is not ready is installed only where it is asked for."""
    listing = Index(
        "theirs",
        (
            _release("loop", "0.3.0-rc.1"),
            _release("loop", "0.2.0"),
            _release("loop", "0.1.0"),
        ),
    )

    newest = listing.newest("loop")

    assert newest is not None
    assert newest.version == "0.2.0"


def test_a_flow_with_nothing_but_prereleases_installs_the_newest_of_those() -> None:
    listing = Index(
        "theirs", (_release("loop", "0.1.0-rc.1"), _release("loop", "0.1.0-rc.2"))
    )

    newest = listing.newest("loop")

    assert newest is not None
    assert newest.version == "0.1.0-rc.2"


def test_the_release_to_install_in_a_range_is_the_newest_in_it() -> None:
    listing = Index(
        "theirs",
        (
            _release("loop", "0.1.0"),
            _release("loop", "0.1.5"),
            _release("loop", "0.1.6-rc.1"),
            _release("loop", "0.2.0"),
        ),
    )

    in_range = listing.newest("loop", ">=0.1.0,<0.2.0")
    nothing_but_a_prerelease = listing.newest("loop", ">0.1.5,<0.2.0")

    assert in_range is not None
    assert in_range.version == "0.1.5"
    assert nothing_but_a_prerelease is not None
    assert nothing_but_a_prerelease.version == "0.1.6-rc.1"
    assert listing.newest("loop", ">=1.0.0") is None
    assert listing.newest("nothing") is None


# ------------------------------------------------------------------- names and places


@pytest.mark.parametrize(
    ("called", "parts"),
    [
        ("theirs/loop", ("theirs", "loop")),
        ("loop", (OFFICIAL, "loop")),
        (f"{OFFICIAL}/loop", (OFFICIAL, "loop")),
    ],
)
def test_a_flow_s_name_says_which_flowverse_it_was_installed_out_of(
    called: str, parts: tuple[str, str]
) -> None:
    """A bare name is one of humanize's own, as everywhere else a flow is named."""
    assert split(called) == parts


def test_what_is_installed_out_of_a_flowverse_is_kept_beside_its_index() -> None:
    assert kept("theirs") == home() / "flowverses" / "theirs" / "installed"
    assert _installed("loop", "0.1.0").at == kept("theirs") / "loop"


def test_an_installed_flow_is_called_as_every_flow_of_its_flowverse_is() -> None:
    assert _installed("loop", "0.1.0").called == "theirs/loop"
    assert _installed("loop", "0.1.0", verse=OFFICIAL).called == "loop"


# ------------------------------------------------------------------- what is installed


def test_what_is_installed_is_read_off_the_records_the_installed_flows_carry() -> None:
    """By flowverse, then by name; and one flowverse's alone where one is asked about."""
    ours = _installed("zeta", "1.0.0", verse=OFFICIAL)
    loop = _installed("loop", "0.1.0")
    helper = _installed("helper", "0.2.0", {"x": ">=0.1.0"})
    for one in (loop, ours, helper):
        _recorded(one)

    assert installed() == [ours, helper, loop]
    assert installed("theirs") == [helper, loop]
    assert installed("nobodys") == []


def test_a_directory_without_a_record_that_reads_is_not_taken_for_an_installed_flow() -> (
    None
):
    """One somebody made by hand, one a killed install left half-moved, one gone wrong."""
    _recorded(_installed("loop", "0.1.0"))
    (kept("theirs") / "by_hand").mkdir()
    (kept("theirs") / "garbled").mkdir()
    (kept("theirs") / "garbled" / RECORD).write_text("{not json", encoding="utf-8")
    # A record that says it is somebody else: copied, or moved by hand.
    _recorded(_installed("other", "0.1.0"), at=kept("theirs") / "moved")
    _recorded(_installed("dup", "0.1.0", verse="elsewhere"), at=kept("theirs") / "dup")
    # And what an install in flight writes beside the place, which is not listed until moved.
    _recorded(_installed("held", "0.1.0"), at=kept("theirs") / ".held.abc123" / "held")
    _recorded(_installed("held", "0.1.0"), at=kept("theirs") / ".held")

    assert [one.name for one in installed()] == ["loop"]


def test_a_record_whose_release_is_not_semver_is_not_taken_for_an_installed_flow() -> (
    None
):
    """One edited by hand is no reason the updates of every other flow cannot be read."""
    _recorded(_installed("loop", "0.1.0"))
    at = _recorded(_installed("edited", "0.1.0"))
    record = json.loads((at / RECORD).read_text(encoding="utf-8"))
    (at / RECORD).write_text(
        json.dumps({**record, "version": "newest"}), encoding="utf-8"
    )

    assert [one.name for one in installed()] == ["loop"]
    assert updates() == []


@pytest.mark.parametrize(
    "key", ["description", "ref", "subdir", "license", "dependencies"]
)
def test_a_key_written_with_nothing_after_it_is_a_key_not_written(
    verse: Flowverse, key: str
) -> None:
    """`subdir:` alone is what somebody writes for the root, not a reason to skip a release."""
    said = _read(verse, {**BASE, key: None})

    assert isinstance(said, Release)
    assert said == _read_as(verse, {k: v for k, v in BASE.items() if k != key})


def _read_as(verse: Flowverse, said: Mapping[str, object]) -> Release:
    """What a manifest reads as, written over the one a test wrote first."""
    read = _read(verse, said)
    assert isinstance(read, Release)
    return read


def test_nothing_installed_is_nothing_rather_than_a_failure() -> None:
    assert installed() == []
    assert updates() == []


def test_uninstalling_takes_the_whole_directory_away_in_one_move() -> None:
    at = _recorded(_installed("loop", "0.1.0"))
    (at / "_beside.py").write_text("", encoding="utf-8")

    assert uninstall("theirs", "loop")

    assert not at.exists()
    assert list(kept("theirs").iterdir()) == []  # nothing left beside it, either
    assert not uninstall("theirs", "loop")  # and again is not an error


def test_a_directory_that_is_not_an_installed_flow_is_not_uninstalled() -> None:
    """Somebody's own directory under the same place is theirs to take away, not this."""
    at = kept("theirs") / "by_hand"
    at.mkdir(parents=True)

    assert not uninstall("theirs", "by_hand")
    assert at.is_dir()


def test_a_flow_another_installed_flow_needs_is_not_uninstalled() -> None:
    """Which is that flow to uninstall first, rather than one to leave broken."""
    helper = _recorded(_installed("helper", "0.1.0"))
    _recorded(_installed("prover", "0.1.0", {"helper": ">=0.1.0"}))

    with pytest.raises(
        ValueError, match=_exactly("theirs/prover needs helper; uninstall that first")
    ):
        uninstall("theirs", "helper")
    assert helper.is_dir()

    _recorded(_installed("checker", "0.1.0", {"helper": ">=0.1.0"}))
    with pytest.raises(
        ValueError,
        match=_exactly(
            "theirs/checker, theirs/prover need helper; uninstall that first"
        ),
    ):
        uninstall("theirs", "helper")


def test_what_another_flowverse_needs_of_the_same_name_does_not_hold_a_flow_back() -> (
    None
):
    """A flow needs flows of its own index: another one's `helper` is a different flow."""
    _recorded(_installed("helper", "0.1.0"))
    _recorded(_installed("prover", "0.1.0", {"helper": ">=0.1.0"}, verse=OFFICIAL))

    assert uninstall("theirs", "helper")


# ------------------------------------------------------------------- what an install is


def test_installing_a_flow_that_needs_nothing_installs_just_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _planning(
        monkeypatch,
        [
            _release("loop", "0.1.0"),
            _release("loop", "0.2.0"),
            _release("loop", "0.3.0-rc.1"),
            _release("other", "1.0.0"),
        ],
    )

    assert _named(plan("theirs", "loop")) == ["loop 0.2.0"]
    assert _named(plan("theirs", "loop", "0.1.0")) == ["loop 0.1.0"]
    # A prerelease is installed where it is asked for by name.
    assert _named(plan("theirs", "loop", "0.3.0-rc.1")) == ["loop 0.3.0-rc.1"]


def test_installing_what_an_index_does_not_list_says_which_half_it_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _planning(monkeypatch, [_release("loop", "0.1.0")])

    with pytest.raises(
        ValueError, match=_exactly("theirs lists no release 9.9.9 of loop")
    ):
        plan("theirs", "loop", "9.9.9")
    with pytest.raises(
        ValueError, match=_exactly("theirs lists no flow called nothing")
    ):
        plan("theirs", "nothing")
    with pytest.raises(
        ValueError, match=_exactly("theirs lists no flow called nothing")
    ):
        plan("theirs", "nothing", "0.1.0")


def test_what_a_flow_needs_is_installed_before_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each after what it needs, the one asked for last: the order they can be run in."""
    _planning(
        monkeypatch,
        [
            _release("a", "0.1.0", {"b": ">=0.1.0"}),
            _release("b", "0.1.0", {"c": ">=0.1.0"}),
            _release("c", "0.1.0"),
        ],
    )

    assert _named(plan("theirs", "a")) == ["c 0.1.0", "b 0.1.0", "a 0.1.0"]


def test_a_flow_two_others_need_is_installed_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _planning(
        monkeypatch,
        [
            _release("a", "0.1.0", {"c": ">=0.1.0", "b": ">=0.1.0"}),
            _release("b", "0.1.0", {"d": ">=0.1.0"}),
            _release("c", "0.1.0", {"d": "<1.0.0"}),
            _release("d", "0.1.0"),
            _release("d", "0.2.0"),
        ],
    )

    assert _named(plan("theirs", "a")) == ["d 0.2.0", "b 0.1.0", "c 0.1.0", "a 0.1.0"]


def test_what_a_flow_needs_is_the_newest_release_its_range_takes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """And not a prerelease, where a release in the range will do."""
    _planning(
        monkeypatch,
        [
            _release("a", "0.1.0", {"helper": ">=0.1.0,<0.2.0"}),
            _release("helper", "0.1.0"),
            _release("helper", "0.1.1"),
            _release("helper", "0.1.2-rc.1"),
            _release("helper", "0.2.0"),
        ],
    )

    assert _named(plan("theirs", "a")) == ["helper 0.1.1", "a 0.1.0"]


def test_a_dependency_already_installed_at_a_version_its_range_takes_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not upgraded to the newest: somebody chose what is installed, and it will do."""
    _planning(
        monkeypatch,
        [
            _release("a", "0.1.0", {"helper": ">=0.1.0,<0.2.0"}),
            _release("helper", "0.1.0"),
            _release("helper", "0.1.1"),
        ],
        held=[_installed("helper", "0.1.0")],
    )

    assert _named(plan("theirs", "a")) == ["a 0.1.0"]


def test_a_dependency_installed_at_a_version_its_range_does_not_take_is_moved_into_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _planning(
        monkeypatch,
        [
            _release("a", "0.1.0", {"helper": ">=0.1.0,<0.2.0"}),
            _release("helper", "0.1.1"),
            _release("helper", "0.2.0"),
        ],
        held=[_installed("helper", "0.2.0")],
    )

    assert _named(plan("theirs", "a")) == ["helper 0.1.1", "a 0.1.0"]


def test_what_another_flowverse_has_installed_is_not_what_this_one_needs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _planning(
        monkeypatch,
        [_release("a", "0.1.0", {"helper": ">=0.1.0"}), _release("helper", "0.1.0")],
        held=[_installed("helper", "0.1.0", verse=OFFICIAL)],
    )

    assert _named(plan("theirs", "a")) == ["helper 0.1.0", "a 0.1.0"]


@pytest.mark.parametrize(
    ("releases", "why"),
    [
        (
            [_release("a", "0.1.0", {"a": ">=0.1.0"})],
            "a needs itself, through a -> a",
        ),
        (
            [
                _release("a", "0.1.0", {"b": ">=0.1.0"}),
                _release("b", "0.1.0", {"a": ">=0.1.0"}),
            ],
            "a needs itself, through a -> b -> a",
        ),
        (
            [
                _release("a", "0.1.0", {"b": ">=0.1.0"}),
                _release("b", "0.1.0", {"c": ">=0.1.0"}),
                _release("c", "0.1.0", {"b": ">=0.1.0"}),
            ],
            "b needs itself, through a -> b -> c -> b",
        ),
    ],
    ids=["itself", "each other", "further down"],
)
def test_flows_that_need_one_another_are_refused(
    monkeypatch: pytest.MonkeyPatch, releases: list[Release], why: str
) -> None:
    _planning(monkeypatch, releases)

    with pytest.raises(ValueError, match=_exactly(why)):
        plan("theirs", "a")


@pytest.mark.parametrize(
    "releases",
    [
        [_release("a", "0.1.0", {"helper": ">=1.0.0"}), _release("helper", "0.1.0")],
        [_release("a", "0.1.0", {"helper": ">=0.1.0"})],
    ],
    ids=["none in range", "none at all"],
)
def test_a_flow_that_needs_what_the_index_does_not_list_is_refused(
    monkeypatch: pytest.MonkeyPatch, releases: list[Release]
) -> None:
    _planning(monkeypatch, releases)
    spec = releases[0].dependencies["helper"]

    with pytest.raises(
        ValueError,
        match=_exactly(
            f"a 0.1.0 needs helper {spec}, and theirs lists no release of it in that range"
        ),
    ):
        plan("theirs", "a")


def test_two_flows_of_one_install_needing_one_flow_in_ranges_no_version_takes_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _planning(
        monkeypatch,
        [
            _release("a", "0.1.0", {"b": ">=0.1.0", "c": ">=0.1.0"}),
            _release("b", "0.1.0", {"d": "<0.2.0"}),
            _release("c", "0.1.0", {"d": ">=0.2.0"}),
            _release("d", "0.1.0"),
            _release("d", "0.2.0"),
        ],
    )

    with pytest.raises(
        ValueError,
        match=_exactly(
            "c 0.1.0 needs d >=0.2.0, and d 0.1.0 is what the rest of this install needs"
        ),
    ):
        plan("theirs", "a")


def test_an_install_that_would_break_another_installed_flow_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rather than leaving somebody's other flow broken by the one they asked for."""
    _planning(
        monkeypatch,
        [
            _release("helper", "0.1.0"),
            _release("helper", "0.2.0"),
            _release("a", "0.1.0", {"helper": ">=0.2.0"}),
        ],
        held=[
            _installed("helper", "0.1.0"),
            _installed("prover", "0.1.0", {"helper": "<0.2.0"}),
        ],
    )

    breaks = "theirs/prover 0.1.0 needs helper <0.2.0; installing helper 0.2.0 would break it"
    with pytest.raises(ValueError, match=_exactly(breaks)):
        plan("theirs", "helper", "0.2.0")
    # And the same where it is what the flow asked for needs, rather than what was asked for.
    with pytest.raises(ValueError, match=_exactly(breaks)):
        plan("theirs", "a")
    # A release the installed flow's range takes is no trouble.
    assert _named(plan("theirs", "helper", "0.1.0")) == ["helper 0.1.0"]


def test_a_flow_being_replaced_is_not_held_to_the_ranges_of_the_release_it_replaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Its new release's ranges are the ones that count, and those were just checked."""
    _planning(
        monkeypatch,
        [
            _release("prover", "0.2.0", {"helper": ">=0.2.0"}),
            _release("helper", "0.1.0"),
            _release("helper", "0.2.0"),
        ],
        held=[
            _installed("helper", "0.1.0"),
            _installed("prover", "0.1.0", {"helper": "<0.2.0"}),
        ],
    )

    assert _named(plan("theirs", "prover")) == ["helper 0.2.0", "prover 0.2.0"]


@pytest.mark.parametrize(
    ("verse", "why"),
    [
        ("nobodys", "no flowverse called 'nobodys'"),
        (LOCAL, "local is a directory of your own flows, not an index"),
        (USER, "user is a directory of your own flows, not an index"),
        (OFFICIAL, "official has not been fetched yet; fetch it first"),
    ],
)
def test_installing_out_of_what_is_not_a_fetched_index_is_refused(
    verse: str, why: str
) -> None:
    """Before anything is fetched: there is no release to fetch."""
    with pytest.raises(ValueError, match=_exactly(why)):
        install(verse, "loop")


def test_installing_copies_what_is_needed_first_and_nothing_already_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A release installed already, at the same commit, is left exactly as it is.

    Asking for one that is installed is asking for what it needs that is not, which is the
    one thing an install of it does: what was asked for is answered with its own record.
    """
    already = _installed("a", "0.2.0", {"helper": ">=0.1.0", "other": ">=0.1.0"})
    _recorded(already)
    _planning(
        monkeypatch,
        [
            _release("a", "0.2.0", {"helper": ">=0.1.0", "other": ">=0.1.0"}),
            _release("helper", "0.1.0"),
            _release("other", "0.1.0"),
        ],
        held=[already],
    )
    put: list[str] = []

    def copies(verse: str, one: Release) -> Installed:
        put.append(f"{verse}/{one.name} {one.version}")
        return _installed(one.name, one.version, one.dependencies, verse)

    monkeypatch.setattr(indexing, "_put", copies)

    done = install("theirs", "a")

    assert put == ["theirs/helper 0.1.0", "theirs/other 0.1.0"]
    assert [(one.name, one.version) for one in done] == [
        ("helper", "0.1.0"),
        ("other", "0.1.0"),
        ("a", "0.2.0"),
    ]
    assert done[-1] == already


# ------------------------------------------------------------------- what is newer


def _updating(
    monkeypatch: pytest.MonkeyPatch,
    held: Sequence[Installed],
    indexes: Mapping[str, Sequence[Release]],
) -> list[str]:
    """Has `updates` see these installs and these indexes; answers with each index it read."""
    read: list[str] = []

    def reads(verse: str) -> Index:
        read.append(verse)
        return Index(verse, tuple(indexes.get(verse, ())))

    monkeypatch.setattr(indexing, "installed", lambda verse="": list(held))
    monkeypatch.setattr(indexing, "index", reads)
    return read


def test_an_installed_flow_with_a_newer_release_is_offered_the_newest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = _installed("loop", "0.1.0")
    _updating(
        monkeypatch,
        [loop],
        {
            "theirs": [
                _release("loop", "0.1.0"),
                _release("loop", "0.1.1"),
                _release("loop", "0.2.0"),
            ]
        },
    )

    assert updates() == [Update(loop, "0.2.0")]


def test_a_flow_on_a_release_is_not_told_about_every_candidate_for_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = _installed("loop", "0.1.0")
    _updating(
        monkeypatch,
        [loop],
        {"theirs": [_release("loop", "0.1.0"), _release("loop", "0.2.0-rc.1")]},
    )

    assert updates() == []


@pytest.mark.parametrize(
    ("listed_", "newest"),
    [
        (["0.2.0-rc.1", "0.2.0-rc.2"], "0.2.0-rc.2"),
        (["0.2.0-rc.1", "0.2.0-rc.2", "0.2.0"], "0.2.0"),
        (["0.2.0-rc.1", "0.1.9"], None),
    ],
)
def test_a_flow_on_a_prerelease_is_offered_the_newest_release_of_either_kind(
    monkeypatch: pytest.MonkeyPatch, listed_: list[str], newest: str | None
) -> None:
    loop = _installed("loop", "0.2.0-rc.1")
    _updating(
        monkeypatch, [loop], {"theirs": [_release("loop", one) for one in listed_]}
    )

    assert updates() == ([] if newest is None else [Update(loop, newest)])


def test_a_flow_whose_index_no_longer_lists_it_has_nothing_newer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _updating(
        monkeypatch,
        [_installed("loop", "0.1.0"), _installed("ours", "0.1.0", verse=OFFICIAL)],
        {"theirs": [_release("other", "9.0.0")]},
    )

    assert updates() == []


def test_each_index_is_read_once_however_many_flows_were_installed_out_of_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = [
        _installed("ours", "0.1.0", verse=OFFICIAL),
        _installed("a", "0.1.0"),
        _installed("b", "0.1.0"),
    ]
    read = _updating(
        monkeypatch,
        held,
        {
            "theirs": [_release("a", "0.2.0"), _release("b", "0.1.0")],
            OFFICIAL: [_release("ours", "1.0.0")],
        },
    )

    assert updates() == [Update(held[0], "1.0.0"), Update(held[1], "0.2.0")]
    assert read == [OFFICIAL, "theirs"]
