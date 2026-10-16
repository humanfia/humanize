"""Anchoring an agent to the machine its work lands on, both ways round.

Where a session is said in Python: the settings, the two calls that run one, and the call
that only asks the target what it is.

The two are opposites and the settings are shared. :func:`connect` keeps the agent here and
answers everything it does from the target -- a mirror of the workspace, a supervisor, a
syscall at a time. :func:`drive` keeps nothing here: the CLI already installed on the target
is the one that runs, and this process carries its streams. Which to use is a fact about the
anchor rather than about the machine, so it is a setting and
:attr:`AnchorConfig.capabilities` is what says it out loud.
"""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from .places import AFAR, NATIVE_CLI, SUPERVISED

if TYPE_CHECKING:
    from collections.abc import Generator, Mapping, Sequence

    from hmz.coganchor.fence import Fence
    from hmz.coganchor.homes import Home, Virtual
    from hmz.coganchor.remote import RemoteClient
    from hmz.coganchor.supervisor import Launch
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


def _unmirrored(path: str, why: OSError) -> Unmirrored:
    """The copy of the workspace that could not be made at `path`, and why, in words."""
    said = why.strerror or str(why)
    if why.filename and str(why.filename) != path and str(why.filename) not in said:
        said = f"{said}: {why.filename}"
    return Unmirrored(f"{UNMIRRORED} {path}: {said}")


#: How long the short commands a native session settles itself with may take. Generous, since
#: each is a round trip to a machine that may be far away, and bounded, since a target that
#: has stopped answering must read as one that has rather than hang the turn forever.
_SETTLING = 120.0

#: What a status has added to it to say a signal ended the command, as every shell reports it.
_SIGNALLED = 128

#: This process's own input. Read from the descriptor rather than through :data:`sys.stdin`, so
#: that what crosses is bytes exactly as they arrived: the backends this exists for frame their
#: protocol themselves, and a reader that waited for a line would hold a request until the next
#: one arrived. How much at a time is the protocol's own chunk, read where it is declared.
_STDIN = 0

#: How long the thread carrying that input waits before looking again at whether the turn is
#: over. A number rather than a blocking read, so that the thread ends when the turn does
#: instead of sitting on this process's input after the call has returned.
_LOOKING = 0.2

#: Finding the CLI on the target, in POSIX sh. `command -v` rather than `which`, which is not
#: POSIX and which some shells answer for a name nothing would run. A path is answered with
#: itself where it is executable, which is what makes one lookup serve both spellings.
_FIND_PROGRAM = 'command -v -- "$1" 2>/dev/null || exit 127'

#: Making the directory a session's credentials live in on the target. `mktemp -d` makes one
#: only its owner may enter; the `umask` and the `chmod` say so again, because a target whose
#: `mktemp` is a shim for something laxer is not a target to take that on trust. The bare form
#: first and a template after it, the two spellings BSD and GNU `mktemp` agree on between them.
_MAKE_SESSION = (
    "umask 077; "
    "d=$(mktemp -d 2>/dev/null || mktemp -d -t humanize) || exit 1; "
    'chmod 700 "$d" || exit 1; '
    'printf %s "$d"'
)

#: Writing one of them, from what arrives on stdin. Anything already at the name goes first,
#: so a link left there is not a link this writes through; the file is made before anything is
#: in it and made unreadable by anyone else in the same breath, so there is no instant at which
#: a credential is on that machine under a mode somebody else could read it through.
_WRITE_PRIVATELY = (
    'umask 077; mkdir -p "$(dirname -- "$1")" || exit 1; rm -f -- "$1" || exit 1; '
    ': > "$1" || exit 1; chmod 600 "$1" || exit 1; cat > "$1"'
)

#: Writing one file of a skill, from what arrives on stdin, with the mode in `$2`: beside it and
#: moved over it, so that a skill on the target is never a file of it half written.
_WRITE_WHOLE = (
    'umask 077; mkdir -p "$(dirname -- "$1")" || exit 1; t="$1.hmz-new"; rm -f -- "$t"; '
    'if cat > "$t" && chmod "$2" "$t" && mv -f -- "$t" "$1"; then exit 0; fi; '
    'rm -f -- "$t"; exit 1'
)

#: Taking one of them away again, whatever it turned out to be.
_SWEEP = 'rm -rf -- "$1"'

#: Reading one of them back, as it stands once the CLI is done with it.
_READ_BACK = 'cat -- "$1"'

#: Everything at the paths after `$1` inside it, each of which may be a glob of one name per
#: part, as one `tar` on stdout -- or nothing, where none of them is there.
_PACK = """
cd "$1" 2>/dev/null || exit 0
shift
n=$#
for p in "$@"; do for f in $p; do [ -e "$f" ] && set -- "$@" "$f"; done; done
shift "$n"
[ $# -gt 0 ] || exit 0
tar cf - "$@" 2>/dev/null
exit 0
"""

