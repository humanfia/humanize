"""The daemons a frontend may switch between: this machine's, and each ssh host written down.

`Local` is always there and never written down. Every other daemon is an ssh host, kept in
Humanize's one settings file under `daemons` with what `ssh` is told to reach it -- the same
fields an ssh runtime has, checked as one is, but for its workdir and fallback -- typed in a
part at a time or brought in from the ssh config. Every frontend that switches between them
writes them, and reaches them, through here.

What is reached there is that machine's own web interface: `hmz web --attached`, started over
ssh and stopped by the ssh going, with a port of this machine's loopback forwarded on to it.
Whoever reaches it asks it with its key: the remote interface keeps its own key, its own runs
and its own refusals.

An `hmz` missing there, or of another version than this one, is installed at this version with
`uv tool install`, uv itself fetched first where the host has none -- but never in place of one
the host's daemon may be running epics under, which keep running the release they started
with. A development build, `0.0.0`, installs nothing: it uses whatever `hmz` is there.

A daemon is reached when it is first asked for, or is told to connect, and reached again,
waiting longer each time, whenever it is lost.
"""

from __future__ import annotations

import contextlib
import dataclasses
import http.client
import json
import queue
import re
import socket
import subprocess
import threading
import time
from typing import TYPE_CHECKING, Any, ClassVar, cast

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from pathlib import Path
    from typing import IO

    from hmz.coganchor.transport import Road

__all__ = [
    "CARRIED",
    "FAILED",
    "LOCAL",
    "UP",
    "Daemons",
    "Remotes",
    "Unreached",
    "carried",
    "forwarding",
    "headers",
    "road",
    "said",
]

#: The daemon of this machine, which is always there and never written down.
LOCAL = "local"

#: The key of the settings file the daemons are kept under.
_KEY = "daemons"

#: What a daemon's name is spelled with: never starting with a dot, so never `.` or `..`.
_NAMED = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

#: What a daemon holds beside its name, as `ssh` is told it.
_FIELDS = (
    "host",
    "user",
    "port",
    "identity_file",
    "proxy_jump",
    "options",
    "alias",
    "config",
)


#: The settings a batch apply carries from one daemon to others, by the page each is set on:
#: never the accounts, which only a secret sets.
CARRIED = ("general", "fallback", "runtimes", "backup")


def carried(hmz: Any, pages: Sequence[str]) -> list[tuple[str, dict[str, Any]]]:
    """What one daemon's settings are written to another with, as its web interface takes them.

    What its Settings pages' `Batch apply` sends, so that a frontend copying them sends the
    same: each address and what is written there, of the pages asked for. A backup target's
    URL goes with nothing signed into it, so a target that signs in is refused there rather
    than its secret carried.

    Args:
      hmz: The daemon's own Humanize, whose settings are carried.
      pages: Which of :data:`CARRIED`.

    Returns:
      Each address and its body, in the order they are written.
    """
    settings = hmz.settings
    sent: list[tuple[str, dict[str, Any]]] = []
    if "general" in pages:
        general: dict[str, Any] = {"btw": settings.btw, "details": settings.details}
        if settings.enable_sentry is not None:
            general["reports"] = settings.enable_sentry
        sent.append(("/api/settings", general))
    if "fallback" in pages:
        sent += [
            (
                "/api/fallbacks",
                {
                    "spec": one.spec,
                    "to": list(one.to),
                    "tries": one.tries,
                    "policy": one.policy,
                    "timeout": one.timeout,
                },
            )
            for one in hmz.fallbacks.all()
        ]
    if "runtimes" in pages:
        for one in hmz.runtimes.all():
            fields = dict(one.held())
            backend, name = fields.pop("backend"), fields.pop("name")
            fields.pop("made", None)
            sent.append(
                (
                    "/api/runtimes",
                    {
                        "backend": backend,
                        "name": name,
                        "fields": fields,
                        "replace": True,
                    },
                )
            )
    if "backup" in pages:
        targets = [
            {
                "name": one.name,
                "url": hmz.verses.plain(one.url),
                "branch": one.branch,
                "policies": list(one.policies),
                "every": one.every,
            }
            for one in hmz.backups.targets()
        ]
        sent.append(
            (
                "/api/settings",
                {
                    "backup": {
                        "targets": targets,
                        "defaults": list(hmz.backups.defaults()),
                    }
                },
            )
        )
    return sent


