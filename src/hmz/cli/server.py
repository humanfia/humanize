"""``hmz server`` -- this machine's daemon, reachable from others until stopped.

`hmz web` serves the runs to a browser on this machine; `hmz server start` serves them to every
other machine that knows a secret, and goes on doing so after the terminal that started it has
gone. What it starts is one process, in a session of its own so that no hangup reaches it: an
`hmz web` on this machine's loopback at `easytier.PORT`, holding the runs through the daemon
and let into with a key derived from the secret, and beside it an `easytier-core` that makes
that one port reachable over the EasyTier network the secret names -- started again whenever it
goes. `hmz server stop` terminates that process, which stops both and leaves every run going.

The secret reaches the process on its standard input, which nobody else can read, rather than
on its command line, which anybody on the machine can; and `home()/server.json` says which
process it is, never what it was started with.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
import urllib.parse
from typing import IO, TYPE_CHECKING, Any, cast

from hmz import home
from hmz.coganchor import atomic, easytier

if TYPE_CHECKING:
    import argparse
    import threading
    from pathlib import Path

__all__ = ["RECORD", "server", "serves"]

#: What `hmz server start` writes down in Humanize's home: which process, and how it serves.
RECORD = "server.json"

#: How the server may be reached: over EasyTier, and as yet no other way.
_MODES = ("p2p",)

#: The schemes an EasyTier node is reached by.
_SCHEMES = ("tcp", "udp", "ws", "wss", "quic", "wg")

#: How long a server has to come up, its web listening and EasyTier running.
_STARTING = 60.0

#: How long a server has to go once it is terminated.
_STOPPING = 30.0

#: How long `easytier-core` has to still be running before it counts as started.
_SETTLING = 0.5

#: How long after `easytier-core` went it is started again.
_AGAIN = 1.0

#: How often the server looks at whether `easytier-core` is still running.
_LOOKING = 0.5

#: What the server says once it is up.
_UP = "up"


def _secret(said: str) -> str:
    """A secret, as `--secret` takes one.

    Raises:
      argparse.ArgumentTypeError: For one fewer than 16 bytes long.
    """
    import argparse

    try:
        return easytier.checked(said)
    except ValueError as why:
        raise argparse.ArgumentTypeError(str(why)) from None


def _peer(said: str) -> str:
    """An EasyTier node, as `--peer` takes one: `<scheme>://<host>:<port>`.

    Raises:
      argparse.ArgumentTypeError: For anything else.
    """
    import argparse

    parts = urllib.parse.urlsplit(said)
    try:
        port = parts.port
    except ValueError:
        port = None
    if parts.scheme not in _SCHEMES or not parts.hostname or port is None:
        msg = (
            f"{said} is not an EasyTier node: <scheme>://<host>:<port>, "
            f"the scheme one of {', '.join(_SCHEMES)}"
        )
        raise argparse.ArgumentTypeError(msg)
    return said


def server(argv: list[str]) -> int:
    """Starts this machine's server apart from the terminal, or stops the one running.

    Args:
      argv: What followed the command name.

    Returns:
      Zero once it has started or stopped; one where one is already running, none is, or it
      could not be started.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="hmz server",
        description="Keep this machine's daemon reachable from other machines that know a "
        "secret, until stopped. Its runs carry on either way.",
    )
    doing = parser.add_subparsers(dest="doing", metavar="{start,stop}", required=True)
    start = doing.add_parser(
        "start",
        help="start the server, apart from this terminal",
        description="Start the server apart from this terminal: this machine's runs, over "
        "EasyTier, to whoever knows the secret.",
    )
    start.add_argument(
        "--mode",
        required=True,
        choices=_MODES,
        help="how the server is reached: p2p, over EasyTier",
    )
    start.add_argument(
        "--secret",
        required=True,
        type=_secret,
        help="at least 16 bytes; the P2P daemon added on another machine takes the same",
    )
    start.add_argument(
        "--peer",
        required=True,
        action="append",
        type=_peer,
        metavar="URL",
        help="an EasyTier node both machines meet through, such as tcp://host:11010; "
        "repeat for more",
    )
    doing.add_parser(
        "stop",
        help="stop the server; its runs carry on",
        description="Stop the server. Its runs carry on.",
    )
    line = parser.parse_args(argv)
    if line.doing == "stop":
        return _stop()
    return _start(line)


def _record() -> Path:
    """Where the record of this machine's server is."""
    return home() / RECORD


def _running() -> int | None:
    """The process of the server running here, if one is: a record whose process is gone is none."""
    from hmz.daemon import where

    try:
        said: object = json.loads(_record().read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    pid = cast("dict[str, Any]", said).get("pid") if isinstance(said, dict) else None
    if isinstance(pid, int) and not isinstance(pid, bool) and where.alive(pid):
        return pid
    return None


def _start(line: argparse.Namespace) -> int:
    """`hmz server start`, its line read."""
    from importlib.metadata import version

    if (pid := _running()) is not None:
        print(f"hmz: a server is already running (pid {pid})", file=sys.stderr)
        return 1
    try:
        # Here rather than in the server, where it would be said to nobody.
        easytier.binary(lambda said: print(f"hmz: {said}", file=sys.stderr, flush=True))
        pid = _started(line.secret, line.peer)
    except OSError as why:
        print(f"hmz: the server cannot be started: {why}", file=sys.stderr)
        return 1
    said = {
        "pid": pid,
        "mode": line.mode,
        "port": easytier.PORT,
        "version": version("hmz"),
    }
    try:
        home().mkdir(parents=True, exist_ok=True)
        atomic.writes(_record(), json.dumps(said, indent=2) + "\n", mode=0o600)
    except OSError as why:
        # A server nobody can find to stop is not one to leave running.
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)
        print(f"hmz: the server cannot be recorded: {why}", file=sys.stderr)
        return 1
    print(f"hmz server: started (pid {pid})")
    return 0


