"""Anchoring an agent to the machine its work lands on, both ways round.

Where a session is said in Python: the settings, the two calls that run one, and the call
that only asks the target what it is.

The two are opposites and the settings are shared. :func:`connect` keeps the agent here and
answers everything it does from the target -- a mirror of the workspace, a supervisor, a
syscall at a time. :func:`drive` keeps nothing here: the CLI already installed on the target
is the one that runs, and this process carries its streams. Which to use is a fact about the
anchor rather than about the machine, so it is a setting and
:attr:`AnchorConfig.capabilities` is what says it out loud.

Both are carried out by `coganchor cog`, the line :meth:`AnchorConfig.command` renders; what is
here is the front door that renders it, spawns it and waits for it.
"""

from __future__ import annotations

import contextlib
import errno
import logging
import os
import subprocess
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from .places import AFAR, NATIVE_CLI, SUPERVISED

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

    from hmz.coganchor.fence import Fence
    from hmz.coganchor.homes import Virtual
    from hmz.coganchor.remote import RemoteClient
    from hmz.coganchor.transport import Target

__all__ = ["AnchorConfig", "NotInstalled", "Unmirrored", "check", "connect", "drive"]

log = logging.getLogger(__name__)


class NotInstalled(FileNotFoundError):  # noqa: N818 -- what it is, not what went wrong
    """The CLI a native turn was to run is not on the target.

    Its own kind rather than the bare `FileNotFoundError` it is one of, because what is done
    about it is particular: it is the one failure that means *install this there*, and the one
    a command line answers with the status a shell uses for a command it could not find.
    Every other missing file on the way to a turn -- a workspace the target has not got, an
    `ssh` this machine has not got -- is a different thing gone wrong and must not be read as
    this one.
    """


class Unmirrored(OSError):  # noqa: N818 -- what it is, not what went wrong
    """The copy of the target's workspace kept on this machine could not be made where it goes.

    Its own kind, and its own words, because what went wrong is this machine's filesystem
    rather than anything the turn was to reach: a path that may not be created here, or one
    that is not a directory. Said as the error underneath says it, a path
    that may not be created reads `Permission denied` -- which is also what a credential
    that was refused reads, and a person sent to sign an account in again is a person sent
    to fix something that was never broken.
    """


#: What a copy of the workspace that could not be made is said as, which is also what a
#: turn that failed for one is known by (:data:`hmz.coganchor.backends.SIGNS`).
UNMIRRORED = "cannot keep the local copy of the work at"


