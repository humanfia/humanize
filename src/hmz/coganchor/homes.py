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
  the user's refreshed token, and a session is where whatever reads it back looks. A CLI
  that saves such a file by writing another and renaming it over the name replaces the link
  with a file of the virtual home's own; as the home is dropped, each link so replaced is
  written back to what it stood for (:meth:`Home.drop`), unless what is there is newer;
- the user-level skills directory (:attr:`~hmz.coganchor.backends.Profile.lodges`) is a
  directory of links to each of the user's own skills, with the flow's beside them. A flow's
  skill of the same name as one of the user's is the one the CLI finds: the session is the
  flow's, and nothing of the user's is written to say so.

Nothing above the user level is touched: the system's own settings are wherever the CLI reads
them, and the project's are the workspace's, read as the CLI always reads them.

What Humanize itself manages for a CLI that takes it at its user level alone -- Qwen Code's
effort, a gateway's entry in Grok Build's `config.toml` -- is merged into those copies as the
home is built (:attr:`Virtual.merges`), each by a function its driver names (:func:`merger`):
said as data, so that a home built on another machine has them merged there too.

Two builders, one for each place a CLI can be: :func:`build`, wherever Humanize runs it -- here
for a CLI this machine starts, and on a harness's own machine for one supervised there
(:mod:`hmz.coganchor.elsewhere`) -- and :data:`SCRIPT`, a POSIX shell script that does the same
on a target whose own CLI a native anchor drives (:func:`hmz.coganchor.anchor.drive`), where
nothing of Humanize runs and nothing is merged.
"""

from __future__ import annotations

import contextlib
import fnmatch
import importlib
import json
import logging
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hmz.coganchor.atomic import writes

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from hmz.coganchor.backends import Profile

__all__ = [
    "BACK",
    "SCRIPT",
    "Home",
    "Virtual",
    "build",
    "merged",
    "merger",
    "virtual",
    "words",
]

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Virtual:
    """What one CLI's virtual home is made of, wherever it is built.

    Attributes:
      variable: The variable that moves the CLI's home, which is set to the virtual one; ""
        for a CLI that only a flag moves.
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
      flag: The flag that moves the CLI's home where no variable does, which takes it relative
        to the directory `default` is in; "" for a CLI a variable moves.
      merges: What a driver merges into the home once it is built, in order, as
        `(the merger's name, its argument as JSON)` (:func:`merged`).
      records: Where the CLI writes down a path of its home that it reads back, as
        `(database, as a glob; table; column)`: said again as the home is dropped.
      keeps: The directory its conversations are kept in instead of the user's home, as an
        absolute path, or "" for the user's: what :attr:`made` and :attr:`kept` link to, and
        what a database it made in the virtual home is moved into, where no supervisor
        answers their paths from there.
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
    flag: str = ""
    merges: tuple[tuple[str, str], ...] = ()
    records: tuple[tuple[str, str, str], ...] = ()
    keeps: str = ""

    def __post_init__(self) -> None:
        """Refuses a virtual home that would name something outside itself.

        Raises:
          ValueError: If the variable is not a variable name, or a path in it climbs out.
        """
        for name in (self.variable, self.secures):
            if name and not name.replace("_", "a").isalnum():
                raise ValueError(f"unsupported variable {name!r}")
        if not (self.variable or self.flag.startswith("--")):
            raise ValueError(
                "a virtual home needs the variable or the flag that moves it"
            )
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
        if self.keeps and not os.path.isabs(self.keeps):  # noqa: PTH117
            raise ValueError(
                f"unsupported directory {self.keeps!r} to keep sessions in"
            )

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
                "flag": self.flag,
                "merges": [list(one) for one in self.merges],
                "records": [list(one) for one in self.records],
                "keeps": self.keeps,
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
                flag=held.get("flag", ""),
                merges=tuple((one, other) for one, other in held.get("merges", ())),
                records=tuple(
                    (one, table, column)
                    for one, table, column in held.get("records", ())
                ),
                keeps=held.get("keeps", ""),
            )
        except (KeyError, TypeError) as wrong:
            raise ValueError(f"not a virtual home: {said!r}") from wrong

    def real(self, environ: Mapping[str, str]) -> Path:
        """The user's own home for this CLI, as a process with that environment finds it."""
        moved = environ.get(self.variable) if self.variable else None
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
    if not (profile.rewrites or profile.lodges) or not (
        profile.home_var or profile.home_flag
    ):
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
        flag="" if profile.home_var else profile.home_flag,
        # A private home's databases are its own, brought back with what they name.
        records=() if private else profile.records,
    )


