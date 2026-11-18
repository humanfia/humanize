"""The envs of an epic, as a client of the daemon reads, writes, searches and runs commands in them.

`hosts.env.list`, `hosts.env.read`, `hosts.env.write`, `hosts.env.exec` and `hosts.env.grep`
(Section 4.23 of daemon.md): each carried out by the host going with the epic, through the env's
own driver on the run's own loop, as the epic's flow would carry it out, without the flow
hearing of it and without attaching. Each env is one the run holds at its root -- a role's,
two roles of one driver each an env of its own, or the workspace no role took; what is here is
the work done in it, which :meth:`hmz.runtime.Host.env` asks for.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import posixpath
import time
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

    from hmz.runtime.flowing.spi import EnvDriver

__all__ = ["NO_FLOW", "EnvRefusal", "answered", "carried", "listed"]

#: How a host with no epic going refuses each of them.
NO_FLOW = "no flow is running, so no env is open"

#: The most of a file `hosts.env.read` reads, and of a stream `hosts.env.exec` answers, in bytes.
_MOST = 1 << 20

#: Where a line `hosts.env.grep` answers is cut, in characters.
_LINE = 400

#: Searches as `hosts.env.grep` does, with no more lines than `$3`, grep alone being unable to
#: stop early; then says grep's own exit status as the last line of stderr.
_GREP = '{ grep -rnIsE --null -e "$1" -- "$2"; echo "$?" >&2; } | head -n "$3"'

#: Says the workdir with every link followed, then the deepest of `$1` and the directories it
#: lies in that is there, likewise: where a path is, said on the env's own machine.
_REAL = (
    'pwd -P && p=$1 && while [ "$p" != . ] && [ ! -e "$p" ] && [ ! -L "$p" ]; '
    'do p=$(dirname -- "$p"); done && readlink -f -- "$p"'
)

#: How long an env's driver may take over anything but a command, in seconds.
_PATIENCE = 120


class EnvRefusal(Exception):  # noqa: N818 -- a refusal, said as the protocol says it
    """A call of Section 4.23 refused, with the code and the words it is refused with."""

    def __init__(self, code: int, why: str) -> None:
        super().__init__(why)
        self.code = code
        self.why = why


def _can(driver: EnvDriver) -> list[str]:
    """What an env offers of `read`, `write`, `exec` and `grep`."""
    from hmz.flows import FilesEnvMixin, ShellEnvMixin

    has = driver.capabilities
    files, shell = FilesEnvMixin in has, ShellEnvMixin in has
    return [
        what
        for what, offered in (
            ("read", files),
            ("write", files),
            ("exec", shell),
            ("grep", shell),
        )
        if offered
    ]


def listed(envs: Mapping[str, EnvDriver]) -> list[dict[str, Any]]:
    """`hosts.env.list`'s `envs`: each env role of the epic, its kind, workdir and offers."""
    return [
        {
            "name": name,
            "kind": str(driver.backend),
            "workdir": str(driver.workdir),
            "can": _can(driver),
        }
        for name, driver in envs.items()
    ]


def _text_of(data: bytes) -> str:
    """Bytes as `hosts.env.read` reads them: UTF-8, every byte that is not replaced by U+FFFD."""
    return data.decode(errors="replace")


def _under(path: str, workdir: str) -> bool:
    return path == workdir or path.startswith(workdir.rstrip("/") + "/")


async def _inside(driver: EnvDriver, env: str, path: str) -> str:
    """A `path` as the env's driver is given it, relative to its workdir.

    Raises:
      EnvRefusal: 400 where it leaves the workdir, by `..`, as an absolute path outside it,
        or through a symbolic link: followed here for an env on this machine, and on its own
        machine for one elsewhere that runs commands.
    """
    workdir = str(driver.workdir)
    whole = posixpath.normpath(posixpath.join(workdir, path))
    outside = EnvRefusal(400, f"{path} is outside the env {env}.")
    if not _under(whole, workdir):
        raise outside
    relative = posixpath.relpath(whole, workdir)
    if str(driver.backend) == "local":
        found = os.path.realpath(whole)  # noqa: ASYNC240 -- a moment's look at this machine
        if not _under(found, os.path.realpath(workdir)):  # noqa: ASYNC240 -- likewise
            raise outside
    elif "exec" in _can(driver):
        code, said, _ = await driver.exec(
            ["sh", "-c", _REAL, "sh", relative], timeout=_PATIENCE
        )
        real, _, found = said.strip().partition("\n")
        if code == 0 and found and not _under(found, real):
            raise outside
    return relative


def _file(driver: EnvDriver, relative: str) -> str:
    """A file `_inside` the workdir, as the driver reads and writes it there.

    A driver takes a path that begins `~` from its machine's home, so one that does is given
    under the workdir's own path, which is absolute or begins `~` itself.
    """
    if relative.split("/", 1)[0] == "~":
        return posixpath.join(str(driver.workdir), relative)
    return relative


def _number(
    said: Mapping[str, Any], key: str, default: int, least: int, most: int
) -> int:
    """An integer param, `default` where it is not given.

    Raises:
      EnvRefusal: -32602 where it is outside `least` to `most`.
    """
    value = said.get(key)
    if value is None:
        return default
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not least <= value <= most
    ):
        raise EnvRefusal(
            -32602,
            f"{said.get('do')!s} takes {key} as an integer from {least} to {most}.",
        )
    return value


async def _read(driver: EnvDriver, env: str, said: Mapping[str, Any]) -> dict[str, Any]:
    from hmz.flows import EnvFileNotFound

    path = str(said["path"])
    offset = _number(said, "offset", 0, 0, 1 << 62)
    length = _number(said, "length", _MOST, 1, _MOST)
    try:
        data = await driver.read(_file(driver, await _inside(driver, env, path)))
    except EnvFileNotFound:
        raise EnvRefusal(404, f"There is no file {path} in {env}.") from None
    return {
        "text": _text_of(data[offset : offset + length]),
        "size": len(data),
        "eof": offset + length >= len(data),
    }


