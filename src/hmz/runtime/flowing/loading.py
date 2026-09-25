"""What a ref names, and bringing the module that holds it in.

A ref is one of::

    :review                                   a flow in the same module as the flow asking
    humanize1  humanize1:gen-plan             a flow in the same flowverse
    git+https://github.com/humanfia/flowverse@main#humanize1:rlcr
                                              a flow in another flowverse, at a ref

and, where no flow is asking -- a command line naming what to run -- `official/rlar`,
`local/scheduler` and a path, looked up nearest first as :mod:`finding` always has. A flow
named bare is the flow named after its directory, else the one visible flow its module holds,
else nothing: the choice is not the runtime's to make.

A flow is a directory whose `__init__.py` is imported as a module named after it, with the
directory itself on `sys.path` so that what it keeps beside it -- `_humanize1/` beside
`humanize1`'s entry point -- is imported by its plain name. Those names are the flow's while a
run uses it: nothing a run imported is taken out of `sys.modules` while that run goes, two
checkouts claiming one name in one run is a :class:`~hmz.flows.FlowLoadConflict`, and a flow
whose files changed is imported afresh by the next run that nobody else is running it in. A
run asks for a module once; every later `load` of the same ref is a dictionary lookup.

A flowverse named by URL is cloned once per commit into humanize's home, the ref resolved to
the commit it stands at, and loaded from there -- fetched on a thread the first time it is
called rather than when `load` is, so that naming one costs a flow nothing until it is used.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib
import importlib.util
import keyword
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from hmz.flows import (
    FlowDefinitionError,
    FlowException,
    FlowLoadConflict,
    FlowNotFound,
    FlowRefError,
)

from .declaring import NAME
from .engine import FlowImpl, current

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping
    from types import ModuleType

    from hmz.flows import AgentCollection, Budget, EnvCollection, FlowParams

    from .engine import Run

__all__ = [
    "FlowModule",
    "Ref",
    "Remote",
    "load",
    "module_of",
    "parse",
    "pick",
]

#: What a flow's directory is entered by.
ENTRY = "__init__.py"

#: How long one git command is given.
_PATIENCE = 120.0

#: The schemes a VCS ref may be fetched over.
_SCHEMES = frozenset({"https", "http", "ssh", "file", "git"})

#: A commit, written out in full.
_SHA = re.compile(r"[0-9a-f]{40}\Z")


class Ref:
    """A ref, read.

    Attributes:
      url: The repository of a VCS ref, as git fetches it; None otherwise.
      rev: The ref after its `@`, or None for the repository's default branch.
      where: The flow part: a flow's name, `<flowverse>/<flow>`, a path, or "" for
        `:<sub>`.
      sub: The flow inside it after the colon, or "" for the bare form.
    """

    __slots__ = ("rev", "sub", "url", "where")

    def __init__(self, url: str | None, rev: str | None, where: str, sub: str) -> None:
        self.url = url
        self.rev = rev
        self.where = where
        self.sub = sub

    def __repr__(self) -> str:
        return f"Ref(url={self.url!r}, rev={self.rev!r}, where={self.where!r}, sub={self.sub!r})"


def parse(ref: str) -> Ref:
    """Reads a ref.

    Raises:
      FlowRefError: For anything that is not one.
    """
    if not isinstance(ref, str) or not ref.strip():  # pyright: ignore[reportUnnecessaryIsInstance]
        raise FlowRefError(f"{ref!r} is not a flow ref")
    said = ref.strip()
    if "#" in said:
        return _vcs(said)
    if said.startswith(":"):
        sub = said[1:]
        if not NAME.match(sub):
            raise FlowRefError(f"{ref!r}: {sub!r} is not a flow name")
        return Ref(None, None, "", sub)
    where, colon, sub = said.rpartition(":")
    if not colon or "/" in sub or os.sep in sub:
        return Ref(None, None, said, "")
    if not where or not NAME.match(sub):
        raise FlowRefError(f"{ref!r} is not <flow>:<subflow>")
    return Ref(None, None, where, sub)


def _vcs(said: str) -> Ref:
    """Reads a pip-style VCS ref: `git+<url>[@<rev>]#<flow>[:<sub>]`."""
    url, _, fragment = said.partition("#")
    if not url.startswith("git+"):
        raise FlowRefError(
            f"{said!r}: a ref naming another flowverse is git+<url>[@<ref>]#<flow>[:<sub>]"
        )
    split = urlsplit(url.removeprefix("git+"))
    if split.scheme not in _SCHEMES or not (split.netloc or split.scheme == "file"):
        raise FlowRefError(f"{said!r}: {url!r} is not a URL git can fetch")
    path, at, rev = split.path.rpartition("@")
    if not at:
        path, rev = split.path, ""
    if not path.strip("/"):
        raise FlowRefError(f"{said!r}: {url!r} names no repository")
    where, colon, sub = fragment.partition(":")
    if not NAME.match(where) or (colon and not NAME.match(sub)):
        raise FlowRefError(f"{said!r}: #{fragment} is not <flow>[:<subflow>]")
    fetched = split._replace(path=path, fragment="", query="").geturl()
    return Ref(fetched, rev or None, where, sub)


# ------------------------------------------------------------------------ flow modules


class FlowModule:
    """One flow's module, imported, and what it claims of `sys.modules` while it is.

    Attributes:
      at: The flow's directory, or the file of a flow that is one.
      entry: The file its module was imported from.
      name: What it is imported as.
      module: The module.
      claims: The top-level names it holds: its own, and whatever its directory keeps
        beside its entry point.
      pins: How many runs going now use it.
    """

    __slots__ = ("_flows", "at", "claims", "entry", "module", "name", "pins", "stamp")

    def __init__(
        self,
        at: Path,
        entry: Path,
        name: str,
        module: ModuleType,
        claims: tuple[str, ...],
        stamp: tuple[tuple[str, int, int], ...],
    ) -> None:
        self.at = at
        self.entry = entry
        self.name = name
        self.module = module
        self.claims = claims
        self.stamp = stamp
        self.pins = 0
        self._flows: dict[str, FlowImpl] | None = None

    def __repr__(self) -> str:
        return f"<flow module {self.name} at {self.at}>"

    @property
    def verse(self) -> Path:
        """The directory of flows it is one of."""
        return self.at.parent

    @property
    def stem(self) -> str:
        """What the flow is called by its directory, or its file less `.py`."""
        return self.at.name if self.at.is_dir() else self.at.stem

    def flows(self) -> dict[str, FlowImpl]:
        """Every flow defined inside the flow's directory that its module holds, by name.

        A flow the module imported from somewhere else is not one of its own.

        Raises:
          FlowDefinitionError: If two of them share a name.
        """
        if self._flows is not None:
            return self._flows
        found: dict[str, FlowImpl] = {}
        root = str(self.at)
        for value in list(vars(self.module).values()):
            if type(value) is not FlowImpl:
                continue
            made = os.path.realpath(value.fn.__code__.co_filename)
            if made != root and not made.startswith(root + os.sep):
                continue
            other = found.get(value.name)
            if other is not None and other is not value:
                raise FlowDefinitionError(
                    f"{self.at}: two flows are called {value.name!r}"
                )
            found[value.name] = value
            value.ref = f"{self.stem}:{value.name}"
            value.home = self
        if not _initializing(self.module):
            self._flows = found
        return found


def _initializing(module: ModuleType) -> bool:
    spec = getattr(module, "__spec__", None)
    return bool(getattr(spec, "_initializing", False))


def pick(module: FlowModule, sub: str, ref: str) -> FlowImpl:
    """The flow a ref names in a module: by name, or the one a bare ref means.

    Raises:
      FlowNotFound: For a name the module has no flow of, or a bare ref that is not the
        flow named after the directory and not the only visible flow either.
    """
    flows = module.flows()
    if sub:
        found = flows.get(sub)
        if found is None:
            raise FlowNotFound(
                f"{ref}: {module.at} holds no flow called {sub!r}"
                + (f"; it holds {', '.join(sorted(flows))}" if flows else "")
            )
        return found
    named = flows.get(module.stem)
    if named is not None:
        return named
    visible = [one for one in flows.values() if not one.hidden]
    if len(visible) == 1:
        return visible[0]
    if not flows:
        raise FlowNotFound(f"{ref}: {module.at} defines no flow")
    raise FlowNotFound(
        f"{ref}: {module.at} holds {', '.join(sorted(flows))} and none is called "
        f"{module.stem!r}; name one as {module.stem}:<flow>"
    )


#: Every flow module imported, by its directory, and every top-level name one claims.
_MODULES: dict[str, FlowModule] = {}
_CLAIMS: dict[str, FlowModule] = {}

#: Held while modules are brought in or let go. Reentrant: a flow's module may load another
#: flow as it is imported.
_LOCK = threading.RLock()


def module_of(entry: Path, run: Run | None) -> FlowModule:
    """The module of the flow at `entry`, imported if it is not, and pinned for `run`.

    Args:
      entry: The flow's `__init__.py`, or the file of a flow that is one.
      run: The run asking, which keeps what it imports until it ends; None outside one.

    Raises:
      FlowLoadConflict: If another run uses a module under a name this one needs.
      FlowDefinitionError: If the module could not be imported.
    """
    entry = Path(os.path.realpath(entry))
    at = entry.parent if entry.name == ENTRY else entry
    with _LOCK:
        held = _MODULES.get(str(at))
        if held is not None and run is not None and held in run.pinned:
            return held
        if held is not None and held.pins == 0 and held.stamp != _stamp(at):
            _evict(held)
            held = None
        if held is None:
            held = _imported(at, entry)
        if run is not None and held not in run.pinned:
            run.pinned.add(held)
            held.pins += 1
        return held


def pin(held: FlowModule, run: Run) -> None:
    """Keeps a module a run is about to use, as it is, until the run ends.

    Asked of the module a flow already came from, which is the one to keep: a module
    imported again since would be another copy of it.
    """
    with _LOCK:
        if _MODULES.get(str(held.at)) is held and held not in run.pinned:
            run.pinned.add(held)
            held.pins += 1


def unpin(run: Run) -> None:
    """Lets go of what a run imported, as it ends."""
    with _LOCK:
        for held in run.pinned:
            held.pins -= 1
        run.pinned.clear()


def _stamp(at: Path) -> tuple[tuple[str, int, int], ...]:
    """What a flow's Python looks like on disk, cheaply: each file, its time and size."""
    files: list[tuple[str, int, int]] = []
    if at.is_file():
        with contextlib.suppress(OSError):
            said = at.stat()
            files.append((at.name, said.st_mtime_ns, said.st_size))
        return tuple(files)
    for root, directories, names in os.walk(at):
        directories[:] = sorted(
            one
            for one in directories
            if one != "__pycache__" and not one.startswith(".")
        )
        for name in sorted(names):
            if name.endswith(".py"):
                path = Path(root) / name
                with contextlib.suppress(OSError):
                    said = path.stat()
                    files.append((str(path), said.st_mtime_ns, said.st_size))
    return tuple(files)


