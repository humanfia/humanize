"""Where flows come from: every place there is one, and what each of them is called.

A flowverse is an index: a git repository of `flows/<flow>/<version>/flow.yaml` for the flows
it lists bare and `flows/<user>/<flow>/<version>/flow.yaml` for the ones it lists under their
owner, one manifest per release of a flow, saying which repository and commit that release is
(:mod:`index`). It is cloned into `~/.hmz/flowverses/<name>/index/`, and holds no code: what
runs is what somebody chose to install out of it, which is kept beside the clone, in
`installed/`, and offered under the flowverse's name. Fetching an index again changes what may
be installed, and never what runs.

What a flow is called says which flowverse it is of. humanize's own are said as `official`
lists them -- `aot`, `alice/kernel` -- and every other place's after an `@` and its name:
`@theirs/review`, `@theirs/alice/kernel`, `@local/scheduler`. Anything starting with `.`, `/`
or `~` is a path instead, and nothing else is.

Three are always there, and none of them can be added or taken away. `official` is humanize's
own, and is there whether or not it has been fetched yet: a list that only mentioned it once
somebody had thought to add it would be a list that hid what there is. And `local` and `user`
are the flows of your own: this project's own flows directory, and the one in your home.

`official` is the one that is read from two places at once. `chat` and the six loops beside it
are in the package, because a machine that has never reached a network still has to have
something to open talking to and a loop to leave running; whatever was installed out of
humanize's index is beside them. Which of the two a flow is in is humanize's business rather
than anybody else's, so both are offered under the one name: `chat` and an installed `aot` are
each one of humanize's flows, said the same way. The package's own wins a name they both hold
-- and an index may not offer one of those names at all.

Those last two are places rather than indexes -- nothing fetches them, nothing is installed
into them, and what is in one is whatever you put there -- but they are flowverses all the same,
because everything that goes looking for a flow has one question to ask and one list to ask it
of. A flow of yours is read where it stands, offered under the name of the place it is in the
way an installed flow is, and looked in first: `@local/chat` says which one it is, and a bare
`chat` finds yours before humanize's.

Nothing here runs a flow, and nothing here reads one. It is the answer to "which flows are
there, and where did each come from" -- and to the three things that can happen to a flowverse:
added, fetched again, taken away.
"""

from __future__ import annotations

import configparser
import contextlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from hmz import here, home

__all__ = [
    "AT",
    "FLOWS",
    "INDEX",
    "INSTALLED",
    "LOCAL",
    "MINE",
    "OFFICIAL",
    "OWNER",
    "USER",
    "Flowverse",
    "add",
    "called",
    "clone",
    "edited",
    "fetch",
    "flowverses",
    "holds",
    "nearest",
    "pathed",
    "plain",
    "refresh",
    "remove",
    "renamed",
    "split",
    "standing",
    "under",
]

#: What humanize's own flows are listed under, and where its index of them is. Always listed,
#: whether or not it has been fetched: what there is to install is not the same question as
#: what has been downloaded, and somebody who has never fetched it should still be able to see
#: it and say so. The flows in the package are listed under this name too -- one name for
#: humanize's flows, whichever of the two places a given one happens to be kept in.
OFFICIAL = "official"
OFFICIAL_URL = "https://github.com/humanfia/flowverse"

#: What the flows of your own are listed under: this project's, and the ones in your home
#: directory. Flowverses like any other, except that nothing fetches them.
LOCAL = "local"
USER = "user"

#: And where those two are, nearest first. Kept unresolved: the project one is relative to
#: wherever humanize is being run, and `~` is whoever is running it, neither of which is
#: settled when this is imported.
MINE = {
    LOCAL: ".hmz/flows",
    USER: "~/.hmz/flows",
}

#: The names a flowverse cannot be added under, being the three that are always listed. One is
#: humanize's own and two are yours, and a repository cloned into any of their slots would be
#: one nobody could reach.
_ALWAYS = (OFFICIAL, LOCAL, USER)

#: The places whose flows are read where they stand rather than installed out of an index.
_AS_THEY_STAND = (LOCAL, USER)