def _started(secret: str, peers: list[str]) -> int:
    """Starts the server, in a session of its own, and waits until it says it is up.

    Returns:
      Its process.

    Raises:
      OSError: With what it said, where it did not come up.
    """
    reading, telling = os.pipe()
    try:
        child = subprocess.Popen(
            [sys.executable, "-Pm", __name__, str(telling), *peers],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            pass_fds=(telling,),
            start_new_session=True,
        )
    finally:
        os.close(telling)
    with os.fdopen(reading, "rb") as told:
        try:
            if child.stdin is not None:
                with child.stdin:
                    child.stdin.write(secret.encode("utf-8"))
            _up(child, told)
        except BaseException:
            # Interrupted as it came up, or it could not: none is left running unrecorded.
            if child.poll() is None:
                _stopped(child)
            raise
    return child.pid


def _up(child: subprocess.Popen[bytes], told: IO[bytes]) -> None:
    """Waits until the server says it is up.

    Raises:
      OSError: With what it said instead, or that it went or took too long.
    """
    import select

    deadline = time.monotonic() + _STARTING
    # Polled as well as read: a daemon it forked may hold the pipe open after it went.
    while time.monotonic() < deadline and child.poll() is None:
        if select.select([told], [], [], 0.2)[0]:
            said = told.readline().decode("utf-8", "replace").strip()
            if said == _UP:
                return
            if said:
                raise OSError(said)
            # Closed without a word: it is going, as whatever went wrong went unsaid.
            with contextlib.suppress(subprocess.TimeoutExpired):
                child.wait(_STOPPING)
            break
    if child.poll() is None:
        msg = f"it did not come up in {_STARTING:.0f} seconds"
        raise OSError(msg)
    msg = f"it exited as it started, with status {child.returncode}"
    raise OSError(msg)


def _stopped(child: subprocess.Popen[bytes]) -> None:
    """Terminates a server that did not come up, and waits for it to go."""
    child.terminate()
    try:
        child.wait(_STOPPING)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()


def _stop() -> int:
    """`hmz server stop`."""
    from hmz.daemon import where

    pid = _running()
    if pid is None:
        # One left behind by a server that went without being stopped is no server.
        _record().unlink(missing_ok=True)
        print("hmz: no server is running", file=sys.stderr)
        return 1
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + _STOPPING
    while where.alive(pid):
        if time.monotonic() >= deadline:
            print(
                f"hmz: the server did not stop in {_STOPPING:.0f} seconds (pid {pid})",
                file=sys.stderr,
            )
            return 1
        time.sleep(0.1)
    _record().unlink(missing_ok=True)
    print("hmz server: stopped")
    return 0


def serves(argv: list[str]) -> int:
    """The server itself, until it is terminated: the web and EasyTier, kept going.

    The secret is read whole from standard input. Once the web listens and `easytier-core`
    runs, `up` is written to the descriptor named, and otherwise what went wrong.

    Args:
      argv: The descriptor to say it is up on, then each EasyTier node to meet through.

    Returns:
      Zero once it has been terminated; one where it could not be started.
    """
    import threading

    telling, peers = int(argv[0]), argv[1:]
    secret = sys.stdin.buffer.read().decode("utf-8")
    # Noted rather than raised: raised, it could land between `easytier-core` starting and
    # its being held, which would leave it running on.
    stopping = threading.Event()

    def noted(_signum: int, _frame: object) -> None:
        stopping.set()

    was = {
        one: signal.signal(one, handler)
        for one, handler in (
            (signal.SIGTERM, noted),
            (signal.SIGHUP, signal.SIG_IGN),
        )
    }
    with os.fdopen(telling, "w", encoding="utf-8") as told:
        try:
            _served(secret, peers, told, stopping)
        except KeyboardInterrupt:
            return 0
        except (OSError, ValueError) as why:
            if not told.closed:
                told.write(f"{why}\n")
            return 1
        finally:
            for one, before in was.items():
                signal.signal(one, before)
    return 0


def _served(
    secret: str, peers: list[str], told: IO[str], stopping: threading.Event
) -> None:
    """The web and EasyTier until `stopping` is set, saying `up` once both are."""
    import threading

    from hmz.web import listening

    cores: list[subprocess.Popen[bytes]] = []
    with listening(port=easytier.PORT, apart=True, key=easytier.key(secret)) as site:
        threading.Thread(
            target=site.serve_forever,
            kwargs={"poll_interval": 0.5},
            daemon=True,
            name="hmz-server-web",
        ).start()
        try:
            cores.append(easytier.serving(secret, peers=peers))
            if stopping.wait(_SETTLING):
                return
            if (status := cores[-1].poll()) is not None:
                msg = f"easytier-core exited as it started, with status {status}"
                raise OSError(msg)
            told.write(f"{_UP}\n")
            told.close()
            # Waited on a while at a time: a terminate taken by another thread is acted on
            # only once this one wakes.
            while not stopping.wait(_LOOKING):
                if cores[-1].poll() is not None and not stopping.wait(_AGAIN):
                    with contextlib.suppress(OSError):
                        cores.append(easytier.serving(secret, peers=peers))
        finally:
            for core in cores:
                if core.poll() is None:
                    _stopped(core)
            site.shutdown()


if __name__ == "__main__":  # pragma: no cover -- the server's own process
    sys.exit(serves(sys.argv[1:]))
