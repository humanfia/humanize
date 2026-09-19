"""Where a flow is, what it is called, and what running its file leaves behind.

A flow is named rather than pathed: `hmz exec -f ralph_loop` is a name, and a path is what is
left for a flow that is nowhere any of them are kept. A name is looked for in the places flows
come from, which is every [flowverse](verses.py) there is -- humanize's own, which is
`official` and is the handful in the package together with the repository of the rest, whatever
has been added, and the flows of your own in `.humanize/flows` here and in your home directory.
Those last two are `local` and `user`, and are flowverses like the rest of them.

Which of them a bare name means is nearest first -- yours, then everybody else's -- so a flow
of your own may stand in for one of humanize's by taking its name, and `local/chat` is the
spelling that says which one it is.

Reading a flow means running it. A flow is a Python file, what it holds is whatever marking a
function with :func:`~hmz.flows.flow` left behind, and the only way to find that out is to run
the file -- with its own directory importable while it does and only while, and forgotten again
afterwards, so that the module beside one flow is never answered with the module beside
another. Run afresh every time, too: a flow rewritten between two runs of it -- by hand, or by
an agent it is itself driving -- is the flow that runs next.

None of this is a thing a flow names. A flow says what it is with the mark, and humanize does
the finding: :mod:`hmz.flows` is the whole of what a flow imports, and everything that reads a
flow is here, written against it.
"""

from __future__ import annotations

import contextlib
import os
import runpy
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

import hmz.flows
from hmz.flows import (
    _SAID,  # pyright: ignore[reportPrivateUsage]
    Flow,
    _first,  # pyright: ignore[reportPrivateUsage]
)

from .verses import LOCAL, MINE, OFFICIAL, flowverses, holds, nearest

if TYPE_CHECKING:
    from .verses import Flowverse

__all__ = [
    "BUILTIN_AT",
    "ENTRY",
    "PROPHECY",
    "Offer",
    "about",
    "at",
    "entry",
    "find",
    "foretold",
    "fork",
    "found",
    "held",
    "inside",
    "loaded",
    "offered",
    "offers",
    "reading",
    "within",
]

#: Where the flows humanize ships in the package are: a directory of them inside
#: :mod:`hmz.flows`, which is where a flow lives, rather than beside this file, which is how
#: one is found. They are the whole of what is there, so there is no `flows/` in it to tell
#: them from the rest. Offered under `official` along with the repository of the rest of
#: humanize's flows: which of the two places one of them is kept in is humanize's business
#: rather than whoever is running it.
BUILTIN_AT = Path(hmz.flows.__file__).parent / "builtin"

#: What a flow's directory holds the flow itself in. The rest of the directory is what it
#: imports and the `skills/` it brings, so the entry point is named rather than guessed.
ENTRY = "__init__.py"

#: And what an atlas's directory may hold the prophecy it was already compiled to in. A
#: flowverse that ships one ships the graph its flow was checked into, and that graph is
#: what runs: the compiling is where an atlas is refused, and a repository which has been
#: through it once has an answer worth carrying rather than working out again.
PROPHECY = "prophecy.pkl"

#: What a flow's own name is separated from the one inside it by. A flow that holds one flow
#: is named by itself; one that holds three names each of them after it.
_INSIDE = ":"


def loaded(where_: str | os.PathLike[str]) -> dict[str, Any]:
    """Runs a flow's entry point and answers with what it left behind.

    With its own directory importable while it runs, and only while: a flow is a directory of
    what it needs, and one that reaches for the module next to it is reaching for something
    that came with it. The directory the flows are in is importable too, for what a flowverse
    keeps beside them for all of them. Put back afterwards, since what a flow imports is not
    something the rest of this process should be able to.

    Run each time rather than cached: a flow rewritten while a run is going is the flow that
    runs next, which is what lets a flow -- or an agent driving one -- rewrite it and go on.

    Args:
      where_: The flow: its directory, or the Python file to run outright.

    Returns:
      Everything running it defined, by name.
    """
    where_ = os.path.join(where_, ENTRY) if os.path.isdir(where_) else where_
    beside = os.path.dirname(os.path.abspath(where_))
    among = os.path.dirname(beside)
    sys.path[:0] = [beside, among]
    try:
        return runpy.run_path(str(where_))
    finally:
        for one in (beside, among):
            with contextlib.suppress(ValueError):
                sys.path.remove(one)
        _forgotten(beside, among)


