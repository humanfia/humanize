"""The skills a flow brings with it, and where they are once they have been fetched.

A flow is a directory, and `skills/` inside it is the skills that flow works by -- laid out
the way every one of these CLIs lays a skill out, one directory apiece with a `SKILL.md` in
it. They travel with the flow: fork it, edit one, and the next run is driven by the edited
one, which is the whole point of a flow being a directory rather than a file.

A role may also name skills that live somewhere else, by writing them where it is declared::

    class Researcher(Agent):
        _skills = ("https://github.com/humanfia/flowverse#deep-research",)

which is a git repository anything can clone and, after the `#`, which of the skills in it is
wanted -- matched against the `skills/*` that repository holds, by the directory each is in.
Without one, every skill that repository holds is brought. Installing a flow fetches every
one its roles name into the installed flow's own `skills/`, with a note in its record of
which came from where, so that what an installed flow works by is in it like the rest of it
and a run of it reaches no network for its skills. A flow that was never installed -- one of
your own, a builtin, a VCS ref -- has them fetched as a run asks for them, into a clone kept
in this machine's own place, `skills/<name>/`, and fetched again the next time.

Nothing here installs anything into a CLI. What is fetched is put in a flow or where humanize
keeps it, and what a session does with it is :func:`hmz.coganchor.agents.skills.mount`: put
where that backend reads a project's own skills for as long as the session lives, and taken
away again after. The skills the person at this machine installed are untouched, being theirs.
"""

from __future__ import annotations

import ast
import hashlib
import shutil
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from hmz import machine
from hmz.coganchor.agents.skills import CARD, SKILLS, Loaded

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "CARD",
    "SKILLS",
    "brought",
    "cached",
    "fetched",
    "named",
    "packed",
    "remote",
    "under",
]

#: What separates the repository from the skill wanted out of it.
_WANTED = "#"


def under() -> Path:
    """Where the skills a flow that was never installed fetched are kept: this machine's own."""
    return machine() / SKILLS


def remote(said: str) -> bool:
    """Whether a skill a role names is somebody else's repository rather than the flow's own."""
    return "#" in said or "://" in said


def brought(at: Path | str, declared: Iterable[str] = ()) -> list[Loaded]:
    """Every skill one flow brings: its own first, then whatever it named.

    Args:
      at: The flow's own directory, which is where its `skills/` is, or "" for a flow that is
        one file and so has none of its own.
      declared: What it named where it was declared -- a git URL apiece, each with an
        optional `#<skill>` saying which of that repository's skills is wanted.

    Returns:
      One per skill, the flow's own in the order they are on disk and the fetched ones in the
      order they were named. A name declared twice is the first of them: the flow's own beats
      a repository's, since a fork that edited a skill meant the edited one. What installing
      the flow fetched into its `skills/` is the repository's it came from, not the flow's own,
      and is read from there without reaching for the repository again.

    Raises:
      OSError: If a repository cannot be fetched, or holds no skill of the name a flow asked
        it for. Said where the flow is being got ready rather than left for the first turn: a
        flow that works by a skill it has not got is not a flow to start and find out about
        an hour in.
    """
    found: list[Loaded] = []
    seen: set[str] = set()
    # "" for a flow that is one file, which has no directory of its own and so has no skills
    # of its own: what is beside such a flow is the other flows, and none of it came with it.
    fetched_in = _fetched_in(Path(at)) if at else {}
    theirs = {name for names in fetched_in.values() for name in names}
    for one in _inside(Path(at) / SKILLS) if at else []:
        if one.name in theirs:
            continue
        seen.add(one.name)
        found.append(Loaded(one.name, one, "this flow"))
    for said in declared:
        if said in fetched_in:
            for name in fetched_in[said]:
                if name not in seen:
                    seen.add(name)
                    found.append(Loaded(name, Path(at) / SKILLS / name, said))
            continue
        url, _, wanted = said.partition(_WANTED)
        wanted = wanted.strip()
        # The one skill it wanted, where the flow has one of that name already: the flow's
        # wins it, so there is nothing to fetch -- a fork of an installed flow runs offline.
        if not url.strip() or wanted in seen:
            continue
        where = fetched(url.strip())
        inside = _inside(where / SKILLS)
        if wanted and not any(one.name == wanted for one in inside):
            # Named and not there: a typo, or a skill that has been renamed upstream. Said
            # here for the reason a repository that cannot be fetched is said here -- a flow
            # working by a skill it has not got is not a flow to start and find out about an
            # hour in -- and it names what the repository does hold, since the answer is
            # usually one of them.
            raise OSError(
                f"{url.strip()} holds no skill called {wanted!r}"
                + (
                    f"; it holds {', '.join(one.name for one in inside)}"
                    if inside
                    else ""
                )
            )
        for one in inside:
            if (wanted and one.name != wanted) or one.name in seen:
                continue
            seen.add(one.name)
            found.append(Loaded(one.name, one, said))
    return found


