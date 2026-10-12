"""Keeping a copy here of what a CLI on another machine logs its sessions to.

A turn whose CLI runs on this machine keeps its sessions in the run's own directory, answered
there by the supervisor. A turn whose CLI runs on another machine cannot: the target's own CLI
(`native`), and a CLI under a harness put on a machine of its own, both write their sessions
under their home on *that* machine, which nothing of this one's reaches. So the files each such
session is logged to are copied here as they grow, laid out as the run's directory lays out a
kept one, and the run reads its sessions where it always does.

Down the road a command already takes to that machine -- `ssh`, `docker exec`, `srun` -- one
short command at a time: one lists what the session has logged and how long each file is, and
one reads what has been appended since the last copy. Nothing is held open between the two and
nothing new is put on the machine.
"""

from __future__ import annotations

import contextlib
import logging
import os
import re
import subprocess
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from hmz.coganchor.anchor import AnchorConfig
    from hmz.coganchor.backends import Profile
    from hmz.coganchor.transport import Road

__all__ = ["EVERY", "Tail", "road", "roots"]

log = logging.getLogger(__name__)

#: How often a session's logs are copied while it is open, in seconds: often enough to read a
#: run as it goes, seldom enough that the commands doing it are nothing beside the turn.
EVERY = 2.0

#: How long one of those commands may take before the copy is left for the next one.
_ASKING = 30.0

#: The most of one log one read takes, so that a long one is read in pieces each in time.
_MOST = 8 << 20

#: How many reads the last copy of a session may take before leaving the rest.
_ROUNDS = 64

#: What a log of lines is named, which is copied as it grows; any other is written in place.
_LINES = ".jsonl"

#: Into the CLI's home on that machine, as the turn found it: the value the turn was given
#: (`$4`), else the one that machine's variable (`$1`) holds -- under `$3` -- else the default
#: under that machine's own home (`$2`). A home that is not there is a session with no logs.
_HOME = r"""
v=$1 d=$2 i=$3 h=$4; shift 4
if [ -z "$h" ] && [ -n "$v" ]; then eval "h=\${$v:-}"; fi
if [ -n "$h" ]; then h="$h/$i"; else h="$HOME/$d"; fi
cd "$h" 2>/dev/null || exit 0
"""

#: Every file the arguments find, a line apiece: its length, a space, its path.
_LIST = (
    _HOME
    + r"""
find "$@" 2>/dev/null | while IFS= read -r f; do
  printf '%s %s\n' "$(wc -c < "$f" | tr -d ' ')" "$f"
done
exit 0
"""
)

#: Each file named, from the first offset to the second, one after the other.
_READ = (
    _HOME
    + r"""
while [ $# -ge 3 ]; do
  tail -c +$(($2 + 1)) "$1" | head -c $(($3 - $2))
  shift 3
done
"""
)

#: What a variable's name may be, since the script reads one by name.
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: What makes a part of a glob a pattern rather than a name.
_WILD = re.compile(r"[*?\[]")


def road(anchor: AnchorConfig) -> Road | None:
    """The road to the machine a turn under this anchor keeps its sessions on.

    Args:
      anchor: Where the turns land.

    Returns:
      The road to the target, for a CLI that is the target's own -- which is this machine's
      own road for a `local` target standing in for one; to the harness's machine, for a
      harness put on another one; and None for a CLI supervised here, or on a machine no
      command is started on -- a `tcp://` or `peer://` target, whose serving half somebody
      else started.
    """
    from hmz.coganchor.elsewhere import elsewhere, harnessed
    from hmz.coganchor.transport import Road, Target

    try:
        if anchor.native:
            return Road.to(Target.parse(anchor.target))
        if elsewhere(anchor):
            return Road.to(harnessed(anchor.harness, anchor.target))
    except ValueError:
        return None
    return None


