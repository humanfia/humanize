"""What a flowverse's index lists, and the flows installed out of one.

A flowverse is an index: a git repository of `flows/<flow>/<version>/flow.yaml`, one manifest
per release of a flow, each saying where that release lives -- a GitHub repository, the commit
it was cut from, and the directory of it the flow is in. The index holds no code, so nothing in
it is ever imported: reading one is reading YAML, and fetching one again changes what may be
installed and never what runs.

What runs is a copy of the release somebody chose, kept under humanize's home at
`installed/<flowverse>/<flow>/` and read from there by everything that looks a flow up. The
directory is named after the flow so that what a flow loads beside itself -- `humanize1`, from
inside `recursive_lean_prover` -- is found where it is found in the repository the two came
from: the installed flows of one flowverse are each other's neighbours. It carries a record of
what it was installed from, written into it before it is moved into place, so that what is there
and what it says it is arrive in one move rather than two writes -- which is all the registry
there is, and why two installs racing each other leave a whole flow behind rather than half of
one beside a record of the other.

A release may name other flows of the same index it needs, each by a SemVer range. Installing
it installs the newest release of each that the range takes, unless one already installed
does, and refuses a cycle or a range that what is installed already rules out, rather than
leaving somebody's other flow broken by the one they asked for.

Nothing here runs a flow. Fetching a release is the one thing that reaches a network, and it is
only ever asked for by name.
"""

from __future__ import annotations

import contextlib
import json
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, NamedTuple, cast

import semver
import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from hmz import home

from .verses import FLOWS, OFFICIAL, named

if TYPE_CHECKING:
    from .verses import Flowverse

__all__ = [
    "RECORD",
    "RELEASE",
    "RESERVED",
    "Index",
    "Installed",
    "Release",
    "Skipped",
    "Update",
    "index",
    "install",
    "installed",
    "kept",
    "plan",
    "reserved",
    "satisfies",
    "split",
    "uninstall",
    "updates",
]

#: What one release of one flow is written down as, inside `flows/<flow>/<version>/`.
RELEASE = "flow.yaml"

#: What an installed flow's directory carries to say what it was installed from. Hidden, so
#: that nothing that reads a flow's directory for what the flow brings takes it for any of it.
RECORD = ".installed.json"

#: The flows humanize ships in the package. Their names are humanize's own: an index may not
#: offer one, and nothing installed may stand in for one, so `chat` is the same flow on every
#: machine whatever anybody has fetched.
RESERVED = frozenset(
    {
        "chat",
        "continue_loop",
        "flame_chase",
        "goal",
        "ralph_loop",
        "rlar",
        "stateful_ralph",
    }
)

#: What a flow in an index may be called: a Python identifier in lower case, since it is the
#: name the flow's module is imported as and the directory it is installed into.
_FLOW = re.compile(r"[a-z][a-z0-9_]*\Z")

#: A commit, written out in full: the one thing a release is installed at.
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")

#: `owner/repo`, which is how a repository on GitHub is named in an index.
_OWNED = re.compile(r"[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*\Z")

#: What a URL an index names may be fetched over -- a mirror, a test's own repository.
_SCHEMES = ("https://", "http://", "ssh://", "git://", "file://")

#: One part of a directory a release names: nothing hidden, nothing that climbs.
_PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")

#: One clause of a range, as python-semver reads it: an operator and a version.
_CLAUSE = re.compile(r"(<=|>=|==|!=|<|>)?(.+)\Z")

#: How old a half-finished install has to be before the next one of that name sweeps it away:
#: longer than any one of them is given, so that nothing still being written is taken.
_STALE = 600.0

#: How many times an install moves what is in its way aside before giving up on the place.
_TRIES = 3


def satisfies(version: str, spec: str) -> bool:
    """Whether a version is one a dependency's range takes.

    Args:
      version: The version, as SemVer.
      spec: The range: clauses joined by `,`, every one of which must hold -- `>=0.1.0,<0.2.0`
        -- each an operator python-semver knows and a version, or a version alone for exactly
        that one.

    Returns:
      Whether it does.

    Raises:
      ValueError: If either is not what it says it is.
    """
    held = semver.Version.parse(version)
    return all(held.match(clause) for clause in _clauses(spec))


def _versioned(value: str) -> str:
    """A version, as it was given, once it is known to be SemVer.

    Raises:
      ValueError: If it is not.
    """
    if not semver.Version.is_valid(value):
        raise ValueError(f"{value!r} is not SemVer, as 0.1.0 is")
    return value