def _forgotten(*under: str) -> None:
    """Forgets what was imported from beside a flow, so nothing of it outlives the run.

    A flow imports the module next to it by its plain name -- `import prompts` -- and every
    flow may have one. Left in `sys.modules`, the first flow loaded in a process owns that name
    for the life of it: the next flow's `import prompts` is answered with the last one's, and a
    menu drawing the list of flows is enough to settle who won. Taken out, each run of a flow
    reads what is beside that flow -- which is also what makes a flow edited between two runs
    of it run as it is now, module beside it and all.

    What is dropped is only what was loaded out of these directories, found by the file each
    module says it came from. Nothing of humanize's own is: a flow kept inside humanize's own
    tree would otherwise unload the package that is running it.

    Args:
      under: The directories, as absolute paths.
    """
    roots = tuple(one + os.sep for one in under)
    for name, module in list(sys.modules.items()):
        if name.startswith("hmz"):
            continue
        at = getattr(module, "__file__", None)
        if at and os.path.abspath(at).startswith(roots):
            del sys.modules[name]


def held(where_: str | os.PathLike[str]) -> list[Flow]:
    """Every flow one file holds: its own first, and the rest as it declares them.

    Args:
      where_: The flow -- its directory, or the file to read outright. It is run to be read,
        so whatever it does as it is imported happens here.

    Returns:
      One per function it marked with :func:`flow`, the one it marked with no name first --
      which is the flow the file holds under its own name. Nothing at all for a file that
      marks none, or cannot be read: this is asked while a list is being drawn, and a file
      that will not import is one line of that list rather than the end of it.
    """
    try:
        inside = loaded(where_)
    except Exception:  # noqa: BLE001 -- a file that will not run holds no flows to list
        return []
    return _flows_of(inside)


def _flows_of(inside: dict[str, Any]) -> list[Flow]:
    """Every flow in what running one file left behind.

    Args:
      inside: What the file defined, by name.

    Returns:
      One per function the file marked with :func:`flow`, in the order it declared them --
      which for three phases of one thing is their order -- and the one it marked with no name
      first, since that is the one the file is named after and a list that put it third would
      read as the third thing in the file. Nothing at all for a file that marks nothing, which
      a directory of flows may well have in it: something the flows beside it import, or the
      file that sets their tests up. A name declared twice is the first of them: a file that
      holds two flows of one name is a file to correct, and picking one of them at random is
      not the way to say so.
    """
    said: list[Flow] = []
    for one in inside.values():
        marked = getattr(one, _SAID, None)
        if not isinstance(marked, Flow) or any(
            marked.name == already.name for already in said
        ):
            continue
        # The file's own docstring where the flow it holds says nothing: a file that is one
        # flow is documented as that flow, and its first line is what it does.
        if not marked.name and not marked.about:
            marked = Flow(
                name="",
                about=_first(inside.get("__doc__")),
                skills=marked.skills,
                resumable=marked.resumable,
                selectable=marked.selectable,
            )
        said.append(marked)
    return [one for one in said if not one.name] + [one for one in said if one.name]


class Offer(NamedTuple):
    """One flow there is to run, as whatever is offering them lists it.

    Attributes:
      whose: Where it came from: a flowverse by name, or `local` and `user` for the flows of
        this project and of yours.
      name: What to call it, which is what `-f` takes.
      about: The line it says about itself, or "" for one that says nothing.
    """

    whose: str
    name: str
    about: str = ""


def found() -> list[Offer]:
    """Every flow there is to run, and where each came from.

    Every place asked the same question, which is :func:`offers`, and asked it in the order
    they are offered in: the flows humanize ships, then whatever flowverses have been added,
    then this project's own flows and yours. One place works out what a flow is called and one
    place lists them, because two of either is two things to drift apart -- and a name that has
    drifted is a name `-f` will not take.

    Returns:
      One per flow. A flow humanize ships is called by a bare name, whichever of the two places
      `official` is kept in it is in, and every other by `<where it came from>/<name>` --
      `local/scheduler`, `theirs/rlar` -- so a flow of yours that happens to share a name with
      one of humanize's is a different flow here rather than the same one, and is written down,
      offered and remembered under a name of its own. A file that holds several says so,
      `<name>:<inside>` apiece.
    """
    return [one for verse in flowverses() for one in offers(verse)]


