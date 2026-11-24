"""``hmz`` -- the whole command line, over layers that have none of their own.

    hmz
    hmz exec -f ralph_loop -a coder=claude/MODEL:high -p budget.cost=5 "$(cat TASK.md)"
    hmz chat -a claude/MODEL:high "what does this repository do?"

A few commands anybody types -- running a flow, saying one message to an agent, serving the web
interface, backing an epic up to git repositories, and moving Humanize itself to its newest
release -- and everything else Humanize keeps is walked at the prompt: a listing with a noun in
it for every store would be a second interface to learn, and the one with the sheets in it is
the interface.

The other command in the listing is `hmz internal`, which is the six lines Humanize spawns
for itself gathered under one name. They are listed rather than hidden because a command
nobody can discover is a command nobody can debug, and a listing that leaves out half of what
a program runs says something untrue about it. What they are is said instead of concealed:
one door marked `internal`, so that `hmz --help` is the whole of what this program does and
still reads as the few commands anybody types.

A command imports what it needs when it is the one asked for, and no earlier: `hmz exec` must
not pay for the terminal interface it is not opening.

A command whose line takes a parser of its own has a module of its own here, so that reaching
one of them costs nothing for the others -- which is what `chat.py`, `web.py`, `update.py`,
`backup.py`, and `cli.py`, `hook.py` and `tools.py`, three of the six under `hmz internal`, are.
The other three -- `anchor`, `cred` and `fence` -- are `coganchor`'s, which this process
becomes. `exec` has none: the line it takes is read by :func:`hmz.runtime.runner.read_line`,
since the terminal interface starts a flow from the same parts.

:mod:`hmz.cli.output` is the one module every command may reach: who is reading -- somebody at
a terminal, or a program -- is one question rather than one per command, and it costs nothing
to ask.
"""

from __future__ import annotations

import contextlib
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from argparse import ArgumentParser
    from collections.abc import Callable, Generator, MutableMapping

    from hmz.sdk import Run
    from hmz.tui import Humanize

__all__ = ["COMMANDS", "INTERNAL", "main", "many", "opens", "summaries"]

#: How long a second interrupt waits for the daemon to say it forced the epic.
_FORCING = 5.0

#: How often `hmz exec` asks whether the backups of its epic are done.
_LOOKING = 0.5

#: How long the interface waits, once it is closed, for the backups it queued itself.
_CLOSING = 15.0


def many(count: int | str, thing: str) -> str:
    """How many of something there are, said as English says it.

    Here rather than beside either line that prints one: a listing that says `1 sessions` is
    a line that reads as a template nobody finished, and there is one rule about that.

    Args:
      count: How many, as a number or as whatever counted them.
      thing: What they are, in the singular.

    Returns:
      The two words -- `1 session`, `3 sessions`.
    """
    return f"{count} {thing}" if str(count) == "1" else f"{count} {thing}s"