def named(at: Path) -> list[str]:
    """Every skill a flow's roles name by a URL, as its source writes them.

    Read off the source rather than imported: installing a flow runs none of it, and what a
    role names is a tuple of strings written where the role is declared. One worked out as the
    flow is imported is one this does not see, and a run of it fetches it as it would for a
    flow that was never installed.

    Args:
      at: The flow's own directory.

    Returns:
      Each once, in the order they are first written, the files read alphabetically.
    """
    found: dict[str, None] = {}
    for source in sorted(at.rglob("*.py")):
        try:
            tree = ast.parse(source.read_bytes(), str(source))
        except (OSError, SyntaxError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for line in node.body:
                if isinstance(line, ast.Assign):
                    targets, value = line.targets, line.value
                elif isinstance(line, ast.AnnAssign) and line.value is not None:
                    targets, value = [line.target], line.value
                else:
                    continue
                if not any(
                    isinstance(target, ast.Name) and target.id == "_skills"
                    for target in targets
                ):
                    continue
                for said in ast.walk(value):
                    if (
                        isinstance(said, ast.Constant)
                        and isinstance(said.value, str)
                        and remote(said.value)
                    ):
                        found[said.value] = None
    return list(found)


def packed(at: Path) -> dict[str, list[str]]:
    """Fetches every skill a flow's roles name by a URL into the flow's own `skills/`.

    What an install does to the copy it is about to move into place, so that the installed
    flow holds what it works by.

    Args:
      at: The flow's own directory, which is written into.

    Returns:
      Every URL :func:`named` found, to the skills it brought into the flow -- for the flow's
      record, which is how :func:`brought` tells them from the flow's own. A skill the flow
      has of its own under the same name is the flow's, and is not brought.

    Raises:
      OSError: If a repository cannot be fetched, holds no skill of a name the flow asked it
        for, or a skill cannot be copied in.
    """
    declared = named(at)
    taken: dict[str, list[str]] = {said: [] for said in declared}
    for one in brought(at, declared):
        if one.whose in taken:
            shutil.copytree(one.at, at / SKILLS / one.name)
            taken[one.whose].append(one.name)
    return taken


def _fetched_in(at: Path) -> dict[str, list[str]]:
    """What installing a flow fetched into its `skills/`, by the URL each was named by.

    Read off the record an installed flow carries; nothing for a flow that has none.
    """
    from .index import RECORD, Installed

    try:
        return Installed.model_validate_json((at / RECORD).read_bytes()).skills
    except (OSError, ValueError):
        return {}


def _inside(at: Path) -> list[Path]:
    """Every skill directory inside one, alphabetically.

    Args:
      at: A `skills/` directory, which may not be there at all.

    Returns:
      One per directory holding a `SKILL.md`, which is what makes a directory a skill.
      Nothing at all where there is no such place -- a flow that brings none has no `skills/`,
      which is not a thing to raise about.
    """
    try:
        return sorted(one for one in at.iterdir() if (one / CARD).is_file())
    except OSError:
        return []


def cached(url: str) -> Path:
    """Where the repository at this URL is kept once it has been fetched.

    Args:
      url: The repository, as a flow named it.

    Returns:
      The directory, whether or not anything has been fetched into it. Named after the
      repository and the owner above it, so that whoever looks in there can see what is
      there -- and ended with a digest of the whole URL, because those two names are not
      unique: `acme/skills` on one host and `acme/skills` on another are two repositories,
      and one directory for both is a flow silently working by somebody else's skills.
    """
    said = PurePosixPath(url.rstrip("/"))
    name = said.name.removesuffix(".git") or "skills"
    whose = said.parent.name
    # Kept to what a directory name may be, since a URL holds whatever somebody put in it.
    plain = [one for one in (_safe(whose), _safe(name)) if one]
    digest = hashlib.sha256(url.strip().encode("utf-8")).hexdigest()[:12]
    return under() / "-".join([*plain, digest])


def _safe(said: str) -> str:
    """One part of a URL, as much of it as may be a directory name."""
    return "".join(one for one in said if one.isalnum() or one in "._-").strip(".-")


def fetched(url: str) -> Path:
    """Clones a repository of skills, or brings the clone of it up to date.

    Args:
      url: Where it is, as git takes it.

    Returns:
      The directory it was fetched into.

    Raises:
      OSError: If git is not there, or the fetch failed. What git said is attached, and a
        clone that failed leaves nothing behind to be taken for a fetched one.
    """
    from .verses import clone, refresh

    at = cached(url)
    if (at / ".git").exists():
        try:
            refresh(at)
        except OSError:
            # Fetched before and unreachable now: a network that is down is not a reason to
            # refuse to run a flow whose skills are already on this machine. A fetch another
            # run is doing at the same moment fails the same way, on git's own lock, and this
            # is the same answer to it: what is here already is what this run works by.
            return at
        return at
    at.parent.mkdir(parents=True, exist_ok=True)
    # `clone` writes the copy beside `at` and moves it in, so that what is at `at` is either
    # nothing or a whole repository. A flow's agents fetch as they are got ready, several at
    # once and often the same repository, and two clones into one directory make one broken
    # one; whoever loses the move throws their own copy away and finds a fetched repository
    # there, which is what this was asking for. Written down once there rather than again
    # here -- a clone means the same thing whichever of the two asked for one.
    #
    # And nothing is swept from here first. Half a clone a killed run left is in the way of
    # the move and `clone` takes it away when it gets there, which looks like the same thing
    # and is not: a sweep before the clone is a sweep of whatever another agent has finished
    # writing into that directory in the meantime, and the run reading skills out of it finds
    # them going as it reads.
    clone(url, at)
    return at
