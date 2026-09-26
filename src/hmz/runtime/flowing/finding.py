"""Where a flow is, what it is called, and the flow a name comes to.

A flow is named rather than pathed: `hmz exec -f ralph_loop` is a name, and a path is what is
left for a flow that is nowhere any of them are kept. A name is looked for in the places flows
come from, which is every [flowverse](verses.py) there is -- humanize's own, which is
`official` and is the handful in the package together with the repository of the rest, whatever
has been added, and the flows of your own in `.humanize/flows` here and in your home directory.
Those last two are `local` and `user`, and are flowverses like the rest of them.

Which of them a bare name means is nearest first -- yours, then everybody else's -- so a flow
of your own may stand in for one of humanize's by taking its name, and `local/chat` is the
spelling that says which one it is.

Reading a flow means importing it: a flow is a directory whose `__init__.py` defines flows with
:func:`hmz.flows.flow`, and the only way to find out which is to import it. That is
:mod:`loading`'s to do, once per module and afresh when its files change, so a flow rewritten
between two runs of it -- by hand, or by an agent it is itself driving -- is the flow that runs
next.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

from .verses import LOCAL, MINE, OFFICIAL, flowverses, holds, nearest

if TYPE_CHECKING:
    from .engine import FlowImpl
    from .verses import Flowverse

__all__ = [
    "BUILTIN_AT",
    "ENTRY",
    "Offer",
    "about",
    "at",
    "builtin",
    "entry",
    "find",
    "fork",
    "found",
    "inside",
    "offered",
    "offers",
    "resolved",
    "within",
]

#: Where the flows humanize ships in the package are: `hmz/flows/builtin`, beside the flow API
#: they are written against, rather than beside this file, which is how one is found. They are
#: the whole of what is there, so there is no `flows/` in it to tell them from the rest. Offered
#: under `official` along with the repository of the rest of humanize's flows: which of the two
#: places one of them is kept in is humanize's business rather than whoever is running it.
#: Worked out from where this file is rather than by importing the flow API, which a listing
#: of places has no need to pay for.
BUILTIN_AT = Path(__file__).resolve().parents[2] / "flows" / "builtin"

#: What a flow's directory holds the flow itself in. The rest of the directory is what it
#: imports and the `skills/` it brings, so the entry point is named rather than guessed.
ENTRY = "__init__.py"

#: What a flow's own name is separated from the one inside it by. A module that holds one
#: visible flow is named by itself; one that holds three names the others after it.
_INSIDE = ":"


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
      rather than instead of it. The flow a bare ref names -- the one named after its
      directory, else the only visible one -- is listed by the directory's name, and every
      other visible flow of the module as `<flow>:<inside>`; hidden flows are not listed, and a
      directory that holds none is not among them -- a directory of flows has directories
      beside them that are not one.

      Just the ones in the package for `official` before it has been fetched, and nothing at
      all for any other flowverse that has not been, which is not the same answer as one that
      holds nothing, and is why :class:`Flowverse` says which it is.

    Note:
      Reading a flow means importing it, so the entry point of every flow in the directories
      the flowverse holds its flows in is imported to find out what it holds -- and nothing
      outside them, which is what those directories are for. Whoever added it is trusting
      that repository with this machine; this is where that trust is spent.
    """
    from .verses import flows

    return [
        Offer(one.name, name if one.name == OFFICIAL else f"{one.name}/{name}", said)
        for base in flows(one)
        if (at_ := within(one, base)) is not None
        for name, said in _named(at_, base)
    ]


def _named(at: Path, called: str) -> list[tuple[str, str]]:
    """What each flow in one module is called, given what the module itself is called.

    Args:
      at: The module's entry point.
      called: What the module is called where it was found.

    Returns:
      One `(name, what it says about itself)` pair per visible flow: the module's own name for
      the one a bare ref names, and `<called>:<inside>` for each of the rest. Nothing at all
      for a module that defines no flow -- a directory of flows has files beside them that are
      not one -- but just the module's name for one that could not be imported: a file that
      will not import is still a flow somebody named, and saying so where they pick it is
      better than leaving it off the list.
    """
    from hmz.flows import FlowException

    from .loading import module_of, pick

    try:
        module = module_of(at, None)
        flows = module.flows()
    except (FlowException, OSError):
        return [(called, "")]
    visible = [one for one in flows.values() if not one.hidden]
    try:
        bare = pick(module, "", called)
    except FlowException:
        bare = None
    said: list[tuple[str, str]] = []
    if bare is not None and not bare.hidden:
        # The module's own docstring where the flow it is named for says nothing: a module
        # that is one flow is documented as that flow, and its first line is what it does.
        said.append((called, bare.description or _first(module.module.__doc__)))
    said.extend(
        (f"{called}{_INSIDE}{one.name}", one.description or "")
        for one in sorted(visible, key=lambda one: one.name)
        if one is not bare
    )
    return said