def _beside(at: Path) -> list[str]:
    """What a flow's directory keeps beside its entry point that imports by a plain name."""
    if not at.is_dir():
        return []
    names: list[str] = []
    with contextlib.suppress(OSError):
        for one in sorted(at.iterdir()):
            if one.name.startswith(".") or one.name == ENTRY:
                continue
            if one.is_dir() and (one / ENTRY).is_file() and one.name.isidentifier():
                names.append(one.name)
            elif one.suffix == ".py" and one.stem.isidentifier():
                names.append(one.stem)
    return names


def _from(module: object, at: Path) -> bool:
    """Whether a module in `sys.modules` was imported from inside `at`."""
    said = getattr(module, "__file__", None)
    if not said:
        return False
    real = os.path.realpath(said)
    root = str(at)
    return real == root or real.startswith(root + os.sep)


def _named(at: Path, entry: Path) -> str:
    """What to import a flow's module as: its own name where that is free."""
    stem = at.name if at.is_dir() else at.stem
    if stem.isidentifier() and not keyword.iskeyword(stem):
        there = sys.modules.get(stem)
        if there is not None:
            if _from(there, at):
                return stem
        else:
            try:
                spec = importlib.util.find_spec(stem)
            except (ImportError, ValueError):
                spec = None
            if spec is None or (
                spec.origin and os.path.realpath(spec.origin) == str(entry)
            ):
                return stem
    safe = re.sub(r"\W", "_", stem)
    return f"_hmz_flow_{safe}_{hashlib.blake2b(str(at).encode(), digest_size=4).hexdigest()}"


