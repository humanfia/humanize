"""Running the harness itself somewhere other than here.

An anchored turn has two halves and they have always been in the same two places: the harness
-- the agent process and the supervisor tracing it -- here, and the work over there. That is
one arrangement of three, and the other two are what this module is.

**The harness here, the work elsewhere.** :func:`~hmz.coganchor.anchor.connect` as it stands.
Nothing in this module is reached for it.

**Both of them elsewhere.** The harness is put on the machine the work lands on and supervises
a turn that never leaves it. What crosses the link is the agent's own three streams, the same
frames a backend already speaks to a process Humanize spawns, and nothing else: no file, no
syscall, no round trip per `open`. A turn whose agent reads a thousand files reads them at
that machine's disk rather than down a wire, which is most of what an anchored turn spends.

**Each of them on a different machine elsewhere.** The harness on one, the work on another,
and Humanize on neither. This is the arrangement nothing above could express, because the two
machines have no way to reach each other: Humanize started both and can talk to both, and
that is all either of them has in common. :mod:`hmz.coganchor.rendezvous` is what it is built
on -- Humanize holds a meeting, tells each half what the other looks like from outside, and
carries the bytes itself if the two cannot be introduced.

Which of the three a session is, is a setting: :attr:`~hmz.coganchor.anchor.AnchorConfig.harness`
names where the harness runs the way `target` names where the work lands. And the whole of the
difference is in the *line*, which is what makes this a module of its own rather than a second
shape for the session to have. `hmz internal anchor` on another machine is `hmz internal
anchor`: it reads the same options, runs the same supervisor and exits with the same status,
so the layers above go on spawning one command and reading its streams and are told none of
this.

What it costs to get there is paid once. The archive is cached on the far machine by its
digest, an `ssh` to a host is opened once and ridden by every command after it, and the mirror
the harness works in is kept between turns under a name derived from what it mirrors -- so the
second turn against a workspace starts with its files already there, which is the largest
single saving available to any of this.

The CLI there runs in a virtual home as it would here (:mod:`hmz.coganchor.homes`): built on
that machine, by the anchor supervising it, from that machine's user's own configuration
(:attr:`~hmz.coganchor.anchor.AnchorConfig.home`). The flow's skills it carries are put there
first, kept between turns under that machine's cache like the archive, by what they hold.
"""

from __future__ import annotations

import hashlib
import logging
import subprocess
import threading
from dataclasses import replace
from typing import TYPE_CHECKING

from hmz.coganchor.transport import Road, Target, serve_line

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hmz.coganchor.anchor import AnchorConfig
    from hmz.coganchor.homes import Virtual
    from hmz.coganchor.rendezvous import Meeting

__all__ = ["afar", "elsewhere", "harnessed"]

log = logging.getLogger(__name__)

#: What :attr:`~hmz.coganchor.anchor.AnchorConfig.harness` says for a harness on this machine,
#: which is the arrangement Humanize has always had and the one nothing here is reached for.
HERE = "local"

#: And for a harness on whichever machine the work lands on, whatever that turns out to be.
#: A word rather than a second copy of the target, so that a flow which moves its work to
#: another machine moves the harness with it and has one thing to change rather than two.
SAME = "same"

#: Puts the flow's skills, arriving on its input as a tar, at the directory `{at}` names on the
#: harness's machine -- unless they are there already -- and prints where that is, as that
#: machine spells it. Unpacked beside it and renamed into place, so that a turn finds them whole
#: or not at all; and what no turn has carried there for a month is swept.
_CARRYING = (
    'd="{at}"; umask 077; '
    'if [ -d "$d" ]; then cat >/dev/null; touch "$d"; else '
    'mkdir -p "${{d%/*}}" && t=$(mktemp -d "$d.XXXXXX") && tar -xf - -C "$t" || exit 1; '
    'mv "$t" "$d" 2>/dev/null; rm -rf "$t" "$d/${{t##*/}}"; fi; '
    '[ -d "$d" ] || exit 1; '
    'find "${{d%/*}}" -mindepth 1 -maxdepth 1 -mtime +30 -exec rm -rf {{}} + 2>/dev/null; '
    'printf "%s\\n" "$d"'
)


def harnessed(where: str, target: str) -> Target:
    """Which machine the harness runs on, as a target of its own.

    Args:
      where: What the settings say, which is `local`, `same`, or a target spelling.
      target: Where the work lands, for the `same` that follows it.

    Returns:
      The harness's machine.

    Raises:
      ValueError: If `where` is not one of those.
    """
    return Target.parse(target if where == SAME else where)


def elsewhere(config: AnchorConfig) -> bool:
    """Whether this session's harness runs on another machine.

    Args:
      config: The settings.

    Returns:
      True if something of this module is needed to start it.
    """
    return (
        config.harness != HERE
        and harnessed(config.harness, config.target).scheme != "local"
    )