#: The directory an index keeps its manifests in, `flows/<flow>/<version>/flow.yaml`, and the
#: only one read for them: an index is a repository, with a README and a CI of its own beside.
FLOWS = "flows"

#: The two directories a flowverse's own directory holds: the clone of its index, and the flows
#: installed out of it. Beside each other rather than one inside the other, so that a fetch,
#: which resets the clone to what its repository says now, never reaches what was installed.
INDEX = "index"
INSTALLED = "installed"

#: What a flowverse may be called: one directory name, and one that cannot climb out of the
#: directory they are kept in.
_NAMED = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")

#: What a flow's name starts with where it is of a flowverse other than `official`, whose own
#: are said bare: `@theirs/review`, `@local/scheduler`.
AT = "@"

#: Who an index may list flows under, `flows/<user>/<flow>/`: a GitHub user or organisation,
#: in lower case, which is who owns the repository the flow is in.
OWNER = re.compile(r"[a-z0-9][a-z0-9-]*\Z")

#: What a path starts with, which is how it is told from a flow's name: nothing else is one.
_PATHED = (".", "/", "~")

#: How long a fetch is given before it is called off. A clone of a repository of text files is
#: seconds; a minute is the difference between slow and not answering.
_PATIENCE = 60.0


@dataclass(frozen=True, slots=True)
class Flowverse:
    """One place flows come from.

    Attributes:
      name: What it is called, which is the directory it is kept in and the name its flows are
        offered under.
      url: Where its index is fetched from, or "" for one that is not fetched from anywhere --
        the two directories your own flows live in.
      at: The directory it is read from, which for an index is the clone of it -- the
        :data:`INDEX` inside the directory :func:`where` names -- rather than the flows
        installed out of it: what its flows are read from is :func:`holds`.
      fetched: Whether the index has been cloned. False for one named but never fetched,
        which `official` is until somebody asks for it, and true for the ones fetched from
        nowhere: a directory that is not there holds no flows, which is what its list of them
        says rather than a download somebody is waiting for. Not the same question as whether
        it offers anything -- `official` offers the flows in the package either way, and what
        was installed out of an index stays installed whether or not it is fetched again.
      fixed: Whether it is always listed and cannot be removed: humanize's own, and the two
        your own flows live in.
    """

    name: str
    url: str
    at: Path
    fetched: bool
    fixed: bool


def under() -> Path:
    """Where every flowverse is kept, which is one directory under humanize's home."""
    return home() / "flowverses"


def holds(one: Flowverse) -> tuple[Path, ...]:
    """The directories one flowverse's flows are read from, and the one place that is worked out.

    What was installed out of its index, except for the two places that are a directory of
    flows and nothing else -- yours -- which are read where they stand. Never the index itself:
    that is manifests, and a flow an index lists that nobody installed is not a flow to run.

    More than one only for `official`, which is humanize's own flows and is kept in two places:
    the ones in the package, read where they stand, and what was installed out of humanize's
    index. The package's own come first, so that a name both hold is the one that is always
    there rather than one an install could change.

    Args:
      one: The flowverse.

    Returns:
      The paths, in the order a name is looked for in them, whether or not there is anything
      at any of them -- a flowverse nothing has been installed out of holds nothing, which is
      a thing to say rather than a thing to raise.
    """
    from .finding import BUILTIN_AT
    from .index import kept

    if one.name in _AS_THEY_STAND:
        return (one.at,)
    if one.name == OFFICIAL:
        return (BUILTIN_AT, kept(OFFICIAL))
    return (kept(one.name),)


def where(name: str) -> Path:
    """The directory one flowverse is kept in: the clone of its index, and what was installed.

    Args:
      name: What it is called.

    Returns:
      The path, whether or not anything has been fetched or installed into it.

    Raises:
      ValueError: If the name is not one a flowverse may have -- a name is a directory, and
        one that climbs out of this one is not a name.
    """
    if not _NAMED.match(name):
        raise ValueError(
            f"{name!r} is not a flowverse name: letters, digits, dot, dash and underscore, "
            "starting with a letter or a digit"
        )
    return under() / name