def _imported(at: Path, entry: Path) -> FlowModule:
    """Imports a flow's module, claiming its names.

    Raises:
      FlowLoadConflict: If a run going now holds one of those names from elsewhere, or
        something that is not a flow does.
      FlowDefinitionError: If running its entry point failed.
    """
    stem = at.name if at.is_dir() else at.stem
    owner = _CLAIMS.get(stem)
    if owner is not None and owner.at != at and not owner.pins:
        # Somebody else's flow of the same name, that nobody is running: this one takes
        # the name, rather than the one no run needs keeping it.
        _evict(owner)
    name = _named(at, entry)
    claims = (name, *(one for one in _beside(at) if one != name))
    for claimed in claims:
        owner = _CLAIMS.get(claimed)
        if owner is not None and owner.at != at:
            if owner.pins:
                raise FlowLoadConflict(
                    f"{at} and {owner.at} both import {claimed!r}, and a run going now "
                    "uses the second"
                )
            _evict(owner)
        there = sys.modules.get(claimed)
        if there is not None and not _from(there, at):
            raise FlowLoadConflict(
                f"importing {at} would replace the module {claimed!r} "
                f"({getattr(there, '__file__', None) or 'built in'})"
            )
    stamp = _stamp(at)
    there = sys.modules.get(name)
    if there is not None:
        # Imported already, by whoever put the flow's directory on `sys.path` themselves.
        held = FlowModule(at, entry, name, there, claims, stamp)
        _registered(held)
        return held
    if at.is_dir() and str(at) not in sys.path:
        sys.path.insert(0, str(at))
    importlib.invalidate_caches()
    spec = importlib.util.spec_from_file_location(
        name, entry, submodule_search_locations=[str(at)] if at.is_dir() else None
    )
    if (
        spec is None or spec.loader is None
    ):  # pragma: no cover - a .py file always has one
        raise FlowDefinitionError(f"{entry} cannot be imported")
    module = importlib.util.module_from_spec(spec)
    held = FlowModule(at, entry, name, module, claims, stamp)
    _registered(held)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException as error:
        _evict(held)
        if isinstance(error, FlowException) or not isinstance(error, Exception):
            raise
        raise FlowDefinitionError(
            f"importing the flow at {at} failed: {error!r}"
        ) from error
    return held