class Unreached(RuntimeError):  # noqa: N818 -- what it is, as `Refused` is named
    """A daemon that is not up, or whose interface refused what it was asked.

    Attributes:
      seen: How it stands, `{state, detail, version}`, where it is not up; else empty.
      status: The HTTP status its interface refused with, or 503 where it was not reached.
    """

    def __init__(
        self, sentence: str, seen: dict[str, str] | None = None, status: int = 503
    ) -> None:
        super().__init__(sentence)
        self.seen = seen or {}
        self.status = status


def _checked(name: str, fields: dict[str, Any]) -> dict[str, Any]:
    """One daemon as it is written down, checked as an ssh runtime is.

    Args:
      name: What it is called.
      fields: The rest of it, `options` as `[[KEYWORD, VALUE], ...]` or by keyword.

    Returns:
      It, `options` as pairs.

    Raises:
      ValueError: If it cannot be one.
    """
    from hmz.coganchor.machines.store import SSH, SSHRuntime, new

    if not _NAMED.fullmatch(name) or name.lower() == LOCAL:
        raise ValueError(
            f"A daemon cannot be called {name!r}: say a letter or digit, then letters, "
            f"digits, dots, dashes and underscores, and not {LOCAL}."
        )
    if extra := sorted(set(fields) - set(_FIELDS)):
        raise ValueError(f"A daemon takes no {', '.join(extra)}.")
    given = dict(fields)
    options: object = given.get("options", [])
    if isinstance(options, list):
        pairs = cast("list[object]", options)
        if not all(
            isinstance(one, list) and len(cast("list[object]", one)) == 2  # noqa: PLR2004
            for one in pairs
        ):
            raise ValueError("Say options as pairs of a keyword and its value.")
        given["options"] = {
            str(key): str(value) for key, value in cast("list[list[object]]", pairs)
        }
    one = cast("SSHRuntime", new(SSH, name, **given))
    return {
        "name": one.name,
        **{field: getattr(one, field) for field in _FIELDS if field != "options"},
        "options": [[key, value] for key, value in one.options.items()],
    }


def _valid(held: dict[str, Any]) -> list[dict[str, Any]]:
    """Every ssh daemon a reading of the settings file holds, in order, each checked.

    One that cannot be one -- written wrong by hand, or under a name taken before it -- is
    left out, and so is gone the next time the daemons are written.
    """
    there: object = held.get(_KEY)
    kept: list[dict[str, Any]] = []
    for one in cast("list[object]", there) if isinstance(there, list) else []:
        fields = dict(cast("dict[str, Any]", one)) if isinstance(one, dict) else {}
        name = fields.pop("name", None)
        if not isinstance(name, str):
            continue
        try:
            entry = _checked(name, fields)
        except ValueError:
            continue
        if all(entry["name"] != each["name"] for each in kept):
            kept.append(entry)
    return kept


def _changes(change: Callable[[list[dict[str, Any]]], None]) -> None:
    """Makes one change to the daemons written down, and to nothing else in the file.

    Raises:
      OSError: If the file cannot be written.
    """
    from hmz.coganchor import settings

    def changing(held: dict[str, Any]) -> None:
        daemons = _valid(held)
        change(daemons)
        held[_KEY] = daemons

    settings.changes(changing)


def _named(alias: str) -> str:
    """What a host of the ssh config is called as a daemon: anything no name holds a dash."""
    return re.sub(r"[^A-Za-z0-9._-]", "-", alias).lstrip("._-")