def _prepare_textual_terminal(
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """Keeps Textual's extended keys off a direct iTerm2 session.

    iTerm2 loses IME-composed text when Textual asks it to report every key with associated
    text. A tmux between them handles that protocol correctly, so only the direct path needs
    Textual's own opt-out. An explicit setting belongs to whoever launched the process.

    Args:
      environ: The process environment, or another mapping for a caller testing the choice.
    """
    import os

    target = os.environ if environ is None else environ
    direct_iterm = not target.get("TMUX") and (
        target.get("TERM_PROGRAM") == "iTerm.app"
        or target.get("LC_TERMINAL") == "iTerm2"
    )
    if direct_iterm:
        target.setdefault("TEXTUAL_DISABLE_KITTY_KEY", "1")


def _exec(argv: list[str]) -> int:
    """Runs the flow named on the command line, on what it names, to its return.

    What the run looks like while it happens is settled here rather than by each backend
    teeing its own progress: watching every session is what makes one run read as one run,
    whichever CLIs it was given, and watching one is what stops that tee.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, once the flow has returned.
    """
    import signal

    try:
        return _executes(argv)
    except KeyboardInterrupt:
        # An interrupt that came before the run was there to stop -- or after it had let go
        # of everything -- which leaves nothing to unwind. It is somebody stopping the line,
        # and it exits as the interrupt would have had it, without a traceback.
        raise SystemExit(128 + signal.SIGINT) from None


def _executes(argv: list[str]) -> int:
    """What :func:`_exec` does, before an interrupt anywhere in it is made an exit status.

    The epic is held by this machine's daemon, on an exec slot of its own: this follows it
    there to its end, and whatever ends this process but a signal leaves it going.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, once the flow has returned; one where it failed.
    """
    import asyncio

    from hmz.runtime import Refused
    from hmz.sdk import Hmz

    from .output import Out, Shown, unreached

    hmz = Hmz()
    # If it has been answered yes, and never otherwise: a run with nobody at a terminal is a
    # run with nobody to ask, and silence is not an answer.
    hmz.reports()
    line = hmz.read(argv)
    # Only now that the line is known to name a flow: `--help` has already exited inside the
    # reading above, and a line that runs nothing must not pay for the flow API to learn the
    # name of what a run that spent its budget raises.
    from hmz.flows import BudgetExceeded

    with Out(as_json=line.as_json) as out, Shown(out) as shown:
        try:
            # Nobody is at a prompt, so whoever is outside the epic is away: a flow that asks
            # the person anything is answered with nothing, or its schema's defaults.
            running = hmz.run(
                line.flow,
                line.task,
                agents=line.agents,
                envs=line.envs,
                params=line.params,
                budget=line.budget,
                profile_flow=line.profile_flow,
                profile_environment=line.profile_environment,
                resume=line.resume,
                backup=line.backup,
            )
        except Refused as error:
            # A flow that is not there, or one given other roles than it declares, is a
            # command line that was wrong before anything ran, so it exits as argparse's
            # own rejections do. What the flow raises for itself is the flow's.
            print(f"hmz exec: error: {error}", file=sys.stderr)
            raise SystemExit(2) from error
        except OSError as error:
            print(unreached(error), file=sys.stderr)
            raise SystemExit(1) from error
        ended: list[int] = []
        running.watch(shown.heard)
        running.opened(shown.opened)
        running.printed(out.printed)
        # What the host notes before the flow is called, said as it is on the stream that is
        # not the answer: a cost limit no price can enforce, an environment moved off the
        # runtime its `-e` named. Said here from the check as well, the first is said twice.
        running.noticed(lambda said: out.aside(f"hmz exec: {said}"))
        try:
            with _ending(running, ended):
                running.run()
        except Refused as error:
            if ended:
                # Refused only because the signal reached what it was asking too.
                raise SystemExit(128 + ended[0]) from None
            # An environment that could not be reached, or one short of what its role
            # needs, which is only known once it has been asked -- still before the flow ran.
            print(f"hmz exec: error: {error}", file=sys.stderr)
            raise SystemExit(2) from error
        except OSError as error:
            print(unreached(error), file=sys.stderr)
            raise SystemExit(1) from error
        except (KeyboardInterrupt, SystemExit):
            # Somebody stopping a run is not a run that went wrong.
            raise
        except BudgetExceeded as why:
            # Nor is a run that spent what it was allowed. It is the ordinary end of a
            # budgeted loop -- a flow with no exit of its own runs until its budget is gone,
            # which is what having one is for -- so it is said in a line rather than reported
            # as a crash and printed as a traceback nobody has anything to do about.
            out.aside(f"hmz exec: stopped -- {why}")
        except (RuntimeError, asyncio.CancelledError) as why:
            if ended:
                # Nor is one an interrupt, a terminate or a hangup stopped, once it has let go
                # of what it made: it exits as the signal would have had it.
                raise SystemExit(128 + ended[0]) from None
            # What the epic's host said of how it failed -- the exception, or the traceback,
            # which the host has reported where reporting was answered yes -- said as it was.
            out.aside(str(why) or type(why).__name__)
            return 1
        finally:
            # Not after a signal, on which it exits as soon as the epic has ended (Section
            # 7.15.1 of cli.md).
            if not ended:
                _backs_up(running, out.aside)
    if ended:
        raise SystemExit(128 + ended[0])
    return 0


def _backs_up(running: Run, say: Callable[[str], object]) -> None:
    """Waits for the backups of an epic that has ended, for so long, and lets go of it.

    Attached all the while, as the run stays until its backups are done, so that its host
    waits for them too (Section 7.11.4 and Section 7.11.5 of cli.md). Asked of the daemon that
    held it, over a session of its own, and never of one started to answer.

    Args:
      running: The run.
      say: What a line on standard error is said through.
    """
    import time

    from hmz.reach import dial
    from hmz.runtime import Refused
    from hmz.sdk.client import Client
    from hmz.sdk.running import BACKING, backed

    epic = running.epic
    if epic is None or not running.wait(0):
        # Never started, or let go of before it ended: there is nothing to wait for here.
        return
    try:
        with Client.over(dial("unix:"), kind="cli") as client:
            if backed(client, epic.name):
                return
            say("hmz exec: backing the epic up")
            ending = time.monotonic() + BACKING
            while time.monotonic() < ending:
                time.sleep(_LOOKING)
                if backed(client, epic.name):
                    return
        say(
            f"hmz exec: a backup took longer than {BACKING:.0f}s and was left; "
            "`hmz backup EPIC` sends it again"
        )
    except (OSError, ValueError, Refused):
        # The daemon gone: nothing is left to wait on.
        return
    finally:
        running.close()


@contextlib.contextmanager
def _ending(running: Run, ended: list[int]) -> Generator[None]:
    """Stops the epic on an interrupt, a terminate or a hangup, while this follows it.

    The daemon holds the epic, so this process ending any other way leaves it going. A signal
    is somebody stopping it: the epic is told to stop, unwinds and lets go of everything it
    made, and this waits for it to end before exiting as the signal would have had it.

    A second terminate or hangup while it does is ignored. A second interrupt is not: it is
    somebody at a terminal whose epic is not letting go, and it forces it -- every session
    with a turn open is closed -- and ends the process there and then.

    Args:
      running: The run.
      ended: Where the signal that stopped it is written, once one has.
    """
    import os
    import signal
    import threading

    # The stopping is done by a thread waiting for the word rather than on the signal's own
    # frame, which may be holding a lock the stopping takes -- the run's, or the one
    # threading takes to start a thread.
    told = threading.Event()

    def stops() -> None:
        told.wait()
        if ended:
            running.stop()

    def forces() -> None:
        # The epic's sessions closed under whatever turn is open, then this process ended
        # as the interrupt would have ended it -- after a moment at most, however slow the
        # daemon is to say it has.
        closing = threading.Thread(target=running.close, daemon=True)
        closing.start()
        closing.join(_FORCING)
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGINT)

    def ends(signum: int, _frame: object) -> None:
        # Once: a second is the epic already letting go of what it made, which stopping it
        # again would cut short -- but for an interrupt, which is asked to cut it short.
        if not ended:
            ended.append(signum)
            told.set()
        elif signum == signal.SIGINT:
            threading.Thread(
                target=forces, daemon=True, name="humanize-forcing"
            ).start()

    was: dict[int, Any] = {}
    for one in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        with contextlib.suppress(ValueError):  # off the main thread, where none reaches
            # A signal somebody chose to have ignored -- a hangup under `nohup`, an interrupt
            # to a job a script put in the background -- stays so.
            if signal.getsignal(one) != signal.SIG_IGN:
                was[one] = signal.signal(one, ends)
    threading.Thread(target=stops, daemon=True, name="humanize-ending").start()
    try:
        yield
    finally:
        for one, before in was.items():
            # None for a handler that was not put there from Python, which is put back as the
            # default it most likely was.
            signal.signal(one, signal.SIG_DFL if before is None else before)
        told.set()