def _registered(held: FlowModule) -> None:
    _MODULES[str(held.at)] = held
    for claimed in held.claims:
        _CLAIMS[claimed] = held


def _evict(held: FlowModule) -> None:
    """Forgets a module nobody is running: out of `sys.modules`, off `sys.path`."""
    if _MODULES.get(str(held.at)) is held:
        del _MODULES[str(held.at)]
    for claimed in held.claims:
        if _CLAIMS.get(claimed) is held:
            del _CLAIMS[claimed]
    for name, module in list(sys.modules.items()):
        top = name.partition(".")[0]
        if (name == held.name or top in held.claims) and (
            module is held.module or _from(module, held.at)
        ):
            del sys.modules[name]
    with contextlib.suppress(ValueError):
        sys.path.remove(str(held.at))


def forget(under: str | os.PathLike[str] | None = None) -> None:
    """Forgets every flow module nobody is running, which a test does between tests.

    Args:
      under: Forget only the flows kept in this directory or below it -- the copy a test
        made of a flowverse, say -- and leave every other flow imported as it was, so that
        what another test imported of one is still the module the next run uses. None
        for every flow.
    """
    root = None if under is None else Path(os.path.realpath(under))
    with _LOCK:
        for held in list(_MODULES.values()):
            if held.pins:
                continue
            if root is None or held.at == root or root in held.at.parents:
                _evict(held)