def flowverses() -> list[Flowverse]:
    """Every place flows come from, in the order they are offered.

    Returns:
      humanize's own first, then whatever else has been added, alphabetically, and last the
      flows of your own: this project's, then the ones in your home directory. Three of them
      are always here: humanize's, which is the one there is anything to fetch, and two
      directories of yours that are read wherever they are.
    """
    held = [
        Flowverse(
            name=OFFICIAL,
            url=OFFICIAL_URL,
            at=where(OFFICIAL) / INDEX,
            fetched=_cloned(where(OFFICIAL) / INDEX),
            fixed=True,
        ),
    ]
    # One with no clone in it -- taken away by hand, with flows still installed beside where it
    # was -- is listed all the same, as one with nowhere to fetch from: what was installed out
    # of it is still offered under its name, and removing it is how it goes.
    for kept in sorted(_directories(under())):
        if kept.name in _ALWAYS or not _NAMED.match(kept.name):
            continue
        at = kept / INDEX
        held.append(
            Flowverse(
                name=kept.name,
                url=_url(at),
                at=at,
                fetched=_cloned(at),
                fixed=False,
            )
        )
    # Last, because that is the order they are read in and not the order they are looked in:
    # a menu of flows opens on the ones there are to run rather than on a directory that is
    # empty in most projects. Which one wins a name is :func:`nearest`.
    held.extend(_own(name) for name in MINE)
    return held


def nearest() -> list[Flowverse]:
    """Every place flows come from, nearest first, which is the order a name is looked up in.

    The same places :func:`flowverses` lists, in the other of the two orders they have: that
    one is the order they are offered in, and this is the order they are searched in. Both are
    written down here, since a place missing from either is a flow that is offered and cannot
    be run, or one that runs and is nowhere to be seen.

    Returns:
      This project's flows, then yours, then the rest as they are listed -- so that a flow of
      your own may stand in for one of humanize's by taking its name, and a project may mean
      its own `chat` by `chat`.
    """
    held = flowverses()
    return [one for one in held if one.name in MINE] + [
        one for one in held if one.name not in MINE
    ]


def _own(name: str) -> Flowverse:
    """One of the two places flows of your own live, as a flowverse like any other.

    Args:
      name: Which of them, as :data:`MINE` names it.

    Returns:
      The flowverse. Fetched, whether or not the directory is there: there is nowhere to fetch
      it from, and a directory that is not there is a place holding no flows rather than one
      with a download outstanding. Fixed, since a place that is wherever you are cannot be
      taken away.

    Note:
      Expanded with `os.path` rather than `Path.expanduser`, which raises where there is no
      home behind the `~`: a machine with no home directory is a machine with no flows of
      yours on it, which is a thing to say rather than the reason a flow humanize itself came
      with could not be found.
    """
    # This project's are in its own directory, which moves one kept under its old name to
    # where they are read from.
    at = here() / "flows" if name == LOCAL else Path(os.path.expanduser(MINE[name]))
    return Flowverse(
        name=name,
        url="",
        at=at,
        fetched=True,
        fixed=True,
    )


def named(name: str) -> Flowverse | None:
    """The flowverse called this, or None for a name none answers to."""
    return next((one for one in flowverses() if one.name == name), None)


def pathed(said: str) -> bool:
    """Whether what names a flow is a path to one rather than its name: `./x`, `/x`, `~/x`."""
    return said.startswith(_PATHED)


def called(verse: str, flow: str) -> str:
    """What a flow is called, given its flowverse and what that flowverse calls it.

    Args:
      verse: The flowverse.
      flow: The flow as it lists it -- `review`, `alice/kernel` -- and `:<inside>` after it for
        one of the other flows of its module.

    Returns:
      The name as it is for `official`, and after `@<flowverse>/` for every other one.
    """
    return flow if verse == OFFICIAL else f"{AT}{verse}/{flow}"