def _clauses(spec: str) -> list[str]:
    """A range, one clause apiece, as python-semver's `match` takes them.

    Raises:
      ValueError: For a range with nothing in it, or a clause that is not an operator and a
        version.
    """
    clauses: list[str] = []
    for part in spec.split(","):
        said = re.sub(r"\s+", "", part)
        found = _CLAUSE.match(said)
        if not said or found is None or not semver.Version.is_valid(found.group(2)):
            raise ValueError(f"{spec!r} is not a version range like >=0.1.0,<0.2.0")
        clauses.append(said if found.group(1) else f"=={said}")
    return clauses


class Release(BaseModel):
    """One release of one flow, as `flows/<flow>/<version>/flow.yaml` says it.

    Keys nobody here knows are let through unread, so that an index written for a later
    humanize still lists for this one.

    Attributes:
      name: The flow, which is the directory its releases are in.
      version: This release, as SemVer, which is the directory it is in.
      description: One line about it.
      repo: Where it lives: `owner/repo` on GitHub, or any URL git fetches.
      ref: The tag or branch it was cut from, for whoever reads the index. What is installed
        is `commit`.
      commit: What `ref` stood at when the release was reviewed, in full.
      subdir: The directory of the repository the flow is in, or "" for its root.
      license: Its licence, as SPDX names it.
      dependencies: Other flows of the same index it needs, each with the range it takes.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    name: str
    version: str
    description: str = ""
    repo: str
    ref: str = ""
    commit: str
    subdir: str = ""
    license: str = ""
    dependencies: dict[str, str] = Field(default_factory=dict[str, str])

    @model_validator(mode="before")
    @classmethod
    def _blank(cls, value: object) -> object:
        """Takes a key written with nothing after it -- `subdir:` -- as a key not written.

        And a version YAML read as a number -- `version: 1.0` -- as the text it was, so that
        what is said about it is that it is not SemVer rather than that it is not a string.
        """
        if not isinstance(value, dict):
            return value
        said = {
            key: held
            for key, held in cast("dict[str, object]", value).items()
            if held is not None
        }
        if isinstance(said.get("version"), int | float):
            said["version"] = str(said["version"])
        return said

    @field_validator("name")
    @classmethod
    def _flow(cls, value: str) -> str:
        if not _FLOW.match(value):
            raise ValueError(f"{value!r} is not a flow name: [a-z][a-z0-9_]*")
        return value

    @field_validator("version")
    @classmethod
    def _semver(cls, value: str) -> str:
        return _versioned(value)

    @field_validator("repo")
    @classmethod
    def _repo(cls, value: str) -> str:
        said = value.strip()
        if not (_OWNED.match(said) or said.startswith(_SCHEMES)):
            raise ValueError(f"{value!r} is neither owner/repo nor a URL git can fetch")
        return said

    @field_validator("commit")
    @classmethod
    def _commit(cls, value: str) -> str:
        said = value.strip().lower()
        if not _COMMIT.match(said):
            raise ValueError(f"{value!r} is not a commit written out in full (40 hex)")
        return said

    @field_validator("subdir")
    @classmethod
    def _subdir(cls, value: str) -> str:
        said = value.strip().strip("/")
        if said in ("", "."):
            return ""
        parts = PurePosixPath(said).parts
        if not all(_PART.match(one) for one in parts):
            raise ValueError(f"{value!r} is not a directory inside the repository")
        return "/".join(parts)

    @field_validator("dependencies")
    @classmethod
    def _needs(cls, value: dict[str, str]) -> dict[str, str]:
        for name, spec in value.items():
            if not _FLOW.match(name):
                raise ValueError(f"{name!r} is not a flow name")
            _clauses(str(spec))
        return {name: str(spec) for name, spec in value.items()}

    @property
    def semver(self) -> semver.Version:
        """The version, as something that compares."""
        return semver.Version.parse(self.version)

    @property
    def url(self) -> str:
        """What git fetches it from: GitHub's address for `owner/repo`, else the URL itself."""
        return (
            f"https://github.com/{self.repo}" if _OWNED.match(self.repo) else self.repo
        )


class Skipped(NamedTuple):
    """A manifest of an index that was not listed, and why.

    Attributes:
      at: The file.
      why: What was wrong with it, in a line.
    """

    at: Path
    why: str