# ---------------------------------------------------------------------------- resolving


def load(ref: str, caller_globals: Mapping[str, Any]) -> FlowImpl | Remote:
    """The flow a ref names, from where it was asked for.

    Raises:
      FlowRefError: If `ref` is not a ref, or is relative with nothing to be relative to.
      FlowNotFound: If it names no flow.
      FlowLoadConflict: If loading it would replace a module a run going now uses.
      FlowDefinitionError: If what it names is written wrong.
    """
    said = parse(ref)
    node = current()
    run = None if node is None else node.run
    if said.url is not None:
        remote = Remote(said, ref)
        if run is not None:
            fetched = run.fetched.get((said.url, said.rev))
            if (
                fetched is not None
                and fetched.done()
                and not fetched.cancelled()
                and fetched.exception() is None
            ):
                return remote.settle(fetched.result(), run)
        return remote
    asking = _asking(caller_globals, node)
    if not said.where:
        if asking is None:
            raise FlowRefError(
                f"{ref!r} is relative to the flow asking, and no flow is asking"
            )
        return _sub(asking, said.sub, ref)
    verse = None if asking is None else asking.verse
    if verse is not None and "/" not in said.where:
        entry = _entry(verse, said.where)
        if entry is not None:
            return pick(module_of(entry, run), said.sub, ref)
    return pick(module_of(_found(said.where, ref), run), said.sub, ref)


def _entry(verse: Path, name: str) -> Path | None:
    """The entry point of the flow called `name` in one directory of flows."""
    beside = verse / name / ENTRY
    if beside.is_file():
        return beside
    alone = verse / f"{name}.py"
    return alone if alone.is_file() else None


def _found(where: str, ref: str) -> Path:
    """The entry point of a flow named where no flow is asking: nearest first, or a path.

    Raises:
      FlowNotFound: For a name nothing answers to.
    """
    from .finding import find

    found = find(where)
    if not Path(found).is_file():
        raise FlowNotFound(f"{ref}: no flow is called {where!r}, and it is not a path")
    return Path(found)


class _Scope:
    """The flows of a module this did not import as a flow: a test's, say.

    Those defined in the module, or -- for a package, such as a flow a test imported
    itself -- anywhere inside its directory; and, for a flow defined inside a function,
    those defined beside it.
    """

    __slots__ = ("globals", "locals", "root")

    def __init__(
        self, globals_: Mapping[str, Any], locals_: Mapping[str, Any] | None
    ) -> None:
        self.globals = globals_
        self.locals = locals_
        said = globals_.get("__file__")
        at = Path(os.path.realpath(said)) if isinstance(said, str) else None
        self.root = at.parent if at is not None and at.name == ENTRY else None

    @property
    def verse(self) -> Path | None:
        """The directory of flows a package is one of, or None for a plain module."""
        return None if self.root is None else self.root.parent

    def flows(self) -> dict[str, FlowImpl]:
        found: dict[str, FlowImpl] = {}
        root = None if self.root is None else str(self.root)
        for namespace in (self.locals, self.globals):
            if namespace is None:
                continue
            for value in list(namespace.values()):
                if type(value) is not FlowImpl:
                    continue
                if value.globals is self.globals or (
                    root is not None
                    and os.path.realpath(value.fn.__code__.co_filename).startswith(
                        root + os.sep
                    )
                ):
                    found.setdefault(value.name, value)
        return found