class Daemons:
    """The ssh daemons written down, and reaching them: what every frontend switches between."""

    #: What a batch apply carries to them, as :data:`CARRIED`.
    CARRIED: ClassVar = CARRIED

    def all(self) -> list[dict[str, Any]]:
        """Every ssh daemon written down, in order; one that cannot be one is left out."""
        from hmz.coganchor import settings

        return _valid(settings.read())

    def find(self, name: str) -> dict[str, Any] | None:
        """The ssh daemon written down under a name, or None where there is none."""
        return next((one for one in self.all() if one["name"] == name), None)

    def write(
        self, name: str, fields: dict[str, Any], *, replace: bool = False
    ) -> dict[str, Any]:
        """Writes one daemon down, or over the one of its name where it is to `replace` it.

        Returns:
          It, as it is written.

        Raises:
          ValueError: If it cannot be one.
          FileExistsError: If one is called that already and it is not to be replaced.
          OSError: If the file cannot be written.
        """
        entry = _checked(name, fields)

        def change(daemons: list[dict[str, Any]]) -> None:
            at = next((i for i, one in enumerate(daemons) if one["name"] == name), -1)
            if at < 0:
                daemons.append(entry)
            elif replace:
                daemons[at] = entry
            else:
                raise FileExistsError(f"There is a daemon called {name} already.")

        _changes(change)
        return entry

    def remove(self, name: str) -> None:
        """Takes one daemon away.

        Raises:
          ValueError: For Local, which is always there.
          LookupError: If none is called that.
          OSError: If the file cannot be written.
        """
        if name.lower() == LOCAL:
            raise ValueError("Local is always there, and cannot be removed.")

        def change(daemons: list[dict[str, Any]]) -> None:
            kept = [one for one in daemons if one["name"] != name]
            if len(kept) == len(daemons):
                raise LookupError(f"There is no daemon called {name}.")
            daemons[:] = kept

        _changes(change)

    def offered(self) -> dict[str, dict[str, Any]]:
        """Each host of the ssh config not written down yet, as the daemon it would be.

        Of two that would be called the same, the first is offered.

        Raises:
          OSError: If the ssh config cannot be read.
        """
        from hmz.coganchor.machines import sshconfig

        daemons = self.all()
        names = {one["name"] for one in daemons}
        taken = {one["alias"] for one in daemons}
        offered: dict[str, dict[str, Any]] = {}
        for alias in sshconfig.aliases():
            if alias in taken:
                continue
            try:
                one = _checked(_named(alias), {"alias": alias})
            except ValueError:
                continue
            if one["name"] not in names:
                names.add(one["name"])
                offered[alias] = one
        return offered

    def imported(self, wanted: Sequence[str]) -> list[str]:
        """Brings hosts of the ssh config in as daemons, by their Host, skipping any there.

        Returns:
          What each one brought in is called.

        Raises:
          ValueError: For none, or for a host that cannot be one.
          LookupError: For a host the ssh config does not name.
          OSError: If the ssh config cannot be read, or the file written.
        """
        from hmz.coganchor.machines import sshconfig

        if not wanted:
            raise ValueError("Say aliases as the hosts to bring in, by their Host.")
        there = sshconfig.aliases()
        if missing := [one for one in wanted if one not in there]:
            raise LookupError(f"Your ssh config has no host {', '.join(missing)}.")
        for alias in wanted:
            try:
                _checked(_named(alias), {"alias": alias})
            except ValueError as why:
                raise ValueError(f"{alias} cannot be a daemon: {why}") from why
        added: list[str] = []

        def change(daemons: list[dict[str, Any]]) -> None:
            names = {one["name"] for one in daemons}
            taken = {one["alias"] for one in daemons}
            for alias in dict.fromkeys(wanted):
                one = _checked(_named(alias), {"alias": alias})
                if alias not in taken and one["name"] not in names:
                    daemons.append(one)
                    names.add(one["name"])
                    added.append(one["name"])

        _changes(change)
        return added

    def remotes(self, version: str | None = None) -> Remotes:
        """Every daemon written down, each reached as it is first asked for, until closed.

        Args:
          version: The version of `hmz` installed where another is found; this one's by
            default.
        """
        return Remotes(version)


#: The release of uv fetched onto a host that has none, through astral's installer for it:
#: the one Humanize Desktop pins.
UV = "0.12.24"

#: What a daemon's state may be.
IDLE, CONNECTING, INSTALLING, UP, FAILED = (
    "idle",
    "connecting",
    "installing",
    "up",
    "failed",
)

#: What every command there runs with: where `uv tool` and astral's installer put what they
#: install, which a shell that is not a login one may not have on its `PATH`.
_PATH = 'export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"; '

#: What is asked of a host before anything is started there: the version of its `hmz`, and
#: whether its daemon is running -- by the process `daemon.json` names in `humanize-<uid>` of
#: any temporary directory one may have been started with, as Humanize Desktop tells --
#: `unknown` where that cannot be read.
_PROBE = (
    _PATH
    + r"""
echo "hmz: $(hmz --version 2>/dev/null | sed -n 's/^hmz //p' | tail -n 1)"
daemon=none
for under in "$TMPDIR" "$TEMP" "$TMP" "$(getconf DARWIN_USER_TEMP_DIR 2>/dev/null)" \
    /tmp /var/tmp; do
  [ -n "$under" ] || continue
  record="${under%/}/humanize-$(id -u)/daemon.json"
  [ -e "$record" ] || continue
  if [ ! -r "$record" ]; then daemon=unknown; continue; fi
  pid=$(sed -n 's/.*"pid": *\([0-9][0-9]*\).*/\1/p' "$record" | head -n 1)
  if [ -z "$pid" ]; then daemon=unknown
  elif kill -0 "$pid" 2>/dev/null || ps -p "$pid" >/dev/null 2>&1; then
    daemon=running; break
  fi
done
echo "daemon: $daemon"
"""
)