def _coganchor(command: str, argv: list[str]) -> int:
    """Hands an internal command to `coganchor`, which carries out the anchor's three.

    This process becomes that program, so nothing after this call runs where there is one.

    Args:
      command: `anchor`, `fence` or `cred`.
      argv: What followed the command's name.

    Returns:
      127, having said so, where no `coganchor` is built for this machine.
    """
    import os
    import platform

    from hmz.coganchor import binary

    program = binary.found()
    if program is not None:
        # And told where the builds for other machines are, as every `coganchor` started here
        # is (`binary.here`): it ships the one a target needs from there.
        os.environ.setdefault(binary.BINARIES, str(binary.shelf()))
        os.execv(program, [str(program), *binary.translated(command, argv)])  # noqa: S606
    print(
        "hmz: no coganchor is built for this machine "
        f"({platform.system()} {platform.machine()})",
        file=sys.stderr,
    )
    return 127


def _anchor(argv: list[str]) -> int:
    """Runs the agent named on the command line, with its work landing on another machine.

    Args:
      argv: What followed the command name.

    Returns:
      127 where there is no `coganchor` to run it; otherwise this process becomes it.
    """
    return _coganchor("anchor", argv)


def _cred(argv: list[str]) -> int:
    """Runs a program whose credentials are kept somewhere other than where it looks.

    Args:
      argv: What followed the command name.

    Returns:
      127 where there is no `coganchor` to run it; otherwise this process becomes it.
    """
    return _coganchor("cred", argv)