def afar(config: AnchorConfig, argv: Sequence[str]) -> list[str]:
    """The command this machine runs to have a supervised turn happen on another one.

    Everything that has to exist before the line can be run is made here: the archive is put
    on the harness's machine, so are the flow's skills the CLI's virtual home carries, and --
    where the work lands somewhere else again -- a meeting is booked and the serving half is
    started on that third machine holding a ticket to it.

    Args:
      config: The settings, whose `harness` is somewhere other than here.
      argv: The agent to run and its own arguments.

    Returns:
      The command to spawn, which carries the agent's three streams and exits with its status.

    Raises:
      ValueError: If the harness or the target cannot be read.
      ConnectionError: If the archive or the skills cannot be put on the harness's machine.
      OSError: If the serving half cannot be started where the work lands.
    """
    from hmz.coganchor.argv import options

    here = harnessed(config.harness, config.target)
    work = Target.parse(config.target)
    road = Road.to(here)
    # `harness` goes back to `local` in the same breath the target is rewritten, and not a
    # step later: by the time this line is read it *is* being read on the harness's machine,
    # and a settings object that said otherwise for an instant would be one refusing itself.
    if _one_machine(here, work):
        # Nothing is introduced and nothing crosses: the harness supervises a target that is
        # its own machine, which is a `local` target the way every stand-in for a machine is.
        inner = replace(
            config,
            harness=HERE,
            target=f"local:{config.remote_path or ''}",
            remote_path=None,
        )
        log.info("running the harness and its work on %s", here.describe())
    else:
        meeting = _booked(work, config)
        inner = replace(config, harness=HERE, target=f"peer://{meeting}")
        log.info(
            "running the harness on %s and its work on %s, met at %s:%s",
            here.describe(),
            work.describe(),
            meeting.host,
            meeting.port,
        )
    setting: list[tuple[str, str]] = []
    if not config.shadow:
        # A mirror of its own on that machine, kept between turns. It is named for what it
        # mirrors rather than for this turn, which is the point: the second turn against a
        # workspace finds its files already there. `force` because the name was derived rather
        # than chosen -- the guard on a mirror exists to stop Humanize emptying a directory
        # somebody else named, and nobody named this one.
        mirror = road.mirror(_named(config, work))
        setting.append(("HUMANIZE_SHADOW", mirror))
        inner = replace(inner, force=True)
    if inner.home is not None and inner.home.skills:
        inner = replace(inner, home=_carried(road, inner.home))
    return road.hmz(
        ["internal", "anchor", *options(inner), *argv], setting=tuple(setting)
    )


def _carried(road: Road, home: Virtual) -> Virtual:
    """The virtual home, its flow's skills put on the harness's machine and named there.

    One archive of them all, unpacked there under that machine's cache in a directory named
    for what it holds (:data:`_CARRYING`): a turn carrying the skills the last one did finds
    them there already. Links followed, since what a link points at here is not there.

    Args:
      road: The way to the harness's machine.
      home: What the CLI's virtual home is made of, its skills named as this machine has them.

    Returns:
      It, its skills named as that machine has them.

    Raises:
      ConnectionError: If they cannot be put there.
    """
    import io
    import tarfile

    packed = io.BytesIO()
    with tarfile.open(fileobj=packed, mode="w", dereference=True) as packing:
        for name, whence in home.skills:
            packing.add(whence, arcname=name)
    carried = packed.getvalue()
    at = f"{road.cache}/skills/{hashlib.sha256(carried).hexdigest()[:16]}"
    # The cache is made, and checked to be that machine's user's own where it has to be, as
    # the archive is put there.
    road.installed()
    done = road.run(["/bin/sh", "-c", _CARRYING.format(at=at)], carried)
    landed = done.stdout.decode(errors="replace").strip()
    if done.returncode != 0 or not landed.startswith("/"):
        raise ConnectionError(
            f"could not carry the flow's skills to {road.target.describe()}: "
            f"{done.stderr.decode(errors='replace').strip()}"
        )
    return replace(
        home, skills=tuple((name, f"{landed}/{name}") for name, _ in home.skills)
    )


def _one_machine(here: Target, work: Target) -> bool:
    """Whether the harness and the work are on the same machine, and so need no introduction.

    The path too, which for a container is the daemon holding it: two containers of one name
    on two daemons are two machines. And an ssh target's options, which may send one host name
    somewhere else entirely.
    """
    return (here.scheme, here.host, here.port, here.path, here.options) == (
        work.scheme,
        work.host,
        work.port,
        work.path,
        work.options,
    )


def _named(config: AnchorConfig, work: Target) -> str:
    """What to call the mirror, so that one workspace on one target has one of them.

    Neither the ticket nor anything else of this turn goes into it. A mirror named for the
    turn is a mirror thrown away after every turn, and the whole of what it is worth keeping
    for is what it already holds.
    """
    said = f"{config.workspace or ''}\0{config.remote_path or ''}\0{work.describe()}"
    return hashlib.sha256(said.encode()).hexdigest()[:16]


def _booked(work: Target, config: AnchorConfig) -> Meeting:
    """Books a meeting and leaves the serving half at it, on the machine the work lands on.

    Args:
      work: Where the work lands.
      config: The settings, for the workspace it exports and the broker it was told to use.

    Returns:
      The meeting, which the harness is about to be sent to.

    Raises:
      OSError: If the serving half cannot be started there.
    """
    from hmz.coganchor import rendezvous

    _, host, port = rendezvous.shared(config.broker)
    meeting = rendezvous.Meeting(rendezvous.ticket(), host, port)
    _, _, export = config.mount()
    started = subprocess.Popen(
        serve_line(work, [export], meeting=meeting),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
    )
    _reap(started)
    return meeting


def _reap(started: subprocess.Popen[bytes]) -> None:
    """Waits out one serving half in a thread of its own, so nothing here has to.

    A run anchoring many turns would otherwise gather a zombie per turn. One thread apiece
    and no bookkeeping beyond it: each of these ends when its session does, and one whose
    harness never arrived ends when the meeting it holds a ticket to runs out of patience.
    """
    threading.Thread(
        target=started.wait, name=f"serve-{started.pid}", daemon=True
    ).start()