#: How long the end of a turn may spend bringing back what it wrote in a projected directory.
_BRINGING = 30.0


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
        as this one; a machine they reach humanize by some other name at says that name here.
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
        built in the turn's private directory on the target (:data:`hmz.coganchor.homes.SCRIPT`),
        beside -- and never over -- anything `projects` put there for the same variable, with
        the flow's own skills written into its skills directory, and taken away with the rest
        of that directory when the turn is over. Supervised, it is built on the machine the
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
        proxy in this process as its one way out where the network is cut, and every command
        it has run on the target is run there under ``hmz internal fence``, drawn again from
        the fence's levels around the target's workspace, its home and its minimum
        (:mod:`hmz.coganchor.fence.abroad`), with no way out at all where the network is cut.
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
                "a peer:// target is a meeting humanize books for a harness it is placing; "
                "naming both is naming the same introduction twice"
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
          ValueError: If the fence was drawn path by path, and so has no levels to draw it
            again on the target with; if the harness is on another machine, whose paths the
            fence does not name; or if the agent's own connections are sent to the target
            while its network is to be cut here, which would send them past the proxy.
        """
        if not self.fence or not self.fence.scopes:
            raise ValueError(
                "a fence drawn path by path cannot be held on another machine; draw it "
                "from its levels with Fence.of"
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
          ConnectionError: If the harness runs on another machine and humanize cannot be put
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
        # A harness on another machine is the same line behind whatever runs humanize there,
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

    The dance both the callers that talk to a target *themselves* begin with -- read the
    settings for where the work lands, open a channel to the serving half, and speak the
    protocol down it -- said once rather than twice, and unwound in the order it was made.
    :func:`connect` does it by hand instead, and on purpose: it prepares a mirror first, and
    a mirror it will not take over is a session that must fail before a machine has been
    bootstrapped to serve it.

    Args:
      config: Where the work lands.

    Yields:
      The target as parsed, the workspace's absolute path here, and the client speaking to
      the half that answers for it. The handshake is not done: a supervised session makes it
      after the agent is forked and stopped, which is later than this.

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
      What the target says about itself -- its `hostname`, the `python` running it, its `pid`
      and the `exports` it opened -- along with the `target` it was reached at, the
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
    been pushed.

    Args:
      command: The agent to run and its own arguments, e.g. `["claude", "--print"]`.
      config: Where its work lands, defaulting to this directory on a local target.

    Returns:
      The agent's own exit status.

    Raises:
      ValueError: If the target cannot be read, or no agent was named.
      FileNotFoundError: If the agent is not on PATH.
      Unmirrored: If the mirror's path cannot be made a directory here.
      FileExistsError: If the mirror's directory holds other files, or mirrors another target.
      OSError: If the target cannot be reached, or the agent's virtual home (`config.home`)
        cannot be built here.
    """
    config = config or AnchorConfig()
    # Answered before anything below is imported, and before a mirror is so much as looked
    # at: driving the CLI on the target needs no ptrace, no register map and no shadow, and a
    # machine that could not supervise a turn can still take one this way.
    if config.native:
        return drive(command, config)

    # And before that too, for the same reason: a harness on another machine is that
    # machine's supervisor to run, and this process is the pipe carrying its three streams.
    # Nothing of the tracer is reached here, so a machine that could not supervise a turn can
    # still be the one that starts one somewhere that can.
    from hmz.coganchor.elsewhere import afar, elsewhere

    if elsewhere(config):
        return subprocess.call(afar(config, command))

    # Built before anything else of the turn, and taken away whatever becomes of it.
    from hmz.coganchor import homes

    home = homes.build(config.home) if config.home is not None else None
    try:
        return _supervised(command, config, home)
    finally:
        if home is not None:
            home.drop()


def _supervised(command: Sequence[str], config: AnchorConfig, home: Home | None) -> int:
    """:func:`connect`, for a harness on this machine: the agent here, supervised.

    Args:
      command: The agent to run and its own arguments.
      config: Where its work lands.
      home: The virtual home it is started in, built here, or None for the user's own. Its
        own like the agent's state directory, and kept here likewise: neither a path in it
        nor a program run from it is sent to the target.

    Returns:
      The agent's own exit status.
    """
    # Imported here rather than at the top: this half needs ptrace and an x86-64 register
    # map, which the machines reading the settings above are not required to have.
    from hmz.coganchor import __version__, statepaths, transport
    from hmz.coganchor._lending import lent, refreshing
    from hmz.coganchor.netproxy import NetProxy
    from hmz.coganchor.policy import Layout, Router, head
    from hmz.coganchor.remote import RemoteClient
    from hmz.coganchor.shadow import ShadowTree, prepare_shadow_root
    from hmz.coganchor.supervisor import Launch, Supervisor

    target, workspace, export = config.mount()
    # Named on the command line right after the CLI's own name, for one no variable moves.
    moved = home.argv if home is not None else ()
    agent = statepaths.resolve([*command[:1], *moved, *command[1:]])
    kept = [str(home.at)] if home is not None else []
    # By the name the kernel has for it, through any symlink on the way there: where a
    # process is, is read back as that name, and a command started in a mirror named
    # otherwise would land outside it -- in the target's home, not the workdir. The name it
    # was given is the other name it answers to, which a driver told the CLI to work at.
    named = os.path.abspath(config.shadow or workspace)
    shadow_root = os.path.realpath(named)
    # Where the agent itself starts: the mirror of the directory it was told to work in,
    # which is the workspace unless a session asked for one inside it.
    started_in = shadow_root
    if config.chdir:
        under = os.path.abspath(config.chdir)
        if under != workspace and not under.startswith(workspace + os.sep):
            raise ValueError(f"{under} is not inside {workspace}")
        started_in = os.path.join(shadow_root, os.path.relpath(under, workspace))
    redirects = tuple(
        (os.path.abspath(named), os.path.abspath(instead))
        for named, instead in config.redirects
    )
    router = Router(
        layouts=(Layout.create(shadow_root, workspace),),
        aliases=tuple(
            dict.fromkeys(
                (
                    *_aliases(target, shadow_root, workspace),
                    *_aliases(target, shadow_root, named, linked=True),
                )
            )
        ),
        local_paths=tuple(
            agent.local_paths
            + kept
            + [os.path.abspath(path) for path in config.local_paths]
            # What a path is answered with is this machine's business: mirroring a
            # provider's credentials onto the target would put them where the work lands,
            # and a session humanize keeps is kept here. A pattern's is the directory it is
            # in, which is the one every path it answers is under.
            + [
                instead if head(instead) == instead else os.path.dirname(head(instead))
                for _, instead in redirects
            ]
        ),
        local_programs=tuple(
            agent.local_programs
            + kept
            + [os.path.abspath(path) for path in config.local_execs]
        ),
        redirects=redirects,
    )
    # The machine it mirrors, by its destination: what ssh is told on the way there -- a key,
    # a keepalive -- is not another machine, and a mirror is not refused for being told it.
    try:
        prepare_shadow_root(
            shadow_root,
            force=config.force,
            target=replace(target, options=()).describe(),
        )
    except FileExistsError:
        # A directory that is somebody's, or another target's mirror: a path that was made,
        # whose own words say what to do about it -- another directory, or `--force`.
        raise
    except OSError as why:
        raise _unmirrored(shadow_root, why) from why

    link = transport.connect(target, [export], config.token)
    client = RemoteClient(link.channel)
    # How the target spells a path is the target's to say -- a Mac reaches `/tmp` through
    # `/private/tmp` and does not tell `A` from `a` -- and it says so at the handshake, which
    # happens once the agent is forked and stopped, after these settings are read. So the
    # router is given the question rather than the answer, and asks when a path needs routing.
    router.platform = lambda: str(client.info.get("platform", ""))
    netproxy = NetProxy(client, config.net_allow) if config.net == "remote" else None
    # The mirror fills itself in as the agent looks at things, and the one directory it
    # cannot be asked about first is the one the agent is started in: the `chdir` happens in
    # the forked child, before it has become the agent and before anything may talk to the
    # target -- a reader thread cannot exist across that fork. So the directory is made here
    # and left empty; the first thing the agent does in it is what fills it in, and a
    # directory the target does not have is emptied again by the same reconciliation.
    os.makedirs(started_in, exist_ok=True)
    launch = Launch(
        program=agent.program,
        argv=agent.argv,
        env=(home.environ(None) if home is not None else dict(os.environ))
        | {
            "HUMANIZE": __version__,
            "HUMANIZE_TARGET": target.describe(),
            "PWD": started_in,
            # Agents surface this to the model; being explicit beats it guessing.
            "HUMANIZE_WORKSPACE": workspace,
        },
        cwd=started_in,
    )
    walls = _Walls(config.fence, shadow_root) if config.fence else None
    supervisor = Supervisor(
        client,
        router,
        # Shared with every other turn working in the same mirror, which is the normal case
        # for the sessions of one run on one environment.
        ShadowTree(client, router, mirror=shadow_root),
        walls.around(launch) if walls is not None else launch,
        netproxy=netproxy,
        token=config.token,
        private=config.private,
        fence=walls.told if walls is not None else None,
    )
    log.info("running %s against %s", agent.profile.name, target.describe())
    try:
        # A sign-in that refreshes itself, answered here in place, is held for the turn's
        # length beside every other turn here using it -- and so never while a copy of it is
        # out on another machine. Files only: a directory answered may be the CLI's sessions.
        with lent(refreshing((one for _, one in redirects), inside=False), away=False):
            if netproxy is not None:
                netproxy.start()
            if walls is not None:
                walls.start()
            return supervisor.run()
    finally:
        if walls is not None:
            walls.stop()
        if netproxy is not None:
            netproxy.close()
        supervisor.shadow.close()
        client.close()
        link.close()


