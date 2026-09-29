"""Listening on loopback only, where a fence cuts the network.

Landlock decides which TCP ports a fenced program may bind, and cannot see the address: a
program let bind a port the kernel picks could bind it on every address, listen, and be
reached from outside the machine -- a way in where the fence was to cut every way out. So
every ``bind`` and ``listen`` inside such a fence is stopped by a seccomp filter
(:func:`~hmz.coganchor.linux.seccomp.build_listen_program`) and answered by
:class:`Supervisor`, which runs in the wrapper outside the fence, beside the proxy.

``listen`` is where it is decided. The supervisor takes a duplicate of the caller's socket
with ``pidfd_getfd``, asks the socket itself what it is bound to, and -- where that is
loopback, or the socket is not an internet one -- makes the ``listen`` call on the duplicate
and answers with what it returned. The caller's call is never run: a duplicate shares the
open socket, so the socket the caller named listens, and it is the socket that was checked,
whatever the caller's threads have since done to their memory or their descriptors. A socket
bound anywhere else -- or not bound at all, which ``listen`` would bind to every address -- is
refused with `EACCES`. Nothing else can be reached from outside: the socket filter lets no
datagram socket be made, and a stream socket that does not listen accepts nothing.

``bind`` is answered early, for the error to arrive where a program expects it. The address is
read out of the caller's memory and one that is an internet address and not loopback --
`127.0.0.0/8`, `::1`, or `127.0.0.0/8` mapped into IPv6 -- is refused with `EACCES`; anything
else is let run, by the kernel and under the caller's own Landlock rules, which still decide
the port. Letting it run is not a check of what it binds -- another thread may rewrite the
address in between -- which is why ``listen`` is the one that holds.

A caller the supervisor may not look into -- one that made itself undumpable, as `ssh-agent`
does -- cannot have its socket checked, and its ``listen`` is refused. So is every call left
once the wrapper has gone: the kernel answers what nobody is listening for with `ENOSYS`. A
machine where no process may look into its children at all -- a container's default seccomp
profile, Yama at `ptrace_scope` 2 -- is one :func:`supervisable` says no for, and a fence that
cuts the network is refused there rather than put up with nothing able to listen.
"""

from __future__ import annotations

import contextlib
import ctypes
import errno
import ipaddress
import logging
import os
import select
import socket
import sys
import threading
from pathlib import Path
from typing import Final

from hmz.coganchor.linux import procfs, seccomp
from hmz.coganchor.linux.syscalls import NR

__all__ = ["Supervisor", "loopback", "supervisable"]

log = logging.getLogger(__name__)

_libc = ctypes.CDLL(None, use_errno=True)
_libc.syscall.restype = ctypes.c_long

#: ``sizeof(struct sockaddr_storage)``: the most ``bind`` takes and ``getsockname`` gives.
_SOCKADDR: Final = 128
#: ``sizeof(struct sockaddr_in)`` and ``SIN6_LEN_RFC2133``: the least each family's ``bind``
#: takes, and so the least an address of it is read from.
_INET: Final = 16
_INET6: Final = 24

#: ``PIDFD_THREAD``, which is ``O_EXCL``: a pidfd on the one thread rather than its process.
_PIDFD_THREAD: Final = os.O_EXCL

_YAMA: Final = "/proc/sys/kernel/yama/ptrace_scope"


def loopback(sockaddr: bytes) -> bool | None:
    """Whether a socket address is on loopback, or not an internet address at all.

    Args:
      sockaddr: The address as the kernel lays it out: the family in the machine's own byte
        order, then the family's own fields.

    Returns:
      True for an IPv4 or IPv6 address on loopback, IPv4 loopback mapped into IPv6 included;
      False for any other internet address, one too short to be one, and ``AF_UNSPEC``, which
      an IPv4 ``bind`` takes to mean every address; and None for every other family -- a Unix
      socket's path, a netlink address -- which reaches nothing past this machine and is not
      this module's to judge.
    """
    if len(sockaddr) < 2:  # noqa: PLR2004 -- `sa_family_t`
        return None
    family = int.from_bytes(sockaddr[:2], sys.byteorder)
    if family == socket.AF_UNSPEC:
        return False
    if family == socket.AF_INET:
        return (
            len(sockaddr) >= _INET and ipaddress.IPv4Address(sockaddr[4:8]).is_loopback
        )
    if family == socket.AF_INET6:
        if len(sockaddr) < _INET6:
            return False
        address = ipaddress.IPv6Address(sockaddr[8:24])
        return (address.ipv4_mapped or address).is_loopback
    return None


def supervisable() -> bool:
    """Whether this process may take a descriptor out of a process it started.

    What :class:`Supervisor` does with every ``listen``, and what a container's default seccomp
    profile refuses outright, as does Yama at `ptrace_scope` 2 and above for every process but
    one's own. Asked of this process itself, which the first answers the same as any other.

    Returns:
      Whether ``pidfd_getfd`` works here and Yama lets a parent reach into its descendants.
    """
    with contextlib.suppress(OSError, ValueError):
        if int(Path(_YAMA).read_text(encoding="ascii")) >= 2:  # noqa: PLR2004
            return False
    try:
        pidfd = os.pidfd_open(os.getpid())
    except OSError:
        return False
    try:
        held = _getfd(pidfd, pidfd)
    finally:
        os.close(pidfd)
    if held < 0:
        return False
    os.close(held)
    return True