#: Installs `hmz` at a version, `{version}`, fetching uv first where there is none.
_INSTALL = _PATH + (
    "export UV_NO_MODIFY_PATH=1; "
    "if ! command -v uv >/dev/null 2>&1; then "
    f"echo 'Getting uv {UV}'; "
    "if command -v curl >/dev/null 2>&1; "
    f"then curl -LsSf https://astral.sh/uv/{UV}/install.sh | sh; "
    f"else wget -qO- https://astral.sh/uv/{UV}/install.sh | sh; fi; "
    "command -v uv >/dev/null 2>&1 || exit 1; fi; "
    "exec uv tool install --force --python '>=3.12' 'hmz=={version}'"
)

#: Starts the interface there, for as long as the ssh holding its standard input lives.
_SERVE = _PATH + "exec hmz web --no-open --attached --port 0"

#: The line it says where it listens with.
_ADDRESS = re.compile(r"hmz web: http://127\.0\.0\.1:(\d+)/\?key=(\S+)")

#: What `ssh` is told for every command here before what the host's own settings and Humanize's
#: say beside them: nothing is asked of anybody, since nobody is at a terminal to answer.
_UNASKED = ("-o", "BatchMode=yes", "-o", "ConnectTimeout=20")

#: How long, in seconds, asking a host what it has may take.
_PROBING = 60.0

#: How long installing `hmz` there may take.
_INSTALLING = 900.0

#: How long the interface there may take to say where it listens.
_STARTING = 60.0

#: How long the forwarded port may take to be listened on.
_FORWARDING = 20.0

#: How long whoever asks for a daemon not yet reached waits for it.
_WAITING = 15.0

#: How long one question to a daemon reached may go unanswered.
_ASKING = 120.0

#: The wait before reaching a daemon again, doubled each time it fails, up to the last.
_BACKOFF = (1.0, 60.0)

#: How long a process is given to stop before it is killed.
_STOPPING = 3.0


class _Failed(Exception):  # noqa: N818 -- the sentence a daemon's state says
    """Reaching a daemon went wrong, as its state says it."""


def _here_version() -> str:
    """This Humanize's version, as PyPI has it."""
    from importlib.metadata import version

    return version("hmz")


def _entry(name: str) -> dict[str, Any] | None:
    """The daemon written down by that name, as it is listed, or None."""
    if name == LOCAL:  # This machine, whatever is written down.
        return None
    return Daemons().find(name)


def road(said: dict[str, Any]) -> Road:
    """How a command is run on a daemon's host, as its entry says to reach it.

    Raises:
      ValueError: For an entry that says no host, or says one wrongly.
    """
    from hmz.coganchor.machines.store import SSHRuntime
    from hmz.coganchor.transport import Road, Target, ssh_flags

    options: Any = said.get("options") or []
    if isinstance(options, dict):
        options = cast("dict[Any, Any]", options).items()
    try:
        pairs = cast("list[tuple[Any, Any]]", list(options))
        runtime = SSHRuntime(
            name="daemon",
            host=str(said.get("host") or ""),
            user=str(said.get("user") or ""),
            port=int(said.get("port") or 0),
            identity_file=str(said.get("identity_file") or ""),
            proxy_jump=str(said.get("proxy_jump") or ""),
            options={str(key): str(value) for key, value in pairs},
            alias=str(said.get("alias") or ""),
            config=str(said.get("config") or ""),
        )
    except (TypeError, ValueError) as why:
        raise ValueError(str(why).removeprefix("daemon: ")) from why
    target = Target(
        "ssh", host=runtime.login(), port=runtime.port, options=runtime.settings()
    )
    road = Road.to(target)
    # After what the host's own settings say, which win, and before what Humanize assumes.
    own = 1 + len(ssh_flags(target.options))
    prefix = (*road.prefix[:own], *_UNASKED, *road.prefix[own:])
    return dataclasses.replace(road, prefix=prefix)


