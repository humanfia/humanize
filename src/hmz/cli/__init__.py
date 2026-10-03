"""``hmz`` -- the whole command line, over layers that have none of their own.

    hmz
    hmz exec -f ralph_loop -a coder=claude/MODEL:high -p budget.cost=5 "$(cat TASK.md)"

There is one command anybody types, and everything else humanize keeps is walked at the
prompt: a listing with a noun in it for every store would be a second interface to learn, and
the one with the sheets in it is the interface.

The other command in the listing is `hmz internal`, which is the five lines humanize spawns
for itself gathered under one name. They are listed rather than hidden because a command
nobody can discover is a command nobody can debug, and a listing that leaves out half of what
a program runs says something untrue about it. What they are is said instead of concealed:
one door marked `internal`, so that `hmz --help` is the whole of what this program does and
still reads as one command anybody types.

A command imports what it needs when it is the one asked for, and no earlier. Two things turn
on that: `hmz exec` must not pay for the terminal interface it is not opening, and
`hmz internal anchor serve` is what the zipapp bootstrapped onto a target runs, where
coganchor is the only layer present and the architecture is whatever the target happens to be.

A command whose line takes a parser of its own has a module of its own here, so that reaching
one of them costs nothing for the others -- which is what `anchor.py`, `cred.py`, `fence.py`,
`hook.py` and `tools.py`, the five under `hmz internal`, are. `exec` has none: the line it takes is
read by :func:`hmz.runtime.runner.read_line`, since the terminal interface starts a flow from
the same parts.

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
    from collections.abc import Generator, MutableMapping

    from hmz.runtime import Run

__all__ = ["APART", "COMMANDS", "INTERNAL", "main", "many", "opens"]

#: What says whether runs may be held apart from the terminal at all, for a machine that
#: would rather they went with the window. `off`, `0` or `no`; anything else is silence, and
#: silence is runs held by a host wherever there is a terminal on both ends.
APART = "HUMANIZE_DAEMON"

#: How many times the runs held here are reached for before they are held in this process
#: instead, and how long apart: a host is a moment from going once its last frontend has.
_TRIES = 3
_AGAIN = 0.5


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

    Args:
      argv: What followed the command name.

    Returns:
      Zero, once the flow has returned.
    """
    from hmz.runtime import Hmz, Refused, telemetry

    from .output import Out, Shown

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
            # Nobody is at a prompt, so whoever is outside the run is away: a flow that asks
            # the person anything is answered with nothing, or its schema's defaults.
            running = hmz.run(
                line.flow,
                line.task,
                agents=line.agents,
                envs=line.envs,
                params=line.params,
                budget=line.budget,
                profile=line.profile,
                resume=line.resume,
            )
        except Refused as error:
            # A flow that is not there, or one given other roles than it declares, is a
            # command line that was wrong before anything ran, so it exits as argparse's
            # own rejections do. What the flow raises for itself is the flow's.
            print(f"hmz exec: error: {error}", file=sys.stderr)
            raise SystemExit(2) from error
        ended: list[int] = []
        try:
            # From the moment there is a run to stop: stopped before it has started, it lets
            # go of the drivers it was given all the same.
            with _ending(running, ended):
                running.watch(shown.heard)
                # An environment moved off the runtime its `-e` named, said as it is.
                running.noticed(lambda said: out.aside(f"hmz exec: {said}"))
                # Said and then run, never asked: a command line has nobody to ask, so what
                # it can do is say so plainly, on the stream that is not the answer.
                if blind := running.unreadable():
                    out.aside(f"hmz exec: {blind}")
                running.run()
        except Refused as error:
            if ended:
                # Refused only because the signal reached what it was asking too.
                raise SystemExit(128 + ended[0]) from None
            # An environment that could not be reached, or one short of what its role
            # needs, which is only known once it has been asked -- still before the flow ran.
            print(f"hmz exec: error: {error}", file=sys.stderr)
            raise SystemExit(2) from error
        except (KeyboardInterrupt, SystemExit):
            # Somebody stopping a run is not a run that went wrong.
            raise
        except BudgetExceeded as why:
            # Nor is a run that spent what it was allowed. It is the ordinary end of a
            # budgeted loop -- a flow with no exit of its own runs until its budget is gone,
            # which is what having one is for -- so it is said in a line rather than reported
            # as a crash and printed as a traceback nobody has anything to do about.
            out.aside(f"hmz exec: stopped -- {why}")
        except BaseException as why:
            if ended:
                # Nor is one an interrupt, a terminate or a hangup stopped, once it has let go
                # of what it made: it exits as the signal would have had it.
                raise SystemExit(128 + ended[0]) from None
            # Reported and then raised on exactly as it was: what a flow does when it fails
            # is the flow's business and the person at the terminal's, and this is only
            # humanize finding out that it happened.
            telemetry.crash(why, doing="hmz exec")
            raise
    if ended:
        raise SystemExit(128 + ended[0])
    return 0