@dataclass(frozen=True, kw_only=True, slots=True)
class AnchorConfig:
    """Where an agent's work lands, and what of it stays on this machine.

    Attributes:
      target: The machine the work lands on, as `ssh://HOST`, `docker://CONTAINER` -- or
        `docker://CONTAINER@ENDPOINT` for a container held by a daemon other than docker's
        default here, and `docker://CONTAINER?user=UID[:GID]&env=NAME=VALUE&exec=WORD` for
        the user, the variables and the wrapper its commands run as, with and under --
        `apple-container://CONTAINER` for an Apple container of this Mac,
        `tcp://HOST:PORT`, `peer://TICKET@HOST:PORT` or `local[:DIR]`, where a local target
        stands in for a remote one.
      harness: Where the agent process and the supervisor tracing it run: `local` for this
        machine, `same` for whichever machine `target` names, or a target spelling of their
        own. The three arrangements anchoring has, said in one setting --
        :mod:`hmz.coganchor.elsewhere` is what the two that are not `local` are made of, and
        what each of them is for.
      broker: Where the two halves are introduced, when `harness` and `target` are two
        different machines and neither can dial the other. Empty asks this machine which of
        its addresses faces outward, which is right wherever the two are on the same network
        as this one; a machine they reach Humanize by some other name at says that name here.
      chdir: Where inside that workspace the agent starts, as the target names it, or None
        for the workspace itself. What a session opened at a directory of its own comes to:
        the agent is put in this machine's mirror of it, and what it does there lands there.
      workspace: The project directory as it exists on the target, defaulting to this one.
      remote_path: Where that workspace really lives on the target, if not `workspace`.
      shadow: The mirror directory on whichever machine the harness runs on, defaulting to
        `workspace` so that the paths the agent sees are the target's own. A harness
        elsewhere that was given none is put in one under that machine's own cache, named for
        what it mirrors and kept between turns.
      local_paths: Paths to keep on this machine even when they are inside the workspace.
      local_execs: Paths whose programs run here rather than on the target.
      private: Variables of the agent's own that must not cross to the target: a credential it
        was given to reach its model provider is the agent's business and not the target's, and
        everything else it exports reaches every command it runs there.
      redirects: Paths this session answers with others, as `(what the agent names, what it
        gets)`. A directory stands for everything inside it, and what a path is answered with
        is kept on this machine like any other state of the agent's own. This is how a turn
        runs as a provider's account: a process has one tracer, so an anchored session
        answers for the credentials itself rather than nesting a supervisor inside this one.
      net: Where the agent's own connections go: `local`, so that its model provider stays
        reachable, or `remote`. What it spawns always uses the target's network.
      net_allow: Hosts to keep local anyway when `net` is remote, as `HOST[:PORT]`.
      token: The shared secret a `tcp://` target expects. A spawned session falls back to
        `$HUMANIZE_TOKEN` when this is None, the way the command line does.
      force: Whether to use a mirror directory that already holds unrelated files.
      native: Whether the agent's own CLI is the one already installed on the target, driven
        there. The other arrangement, and the opposite of everything above it: there is no
        mirror, no supervisor and no tracing, because there is no local process to trace --
        the CLI runs on the target, in the target's own copy of the workspace, and this
        machine carries its three streams and its exit status and nothing else. Which is why
        the settings above that describe the mirror -- `shadow`, `local_paths`, `local_execs`,
        `redirects`, `net`, `net_allow` -- say nothing here: each of them is an answer about a
        local process, and there is none.
      hushes: Variables the turn is run without on the target, whoever left them there. The
        other half of what `private` is under a supervisor: a key exported in the target's own
        shell profile outranks the account the turn was given, and a turn that ran -- and
        billed -- as that key would look like nothing was wrong.
      projects: Credentials to put on the target for the length of the turn, as
        `(variable, the directory on this machine holding it)`. Each is written into a
        directory only the target's own user may enter, taken away when the turn is over, and
        named to the CLI by setting that variable to where it landed. Never by argv: what is
        in a command line is in another user's `ps`. A file holding a refresh token is out to
        one turn at a time, and what the CLI refreshed it to is written back over it here.
      home: The virtual home to start the CLI in, or None for its own home. Native, it is
        built in the turn's private directory on the target, beside -- and never over --
        anything `projects` put there for the same variable, with the flow's own skills
        written into its skills directory, and taken away with the rest of that directory
        when the turn is over. Supervised, it is built on the machine the
        harness runs on, around the CLI the supervisor starts there (:func:`connect`), with
        what its driver manages merged in -- which is how a harness on another machine gets
        one, its skills having been carried there (:func:`hmz.coganchor.elsewhere.afar`); a
        CLI supervised here is started in one by whoever spawns it instead. Either way what
        the CLI rewrites of its configuration goes with it, and the user's own is never
        written.
      brings: What of a projected directory to bring back here before it is taken away, as
        `(VARIABLE/PATH, the directory on this machine)`: every file at or under `PATH` --
        which may be a glob -- inside the directory `VARIABLE` was projected as, put at the same
        place under that directory here. Which is how a session the CLI keeps under a home a
        provider moved into the turn's private directory outlives the turn; nothing outside
        `PATH` is brought, so the credentials beside it stay on the target until they go.
      tells: A directory on this machine to keep a file in for as long as the turn runs, of
        `VARIABLE=where it landed` lines, one per projected variable: which is how what copies
        a session as it goes finds a home the turn moved into its private directory, whose
        name the target chose. Empty to tell nobody.
      installs: The one line that puts this CLI on the target, said when it is not there.
        Handed in rather than looked up: which line installs a backend is a fact about that
        backend, and coganchor is underneath the layer those are written down in.
      fence: What the agent may reach, or None for a session held to nothing. Held on both
        machines, each around its own paths. Supervised, the agent process here is walled in
        by Landlock -- the workspace it is given being this machine's mirror of it -- with a
        proxy beside it as its one way out where the network is cut, and every command it
        has run on the target is run there under ``coganchor internal fence``, drawn again
        from the fence's rules around the target's workspace, its home and its minimum, with
        no way out at all where the network is cut.
        Native, the CLI itself is run so on the target, with the hosts its model is at and the
        state it keeps under its home. A target that cannot hold it refuses the session.
    """

    target: str = "local"
    harness: str = "local"
    broker: str = ""
    workspace: str | None = None
    chdir: str | None = None
    remote_path: str | None = None
    shadow: str | None = None
    local_paths: tuple[str, ...] = ()
    local_execs: tuple[str, ...] = ()
    private: tuple[str, ...] = ()
    redirects: tuple[tuple[str, str], ...] = ()
    net: str = "local"
    net_allow: tuple[str, ...] = ()
    token: str | None = None
    force: bool = False
    native: bool = False
    hushes: tuple[str, ...] = ()
    projects: tuple[tuple[str, str], ...] = ()
    home: Virtual | None = None
    brings: tuple[tuple[str, str], ...] = ()
    tells: str = ""
    installs: str = ""
    fence: Fence | None = None

    def __post_init__(self) -> None:
        """Refuses what the command line refuses, so both spellings mean the same thing.

        Where it is written, rather than where it is used: a flow that misspells a target
        hears about it as it configures its agents, not hours into the loop that drives them.

        Raises:
          ValueError: If the target cannot be read, the work's own connections are neither
            kept local nor sent to the target, a path is answered with something that is not
            a path, a variable to run without is not a variable name, a credential or a
            directory is to be put somewhere that is not a place, or a fence is one that
            cannot be held where this session runs.
        """
        from hmz.coganchor.elsewhere import harnessed
        from hmz.coganchor.transport import Target

        work = Target.parse(self.target)
        # Read rather than merely stored, so a harness pointed at a machine that cannot be
        # spelled is refused here with every other misspelling instead of hours later.
        where = harnessed(self.harness, self.target)
        if self.native and where.scheme != "local":
            raise ValueError(
                "a native session has no harness to put anywhere: the CLI on the target is "
                "the one that runs, so --harness and --native ask for opposite things"
            )
        if self.harness != "local" and work.scheme == "peer":
            raise ValueError(
                "a peer:// target is a meeting Humanize books for a harness it is placing; "
                "naming both is naming the same introduction twice"
            )
        if where.scheme != "local" and work.scheme == "tcp":
            raise ValueError(
                "a tcp:// target is a serving half somebody else left listening, which "
                "Humanize can start nothing beside; a harness on another machine has no "
                "way to be introduced to it"
            )
        if self.net not in ("local", "remote"):
            raise ValueError(f"unsupported net {self.net!r}; expected local or remote")
        for pair in self.redirects:
            # Absolute both ways: what the agent names is resolved before it is looked up,
            # and a relative answer would be read against wherever the turn happens to be.
            if not all(part.startswith("/") for part in pair):
                raise ValueError(
                    f"unsupported redirect {'='.join(pair)!r}; expected two absolute paths"
                )
        for name in self.hushes:
            # `env -u NAME` is what takes one off on the target, and `env` refuses a name
            # with an `=` in it -- so one written that way is a turn that would not start,
            # said here instead where the settings are read.
            if not name or "=" in name:
                raise ValueError(f"unsupported hush {name!r}; expected a variable name")
        for name, whence in self.projects:
            if not name or "=" in name or not whence.startswith("/"):
                raise ValueError(
                    f"unsupported projection {name}={whence!r}; expected a variable name "
                    "and an absolute path"
                )
        if self.fence is not None and not self.fence.open:
            self._fenceable(where.scheme)
        if self.tells and not self.tells.startswith("/"):
            raise ValueError(
                f"unsupported tell {self.tells!r}; expected an absolute path"
            )
        projected = {name for name, _ in self.projects}
        for named, into in self.brings:
            variable, _, under = named.partition("/")
            if (
                variable not in projected
                or not under
                or under.startswith("/")
                or ".." in under.split("/")
                or not into.startswith("/")
            ):
                raise ValueError(
                    f"unsupported bring {named}={into!r}; expected a projected VARIABLE, "
                    "a PATH inside it and an absolute path"
                )

    def _fenceable(self, harness: str) -> None:
        """Refuses a fence this session could not hold, as the settings are read.

        Raises:
          ValueError: If the fence was drawn path by path, and so has no rules to draw it
            again on the target with; if the harness is on another machine, whose paths the
            fence does not name; or if the agent's own connections are sent to the target
            while its network is to be cut here, which would send them past the proxy.
        """
        if not self.fence or not self.fence.drawn:
            raise ValueError(
                "a fence drawn path by path cannot be held on another machine; draw it "
                "from its rules with Fence.of"
            )
        if harness != "local":
            raise ValueError(
                "a fence is drawn around this machine's paths, and cannot hold a harness "
                "on another machine"
            )
        if self.net == "remote" and not self.fence.online:
            raise ValueError(
                "a fence that cuts the network keeps the agent's own connections here; "
                "--net remote would send them past it"
            )

    @property
    def capabilities(self) -> frozenset[str]:
        """What reaching a turn through this anchor comes to.

        The other half of what a place answers for. A machine's own settings say *where* the
        work lands -- somewhere else, somewhere isolated, somewhere started for the agent --
        and this says *how* a turn gets there, which is a fact about the anchor rather than
        about the machine: the same machine reached two ways is two different sets of things
        a turn may be asked to do.

        There are two ways and each is a function here. :data:`~hmz.coganchor.places.SUPERVISED`
        is :func:`connect`: the agent runs under coganchor's supervisor, and every file it
        opens and every command it spawns is answered from the target.
        :data:`~hmz.coganchor.places.NATIVE_CLI` is :func:`drive`: the CLI already installed on
        the target is the one that runs, read off its own three streams, with nothing traced
        and nothing mirrored. Further ways name themselves in
        :data:`~hmz.coganchor.places.ROADS` as they arrive, each under `anchor:` and its own
        name, so that a flow needing one asks for it by name instead of inferring it from a
        target.

        :data:`~hmz.coganchor.places.AFAR` is the one of those that is not a third way but a
        second question about the first: the turn is supervised, and what the name adds is
        that the supervisor and the agent process are on a machine other than this one. So it
        is said *alongside* `anchor:supervised` rather than instead of it, and a flow that
        must keep the agent's own process here is one that refuses it.

        The words themselves come from :mod:`hmz.coganchor.places` rather than being written
        out here, for the reason they are gathered there at all: the same two are what the
        capability catalogue describes and what a flow asks under, and a road spelled out once
        per place that says it is a road renamed in one of them.

        Returns:
          The names reaching this anchor answers to.
        """
        from hmz.coganchor.elsewhere import elsewhere

        if self.native:
            return frozenset({NATIVE_CLI})
        reached = {SUPERVISED, AFAR} if elsewhere(self) else {SUPERVISED}
        return frozenset(reached)

    def command(
        self,
        argv: Sequence[str],
        *,
        swaps: Sequence[tuple[str, str]] = (),
        private: Sequence[str] = (),
        chdir: str = "",
    ) -> list[str]:
        """Renders the invocation that runs `argv` under this anchor in a process of its own.

        What :func:`connect` does in this one, for callers that cannot lend it theirs. A
        method rather than the function it calls, so that a caller holding a stand-in for
        these settings can answer for what a turn is spawned as.

        Args:
          argv: The agent to run and its own arguments.
          swaps: Paths this one turn answers with others, on top of :attr:`redirects`. Where a
            turn under a provider says which credentials it is taken with, rather than the
            settings saying it for every turn.
          private: Variables this one turn keeps to itself, on top of :attr:`private` -- the
            same thing said for the credentials a provider hands the agent as variables
            rather than as files.
          chdir: Where inside the workspace this one session works, as the target names it,
            in place of :attr:`chdir`. Where a session opened at a directory of its own says
            so, rather than the settings saying it for every session.

        Returns:
          The command to spawn, which exits with the agent's own status.

        Raises:
          ValueError: If a swap is not between two absolute paths.
          ConnectionError: If the harness runs on another machine and Humanize cannot be put
            there, or the serving half cannot be left where the work lands.
        """
        from hmz.coganchor.argv import render
        from hmz.coganchor.elsewhere import afar, elsewhere

        answering = (
            replace(
                self,
                redirects=(*self.redirects, *swaps),
                private=(*self.private, *private),
                chdir=chdir or self.chdir,
            )
            if swaps or private or chdir
            else self
        )
        # A harness on another machine is the same line behind whatever runs Humanize there,
        # which is why it is answered here: what the layers above spawn is one command whose
        # streams are the agent's, and where that command runs is no part of what they read.
        if elsewhere(answering):
            return afar(answering, argv)
        return render(answering, argv)

    def mount(self) -> tuple[Target, str, str]:
        """Reads the target, and works out where the workspace is on each side of it.

        Returns:
          The target as parsed, the workspace's absolute path on this machine, and the export
          that names it to the target, as `VIRTUAL[:REAL]`.

        Raises:
          ValueError: If the target cannot be read.
        """
        from hmz.coganchor.transport import Target

        target = Target.parse(self.target)
        workspace = os.path.abspath(self.workspace or os.getcwd())
        # A `local:` target's path is the directory standing in for the far side; any other
        # target's path is something else of its own -- a ticket, a container's daemon.
        real = self.remote_path or (target.path if target.scheme == "local" else "")
        return target, workspace, f"{workspace}:{real}" if real else workspace


