"""A project's own configuration that would start programs on a machine that is not its own.

A CLI reads settings out of the project it works in, and some of them are programs: a hook, an
MCP server it spawns, a helper it asks for a key, a plugin it loads. The CLI starts each of
them where the CLI itself runs. Run on the work's own machine -- here for work here, on the
target for a native turn, or under a harness put on the target itself -- that is the machine
the project is on, and starting what the project names is what that project already asked of
its own machine. Run anywhere else -- here, in a mirror of work on another machine, or under a
harness put on a third -- it is a program a project on one machine starts on another, which
nobody on that other machine agreed to.

So a session whose CLI runs apart from its work is refused where the work's project holds
any such thing, before a turn has started it. What counts is written down per CLI, as
:attr:`~hmz.coganchor.backends.Profile.launchers`, and read here off the work's own machine.
"""

from __future__ import annotations

import errno
import io
import os
import tomllib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from hmz.coganchor.anchor import AnchorConfig
    from hmz.coganchor.backends import Launcher

__all__ = ["apart", "found", "held", "refuse"]

#: What a read that found nothing to read says.
_ABSENT = (errno.ENOENT, errno.ENOTDIR, errno.EISDIR)


def apart(config: AnchorConfig) -> bool:
    """Whether a CLI whose turns land where `config` says runs on another machine than they do.

    Not for a native turn, the CLI being the target's own; nor for a harness put on the
    target itself. For every other: a supervised turn's CLI is here, the work there, and a
    harness put on a third machine is on neither.

    Args:
      config: Where the turns land, and where their harness runs.

    Returns:
      Whether the two are two machines.
    """
    from hmz.coganchor.elsewhere import elsewhere, harnessed
    from hmz.coganchor.transport import Target

    if config.native:
        return False
    if not elsewhere(config):
        return True
    return harnessed(config.harness, config.target) != Target.parse(config.target)


def held(
    launchers: Sequence[Launcher], read: Callable[[str], bytes | None]
) -> list[str]:
    """What of a project's own configuration would start a program, read off its files.

    Args:
      launchers: What the CLI reads that could, as its profile says.
      read: The content of one of those files by its path relative to the project, or None
        where there is no such file -- or, for a path ending in `/`, anything but None where
        that directory holds something. ValueError for one that is there and cannot be
        read.

    Returns:
      Each file and key that would, in words, in the order they are written down -- a file
      that cannot be read as its kind among them, since whether it would cannot be told.
    """
    said: list[str] = []
    for launcher in launchers:
        try:
            content = read(launcher.path)
        except ValueError:
            said.append(f"{launcher.path} (unreadable)")
            continue
        if content is None:
            continue
        if not launcher.keys:
            said.append(launcher.path)
            continue
        try:
            parsed = _parsed(launcher.path, content)
        except ValueError:
            said.append(f"{launcher.path} (unreadable)")
            continue
        said.extend(
            f"{launcher.path}: {key}" for key in launcher.keys if _holds(parsed, key)
        )
    return said