def forwarding(on: Road, local: int, remote: int) -> list[str]:
    """The `ssh` that forwards a port of this machine's loopback to one of the host's.

    A connection of its own rather than one riding a shared master, whose forwards outlive
    the client that asked for them; and one that lasts as long as its standard input, which
    whatever started it holds, so that it goes with it however that goes.
    """
    ssh, *options, host = on.prefix
    alone = (
        ssh,
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPath=none",
        "-o",
        "ExitOnForwardFailure=yes",
        *options,
        "-L",
        f"127.0.0.1:{local}:127.0.0.1:{remote}",
        host,
    )
    return dataclasses.replace(on, prefix=alone).line(["cat"])


def said(lines: Sequence[str]) -> dict[str, str]:
    """What a host answered the probe with, by what each line says it is."""
    found: dict[str, str] = {}
    for line in lines:
        key, colon, value = line.partition(":")
        if colon and key in ("hmz", "daemon"):
            found[key] = value.strip()
    return found


def headers(port: int, key: str) -> dict[str, str]:
    """What a request to an interface listening on `port` carries to be let in, as its page's."""
    return {
        "Host": f"127.0.0.1:{port}",
        "Origin": f"http://127.0.0.1:{port}",
        "Sec-Fetch-Site": "same-origin",
        "Cookie": f"hmz-{port}={key}",
    }


def _free(wanted: int) -> int:
    """A port free on this machine's loopback: `wanted` where it is, else any.

    The one the other interface listens on where it can be had, so that a cookie for one is
    named as a cookie for the other.
    """
    for port in (wanted, 0):
        with socket.socket() as trying:
            try:
                trying.bind(("127.0.0.1", port))
            except OSError:
                continue
            return int(trying.getsockname()[1])
    raise _Failed("No port is free here to forward.")


def _last(lines: Sequence[str], otherwise: str) -> str:
    """The last line said, or what is said otherwise."""
    return next((line for line in reversed(lines) if line.strip()), otherwise).strip()


