"""What the editor offers to finish, which is the only way anything is typed here.

A command line is typed, never filled in on a form: `/` offers the commands, `/settings`
its pages, and `/flow` the flows there are -- the ones humanize ships, the ones installed out
of a flowverse, and this project's own and yours. Never a flow a flowverse only lists: that is
one to install from `/flow` before there is anything to run. So does `$`, which is the flow
said outright rather than chosen from a menu: the same list, under the sigil that starts one.
A flow anywhere else is a path, and a path is typed: looking for one would mean reading every
Python file below here to see which declare a flow, which is a guess, and far too slow to make
between keystrokes.

`hmz internal anchor` is not offered: it is not something to do to a flow while it runs, and
it takes a command line of its own. What a run left behind is `/epics`, which is where the runs are.

A path written on a form is finished as well, as a shell finishes one (:func:`paths`): where an
export lands is a file or a directory somebody has to spell, and spelling a path a letter at a
time with nothing to say what is there is spelling it wrong.
"""

from __future__ import annotations

import functools
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from hmz.runtime.flowing import Offer

    from .app import Humanize

__all__ = ["VIEWS", "Command", "hinted", "offered", "paths"]

#: Every view a command can be typed in: the monitor, the transcript every agent is on, one
#: agent's or one conversation's, and what one outworlder asks.
VIEWS = frozenset({"monitor", "aggregate", "session", "outworlder"})


@dataclass(frozen=True)
class Command:
    """One command of the editor, declared once and whole.

    Everything there is to know about a command is here: what it is called, what it is for,
    what may be written after its name, what carries it out, and when there is anything for
    it to carry out. Three of those used to be declared in three files that a test kept in
    step, which is a command added in two of them and missing from the third until somebody
    ran the suite -- offered but doing nothing, or working but offered to nobody.
    """

    #: What is typed after the slash.
    name: str
    #: What it is for, shown beside its name in the list.
    about: str
    #: What running it does, given the interface and whatever was written after the name.
    #: What it answers with is nothing to the caller -- a worker, a None -- so it says
    #: nothing about that.
    does: Callable[[Humanize, list[str]], object]
    #: How its arguments are written, shown beside it so that the list says what may be
    #: written and not only what may be started. A switch takes `on` or `off` as well as
    #: being flipped, and nothing says so unless the list does. "" takes none.
    takes: str = ""
    #: The words it takes after its name, offered as they are typed: the pages `/settings`
    #: opens on. Empty for a command whose argument is anything, or nothing.
    offers: tuple[str, ...] = ()
    #: Which views it works in -- `monitor`, `aggregate` (the transcript every agent is
    #: on), `session` (one agent's or one conversation's) and `outworlder` (what one
    #: outworlder asks) -- offered in those and refused, saying where it works, in the rest.
    where: frozenset[str] = VIEWS
    #: Why it cannot be run as things stand, given the interface, or "" where it can: `/stop`
    #: with no flow running, `/resume` with one. Asked before the list is drawn as well as
    #: before a sent line is carried out, so that a command is offered exactly while it would
    #: do something and is turned down, saying why, the rest of the time. None for one that
    #: works whatever is happening.
    refuses: Callable[[Humanize], str] | None = None
    #: Whether it is left out of the list though a line naming it is still carried out: for
    #: one whose having nothing to do is only known as of a while ago, and which looks again
    #: for itself when it is run. None for one listed whenever it is not refused.
    unlisted: Callable[[Humanize], bool] | None = None
    #: What it is for as things stand, where that changes with them, or "" for `about`: the
    #: flow menu opened during a run sets up that run's agents rather than switching flows.
    #: None for one whose line never changes.
    now: Callable[[Humanize], str] | None = None


#: A command and the word being typed after it -- `/flow` and a flow, `/settings` and a
#: page. A third word is a line that has moved on.
_FLOW_AND_NAME = 2