def split(name: str) -> tuple[str, str]:
    """A flow's name, as :func:`called` makes one, into its flowverse and what that one calls it.

    Args:
      name: `[@<flowverse>/][<user>/]<flow>`, without the `:<inside>`.

    Returns:
      The two: `@theirs/alice/kernel` is `theirs` and `alice/kernel`, and a name with no `@` is
      `official`'s.

    Raises:
      ValueError: For what is no such name: a part empty or hidden, or one too many -- your
        own places keep flows by name alone, so a `<user>/` is one too many in either.
    """
    verse, flow = OFFICIAL, name
    if name.startswith(AT):
        verse, _, flow = name.removeprefix(AT).partition("/")
    parts = flow.split("/")
    if (
        not _NAMED.match(verse)
        or any(not one or one.startswith(".") for one in parts)
        or len(parts) > (1 if verse in MINE else 2)
    ):
        raise ValueError(
            f"{name!r} is not a flow's name, [@<flowverse>/][<user>/]<flow>"
        )
    return verse, flow


def renamed(name: str) -> str:
    """What a flow said the way names were said before the `@` is called now.

    `local/x` and `user/x` are `@local/x` and `@user/x`, `<flowverse>/x` is `@<flowverse>/x`
    for a flowverse there is, and `official/x` is `x`. Anything else -- a name said as names
    are now, a path, a ref, a bare name -- is as it was.

    Args:
      name: What the flow was called, `:<inside>` and all.

    Returns:
      What it is called now.
    """
    head, colon, inside = name.rpartition(":")
    if not colon or "/" in inside:
        head, inside = name, ""
    whose, _, flow = head.partition("/")
    if not flow or "/" in flow or named(whose) is None:
        return name
    now = called(whose, flow)
    return f"{now}:{inside}" if inside else now


def add(url: str, name: str = "") -> Flowverse:
    """Fetches a flowverse's index, and answers with what was fetched.

    Nothing is installed out of it: which of its flows to install, and at which release, is
    for whoever added it to say.

    Args:
      url: Where it is, as git takes it: a URL, or `owner/repo` for one on GitHub.
      name: What to call it, defaulting to the repository's own name. It is the directory it
        is kept in and the name the flows installed out of it are offered under.

    Returns:
      The flowverse, fetched.

    Raises:
      ValueError: If the name is not one a flowverse may have, one is already called that, or
        it is one of the three that are always listed -- humanize's own and the two your own
        flows live in -- since a repository cloned into any of those slots is one nobody could
        reach.
      OSError: If git is not there, or the fetch failed. What git said is attached, and
        whatever it had written before it failed is taken away again.
    """
    said = url.strip()
    if not said:
        raise ValueError("no repository to fetch a flowverse from")
    called = name or _called(said)
    if called == OFFICIAL:
        # This one is listed from the start with humanize's own URL against it, so a stranger's
        # repository here would be shown as humanize's own.
        raise ValueError(
            f"{OFFICIAL} is humanize's own repository of flows; "
            f"`fetch {OFFICIAL}` gets it, and another name holds another one"
        )
    if called in MINE:
        # Same again: these two are the flows of your own, read out of a directory rather than
        # a clone, so a repository under the name would be listed and never looked at.
        raise ValueError(
            f"{called} is what your own flows in {MINE[called]} are listed under; "
            "pick another name"
        )
    if where(called).exists():
        raise ValueError(f"there is already a flowverse called {called!r}")
    at = where(called) / INDEX
    try:
        clone(said, at)
    except BaseException:
        # Made for the clone and holding nothing now, so that a fetch that failed leaves no
        # flowverse behind it -- and only if it is empty, which another add of the same name
        # that got there first is not.
        with contextlib.suppress(OSError):
            at.parent.rmdir()
        raise
    return Flowverse(
        name=called, url=_url(at), at=at, fetched=_cloned(at), fixed=called == OFFICIAL
    )


