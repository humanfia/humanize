"""Running a program inside a :class:`~hmz.coganchor.fence.Fence`, and waiting for it.

What ``hmz internal fence`` is: the program is forked, the child walls itself in and becomes
it, and the parent stays outside the wall for as long as the program runs -- serving the
proxy that is the one way out of it where the network is cut, passing on the signals meant for
the program, and exiting with the program's own status once it is done.

The wall is put up in the child, just before ``execve``, because that is the only place it can
be: Landlock and seccomp restrict the thread that asks and everything it later starts, and
nothing already running can be restricted from outside. In order: the environment is settled;
where the network is cut, the socket filter is loaded and so is the filter that stops every
``bind`` and ``listen`` for the parent to answer (:mod:`hmz.coganchor.fence.loopback`), whose
descriptor is handed up to it; the Landlock ruleset is applied; and the program is run. A step
that fails is a program that does not run -- never one that runs with less of the wall than
was asked for.

Where the network is cut the parent is also the subreaper of everything inside: a process
that left its parent behind -- a daemon that forked twice -- is still one of the wrapper's
descendants, which is what this kernel asks of a process before it lets another read its
memory or take one of its descriptors, and so still one whose ``listen`` can be answered.
"""

from __future__ import annotations

import contextlib
import ctypes
import errno
import importlib
import os
import shutil
import signal
import socket
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Final

from hmz.coganchor.fence import Fence, Proxy

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hmz.coganchor.fence.loopback import Supervisor

__all__ = ["CACHES", "PROXIES", "environ", "run"]

#: The variables every common HTTP client reads its proxy from, in both the spellings they are
#: read in -- curl reads only the lower-case `http_proxy`, most others either.
PROXIES: Final = (
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    "https_proxy",
    "http_proxy",
    "all_proxy",
)

#: The variables that say where a build keeps its caches, each with where it keeps them when
#: nothing is said -- under the home, which a fence that does not let the home be written
#: would make a build fail over. Such a cache is pointed into the fence's own scratch instead,
#: so that installing and compiling go on working and only go on more slowly.
CACHES: Final = {
    "XDG_CACHE_HOME": "~/.cache",
    "UV_CACHE_DIR": "~/.cache/uv",
    "npm_config_cache": "~/.npm",
    "PIP_CACHE_DIR": "~/.cache/pip",
    "GOCACHE": "~/.cache/go-build",
}

#: What a program that was never run exits with: 126 for one that was found and could not be
#: run, which a fence that could not be put up is.
_UNFENCED: Final = 126

#: `prctl`'s option for the signal a process is sent when its parent dies.
_PR_SET_PDEATHSIG: Final = 1

#: `prctl`'s option that makes a process the one its orphaned descendants are handed to.
_PR_SET_CHILD_SUBREAPER: Final = 36


def environ(
    fence: Fence, given: Mapping[str, str], *, tmp: str, port: int | None
) -> dict[str, str]:
    """The environment the program is run with inside the fence.

    Args:
      fence: The fence.
      given: The environment it would have been run with.
      tmp: The fence's scratch directory.
      port: The proxy's port on loopback, or None where the network is not cut.

    Returns:
      `given`, with the scratch directory as the temporary directory, every cache the fence
      would not let it write where it is pointed into the scratch instead, and -- where the
      network is cut -- the proxy as every client's proxy, with nothing exempted from it.
    """
    held = dict(given)
    for name in ("TMPDIR", "TMP", "TEMP"):
        held[name] = tmp
    for name, usual in CACHES.items():
        at = Path(held.get(name) or Path(usual).expanduser())
        if not (at.is_absolute() and fence.allows(at, write=True)):
            held[name] = str(Path(tmp, "cache", name.lower()))
    if port is not None:
        proxy = f"http://127.0.0.1:{port}"
        held.update(dict.fromkeys(PROXIES, proxy))
        # Emptied rather than removed: a `NO_PROXY` somebody exported would otherwise send
        # the hosts it names around the proxy, into a wall.
        held.update(NO_PROXY="", no_proxy="", NODE_USE_ENV_PROXY="1")
    return held