def _globbed(name: str) -> bool:
    """Whether a name is a pattern rather than a name."""
    return any(one in name for one in "*?[")


#: Every way of merging what a driver manages into a virtual home, by its name (:func:`merger`).
_MERGERS: dict[str, Callable[[Path, Any], None]] = {}


def merger(merging: Callable[[Path, Any], None]) -> Callable[[Path, Any], None]:
    """Makes a function one way of merging what a driver manages into a virtual home.

    Named by its module and its own name, which is how :func:`build` finds it on a machine
    where nothing has imported it yet: a harness's own, where the home is built by the anchor
    supervising the CLI there.

    Args:
      merging: It, which is called with the home just built and what :func:`merged` was given.

    Returns:
      It, as it was.
    """
    _MERGERS[f"{merging.__module__}:{merging.__qualname__}"] = merging
    return merging


def merged(merging: Callable[[Path, Any], None], said: Any = None) -> tuple[str, str]:
    """One merge into a home, as :attr:`Virtual.merges` holds it.

    Args:
      merging: A function :func:`merger` made one.
      said: What it is to be given, which crosses as JSON.

    Returns:
      `(its name, its argument as JSON)`.

    Raises:
      ValueError: If it is not one :func:`merger` made.
    """
    name = f"{merging.__module__}:{merging.__qualname__}"
    if _MERGERS.get(name) is not merging:
        raise ValueError(f"{name} is not a merger")
    return name, json.dumps(said)


def _merging(name: str) -> Callable[[Path, Any], None]:
    """The merger of that name, its module imported first where none of it is here yet.

    Raises:
      ValueError: If Humanize has no merger of that name.
    """
    module = name.partition(":")[0]
    if name not in _MERGERS and module.startswith("hmz."):
        with contextlib.suppress(ImportError):
            importlib.import_module(module)
    try:
        return _MERGERS[name]
    except KeyError:
        raise ValueError(f"no merger {name!r}") from None