def _getfd(pidfd: int, fd: int) -> int:
    """``pidfd_getfd``: a descriptor of this process's on another's, or the negated errno."""
    ctypes.set_errno(0)
    held = int(_libc.syscall(NR.PIDFD_GETFD, pidfd, fd, 0))
    return held if held >= 0 else -ctypes.get_errno()


def _pidfd(tid: int) -> int:
    """A pidfd on a thread whose descriptors are the ones it names by number.

    That thread itself where the kernel opens one on a thread (6.9 on, ``PIDFD_THREAD``), and
    its thread group otherwise -- which is the same table of descriptors for every thread that
    did not ask for one of its own.
    """
    with contextlib.suppress(OSError):
        return os.pidfd_open(tid, _PIDFD_THREAD)
    with Path(f"/proc/{tid}/status").open("rb") as status:
        said = status.read(4096).decode("ascii", "replace")
    tgid = next(
        (line.split()[1] for line in said.splitlines() if line.startswith("Tgid:")),
        str(tid),
    )
    return os.pidfd_open(int(tgid))


class Supervisor:
    """The thread that answers every ``bind`` and ``listen`` a fenced program makes.

    Started on the listener descriptor the child handed over, and stopped once the program
    has exited. Every call it receives it answers, whatever goes wrong in between -- a caller
    left stopped would be a program hung on a call nobody sees. The descriptor is closed as
    the thread ends, however it ends, and from then on the kernel answers every call with
    `ENOSYS` rather than leave one stopped.

    Args:
      listener: The filter's listener descriptor, which this closes when it stops.
    """

    def __init__(self, listener: int) -> None:
        self._listener = listener
        self._wake, self._woken = os.pipe()
        self._thread = threading.Thread(
            target=self._serve, name="fence-listen", daemon=True
        )

    def start(self) -> None:
        """Starts answering."""
        self._thread.start()

    def stop(self) -> None:
        """Stops answering and lets the descriptor go; the calls still to come get `ENOSYS`."""
        with contextlib.suppress(OSError):
            os.write(self._woken, b"!")
        if self._thread.ident is None:  # never started, so nothing else will close it
            os.close(self._listener)
        else:
            self._thread.join()
        for fd in (self._wake, self._woken):
            with contextlib.suppress(OSError):
                os.close(fd)

    def _serve(self) -> None:
        try:
            self._answering()
        except Exception:
            log.exception("the fence stopped answering its binds")
        finally:
            os.close(self._listener)

    def _answering(self) -> None:
        polled = select.poll()
        polled.register(self._listener, select.POLLIN)
        polled.register(self._wake, select.POLLIN)
        while True:
            ready = dict(polled.poll())
            if self._wake in ready:
                return
            said = ready.get(self._listener, 0)
            if said & (select.POLLHUP | select.POLLERR | select.POLLNVAL):
                return  # every process the filter held is gone
            if not said & select.POLLIN:
                continue
            try:
                call = seccomp.receive(self._listener)
            except OSError as why:
                if why.errno in (errno.ENOENT, errno.EINTR):
                    continue
                raise
            self._answer(call)

    def _answer(self, call: seccomp.Notification) -> None:
        try:
            if call.nr == NR.LISTEN:
                done = self._listen(call)
            elif call.nr == NR.BIND:
                done = self._bind(call)
            else:
                done = -errno.ENOSYS
        # Everything, deliberately: whatever went wrong, the caller is answered, and with the
        # answer that lets nothing through.
        except Exception:
            log.exception("the fence could not decide a %d", call.nr)
            done = -errno.EACCES
        with contextlib.suppress(OSError):  # the caller has gone, or was interrupted
            if done is None:
                seccomp.respond(self._listener, call.id, go=True)
            elif done < 0:
                seccomp.respond(self._listener, call.id, error=-done)
            else:
                seccomp.respond(self._listener, call.id, value=done)

    def _bind(self, call: seccomp.Notification) -> int | None:
        """``bind(fd, addr, len)``: refused where the address is off loopback, else run."""
        _, at, length = call.args[:3]
        length = ctypes.c_int32(length).value
        if not 0 <= length <= _SOCKADDR:
            return None  # the kernel refuses it, having read nothing
        try:
            address = procfs.read_bytes(call.pid, at, length)
        except OSError:
            # Not readable, as the kernel will find it too, or not by this process; `listen`
            # is what holds either way.
            return None
        if not seccomp.valid(self._listener, call.id):
            return None  # read from whatever has the pid now; the answer reaches nobody
        return -errno.EACCES if loopback(address) is False else None

    def _listen(self, call: seccomp.Notification) -> int:
        """``listen(fd, backlog)``: made here, on the socket itself, where it is on loopback."""
        fd, backlog = (ctypes.c_int32(one).value for one in call.args[:2])
        pidfd = _pidfd(call.pid)
        try:
            if not seccomp.valid(self._listener, call.id):
                return -errno.ESRCH  # not the process it was; the answer reaches nobody
            held = _getfd(pidfd, fd)
        finally:
            os.close(pidfd)
        if held < 0:
            return held if held == -errno.EBADF else -errno.EACCES
        try:
            name = ctypes.create_string_buffer(_SOCKADDR)
            size = ctypes.c_uint32(_SOCKADDR)
            ctypes.set_errno(0)
            if _libc.getsockname(held, name, ctypes.byref(size)) != 0:
                return -ctypes.get_errno()
            if loopback(name.raw[: min(size.value, _SOCKADDR)]) is False:
                return -errno.EACCES
            ctypes.set_errno(0)
            if _libc.listen(held, backlog) != 0:
                return -ctypes.get_errno()
            return 0
        finally:
            os.close(held)