def run(fence: Fence, argv: Sequence[str]) -> int:
    """Runs a program inside a fence, and waits for it.

    Args:
      fence: What it may reach.
      argv: The program and its arguments.

    Returns:
      Its exit status, or 128 plus the signal that killed it, or 126 where the fence could
      not be put up and the program never ran.

    Raises:
      ValueError: If there is no program to run.
      RuntimeError: If this host cannot enforce the fence, said before anything is started.
    """
    from hmz.coganchor.fence import enforceable
    from hmz.coganchor.providers.redirect import failed, swept

    if not argv:
        raise ValueError("no program to run")
    if not enforceable(net=not fence.online):
        needs = "Landlock ABI 4 and seccomp" if not fence.online else "Landlock"
        raise RuntimeError(f"this machine cannot fence a program: it needs {needs}")
    # Loaded before the fork rather than in the child: a child of a process with threads --
    # the proxy's -- may take no lock one of them held, and importing takes one.
    from hmz.coganchor.linux import landlock

    if not fence.online:
        importlib.import_module("hmz.coganchor.linux.seccomp")
    landlock.abi()
    libc = ctypes.CDLL(None, use_errno=True)
    made = not fence.tmp
    tmp = fence.tmp or tempfile.mkdtemp(prefix="hmz-fence-")
    Path(tmp).mkdir(mode=0o700, parents=True, exist_ok=True)
    proxy = None if fence.online else Proxy(fence.hosts)
    supervisor: Supervisor | None = None
    try:
        if proxy is not None:
            proxy.start()
            if libc.prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
                code = ctypes.get_errno()
                raise OSError(code, os.strerror(code), "prctl(PR_SET_CHILD_SUBREAPER)")
        port = proxy.port if proxy is not None else None
        env = environ(fence, os.environ, tmp=tmp, port=port)
        parent = os.getpid()
        ours, theirs = socket.socketpair() if proxy is not None else (None, None)
        pid = os.fork()
        if not pid:
            _become(fence, argv, env, tmp, (port, theirs), (parent, libc))
        try:
            if ours is not None and theirs is not None:
                theirs.close()
                with ours:
                    # Nothing where the child failed before it could hand the listener up,
                    # and then it exits unfenced rather than runs: it is waited for as it is.
                    _, handed, _, _ = socket.recv_fds(ours, 1, 1)
                if handed:
                    from hmz.coganchor.fence.loopback import Supervisor

                    supervisor = Supervisor(handed[0])
                    supervisor.start()
            return failed(_waited(pid))
        finally:
            # What a supervisor inside left of a credential in memory, where the program
            # was `hmz internal cred` and was killed before it could take it away itself.
            swept(pid)
    finally:
        if supervisor is not None:
            supervisor.stop()
        if proxy is not None:
            proxy.stop()
        if made:
            shutil.rmtree(tmp, ignore_errors=True)