def entry(under: Path, name: str) -> Path | None:
    """The file to run for the flow of that name in one directory of flows.

    A flow is a module, and there are two shapes of one: a directory with an `__init__.py` in
    it -- which is what a flow that brings skills or imports what came with it has to be --
    and a single `.py` file, which is what a flow that is one function still is. The directory
    wins where both are there, being the one that says most about itself.

    Args:
      under: The directory the flows are in.
      name: The flow, by the name it is offered under.

    Returns:
      The path to run, or None where there is no such flow.
    """
    beside = under / name / ENTRY
    if beside.is_file():
        return beside
    alone = under / f"{name}.py"
    return alone if alone.is_file() else None


def within(one: Flowverse, name: str) -> Path | None:
    """The file to run for the flow of that name in one flowverse, wherever it keeps them.

    A flowverse keeps its flows in one directory, except `official`, which is humanize's own
    and is kept in two: the handful in the package, and the repository of the rest. Asked here
    rather than at each of the places that looks a flow up, so that both are searched in the
    one order and a flow found while a list is drawn is the flow that runs.

    Args:
      one: The flowverse.
      name: The flow, by the name it is offered under.

    Returns:
      The path to run, from the first of its directories to hold one, or None where none does.
    """
    for under in holds(one):
        beside = entry(under, name)
        if beside is not None:
            return beside
    return None


def offered(under: Path) -> list[str]:
    """Every flow in one directory of flows, by the name each is offered under.

    Args:
      under: The directory the flows are in, which may not be there at all.

    Returns:
      One name apiece, alphabetically and without repeating a name that is there both ways.
      A name starting with an underscore is not a flow but something the flows beside it
      import; nor is a directory with no entry point in it. Nothing at all where there is no
      such directory.
    """
    found_: list[str] = []
    try:
        held = sorted(under.iterdir())
    except OSError:
        return []
    for path in held:
        name = path.name.removesuffix(".py")
        if name.startswith("_") or name in found_:
            continue
        if (path / ENTRY).is_file() or (path.is_file() and path.suffix == ".py"):
            found_.append(name)
    return found_


def offers(one: Flowverse) -> list[Offer]:
    """Every flow one flowverse offers, and the name each is offered by.

    The one place that rule is written down. :func:`found` asks this of every flowverse in
    turn, and so does anything that wants a single one's -- two places working out what a flow
    is called is two places to drift, and a name that drifts is a name `-f` will not take.

    Args:
      one: The flowverse.

    Returns:
      One per flow, by directory, alphabetically: `<flowverse>/<flow>`, except for humanize's
      own, which are called by a bare name. Which of the two places `official` is kept in a
      flow of humanize's is in makes no difference to what it is called: the package's `chat`
      and the repository's `rlar` are both humanize's, so both are said the same way and a flow
      that moves between the two goes on answering to the name it always had. Yours are named
      the same way as anybody else's -- `local/scheduler`, `user/scheduler` -- so that a flow of
      yours sharing a name with one of humanize's is listed beside it under a name of its own
      rather than instead of it. A flow that holds several names each of them,
      `<flow>:<inside>` apiece, and a directory that holds none is not among them -- a directory
      of flows has directories beside them that are not one.

      Just the ones in the package for `official` before it has been fetched, and nothing at
      all for any other flowverse that has not been, which is not the same answer as one that
      holds nothing, and is why :class:`Flowverse` says which it is.

    Note:
      Reading a flow means running it, so the entry point of every flow in the directories the
      flowverse holds its flows in is run to find out what it holds -- and nothing outside
      them, which is what those directories are for. Whoever added it is trusting that
      repository with this machine; this is where that trust is spent.
    """
    from .verses import flows

    return [
        Offer(one.name, name if one.name == OFFICIAL else f"{one.name}/{name}", said)
        for base in flows(one)
        if (at_ := within(one, base)) is not None
        for name, said in _named(at_, base)
    ]