def offered(
    typed: str, commands: tuple[Command, ...], *, flows: bool = True
) -> list[str]:
    """What the line being typed could be finished with.

    Args:
      typed: The line as it stands.
      commands: The commands there are.
      flows: Whether a flow may be chosen now, which is what the flows are offered for --
        after a `$` and after `/flow`. Not while one runs: both are refused then.

    Returns:
      Everything the last word could become, in full, so that taking one replaces what was
      typed rather than being appended to it, and in alphabetical order -- the only order a
      list of commands has that a reader can predict. Never the word itself, and nothing at
      all for a word that has been written out already, whether it is a command or a flow: it
      is finished, and enter over an open list takes what is under the cursor rather than
      sending the line -- so `/flow`, with `/flowverses` beside it in the list, would be a
      command nobody could send, and `$rlar`, with `$rlar2` beside it, a flow nobody could
      start.
    """
    words = typed.split(" ")
    tail = words[-1]
    # A `$` names a flow to start, so it offers the flows and nothing else -- and only while
    # that first word is the one being typed: everything after it is the prompt, which is
    # prose and has nothing to finish it with.
    if typed.startswith("$"):
        if len(words) > 1 or not flows:
            return []
        offers = [f"${one.name}" for one in _flows()]
    elif not typed.startswith("/"):
        return []
    elif len(words) == 1:  # still naming the command
        if any(tail.removeprefix("/") == one.name for one in commands):
            return []
        offers = sorted(f"/{one.name}" for one in commands)
    # The flow is the one thing `/flow` takes, and a page the one thing `/settings` does, so
    # each is offered while that word is the one being typed and not after it: a line that
    # already names one is a finished line.
    elif len(words) == _FLOW_AND_NAME:
        offers = (
            ([one.name for one in _flows()] if flows else [])
            if words[0] == "/flow"
            else next(
                (list(one.offers) for one in commands if words[0] == f"/{one.name}"),
                list[str](),
            )
        )
    else:
        return []
    if tail in offers:
        return []  # written out in full, so enter over the list still sends the line
    return [offer for offer in offers if offer.startswith(tail) and offer != tail]


#: How long one reading of the flows stands for. Reading them means importing and running
#: every flow file there is, and a `$` asks for them on every keystroke of the name after it
#: -- twice, since the offers are reconsidered when the cursor moves as well as when the text
#: does. A moment's cache is the difference between a list that keeps up with typing and one
#: that does not, and the flows there are change when a flow is installed or a file is
#: written, neither of which happens between two keystrokes.
_FOR = 2.0


def _flows() -> tuple[Offer, ...]:
    """Every flow there is to run, read where it is offered rather than kept here.

    Returns:
      One per flow, as `hmz.runtime.flowing` lists them -- the one place that works out what
      each is called, since a name that drifted is a name nothing would take. As it was up to
      a moment ago, rather than as it is this instant.
    """
    return _found(int(time.monotonic() / _FOR), str(Path.cwd()))


@functools.lru_cache(maxsize=1)
def _found(_moment: int, _where: str) -> tuple[Offer, ...]:
    """One reading of the flows, kept under the moment and the directory it was read in.

    The arguments are the cache rather than the question: one bucket of `_FOR` seconds and one
    working directory is one answer, and the next bucket evicts it. Kept by directory as well,
    since `local` flows are this project's and a process that changed directory changed the
    list.

    Args:
      _moment: Which bucket of time this is.
      _where: The directory the flows were looked for from.

    Returns:
      One per flow.
    """
    from hmz.runtime.flowing import found

    return tuple(found())


def hinted(typed: str, commands: tuple[Command, ...]) -> str:
    """The command a line is writing, for as long as it is still being written.

    Args:
      typed: The line as it stands.
      commands: The commands there are.

    Returns:
      The command the line names, without its slash, or "" if it names none. Shown rather
      than offered: the line about a command says what it takes after its name, which is the
      half of it that matters most while that part is being typed -- and a list that empties
      the moment the name is finished takes it away exactly then. Nothing about it is taken,
      so enter over one sends the line as it always did.
    """
    if not typed.startswith("/"):
        return ""
    named = typed[1:].partition(" ")[0]
    return named if any(named == one.name for one in commands) else ""


def paths(typed: str) -> list[str]:
    """Every file and directory a path being typed could become, as a shell would finish it.

    Args:
      typed: The path as it stands -- relative to where this was started, from the root, or
        from the home a leading `~` names.

    Returns:
      Each in full, spelled as it would be typed: the `~` kept rather than spelled out, and a
      directory ending in a separator, so that taking one is already the way into it. In
      alphabetical order; a name starting with a dot only once a dot is typed, as a shell
      offers them; and nothing for a directory that cannot be read, or for a `~` naming
      somebody: finishing that is a list of the machine's users rather than of a directory.
    """
    if typed.startswith("~") and os.sep not in typed:
        return [f"~{os.sep}"] if typed == "~" else []
    head, sep, tail = typed.rpartition(os.sep)
    prefix = head + sep
    try:
        with os.scandir(Path(prefix).expanduser()) as names:
            found = [
                one.name + os.sep if one.is_dir() else one.name
                for one in names
                if one.name.startswith(tail)
                and (tail.startswith(".") or not one.name.startswith("."))
            ]
    except (OSError, RuntimeError):  # RuntimeError: a `~somebody/` nobody is
        return []
    return sorted(prefix + one for one in found)