def found(
    config: AnchorConfig, launchers: Sequence[Launcher], cwd: str | None
) -> list[str]:
    """What of the work's project would start a program, read off the work's own machine.

    Looked for in the directory a session works in and in every one above it up to the
    workspace, which is where the CLIs that walk up for their project's settings stop.

    Args:
      config: Where the work lands.
      launchers: What the CLI reads that could.
      cwd: The directory the session works in, as the target names it, or None for the
        workspace.

    Returns:
      Each directory's findings, in words, the directory named where it is not the
      workspace.

    Raises:
      ValueError: If the target cannot be read.
      OSError: If it cannot be reached.
    """
    if not launchers:
        return []
    from hmz.coganchor import transport
    from hmz.coganchor.proto import ProtocolError, RemoteOSError
    from hmz.coganchor.remote import RemoteClient

    target, workspace, export = config.mount()
    where = os.path.abspath(cwd) if cwd is not None else workspace  # noqa: PTH100
    said: list[str] = []
    link = transport.connect(target, [export], config.token)
    client = RemoteClient(link.channel)
    try:
        try:
            client.start(config.token)
        except ProtocolError as why:
            raise ConnectionError(f"{config.target}: {why}") from why

        def read(path: str) -> bytes | None:
            sink = io.BytesIO()
            try:
                if path.endswith("/"):
                    # A directory of programs, which is there when anything is in it.
                    listed = client.listdir(path.rstrip("/"))["entries"]
                    return b"" if listed else None
                client.read_file(path, sink)
            except RemoteOSError as why:
                # The target answered, and said why: nothing there, or something there
                # nobody here may read -- which may say anything, and is taken to.
                if why.errno in _ABSENT:
                    return None
                raise ValueError(why.strerror) from why
            return sink.getvalue()

        for directory in _upward(where, workspace):
            named = os.path.relpath(directory, workspace)
            said.extend(
                one if named == "." else f"{named}/{one}"
                for one in held(
                    launchers,
                    lambda path, at=directory: read(os.path.join(at, path)),  # noqa: PTH118
                )
            )
    finally:
        client.close()
        link.close()
    return said


def refuse(
    config: AnchorConfig, launchers: Sequence[Launcher], cwd: str | None, cli: str
) -> None:
    """Refuses a session whose CLI runs apart from its work, where the work would start one.

    Args:
      config: Where the session's turns land, and where their harness runs.
      launchers: What the CLI reads that could start a program.
      cwd: The directory it works in, as the target names it, or None for the workspace.
      cli: What the CLI is called, for the refusal.

    Raises:
      NotImplementedError: If the CLI runs apart from the work, and the work's project
        configuration would start a program: what this CLI cannot do there.
      ValueError: If the target cannot be read.
      OSError: If it cannot be reached.
    """
    if not apart(config):
        return
    said = found(config, launchers, cwd)
    if said:
        raise NotImplementedError(
            f"{cli} runs on another machine than its work on {config.target}, and the "
            f"project's own configuration there would have it start programs on {cli}'s "
            f"machine rather than the work's: {'; '.join(said)}. Run it natively on "
            f"{config.target}, or take those out of the project"
        )


def _upward(where: str, workspace: str) -> list[str]:
    """`where` and every directory above it up to `workspace`; none outside it."""
    if where != workspace and not where.startswith(workspace + os.sep):
        return []
    found_: list[str] = []
    while True:
        found_.append(where)
        if where == workspace:
            return found_
        where = os.path.dirname(where)  # noqa: PTH120


def _parsed(path: str, content: bytes) -> Any:
    """A configuration file's content, as its kind is read.

    Raises:
      ValueError: If it is not that kind.
    """
    if path.endswith(".toml"):
        return tomllib.loads(content.decode())
    if path.endswith((".yml", ".yaml")):
        import yaml

        try:
            return yaml.safe_load(content.decode())
        except yaml.YAMLError as why:
            raise ValueError(str(why)) from why
    # JSON with comments and trailing commas, as most of these CLIs read their JSON: a file
    # one of them reads that this could not would be one whose hooks went unseen.
    import json5

    return json5.loads(content.decode())


def _holds(parsed: object, key: str) -> bool:
    """Whether a parsed file holds something at a dotted key path."""
    level = [parsed]
    for part in key.split("."):
        deeper: list[object] = []
        for one in level:
            if isinstance(one, dict):
                table: dict[str, object] = one  # pyright: ignore[reportUnknownVariableType]
                if part == "*":
                    deeper.extend(table.values())
                elif part in table:
                    deeper.append(table[part])
            elif isinstance(one, list) and part == "*":
                deeper.extend(one)  # pyright: ignore[reportUnknownArgumentType]
        level = deeper
    return any(_something(one) for one in level)


def _something(value: object) -> bool:
    """Whether a setting says anything: not null or false, nor an empty string, table or list."""
    if value is None or value is False:
        return False
    if isinstance(value, (str, list, dict)):
        return bool(value)  # pyright: ignore[reportUnknownArgumentType]
    return True