@dataclass(frozen=True, slots=True)
class Home:
    """One virtual home, built on this machine.

    Attributes:
      at: Where it is, with every link in its path followed: the spelling a CLI is told.
      real: The user's own home it stands for.
      sets: What a process started in it is to be started with on top of its environment.
      rewrites: What in it is a copy of its own, as :attr:`Virtual.rewrites`.
      kept: What of it is moved into the user's home as it is dropped, as :attr:`Virtual.kept`.
      argv: What the CLI is told after its own name to be started in it: the flag naming it,
        for a CLI no variable moves.
      linked: The names directly in it that were links to the user's home when it was built:
        what is written back as it is dropped, where the CLI replaced one.
      answered: What a supervisor answers a path of the user's home with, as :func:`build`
        took it: where what is written back goes instead, for an account's own file.
      records: Where the CLI writes down paths of this home, as :attr:`Virtual.records`.
      keeps: Where its conversations are kept instead of :attr:`real`, as
        :attr:`Virtual.keeps`; None for the user's home.
      held: The names of :attr:`linked` that were links into :attr:`keeps`: what is written
        back there rather than to the user's home.
    """

    at: Path
    real: Path
    sets: tuple[tuple[str, str], ...]
    rewrites: tuple[str, ...] = ()
    kept: tuple[str, ...] = ()
    argv: tuple[str, ...] = ()
    linked: tuple[str, ...] = ()
    answered: Callable[[str], str | None] = field(
        default=lambda _path: None, compare=False, repr=False
    )
    records: tuple[tuple[str, str, str], ...] = ()
    keeps: Path | None = None
    held: tuple[str, ...] = ()

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

        A link the CLI replaced -- a credential or a session file it saved by renaming another
        over it -- is written back first to what it stood for, or to what a supervisor answers
        that with: a file whole and atomically, with the mode the one there had; a directory a
        file at a time, each that is new or changed. Never over one that is newer, which is
        another process of the same account having saved since: the last to save wins.

        What the CLI made here that is the user's to keep (:attr:`kept`) and that the user's
        home -- or :attr:`keeps`, for a home keeping its conversations there -- has none of yet
        is moved there next, rather than going with the rest. And a path of this home it wrote
        down to read back (:attr:`records`) is said again with its links followed, while they
        are still here to follow: what it names is where they lead.
        """
        _respelled(self.at, self.records, self.kept if self.keeps is not None else ())
        for name in self.linked:
            whence = (
                self.keeps
                if self.keeps is not None and name in self.held
                else self.real
            )
            entry = self.at / name
            if entry.is_symlink() or not entry.exists():
                continue
            if entry.is_dir():
                try:
                    held = sorted(entry.rglob("*"))
                except OSError as why:
                    log.warning("could not write %s back: %s", entry, why)
                    continue
                for one in held:
                    if one.is_file() and not one.is_symlink():
                        _back(
                            one,
                            whence / name / one.relative_to(entry),
                            self.answered,
                        )
            else:
                _back(entry, whence / name, self.answered)
        into = self.real if self.keeps is None else self.keeps
        with contextlib.suppress(OSError):
            for entry in self.at.iterdir() if self.kept else ():
                there = into / entry.name
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
      ValueError: If one of its merges is none of Humanize's. And whatever a merger raises,
        for what it could not merge.
    """
    said = os.environ if environ is None else environ
    real = spec.real(said)
    at = Path(os.path.realpath(tempfile.mkdtemp(prefix="hmz-home-", dir=under)))
    try:
        linked, held = _built(spec, said, real, at, answered)
        for name, argument in spec.merges:
            _merging(name)(at, json.loads(argument))
    except BaseException:
        shutil.rmtree(at, ignore_errors=True)
        raise
    # What a merge made the home's own in place of a link is the driver's, never written back.
    linked = tuple(one for one in linked if (at / one).is_symlink())
    held = tuple(one for one in held if one in linked)
    sets = [(spec.variable, str(at))] if spec.variable else []
    argv: tuple[str, ...] = ()
    if spec.flag:
        # Relative to where the default home is, which is the only way such a flag takes one:
        # climbing out of there, for a home that is somewhere else entirely.
        whence = Path(said.get("HOME") or Path.home()) / spec.default
        argv = (f"{spec.flag}={os.path.relpath(at, whence.parent)}",)
    if spec.secures and spec.secures not in said:
        # The user's own value of the home variable, or nothing: Claude Code names its
        # keychain item and finds `.credentials.json` by this, and an empty one is the home
        # it would have had with the variable unset.
        sets.append((spec.secures, said.get(spec.variable, "")))
    return Home(
        at=at,
        real=real,
        sets=tuple(sets),
        rewrites=spec.rewrites,
        kept=spec.kept,
        argv=argv,
        linked=linked,
        answered=answered,
        records=spec.records,
        keeps=Path(spec.keeps) if spec.keeps else None,
        held=held,
    )


def _respelled(
    at: Path, records: Iterable[tuple[str, str, str]], moved: Iterable[str] = ()
) -> None:
    """Says each path of a virtual home a CLI's databases hold with that home's links followed.

    Only through a database that is a link, which is the user's, or one of the home's own that
    is moved out of it as it is dropped (`moved`, globs of its names): any other goes with it.
    A path whose file is not there to follow to is left as it was.
    """
    moved = tuple(moved)
    import sqlite3

    root = f"{at}/"
    for pattern, table, column in records:
        for database in sorted(at.glob(pattern)):
            if not database.is_symlink() and not any(
                fnmatch.fnmatchcase(database.name, one) for one in moved
            ):
                continue
            try:
                connection = sqlite3.connect(database, timeout=10)
            except sqlite3.Error as why:
                log.warning("could not read %s: %s", database, why)
                continue
            try:
                with connection:
                    said = connection.execute(
                        f'select rowid, "{column}" from "{table}"'  # noqa: S608 -- names of ours
                        f' where substr("{column}", 1, ?) = ?',
                        (len(root), root),
                    ).fetchall()
                    for row, path in said:
                        followed = os.path.realpath(path)
                        if followed != path and Path(followed).exists():
                            connection.execute(
                                f'update "{table}" set "{column}" = ?'  # noqa: S608
                                " where rowid = ?",
                                (followed, row),
                            )
            except sqlite3.Error as why:
                log.warning("could not respell %s in %s: %s", column, database, why)
            finally:
                connection.close()