@contextlib.contextmanager
def _reached(config: AnchorConfig) -> Generator[tuple[Target, str, RemoteClient]]:
    """Opens the road to the target and puts it down again, whatever was asked of it.

    What a caller that talks to a target *itself* begins with -- read the settings for where
    the work lands, open a channel to the serving half, and speak the protocol down it --
    unwound in the order it was made. :func:`connect` does none of it: `coganchor cog` does.

    Args:
      config: Where the work lands.

    Yields:
      The target as parsed, the workspace's absolute path here, and the client speaking to
      the half that answers for it. The handshake is not done.

    Raises:
      ValueError: If the target cannot be read.
      OSError: If it cannot be reached.
    """
    from hmz.coganchor import transport
    from hmz.coganchor.remote import RemoteClient

    target, workspace, export = config.mount()
    link = transport.connect(target, [export], config.token)
    client = RemoteClient(link.channel)
    try:
        yield target, workspace, client
    finally:
        client.close()
        link.close()


def check(config: AnchorConfig | None = None) -> dict[str, Any]:
    """Asks the target what it is, without running anything on it.

    Args:
      config: Where the work would land, defaulting to this directory on a local target.

    Returns:
      What the target says about itself -- its `hostname`, the `pid` of the `coganchor`
      serving it and the `exports` it opened -- along with the `target` it was reached at, the
      `workspace`, and how many `entries` that workspace holds.

    Raises:
      ValueError: If the target cannot be read.
      OSError: If the target cannot be reached, or the workspace is not there.
    """
    config = config or AnchorConfig()
    with _reached(config) as (target, workspace, client):
        return client.start(config.token) | {
            "target": target.describe(),
            "workspace": workspace,
            "entries": len(client.listdir(workspace)["entries"]),
        }