async def _write(
    driver: EnvDriver, env: str, said: Mapping[str, Any]
) -> dict[str, Any]:
    data = str(said["text"]).encode()
    await driver.write(
        _file(driver, await _inside(driver, env, str(said["path"]))), data
    )
    return {"size": len(data)}


def _tail(text: str) -> str:
    """The last of a stream a command wrote, as `hosts.env.exec` answers it."""
    return _text_of(text.encode(errors="replace")[-_MOST:])


async def _exec(driver: EnvDriver, env: str, said: Mapping[str, Any]) -> dict[str, Any]:
    from hmz.flows import EnvCommandTimeout

    del env
    argv = [str(one) for one in said.get("argv") or ()]
    if not argv:
        raise EnvRefusal(400, "hosts.env.exec runs a command: give argv.")
    seconds = _number(said, "seconds", 120, 1, 3600)
    try:
        code, stdout, stderr = await driver.exec(argv, timeout=seconds)
    except EnvCommandTimeout as late:
        code, stdout, stderr = None, late.stdout, late.stderr
    return {"code": code, "stdout": _tail(stdout), "stderr": _tail(stderr)}


async def _grep(driver: EnvDriver, env: str, said: Mapping[str, Any]) -> dict[str, Any]:
    pattern = str(said["pattern"])
    limit = _number(said, "limit", 200, 1, 2000)
    under = await _inside(driver, env, str(said.get("path") or "."))
    _, stdout, stderr = await driver.exec(
        ["sh", "-c", _GREP, "sh", pattern, under, str(limit + 1)], timeout=_PATIENCE
    )
    said_, _, status = stderr.rstrip("\n").rpartition("\n")
    if status.strip() not in ("0", "1") and not stdout and said_.strip():
        # Every unreadable file is silenced: what grep says is of the pattern it was given.
        raise EnvRefusal(400, said_.strip())
    matches: list[dict[str, Any]] = []
    for one in stdout.split("\n"):
        path, _, rest = one.partition("\0")
        line, _, text = rest.partition(":")
        if line.isdigit():
            matches.append(
                {
                    "path": posixpath.normpath(path),
                    "line": int(line),
                    "text": text[:_LINE],
                }
            )
    return {"matches": matches[:limit], "more": len(matches) > limit}


#: What each method but `env.list` needs of the env, as it is refused without, and does.
_DOES = {
    "hosts.env.read": ("read", "read files", _read),
    "hosts.env.write": ("write", "write files", _write),
    "hosts.env.exec": ("exec", "run commands", _exec),
    "hosts.env.grep": ("grep", "search files", _grep),
}


async def carried(
    method: str, envs: Mapping[str, EnvDriver], said: Mapping[str, Any]
) -> dict[str, Any]:
    """Carries out one call of Section 4.23 on the env it names, and answers its result.

    Args:
      method: Which: `hosts.env.read`, `hosts.env.write`, `hosts.env.exec` or
        `hosts.env.grep`.
      envs: The driver of each env role of the epic going, by role.
      said: The call's params.

    Raises:
      EnvRefusal: As Section 4.23 refuses it.
      EnvError: What the env could not do, as its driver raised it.
    """
    env = str(said.get("env") or "")
    driver = envs.get(env)
    if driver is None:
        raise EnvRefusal(404, f"The epic has no env {env}.")
    needs, what, does = _DOES[method]
    if needs not in _can(driver):
        raise EnvRefusal(409, f"The env {env} cannot {what}.")
    return await does(driver, env, said)


class Holds(Protocol):
    """A run going, as far as `hosts.env.*` go: its envs by name, and the loop they live on."""

    @property
    def loop(self) -> asyncio.AbstractEventLoop: ...

    def env_roles(self) -> Mapping[str, EnvDriver]:
        """The driver of each env it holds at its root, by name. From any thread."""
        ...


def answered(holds: Holds, said: Mapping[str, Any]) -> dict[str, Any]:
    """Carries out one call of Section 4.23 on what a run going holds, from any other thread.

    Args:
      holds: The run, as its engine holds it: its envs, and the loop their drivers live on.
      said: The call: `do`, the method's whole name, and its params.

    Raises:
      EnvRefusal: As Section 4.23 refuses it; 409 where the run's loop has ended.
      EnvError: What the env could not do, as its driver raised it.
    """
    envs = holds.env_roles()
    method = str(said.get("do"))
    if method == "hosts.env.list":
        return {"envs": listed(envs)}
    # A command's own time, and a moment for its env to be reached: then given up on.
    until = (
        time.monotonic()
        + _PATIENCE
        + (_number(said, "seconds", 120, 1, 3600) if method == "hosts.env.exec" else 0)
    )
    loop = holds.loop
    work = carried(method, envs, said)
    try:
        done = asyncio.run_coroutine_threadsafe(work, loop)
    except RuntimeError:  # the loop has closed
        work.close()
        raise EnvRefusal(409, NO_FLOW) from None
    while True:
        try:
            return done.result(timeout=0.25)
        except concurrent.futures.TimeoutError:
            if loop.is_closed() or not loop.is_running():
                done.cancel()
                raise EnvRefusal(409, NO_FLOW) from None
            if time.monotonic() > until:
                done.cancel()
                raise EnvRefusal(
                    409, f"The env {said.get('env')} did not answer in time."
                ) from None
        except concurrent.futures.CancelledError:
            raise EnvRefusal(409, NO_FLOW) from None