def _become(
    fence: Fence,
    argv: Sequence[str],
    env: dict[str, str],
    tmp: str,
    offline: tuple[int | None, socket.socket | None],
    orphaned: tuple[int, ctypes.CDLL],
) -> None:
    """The child's half: wall itself in and become the program. Never returns.

    It goes when the wrapper does, however the wrapper went: a `SIGKILL` is not a signal the
    wrapper can pass on, and a program left running without it would be one whose proxy has
    gone and whose turn nobody is waiting for.
    """
    try:
        from hmz.coganchor.linux import landlock

        port, handoff = offline
        parent, libc = orphaned
        libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0)
        if os.getppid() != parent:  # the wrapper went before that was said
            os._exit(_UNFENCED)

        if port is not None:
            from hmz.coganchor.linux import seccomp

            seccomp.install_socket_filter()
            try:
                listener = seccomp.install_listener()
            except OSError as why:
                if why.errno != errno.EBUSY:
                    raise
                # A thread answers to one supervisor, and this one already has: it is inside
                # a fence that cut the network, whose wrapper already keeps it on loopback.
                raise RuntimeError(
                    "it is already inside a fence that cuts the network"
                ) from why
            if handoff is None:
                raise RuntimeError("nobody to answer its binds")  # noqa: TRY301
            socket.send_fds(handoff, [b"!"], [listener])
            # Closed before the program runs, not merely on exec: a program holding the
            # listener could answer its own calls.
            os.close(listener)
            handoff.close()
        landlock.Ruleset(
            read=fence.read,
            write=(*fence.write, tmp),
            connect_ports=() if port is None else (port,),
            # A port the kernel picks is a listener only, which reaches nothing: a CLI that
            # serves itself on loopback (agy's language server) cannot start without one. A
            # CLI that has to be found at a port of its own (kimi's daemon) names it in
            # `listen`.
            bind_ports=() if port is None else (0, *fence.listen),
            net=port is not None,
        ).restrict_self()
    # Everything, deliberately: this is the forked child, and anything escaping here would run
    # the parent's code a second time rather than report a fence that could not be put up.
    except BaseException as why:  # noqa: BLE001
        os.write(2, f"hmz internal fence: cannot fence {argv[0]}: {why}\n".encode())
        os._exit(_UNFENCED)
    try:
        # Becoming the program is the whole errand of this fork, and it is an argv rather
        # than a command line, so there is no shell for one to go through.
        os.execvpe(argv[0], list(argv), env)  # noqa: S606
    except BaseException as why:  # noqa: BLE001
        os.write(2, f"hmz internal fence: cannot run {argv[0]}: {why}\n".encode())
    os._exit(127)


def _waited(pid: int) -> int:
    """Waits for the program, passing on the signals meant for it; returns its wait status.

    A signal aimed at this process is aimed at the program inside: whatever asked for it -- a
    flow taking a session down, a service manager -- asked for the agent to stop, and this is
    only the wall around it. `SIGINT` is ignored rather than passed, since a ctrl-c at a
    terminal already reaches the whole group, and passing it would deliver it twice.
    """

    def passed(said: int, _frame: object) -> None:
        with contextlib.suppress(OSError):
            os.kill(pid, said)

    with contextlib.suppress(OSError, ValueError):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    for said in (signal.SIGTERM, signal.SIGQUIT, signal.SIGHUP):
        with contextlib.suppress(OSError, ValueError):
            signal.signal(said, passed)
    while True:
        try:
            # Any child rather than the program alone: an orphan handed to this subreaper is
            # collected as it exits, rather than left a zombie until the wrapper goes.
            done, status = os.waitpid(-1, 0)
        except InterruptedError:  # pragma: no cover -- retried
            continue
        except ChildProcessError:
            return 1 << 8
        if done == pid and (os.WIFEXITED(status) or os.WIFSIGNALED(status)):
            return status


def main(policy: str, argv: Sequence[str]) -> int:
    """Reads a policy and runs a program inside it, saying why where it cannot.

    Args:
      policy: The fence as JSON, or `@PATH` for a file holding it.
      argv: The program and its arguments.

    Returns:
      The program's exit status, or 126 where it was never run.
    """
    try:
        if policy.startswith("@"):
            policy = Path(policy[1:]).read_text(encoding="utf-8")
        fence = Fence.loads(policy)
        return run(fence, argv)
    except (OSError, RuntimeError, ValueError) as why:
        # Refused rather than run without it: a program the fence was meant to hold, run
        # unfenced, would be one reaching whatever it liked while the flow believed it held.
        print(f"hmz internal fence: {why}", file=sys.stderr)  # noqa: T201
        return _UNFENCED
