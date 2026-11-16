"""The `coganchor cog` line, written out from the settings a session runs under.

`coganchor cog` takes the options `hmz internal anchor` always took and reads them into the
same settings; :meth:`~hmz.coganchor.anchor.AnchorConfig.command` renders a turn as that line
for a process of its own, so a setting that :func:`options` does not write is one a spawned
turn silently loses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from .anchor import AnchorConfig

__all__ = ["forget", "kept", "options", "render"]


def render(config: AnchorConfig, argv: Sequence[str]) -> list[str]:
    """Writes the settings back out as the `coganchor cog` line that would read as them.

    Args:
      config: The settings to run the agent under.
      argv: The agent to run and its own arguments.

    Returns:
      The command to spawn, which exits with the agent's own status.

    Raises:
      FileNotFoundError: Where there is no `coganchor` for this machine.
    """
    from hmz.coganchor import binary

    return [str(binary.here()), "cog", *options(config), *argv]


def options(config: AnchorConfig) -> list[str]:
    """The settings as the options that read back as them, with nothing in front.

    The half of :func:`render` that says nothing about *where* the line runs, which is what a
    harness on another machine needs: the same options reach it, in front of the same
    subcommand, behind whatever that machine runs Humanize as.

    Args:
      config: The settings to write out.

    Returns:
      One option per setting that is not its default.
    """
    # Joined to their flag rather than following it, so that a setting reading as an option
    # of ours -- a token that happens to start with a dash -- is still its value.
    written = [f"--target={config.target}", f"--net={config.net}"]
    for flag, value in (
        ("--workspace", config.workspace),
        ("--chdir", config.chdir),
        ("--remote-path", config.remote_path),
        ("--shadow", config.shadow),
        # By the file it is kept in, never by itself: a command line is in every user's `ps`.
        ("--token-file", kept(config.token) if config.token is not None else None),
        # Written only where there is one, unlike the two above: each defaults to "" rather
        # than to None, and an empty line would read as a CLI nothing installs.
        ("--installs", config.installs or None),
        ("--broker", config.broker or None),
        ("--fence", config.fence.dumps() if config.fence is not None else None),
        ("--home", config.home.dumps() if config.home is not None else None),
    ):
        if value is not None:
            written.append(f"{flag}={value}")
    # Not written where it is the default, so that the line a harness here is spawned with is
    # the line it always was -- and a harness elsewhere is handed `local`, since by the time
    # the line reaches that machine it is the machine the harness runs on.
    if config.harness != "local":
        written.append(f"--harness={config.harness}")
    for flag, values in (
        ("--local-path", config.local_paths),
        ("--local-exec", config.local_execs),
        ("--net-allow", config.net_allow),
        ("--hush", config.hushes),
    ):
        written += [f"{flag}={value}" for value in values]
    for flag, pairs in (
        ("--redirect", config.redirects),
        ("--project", config.projects),
        ("--bring", config.brings),
    ):
        written += [f"{flag}={one}={other}" for one, other in pairs]
    written += [f"--private={name}" for name in config.private]
    if config.tells:
        written.append(f"--tell={config.tells}")
    if config.force:
        written.append("--force")
    if config.native:
        written.append("--native")
    return written


def kept(token: str) -> str:
    """The file a secret is kept in for a command line to name, written where it is not yet.

    Among what is this machine's and this user's alone, named by the secret's digest -- so a
    secret written down once is the same file however many lines name it -- and readable by
    nobody else from the instant it exists.

    Args:
      token: The secret.

    Returns:
      The file's path.
    """
    import os

    at = _keeping(token)
    if not at.exists():
        at.parent.mkdir(mode=0o700, exist_ok=True)
        staged = at.with_name(f".{at.name}.{os.getpid()}")
        made = os.open(staged, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(made, token.encode())
        finally:
            os.close(made)
        staged.replace(at)
    return str(at)


def forget(token: str) -> None:
    """Removes the file a secret was kept in, for one nothing will be asked for again."""
    _keeping(token).unlink(missing_ok=True)


def _keeping(token: str) -> Path:
    """Where :func:`kept` keeps a secret, whether or not it is there yet."""
    import hashlib

    from hmz import machine

    return machine() / "tokens" / hashlib.sha256(token.encode()).hexdigest()[:32]