class Index(NamedTuple):
    """Everything one flowverse's index lists, and what it could not.

    Attributes:
      verse: The flowverse.
      releases: Every release that read, by flow and then newest first.
      skipped: Every manifest that did not, with why -- listed rather than raised, since one
        bad file in somebody's index is no reason the rest of it cannot be installed from.
    """

    verse: str
    releases: tuple[Release, ...] = ()
    skipped: tuple[Skipped, ...] = ()

    def flows(self) -> list[str]:
        """Every flow it has a release of, alphabetically."""
        return sorted({one.name for one in self.releases})

    def versions(self, flow: str) -> list[Release]:
        """Every release of one flow, newest first."""
        return sorted(
            (one for one in self.releases if one.name == flow),
            key=lambda one: one.semver,
            reverse=True,
        )

    def release(self, flow: str, version: str) -> Release | None:
        """One release of one flow, or None for one it does not list."""
        return next(
            (one for one in self.versions(flow) if one.version == version), None
        )

    def newest(self, flow: str, spec: str = "") -> Release | None:
        """The release to install of a flow when nobody said which.

        The newest that is not a prerelease, else the newest prerelease: a release that says it
        is not ready is installed only where nothing is.

        Args:
          flow: The flow.
          spec: A range it must fall in, or "" for any.

        Returns:
          The release, or None where there is none -- or none in the range.
        """
        fits = [
            one
            for one in self.versions(flow)
            if not spec or satisfies(one.version, spec)
        ]
        return next((one for one in fits if not one.semver.prerelease), None) or next(
            iter(fits), None
        )


class Installed(BaseModel):
    """One flow installed out of an index, as the record in its directory says.

    Attributes:
      verse: The flowverse it was installed from.
      name: The flow.
      version: The release installed.
      commit: The commit it was copied out of.
      repo: Where that commit lives.
      ref: The tag or branch the release was cut from.
      subdir: The directory of the repository the flow was copied out of.
      dependencies: What the release said it needs, which uninstalling and installing others
        are checked against.
      skills: The skills its roles name by a URL, each to the ones installing it fetched into
        its own `skills/` -- which a run of it reads from there, as it does the flow's own.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    verse: str
    name: str
    version: str
    commit: str
    repo: str
    ref: str = ""
    subdir: str = ""
    dependencies: dict[str, str] = Field(default_factory=dict[str, str])
    skills: dict[str, list[str]] = Field(default_factory=dict[str, list[str]])

    @field_validator("version")
    @classmethod
    def _semver(cls, value: str) -> str:
        """A record whose release is not SemVer is one written by hand, and reads as none."""
        return _versioned(value)

    @property
    def called(self) -> str:
        """What it is offered under: a bare name for `official`'s, `<verse>/<flow>` otherwise."""
        return self.name if self.verse == OFFICIAL else f"{self.verse}/{self.name}"

    @property
    def at(self) -> Path:
        """The directory it is installed in."""
        return kept(self.verse) / self.name


class Update(NamedTuple):
    """A flow with a newer release in its index than the one installed.

    Attributes:
      installed: What is installed.
      version: The newest release after it -- a prerelease only for a flow that is on one.
    """

    installed: Installed
    version: str


def reserved() -> frozenset[str]:
    """The names nothing installed may take: :data:`RESERVED`, and whatever the package holds."""
    from .finding import BUILTIN_AT, offered

    return RESERVED | frozenset(offered(BUILTIN_AT))


def kept(verse: str) -> Path:
    """Where the flows installed out of one flowverse are.

    Args:
      verse: The flowverse, by name.

    Returns:
      The directory, whether or not anything has been installed into it.
    """
    return home() / "installed" / verse


def split(called: str) -> tuple[str, str]:
    """A flow's name, as it is offered, into the flowverse and the flow.

    Args:
      called: `<flowverse>/<flow>`, or a bare name for one of `official`'s.

    Returns:
      The two.
    """
    whose, _, flow = called.partition("/")
    return (whose, flow) if flow else (OFFICIAL, whose)


def index(one: Flowverse | str) -> Index:
    """Reads every release one flowverse's index lists.

    Read off the clone as it stands, which is the last time it was fetched: nothing here goes
    near a network.

    Args:
      one: The flowverse, or its name.

    Returns:
      What it lists, and what it could not. Nothing at all for one that has not been fetched,
      one that is not an index -- your own flows' places -- and a name none answers to.
    """
    verse = named(one) if isinstance(one, str) else one
    if verse is None:
        return Index(one if isinstance(one, str) else "")
    if not verse.url or not verse.fetched:
        return Index(verse.name)
    taken = reserved()
    releases: list[Release] = []
    skipped: list[Skipped] = []
    for flow in _directories(verse.at / FLOWS):
        for version in _directories(flow):
            at = version / RELEASE
            said = _read(at, flow.name, version.name, taken)
            if isinstance(said, Release):
                releases.append(said)
            else:
                skipped.append(Skipped(at, said))
    # Newest first, then by flow: the second sort keeps the first one's order within a flow.
    releases.sort(key=lambda one: one.semver, reverse=True)
    releases.sort(key=lambda one: one.name)
    return Index(verse.name, tuple(releases), tuple(skipped))


