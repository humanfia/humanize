"""One run of one flow, packaged up whole so that somebody else can read it.

An epic is what a run was, and it is written to be read on the machine it ran on: the record
of what happened, the state a resumable flow left, the trace anybody gathered afterwards --
and, beside those, the sessions themselves, which every turn of the run kept there in the
layout its CLI keeps them in at home.

A directory is not something to attach to an issue, so this is the other reading of a run:
every file each session was logged to carried whole, every record it holds, and a manifest
saying what humanize and each backend were when it ran -- their versions, and the hash of the
executable that actually took the turns. One archive. An epic written before sessions were
kept holds links instead, and those are followed to the files behind them.

**What it carries is the user's. What it never carries is a credential.**
:mod:`hmz.runtime.telemetry` promises that nothing anybody typed, nothing an agent said and nothing
out of any file leaves the machine on humanize's initiative. A bundle is the opposite errand --
somebody is sending their run on purpose, prompts and output and all, because a report of a bug
without the run in it is a report nobody can develop against -- so the contents are theirs to send.
Credentials are nobody's to send. Every byte written here goes through :func:`plain` first: the
values of every account's variables struck out literally, the shapes the vendors mint keys in struck
out by pattern, and anything signed into a URL taken out the way a flowverse's own URL is taken
apart before it is shown. A token in a bundle is a token in an issue tracker, forever.

Less what the run is read by. `input_tokens` is how these backends write down what a turn
cost, and an account may hold the model to ask for -- a bundle with the bill or the model
struck out of it is a bundle nobody can develop against either.

A backend that logs nothing -- opencode and mimocode keep their sessions in a database of
their own -- is said so in the manifest rather than left as an empty directory. A bundle that
quietly holds no sessions and a backend that quietly writes none read identically, and only
one of them is a bug.

And read back. A bundle imported on another machine is an epic there like any other, under
the workspace it says it ran in and laid out as one written there would be -- each session's
logs where that session says it is kept -- with a line saying where it came from. Whether it
can be picked up is :func:`hmz.runtime.epic.foreign`'s to say.
"""

from __future__ import annotations