def connect(command: Sequence[str], config: AnchorConfig | None = None) -> int:
    """Runs a coding agent on this machine that acts on another one.

    The agent process stays here, keeping its credentials, its state directory and its link
    to its model provider. Everything it *does* -- reading and writing project files, running
    commands, reaching the network from those commands -- happens on the target, and is
    undone by nothing: the call returns once the agent has exited and everything it wrote has
    been pushed. Where the settings say `native`, it is :func:`drive` instead; where the harness
    is on another machine, it is that machine's to run.

    All three are `coganchor cog`, spawned as :meth:`AnchorConfig.command` renders it with this
    process's own three streams, and waited for: a signal aimed here is aimed at it.

    Args:
      command: The agent to run and its own arguments, e.g. `["claude", "--print"]`.
      config: Where its work lands, defaulting to this directory on a local target.

    Returns:
      The agent's own exit status, or one `coganchor` gave for a turn that never ran.

    Raises:
      ValueError: If the target cannot be read, or no agent was named.
      FileNotFoundError: If there is no `coganchor` for this machine.
      NotInstalled: If the session is native and the agent is not installed on the target.
      ConnectionError: If the harness runs on another machine and `coganchor` cannot be put
        there, or the serving half cannot be left where the work lands.
    """
    config = config or AnchorConfig()
    if config.native:
        return drive(command, config)
    if not command:
        raise ValueError("no agent given")
    return _carried(config.command(command))


