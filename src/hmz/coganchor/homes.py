"""A CLI's virtual home: its user-level directory, rebuilt for one process of it and dropped after.

A coding agent CLI writes its own configuration while it runs. Claude Code rewrites
`.claude.json` with every project it has been opened in, Codex's app server writes
`projects."<workspace>".trust_level` into `config.toml` for every workspace it opened a writing
thread in -- and a flow opens a great many workspaces, temporary ones among them. Run against the
user's own home, every one of those writes is a change to their configuration that outlives the
run, and is read by every CLI they start afterwards.

So a process of such a CLI is started with its home variable naming a directory of its own,
built on the machine the CLI runs on as it starts and taken away when it stops:

- the files the CLI rewrites (:attr:`~hmz.coganchor.backends.Profile.rewrites`) are *copies* of
  the user's own, so that what it writes lands in the copy and goes with it;
- everything else of the user's home is *linked*, so that credentials, caches and the
  conversations the CLI keeps are the ones it always reads and writes -- a refreshed token is
  the user's refreshed token, and a session is where whatever reads it back looks;
- the user-level skills directory (:attr:`~hmz.coganchor.backends.Profile.lodges`) is a
  directory of links to each of the user's own skills, with the flow's beside them. A flow's
  skill of the same name as one of the user's is the one the CLI finds: the session is the
  flow's, and nothing of the user's is written to say so.

Nothing above the user level is touched: the system's own settings are wherever the CLI reads
them, and the project's are the workspace's, read as the CLI always reads them.

Two builders, one for each place a CLI can be: :func:`build`, here, for a CLI this machine
starts, and :data:`SCRIPT`, a POSIX shell script that does the same on a target whose own CLI a
native anchor drives (:func:`hmz.coganchor.anchor.drive`), where nothing of humanize runs.
"""

from __future__ import annotations

import contextlib
import fnmatch
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from hmz.coganchor.backends import Profile

__all__ = ["SCRIPT", "Home", "Virtual", "build", "virtual", "words"]


@dataclass(frozen=True, slots=True)
class Virtual:
    """What one CLI's virtual home is made of, wherever it is built.

    Attributes:
      variable: The variable that moves the CLI's home, which is set to the virtual one.
      default: Where that home is under the user's own where the variable is unset.
      rewrites: What under that home is copied rather than linked, relative to it.
      outside: For each of those kept outside the home while the variable is unset, where
        -- relative to the user's own home -- as `(path under the home, path under ~)`.
      lodges: The user-level skills directory under the home, or "" for none.
      secures: A variable that keeps where the CLI looks for its sign-in -- a keychain item
        named for its home, a credentials file in it -- where the user's own home would put
        it, or "" for a CLI whose sign-in moves with the home like any other file.
      private: Names directly under the home, each of which may be a glob, that are neither
        linked nor made: what a turn keeps in the virtual home itself, such as the
        conversations of an account projected into it.
      made: Names directly under the home whose own directory is made where the user has
        none yet, so that what the CLI first writes there lands in the user's home rather
        than in this one: where its conversations are kept. A name with a dot is a file, and
        is linked to where it would be without being made.
      kept: Globs of names directly under the home that are the user's to keep but cannot be
        linked before the CLI names them -- a database named for its schema's version. One
        the CLI made in the virtual home, where the user's has none, is moved into the user's
        as the home is dropped.
      skills: The flow's own skills, as `(name, the directory holding its SKILL.md)`.
    """

    variable: str
    default: str
    rewrites: tuple[str, ...] = ()
    outside: tuple[tuple[str, str], ...] = ()
    lodges: str = ""
    secures: str = ""
    private: tuple[str, ...] = ()
    made: tuple[str, ...] = ()
    kept: tuple[str, ...] = ()
    skills: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        """Refuses a virtual home that would name something outside itself.

        Raises:
          ValueError: If the variable is not a variable name, or a path in it climbs out.
        """
        for name in (self.variable, self.secures):
            if name and not name.replace("_", "a").isalnum():
                raise ValueError(f"unsupported variable {name!r}")
        if not self.variable:
            raise ValueError("a virtual home needs the variable that moves it")
        for one in (
            self.default,
            *self.rewrites,
            *(there for _, there in self.outside),
            self.lodges,
            *self.made,
            *(name for name, _ in self.skills),
        ):
            if one.startswith("/") or ".." in one.split("/"):
                raise ValueError(f"unsupported path {one!r} in a virtual home")

    def dumps(self) -> str:
        """It, as one JSON line a command line can carry."""
        return json.dumps(
            {
                "variable": self.variable,
                "default": self.default,
                "rewrites": list(self.rewrites),
                "outside": [list(one) for one in self.outside],
                "lodges": self.lodges,
                "secures": self.secures,
                "private": list(self.private),
                "made": list(self.made),
                "kept": list(self.kept),
                "skills": [list(one) for one in self.skills],
            },
            separators=(",", ":"),
        )

    @classmethod
    def loads(cls, said: str) -> Virtual:
        """Reads what :meth:`dumps` wrote.

        Raises:
          ValueError: If it is not that.
        """
        try:
            held = json.loads(said)
            return cls(
                variable=held["variable"],
                default=held["default"],
                rewrites=tuple(held["rewrites"]),
                outside=tuple((one, other) for one, other in held["outside"]),
                lodges=held["lodges"],
                secures=held["secures"],
                private=tuple(held["private"]),
                made=tuple(held["made"]),
                kept=tuple(held["kept"]),
                skills=tuple((one, other) for one, other in held["skills"]),
            )
        except (KeyError, TypeError) as wrong:
            raise ValueError(f"not a virtual home: {said!r}") from wrong

    def real(self, environ: Mapping[str, str]) -> Path:
        """The user's own home for this CLI, as a process with that environment finds it."""
        moved = environ.get(self.variable)
        if moved:
            return Path(moved)
        return Path(environ.get("HOME") or Path.home()) / self.default