def _first(doc: str | None) -> str:
    """The first line of a docstring, or "" for none."""
    said = (doc or "").strip().splitlines()
    return said[0].strip() if said else ""


def about(named_: str) -> str:
    """The line one flow says about itself, for whoever is choosing between them.

    Args:
      named_: What the flow is called, as :func:`found` calls it.

    Returns:
      The line, or "" for a flow that says nothing or cannot be read.
    """
    from hmz.flows import FlowException

    try:
        flow = resolved(named_)
    except (FlowException, OSError):
        return ""
    if flow.description or inside(named_) or flow.home is None:
        return flow.description or ""
    # The module's own docstring where the flow a bare name means says nothing, as the list
    # of flows says it: a module that is one flow is documented as that flow.
    return _first(flow.home.module.__doc__)


def resolved(named_: str) -> FlowImpl:
    """The flow a name comes to, loaded, as a way in runs it.

    Anything :func:`hmz.flows.load` takes where no flow is asking: a name nearest first,
    `<flowverse>/<flow>`, either with `:<inside>`, a path, or a `git+<url>#<flow>` ref, which
    is fetched here, on this thread. A flow humanize ships is handed its harness's every
    capability, with :func:`~hmz.runtime.flowing.engine.full_view`: `chat` talks to whichever
    agent it is given, and so declares nothing of any, and it is the flows in the package
    rather than a name that says which flow that is.

    Args:
      named_: What the flow is called.

    Returns:
      The flow.

    Raises:
      FlowRefError: If `named_` is no ref, or is relative to a flow when none is asking.
      FlowNotFound: If nothing answers to it.
      FlowDefinitionError: If what it names is written wrong or will not import.
      FlowLoadConflict: If loading it would replace a module a run going now uses.
    """
    from hmz.flows import FlowNotFound

    from .engine import FlowImpl, full_view
    from .loading import load

    try:
        found_ = load(named_, {})
    except FlowNotFound as missing:
        # Only for a name nothing answers to: one that found its module and then no flow in
        # it is a flow to correct, whatever has been fetched.
        if "#" in named_ or os.path.isfile(find(named_)):
            raise
        waiting = _unfetched(named_)
        if not waiting:
            raise
        raise FlowNotFound(f"{named_}: {waiting}") from missing
    if isinstance(found_, FlowImpl):
        flow = found_
    else:
        # Fetched on this thread: a way in asks before anything runs, and has no loop yet.
        _ = found_.name
        fetched = found_.flow
        assert fetched is not None  # noqa: S101 -- asking its name fetched it
        flow = fetched
    if builtin(flow):
        full_view(flow)
    return flow


def _unfetched(named_: str) -> str:
    """Why a flow that was named is not there, where a flowverse not fetched yet is why.

    A flowverse is offered before it is fetched -- `official` is there from the start -- so
    "no such flow" would be the answer to a name that is right, given by the one thing that
    knows it has not been downloaded. A name that said which place it came from is a question
    about that place alone; a bare one is looked for in every one of them.

    Args:
      named_: What was asked for, as it was written.

    Returns:
      The reason, or "" where every flowverse it could have come from has been fetched.
    """
    whose, _, rest = _split(named_)[0].partition("/")
    waiting = [
        one.name
        for one in flowverses()
        if one.url and not one.fetched and (one.name == whose if rest else True)
    ]
    if not waiting:
        return ""
    which = "flowverse has" if len(waiting) == 1 else "flowverses have"
    return (
        f"the {' and '.join(waiting)} {which} not been fetched yet -- open /flowverses "
        "and press r on it"
    )


def builtin(flow: FlowImpl) -> bool:
    """Whether a flow is one humanize ships in the package.

    Args:
      flow: The flow.

    Returns:
      Whether it was defined under :data:`BUILTIN_AT`.
    """
    made = Path(os.path.realpath(flow.fn.__code__.co_filename))
    return made.is_relative_to(BUILTIN_AT)


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