class _Remote:
    """One daemon, reached and reached again on a thread of its own until it is closed."""

    def __init__(self, name: str, version: str, changed: threading.Condition) -> None:
        self.name = name
        self._version = version
        self._changed = changed
        self.state = IDLE
        self.detail = ""
        self.there = ""
        self.port = 0
        self.remote = 0
        self.key = ""
        self.entry: dict[str, Any] | None = None
        #: What is said of it while it is up: why its hmz is not this one's, where it is not.
        self._note = ""
        self._children: set[subprocess.Popen[str]] = set()
        self._closed = threading.Event()
        self._again = threading.Event()
        self._thread: threading.Thread | None = None

    def seen(self) -> dict[str, str]:
        return {"state": self.state, "detail": self.detail, "version": self.there}

    def starts(self, said: dict[str, Any], *, now: bool) -> None:
        """Reaches it, as `said` is its entry.

        Again at once where that has changed, or where it failed and is wanted `now` rather
        than after its wait.
        """
        if self._thread is None or not self._thread.is_alive():
            self._closed.clear()
            self._thread = threading.Thread(
                target=self._keeps, daemon=True, name=f"hmz-remote-{self.name}"
            )
            self._thread.start()
        elif (now and self.state == FAILED) or said != self.entry:
            self._again.set()

    def close(self) -> None:
        self._closed.set()
        self._again.set()
        with self._changed:
            children = list(self._children)
        for child in children:
            _stops(child)
        if self._thread is not None:
            self._thread.join(timeout=_STOPPING * 3)

    def _says(self, state: str, detail: str = "") -> None:
        with self._changed:
            self.state, self.detail = state, detail
            self._changed.notify_all()

    def _keeps(self) -> None:
        """Reaches it, holds it while it lasts, and reaches it again after a wait."""
        wait = _BACKOFF[0]
        while not self._closed.is_set():
            self._again.clear()
            self._says(CONNECTING)
            try:
                web, forward = self._reaches()
            except Exception as why:  # noqa: BLE001 -- whatever it was is what it says
                self._ends()
                if self._closed.is_set():
                    break
                self._says(FAILED, str(why))
            else:
                self._says(UP, self._note)
                wait = _BACKOFF[0]
                while not self._again.wait(0.25):
                    if web.poll() is not None or forward.poll() is not None:
                        break
                self._ends()
                if self._closed.is_set():
                    break
                if self._again.is_set():
                    continue
                self._says(CONNECTING, "Lost")
            self._again.wait(wait)
            wait = min(wait * 2, _BACKOFF[1])
        self._says(IDLE)

    def _reaches(self) -> tuple[subprocess.Popen[str], subprocess.Popen[str]]:
        """Reaches it.

        Probes the host, installs `hmz` there where it must, starts the interface there and
        forwards a port to it.

        Returns:
          The interface there, and the forward.

        Raises:
          _Failed: Saying what went wrong.
        """
        self.entry = _entry(self.name)
        if self.entry is None:
            raise _Failed(f"No daemon is called {self.name}.")
        try:
            on = road(self.entry)
        except ValueError as why:
            raise _Failed(str(why)) from why
        version = self._installed(on)
        self.there = version
        web = self._started(on.line(["sh", "-c", _SERVE]), apart=True)
        address = self._listens(web)
        self.remote, self.key = int(address[1]), address[2]
        self.port = _free(self.remote)
        forward = self._started(forwarding(on, self.port, self.remote))
        told = _drained(forward)
        ending = time.monotonic() + _FORWARDING
        while not _listened(self.port):
            if forward.poll() is not None:
                time.sleep(0.1)  # For what it said last to be read.
                raise _Failed(_last(told, "The port could not be forwarded."))
            if self._closed.is_set() or time.monotonic() > ending:
                raise _Failed("The port was not forwarded in time.")
            time.sleep(0.05)
        return web, forward

    def _installed(self, on: Road) -> str:
        """The version of `hmz` there, once it is this one where it may be made so."""
        self._note = ""
        found = self._probed(on)
        there = found.get("hmz", "")
        wanted = self._version
        if wanted in ("0.0.0", there):
            if not there:
                raise _Failed(f"hmz is not installed on {self.name}.")
            return there
        if there and found.get("daemon") != "none":
            if found.get("daemon") == "running":
                why = f"hmz {there} there holds running epics; hmz {wanted} waits"
            else:
                why = f"Whether hmz {there} there runs epics is unknown; not replaced"
            self._note = why
            return there
        self._says(INSTALLING, f"hmz {wanted}")
        lines: list[str] = []
        installing = self._started(
            on.line(["sh", "-c", _INSTALL.format(version=wanted)])
        )
        for line in _lines(installing, _INSTALLING):
            lines.append(line)
            if line.strip():
                self._says(INSTALLING, line.strip())
        if installing.wait() != 0:
            raise _Failed(_last(lines, f"hmz {wanted} could not be installed."))
        there = self._probed(on).get("hmz", "")
        if there != wanted:
            raise _Failed(f"hmz {wanted} was installed, and hmz {there} answers.")
        return there

    def _probed(self, on: Road) -> dict[str, str]:
        probing = self._started(on.line(["sh", "-c", _PROBE]))
        lines = list(_lines(probing, _PROBING))
        if probing.wait() != 0 or "daemon" not in said(lines):
            raise _Failed(_last(lines, f"{self.name} did not answer."))
        return said(lines)

    def _listens(self, web: subprocess.Popen[str]) -> re.Match[str]:
        """Where the interface there listens, once it says."""
        stdout = web.stdout
        assert stdout is not None  # noqa: S101 -- it was started with one
        assert web.stderr is not None  # noqa: S101
        heard: queue.Queue[str | None] = queue.Queue()
        errors = _drained(web, web.stderr)

        def reads() -> None:
            # Read to its end, which it says nothing more before.
            with contextlib.suppress(OSError, ValueError), stdout:
                for line in stdout:
                    heard.put(line)
            heard.put(None)

        threading.Thread(target=reads, daemon=True, name="hmz-remote").start()
        ending = time.monotonic() + _STARTING
        while True:
            try:
                line = heard.get(timeout=min(1.0, max(0.0, ending - time.monotonic())))
            except queue.Empty:
                if time.monotonic() >= ending:
                    raise _Failed(
                        _last(errors, "hmz web there did not say where it listens.")
                    ) from None
                # What it says while it comes up, said as how it stands.
                if errors:
                    self._says(CONNECTING, _last(errors, ""))
                continue
            if line is None:
                web.wait()
                raise _Failed(_last(errors, "hmz web there stopped."))
            found = _ADDRESS.search(line)
            if found:
                return found

    def _started(
        self, argv: list[str], *, apart: bool = False
    ) -> subprocess.Popen[str]:
        """A process, which is stopped as this daemon is closed or lost.

        Its standard input is held open until then, so that it goes with this one however
        that goes; what it says on stderr is read `apart` from its stdout, or with it.
        """
        with self._changed:
            if self._closed.is_set():
                raise _Failed("Closed.")
            try:
                child = subprocess.Popen(
                    argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE if apart else subprocess.STDOUT,
                    text=True,
                    errors="replace",
                    start_new_session=True,
                )
            except OSError as why:
                raise _Failed(f"ssh could not be run: {why}") from why
            self._children.add(child)
        return child

    def _ends(self) -> None:
        """Stops and reaps every process started for it."""
        with self._changed:
            children = list(self._children)
            self._children.clear()
        for child in children:
            _stops(child)