def virtual(
    profile: Profile,
    skills: Iterable[tuple[str, str]] = (),
    *,
    private: bool = False,
) -> Virtual | None:
    """What a process of one CLI is started with a virtual home of, or None for no such CLI.

    Args:
      profile: The CLI.
      skills: The flow's own skills it is to carry, as `(name, directory)`.
      private: Whether its conversations are kept in the virtual home itself rather than
        linked to the user's: a native turn whose account is projected into it, which brings
        them back from there. Its credentials are then the projected account's alone: none of
        the user's is linked or copied beside them.

    Returns:
      The virtual home, or None for a CLI that writes nothing of its home worth keeping from
      the user and carries no skills there -- every CLI that has not said otherwise -- and for
      one whose variable names a parent of its home rather than the home.
    """
    if not (profile.rewrites or profile.lodges) or not profile.home_var:
        return None
    if profile.home_in:
        return None
    names = tuple(dict.fromkeys(said.split("/")[0] for said in profile.sessions))
    creds = {
        said.split("/")[0]
        for said in profile.creds
        if not said.startswith(("~/", "config/"))
    }
    return Virtual(
        variable=profile.home_var,
        default=profile.home_dir,
        rewrites=tuple(
            one for one in profile.rewrites if not (private and one in creds)
        ),
        outside=profile.outside,
        lodges=profile.lodges,
        secures=profile.secures,
        private=(*names, *sorted(creds)) if private else (),
        made=() if private else tuple(one for one in names if not _globbed(one)),
        kept=() if private else tuple(one for one in names if _globbed(one)),
        skills=tuple(skills) if profile.lodges else (),
    )


def _globbed(name: str) -> bool:
    """Whether a name is a pattern rather than a name."""
    return any(one in name for one in "*?[")


