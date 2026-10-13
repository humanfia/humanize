"""Daemons on other machines, reached over ssh and answered through this interface.

Each daemon written down under `daemons` in humanize's settings is a host that `ssh` reaches.
What is reached there is that machine's own web interface: `hmz web --attached`, started over
ssh and stopped by the ssh going, with a port of this machine's loopback forwarded on to it. A
page asks this interface, which asks that one with its key: the remote interface keeps its own
key, its own runs and its own refusals, and nothing of it is served to anything but this page.

An `hmz` missing there, or of another version than this one, is installed at this version with
`uv tool install`, uv itself fetched first where the host has none -- but never in place of one
the host's daemon may be running epics under, which keep running the release they started
with. A development build, `0.0.0`, installs nothing: it uses whatever `hmz` is there.

A daemon is reached when a page first asks for it, or is told to connect, and reached again,
waiting longer each time, whenever it is lost.
"""

from __future__ import annotations

import contextlib
import dataclasses
import queue
import re
import socket
import subprocess
import threading
import time
from typing import TYPE_CHECKING, Any, cast

from .routing import Refusal, routes

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from typing import IO

    from hmz.coganchor.transport import Road

    from .routing import Asked

__all__ = ["ROUTES", "Remotes", "forwarding", "headers", "road", "said"]

#: The release of uv fetched onto a host that has none, through astral's installer for it:
#: the one the desktop app pins.
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
#: any temporary directory one may have been started with, as the desktop app tells --
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

#: What `ssh` is told for every command here before what the host's own settings and humanize's
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

#: How long a page asking for a daemon not yet reached waits for it.
_WAITING = 15.0

#: The wait before reaching a daemon again, doubled each time it fails, up to the last.
_BACKOFF = (1.0, 60.0)

#: How long a process is given to stop before it is killed.
_STOPPING = 3.0


class _Failed(Exception):  # noqa: N818 -- the sentence a daemon's state says
    """Reaching a daemon went wrong, as its state says it."""


def _here_version() -> str:
    """This humanize's version, as PyPI has it."""
    from importlib.metadata import version

    return version("hmz")


def _entries() -> list[dict[str, Any]]:
    """Every daemon written down, as humanize's settings hold them."""
    from hmz.coganchor import settings

    said = settings.read().get("daemons")
    if not isinstance(said, list):
        return []
    return [
        cast("dict[str, Any]", one)
        for one in cast("list[object]", said)
        if isinstance(one, dict)
    ]


def _entry(name: str) -> dict[str, Any] | None:
    """The daemon written down by that name, or None."""
    if name == "local":  # This machine, whatever is written down.
        return None
    return next((one for one in _entries() if one.get("name") == name), None)


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
    # After what the host's own settings say, which win, and before what humanize assumes.
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
                target=self._keeps, daemon=True, name=f"hmz-web-remote-{self.name}"
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

        threading.Thread(target=reads, daemon=True, name="hmz-web-remote").start()
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

    threading.Thread(target=drains, daemon=True, name="hmz-web-remote").start()
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
        `up` or `failed`.
        """
        with self._changed:
            held = self._held.get(name)
            return held.seen() if held else {"state": IDLE, "detail": "", "version": ""}

    def connect(self, name: str) -> dict[str, str]:
        """Starts reaching a daemon, or reaches it again at once where it failed.

        Returns:
          How it stands.

        Raises:
          Refusal: If no daemon is written down by that name.
        """
        self._starts(name, now=True)
        return self.state(name)

    def reached(self, name: str) -> tuple[int, str]:
        """Where a daemon is reached here, and the key it lets in.

        Reached first where it was not, waiting a while for it.

        Returns:
          The port of this machine's loopback forwarded to it, and its key.

        Raises:
          Refusal: If it is not up, with its state; or if none is called that.
        """
        held = self._up(name)
        return held.port, held.key

    def asks(self, name: str) -> tuple[int, dict[str, str]]:
        """Where a daemon is reached here, and what a request to it carries to be let in.

        Raises:
          Refusal: As `reached` does.
        """
        held = self._up(name)
        return held.port, headers(held.remote, held.key)

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
          Refusal: If none is written down by that name -- one that was is let go of.
        """
        said = _entry(name)
        with self._changed:
            if self._closed:
                raise Refusal("This interface is stopping.", 503)
            if said is None:
                gone = self._held.pop(name, None)
                if gone is not None:
                    threading.Thread(target=gone.close, daemon=True).start()
                raise Refusal("There is no daemon by that name.", 404)
            held = self._held.setdefault(
                name, _Remote(name, self._version, self._changed)
            )
        held.starts(said, now=now)
        return held

    def _up(self, name: str) -> _Remote:
        """A daemon once it is up, waiting a while for one being reached.

        Raises:
          Refusal: If it is not up, with its state; or if none is called that.
        """
        held = self._starts(name, now=False)
        with self._changed:
            # Not past a failure, which is reached again after its wait rather than at once.
            self._changed.wait_for(
                lambda: held.state in (UP, FAILED, INSTALLING), timeout=_WAITING
            )
            if held.state == UP:
                return held
            raise Refusal(
                held.detail or f"{name} is not reached yet.", 503, **held.seen()
            )


def _local() -> dict[str, str]:
    return {"state": UP, "detail": "", "version": _here_version()}


def _remotes(asked: Asked) -> Remotes:
    """The daemons on other machines, where the interface reaches any by the name asked."""
    if asked.site.remotes is None or _entry(asked.matched["name"]) is None:
        raise Refusal("There is no daemon by that name.", 404)
    return asked.site.remotes


def _state(asked: Asked) -> dict[str, str]:
    name = asked.matched["name"]
    return _local() if name == "local" else _remotes(asked).state(name)


def _connect(asked: Asked) -> dict[str, str]:
    name = asked.matched["name"]
    return _local() if name == "local" else _remotes(asked).connect(name)


#: How a page reads how a daemon stands, and has it reached.
ROUTES = routes(
    ("GET", "/api/daemons/{name}/state", _state),
    ("POST", "/api/daemons/{name}/connect", _connect),
)