def _aliases(
    target: Target, shadow_root: str, workspace: str, *, linked: bool = False
) -> tuple[tuple[str, str], ...]:
    """The other name the agent may reach its mirror by, as `(name, mirror)`, if it has one.

    The workspace's own path, for a harness on another machine than this session's driver:
    its mirror is kept under that machine's mirror cache, and the driver tells a CLI where to
    work by the workspace's own path, over its protocol rather than as a directory to start
    in -- Codex's `thread/start` takes a `cwd`, and every shell it then ran was started in a
    directory that harness had never had. That harness reaches its work at a `peer://`
    target, and only there is the path the target's alone: whatever this machine holds at it
    is some other directory of the same name. Nothing for a mirror nested in its workspace,
    or the other way about, where one name for both could only be answered in circles.

    Or, `linked`, the name the mirror was given where a symlink on the way there makes it
    another name than the kernel's -- a mirror under a home whose `~/.cache` is a link
    elsewhere -- which is the name a driver told the CLI to work at, whatever the target.

    Args:
      target: Where the work lands.
      shadow_root: The mirror, as this machine names it.
      workspace: The workspace, as the target names it; or, `linked`, the mirror as it
        was named.
      linked: Whether `workspace` is the mirror's own other name.

    Returns:
      The alias, or nothing.
    """
    from hmz.coganchor.proto import path_within

    if (
        (target.scheme != "peer" and not linked)
        or path_within(shadow_root, workspace) is not None
        or path_within(workspace, shadow_root) is not None
    ):
        return ()
    return ((workspace, shadow_root),)