class Tail:
    """A copy here of the sessions one agent's CLI logs on another machine, kept up to date.

    One thread for every session it follows, which copies what each has logged since the
    last time every :data:`EVERY` seconds, and ends once it follows none. A log of lines is
    copied a whole line at a time as it grows; any other log -- a database, written in place
    -- is copied whole once, as its session closes. A copy that fails is said once and tried
    again next time: it is never the turn's business.
    """

    def __init__(
        self,
        way: Road,
        profile: Profile,
        into: Path,
        home: str = "",
        told: Path | None = None,
    ) -> None:
        """Copies nothing yet.

        Args:
          way: The road to the machine the CLI runs on.
          profile: The CLI, for where it keeps its home and what it logs a session to.
          into: Where the copies go, laid out as that home is.
          home: The CLI's home as the turn was told it, or "" for wherever that machine says.
          told: A directory on this machine in place of `home`, in which each turn moving the
            CLI's home keeps a file of `VARIABLE=where it went` lines while it runs -- every
            home they name being followed, and none while there are none.
        """
        self._way, self._profile, self._into, self._told = way, profile, into, told
        variable = profile.home_var if _NAME.fullmatch(profile.home_var) else ""
        self._home = (variable, profile.home_dir, profile.home_in, home)
        self._following: set[str] = set()
        self._held = threading.Lock()
        self._copying = threading.Lock()
        self._thread: threading.Thread | None = None
        self._said = False

    def follow(self, ident: str) -> None:
        """Keeps one session's copy up to date from now until :meth:`forget`.

        Args:
          ident: The session, by the id the CLI gave it.
        """
        with self._held:
            self._following.add(ident)
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._run, name=f"hmz-tail-{self._profile.name}", daemon=True
                )
                self._thread.start()

    def forget(self, ident: str, *, wait: bool = True) -> None:
        """Stops following one session, copying the whole of what it logged. Never raises.

        Args:
          ident: The session, by the id the CLI gave it. One not followed is left alone.
          wait: Whether to wait for that last copy, rather than leave it to a thread.
        """
        with self._held:
            if ident not in self._following:
                return
            self._following.discard(ident)
        if wait:
            self.copy((ident,), whole=True)
            return
        # Not at all where the interpreter is already going away.
        with contextlib.suppress(RuntimeError):
            threading.Thread(
                target=self.copy,
                args=((ident,),),
                kwargs={"whole": True},
                name=f"hmz-tail-{self._profile.name}-last",
                daemon=True,
            ).start()

    def copy(self, idents: Iterable[str], *, whole: bool = False) -> None:
        """Copies what these sessions have logged since the last copy. Never raises.

        Args:
          idents: The sessions, by the ids the CLI gave them.
          whole: Whether this is the last copy, which takes a line still being written and
            every log that is not lines too, and goes on until nothing is left behind.
        """
        with self._copying:
            try:
                # Bounded, for a log growing as fast as it is read.
                for _ in range(_ROUNDS if whole else 1):
                    if not self._copied(tuple(idents), whole=whole):
                        break
            except (OSError, ValueError, subprocess.SubprocessError) as why:
                (log.debug if self._said else log.warning)(
                    "could not copy %s's sessions from %s: %s",
                    self._profile.name,
                    self._way.target.describe(),
                    why,
                )
                self._said = True

    def _run(self) -> None:
        """Copies every session followed, every :data:`EVERY` seconds, until there are none."""
        while True:
            time.sleep(EVERY)
            with self._held:
                following = tuple(self._following)
                if not following:
                    self._thread = None
                    return
            self.copy(following)

    def _homes(self) -> list[tuple[str, str, str, str]]:
        """Each home to copy from, as the scripts above take one."""
        if self._told is None:
            return [self._home]
        variable, directory, inside, _ = self._home
        said: list[str] = []
        with contextlib.suppress(OSError):
            for one in sorted(self._told.iterdir()):
                with contextlib.suppress(OSError):
                    said += one.read_text(encoding="utf-8").splitlines()
        went = dict.fromkeys(
            where
            for name, _, where in (one.partition("=") for one in said)
            if name == variable and where
        )
        return [(variable, directory, inside, where) for where in went]

    def _copied(self, idents: tuple[str, ...], *, whole: bool) -> bool:
        """:meth:`copy` once, raising what went wrong.

        Returns:
          Whether a log was left only partly read, being longer than one read takes.
        """
        behind = False
        for home in self._homes():
            behind |= self._copied_from(home, idents, whole=whole)
        return behind

    def _copied_from(
        self, home: tuple[str, str, str, str], idents: tuple[str, ...], *, whole: bool
    ) -> bool:
        """:meth:`_copied`, from one home."""
        patterns = [
            # `find -path` lets a `*` cross a `/`, so a `**/` is a `*` that may be nothing.
            glob.replace("**/", "*")
            for ident in idents
            for glob in self._profile.logged(ident)
        ]
        # And names what it finds under `.` as `./` and the rest.
        patterns = [one if _root(one) != "." else f"./{one}" for one in patterns]
        if not patterns:
            return False
        roots = sorted({_root(one) for one in patterns})
        found: list[str] = ["("]
        for one in patterns:
            found += [*([] if len(found) == 1 else ["-o"]), "-path", one]
        listed = self._ran(_LIST, home, [*roots, "-type", "f", *found, ")"])
        grown: list[tuple[str, int, int, int]] = []
        for line in listed.decode("utf-8", "replace").splitlines():
            size, _, path = line.partition(" ")
            if not size.isdigit() or path.startswith("/") or ".." in path.split("/"):
                continue
            lines = path.endswith(_LINES)
            if not (lines or whole):
                continue  # written in place: copied whole, once, as the session closes
            here = self._into / path
            was = here.stat().st_size if here.is_file() else 0
            # Shorter than the copy is a file written again from the start.
            have = 0 if not lines or int(size) < was else was
            if int(size) > have or not lines:
                end = min(int(size), have + _MOST) if lines else int(size)
                grown.append((path, was, have, end))
        if not grown:
            return False
        said = self._ran(
            _READ,
            home,
            [str(one) for path, _, have, end in grown for one in (path, have, end)],
        )
        if len(said) != sum(end - have for _, _, have, end in grown):
            # Changed between the two commands: read again, now for a last copy, and next
            # time otherwise.
            return whole
        at, behind = 0, False
        for path, was, have, end in grown:
            chunk, at = said[at : at + end - have], at + end - have
            capped = path.endswith(_LINES) and end - have == _MOST
            behind |= capped
            if not (whole or capped):
                chunk = chunk[: chunk.rfind(b"\n") + 1]  # whole lines, until the last
            if not chunk:
                continue
            here = self._into / path
            here.parent.mkdir(parents=True, exist_ok=True)
            here.touch()
            with here.open("r+b") as copy:
                if copy.seek(0, os.SEEK_END) != was:
                    continue  # written meanwhile by something else, whose it is now
                copy.seek(have)
                copy.write(chunk)
                copy.truncate()
        return behind

    def _ran(
        self, script: str, home: tuple[str, str, str, str], args: list[str]
    ) -> bytes:
        """What one of the scripts above wrote, run on that machine.

        Raises:
          OSError: If it did not succeed.
          subprocess.TimeoutExpired: If it took longer than :data:`_ASKING`.
        """
        done = self._way.run(
            ["/bin/sh", "-c", script, "humanize", *home, *args], timeout=_ASKING
        )
        if done.returncode != 0:
            said = done.stderr.decode("utf-8", "replace").strip()
            raise OSError(f"exited {done.returncode}: {said}")
        return done.stdout


def roots(profile: Profile) -> tuple[str, ...]:
    """The directories under a CLI's home that it logs its sessions under, a file apiece.

    Args:
      profile: The CLI.

    Returns:
      Each, as the part of a log's glob before its first pattern; none is `.`.
    """
    return tuple(sorted({one for glob in profile.logs if (one := _root(glob)) != "."}))


def _root(glob: str) -> str:
    """The directory a glob is under, up to its first part that is a pattern."""
    parts = glob.split("/")[:-1]
    fixed: list[str] = []
    for part in parts:
        if _WILD.search(part):
            break
        fixed.append(part)
    return "/".join(fixed) or "."