def fetch(name: str) -> Flowverse:
    """Fetches a flowverse's index again, or for the first time.

    The first time is what `official` is usually having done to it: it is listed from the
    start and fetched in the background the first time the interface opens. What is installed
    out of it is left exactly as it is: a newer release in the index is an update to offer,
    not one to take.

    Args:
      name: What it is called.

    Returns:
      The flowverse, as it is now.

    Raises:
      ValueError: If there is no such flowverse, or it is one that is not fetched from
        anywhere -- your own flows are a directory you keep, which is not somewhere to fetch
        from.
      OSError: If git is not there, or the fetch failed. What git said is attached.
    """
    one = named(name)
    if one is None:
        raise ValueError(f"no flowverse called {name!r}")
    if not one.url:
        # Two ways to have no URL now that the package's own flows are under `official`:
        # a directory of yours, which is not fetched from anywhere, and a directory under the
        # flowverses home that is not a clone -- what a clone killed partway leaves behind.
        # Telling somebody the second is their own flows directory is telling them to look in
        # a place their problem is not in.
        said = (
            f"a directory of flows of your own, {MINE[name]}"
            if name in MINE
            else "a flowverse with no clone of an index in it; remove it and add it again"
        )
        raise ValueError(f"{name} is {said}; there is nothing to fetch")
    if not one.fetched:
        clone(one.url, one.at)
    else:
        refresh(one.at)
    return Flowverse(
        name=one.name,
        url=one.url,
        at=one.at,
        fetched=_cloned(one.at),
        fixed=one.fixed,
    )


def remove(name: str) -> bool:
    """Takes a flowverse away: its index, and every flow installed out of it.

    The flows go with it because nothing else would ever reach them: an installed flow is
    offered under its flowverse's name, and a name nothing lists is a flow nobody can update,
    uninstall or tell is there.

    Both are in its one directory, which is moved out of its place in one rename before
    anything in it is deleted, so that a delete that fails partway leaves a hidden directory
    nothing lists rather than half an index, or an installed flow with its record and without
    its entry point.

    Args:
      name: What it is called.

    Returns:
      Whether there was one to take away.

    Raises:
      ValueError: If it is one of the three that are always there: humanize's own, and the
        two directories your own flows live in, which are wherever you are.
      OSError: If it will not move out of its place.
    """
    import shutil
    import tempfile

    one = named(name)
    if one is None:
        return False
    if one.fixed:
        raise ValueError(f"{name} is always here; it is not one to take away")
    place = where(name)
    if not place.is_dir():
        return False
    holding = Path(tempfile.mkdtemp(dir=place.parent, prefix=f".{name}."))
    try:
        place.rename(holding / name)
    finally:
        shutil.rmtree(holding, ignore_errors=True)
    return True


def flows(one: Flowverse) -> list[str]:
    """The flows one flowverse offers to run, by the name each is offered under.

    Args:
      one: The flowverse.

    Returns:
      One name per flow in the directories it holds them in, alphabetically -- a directory with
      an `__init__.py` in it, or a single `.py` file, both of which are a module -- as the
      flowverse calls it: `review`, and `alice/kernel` for one installed out of an index's
      `flows/alice/`. A directory without an entry point is what the flows beside it import
      rather than a flow, and neither is a name that starts with an underscore or a dot.
      Nothing at all for an index nothing has been installed out of: what it lists is offered
      to install, not to run.

      One name apiece for `official`, which is kept in two places: a flow the package and an
      install both hold is one name here, and which of the two it resolves to is the order
      :func:`holds` puts them in.
    """
    from .finding import ENTRY, offered
    from .index import kept

    found_: list[str] = []
    for under_ in holds(one):
        names = offered(under_)
        if one.name not in MINE and under_ == kept(one.name):
            # What was installed out of an index under somebody's name is a directory deeper.
            names += [
                f"{owner.name}/{name}"
                for owner in sorted(_directories(under_))
                if OWNER.match(owner.name) and not (owner / ENTRY).is_file()
                for name in offered(owner)
            ]
        found_.extend(name for name in names if name not in found_)
    return sorted(found_)