def _lines(child: subprocess.Popen[str], patience: float) -> Iterator[str]:
    """Each line a process says, until it ends or has taken longer than `patience`."""
    assert child.stdout is not None  # noqa: S101 -- it was started with one
    timer = threading.Timer(patience, child.kill)
    timer.start()
    try:
        with child.stdout:
            yield from (line.rstrip("\n") for line in child.stdout)
    finally:
        timer.cancel()


def _drained(child: subprocess.Popen[str], said: IO[str] | None = None) -> list[str]:
    """The last lines a process says, read as it says them so that it is never held up.

    Args:
      child: The process.
      said: What of it is read: its stdout, by default.
    """
    lines: list[str] = []
    held = said or child.stdout
    assert held is not None  # noqa: S101 -- it was started with one

    def drains() -> None:
        with held, contextlib.suppress(OSError, ValueError):
            for line in held:
                lines.append(line.rstrip("\n"))
                del lines[:-20]

    threading.Thread(target=drains, daemon=True, name="hmz-remote").start()
    return lines


def _listened(port: int) -> bool:
    """Whether something listens on a port of this machine's loopback."""
    with socket.socket() as trying:
        trying.settimeout(1.0)
        return trying.connect_ex(("127.0.0.1", port)) == 0


def _stops(child: subprocess.Popen[str]) -> None:
    """Stops a process and reaps it: its standard input closed, then terminated, then killed."""
    if child.stdin is not None:
        with contextlib.suppress(OSError):
            child.stdin.close()
    with contextlib.suppress(subprocess.TimeoutExpired):
        child.wait(timeout=1.0)
    if child.poll() is None:
        with contextlib.suppress(OSError):
            child.terminate()
        try:
            child.wait(timeout=_STOPPING)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