def _named(at: Path, called: str) -> list[tuple[str, str]]:
    """What each flow in one file is called, given what the file itself is called.

    Args:
      at: The file.
      called: What the file is called where it was found.

    Returns:
      One `(name, what it says about itself)` pair per flow: the file's own name for the flow
      it holds under it, and `<called>:<inside>` for each of the rest. Nothing at all for a
      file that holds no flow -- a directory of flows has files beside them that are not one --
      but just the file's name for one that could not be read: a file that will not import is
      still a flow somebody named, and saying so where they pick it is better than leaving it
      off the list.
    """
    try:
        inside = loaded(at)
    except Exception:  # noqa: BLE001 -- named as a flow, and not readable to be sure it is
        return [(called, "")]
    return [
        (called if not one.name else f"{called}{_INSIDE}{one.name}", one.about)
        for one in _flows_of(inside)
        if one.selectable
    ]


def about(named_: str) -> str:
    """The line one flow says about itself, for whoever is choosing between them.

    Args:
      named_: What the flow is called, as :func:`found` calls it.

    Returns:
      The line, or "" for a flow that says nothing or cannot be read.
    """
    at, inside = _split(named_)
    for one in held(find(at)):
        if one.name == inside:
            return one.about
    return ""


def _split(named_: str) -> tuple[str, str]:
    """One flow's name, split into the file and the flow inside it.

    Args:
      named_: What the flow is called.

    Returns:
      The file's name and the name inside it, which is "" for a file's own flow. A colon in a
      path -- a Windows drive, a URL somebody pasted -- is not one of these: only the last
      one is read, and only where what follows it is a name rather than a path.
    """
    at, sep, inside = named_.rpartition(_INSIDE)
    if not sep or os.sep in inside or "/" in inside:
        return named_, ""
    return at, inside


def find(named_: str) -> str:
    """Where the entry point of the flow called this is.

    Args:
      named_: A flow's name -- `ralph_loop`, `official/rlar`, `local/scheduler`,
        `humanize1:gen-plan` -- or the path to a flow taken as given, `~` and all: its
        directory, or the file to run outright.

    Returns:
      The path to run: the flow the flowverse named holds, else the nearest flow of that
      name, else what the path names -- and `named_` itself if nothing answers to it, so
      that whatever named it hears about it. Resolved, since a flow is free to change the
      working directory the name was resolved against.
    """
    at_, _ = _split(named_)
    whose, _, rest = at_.partition("/")
    if rest:
        # Named outright -- `official/rlar`, `local/scheduler` -- which is the one spelling
        # that says which place it came from, and so the one that cannot be stood in for.
        for verse in flowverses():
            if whose != verse.name:
                continue
            beside = within(verse, rest)
            if beside is not None:
                return str(beside.resolve())
    else:
        # Nearest wins: this project, then yours, then whatever there is to run -- so a flow
        # of your own may stand in for one of humanize's by taking its name.
        for verse in nearest():
            beside = within(verse, at_)
            if beside is not None:
                return str(beside.resolve())
    # A path taken as given, in both the shapes a flow is: the directory it is, the file it is
    # for whoever points at one outright -- a flow being written, a file a test wrote out --
    # and the `.py` beside a path with the extension left off, which is how a single-file flow
    # is written down anywhere its name is not what it is called by.
    said = os.path.expanduser(at_)
    for shape in (os.path.join(said, ENTRY), said, f"{said}.py"):
        if os.path.isfile(shape):
            return os.path.realpath(shape)
    return at_


def reading(named_: str) -> str:
    """What to point a reading of one flow at, which is not always what runs it.

    A flow is a directory or a single file, and the two readings of one -- the checking and
    the compiling -- take the whole of it either way: the directory where there is one, so
    that what the entry point imports beside it is read too, and the file where there is
    not. :func:`find` answers with the entry point instead, that being what is run.

    Args:
      named_: A flow's name, as :func:`find` takes it.

    Returns:
      The path to read: the flow's own directory, or the file a single-file flow is. A name
      nothing answers to comes back as :func:`find` left it, so whatever asked hears about
      it where it looks rather than here.
    """
    found_ = find(named_)
    if os.path.isfile(found_) and os.path.basename(found_) == ENTRY:
        return os.path.dirname(found_)
    return found_