def _asking(caller_globals: Mapping[str, Any], node: Any) -> FlowModule | _Scope | None:
    """Which flow's module a relative ref is relative to.

    The flow directory the asking code is in, whichever of its files it is in; else the
    flow being run, where it was defined outside any flow directory; else the module
    asking, if it defines flows at all.
    """
    said = caller_globals.get("__file__")
    if isinstance(said, str):
        held = _within(Path(os.path.realpath(said)))
        if held is not None:
            return held
    if node is not None and node.impl is not None:
        running: FlowImpl = node.impl
        if running.globals is caller_globals:
            home = running.home
            if home is not None:
                return home
            return _Scope(
                running.globals,
                None if running.locals is running.globals else running.locals,
            )
    scope = _Scope(caller_globals, None)
    return scope if scope.flows() else None


def _within(path: Path) -> FlowModule | None:
    """The imported flow module whose directory, or single file, holds `path`."""
    with _LOCK:
        held = _MODULES.get(str(path))
        if held is not None:
            return held
        for parent in path.parents:
            held = _MODULES.get(str(parent))
            if held is not None:
                return held
    return None


def _sub(asking: FlowModule | _Scope, sub: str, ref: str) -> FlowImpl:
    flows = asking.flows()
    found = flows.get(sub)
    if found is None:
        raise FlowNotFound(
            f"{ref}: no flow called {sub!r} beside the flow asking"
            + (f"; there are {', '.join(sorted(flows))}" if flows else "")
        )
    return found


def home_of(flow: FlowImpl) -> FlowModule | None:
    """The flow module a flow was defined in, if it was imported as one."""
    return _within(Path(os.path.realpath(flow.fn.__code__.co_filename)))


# ------------------------------------------------------------------------- flowverses


class Remote:
    """A flow in another flowverse, fetched the first time it is called or asked about.

    Answers to :class:`hmz.flows.Flow`; once fetched, it is that flow.
    """

    __slots__ = ("_ref", "_said", "flow")

    def __init__(self, said: Ref, ref: str) -> None:
        self._said = said
        self._ref = ref
        self.flow: FlowImpl | None = None

    def __repr__(self) -> str:
        return f"<flow {self._ref}{'' if self.flow else ' (not fetched)'}>"

    def settle(self, checkout: Path, run: Run | None) -> FlowImpl:
        """The flow, out of a fetched checkout."""
        said = self._said
        entry = _entry(checkout / "flows", said.where)
        if entry is None:
            raise FlowNotFound(
                f"{self._ref}: {said.url} has no flow called {said.where!r} in flows/"
            )
        flow = pick(module_of(entry, run), said.sub, self._ref)
        self.flow = flow
        return flow

    def _now(self) -> FlowImpl:
        """The flow, fetched on this thread if it has not been."""
        flow = self.flow
        if flow is None:
            node = current()
            run = None if node is None else node.run
            said = self._said
            assert said.url is not None  # noqa: S101 -- only a VCS ref is remote
            flow = self.settle(pinned(said.url, said.rev), run)
        return flow

    async def fetched(self) -> FlowImpl:
        """The flow, fetched on a thread if it has not been: once per run per URL and ref."""
        flow = self.flow
        if flow is not None:
            return flow
        said = self._said
        assert said.url is not None  # noqa: S101 -- only a VCS ref is remote
        node = current()
        run = None if node is None else node.run
        key = (said.url, said.rev)
        fetching = None if run is None else run.fetched.get(key)
        if fetching is None:
            fetching = asyncio.ensure_future(
                asyncio.to_thread(pinned, said.url, said.rev)
            )
            if run is not None:
                run.fetched[key] = fetching
        return self.settle(await asyncio.shield(fetching), run)

    @property
    def name(self) -> str:
        return self._now().name

    @property
    def description(self) -> str | None:
        return self._now().description

    @property
    def expected_agents(self) -> type[AgentCollection]:
        return self._now().expected_agents

    @property
    def expected_envs(self) -> type[EnvCollection]:
        return self._now().expected_envs

    @property
    def expected_params(self) -> type[FlowParams]:
        return self._now().expected_params

    @property
    def resumable(self) -> bool:
        return self._now().resumable

    async def __call__(
        self,
        task: str,
        *,
        agents: Mapping[str, Any],
        envs: Mapping[str, Any],
        params: Any,
        budget: Budget | None = None,
    ) -> Any:
        flow = self.flow or await self.fetched()
        return await flow(task, agents=agents, envs=envs, params=params, budget=budget)