class _Walls:
    """The fence around a supervised agent, on both sides of the anchor.

    Here, the agent process itself: the fence as it was drawn on this machine, with the
    mirror granted as the workspace is -- the mirror being the workspace, to a process whose
    every path into it is rewritten into the mirror -- put up in the forked child
    (:class:`~hmz.coganchor.supervisor.Launch`), with the proxy that is its one way out
    served by this process, outside the wall. There, every command the agent has run: the
    fence's levels, :attr:`told` with each one, for the target to draw the fence again around
    its own paths. The supervisor, its link to the target and its mirror are all outside it,
    which is what lets a session reach a target over ssh while its agent reaches no host but
    its model's.

    Args:
      fence: What the agent may reach.
      mirror: This machine's mirror of the workspace.

    Raises:
      PermissionError: If this machine cannot put the wall up.
    """

    def __init__(self, fence: Fence, mirror: str) -> None:
        import tempfile

        from hmz.coganchor.fence import ALL, READ, Proxy, abroad, landlocked

        if not landlocked(net=not fence.online):
            raise PermissionError(
                "this machine cannot fence the agent: it needs Landlock"
                + ("" if fence.online else " ABI 4 and seccomp")
            )
        level = fence.scopes[0] if fence.scopes else ""
        self.fence = fence.granting(
            read=[mirror] if level == READ else [],
            write=[mirror] if level == ALL else [],
        )
        self._made = not fence.tmp
        self.tmp = fence.tmp or tempfile.mkdtemp(prefix="hmz-fence-")
        os.makedirs(self.tmp, mode=0o700, exist_ok=True)
        # With the scratch the agent is given, for the target to keep its own at the same
        # path: the agent names it in the commands it sends there.
        self.told = abroad.told(
            replace(fence, tmp=self.tmp), home=os.path.expanduser("~"), native=False
        )
        self._proxy = None if fence.online else Proxy(fence.hosts)

    def around(self, launch: Launch) -> Launch:
        """The launch, walled in, with the environment a fenced program runs with."""
        from hmz.coganchor.fence.wrap import environ
        from hmz.coganchor.linux import landlock

        port = self._proxy.port if self._proxy is not None else None
        return replace(
            launch,
            env=environ(self.fence, launch.env, tmp=self.tmp, port=port),
            walled=landlock.Ruleset(
                read=self.fence.read,
                write=(*self.fence.write, self.tmp),
                connect_ports=() if port is None else (port,),
                # As `hmz internal fence` has them: a port the kernel picks, and the ones the
                # fence names; each held to loopback by the supervisor (see `Launch`).
                bind_ports=() if port is None else (0, *self.fence.listen),
                net=port is not None,
            ),
            sockets=port is not None,
        )

    def start(self) -> None:
        """Serves the proxy, where there is one."""
        if self._proxy is not None:
            self._proxy.start()

    def stop(self) -> None:
        """Stops the proxy, and takes away the scratch this made."""
        import shutil

        if self._proxy is not None:
            self._proxy.stop()
        if self._made:
            shutil.rmtree(self.tmp, ignore_errors=True)


def drive(command: Sequence[str], config: AnchorConfig | None = None) -> int:
    """Runs the CLI already installed on the target, and carries its streams to this process.

    The other arrangement, and the simpler one. Nothing runs here: the CLI is started on the
    target, in the target's own copy of the workspace, and this process is a pipe -- what it
    is given on stdin reaches the CLI's stdin, what the CLI writes reaches these streams
    unchanged and unbuffered, a signal aimed here is aimed there, and the call returns with
    the CLI's own status. Which is what makes running a turn elsewhere an argv change for the
    backends that already speak a framed protocol to a process humanize spawns: the frames
    cross a machine boundary and neither end is told.

    Three things do not ride along on their own, and each is answered here. The environment is
    composed on the target, so what a provider hushes is taken off there with `env -u` rather
    than merely left out of what is sent. Credentials are written into a directory of the
    turn's own that only the target's user may enter, named to the CLI by variable and never by
    argv, and taken away whatever happens -- except a sign-in that refreshes itself, which is
    let out to one turn at a time and whose refreshed copy is written back over the original
    before it is taken away (:func:`_lending`). And the flow's own skills go into the virtual
    home the CLI is started in (`config.home`), never into the workspace.

    Args:
      command: The agent to run and its own arguments, e.g. `["claude", "--print"]`.
      config: Where it runs, defaulting to this directory on a local target.

    Returns:
      The CLI's own exit status, or 128 plus the signal that killed it.

    Raises:
      ValueError: If the target cannot be read, or no agent was named.
      NotInstalled: If the agent is not installed on the target.
      OSError: If the target cannot be reached, or a credential cannot be put on it -- or,
        with `EBUSY`, if a sign-in that refreshes itself is out for another turn already.
    """
    from pathlib import Path

    from hmz.coganchor import __version__
    from hmz.coganchor.atomic import writes

    config = config or AnchorConfig()
    if not command:
        raise ValueError("no agent given")
    _, workspace, _ = config.mount()
    started_in = config.chdir or workspace
    if started_in != workspace and not started_in.startswith(workspace + "/"):
        raise ValueError(f"{started_in} is not inside {workspace}")

    lent: list[_Lent] = []
    session = ""
    projected: dict[str, str] = {}
    told = ""
    # What names this turn's file of where its projected variables landed.
    whose = uuid.uuid4().hex
    # A sign-in that refreshes itself is held for the whole turn before anything is reached:
    # one copy of it out at a time, and that copy brought back over the original at the end.
    with (
        _lending(config.projects) as refreshing,
        _reached(config) as (target, _, client),
    ):
        try:
            client.start(config.token)
            program = _installed(
                client, command[0], workspace, config, target.describe()
            )
            said = {
                "HUMANIZE": __version__,
                "HUMANIZE_TARGET": target.describe(),
                # Agents surface this to the model; being explicit beats it guessing.
                "HUMANIZE_WORKSPACE": workspace,
            }
            fence = _fenced(client, config)
            if config.projects or config.home is not None:
                session = _session(client, workspace)
            if config.projects:
                projected = _projected(
                    client, config.projects, session, workspace, refreshing, lent
                )
                said |= projected
                if config.tells:
                    # Nobody told is a session copied as the turn ends rather than as it goes.
                    with contextlib.suppress(OSError):
                        told = os.path.join(config.tells, whose)
                        writes(
                            Path(told),
                            "".join(
                                f"{k}={v}\n" for k, v in projected.items()
                            ).encode(),
                        )
            if config.home is not None:
                said |= _homed(client, config.home, session, workspace, projected)
            if session and fence is not None:
                fence["write"] = [*fence["write"], session]
            log.info("driving %s on %s", program, target.describe())
            argv = [*_wrapping(config.hushes, said), program, *command[1:]]
            return _drives(client, argv, started_in, dict(os.environ), fence)
        finally:
            # Inside the channel rather than beside it: what this takes off the target is
            # taken off *through* that channel, so it has to happen while there is one. And
            # a refreshed sign-in is read back before the copy it is in is taken away.
            _brought_back(client, lent, workspace)
            _brought_home(client, config.brings, projected, workspace)
            if session and config.home is not None:
                _written_back(client, session, config.home, workspace)
            if told:
                with contextlib.suppress(OSError):
                    os.unlink(told)
            _swept(client, session, workspace)