def foretold(named_: str) -> str:
    """Where the prophecy one flow ships is, for a flow that ships one.

    An atlas is compiled before it runs, and a flowverse may ship what compiling it came
    to: `prophecy.pkl`, beside the entry point, holding the graph the atlas was read into.
    Where there is one it is what runs -- the compiling having already happened, in the
    repository the flow came from, over the source that repository holds.

    What is beside it still matters. A prophecy names the functions its nodes are, and
    those are in the flow's own Python: a directory holding a prophecy and no entry point
    is not a flow, the same way a directory holding neither is not one.

    Args:
      named_: A flow's name, as :func:`find` takes it.

    Returns:
      The path to it, and "" for a flow that ships none -- which is every flow that is not
      an atlas, and most atlases.
    """
    from .prophecy import shipped

    beside = at(named_)
    held = shipped(beside) if beside else None
    return "" if held is None else str(held.at)


def at(named_: str) -> str:
    """The flow's own directory, which is where what it brings with it lives.

    Args:
      named_: A flow's name, as :func:`find` takes it.

    Returns:
      The directory its `__init__.py` is in, and "" for a name nothing answers to -- and for
      a flow that is a single file, which has no directory of its own: what is beside such a
      flow is the other flows, and none of it came with this one.
    """
    found_ = find(named_)
    if not os.path.isfile(found_) or os.path.basename(found_) != ENTRY:
        return ""
    return os.path.dirname(found_)


def inside(named_: str) -> str:
    """Which of the flows in a file this name asks for.

    Args:
      named_: What the flow is called.

    Returns:
      The name after the colon, or "" for the flow a file holds under its own name.
    """
    return _split(named_)[1]


def fork(named_: str, into: str | os.PathLike[str] | None = None) -> str:
    """Copies one flow into this project's own, to be changed however you like.

    A flow is a directory, which is what makes this a copy rather than a rewrite: the entry
    point, whatever it imports beside it and the `skills/` it brings all come across, and what
    lands is a flow of yours under the name it already had. Yours are looked in first, so from
    then on that name means the copy -- `official/rlar` forked is `rlar`, and `-f rlar` runs
    what you have since made of it.

    Which is the way to change a flow at all: a flowverse is somebody else's repository and is
    fetched again over whatever was written into it, so an edit made there is an edit that
    goes away the next time it is fetched.

    Args:
      named_: The flow to copy, by the name it is offered under.
      into: Where to put it, defaulting to this project's own flows.

    Returns:
      The directory it was copied to.

    Raises:
      ValueError: If there is no such flow, or there is already one of that name there --
        which is a copy to edit, run or take away rather than one to write over.
    """
    import shutil
    import tempfile

    found_ = find(named_)
    if not os.path.isfile(found_):
        raise ValueError(f"there is no flow called {named_} to copy")
    beside = os.path.dirname(found_)
    whole = os.path.basename(found_) == ENTRY
    name = os.path.basename(beside) if whole else os.path.basename(found_)
    mine = os.path.expanduser(str(into) if into is not None else MINE[LOCAL])
    at_ = os.path.join(mine, name)
    # Both shapes of the name, whichever this one is: a flow is a directory or a file, the
    # directory wins the name where there is one of each, and a copy that landed beside a
    # flow of yours would take that flow's name away without touching the file it is in.
    stem = at_.removesuffix(".py")
    if os.path.exists(stem) or os.path.exists(stem + ".py"):
        raise ValueError(f"there is already a flow of your own at {at_}")
    os.makedirs(mine, exist_ok=True)
    # Copied beside and then moved into place: a copy that fails partway -- a disk that filled,
    # a file that could not be read -- would otherwise leave half a flow under the name, which
    # is a flow that will not run, cannot be forked again, and hides the one it was copied from.
    holding = tempfile.mkdtemp(dir=mine, prefix=f".{name}.")
    try:
        held = os.path.join(holding, name)
        if whole:
            # The whole directory: what a flow is made of travels with it, which is what makes
            # a copy of one a flow rather than half of one.
            shutil.copytree(beside, held)
        else:
            # A flow that is one file is copied as one: a flow is a module, and this is the
            # shape that module has.
            shutil.copy2(found_, held)
        os.replace(held, at_)
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    return at_