def plain(url: str) -> str:
    """One URL with whatever was signed into it taken out.

    A flowverse is cloned from wherever somebody said, and a private one in CI is normally
    said as `https://x-access-token:$TOKEN@github.com/org/flows` -- which git writes into the
    clone's config verbatim and is read back out of it here. Where a flowverse came from is
    shown every time they are listed, at a prompt and on a command line both, so a token
    printed once is a token in a scrollback and in the log of every job that ran it.

    Here rather than beside either of the two things that print it: one place a thing is
    scrubbed is one place it is scrubbed, whichever way somebody reached it.

    Args:
      url: Where it was fetched from, as its clone records it.

    Returns:
      The same URL with any user and password between `//` and `@` replaced, and the URL
      untouched where there is none -- which is nearly always.
    """
    return re.sub(r"(?<=//)[^/@]+@", "***@", url, count=1)


def refresh(at: Path) -> None:
    """Takes what a fetched repository says now, whatever is in the clone of it.

    Fetched and reset rather than pulled: what humanize keeps is a copy of somebody else's
    repository, not a branch of your own, and a merge nobody asked for is a fetch that fails
    the next time it is run.

    Args:
      at: The clone.

    Raises:
      OSError: If git is not there, or the fetch failed. What git said is attached.
    """
    _git("-C", str(at), "fetch", "--depth", "1", "origin", "HEAD")
    _git("-C", str(at), "reset", "--hard", "FETCH_HEAD")


def edited(at: Path) -> bool:
    """Whether a clone has anything written into it that fetching it again would undo.

    An index is a copy of somebody else's repository and a fetch resets the clone to what that
    repository says now, so anything written into it goes. That is a fair thing to do on a key
    somebody pressed, and not a fair thing to do behind them: somebody writing the manifest of
    their next release into an index they added would lose it to a fetch nobody asked for.
    Whoever fetches without being asked asks this first.

    Tracked files only, which is exactly what `reset --hard` takes back: a file somebody added
    and never committed survives a fetch, and the `__pycache__` that reading a flow leaves
    behind would otherwise make every repository without a `.gitignore` look edited forever.

    Args:
      at: The clone.

    Returns:
      Whether git has anything to report about it, and False where git cannot be asked -- a
      directory that is not a clone has nothing in it that a fetch could take away, there
      being no fetch.
    """
    return bool(_asked("-C", str(at), "status", "--porcelain", "--untracked-files=no"))


def standing(at: Path) -> str:
    """Which commit a clone stands at, which is what a fetch that brought anything down moves.

    Asked either side of a fetch by whatever fetches without being asked to, so that what is
    done about a fetch that landed is done about the fetches that landed something. Most of
    them land nothing -- the repository has not moved since the last start -- and taking one
    of those for a change is every menu reading its index again to arrive at the list that was
    already drawn.

    Args:
      at: The clone.

    Returns:
      The commit it is on, and "" for a directory that is not a clone, or one git will not
      answer about. That compares unequal to any commit, so a place cloned for the first time
      reads as having changed, which it has: its flows were not there before.
    """
    return _asked("-C", str(at), "rev-parse", "HEAD")