def drive(command: Sequence[str], config: AnchorConfig | None = None) -> int:
    """Runs the CLI already installed on the target, and carries its streams to this process.

    The other arrangement, and the simpler one. Nothing runs here: the CLI is started on the
    target, in the target's own copy of the workspace, and this process is a pipe -- what it
    is given on stdin reaches the CLI's stdin, what the CLI writes reaches these streams
    unchanged and unbuffered, a signal aimed here is aimed there, and the call returns with
    the CLI's own status. `coganchor cog --native` carries it out.

    Args:
      command: The agent to run and its own arguments, e.g. `["claude", "--print"]`.
      config: Where it runs, defaulting to this directory on a local target.

    Returns:
      The CLI's own exit status, or 128 plus the signal that killed it.

    Raises:
      ValueError: If the target cannot be read, or no agent was named.
      FileNotFoundError: If there is no `coganchor` for this machine.
      NotInstalled: If the agent is not installed on the target, which `coganchor` says by
        exiting as a shell does for a command it could not find.
    """
    config = replace(config or AnchorConfig(), native=True)
    if not command:
        raise ValueError("no agent given")
    status = _carried(config.command(command))
    if status == _NOTHING_TO_RUN:
        fix = f"; install it there with `{config.installs}`" if config.installs else ""
        raise NotInstalled(
            errno.ENOENT,
            f"{command[0]} is not installed on {config.target}{fix}",
            command[0],
        )
    return status