def _built(
    spec: Virtual,
    said: Mapping[str, str],
    real: Path,
    at: Path,
    answered: Callable[[str], str | None],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Fills a virtual home in; :func:`build`'s, which takes it away again if this fails.

    Returns:
      The names directly in it that it linked to the user's home or to where its
      conversations are kept, and of those the ones linked to the latter.
    """
    linked: list[str] = []
    held: list[str] = []
    keeps = Path(spec.keeps) if spec.keeps else None
    sessions = real if keeps is None else keeps
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
            (sessions / name).mkdir(parents=True, exist_ok=True)
        elif not sessions.is_dir():
            sessions.mkdir(parents=True)
        if _link(at / name, sessions / name):
            linked.append(name)
            held.append(name)
    if keeps is not None and spec.kept:
        # A database named for its schema's version: whichever the user's home or the kept
        # directory has, linked to the kept one -- there or not yet -- so that the CLI opening
        # it opens that one, as every process keeping its conversations there does.
        keeps.mkdir(parents=True, exist_ok=True)
        names = {
            entry.name
            for root in (real, keeps)
            if root.is_dir()
            for entry in root.iterdir()
            if any(fnmatch.fnmatchcase(entry.name, one) for one in spec.kept)
        }
        for name in sorted(names):
            if _link(at / name, keeps / name):
                linked.append(name)
                held.append(name)
    if real.is_dir():
        for entry in real.iterdir():
            name = entry.name
            if name in copied or name == spec.lodges:
                continue
            if any(fnmatch.fnmatchcase(name, one) for one in spec.private):
                continue
            if _link(at / name, entry):
                linked.append(name)
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
    return tuple(linked), tuple(held)


def _link(at: Path, to: Path) -> bool:
    """Links one name to what it stands for, leaving one already there as it is.

    Returns:
      Whether it linked it.
    """
    try:
        at.symlink_to(to)
    except FileExistsError:
        return False
    return True


def _back(entry: Path, whence: Path, answered: Callable[[str], str | None]) -> None:
    """Writes one file the CLI saved in place of a link back to where the link pointed.

    Never raises: this runs as a home is dropped, which is the end of a turn.

    Args:
      entry: The file the CLI saved.
      whence: Where it stands for in the user's home.
      answered: What a supervisor answers that with, as :func:`build` took it.
    """
    there = whence
    try:
        there = Path(os.path.realpath(answered(str(whence)) or whence))
        now = entry.stat()
        try:
            was: os.stat_result | None = there.stat()
        except FileNotFoundError:
            was = None
        if was is not None and (
            not stat.S_ISREG(was.st_mode) or was.st_mtime_ns >= now.st_mtime_ns
        ):
            return  # saved there since, or not a file to write over
        there.parent.mkdir(parents=True, exist_ok=True)
        with entry.open("rb") as reading:
            writes(
                there,
                iter(lambda: reading.read(1 << 20), b""),
                mode=stat.S_IMODE((was or now).st_mode),
            )
        os.utime(there, ns=(now.st_atime_ns, now.st_mtime_ns))
    except OSError as why:
        log.warning("could not write %s back to %s: %s", entry, there, why)


#: The same as :func:`build`, as a POSIX shell script for a target where nothing of Humanize
#: runs. Run as `sh -c SCRIPT Humanize AT VARIABLE DEFAULT LODGES [WORD...]`, after anything
#: projected into `AT` has landed there, which this leaves as it is. Each word is one of
#: `copy=PATH=OUTSIDE` (a rewrite, and where it is under `~` while the variable is unset, or
#: nothing), `keep=GLOB` (private), `make=NAME` (made) and `skill=NAME` (a flow's own skill,
#: which the caller writes into `AT/LODGES/NAME` afterwards). It prints the user's own value
#: of the variable, which is what `secures` is set to. What it links directly in `AT` it lists,
#: a target per line, in `AT.links` beside it, for :data:`BACK`.
SCRIPT = r"""
set -e
at=$1 var=$2 default=$3 lodges=$4
shift 4
eval "moved=\${$var:-}"
real=${moved:-$HOME/$default}
umask 077
mkdir -p "$at"
: > "$at.links"
nl='
'
link() {
  if [ -e "$at/$1" ] || [ -h "$at/$1" ]; then return 0; fi
  ln -s -- "$real/$1" "$at/$1"
  case $real/$1 in *"$nl"*) ;; *) printf '%s\n' "$real/$1" >> "$at.links" ;; esac
}
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
    link "$name" ;;
  esac