def _fenced(client: RemoteClient, config: AnchorConfig) -> dict[str, Any] | None:
    """What the target is told to hold a native CLI to, having said it can.

    Args:
      client: The open connection, past its handshake.
      config: The settings, whose `fence` is what the CLI may reach.

    Returns:
      The fence's levels, with the hosts the CLI's model is at and the state it keeps under
      its home, or None for a session held to nothing.

    Raises:
      PermissionError: If the target said at the handshake that it cannot fence, or said
        nothing, which a target of a build before fences does.
    """
    import errno

    from hmz.coganchor.fence import abroad
    from hmz.coganchor.proto import hello_fences

    fence = config.fence
    if fence is None or fence.open:
        return None
    if not hello_fences(client.info, net=not fence.online):
        raise PermissionError(
            errno.EPERM,
            "the target cannot fence the CLI: it needs Landlock"
            + ("" if fence.online else " ABI 4 and seccomp"),
        )
    return abroad.told(fence, home=os.path.expanduser("~"), native=True)


def _ran(
    client: RemoteClient, argv: list[str], cwd: str, feeding: bytes = b""
) -> tuple[int, str]:
    """Runs one short command on the target and waits for the line it answered with.

    Args:
      client: The open connection.
      argv: The command, as :func:`_exchanged` takes it.
      cwd: Where to run it, as the target names it.
      feeding: What to write to its stdin.

    Returns:
      Its exit status, and what it wrote to stdout with the trailing newline taken off.

    Raises:
      OSError: If the target could not be asked at all.
    """
    status, said = _exchanged(client, argv, cwd, feeding)
    return status, said.decode("utf-8", "replace").strip()


def _exchanged(
    client: RemoteClient,
    argv: list[str],
    cwd: str,
    feeding: bytes = b"",
    within: float = _SETTLING,
) -> tuple[int, bytes]:
    """Runs one short command on the target and waits for the whole of what it said.

    For the handful of things a session has to settle before the CLI starts -- is it there,
    where may a credential be put, what is to be swept up -- each of which is one command that
    answers in a line. The CLI itself is :func:`_drives`, which never waits for anything.

    Args:
      client: The open connection.
      argv: The command, whose paths may be the workspace's virtual ones: the target rewrites
        them to its own before it runs anything.
      cwd: Where to run it, as the target names it.
      feeding: What to write to its stdin, for a command whose input must not be in its argv.
      within: How long to wait for it, in seconds.

    Returns:
      Its exit status, and what it wrote to stdout byte for byte.

    Raises:
      OSError: If the target could not be asked at all.
    """
    import threading

    from hmz.coganchor.proto import CHUNK_SIZE, Stream

    said = bytearray()
    done = threading.Event()
    held: dict[str, Any] = {}

    def on_output(stream: Stream, data: bytes) -> None:
        if stream is Stream.STDOUT:
            said.extend(data)

    def on_exit(result: dict[str, Any] | None, error: OSError | None) -> None:
        held["result"], held["error"] = result, error
        done.set()

    import signal as signals

    handle = client.start_exec(argv, cwd, {}, on_output, on_exit)
    # A frame apiece, at the size the protocol carries one in: nothing here is ever that big,
    # and a file that was would otherwise be one frame nobody sized.
    for at in range(0, len(feeding), CHUNK_SIZE):
        handle.send_stdin(feeding[at : at + CHUNK_SIZE])
    handle.close_stdin()
    if not done.wait(timeout=within):
        # Ended there as well as given up on here, best effort: these are one-line commands,
        # so one that has not answered in this long is stuck, and a stuck command left running
        # on the target is one nothing will ever come back for.
        with contextlib.suppress(OSError):
            handle.signal(signals.SIGKILL)
        raise TimeoutError(f"the target did not answer {argv[0]!r} in {within:.0f}s")
    if (error := held.get("error")) is not None:
        raise error
    return _status(held.get("result")), bytes(said)


def _status(result: dict[str, Any] | None) -> int:
    """What a command on the target exited with, as a shell would report it.

    Args:
      result: What the target answered the exchange with.

    Returns:
      Its own status, or 128 plus the signal that killed it -- and 1 for a command the target
      said nothing about, which is a command that did not succeed.
    """
    if result is None:
        return 1
    if (signalled := result.get("signal")) is not None:
        return _SIGNALLED + int(signalled)
    return int(result.get("exit_code", 1))


def _installed(
    client: RemoteClient,
    named: str,
    workspace: str,
    config: AnchorConfig,
    where: str,
) -> str:
    """Finds the CLI on the target, before anything is put there on its behalf.

    Asked first because a turn that cannot run must not leave a credential behind it, and
    because what is wrong is one sentence rather than whatever a CLI that is not there makes
    of its arguments. A name is looked up on the target's own `PATH`; a path is tried as it is
    and then by its last component, which is the same fallback a command spawned under a
    supervisor already gets -- an agent bundles helpers under its own install directory, and
    that directory is this machine's.

    Args:
      client: The open connection.
      named: The CLI, as the command line named it.
      workspace: Where to look from, as the target names it.
      config: The settings, for the line that installs it.
      where: The target, as it describes itself, for the sentence this fails with.

    Returns:
      Where it is on the target, as an absolute path.

    Raises:
      NotInstalled: If it is not installed there.
    """
    import errno
    import posixpath

    for candidate in dict.fromkeys((named, posixpath.basename(named))):
        status, found = _ran(
            client, ["/bin/sh", "-c", _FIND_PROGRAM, "humanize", candidate], workspace
        )
        if status == 0 and found:
            return found
    fix = f"; install it there with `{config.installs}`" if config.installs else ""
    raise NotInstalled(errno.ENOENT, f"{named} is not installed on {where}{fix}", named)