#: What a shell exits with for a command it could not find, which a native turn's CLI not
#: being on the target is.
_NOTHING_TO_RUN = 127

#: What a status has added to it to say a signal ended the command, as every shell reports it.
_SIGNALLED = 128


def _carried(argv: Sequence[str]) -> int:
    """Runs a line with this process's own three streams, and waits for it.

    A signal aimed at this process is aimed at the line: whatever asked for it -- a flow taking
    a session down, a service manager -- asked for the agent to stop, and `coganchor` is what
    stops it, bringing back what it has to on the way. So it is passed on rather than acted on,
    from the main thread, which is the one a handler can be put up on. `SIGINT` is the
    exception, and is ignored: a ctrl-c at a terminal already reaches the whole group, so
    passing it on would deliver it twice.

    Args:
      argv: The line.

    Returns:
      Its exit status, or 128 plus the signal that ended it.
    """
    import signal
    import threading

    started = subprocess.Popen(list(argv))

    def passed(signum: int, _frame: object) -> None:
        with contextlib.suppress(OSError):
            started.send_signal(signum)

    was: dict[int, Any] = {}
    if threading.current_thread() is threading.main_thread():
        for signum, then in (
            (signal.SIGINT, signal.SIG_IGN),
            (signal.SIGTERM, passed),
            (signal.SIGQUIT, passed),
            (signal.SIGHUP, passed),
        ):
            with contextlib.suppress(OSError, ValueError):
                was[signum] = signal.signal(signum, then)
    try:
        status = started.wait()
    finally:
        for signum, before in was.items():
            with contextlib.suppress(OSError, ValueError):
                signal.signal(signum, signal.SIG_DFL if before is None else before)
    return _SIGNALLED - status if status < 0 else status