#: One lock per repository, so that two runs fetching one never clone it twice at once.
_FETCHING: dict[str, threading.Lock] = {}
_FETCHING_LOCK = threading.Lock()


def pinned(url: str, rev: str | None) -> Path:
    """A checkout of a repository at the commit a ref stands at now, cloned if need be.

    Kept under humanize's home by the URL and the commit, so a commit is cloned once and a
    branch costs one `git ls-remote` a run.

    Raises:
      FlowNotFound: If it cannot be fetched, or has no such ref.
    """
    from .verses import under

    kept = (
        under() / ".pinned" / hashlib.blake2b(url.encode(), digest_size=8).hexdigest()
    )
    with _FETCHING_LOCK:
        lock = _FETCHING.setdefault(str(kept), threading.Lock())
    with lock:
        sha = rev if rev is not None and _SHA.match(rev) else _remote_sha(url, rev)
        if sha is not None and (kept / sha / ".git").exists():
            return kept / sha
        kept.mkdir(parents=True, exist_ok=True)
        beside = kept / f".{uuid.uuid4().hex}"
        try:
            _git("clone", "--quiet", "--no-checkout", url, str(beside))
            _git(
                "-C",
                str(beside),
                "checkout",
                "--quiet",
                "--detach",
                sha or rev or "HEAD",
            )
            sha = _asked("-C", str(beside), "rev-parse", "HEAD")
            at = kept / sha
            if not (at / ".git").exists():
                beside.rename(at)
        except OSError as error:
            raise FlowNotFound(
                f"{url}{'@' + rev if rev else ''} could not be fetched: {error}"
            ) from error
        finally:
            shutil.rmtree(beside, ignore_errors=True)
        return at


def _remote_sha(url: str, rev: str | None) -> str | None:
    """The commit a ref stands at in a remote repository, or None where it names none."""
    try:
        said = _asked("ls-remote", url, rev or "HEAD")
    except OSError as error:
        raise FlowNotFound(f"{url} could not be reached: {error}") from error
    lines = [line.split() for line in said.splitlines() if line.strip()]
    peeled = [one[0] for one in lines if len(one) == 2 and one[1].endswith("^{}")]  # noqa: PLR2004
    return peeled[0] if peeled else lines[0][0] if lines else None


def _git(*said: str) -> None:
    _asked(*said)


def _asked(*said: str) -> str:
    """Runs git, answering with what it printed.

    Raises:
      OSError: If git is not there, or failed.
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
        raise OSError("git is not installed here") from gone
    except subprocess.TimeoutExpired as slow:
        raise OSError(f"git {said[0]} took longer than {_PATIENCE:.0f}s") from slow
    if done.returncode != 0:
        raise OSError(done.stderr.strip() or f"git {said[0]} failed")
    return done.stdout.strip()


def modules() -> Iterator[FlowModule]:
    """Every flow module imported now, for a test to look at."""
    with _LOCK:
        yield from list(_MODULES.values())