def _session(client: RemoteClient, workspace: str) -> str:
    """Makes the directory this session keeps its credentials in on the target.

    Made by `mktemp`, which every POSIX system has and which makes a directory only its owner
    may enter, and then told to be exactly that whatever the target's `umask` had to say.
    Under the target's own temporary directory rather than inside the workspace: what is in
    the workspace is the project's, and a credential written there would be a credential
    committed.

    Args:
      client: The open connection.
      workspace: Where to run the command from, as the target names it.

    Returns:
      Its absolute path on the target.

    Raises:
      OSError: If the target would not make one.
    """
    import errno

    status, made = _ran(client, ["/bin/sh", "-c", _MAKE_SESSION, "humanize"], workspace)
    if status != 0 or not made.startswith("/"):
        raise OSError(
            errno.EACCES,
            "could not make a private directory on the target",
            made or None,
        )
    return made


@dataclass(frozen=True, slots=True)
class _Lent:
    """A sign-in that refreshes itself, as it was put on the target for one turn.

    Attributes:
      here: The file on this machine it is a copy of.
      there: Where the copy is on the target.
      sent: What the copy held as it was sent, which is what the original must still hold for
        the copy to be brought back over it.
    """

    here: str
    there: str
    sent: bytes


def _json(said: bytes) -> bool:
    """Whether some bytes are a whole JSON document, as every sign-in file of these CLIs is."""
    import json

    try:
        json.loads(said)
    except ValueError:
        return False
    return True


@contextlib.contextmanager
def _lending(projects: Sequence[tuple[str, str]]) -> Generator[frozenset[str]]:
    """Holds every projected sign-in that refreshes itself for one turn, or refuses the turn.

    A copy of such a sign-in is a second holder of one family of tokens: whichever holder
    refreshes first spends the refresh token the other still has, and the vendor revokes the
    family when that is presented (:mod:`hmz.coganchor._lending`). So the copy goes
    only while nothing else holds the file, and nothing else may until it is brought back.

    Args:
      projects: What the turn projects, as `(variable, the directory on this machine)`.

    Yields:
      The files on this machine that are such sign-ins, by path. Nothing at all for an
      account that is keys and settings, which is held by nothing.

    Raises:
      OSError: With `EBUSY`, if another turn is using one of them.
    """
    from hmz.coganchor._lending import lent, refreshing

    files = refreshing(whence for _, whence in projects)
    with lent(files, away=True):
        yield files


def _projected(
    client: RemoteClient,
    projects: Sequence[tuple[str, str]],
    session: str,
    workspace: str,
    refreshing: frozenset[str] = frozenset(),
    lent: list[_Lent] | None = None,
) -> dict[str, str]:
    """Puts this turn's credentials on the target, and says what to call each of them.

    One file at a time and each through the command that writes it, rather than through the
    filesystem calls: those are bounded by what the target exported, which is the workspace,
    and this deliberately lands outside it. The contents cross on the command's stdin, so no
    part of a credential is ever in an argument -- an argument being a line in every other
    user's `ps`.

    Args:
      client: The open connection.
      projects: What to put there, as `(variable, the directory on this machine)`.
      session: The directory on the target to put it under.
      workspace: Where to run the commands from, as the target names it.
      refreshing: The files among them that are sign-ins refreshing themselves, as
        :func:`_lending` found them.
      lent: Filled in with each of those as it lands, so that what the CLI refreshes it to can
        be brought back over the original however the turn ends -- given rather than answered
        with, so one that lands before a later one fails is still brought back.

    Returns:
      The variable to set for each, naming where it landed.

    Raises:
      OSError: If a credential could not be written to the target, which is a turn that must
        not run: a CLI that did not find the account it was given would sign in as whoever
        the target is.
    """
    import errno
    import posixpath
    from pathlib import Path

    named: dict[str, str] = {}
    for variable, whence in projects:
        root = Path(whence)
        landed = posixpath.join(session, variable.lower())
        for one in sorted(path for path in root.rglob("*") if path.is_file()):
            at = posixpath.join(landed, *one.relative_to(root).parts)
            sent = one.read_bytes()
            status, said = _ran(
                client,
                ["/bin/sh", "-c", _WRITE_PRIVATELY, "humanize", at],
                workspace,
                feeding=sent,
            )
            if status != 0:
                raise OSError(
                    errno.EACCES, f"could not put {variable} on the target: {said}", at
                )
            if lent is not None and str(one) in refreshing:
                lent.append(_Lent(here=str(one), there=at, sent=sent))
        named[variable] = landed
    return named


def _homed(
    client: RemoteClient,
    home: Virtual,
    session: str,
    workspace: str,
    projected: Mapping[str, str],
) -> dict[str, str]:
    """Builds the CLI's virtual home on the target, and says what to start the CLI with.

    In the turn's private directory, where anything projected for the same variable has
    landed already and is left as it is: the account a provider gave this turn is the one it
    runs as. The flow's skills are written into it a file at a time, as credentials are -- what
    is outside the workspace is not the filesystem calls' to reach.

    Args:
      client: The open connection.
      home: What the virtual home is made of.
      session: The turn's private directory on the target.
      workspace: Where to run the commands from, as the target names it.
      projected: What was projected, by variable, as :func:`_projected` said.

    Returns:
      The variables to set: the home's, naming where it landed, and the one keeping the CLI's
      sign-in where it would be -- in the projected account where there is one, and where the
      target user's own home would have it otherwise.

    Raises:
      OSError: If it could not be built, which is a turn that must not run: a CLI pointed at
        half a home is a CLI that has lost its settings.
    """
    import errno
    import posixpath
    import stat
    from pathlib import Path

    from hmz.coganchor.homes import SCRIPT, words

    landed = posixpath.join(session, home.variable.lower())
    status, moved = _ran(
        client,
        [
            "/bin/sh",
            "-c",
            SCRIPT,
            "humanize",
            landed,
            home.variable,
            home.default,
            home.lodges,
            *words(home),
        ],
        workspace,
    )
    if status != 0:
        raise OSError(
            errno.EACCES, f"could not build {home.variable} on the target: {moved}"
        )
    for name, whence in home.skills:
        root = Path(whence)
        for one in sorted(path for path in root.rglob("*") if path.is_file()):
            at = posixpath.join(landed, home.lodges, name, *one.relative_to(root).parts)
            # Its owner's bits alone, a script's among them: the target need not be one user's.
            mode = format(stat.S_IMODE(one.stat().st_mode) & 0o700, "o")
            status, said = _ran(
                client,
                ["/bin/sh", "-c", _WRITE_WHOLE, "humanize", at, mode],
                workspace,
                feeding=one.read_bytes(),
            )
            if status != 0:
                # A skill that could not be written is a turn that runs without it, as one a
                # workspace could not take is -- and none of it, rather than half.
                log.warning("could not carry %s to %s: %s", whence, at, said)
                half = posixpath.join(landed, home.lodges, name)
                with contextlib.suppress(OSError):
                    _ran(client, ["/bin/sh", "-c", _SWEEP, "humanize", half], workspace)
                break
    told = {home.variable: landed}
    if home.secures:
        told[home.secures] = landed if home.variable in projected else moved
    return told