class Remotes:
    """Every daemon on another machine, as each is reached.

    Args:
      version: The version of `hmz` installed where another is found; this one's by default.
    """

    def __init__(self, version: str | None = None) -> None:
        self._version = version or _here_version()
        self._changed = threading.Condition()
        self._held: dict[str, _Remote] = {}
        self._closed = False

    def state(self, name: str) -> dict[str, str]:
        """How a daemon stands: `{state, detail, version}`.

        Its state is `idle` where it has not been asked for, then `connecting`, `installing`,
        `up` or `failed`; Local's is `up` at this version.
        """
        if name == LOCAL:
            return {"state": UP, "detail": "", "version": _here_version()}
        with self._changed:
            held = self._held.get(name)
            return held.seen() if held else {"state": IDLE, "detail": "", "version": ""}

    def connect(self, name: str) -> dict[str, str]:
        """Starts reaching a daemon, or reaches it again at once where it failed.

        Returns:
          How it stands.

        Raises:
          LookupError: If no daemon is written down by that name.
          Unreached: If these are closing.
        """
        self._starts(name, now=True)
        return self.state(name)

    def reached(self, name: str) -> tuple[int, str]:
        """Where a daemon is reached here, and the key it lets in.

        Reached first where it was not, waiting a while for it.

        Returns:
          The port of this machine's loopback forwarded to it, and its key.

        Raises:
          Unreached: If it is not up, with its state.
          LookupError: If none is called that.
        """
        held = self._up(name)
        return held.port, held.key

    def asks(self, name: str) -> tuple[int, dict[str, str]]:
        """Where a daemon is reached here, and what a request to it carries to be let in.

        Raises:
          Unreached: As `reached` does.
          LookupError: As `reached` does.
        """
        held = self._up(name)
        return held.port, headers(held.remote, held.key)

    def asked(
        self,
        name: str,
        path: str,
        body: dict[str, Any] | None = None,
        *,
        into: Path | None = None,
    ) -> Any:
        """What a daemon's interface answers, reached first where it was not.

        Args:
          name: The daemon.
          path: What is asked of it, `/api/...` and its query; a write where there is a body.
          body: What is written, as JSON; None for a read.
          into: Where what it answers is written, as it comes, rather than read as JSON.

        Returns:
          Its answer, read as JSON; or, `into` a file, how many bytes were written there.

        Raises:
          Unreached: If it is not up, or refused, saying why.
          LookupError: If none is called that.
          OSError: If it went where it was asked, or the file could not be written.
        """
        port, said = self.asks(name)
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=_ASKING)
        try:
            return self._answer(connection, name, path, said, body, into)
        except (http.client.HTTPException, ValueError) as why:
            raise Unreached(f"{name} answered what cannot be read: {why}") from why
        finally:
            connection.close()

    @staticmethod
    def _answer(
        connection: http.client.HTTPConnection,
        name: str,
        path: str,
        said: dict[str, str],
        body: dict[str, Any] | None,
        into: Path | None,
    ) -> Any:
        """What one question to a daemon's interface is answered with, as `asked` says.

        What is written `into` a file is written beside it first and moved into place, so
        that a file there already is replaced whole or not at all.
        """
        if body is None:
            connection.request("GET", path, headers=said)
        else:
            connection.request(
                "POST",
                path,
                json.dumps(body).encode(),
                said | {"Content-Type": "application/json"},
            )
        answer = connection.getresponse()
        if answer.status >= 300:  # noqa: PLR2004 -- any status but a success
            try:
                refused: object = json.loads(answer.read() or b"{}")
            except ValueError:
                refused = None
            why = (
                cast("dict[str, Any]", refused).get("error")
                if isinstance(refused, dict)
                else None
            )
            raise Unreached(
                str(why or f"{name} answered {answer.status}"),
                status=answer.status,
            )
        if into is None:
            return json.loads(answer.read() or b"null")
        beside = into.with_name(f".{into.name}.new")
        written = 0
        try:
            with beside.open("wb") as file:
                while chunk := answer.read(65536):
                    written += file.write(chunk)
            beside.replace(into)
        finally:
            beside.unlink(missing_ok=True)
        return written

    def followed(
        self, name: str, path: str, going: threading.Event
    ) -> Iterator[tuple[str, Any]]:
        """Each server-sent event a daemon's interface says at one address, as it says it.

        Args:
          name: The daemon.
          path: What is followed there, `/api/...` and its query.
          going: Set to stop following, which the next word from there or its quiet ends.

        Yields:
          Each event's name and its data, read as JSON, until the stream ends.

        Raises:
          Unreached: If it is not up, or refused, saying why.
          LookupError: If none is called that.
        """
        port, said = self.asks(name)
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=_ASKING)
        try:
            connection.request("GET", path, headers=said)
            answer = connection.getresponse()
            if answer.status >= 300:  # noqa: PLR2004 -- any status but a success
                raise Unreached(
                    f"{name} answered {answer.status}", status=answer.status
                )
            event, data = "", list[str]()
            while not going.is_set() and (line := answer.readline()):
                heard = line.decode().rstrip("\r\n")
                if heard.startswith("event:"):
                    event = heard[6:].strip()
                elif heard.startswith("data:"):
                    data.append(heard[5:].removeprefix(" "))
                elif not heard:
                    if event and data:
                        yield event, json.loads("\n".join(data))
                    event, data = "", []
        finally:
            connection.close()

    def close(self) -> None:
        """Stops reaching every daemon, every process started for one stopped and reaped."""
        with self._changed:
            self._closed = True
            held = list(self._held.values())
        stopping = [threading.Thread(target=one.close) for one in held]
        for one in stopping:
            one.start()
        for one in stopping:
            one.join()

    def _starts(self, name: str, *, now: bool) -> _Remote:
        """A daemon, being reached: again where what reaches it has changed.

        Raises:
          LookupError: If none is written down by that name -- one that was is let go of.
          Unreached: If these are closing.
        """
        said = _entry(name)
        with self._changed:
            if self._closed:
                raise Unreached("Reaching daemons is stopping.")
            if said is None:
                gone = self._held.pop(name, None)
                if gone is not None:
                    threading.Thread(target=gone.close, daemon=True).start()
                raise LookupError("There is no daemon by that name.")
            held = self._held.setdefault(
                name, _Remote(name, self._version, self._changed)
            )
        held.starts(said, now=now)
        return held

    def _up(self, name: str) -> _Remote:
        """A daemon once it is up, waiting a while for one being reached.

        Raises:
          Unreached: If it is not up, with its state.
          LookupError: If none is called that.
        """
        held = self._starts(name, now=False)
        with self._changed:
            # Not past a failure, which is reached again after its wait rather than at once.
            self._changed.wait_for(
                lambda: held.state in (UP, FAILED, INSTALLING), timeout=_WAITING
            )
            if held.state == UP:
                return held
            raise Unreached(held.detail or f"{name} is not reached yet.", held.seen())