done
for f in "$real"/* "$real"/.[!.]* "$real"/..?*; do
  [ -e "$f" ] || [ -h "$f" ] || continue
  name=${f##*/}
  skipped "$@" && continue
  link "$name"
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


#: :meth:`Home.drop`'s writing back, for a home :data:`SCRIPT` built: run as
#: `sh -c BACK Humanize AT` once the CLI is done, before `AT` is taken away. Each link listed in
#: `AT.links` that the CLI replaced is written back to the file it pointed at -- a directory a
#: file at a time -- by a copy renamed over it, with the mode the one there had, and never over
#: one that is as new or newer.
BACK = r"""
at=$1
shift
[ -f "$at.links" ] || exit 0
put='
src=$1 dst=$2
shift 2
for g in "$@"; do
  [ -f "$g" ] && [ ! -h "$g" ] || continue
  t=$dst${g#"$src"} n=0
  while [ -h "$t" ] && [ $n -lt 8 ]; do
    l=$(readlink -- "$t") || break
    case $l in /*) t=$l ;; *) t=$(dirname -- "$t")/$l ;; esac
    n=$((n + 1))
  done
  if [ -e "$t" ]; then
    [ -f "$t" ] || continue
    # Where times are only to the second, the same second and other bytes is newer.
    [ "$g" -nt "$t" ] || { ! [ "$t" -nt "$g" ] && ! cmp -s -- "$g" "$t"; } || continue
  fi
  d=$(dirname -- "$t")
  mkdir -p -- "$d" 2>/dev/null || continue
  tmp=$d/.hmz-back.$$
  rm -f -- "$tmp"
  if [ -e "$t" ] && cp -p -- "$t" "$tmp" 2>/dev/null && cat -- "$g" > "$tmp" 2>/dev/null &&
    touch -r "$g" "$tmp"; then :
  else rm -f -- "$tmp"; cp -p -- "$g" "$tmp" || { rm -f -- "$tmp"; continue; }
  fi
  mv -f -- "$tmp" "$t" || rm -f -- "$tmp"
done
'
while IFS= read -r f; do
  p=$at/${f##*/}
  if [ -h "$p" ]; then continue; fi
  if [ -d "$p" ]; then find "$p" -type f -exec sh -c "$put" sh "$p" "$f" {} +
  elif [ -f "$p" ]; then sh -c "$put" sh "$p" "$f" "$p"
  fi
done < "$at.links"
command -v sqlite3 >/dev/null 2>&1 || exit 0
q() { printf '%s' "$1" | sed "s/'/''/g"; }
for word in "$@"; do
  case $word in record=*) ;; *) continue ;; esac
  spec=${word#record=}; glob=${spec%%=*}; rest=${spec#*=}
  table=${rest%%=*}; column=${rest#*=}
  for db in "$at"/$glob; do
    [ -h "$db" ] || continue
    while IFS= read -r f; do
      from=$(q "$at/${f##*/}/"); to=$(q "$f/")
      sqlite3 -cmd '.timeout 10000' "$db" "UPDATE \"$table\" SET \"$column\" = '$to' ||
        substr(\"$column\", length('$from') + 1)
        WHERE substr(\"$column\", 1, length('$from')) = '$from';" 2>/dev/null || :
    done < "$at.links"
  done
done
exit 0
"""


def words(spec: Virtual) -> list[str]:
    """What :data:`SCRIPT` is told after its first four arguments, for one virtual home.

    And :data:`BACK` after its first: the paths its databases hold of the home
    (:attr:`Virtual.records`), said again with the home's links followed where the target has
    `sqlite3` to say them with, which `SCRIPT` passes over.
    """
    outside = dict(spec.outside)
    return [
        *(f"copy={one}={outside.get(one, '')}" for one in spec.rewrites),
        *(f"keep={one}" for one in spec.private),
        *(f"make={one}" for one in spec.made),
        *(f"skill={name}" for name, _ in spec.skills),
        *(f"record={one}={table}={column}" for one, table, column in spec.records),
    ]