def _brought_back(client: RemoteClient, lent: Sequence[_Lent], workspace: str) -> None:
    """Writes what the CLI refreshed each lent sign-in to back over the one it was copied from.

    The other half of :func:`_lending`. A CLI that refreshed its sign-in on the target has
    spent the refresh token the original still holds, so the original is only still an
    account if the new one is brought back into it. Only over an original that still holds
    exactly what was sent: one that changed meanwhile was refreshed here too, which makes the
    two copies the case all of this is to prevent, and writing over it would only choose which
    half of a revoked family to keep. That is said, since the account will need signing in
    again and nothing else would say why.

    Never raises, for the reason :func:`_swept` does not: this runs on the way out of a turn.

    Args:
      client: The connection, which may already be broken.
      lent: The sign-ins that were put on the target.
      workspace: Where to run the command from, as the target names it.
    """
    from pathlib import Path

    from hmz.coganchor._lending import REFRESHES
    from hmz.coganchor.atomic import writes

    for one in lent:
        try:
            status, now = _exchanged(
                client, ["/bin/sh", "-c", _READ_BACK, "humanize", one.there], workspace
            )
        except (OSError, ValueError) as why:
            log.warning("could not read %s back from the target: %s", one.here, why)
            continue
        if now == one.sent:
            continue  # not refreshed, which is most turns
        if (
            status != 0
            or not REFRESHES.search(now)
            or (_json(one.sent) and not _json(now))
        ):
            # Gone, or caught half written: no sign-in to keep. Said, since the original may
            # now hold a refresh token the target spent, and nothing else would say why.
            log.warning(
                "could not bring %s back from the target, which left no whole sign-in "
                "there; if the account was refreshed there, it needs signing in again",
                one.here,
            )
            continue
        here = Path(one.here)
        try:
            if here.read_bytes() != one.sent:
                log.warning(
                    "%s was refreshed both here and on the target during one turn; the "
                    "vendor may have revoked it, and the account may need signing in again",
                    one.here,
                )
                continue
            writes(here, now)
        except OSError as why:
            log.warning("could not bring %s back from the target: %s", one.here, why)


def _brought_home(
    client: RemoteClient,
    brings: Sequence[tuple[str, str]],
    projected: Mapping[str, str],
    workspace: str,
) -> None:
    """Brings what a turn wrote under a projected directory back here, before it goes.

    One `tar` per directory, of the paths named under it and nothing else, unpacked here
    over whatever was there -- refusing anything that would land outside. Never raises, for
    the reason :func:`_swept` does not, and waits no longer than :data:`_BRINGING` all told:
    this is the end of a turn, and whatever is not back by then is left.

    Args:
      client: The connection, which may already be broken.
      brings: What to bring, as :attr:`AnchorConfig.brings` says it.
      projected: Where each projected variable landed on the target.
      workspace: Where to run the commands from, as the target names it.
    """
    import io
    import tarfile
    import time

    wanted: dict[tuple[str, str], list[str]] = {}
    for named, into in brings:
        variable, _, under = named.partition("/")
        if (landed := projected.get(variable)) is not None:
            wanted.setdefault((landed, into), []).append(under)
    until = time.monotonic() + _BRINGING
    for (landed, into), paths in wanted.items():
        if (left := until - time.monotonic()) <= 0:
            log.warning("ran out of time bringing %s back from the target", into)
            return
        try:
            _, packed = _exchanged(
                client,
                ["/bin/sh", "-c", _PACK, "humanize", landed, *paths],
                workspace,
                within=left,
            )
            if packed:
                with tarfile.open(fileobj=io.BytesIO(packed)) as unpacking:
                    unpacking.extractall(into, filter="data")
        except (OSError, ValueError, tarfile.TarError) as why:
            log.warning("could not bring %s back from the target: %s", into, why)


def _written_back(
    client: RemoteClient, session: str, home: Virtual, workspace: str
) -> None:
    """Writes back what the CLI replaced of the links in its virtual home on the target.

    :data:`hmz.coganchor.homes.BACK`, for the home :func:`_homed` built. Never raises, for the
    reason :func:`_swept` does not.

    Args:
      client: The connection, which may already be broken.
      session: The private directory the home is in.
      home: What the virtual home is made of.
      workspace: Where to run the command from, as the target names it.
    """
    import posixpath

    from hmz.coganchor.homes import BACK, words

    landed = posixpath.join(session, home.variable.lower())
    try:
        status, said = _ran(
            client, ["/bin/sh", "-c", BACK, "humanize", landed, *words(home)], workspace
        )
    except (OSError, ValueError) as why:
        log.warning("could not write back what %s replaced: %s", landed, why)
        return
    if status != 0:
        log.warning("could not write back what %s replaced: %s", landed, said)