def _fence(argv: list[str]) -> int:
    """Runs a program walled in to what its flow's permission lets it reach.

    Args:
      argv: What followed the command name.

    Returns:
      127 where there is no `coganchor` to run it; otherwise this process becomes it.
    """
    return _coganchor("fence", argv)


def _tools(argv: list[str]) -> int:
    """Carries the tool protocol between a coding agent and the flow whose callbacks it is.

    Args:
      argv: What followed the command name.

    Returns:
      Zero once either end has gone, or one for a flow that is no longer there.
    """
    from .tools import tools

    return tools(argv)


def _cli(argv: list[str]) -> int:
    """Carries one run of a flow's own command line to the flow whose function answers it.

    Args:
      argv: What followed the command name.

    Returns:
      What the flow said the program exits with, or one for a flow that is no longer there.
    """
    from .cli import cli

    return cli(argv)


def _hook(argv: list[str]) -> int:
    """Carries one call of a coding agent's own hook table to the flow whose moment it is.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, whatever the flow said and whether or not it was there to say it.
    """
    from .hook import hook

    return hook(argv)


def _chat(argv: list[str]) -> int:
    """Says one message to an agent in this directory, and prints what it answered.

    Args:
      argv: What followed the command name.

    Returns:
      Zero once the turn is done; one where it failed or the daemon could not be reached.
    """
    from .chat import chat

    return chat(argv)


def _web(argv: list[str]) -> int:
    """Serves this directory's runs to a browser on this machine, until interrupted.

    Args:
      argv: What followed the command name.

    Returns:
      Zero once it has been interrupted; one where it could not be served.
    """
    from .web import web

    return web(argv)


def _daemon(argv: list[str]) -> int:
    """Runs, reaches, pairs or installs this machine's daemon.

    Args:
      argv: What followed the command name.

    Returns:
      That command's exit status.
    """
    from .daemon import daemon

    return daemon(argv)


def _relay(argv: list[str]) -> int:
    """Serves a relay daemons register with and devices reach them through, until stopped.

    Args:
      argv: What followed the command name.

    Returns:
      Zero once it has been stopped; one where it could not listen.
    """
    from .relay import relay

    return relay(argv)


def _update(argv: list[str]) -> int:
    """Moves this install of Humanize to its newest release, with whatever installed it.

    Args:
      argv: What followed the command name.

    Returns:
      Zero once it is the newest release; one where it could not be made so.
    """
    from .update import update

    return update(argv)


def _backup(argv: list[str]) -> int:
    """Backs one epic up to git repositories now, and says how it went.

    Args:
      argv: What followed the command name.

    Returns:
      Zero where every target took it; one where one did not.
    """
    from .backup import backup

    return backup(argv)


def _internal(argv: list[str]) -> int:
    """Routes to whichever of the lines Humanize spawns for itself was named.

    The same routing as the top of the line, one level down, and for the same reason: a name
    it knows is handed the rest of the line untouched, so that `hmz internal anchor --help` is
    answered by the anchor's own parser rather than eaten by this one, and reaching one of
    them loads no module of any other. Anything else -- a name nobody has, or nothing at all
    -- is answered by a parser built here, which lists the six and exits.

    Args:
      argv: What followed `internal`, beginning with the name of one of them.

    Returns:
      That command's exit status.
    """
    if not argv or argv[0] not in INTERNAL:
        import argparse

        # Its own parser rather than a subparser of the one at the top: the top-level help
        # names the commands and not what they take, so this is where the six are written
        # out, and it is reached only when somebody asks about them.
        parser = argparse.ArgumentParser(
            prog="hmz internal",
            description="Commands Humanize spawns for itself, listed for debugging. "
            "Not intended to be run directly.",
            epilog="Run `hmz internal COMMAND --help` for more information on a "
            "command.",
        )
        commands = parser.add_subparsers(metavar="COMMAND", required=True)
        for name, (_, summary) in INTERNAL.items():
            commands.add_parser(name, help=summary, add_help=False)
        # Says which there are and exits, so nothing below this runs.
        parser.parse_args(argv)

    return INTERNAL[argv[0]][0](argv[1:])