import contextlib
import datetime
import gzip
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import zlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz.coganchor import backends
from hmz.runtime.epic import (
    JOURNAL,
    RESUME,
    SESSIONS,
    TRACES,
    logs,
    note,
    read,
    records,
    sessions,
    tree,
    under,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    from hmz.runtime.epic import Called, Ran, Session

__all__ = [
    "BUNDLE",
    "MANIFEST",
    "REDACTED",
    "STRUCK",
    "TRANSCRIPT",
    "bundle",
    "logged",
    "placed",
    "plain",
    "sized",
    "unbundle",
    "unpacked",
]

#: What a bundle is called, which says which run it is of rather than when it was written: a
#: run has a name already and that name holds the moment it started, so a second moment in
#: the filename would only say when somebody pressed the key. Exporting one run twice is the
#: same run twice, and the later archive is the earlier one plus whatever has happened since
#: -- so it replaces it rather than leaving two nobody can tell apart.
#: A gzipped tar all the same, under an extension of its own so that an import knows one when
#: it is handed one.
BUNDLE = "{epic}.hmzepic"

#: What the archive says about itself.
MANIFEST = "manifest.json"

#: What a transcript goes in, for the caller that has one to hand in. There is none in a
#: bundle asked for of a run out of `/epics` or from a command line: a run in that list may be
#: a week old and what is on the screen now is not it, and an empty file saying so would read
#: as a run that said nothing.
TRANSCRIPT = "transcript.md"

#: What stands where something was taken out. One word, so that a bundle can be read for what
#: was struck as easily as for what was not.
REDACTED = "[redacted]"

#: What is taken out of everything written here, in the words the manifest repeats and the
#: documentation says. This is the promise; the patterns below are what keep it true.
STRUCK = (
    "every account's own variables, by value, less what the run says it ran",
    "keys in the shapes the vendors mint them -- sk-, ghp_, AIza, a JWT",
    "whatever is signed into a URL, as a user, a password or a query",
    "anything a log named as a token, a secret, a key or a password",
)

#: How long a value has to be before striking it out is worth more than reading it. An
#: account's variables are struck by value rather than by name -- the address of somebody's
#: private gateway is as much theirs as the key that opens it -- but a variable set to `1` or
#: to `true` is a word, and striking every `true` out of a session log would leave a bundle
#: nobody can read.
_ENOUGH = 8

#: How much of a file is scrubbed in memory before the rest spills to disk. A session log is
#: read a line at a time and most are small; a nine-hour run's is not, and a bundle that read
#: one of those whole would want the memory of the run that wrote it.
_SPOOL = 1 << 20

#: How long a program is given to say what version it is, or a repository to say what commit
#: it is on. Neither is what an export is for, so one that hangs is a manifest with a field
#: missing rather than an export that never finishes.
_PATIENCE = 20.0

#: How much of what a backend says about itself is kept. Some of them print a banner.
_ENOUGH_VERSION = 200

#: What a size is said in, thousands apart, and where the digits stop mattering. A line about
#: a file is read for whether it is small enough to attach to something.
_UNITS = ("B", "kB", "MB", "GB", "TB")
_THOUSAND = 1000.0
_ROUGHLY = 10.0

#: What is struck out of every byte this writes, by pattern, and what stands in its place.
#: Read in order, and written here rather than reached for in :mod:`hmz.runtime.telemetry`: that
#: module scrubs what humanize sends about somebody, which is a promise about names and
#: counts, and this scrubs what somebody sends about themselves, which is a promise about
#: credentials alone. Two promises, deliberately not one regular expression.
_SCRUBS: tuple[tuple[re.Pattern[str], str], ...] = (
    # A user and a password signed into a URL, which is how a private flowverse is added and
    # how several of these gateways are configured. `/flowverses` takes exactly this out of
    # the URL it shows, for the reason it gives: a token on a screen is a token in a
    # photograph, and a token in an archive is one in whatever issue the archive is attached
    # to. Only the run immediately after `//`, so a comment holding an address is left alone.
    (re.compile(r"(?<=//)[^/\s@\"'<>]+(?=@)"), REDACTED),
    # A token signed into a query string, which is how every pre-signed URL there is carries
    # one -- an upload to a bucket, a webhook, a download link an agent was handed. The name
    # must end where the word does and whatever comes before it must end at a separator:
    # `?max_tokens=` is what a turn cost and `?monkey=` is somebody's parameter, and a bundle
    # that struck either out would be one nobody can read.
    (
        re.compile(
            r"(?i)([?&](?:[a-z0-9.-]+[_-])?"
            r"(?:access_token|token|api[_-]?key|key|secret|sig|signature|password"
            r"|credential)=)[^&\s\"'<>]+"
        ),
        rf"\1{REDACTED}",
    ),
    # The shapes the vendors mint keys in. A prefix and a separator, which is what makes
    # these safe to strike on sight: no English word begins `sk-` or `ghp_`.
    (
        re.compile(
            r"\b(?:sk|pk|ghp|gho|ghu|ghs|ghr|github_pat|glpat|xai|xoxb|xoxp|hf)"
            r"[-_][A-Za-z0-9_-]{12,}\b"
        ),
        REDACTED,
    ),
    # Google's, which has no separator, and a JWT, which is three pieces of base64 with a dot
    # between each -- what half of these CLIs actually hold a session open with.
    (re.compile(r"\bAIza[A-Za-z0-9_-]{16,}\b"), REDACTED),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
        REDACTED,
    ),
    # What an Authorization header is, wherever a log happened to write one down.
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{16,}"), rf"\1{REDACTED}"),
    # And a value a log named itself: `"api_key": "..."` in JSON, `SOMETHING_TOKEN=...` in an
    # environment. The name must end there -- `token`, not `tokens` -- because `input_tokens`
    # is how every one of these backends writes down what a turn cost, and a bundle that
    # struck the numbers out of those would be one nobody can read a bill out of.
    (
        re.compile(
            r"(?i)(\"[A-Za-z0-9_.-]*(?:token|secret|api[_-]?key|password|credential)\""
            r"\s*:\s*\")[^\"]{4,}"
        ),
        rf"\1{REDACTED}",
    ),
    (
        re.compile(
            r"(?i)\b([A-Za-z0-9_]*(?:token|secret|api[_-]?key|password|credential)=)"
            r"[^\s\"',}]{4,}"
        ),
        rf"\1{REDACTED}",
    ),
)