@dataclass(frozen=True, slots=True)
class Home:
    """One virtual home, built on this machine.

    Attributes:
      at: Where it is, with every link in its path followed: the spelling a CLI is told.
      real: The user's own home it stands for.
      sets: What a process started in it is to be started with on top of its environment.
      rewrites: What in it is a copy of its own, as :attr:`Virtual.rewrites`.
      kept: What of it is moved into the user's home as it is dropped, as :attr:`Virtual.kept`.
    """

    at: Path
    real: Path
    sets: tuple[tuple[str, str], ...]
    rewrites: tuple[str, ...] = ()
    kept: tuple[str, ...] = ()

    def environ(self, environ: Mapping[str, str] | None) -> dict[str, str]:
        """The whole environment a process of the CLI is started in, given the one it had.

        Args:
          environ: The environment it would have had, or None for this process's own.

        Returns:
          It, with the home moved here.
        """
        return {**(os.environ if environ is None else environ), **dict(self.sets)}

    def spelled(self, pairs: Iterable[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
        """Paths a supervisor answers under the real home, said under this one too.

        A supervisor answers the path a CLI names, before anything follows a link in it: one
        that names a session or a credential through this home names a path no table of the
        real home's has heard of. So each is said again with this home in place of that one,
        and answered the same.

        Not what this home copies: that is this home's own, which the CLI is to read here
        rather than be answered for.

        Args:
          pairs: `(the path the CLI names, the path it gets)`, as a supervisor takes them.

        Returns:
          The pairs, and one more per pair under the real home -- by either spelling of it.
        """
        roots = dict.fromkeys((str(self.real), os.path.realpath(self.real)))
        copied = {one.split("/")[0] for one in self.rewrites}
        held = list(pairs)
        added: list[tuple[str, str]] = []
        for named, instead in held:
            for root in roots:
                if not named.startswith(root + "/"):
                    continue
                under = named[len(root) + 1 :]
                if under.split("/")[0] not in copied:
                    added.append((f"{self.at}/{under}", instead))
        return tuple(dict.fromkeys((*held, *added)))

    def drop(self) -> None:
        """Takes it away: the copies and the links, never what a link points at.

        What the CLI made here that is the user's to keep (:attr:`kept`) and that the user's
        home has none of yet is moved there first, rather than going with the rest.
        """
        with contextlib.suppress(OSError):
            for entry in self.at.iterdir() if self.kept else ():
                there = self.real / entry.name
                if (
                    not entry.is_symlink()
                    and any(fnmatch.fnmatchcase(entry.name, one) for one in self.kept)
                    and not there.exists()
                ):
                    shutil.move(entry, there)
        shutil.rmtree(self.at, ignore_errors=True)


def build(
    spec: Virtual,
    environ: Mapping[str, str] | None = None,
    *,
    under: Path | None = None,
    answered: Callable[[str], str | None] = lambda _path: None,
) -> Home:
    """Builds one virtual home on this machine, for one process of the CLI about to start.

    Args:
      spec: What it is made of.
      environ: The environment that process would have been started in, which is what says
        where the user's own home is; None for this process's own.
      under: The directory to make it in, or None for the system's temporary one.
      answered: What a supervisor would answer a path of the user's home with, or None for a
        path it leaves alone: a provider's own copy of a credential, which is what the CLI
        would have read where this home copies the file instead.

    Returns:
      The home, to be dropped once the process is over.

    Raises:
      OSError: If it could not be built, which is a turn that must not run: a CLI pointed at
        half a home is a CLI that has lost its settings.
    """
    said = os.environ if environ is None else environ
    real = spec.real(said)
    at = Path(os.path.realpath(tempfile.mkdtemp(prefix="hmz-home-", dir=under)))
    try:
        _built(spec, said, real, at, answered)
    except OSError:
        shutil.rmtree(at, ignore_errors=True)
        raise
    sets = [(spec.variable, str(at))]
    if spec.secures and spec.secures not in said:
        # The user's own value of the home variable, or nothing: Claude Code names its
        # keychain item and finds `.credentials.json` by this, and an empty one is the home
        # it would have had with the variable unset.
        sets.append((spec.secures, said.get(spec.variable, "")))
    return Home(
        at=at, real=real, sets=tuple(sets), rewrites=spec.rewrites, kept=spec.kept
    )


def _built(
    spec: Virtual,
    said: Mapping[str, str],
    real: Path,
    at: Path,
    answered: Callable[[str], str | None],
) -> None:
    """Fills a virtual home in; :func:`build`'s, which takes it away again if this fails."""
    for one in spec.rewrites:
        whence = real / one
        if not said.get(spec.variable):
            for name, there in spec.outside:
                if name == one:
                    whence = Path(said.get("HOME") or Path.home()) / there
        source = Path(answered(str(whence)) or whence)
        into = at / one
        into.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            # A directory the CLI writes into -- Claude's backups of what it rewrites -- starts
            # empty: what it holds is the user's, and none of it is read back.
            into.mkdir(exist_ok=True)
        elif source.is_file():
            shutil.copy2(source, into)
    copied = {one.split("/")[0] for one in spec.rewrites}
    for name in spec.made:
        if name in copied or name == spec.lodges:
            continue
        if "." not in name:
            (real / name).mkdir(parents=True, exist_ok=True)
        elif not real.is_dir():
            real.mkdir(parents=True)
        _link(at / name, real / name)
    if real.is_dir():
        for entry in real.iterdir():
            name = entry.name
            if name in copied or name == spec.lodges:
                continue
            if any(fnmatch.fnmatchcase(name, one) for one in spec.private):
                continue
            _link(at / name, entry)
    if spec.lodges:
        into = at / spec.lodges
        into.mkdir(parents=True, exist_ok=True)
        flows = {name for name, _ in spec.skills}
        theirs = real / spec.lodges
        if theirs.is_dir():
            for entry in theirs.iterdir():
                if entry.name not in flows:
                    _link(into / entry.name, entry)
        for name, whence in spec.skills:
            _link(into / name, Path(whence))


def _link(at: Path, to: Path) -> None:
    """Links one name to what it stands for, leaving one already there as it is."""
    with contextlib.suppress(FileExistsError):
        at.symlink_to(to)


#: The same as :func:`build`, as a POSIX shell script for a target where nothing of humanize
#: runs. Run as `sh -c SCRIPT humanize AT VARIABLE DEFAULT LODGES [WORD...]`, after anything
#: projected into `AT` has landed there, which this leaves as it is. Each word is one of
#: `copy=PATH=OUTSIDE` (a rewrite, and where it is under `~` while the variable is unset, or
#: nothing), `keep=GLOB` (private), `make=NAME` (made) and `skill=NAME` (a flow's own skill,
#: which the caller writes into `AT/LODGES/NAME` afterwards). It prints the user's own value
#: of the variable, which is what `secures` is set to.
SCRIPT = r"""
set -e
at=$1 var=$2 default=$3 lodges=$4
shift 4
eval "moved=\${$var:-}"
real=${moved:-$HOME/$default}
umask 077
mkdir -p "$at"
skipped() {
  for word in "$@"; do
    case $word in
    copy=*) spec=${word#copy=}; rel=${spec%%=*}; [ "$name" = "${rel%%/*}" ] && return 0 ;;
    keep=*) case $name in ${word#keep=}) return 0 ;; esac ;;
    esac
  done
  [ "$name" = "$lodges" ]
}
for word in "$@"; do
  case $word in
  copy=*)
    spec=${word#copy=}; rel=${spec%%=*}; alt=${spec#*=}; src=$real/$rel
    if [ -z "$moved" ] && [ -n "$alt" ]; then src=$HOME/$alt; fi
    if [ -d "$src" ]; then mkdir -p "$at/$rel"
    elif [ ! -e "$at/$rel" ] && [ -e "$src" ]; then
      mkdir -p "$(dirname -- "$at/$rel")"; cp -p -- "$src" "$at/$rel"
    fi ;;
  esac
done
for word in "$@"; do
  case $word in
  make=*)
    name=${word#make=}
    skipped "$@" && continue
    case $name in *.*) mkdir -p "$real" ;; *) mkdir -p "$real/$name" ;; esac
    [ -e "$at/$name" ] || [ -h "$at/$name" ] || ln -s -- "$real/$name" "$at/$name" ;;
  esac
done
for f in "$real"/* "$real"/.[!.]* "$real"/..?*; do
  [ -e "$f" ] || [ -h "$f" ] || continue
  name=${f##*/}
  skipped "$@" && continue
  [ -e "$at/$name" ] || [ -h "$at/$name" ] || ln -s -- "$f" "$at/$name"
done
if [ -n "$lodges" ]; then
  mkdir -p "$at/$lodges"
  for f in "$real/$lodges"/* "$real/$lodges"/.[!.]* "$real/$lodges"/..?*; do
    [ -e "$f" ] || [ -h "$f" ] || continue
    name=${f##*/}
    ours=
    for word in "$@"; do [ "$word" = "skill=$name" ] && ours=1; done
    [ -n "$ours" ] || [ -e "$at/$lodges/$name" ] || ln -s -- "$f" "$at/$lodges/$name"
  done
fi
printf '%s\n' "$moved"
"""


def words(spec: Virtual) -> list[str]:
    """What :data:`SCRIPT` is told after its first four arguments, for one virtual home."""
    outside = dict(spec.outside)
    return [
        *(f"copy={one}={outside.get(one, '')}" for one in spec.rewrites),
        *(f"keep={one}" for one in spec.private),
        *(f"make={one}" for one in spec.made),
        *(f"skill={name}" for name, _ in spec.skills),
    ]