def _line(*, plain: bool = False) -> ArgumentParser:
    """The line `hmz` itself takes, which is how the interface is opened.

    It takes nothing at all: which flow runs and what drives it are chosen at the prompt,
    and whether the run is held apart from this terminal is read off the terminal rather than
    asked for -- a run nobody can walk away from is not a thing to want. What is left is a
    parser that names the program and refuses anything else. Its help is not argparse's flat
    listing but the page `hmz help` writes (:func:`hmz.cli.commands.help.top`): the commands
    under what they are about, what they share, and what to run next.

    Args:
      plain: Whether that page is written without escapes whatever is reading it.

    Returns:
      The parser, without the commands: whoever wants those adds them.
    """
    import argparse

    class Line(argparse.ArgumentParser):
        def format_help(self) -> str:
            from .commands.help import top

            return top(colour=False if plain else None)

    return Line(prog="hmz")


def summaries() -> dict[str, str]:
    """Every command there is, with the line a listing shows it as.

    Those that read their own line (:data:`COMMANDS`) and then those written as declarations
    (:mod:`hmz.cli.tree`), which is the order a line is routed in: a name in both is the
    first's.

    Returns:
      Each command's summary by its name.
    """
    from hmz.words import t

    from . import tree

    found = {name: summary for name, (_, summary) in COMMANDS.items()}
    for name, command in tree.commands().items():
        found.setdefault(name, t(command.summary))
    return found


def _tui() -> int:
    """Opens the terminal interface, as this directory left it.

    The line says nothing about what to run: which flow, what drives it and what it is set up
    with are chosen at the prompt, and what was chosen there is what the next `hmz` opens on.
    Nothing is started either -- the interface opens ready, and what starts it is still the
    first thing said.

    Returns:
      Zero, once the interface has been closed.
    """
    # Textual reads this once, while it is imported, so the terminal must be prepared before
    # reaching the lazily imported interface below.
    _prepare_textual_terminal()

    return opens()


def opens() -> int:
    """Opens the interface, in this process, as a frontend of this machine's daemon.

    Epics outlive the terminal they were started from, which is what makes leaving one
    running an answer to `/exit`: a host of the daemon holds this directory's epics where
    nothing has to be reading them, and every interface opened here -- this one, one in the
    next terminal, one a colleague opened over ssh -- is one more frontend of the same epics,
    each whole and each its own. The daemon is started where none runs.

    Returns:
      Zero, once the interface has been closed; one where the daemon let go of it first, or
      could not be reached.
    """
    from hmz import daemon

    from .output import Out

    try:
        # Reaching a daemon can mean starting one, which takes long enough on a blank terminal
        # to read as nothing happening. The clock says otherwise, and is gone, line and all,
        # before the interface takes the screen.
        with Out() as out:
            out.spins(lambda: "connecting to the runs held here")
            link = daemon.attach("tui")
    except daemon.Older as why:
        # This machine's runs held by an older Humanize, which nothing here can read and
        # which a second daemon beside it would fight over the socket with.
        print(f"hmz: {why}", file=sys.stderr)
        return 1
    except OSError as failed:
        print(f"hmz: the daemon cannot be reached: {failed}", file=sys.stderr)
        return 1
    from hmz.tui import Humanize

    return _closes(Humanize(link=link))


def _closes(app: Humanize) -> int:
    """Runs the interface, then lets the backups this process queued finish, for so long.

    An epic backed up from `/epics`, or one whose runs this process held, is backed up by
    nothing but this process: going at once would drop it, and waiting for ever on a remote
    that does not answer would hold up a terminal somebody has finished with.

    Args:
      app: The interface.

    Returns:
      What it closed with.
    """
    from hmz.runtime import Hmz

    app.run()
    backups = Hmz().backups
    if not backups.wait(0):
        print("hmz: backing epics up", file=sys.stderr)
        try:
            done = backups.wait(_CLOSING)
        except KeyboardInterrupt:  # not waited for, which is leaving them as well
            done = False
        if not done:
            print(
                f"hmz: a backup took longer than {_CLOSING:.0f}s and was left; "
                "`hmz backup EPIC` sends it again",
                file=sys.stderr,
            )
    return app.return_code or 0