def clone(url: str, at: Path) -> None:
    """Clones a repository, and leaves nothing behind where it could not.

    Cloned beside and then moved into place, so that what is at `at` is either nothing or a
    whole repository and never the middle of one.

    git tidies up after its own failures, but not after being killed: a clone called off for
    taking too long is stopped where it stood, and what it had written so far stays. Written
    straight into `at`, that is a name taken by a flowverse that is not there -- and since a
    name already taken is refused, it is a name nobody can use again until somebody finds the
    directory and removes it. Written beside, it is a hidden directory, and :func:`_swept`
    is what comes by for it.

    And two callers reach one directory as a matter of course: the interface takes what every
    index says now as it opens, and the flow menu fetches one as it is asked to, so asking for
    `official` on a machine where the first fetch of it is still going is two clones of one
    place, each begun before the other had finished. Cloning straight into
    `at` makes the second of them fail on a directory that is already there -- and tidying up
    after that failure by taking `at` away is taking away the clone the first one had just
    written. The move is what settles who won, and whoever lost throws their own copy away and
    says nothing: what they were asking for was a fetched repository, and there is one.

    Which is why what is in the way is swept from here, after the move has failed, rather than
    by whoever is about to call: a caller that cleared the place first would be clearing away
    whatever another caller had just finished writing into it, and that is the whole of what
    the move is for.

    Args:
      url: Where the repository is, as somebody wrote it.
      at: The directory to clone into. One holding a repository by the time the copy made here
        is ready to move in is somebody else's clone, which is left where it is; anything else
        in the way is taken away, having no repository in it to lose.

    Raises:
      OSError: If git is not there, or the clone failed -- and if what is in the way of the
        move will not go, which is the one failure the move can neither answer by letting the
        other one win nor by clearing the place. What git said is attached.
    """
    import shutil
    import tempfile

    # Made here as well as by the callers, since the copy is written beside `at` rather than
    # at it: there has to be somewhere to put it.
    at.parent.mkdir(parents=True, exist_ok=True)
    _swept(at)
    beside = Path(tempfile.mkdtemp(dir=at.parent, prefix=f".{at.name}."))
    beside.rmdir()  # git clones into a directory it makes; this was only to take the name
    try:
        _git("clone", "--depth", "1", _url_of(url), str(beside))
    except BaseException:
        shutil.rmtree(beside, ignore_errors=True)
        raise
    if _moved(beside, at):
        return
    # Nothing that answers for a commit is in the way, so what is there is half a clone a run
    # killed partway left behind, or a directory somebody made by hand: neither is a
    # repository, and neither is anything to keep a fetched one out.
    shutil.rmtree(at, ignore_errors=True)
    if _moved(beside, at):
        return
    shutil.rmtree(beside, ignore_errors=True)
    # Scrubbed, the way every other place that says where a flowverse came from is: a
    # private one is added as `https://x-access-token:$TOKEN@...`, and this is a line in
    # somebody's log.
    raise OSError(f"{at} is in the way of a clone of {plain(url)}, and will not go")


def _moved(beside: Path, at: Path) -> bool:
    """Moves a finished clone into the place it is kept, and says whether one is there now.

    The move is one call, so there is no moment when half of it has happened: what is at `at`
    goes from nothing to a whole repository, whoever is looking.

    Args:
      beside: The clone just written, under a name of its own.
      at: Where it is to be kept.

    Returns:
      Whether `at` holds a repository now -- this one, or the one somebody else got there
      first with, which is the same answer to whoever asked for a clone. False for anything
      else in the way, which is for the caller to clear.

    Note:
      Asked with :func:`standing` rather than by looking for a `.git`, which the half a clone
      a killed run leaves has too -- git writes its config in the first moments. A stump
      taken for somebody else's win is a flowverse listed as fetched with no flows in it, and
      the difference between the two is whether git will name a commit for it.
    """
    import shutil

    try:
        beside.rename(at)
    except OSError:
        if not standing(at):
            return False
        # Somebody else got there first, which is a fetched repository either way, so the
        # copy written here is one to throw away rather than one to put anywhere.
        shutil.rmtree(beside, ignore_errors=True)
    return True


def _swept(at: Path) -> None:
    """Takes away what clones of one name left beside it when they were killed.

    A clone is written beside the place and moved into it, so a run killed partway through one
    leaves a `.index.XXXXXX` in the flowverse's directory holding as much of somebody's
    repository as git had written by then. Nothing reads it -- a hidden directory is neither
    the clone nor a flow installed out of it, which is why the copy is written under one -- so
    nothing would ever notice it either. This is what comes by, on the way past to the next clone of
    that name.

    Only the ones nothing could still be writing. A clone in flight is a directory of exactly
    this shape, written by whoever else is cloning the same place at this moment, and sweeping
    one of those away is the very thing the move is here to stop. So what goes is what is
    older than the longest a clone is given before it is called off: nothing that old is still
    being written to by anything this module started.

    Args:
      at: Where the clone is to be kept, whose name the copies beside it are named after.
    """
    import shutil
    import time

    stale = time.time() - _PATIENCE
    for one in at.parent.glob(f".{at.name}.*"):
        try:
            if one.is_dir() and one.stat().st_mtime < stale:
                shutil.rmtree(one, ignore_errors=True)
        except OSError:
            # One that went while this was looking at it, which is somebody else having
            # swept it: there is nothing here that wants it to still be there.
            continue