@contextlib.contextmanager
def _ending(running: Run, ended: list[int]) -> Generator[None]:
    """Stops a run on an interrupt, a terminate or a hangup, while it runs.

    Left to themselves a terminate or a hangup would end the process where it stood, and what
    the run made would outlive it -- a container going on running until the next run on its
    provider found it. An interrupt left to itself is asyncio's, which cancels the flow and
    then raises on whatever the flow's cancelling ended in, as a traceback. Stopped here
    instead, all three the same way, the run unwinds and lets go of everything it made first.

    A second terminate or hangup while it does is ignored. A second interrupt is not: it is
    somebody at a terminal whose run is not letting go, and it ends the process there and
    then, as the interrupt would have without any of this -- which is the one way out of an
    unwinding that hangs that does not need another terminal.

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

    def ends(signum: int, _frame: object) -> None:
        # Once: a second is the run already letting go of what it made, which cancelling it
        # again would cut short -- but for an interrupt, which is asked to cut it short.
        if not ended:
            ended.append(signum)
            told.set()
        elif signum == signal.SIGINT:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            os.kill(os.getpid(), signal.SIGINT)

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


def _anchor(argv: list[str]) -> int:
    """Runs the agent named on the command line, with its work landing on another machine.

    Args:
      argv: What followed the command name.

    Returns:
      The agent's exit status, or one of our own if it never ran.
    """
    from .anchor import anchor

    return anchor(argv)


def _cred(argv: list[str]) -> int:
    """Runs a program whose credentials are kept somewhere other than where it looks.

    Args:
      argv: What followed the command name.

    Returns:
      The program's exit status, or one of our own if it never ran.
    """
    from .cred import cred

    return cred(argv)


def _fence(argv: list[str]) -> int:
    """Runs a program walled in to what its flow's permission lets it reach.

    Args:
      argv: What followed the command name.

    Returns:
      The program's exit status, or one of our own if it never ran.
    """
    from .fence import fence

    return fence(argv)


def _tools(argv: list[str]) -> int:
    """Carries the tool protocol between a coding agent and the flow whose callbacks it is.

    Args:
      argv: What followed the command name.

    Returns:
      Zero once either end has gone, or one for a flow that is no longer there.
    """
    from .tools import tools

    return tools(argv)


def _hook(argv: list[str]) -> int:
    """Carries one call of a coding agent's own hook table to the flow whose moment it is.

    Args:
      argv: What followed the command name.

    Returns:
      Zero, whatever the flow said and whether or not it was there to say it.
    """
    from .hook import hook

    return hook(argv)


def _internal(argv: list[str]) -> int:
    """Routes to whichever of the lines humanize spawns for itself was named.

    The same routing as the top of the line, one level down, and for the same reason: a name
    it knows is handed the rest of the line untouched, so that `hmz internal anchor --help` is
    answered by the anchor's own parser rather than eaten by this one, and reaching one of
    them loads no module of any other. Anything else -- a name nobody has, or nothing at all
    -- is answered by a parser built here, which lists the five and exits.

    Args:
      argv: What followed `internal`, beginning with the name of one of them.

    Returns:
      That command's exit status.
    """
    if not argv or argv[0] not in INTERNAL:
        import argparse

        # Its own parser rather than a subparser of the one at the top: the top-level help
        # names the commands and not what they take, so this is where the five are written
        # out, and it is reached only when somebody asks about them.
        parser = argparse.ArgumentParser(
            prog="hmz internal",
            description="Commands humanize spawns for itself, listed for debugging. "
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


def _line() -> ArgumentParser:
    """The line `hmz` itself takes, which is how the interface is opened.

    It takes nothing at all: which flow runs and what drives it are chosen at the prompt,
    and whether the run is held apart from this terminal is read off the terminal rather than
    asked for -- a run nobody can walk away from is not a thing to want. What is left is a
    parser that names the program and refuses anything else, built here rather than where it
    is parsed because the help asks it what `hmz` takes.

    Returns:
      The parser, without the commands: whoever wants those adds them.
    """
    import argparse

    return argparse.ArgumentParser(
        prog="hmz",
        description="Orchestrate, execute, and observe agent flows. Running without a "
        "command opens the terminal interface where this directory left off.",
        epilog="Run `hmz COMMAND --help` for more information on a command.",
    )


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
    """Opens the interface, in this process, on the runs held for this directory.

    Runs of a flow outlive the terminal they were started from, which is what makes leaving
    one running an answer to `/exit`: a host holds this directory's runs where nothing has to
    be reading them, and every interface opened here -- this one, one in the next terminal,
    one a colleague opened over ssh -- is one more frontend of the same runs, each whole and
    each its own. So a line that opens the interface reads the runs a host already holds
    here, and starts a host where none is.

    A terminal on both ends is what makes that worth doing. With nobody to read it -- output
    going to a file, a test driving the interface itself -- the runs are held in this process
    instead, and go with it.

    Returns:
      Zero, once the interface has been closed; one where the runs let go of it first.
    """
    if not (_apart_is_wanted() and _at_a_terminal()):
        return _here()

    import time

    from hmz import daemon
    from hmz.daemon.proto import PROTOCOL

    failed: OSError | None = None
    for _ in range(_TRIES):
        found = daemon.running()
        if found is not None and found.protocol != PROTOCOL:
            # This machine's runs held by an older humanize, which nothing here can read and
            # which a second daemon beside it would fight over the socket with.
            print(f"hmz: {daemon.older(found)}", file=sys.stderr)
            return 1
        try:
            link = (found or daemon.host()).link(kind="tui")
            break
        except OSError as why:
            failed = why
            # A host found on its way out -- the last interface on it has just gone -- is
            # found gone the next time, and one started in its place.
            time.sleep(_AGAIN)
    else:
        # A machine that will not fork, a home directory that cannot be written, a socket
        # that will not bind: none of those is a reason not to open the interface. What is
        # lost is being able to walk away from the runs, which is said and then done without.
        print(
            f"hmz: runs cannot be detached from the terminal ({failed}), so "
            "they will run in this process instead",
            file=sys.stderr,
        )
        return _here()
    from hmz.tui import Humanize

    app = Humanize(link=link)
    app.run()
    return app.return_code or 0


def _here() -> int:
    """Opens the interface in this process, holding this directory's runs itself."""
    from hmz.tui import Humanize

    app = Humanize()
    app.run()
    return app.return_code or 0