#: What Humanize spawns for itself, each as what carries it out and the line `hmz internal`
#: shows it as. A turn taken as an account runs the CLI with the paths it keeps its
#: credentials at pointed into that account's directory, and the supervisor doing the pointing
#: has to be a process of its own -- it forks the program and takes the signal handling with
#: it, which a flow pumping turns from threads of its own has none to lend. A flow's own
#: callbacks are the same shape the other way round: a CLI takes a tool by starting a program,
#: so there is a program, and it does nothing but carry the protocol back to the process the
#: callbacks are in. A moment of a flow's is that same shape once more: a CLI takes a hook by
#: starting a program and waiting for what it says, which is the one place a `PreToolUse` can
#: be refused rather than watched. An anchored turn is the fourth: `AnchorConfig.command()`
#: renders one for every turn whose work lands on another machine, and the `coganchor`
#: shipped to a target answers it by running `coganchor anchor`. A fenced turn
#: is the fifth, and the same shape as the first: the wall around a CLI is put up by the
#: process it walls in, and the one serving its proxy has to stay outside it. A flow's own
#: command line is the sixth: a shell runs a program by finding a file on its PATH, so the
#: file is a script that starts a program carrying the run back to the flow. All six are
#: a command line because there is no other way to start a process, and none of them is a line
#: anybody types -- which is a reason to keep them together under one name and behind one
#: sentence saying so, and not a reason to keep them out of the listing. A command that is not
#: in the listing is one nobody can look up when it is the thing that failed, and every one of
#: these fails where a person is reading: a relay that could not reach a flow, a supervisor
#: whose program was not there, a target that answered nothing.
INTERNAL = {
    "anchor": (_anchor, "run an agent turn on another machine"),
    "cli": (_cli, "relay agent runs of a flow's command line to the flow"),
    "cred": (_cred, "run a program with credentials from an account"),
    "fence": (_fence, "run a program held to what its flow permits"),
    "hook": (_hook, "relay agent hooks to a flow"),
    "tools": (_tools, "relay agent tool calls to a flow"),
}

#: Each command, as what carries it out and the line a listing shows it as. Seven are for
#: anybody: running a flow in a directory, saying one message to an agent there, serving the
#: web interface, running, reaching and pairing this machine's daemon, serving a relay daemons
#: and devices meet through, moving Humanize itself to its newest release, and backing an
#: epic up from a script -- everything else Humanize keeps is walked at the prompt rather
#: than typed, a run already held here included, which `hmz` with no command opens.
#: The last is the door onto :data:`INTERNAL` -- one entry rather than six, so that what a
#: person may type stays short while what Humanize runs stays something they can read. There
#: is no command for the terminal interface either: naming nothing at all is how it opens.
COMMANDS = {
    "exec": (_exec, "run an agent flow in this directory"),
    "chat": (_chat, "say one message to an agent in this directory"),
    "web": (_web, "open this machine's epics in a browser on it"),
    "daemon": (_daemon, "run, reach, pair and install this machine's daemon"),
    "relay": (_relay, "relay daemons and the devices that reach them"),
    "update": (_update, "update hmz to its newest release"),
    "backup": (_backup, "back epics up to git repositories, or download them"),
    "internal": (_internal, "internal commands used by Humanize; do not run directly"),
}


def main(argv: list[str] | None = None) -> int:
    """Runs the command named on the command line, or opens the interface if none is.

    Args:
      argv: The arguments to parse, defaulting to this process's own.

    Returns:
      The command's exit status.
    """
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        return _tui()
    if arguments[0] not in COMMANDS:
        from . import tree

        # A command written as a declaration (`hmz.cli.commands`): the tree reads its line.
        if arguments[0] in tree.commands():
            return tree.runs(arguments)
        if arguments == ["--version"]:
            # Read from the installed metadata, which costs more to reach than everything
            # else here put together -- so it is reached only when it is what was asked for.
            from importlib.metadata import version

            print(f"hmz {version('hmz')}")
            return 0
        # Anything else naming no command it knows: argparse says which was meant and exits,
        # so nothing below it runs.

        # The same line `hmz` itself takes, with the commands added: one help, saying both
        # what may be opened and what may be run, since both are `hmz` and somebody typing
        # `hmz --help` is asking about the whole of it. Every command is in it, including the
        # door onto what Humanize spawns for itself -- a listing that showed only the line a
        # person types would be describing a different program from the one that runs. It
        # knows the commands by name and not by what they take -- each one answers
        # `hmz COMMAND --help` itself.
        parser = _line(plain="--no-color" in arguments)
        commands = parser.add_subparsers(metavar="COMMAND", required=True)
        for name in summaries():
            commands.add_parser(name, add_help=False)
        parser.parse_args(arguments)

    return COMMANDS[arguments[0]][0](arguments[1:])