def _git(*said: str) -> None:
    """Runs one git command, and says what it said if it would not.

    Args:
      said: The arguments, after `git` itself.

    Raises:
      OSError: If git is not there, or the command failed.
    """
    try:
        done = subprocess.run(
            ["git", *said],
            capture_output=True,
            text=True,
            check=False,
            timeout=_PATIENCE,
        )
    except FileNotFoundError as gone:
        raise OSError(
            "git is not installed here, and a flowverse is a git repository"
        ) from gone
    except subprocess.TimeoutExpired as slow:
        raise OSError(f"git {said[0]} took longer than {_PATIENCE:.0f}s") from slow
    if done.returncode != 0:
        raise OSError(done.stderr.strip() or f"git {said[0]} failed")


def _asked(*said: str) -> str:
    """Runs one git command to read it, and answers with nothing where it could not be run.

    The other half of :func:`_git`, which is for the commands that change something and says
    what git said by raising. This is for the two that are run to be read -- whether a clone
    has been written into, and which commit it stands at -- where git refusing, or not being
    installed at all, is an answer rather than something to raise: both are asked of a
    directory that may not be a clone, and both are asked while something is being drawn.

    Args:
      said: The arguments, after `git` itself.

    Returns:
      What git printed, with the whitespace off it, and "" where it would not run or would
      not answer.
    """
    try:
        done = subprocess.run(
            ["git", *said],
            capture_output=True,
            text=True,
            check=False,
            timeout=_PATIENCE,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


#: What `owner/repo` looks like, which is the one spelling that is not already something git
#: can clone: two names and one slash between them, and nothing that could be a path.
_OWNED = re.compile(r"[A-Za-z0-9][\w.-]*/[A-Za-z0-9][\w.-]*\Z")


def _url_of(said: str) -> str:
    """The URL to clone, from what somebody wrote.

    Args:
      said: A URL, a path to a repository on this machine, or `owner/repo` for one on GitHub
        -- which is how these are usually named, and how the one humanize ships is written
        down.

    Returns:
      Something git can clone.
    """
    if _OWNED.match(said) and not Path(said).expanduser().exists():
        return f"https://github.com/{said}"
    return said


def _called(url: str) -> str:
    """What a flowverse fetched from this URL is called, which is the repository's own name.

    Read as a posix path whatever this machine's separator is: it is a URL or an `owner/repo`,
    which are written with slashes wherever they are typed.
    """
    return PurePosixPath(url.rstrip("/")).name.removesuffix(".git") or "flowverse"


def _cloned(at: Path) -> bool:
    """Whether there is a fetched flowverse at this path."""
    return (at / ".git").exists()


def _url(at: Path) -> str:
    """Where a fetched flowverse came from, as its own clone says.

    Read out of the clone's own config rather than asked of git: this is answered every time
    the flowverses are listed, which is every time a list of flows is drawn, and a subprocess
    apiece per keystroke is a list that lags.

    Args:
      at: Its directory.

    Returns:
      The URL, or "" for one that cannot be read -- which is one that is not there.
    """
    # No interpolation: a `%` in a URL is ordinary -- a percent-encoded password, or a path
    # with one in it -- and configparser's default would read it as the start of a substitution
    # and raise. Lazily, too: it raises where the value is read rather than where the file is,
    # so the read is inside the try along with it.
    held = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        held.read(at / ".git" / "config")
        return held.get('remote "origin"', "url", fallback="").strip()
    except (OSError, configparser.Error):
        return ""


def _directories(at: Path) -> list[Path]:
    """Every directory directly inside one, and nothing at all where there is no such place."""
    try:
        return [path for path in at.iterdir() if path.is_dir()]
    except OSError:
        return []