def _apart_is_wanted() -> bool:
    """Whether this machine wants a run held apart from the terminal at all.

    Answered for one process without writing anything down, the way the reporting question
    is: a scripted install, a machine somebody would rather have the run go with the window
    on, and this suite are all one variable rather than a line each of them has to remember
    to pass.

    Returns:
      Whether to hold one. False only where the variable says so outright.
    """
    import os

    return os.environ.get(APART, "").strip().lower() not in ("off", "0", "no")


def _at_a_terminal() -> bool:
    """Whether there is a terminal on both ends of this process to walk away from.

    Runs held apart from the terminal are worth holding so only where somebody could come
    back to them: output going to a file and input coming from a pipe are runs held here, in
    this process, exactly as they always were.

    Returns:
      Whether there is one.
    """
    return sys.stdin.isatty() and sys.stdout.isatty()


#: What humanize spawns for itself, each as what carries it out and the line `hmz internal`
#: shows it as. A turn taken as an account runs the CLI with the paths it keeps its
#: credentials at pointed into that account's directory, and the supervisor doing the pointing
#: has to be a process of its own -- it forks the program and takes the signal handling with
#: it, which a flow pumping turns from threads of its own has none to lend. A flow's own
#: callbacks are the same shape the other way round: a CLI takes a tool by starting a program,
#: so there is a program, and it does nothing but carry the protocol back to the process the
#: callbacks are in. A moment of a flow's is that same shape once more: a CLI takes a hook by
#: starting a program and waiting for what it says, which is the one place a `PreToolUse` can
#: be refused rather than watched. An anchored turn is the fourth: `AnchorConfig.command()`
#: renders one for every turn whose work lands on another machine, and the zipapp
#: bootstrapped onto a target answers it by running `hmz internal anchor serve`. A fenced turn
#: is the fifth, and the same shape as the first: the wall around a CLI is put up by the
#: process it walls in, and the one serving its proxy has to stay outside it. All five are
#: a command line because there is no other way to start a process, and none of them is a line
#: anybody types -- which is a reason to keep them together under one name and behind one
#: sentence saying so, and not a reason to keep them out of the listing. A command that is not
#: in the listing is one nobody can look up when it is the thing that failed, and every one of
#: these fails where a person is reading: a relay that could not reach a flow, a supervisor
#: whose program was not there, a target that answered nothing.
INTERNAL = {
    "anchor": (_anchor, "run an agent turn on another machine"),
    "cred": (_cred, "run a program with credentials from an account"),
    "fence": (_fence, "run a program held to what its flow permits"),
    "hook": (_hook, "relay agent hooks to a flow"),
    "tools": (_tools, "relay agent tool calls to a flow"),
}

#: Each command, as what carries it out and the line a listing shows it as. One is for
#: anybody: running a flow in a directory is what a line is for, and everything else humanize
#: keeps is walked at the prompt rather than typed -- a run already held here included, which
#: `hmz` with no command opens. The other is the door onto :data:`INTERNAL` -- one entry
#: rather than four, so that what a person may type stays one line long while what humanize
#: runs stays something they can read. There is no command for the terminal interface either:
#: naming nothing at all is how it opens.
COMMANDS = {
    "exec": (_exec, "run an agent flow in this directory"),
    "internal": (_internal, "internal commands used by humanize; do not run directly"),
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
        # door onto what humanize spawns for itself -- a listing that showed only the line a
        # person types would be describing a different program from the one that runs. It
        # knows the commands by name and not by what they take -- each one answers
        # `hmz COMMAND --help` itself.
        parser = _line()
        commands = parser.add_subparsers(metavar="COMMAND", required=True)
        for name, (_, summary) in COMMANDS.items():
            commands.add_parser(name, help=summary, add_help=False)
        parser.parse_args(arguments)

    return COMMANDS[arguments[0]][0](arguments[1:])