def _swept(client: RemoteClient, session: str, workspace: str) -> None:
    """Takes away everything this turn put on the target, whatever became of it.

    Never raises: this runs on the way out of a turn that may itself be on its way out badly,
    and a session that failed to tidy up must not turn into a session that failed.

    Args:
      client: The connection, which may already be broken.
      session: The private directory this turn's credentials and home went into, or "" for a
        turn that made none. It is this turn's alone, so it goes whole and without asking.
      workspace: Where to run the command from, as the target names it.
    """
    if not session:
        return
    try:
        status, said = _ran(
            client, ["/bin/sh", "-c", _SWEEP, "humanize", session], workspace
        )
    except (OSError, ValueError) as why:
        log.warning("could not clear %s from the target: %s", session, why)
        return
    if status != 0:
        log.warning("could not clear %s from the target: %s", session, said)


def _wrapping(hushes: Sequence[str], said: Mapping[str, str]) -> list[str]:
    """The `env` the CLI is started behind on the target, for what its environment cannot say.

    Two things have to be said on the target's own command line rather than in what is sent to
    it. A variable is *taken away* here, because the environment a command runs in there is
    composed there -- this machine's is layered onto the target's own, so a key in the target's
    shell profile survives merely not being sent. And a variable is *set* here where the target
    would strike it out on the way in: the ones that move a program's home are exactly the ones
    it reads as describing the wrong machine, and so are humanize's own, and both are things a
    turn taken here would have had.

    Every one of them is a name or a path rather than a secret. What the account actually is
    travels in the environment, which is not a command line.

    Args:
      hushes: The variables to run without.
      said: The variables to run with, by name.

    Returns:
      The words to put in front of the CLI. Always some: a turn always has at least what
      humanize marks it with to say, so there is no case worth a branch.
    """
    return [
        "env",
        *(word for name in sorted(hushes) for word in ("-u", name)),
        *(f"{name}={value}" for name, value in sorted(said.items())),
    ]


def _drives(
    client: RemoteClient,
    argv: list[str],
    cwd: str,
    environ: Mapping[str, str],
    fence: dict[str, Any] | None = None,
) -> int:
    """Runs the CLI on the target with this process's own streams, and waits for it.

    Byte for byte and without waiting for a line: the backends this exists for speak a framed
    protocol over these streams, and a relay that buffered would be a turn that never answers.

    Args:
      client: The open connection.
      argv: The CLI and its arguments, as the target is to run them.
      cwd: Where it works, as the target names it.
      environ: What to run it with, on top of the target's own.
      fence: What the target holds it to, as :func:`_fenced` says it, or None.

    Returns:
      Its exit status, or 128 plus the signal that killed it.
    """
    import selectors
    import signal as signals
    import threading

    from hmz.coganchor.proto import CHUNK_SIZE, Stream

    done = threading.Event()
    held: dict[str, Any] = {}

    def on_output(stream: Stream, data: bytes) -> None:
        sink = sys.stderr if stream is Stream.STDERR else sys.stdout
        sink.buffer.write(data)
        sink.buffer.flush()

    def on_exit(result: dict[str, Any] | None, error: OSError | None) -> None:
        held["result"], held["error"] = result, error
        done.set()

    handle = client.start_exec(
        argv, cwd, dict(environ), on_output, on_exit, fence=fence
    )

    def upward() -> None:
        """Carries what this process is given to the CLI, and says when there is no more.

        Watched for rather than read into, so that the thread ends when the turn does: a read
        that simply blocked would still be holding this process's input after the call had
        returned, and the next thing to read it would find its first bytes gone.
        """
        try:
            with selectors.DefaultSelector() as watching:
                watching.register(_STDIN, selectors.EVENT_READ)
                while not done.is_set():
                    if not watching.select(timeout=_LOOKING):
                        continue
                    if not (data := os.read(_STDIN, CHUNK_SIZE)):
                        return  # end of input, which the turn is told below
                    handle.send_stdin(data)
        except (OSError, ValueError):
            pass  # stdin closed under us, which is the end of the input either way
        finally:
            # Suppressed for the same reason the read above is: the far end may already be
            # gone, and a thread that raised on the way out would print a traceback over a
            # turn that had finished perfectly well.
            with contextlib.suppress(OSError, ValueError):
                handle.close_stdin()

    reading = threading.Thread(target=upward, name="hmz-anchor-stdin", daemon=True)
    reading.start()

    def onward(number: int, _frame: object) -> None:
        """Sends the signal on to the CLI, and steps out of the way if it is sent twice."""
        # The first is aimed at the CLI rather than swallowed here: a turn stopped by hand has
        # to stop the thing that is running, and one that stops is one whose own exit status
        # says so. The second is aimed at this process, because a CLI that did not stop for
        # the first is one somebody is now pressing the key at -- and a relay that answered
        # every one of them by forwarding would be a relay nobody can get out of.
        signals.signal(number, before.get(number) or signals.SIG_DFL)
        handle.signal(number)

    # Only from the main thread, which is the only one a handler may be installed from -- and
    # is where this runs, this process having been spawned to be exactly this.
    catching = (signals.SIGINT, signals.SIGTERM)
    main = threading.current_thread() is threading.main_thread()
    before: dict[int, Any] = {}
    if main:
        # `getsignal` answers None for a handler that was not installed from Python, and
        # `signal` will not take None back -- so what is remembered is the default instead,
        # which is what restoring one of those has to come to anyway.
        before = {
            number: signals.getsignal(number) or signals.SIG_DFL for number in catching
        }
        for number in catching:
            signals.signal(number, onward)
    try:
        done.wait()
    finally:
        for number, was in before.items():
            signals.signal(number, was)
        reading.join(timeout=_LOOKING * 2)
    if (error := held.get("error")) is not None:
        raise error
    return _status(held.get("result"))