def bundle(
    epic: Path,
    at: str | os.PathLike[str],
    *,
    transcript: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Writes one whole run as one archive, credentials struck out of every byte of it.

    Everything the run wrote goes in -- its own record, a record per flow it called, the
    state a resumable flow left, the profile of the programs it ran, every trace gathered of
    it -- and beside those the session logs themselves, each filed under the session it is a
    log of.

    Args:
      epic: The run, by the directory it is written in.
      at: Where to write it: a file outright, or a directory to write it into under its own
        name. Always named: a bundle is made to be sent, and one that landed somewhere of its
        own choosing is one somebody has to go looking for -- or, landed in the project they
        are standing in, one the next commit of everything carries along.
      transcript: A screen that went with this run, as it was written rather than as it was
        drawn, or None -- which is what everything humanize itself asks for a bundle with
        hands in, the run being one read back rather than one being watched.

    Returns:
      Where it was written, and the manifest as it was written there -- so that whatever
      asked for the bundle says what is in it out of the archive's own account of itself
      rather than by reading the run a second time and describing something else.

    Raises:
      ValueError: For a directory holding no run, which is nothing to export, and for a
        `~somebody` nobody is, which is nowhere to write it.
    """
    ran = read(epic)
    if ran is None:
        raise ValueError(f"{epic} is not a run")
    landed = _lands(epic, at)
    landed.parent.mkdir(parents=True, exist_ok=True)
    # Written whole under a name of its own and moved into place: an archive read while it
    # is being written is one nothing can open, and two exports of one run at once would
    # otherwise be two gzip streams into one file. The mode this makes it with is the one it
    # keeps -- readable by whoever exported it and nobody else, since what is in it is their
    # prompts and their agents' output, and a shared machine is a shared machine.
    handle, temporary = tempfile.mkstemp(
        dir=landed.parent, prefix=f".{landed.name}.", suffix=".new"
    )
    os.close(handle)
    beside = Path(temporary)
    try:
        with tarfile.open(beside, "w:gz") as writing:
            said = _writes(
                epic,
                ran,
                transcript,
                lambda name, source, struck: _copies(
                    writing, f"{epic.name}/{name}", source, struck
                ),
                lambda name, data: _puts(writing, f"{epic.name}/{name}", data),
            )
        beside.replace(landed)
    finally:
        beside.unlink(missing_ok=True)
    return landed, cast("dict[str, Any]", json.loads(said))


def unpacked(epic: Path, into: Path) -> dict[str, Any]:
    """Writes what a bundle of one run holds as files under a directory, not as an archive.

    The same files, struck of credentials the same way, laid out as a bundle lays them out
    under the run's own name -- which is what a backup commits, so that a repository of runs
    reads file by file rather than as a pile of archives nothing can diff.

    Args:
      epic: The run, by the directory it is written in.
      into: The directory to write it into, made where it is not there.

    Returns:
      The manifest, as it was written there.

    Raises:
      ValueError: For a directory holding no run.
      OSError: Where what is under `into` cannot be written.
    """
    ran = read(epic)
    if ran is None:
        raise ValueError(f"{epic} is not a run")

    def copies(name: str, source: Path, struck: Sequence[str]) -> bool:
        to = into / name
        to.parent.mkdir(parents=True, exist_ok=True)
        # A line at a time, for the reason an archive is: a nine-hour run's log is big. One
        # that goes while it is read is left out, as an archive leaves it.
        try:
            with (
                source.open("r", encoding="utf-8", errors="replace") as reading,
                to.open("w", encoding="utf-8") as writing,
            ):
                for line in reading:
                    writing.write(plain(line, struck))
        except OSError:
            to.unlink(missing_ok=True)
            return False
        return True

    def puts(name: str, data: bytes) -> None:
        (into / name).parent.mkdir(parents=True, exist_ok=True)
        (into / name).write_bytes(data)

    return cast("dict[str, Any]", json.loads(_writes(epic, ran, None, copies, puts)))


def _writes(
    epic: Path,
    ran: Ran,
    transcript: str | None,
    copies: Callable[[str, Path, Sequence[str]], bool],
    puts: Callable[[str, bytes], None],
) -> str:
    """Hands over everything a bundle of one run holds, file by file, and its manifest.

    Args:
      epic: The run, by the directory it is written in.
      ran: What it was, already read.
      transcript: A screen that went with it, or None.
      copies: What puts a file of the run's in, by the name it goes under, scrubbed of the
        values given as well as the patterns; it says whether it went in.
      puts: What puts something this made itself in, by name.

    Returns:
      The manifest, as it was written.
    """
    struck = _struck(ran)
    # What each session was logged to, found once. The manifest says what the bundle
    # holds, and a second look would let it name a file the bundle has not got: a log
    # rolls over while this runs, and an absence that means that reads exactly like an
    # absence that means the bundle lost it.
    behind = logged(epic)
    found = {one.name: dict(behind.get(one.name, {})) for one in ran.sessions}
    held: list[str] = []
    for name, source in _files(epic):
        if copies(name, source, struck):
            held.append(name)
    for one in ran.sessions:
        kept: dict[str, Path] = {}
        for name, source in found[one.name].items():
            under = f"{SESSIONS}/{one.name}/{name}"
            if copies(under, source, struck):
                kept[name] = source
                held.append(under)
        found[one.name] = kept
    if transcript is not None:
        puts(TRANSCRIPT, plain(transcript, struck).encode("utf-8"))
        held.append(TRANSCRIPT)
    # Through the same scrubbing as everything else. It holds what the run was asked to do,
    # which is a line somebody typed and may hold whatever they had in hand -- and it is the
    # file whoever opens the bundle reads first.
    said = plain(
        json.dumps(
            _manifest(epic, ran, _sessions(ran, found), held),
            ensure_ascii=False,
            indent=2,
        ),
        struck,
    )
    puts(MANIFEST, said.encode("utf-8"))
    return said


def unbundle(archive: str | os.PathLike[str]) -> Path:
    """Reads one bundle back in as an epic of this machine's.

    Placed under the workspace the run says it ran in, as a run there would be, and laid out
    as one: each session's logs where that session says it is kept -- or, for one that stayed
    in its CLI's own home, in the epic as a session kept there, the line saying so rewritten,
    since another machine's home is nowhere here. A line saying which file it came from goes
    last, which is what says it was imported.

    Args:
      archive: The bundle, which is a `.hmzepic`.

    Returns:
      Where the epic now is.

    Raises:
      ValueError: For a file that is not a bundle -- not named as one, not a gzipped tar,
        not one epic holding its record and manifest, or holding anything but plain files
        under it -- for a run that says no workspace, and for an epic already here.
    """
    source = Path(archive).expanduser()
    if not source.name.endswith(BUNDLE.removeprefix("{epic}")):
        raise ValueError(f"{source.name} is not a {BUNDLE.removeprefix('{epic}')} file")
    try:
        with tarfile.open(source, "r:gz") as reading:
            members = reading.getmembers()
            name = _one(
                source.name,
                [
                    (one.name, "file" if one.isfile() else "dir" if one.isdir() else "")
                    for one in members
                ],
            )

            def said(under: str) -> bytes | None:
                held = reading.extractfile(f"{name}/{under}")
                return held.read() if held is not None else None

            return _places(
                name,
                said(MANIFEST),
                said(JOURNAL),
                source.name,
                lambda beside: reading.extractall(
                    beside, members=members, filter="data"
                ),
            )
    except (tarfile.TarError, gzip.BadGzipFile, EOFError, zlib.error) as why:
        raise ValueError(
            f"{source.name} is not a bundle humanize can read: {why}"
        ) from why
    except OSError as why:
        raise ValueError(f"{source.name} could not be imported: {why}") from why


def placed(epic: Path, origin: str) -> Path:
    """Reads one epic laid out as files, as :func:`unpacked` lays it out, back in as this machine's.

    Exactly as :func:`unbundle` reads a bundle back in, the directory standing for the archive:
    which is what a backup commits, so that an epic backed up on one machine is downloaded on
    another as it would be imported.

    Args:
      epic: The epic's directory, named as the epic is, holding its record and manifest.
      origin: Where it came from, as the line saying it was imported says it -- with nothing
        signed into it.

    Returns:
      Where the epic now is.

    Raises:
      ValueError: For a directory not laid out as one epic -- no record, no manifest, or
        anything under it but plain files and directories -- for a run that says no workspace,
        and for an epic already here.
    """
    try:
        # Nothing but plain files and directories, as a bundle holds: a link out of a
        # repository is a file of this machine's read as the epic's.
        name = _one(
            origin,
            [
                (
                    "/".join((epic.name, *one.relative_to(epic).parts)),
                    ""
                    if one.is_symlink()
                    else "dir"
                    if one.is_dir()
                    else "file"
                    if one.is_file()
                    else "",
                )
                for one in [epic, *epic.rglob("*")]
            ],
        )
        return _places(
            name,
            (epic / MANIFEST).read_bytes(),
            (epic / JOURNAL).read_bytes(),
            origin,
            lambda beside: shutil.copytree(epic, beside / name),
        )
    except OSError as why:
        raise ValueError(f"{epic.name} could not be imported: {why}") from why


def _places(
    name: str,
    manifest: bytes | None,
    journal: bytes | None,
    origin: str,
    fills: Callable[[Path], object],
) -> Path:
    """Puts one epic, already checked, where it goes here, and says where it came from.

    Args:
      name: The epic's name.
      manifest: Its manifest, as written.
      journal: Its record, as written.
      origin: Where it came from, for the line saying it was imported.
      fills: What writes the epic, as `<name>/`, into the directory it is handed.

    Returns:
      Where the epic now is.

    Raises:
      ValueError: For a run that says no workspace, and for an epic already here.
      OSError: Where it cannot be written.
    """
    head = _head_of(manifest)
    kept = under(_workspace_of(name, journal))
    if (kept / name).exists():
        raise ValueError(f"{name} is already here, at {kept / name}")
    kept.mkdir(parents=True, exist_ok=True)
    # Written whole beside where it goes and moved into place, one level down so
    # that nothing listing the runs there reads it half-written as one.
    beside = Path(tempfile.mkdtemp(dir=kept, prefix=f".{name}."))
    try:
        fills(beside)
        epic = beside / name
        _settle(epic, beside)
        note(epic, "imported", **{"from": origin, "head": head})
        try:
            epic.rename(kept / name)
        except OSError as why:
            raise ValueError(f"{name} is already here, at {kept / name}") from why
    finally:
        shutil.rmtree(beside, ignore_errors=True)
        # The workspace's own directory, where this import was the first run in it
        # and it failed.
        with contextlib.suppress(OSError):
            kept.rmdir()
    return kept / name


def _one(source: str, members: Sequence[tuple[str, str]]) -> str:
    """The one epic a bundle holds, by name, having checked that it holds nothing else.

    Args:
      source: The bundle, by name, for what is said of it.
      members: Everything in it, by name, each a `file`, a `dir` or "" for anything else.

    Returns:
      The epic's name, which is what it is filed under here.

    Raises:
      ValueError: For anything but plain files and directories under one plain name holding
        the epic's record and its manifest.
    """
    names = {one.split("/", 1)[0] for one, _ in members}
    if len(names) != 1:
        raise ValueError(f"{source} does not hold exactly one epic")
    name = names.pop()
    if name in {"", ".", ".."} or name.startswith(".") or "\\" in name:
        raise ValueError(f"{source} holds an epic named {name!r}")
    for one, kind in members:
        if not kind or ".." in one.split("/"):
            raise ValueError(f"{source} holds {one}, which is not a file in it")
    files = {one for one, kind in members if kind == "file"}
    for needed in (JOURNAL, MANIFEST):
        if f"{name}/{needed}" not in files:
            raise ValueError(f"{source} has no {needed}")
    return name


def _head_of(manifest: bytes | None) -> str:
    """The commit a manifest says its workspace was on, or "" where it says none."""
    try:
        said: object = json.loads(manifest) if manifest is not None else None
    except ValueError:
        return ""
    if isinstance(said, dict):
        workspace = cast("dict[str, Any]", said).get("workspace")
        if isinstance(workspace, dict):
            return str(cast("dict[str, Any]", workspace).get("head") or "")
    return ""


def _workspace_of(name: str, journal: bytes | None) -> str:
    """Where the run says it ran, off the line its record began with.

    Raises:
      ValueError: For a run that says nowhere, which is nowhere to put it.
    """
    for line in journal.splitlines() if journal is not None else ():
        try:
            said = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(said, dict)
            and cast("dict[str, Any]", said).get("event") == "began"
        ):
            ran_in = str(cast("dict[str, Any]", said).get("workspace") or "")
            if ran_in and Path(ran_in).is_absolute():
                return ran_in
            break
    raise ValueError(f"{name} says no workspace it ran in")


def _settle(epic: Path, beside: Path) -> None:
    """Moves each session's logs out of where the bundle filed them to where it is kept.

    A bundle files them under `sessions/<session>/`; the session says where it is kept, from
    the epic. One that said another machine's whole path is kept in the epic instead, where
    its CLI's sessions are kept, and its lines are rewritten to say so.

    Args:
      epic: The epic, read out of the bundle.
      beside: Somewhere to put what the bundle filed while it is being moved.
    """
    filed = beside / f".{SESSIONS}"
    if (epic / SESSIONS).is_dir():
        (epic / SESSIONS).rename(filed)
    _rehomed(epic)
    for one in sessions(epic):
        source = filed / one.name
        target = (epic / (one.where or f"{SESSIONS}/{one.name}")).resolve()
        if not source.is_dir() or not target.is_relative_to(epic.resolve()):
            continue
        for found in sorted(source.rglob("*")):
            if found.is_file():
                at = target / found.relative_to(source)
                at.parent.mkdir(parents=True, exist_ok=True)
                found.replace(at)


def _rehomed(epic: Path) -> None:
    """Rewrites each line saying a session stayed in another machine's home to say the epic.

    Args:
      epic: The epic, read out of the bundle.
    """
    for record in records(epic):
        lines = record.read_text(encoding="utf-8", errors="replace").splitlines()
        record.write_text(
            "".join(f"{_rehome(one)}\n" for one in lines), encoding="utf-8"
        )


def _rehome(line: str) -> str:
    """One line of a record, rewritten where it says a session stayed in a CLI's own home."""
    try:
        said = json.loads(line)
    except ValueError:
        return line
    if not isinstance(said, dict):
        return line
    held = cast("dict[str, Any]", said)
    if (
        held.get("event") != "opened"
        or not Path(str(held.get("where") or "")).is_absolute()
    ):
        return line
    return json.dumps(held | {"where": f"{SESSIONS}/{held.get('backend') or ''}"})


def logged(epic: Path) -> dict[str, dict[str, Path]]:
    """Every file one run's sessions were logged to.

    Which the epic holds itself, under `sessions/<cli>/` laid out as that CLI's home is --
    or, for a session that could not be kept there, wherever its CLI keeps it. A file that
    has gone -- rolled over, cleaned up -- is left out rather than carried as a name with
    nothing behind it.

    Args:
      epic: The run, by the directory it is written in.

    Returns:
      One entry per session that was logged to anything, by the name the run gave it, and
      inside it each file by where it is under the directory that session is kept in -- which
      is the name the archive files it as, under the session's own. A session whose backend
      logs nothing at all has no entry, which is what the manifest says in words instead.
    """
    held: dict[str, dict[str, Path]] = {}
    for one in sessions(epic):
        found = logs(epic, one)
        if found:
            held[one.name] = found
    return held


def plain(said: str, struck: Sequence[str] = ()) -> str:
    """One piece of text with every credential in it taken out.

    Args:
      said: The text, as it was written.
      struck: Values to take out literally as well, which is what an account's own variables
        are: a gateway's key is whatever somebody pasted, and no pattern would know it.

    Returns:
      The same text with each of those replaced by :data:`REDACTED`.
    """
    for one in struck:
        said = said.replace(one, REDACTED)
    for pattern, instead in _SCRUBS:
        said = pattern.sub(instead, said)
    return said


def sized(count: int) -> str:
    """How big something is, in the words a line about a file says it.

    Args:
      count: How many bytes.

    Returns:
      Three digits and a unit -- `912 kB`, `1.4 MB` -- since what somebody reads off a line
      saying where a bundle landed is whether it is small enough to attach to something.
    """
    held = float(count)
    for unit in _UNITS:
        if held < _THOUSAND or unit == _UNITS[-1]:
            if unit == _UNITS[0] or held >= _ROUGHLY:
                return f"{held:.0f} {unit}"
            return f"{held:.1f} {unit}"
        held /= _THOUSAND
    raise AssertionError  # pragma: no cover -- the loop returns at the last unit


def _now() -> str:
    """This moment, as every file humanize writes spells one."""
    return (
        datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    )


def _lands(epic: Path, at: str | os.PathLike[str]) -> Path:
    """Where one bundle is written, out of what was asked for.

    Args:
      epic: The run, by the directory it is written in.
      at: A file, or a directory to put it in under its own name, from the home a leading
        `~` names where it starts with one.

    Returns:
      The file to write, whole rather than relative: what is printed and what is shown is a
      path somebody is about to attach something to, and a relative one is a path they then
      have to remember which directory they were standing in for.
    """
    named = BUNDLE.format(epic=epic.name)
    said = os.fspath(at)
    try:
        asked = Path(said).expanduser().absolute()
    except RuntimeError as why:
        raise ValueError(f"{said} is in no home directory there is") from why
    # A trailing separator as well as a directory that is already there: `-o out/` where
    # `out/` has not been made yet is a directory somebody means to fill, and answering it
    # with an extensionless file called `out` would have the next run write over the last.
    if asked.is_dir() or said.endswith(("/", os.sep)):
        return asked / named
    return asked


def _files(epic: Path) -> Iterator[tuple[str, Path]]:
    """Everything one run wrote down about itself, by the name it goes in the archive under.

    The run's own record first, then a record per flow it called, then the journal a
    resumable flow kept, the profile of the programs it ran, and every trace gathered of it.
    Each is absent from a run that never wrote one -- a flow that is not resumable, a run
    nobody profiled -- and an absent one is left out rather than carried as an empty file.

    Args:
      epic: The run, by the directory it is written in.

    Yields:
      What to call it inside the archive, and where to read it from.
    """
    from hmz.runtime.tracing.profile import PROFILE

    for one in records(epic):
        yield one.name, one
    for name in (RESUME, PROFILE):
        if (epic / name).is_file():
            yield name, epic / name
    with contextlib.suppress(OSError):
        for one in sorted((epic / TRACES).iterdir()):
            if one.is_file():
                yield f"{TRACES}/{one.name}", one


def _copies(
    writing: tarfile.TarFile, name: str, source: Path, struck: Sequence[str]
) -> bool:
    """Puts one file in the archive with every credential in it taken out.

    A line at a time, spilling to disk past a megabyte: a session log of a nine-hour run is a
    file, and reading one whole into memory to scrub it would want the memory of the run that
    wrote it.

    Args:
      writing: The archive.
      name: What to call it inside it.
      source: The file to read.
      struck: The values to strike out as well as the patterns.

    Returns:
      Whether it went in. A file that went while it was being read is a bundle without it,
      and what the manifest says the bundle holds is what actually went in it.
    """
    with tempfile.SpooledTemporaryFile(max_size=_SPOOL) as holder:
        size = 0
        try:
            with source.open("r", encoding="utf-8", errors="replace") as reading:
                for line in reading:
                    said = plain(line, struck).encode("utf-8")
                    holder.write(said)
                    size += len(said)
        except OSError:
            return False
        holder.seek(0)
        writing.addfile(_about(name, size), holder)
    return True


def _puts(writing: tarfile.TarFile, name: str, said: bytes) -> None:
    """Puts something this made itself in the archive.

    Args:
      writing: The archive.
      name: What to call it inside it.
      said: The whole of it.
    """
    writing.addfile(_about(name, len(said)), io.BytesIO(said))


def _about(name: str, size: int) -> tarfile.TarInfo:
    """What the archive says one member is: its name, its size, and nothing about this machine.

    No owner, no group and the plainest mode there is. A tar carries whoever wrote it by
    default, and the login name of the person who exported a run is not a thing a bundle
    needs to hand anybody.

    Args:
      name: What it is called inside the archive.
      size: How many bytes of it there are.

    Returns:
      The header.
    """
    held = tarfile.TarInfo(name)
    held.size = size
    held.mtime = int(datetime.datetime.now(datetime.UTC).timestamp())
    held.mode = 0o644
    held.uid = held.gid = 0
    held.uname = held.gname = ""
    return held


def _struck(ran: Ran) -> tuple[str, ...]:
    """Every credential humanize keeps here, as the values to take out of anything copied.

    By value rather than by name. An account is `ANTHROPIC_AUTH_TOKEN` and a base URL and
    whatever else that way asked for, and which of those is secret is a judgement no rule
    makes reliably -- the address of somebody's private gateway is as much theirs as the key
    that opens it. So every value long enough to be one goes, and a variable set to a word is
    left alone rather than turning every `true` in a session log into a redaction.

    Less what the run itself is read by. An account may say which model to ask for -- Kimi
    Code's does, and half the gateway configurations do -- and a bundle that struck the model
    name out of the run because some other account had it in a variable would be a bundle
    saying nothing about what actually ran.

    Args:
      ran: What the run was, so that what it says it ran can be kept.

    Returns:
      Them, longest first so that a value holding another is struck as the longer of the two.
    """
    from hmz.coganchor.providers import providers

    held: set[str] = set()
    with contextlib.suppress(OSError):
        for one in providers():
            held.update(
                value.strip()
                for value in one.env.values()
                if len(value.strip()) >= _ENOUGH
            )
    return tuple(sorted(held - _read_by(ran), key=len, reverse=True))


def _read_by(ran: Ran) -> set[str]:
    """What one run says it ran, which is what a bundle is read by rather than a credential.

    Args:
      ran: What the run was.

    Returns:
      The flow, and every agent's CLI, model, effort, account and name -- each also split on
      the slash a model may hold, since `fixture/fixture-model` is written one way in the run
      and the other in the variable that names it.
    """
    held: set[str] = {ran.flow, *ran.flow.split("/")}
    for one in ran.agents:
        held.update(
            {one.backend, one.effort, one.provider, one.model, *one.model.split("/")}
        )
    for one in ran.sessions:
        held.update({one.agent, one.backend, one.provider})
    return {said for said in held if said}


def _sessions(
    ran: Ran, found: Mapping[str, Mapping[str, Path]]
) -> list[dict[str, Any]]:
    """What each session of one run was, and what of it the bundle actually holds.

    Every session gets an entry, the ones with nothing behind them among them: a CLI that
    keeps its sessions in a database of its own logs nothing humanize can read, and a bundle
    that answered that with an absence would read exactly like a bundle that lost the logs.

    Args:
      ran: What that run was, already read.
      found: What actually went in the archive, by session name -- rather than what is
        there now, which is a second reading and may be a different answer.

    Returns:
      One entry apiece, oldest session first.
    """
    held: list[dict[str, Any]] = []
    for one in ran.sessions:
        said: dict[str, Any] = {
            "name": one.name,
            "agent": one.agent,
            "backend": one.backend,
            # The account by the name it is called here, and never what it runs a turn with:
            # that is the credential, and it is what this whole module is careful of.
            "provider": one.provider,
            "session": one.ident,
            "flow": one.flow,
            # Which record it was opened in, so that two concurrent calls of one flow read
            # as the two conversations they were. The run wrote it down; nothing here works
            # it out again.
            "record": one.record or JOURNAL,
            "at": one.at,
            "logs": sorted(found.get(one.name) or ()),
        }
        if not said["logs"]:
            said["because"] = _nothing(one)
        held.append(said)
    return held


def _called(calls: Sequence[Called], under: str = JOURNAL) -> list[dict[str, Any]]:
    """Every flow this run called, at whatever depth, and which record called each.

    The tree flattened, rather than the tree: a manifest is read by whoever opens the bundle
    and by whatever they open it with, and one flat list with a parent named on each entry is
    the shape both of those already know. What makes it a tree is `under` -- a flow called
    twice is two records, so it names the call rather than the flow, which is what tells two
    concurrent calls of one flow apart.

    Args:
      calls: What one record called, as :func:`hmz.runtime.epic.tree` read them.
      under: The record that called them.

    Returns:
      One entry per called flow, deepest last within each branch.
    """
    held: list[dict[str, Any]] = []
    for one in calls:
        held.append(
            {
                "flow": one.flow,
                "task": one.task,
                "record": one.record,
                "under": under,
                "began": one.began,
                "ended": one.ended,
                "how": one.how or "left unfinished",
            }
        )
        held.extend(_called(one.calls, one.record))
    return held


def _nothing(one: Session) -> str:
    """Why a bundle holds no log for one session, said rather than left as an absence.

    Args:
      one: The session.

    Returns:
      Which of the two it is: a CLI that writes no log anybody can read, or a log that was
      not there when the bundle was made.
    """
    profile = backends.named(one.backend)
    if profile is None:
        return (
            f"humanize knows no backend called {one.backend!r}, so knows no logs of one"
        )
    if not profile.logs:
        return (
            f"{profile.name} keeps its sessions to itself -- there is no file humanize can "
            "read one out of, so there is none to carry"
        )
    return "nothing was logged here, or what was has since gone"


def _manifest(
    epic: Path, ran: Ran, said: Sequence[dict[str, Any]], held: Sequence[str]
) -> dict[str, Any]:
    """What this bundle is, for whoever opens it on another machine.

    Which run, of which flow, driven by which agents at which models and efforts -- and under
    those, what each backend actually was: the version it says it is and the hash of the
    executable that took the turns. A bug in a CLI is a bug in a build of it, and a report
    that says which build is a report somebody can act on.

    Args:
      epic: The run, by the directory it is written in.
      ran: What that run was, already read.
      said: What each of its sessions was, and what of it the bundle holds.
      held: Everything in the archive besides the manifest, by the name it is under.

    Returns:
      The manifest, as it is written.
    """
    from importlib.metadata import PackageNotFoundError, version

    try:
        mine = version("hmz")
    except PackageNotFoundError:  # pragma: no cover -- an install that is not one
        mine = ""
    head = _pinned(epic)
    if head is None:
        head = _head(Path(ran.workspace) if ran.workspace else epic)
    named = sorted(
        {one.backend for one in ran.agents} | {one.backend for one in ran.sessions}
    )
    return {
        "humanize": mine,
        "made": _now(),
        "python": platform.python_version(),
        "machine": platform.platform(),
        "epic": epic.name,
        "run": {
            "flow": ran.flow,
            "task": ran.task,
            "began": ran.began,
            "ended": ran.ended,
            "how": ran.how or "left unfinished",
            "resumable": ran.resumable,
        },
        "workspace": {"at": ran.workspace, "head": head},
        "agents": [
            {
                "agent": one.agent,
                # What the agent filling that role was called, which its sessions are under:
                # the role itself, for a run written before an agent had a name of its own.
                "name": one.name or one.agent,
                "backend": one.backend,
                "model": one.model,
                "effort": one.effort,
                # By name, and by name only: what an account runs a turn with is the one
                # thing a bundle must never carry.
                "provider": one.provider,
                "runs": one.spec,
            }
            for one in ran.agents
        ],
        "envs": list(ran.envs),
        "used": list(ran.used),
        "called": _called(tree(epic)),
        "sessions": list(said),
        "backends": {name: _cli(name) for name in named},
        "held": [*held, MANIFEST],
        "redacted": list(STRUCK),
    }


def _pinned(epic: Path) -> str | None:
    """The commit an imported run was said to be on, off its last import; None for one not.

    Its workspace here is another checkout, if it is here at all, so what that is on now is
    not what the run was on.
    """
    with contextlib.suppress(OSError):
        lines = (epic / JOURNAL).read_text(encoding="utf-8", errors="replace")
        for line in reversed(lines.splitlines()):
            try:
                said = json.loads(line)
            except ValueError:
                continue
            if (
                isinstance(said, dict)
                and cast("dict[str, Any]", said).get("event") == "imported"
            ):
                return str(cast("dict[str, Any]", said).get("head") or "")
    return None


def _head(workspace: Path) -> str:
    """What the workspace is at, for one that is a git repository.

    Args:
      workspace: Where the run ran.

    Returns:
      The commit that directory is on, and "" for one that is not a repository, has no commit
      yet, or has no git to ask. What it is on now rather than what it was on when the run
      happened -- nothing wrote that down -- so it is what a reader checks a report against.
    """
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        done = subprocess.run(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=_PATIENCE,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        if done.returncode == 0:
            return done.stdout.strip()
    return ""


def _cli(name: str) -> dict[str, Any]:
    """What one backend actually is on this machine, as a bundle has to say it.

    The version it answers with and the hash of the executable that answered, which is the
    pair `bench/cli-concurrency/run.py --list` keeps beside a measurement and for the same
    reason: these CLIs move weekly, two installs of one version are not always one program,
    and a run that cannot be pinned to a build is a run nobody can repeat.

    Args:
      name: The backend, by the name humanize knows it under.

    Returns:
      What it is, with whatever could not be found left empty.
    """
    profile = backends.named(name)
    if profile is None:
        return {"command": name, "executable": "", "version": "", "sha256": ""}
    command = profile.name
    # Where a backend may be installed is backends' to know: shutil.which alone
    # calls a CLI under ~/.local/bin not installed, and the manifest would say so.
    found = backends.program(command)
    held: dict[str, Any] = {
        "command": command,
        "executable": found or "",
        "version": "",
        "sha256": "",
        # Whether this CLI writes a session log at all, said here as well as against each
        # session: a reader wondering why a bundle is thin should not have to work it out
        # from which entries have no files under them.
        "logs": bool(profile.logs),
    }
    if not found:
        return held
    at = Path(found).resolve()
    held["executable"] = str(at)
    with contextlib.suppress(OSError), at.open("rb") as handle:
        held["sha256"] = hashlib.file_digest(handle, "sha256").hexdigest()
    held["version"] = _version(command)
    return held


def _version(command: str) -> str:
    """What one backend says it is, asked of the program itself.

    Args:
      command: What it is installed as.

    Returns:
      Its first line's worth, and "" for a CLI that will not say, has no such flag, or takes
      too long about it. Nothing depends on the answer, so none of those is a failure.
    """
    with contextlib.suppress(OSError, subprocess.SubprocessError):
        done = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            timeout=_PATIENCE,
            check=False,
            stdin=subprocess.DEVNULL,
        )
        for line in (done.stdout or done.stderr).splitlines():
            if line.strip():
                # Not scrubbed here: this lands in the manifest and the manifest goes
                # through the scrubbing whole, which is one place rather than two.
                return line.strip()[:_ENOUGH_VERSION]
    return ""