def _read(at: Path, flow: str, version: str, taken: frozenset[str]) -> Release | str:
    """One manifest, read and checked against where it is.

    Args:
      at: The manifest.
      flow: The directory of the flow it is in.
      version: The directory of the version it is in.
      taken: The names it may not have.

    Returns:
      The release, or why it is not one.
    """
    try:
        loaded: object = yaml.safe_load(at.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return f"no {RELEASE} in it"
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as why:
        return f"unreadable: {str(why).splitlines()[0] if str(why) else type(why).__name__}"
    if not isinstance(loaded, dict):
        return "not a mapping of keys to values"
    try:
        release = Release.model_validate(loaded)
    except ValidationError as why:
        first = why.errors()[0]
        where = ".".join(str(one) for one in first["loc"])
        return f"{where}: {first['msg']}" if where else str(first["msg"])
    if release.name != flow:
        return f"name {release.name} is not the directory it is in, {flow}"
    if release.version != version:
        return f"version {release.version} is not the directory it is in, {version}"
    if release.name in taken:
        return (
            f"{release.name} is built into humanize; nothing may be installed over it"
        )
    return release


def installed(verse: str = "") -> list[Installed]:
    """Every flow installed out of an index, or out of one of them.

    Read off the records the installed flows carry, so that a directory with none -- one
    somebody made by hand, one a killed install left half-moved -- is not taken for one.

    Args:
      verse: The flowverse, or "" for every one of them.

    Returns:
      One apiece, by flowverse and then by name.
    """
    roots = [kept(verse)] if verse else _directories(home() / "installed")
    found: list[Installed] = []
    for root in roots:
        for at in _directories(root):
            one = _record(at)
            if one is not None and one.verse == root.name and one.name == at.name:
                found.append(one)
    return found


def _record(at: Path) -> Installed | None:
    """What one installed flow's directory says it is, or None where it says nothing that reads."""
    try:
        return Installed.model_validate(
            json.loads((at / RECORD).read_text(encoding="utf-8"))
        )
    except (OSError, ValueError):
        return None


def updates() -> list[Update]:
    """Every installed flow whose index lists a newer release than the one installed.

    Read off each index as it was last fetched, so this is as up to date as the last fetch and
    no more -- and costs a read of some YAML rather than a round trip.

    Returns:
      One per flow with something newer, naming the newest. A prerelease is offered only to a
      flow that is on one already: somebody who installed a release has not asked to be told
      about every candidate for the next one.
    """
    indexes: dict[str, Index] = {}
    found: list[Update] = []
    for one in installed():
        listed = indexes.get(one.verse)
        if listed is None:
            listed = indexes[one.verse] = index(one.verse)
        now = semver.Version.parse(one.version)
        newer = [
            each
            for each in listed.versions(one.name)
            if each.semver > now and (not each.semver.prerelease or now.prerelease)
        ]
        if newer:
            found.append(Update(one, newer[0].version))
    return found


def plan(verse: str, flow: str, version: str = "") -> list[Release]:
    """What installing one release comes to: it, and whatever it needs that is not there yet.

    Args:
      verse: The flowverse.
      flow: The flow.
      version: The release, or "" for the newest that is not a prerelease.

    Returns:
      The releases to install, each after what it needs, the one asked for last. A dependency
      already installed at a version its range takes is left as it is and is not among them.

    Raises:
      ValueError: If there is no such flowverse, flow or release; if what it needs is not
        listed in a version its range takes; if two of them need one another; if two of them
        need one flow in ranges no one version satisfies; or if installing any of them would
        take away a version another installed flow needs.
    """
    listed = _index_of(verse)
    held = {one.name: one for one in installed(verse)}
    asked = listed.release(flow, version) if version else listed.newest(flow)
    if asked is None:
        raise ValueError(
            f"{verse} lists no release {version} of {flow}"
            if version and listed.versions(flow)
            else f"{verse} lists no flow called {flow}"
        )
    chosen: dict[str, Release] = {}
    ordered: list[Release] = []
    #: Every range asked of a flow along the way, by whom: one kept because what is
    #: installed takes it is still a range a release picked later for somebody else must take.
    wanted: list[tuple[Release, str, str]] = []

    def visit(one: Release, path: tuple[str, ...]) -> None:
        chosen[one.name] = one
        for need, spec in sorted(one.dependencies.items()):
            wanted.append((one, need, spec))
            if need in (*path, one.name):
                cycle = " -> ".join((*path, one.name, need))
                raise ValueError(f"{need} needs itself, through {cycle}")
            picked = chosen.get(need)
            if picked is not None:
                if not satisfies(picked.version, spec):
                    raise ValueError(
                        f"{one.name} {one.version} needs {need} {spec}, and {need} "
                        f"{picked.version} is what the rest of this install needs"
                    )
                continue
            have = held.get(need)
            if have is not None and satisfies(have.version, spec):
                continue
            picked = listed.newest(need, spec)
            if picked is None:
                raise ValueError(
                    f"{one.name} {one.version} needs {need} {spec}, and {verse} lists "
                    "no release of it in that range"
                )
            visit(picked, (*path, one.name))
        ordered.append(one)

    visit(asked, ())
    for one, need, spec in wanted:
        landing = chosen[need].version if need in chosen else held[need].version
        if not satisfies(landing, spec):
            raise ValueError(
                f"{one.name} {one.version} needs {need} {spec}, and {need} {landing} is "
                "what the rest of this install needs"
            )
    for one in ordered:
        for other in held.values():
            if other.name in chosen:
                continue  # replaced by this install, whose own ranges were just checked
            spec = other.dependencies.get(one.name)
            if spec is not None and not satisfies(one.version, spec):
                raise ValueError(
                    f"{other.called} {other.version} needs {one.name} {spec}; installing "
                    f"{one.name} {one.version} would break it"
                )
    return ordered


def install(verse: str, flow: str, version: str = "") -> list[Installed]:
    """Installs one release of a flow, and whatever it needs that is not there yet.

    Each flow is copied out of a checkout of its repository at its commit into a directory
    beside the one it is to be kept in, its record written into that, and then moved into
    place in one rename -- moving whatever release was there aside first -- so that what is at
    the place is a whole release of the flow, record and all, at every moment anybody looks.

    Args:
      verse: The flowverse whose index lists it.
      flow: The flow.
      version: The release, or "" for the newest that is not a prerelease.

    Returns:
      What is installed now of each flow the install came to, the one asked for last.

    Raises:
      ValueError: For anything :func:`plan` refuses, and a release whose repository has no
        flow where it says.
      OSError: If a repository, or a skill a flow's roles name by a URL, cannot be fetched, or
        the flow cannot be copied into place.
    """
    done: list[Installed] = []
    for one in plan(verse, flow, version):
        have = _record(kept(verse) / one.name)
        if have is not None and (have.version, have.commit) == (
            one.version,
            one.commit,
        ):
            done.append(have)
            continue
        done.append(_put(verse, one))
    return done


def _put(verse: str, one: Release) -> Installed:
    """Copies one release into place.

    Args:
      verse: The flowverse it is installed out of.
      one: The release.

    Returns:
      Its record, as it now stands in the directory.

    Raises:
      ValueError: If its repository has no flow where it says.
      OSError: If the repository, or a skill its roles name by a URL, cannot be fetched, or
        the flow cannot be copied.
    """
    from hmz.flows import FlowNotFound

    from .finding import ENTRY
    from .loading import pinned
    from .skills import packed

    try:
        checkout = pinned(one.url, one.commit).resolve()
    except FlowNotFound as why:
        raise OSError(str(why)) from why
    source = (checkout / one.subdir).resolve()
    if not source.is_relative_to(checkout):
        raise ValueError(f"{one.subdir} climbs out of {one.repo}")
    whole, alone = source / ENTRY, source / f"{one.name}.py"
    if not whole.is_file() and not alone.is_file():
        raise ValueError(
            f"{one.repo} at {one.commit[:12]} has no flow in {one.subdir or 'its root'}: "
            f"neither {ENTRY} nor {one.name}.py"
        )
    root = kept(verse)
    root.mkdir(parents=True, exist_ok=True)
    _swept(root, one.name)
    holding = Path(tempfile.mkdtemp(dir=root, prefix=f".{one.name}."))
    try:
        held = holding / one.name
        if whole.is_file():
            # The whole directory: what a flow imports beside itself and the skills it brings
            # are the flow as much as its entry point is.
            shutil.copytree(
                source,
                held,
                symlinks=True,
                ignore=shutil.ignore_patterns(".git", "__pycache__"),
            )
        else:
            # A flow that is one file becomes the entry point of a directory of its own, so
            # that every installed flow is the one shape and has somewhere to keep its record.
            held.mkdir()
            shutil.copy2(alone, held / ENTRY)
        try:
            # Fetched now, into the copy, so that a run of the installed flow reads every skill
            # it works by out of the flow and reaches no network for one.
            skills = packed(held)
        except OSError as why:
            raise OSError(
                f"{verse}/{one.name} {one.version} names a skill that cannot be fetched: {why}"
            ) from why
        record = Installed(
            verse=verse,
            name=one.name,
            version=one.version,
            commit=one.commit,
            repo=one.repo,
            ref=one.ref,
            subdir=one.subdir,
            dependencies=one.dependencies,
            skills=skills,
        )
        (held / RECORD).write_text(record.model_dump_json(indent=2), encoding="utf-8")
        _moved(held, root / one.name, holding)
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    return record


def _moved(held: Path, at: Path, holding: Path) -> None:
    """Moves a flow into place, moving aside whatever release is already there.

    Args:
      held: The flow, copied and recorded.
      at: Where it is to be.
      holding: The directory it was written in, which takes what was in the way and is thrown
        away by the caller.

    Raises:
      OSError: If something stays in the way however often it is moved: another install that
        keeps winning the place, or a directory that will not move.
    """
    for tries in range(_TRIES):
        try:
            held.rename(at)
        except OSError:
            if not at.exists():
                raise
        else:
            return
        if tries == _TRIES - 1:
            # Not moved aside on the last try: what is in the way is left in the place, which
            # is a whole release of somebody's, rather than the place left empty.
            break
        # Moved rather than removed, so that the place is empty only for as long as two renames
        # take, and whatever is removed is removed after the new one is in.
        with contextlib.suppress(FileNotFoundError):
            at.rename(holding / f".was{tries}")
    raise OSError(f"{at} is in the way of the install, and will not move")


def _swept(root: Path, name: str) -> None:
    """Takes away what installs of one name left beside it when they were killed.

    Only the ones old enough that nothing can still be writing them: an install going now
    writes a directory of exactly this shape.
    """
    import time

    stale = time.time() - _STALE
    for one in root.glob(f".{name}.*"):
        with contextlib.suppress(OSError):
            if one.is_dir() and one.stat().st_mtime < stale:
                shutil.rmtree(one, ignore_errors=True)


def uninstall(verse: str, flow: str) -> bool:
    """Takes away one flow installed out of an index.

    Args:
      verse: The flowverse it was installed out of.
      flow: The flow.

    Returns:
      Whether there was one to take away.

    Raises:
      ValueError: If another installed flow needs it -- which is that flow to uninstall first,
        rather than one to leave broken.
      OSError: If it will not go.
    """
    at = kept(verse) / flow
    if _record(at) is None:
        return False
    needing = sorted(
        one.called
        for one in installed(verse)
        if one.name != flow and flow in one.dependencies
    )
    if needing:
        raise ValueError(
            f"{', '.join(needing)} {'needs' if len(needing) == 1 else 'need'} {flow}; "
            "uninstall that first"
        )
    holding = Path(tempfile.mkdtemp(dir=at.parent, prefix=f".{flow}."))
    try:
        # Out of its place in one move, so that what is listed never holds half a flow.
        at.rename(holding / flow)
    except FileNotFoundError:
        return False
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    return True


def _index_of(verse: str) -> Index:
    """The index of a flowverse an install is asked of.

    Raises:
      ValueError: If there is no such flowverse, it is not an index, or it has not been
        fetched yet.
    """
    one = named(verse)
    if one is None:
        raise ValueError(f"no flowverse called {verse!r}")
    if not one.url:
        raise ValueError(f"{verse} is a directory of your own flows, not an index")
    if not one.fetched:
        raise ValueError(f"{verse} has not been fetched yet; fetch it first")
    return index(one)


def _directories(at: Path) -> list[Path]:
    """Every directory directly inside one that is not hidden, alphabetically."""
    try:
        return sorted(
            one for one in at.iterdir() if one.is_dir() and not one.name.startswith(".")
        )
    except OSError:
        return []
