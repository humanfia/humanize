"""The structural rules of the package tree, in one table.

Two things nothing else can check. The layers keep the dependencies the merged projects had,
gathered now into the directories the tree is made of: `coganchor` is everything humanize
knows about driving a coding agent CLI -- what each one is, driving it, the account it runs
as, the machine its turns land on and the anchor onto that machine -- and it is the layer
`flows` and `runtime` are written against. A flow is written against `flows` and names
nothing else, which is what makes `flows` the layer that names the agents rather than the
flow doing it; `runtime` is what reads a command line into a run, drives it, writes it down
as an epic and reads the whole of it back afterwards -- and composes all of that into the one
object above it, which is what every way in holds. Nothing points both ways, which is checked
here too.

And the target half runs on the target, which may be any architecture, while
:mod:`hmz.coganchor.linux` picks a register map at import time and refuses any architecture it
has not got one for -- so the serving half must not reach the rest of `coganchor`, nor may
anything a caller imports to configure one.

The rules are on the layers alone. Above them sit the ways in: the interface, which reaches
the runtime through the daemon holding the run it is drawing, and the command line, which
joins them and so may name any of them -- and which is checked instead by what a run of it
actually loads. `sdk` is above all of it and is the way in from outside; what says so is that
nothing below it names it.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from hmz.coganchor.transport import build_bundle

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The package tree being read, counted back from this file: three directories up out of
#: `tests/integration/layering/` is the checkout, and `src/` beside it is what the rules
#: below are about. A test that is moved and keeps the old count reads an empty tree, which
#: passes every rule in it.
SRC = Path(__file__).resolve().parents[3] / "src"

#: What each layer may import besides its own subtree and :mod:`hmz` itself. Longest
#: matching layer wins, and a layer it may name covers the modules inside that layer.
ALLOWED: dict[str, set[str]] = {
    # Everything humanize knows about driving a coding agent CLI, which is one layer because
    # it is one capability: the facts about each CLI, the drivers, the accounts a turn runs
    # as, the machine it lands on, where a turn goes when the place taking it cannot, what a
    # token costs, and the anchor that puts an agent's work on another machine. What is
    # inside it names what is beside it freely -- as the insides of `flows`, `tui` and `sdk`
    # do -- and the one edge out is the reporter every layer may reach for, which names
    # nothing above itself and so widens the DAG without bending it.
    "hmz.coganchor": {"hmz.runtime.telemetry"},
    # Except the target half, which is held apart from the rest of its own package. It runs
    # on the target, which may be any architecture and has only what the bundle carried, so
    # it may name the wire and nothing else -- not even the package it sits in, whose name
    # would be leave to name every driver in it.
    "hmz.coganchor.serve": {"hmz.coganchor.proto"},
    # What a run is: driving one, writing it down as it happens, and reading it back
    # afterwards. Held open as its own modules rather than closed as one layer, because what
    # humanize reports about itself lives here and every layer may reach for it -- including
    # the one this names. The front door names only the modules beside it, which is what a
    # front door is: `hmz.runtime.Hmz` is handed through out of `doing`, and nothing above
    # this may reach past it to a module it did not mean to name.
    "hmz.runtime": set(),
    # What an agent is written down as, which is a shape and a file and nothing else: the
    # interface keeps them and a command line reads the same ones, so it sits under both.
    "hmz.runtime.kept": set(),
    # What humanize remembers: what each workspace was set up to run, and the handful of
    # settings that are not a workspace's. A leaf for the reason `kept` is one -- the
    # interface writes them and a command line has to be able to read them without loading
    # the interface to do it -- and it names `kept` because an agent is written down the
    # same way wherever it is written down.
    "hmz.runtime.settings": {"hmz.runtime.kept"},
    # What humanize reports about itself, which every layer may do and none of them may be
    # reached into to do: what goes with a report is handed over as a callable by whoever
    # knows it. So this names only the setting that says whether to report at all.
    "hmz.runtime.telemetry": {"hmz.runtime.settings"},
    # One run of one flow as a directory: the journal, the links to each session's log, and
    # what a flow that can be picked up left behind. It names the agents it drove and the
    # facts about the CLIs they are, and points a link at each of the logs the backend is
    # writing them to -- and a run that is being profiled samples the programs its agents
    # start, which is `tracing`: what a run left behind, read back.
    "hmz.runtime.epic": {"hmz.coganchor", "hmz.runtime.tracing"},
    # Reading the backends' logs back, which needs only where they are.
    "hmz.runtime.tracing": {"hmz.coganchor"},
    # One run packaged up to send somewhere, which is that run read back with every link
    # followed. It names what a run is, the facts about the CLIs that ran it, the accounts
    # whose values it strikes out of everything it carries, and where a profile of a run is
    # written. None of those names it back.
    "hmz.runtime.exporting": {
        "hmz.coganchor",
        "hmz.runtime.epic",
        "hmz.runtime.tracing",
    },
    # Handing a flow the agents it declared, naming them, and running it under an epic. Also
    # reads the `hmz exec` line, which the interface starts a flow from too. What the flow
    # says it drives is `flows`'s to answer.
    "hmz.runtime.runner": {
        "hmz.coganchor",
        "hmz._legacy_flows",
        "hmz.runtime.epic",
        "hmz.runtime.flowing",
        "hmz.runtime.settings",
        "hmz.runtime.telemetry",
    },
    # Everything humanize does to a flow that the flow itself never names: where flows come
    # from and what each is called, what one says it drives, the two readings that refuse one
    # before it can cost anything, compiling an atlas and walking the prophecy it came to, and
    # fetching the skills a flow named. It names what a flow is written against, because
    # reading a flow means reading the mark and the interfaces it declared its agents with; it
    # names the agents those flows drive; and a flow that calls another is written into the
    # epic of the run that called it. And the new flow API's engine, the seam its drivers
    # are written against, and the reading of the flags that name them, all written against
    # `hmz.flows` -- beside the old ones until every way in has moved over.
    "hmz.runtime.flowing": {
        "hmz.coganchor",
        "hmz._legacy_flows",
        "hmz.flows",
        "hmz.runtime.epic",
        "hmz.runtime.telemetry",
    },
    # What a flow is written against, which is why it is also the one import a flow needs:
    # the protocols its agents, environments and context answer to, the moments it hangs
    # hooks on, the exceptions it catches, and the decorator that makes a function a flow.
    # Types, bar three calls -- `flow`, `load` and `Outworlder.new` -- which hand what they
    # are given to the engine in `hmz.runtime.flowing` when they are made, and never at
    # import: see HANDED_THROUGH. It names nothing else of humanize's, not even `coganchor`:
    # a flow is somebody else's repository, and what it imports is a promise.
    "hmz.flows": {"hmz.runtime.flowing"},
    # The old flow API, kept whole under a name nothing new will import until every way in
    # has moved to `hmz.flows` and it can go: the interfaces its flows drive, the mark that
    # makes a function one of them, the marks an atlas declares its graph with, and the
    # vocabulary a turn is described in, handed through from `coganchor`. The one thing it
    # names in `hmz.runtime.flowing` is what it hands back to a flow that calls another, and
    # it names it for a type checker and never at import: see HANDED_THROUGH.
    "hmz._legacy_flows": {"hmz.coganchor", "hmz.runtime.flowing"},
    # humanize as one object: one workspace and everything that can be done in it, composed
    # out of the layers beside it. It is the front door of the runtime rather than a layer of
    # its own -- everything here is one place several callers would otherwise each have
    # written the same answer, and every rule it composes is still written where it is
    # carried out. Everything is reached from inside the call that needs it, which is what
    # keeps `hmz exec` from paying for a tracer.
    "hmz.runtime.doing": {
        "hmz.coganchor",
        "hmz._legacy_flows",
        "hmz.runtime.epic",
        "hmz.runtime.exporting",
        "hmz.runtime.flowing",
        "hmz.runtime.runner",
        "hmz.runtime.settings",
        "hmz.runtime.telemetry",
        "hmz.runtime.tracing",
    },
    # The run held where a terminal closing cannot end it. How one is opened is still none of
    # its business -- it is handed something that opens one and returns when it is over -- but
    # what a run is, is: this is the process a run of the workspace happens in, so it is where
    # the runtime is reached from, and what is running here is a question it answers itself.
    # The front door and nothing past it, so that the half of humanize which is a process and
    # a socket costs the layers it asks and not the ones beside them.
    "hmz.daemon": {"hmz.runtime"},
    "hmz.tui": {
        # The agents, the facts about them, the accounts they run as, what a turn falls back
        # to and what a token costs -- all of which are one layer now, and all of which the
        # sheets read to draw what they are about.
        "hmz.coganchor",
        "hmz._legacy_flows",
        # What a flow says it drives, which the flow picker asks before it offers an agent for
        # a place, and where flows come from, which is the list `/flow` walks.
        "hmz.runtime.flowing",
        # The runs of this directory, which `/epics` lists and picks one up from, and how big
        # a bundle of one came out. Writing one is asked of the runtime like everything else
        # the interface does rather than draws; how many bytes it came to is said in words.
        "hmz.runtime.epic",
        "hmz.runtime.exporting",
        # The agents written down under a name, which the Agents page of `/flow` walks and
        # `hmz exec` reads back. It names nothing, so this widens the DAG without bending it.
        "hmz.runtime.kept",
        # The interface is where humanize's own failures are answered for -- it is the one
        # thing here with somebody to ask -- and where what it does that nobody meant is
        # noticed. The reporter names nothing above itself.
        "hmz.runtime.telemetry",
        # What holds a run where a terminal closing cannot end it, and through it humanize as
        # one object: what starts a flow, gathers a trace of one that has ended, and walks
        # every store the sheets show. Everything the interface does rather than draws is
        # asked of it -- which is why the runner and what humanize remembers are not named
        # here: the sheets reach both through this and nothing here may reach past it to
        # them. Through the daemon and not around it because a run of this workspace is held
        # in a process of its own and this interface is what is drawing in it -- so the thing
        # holding the run is the thing it asks, and a run held apart from a terminal and a run
        # in the terminal somebody typed `hmz` in are one interface rather than two.
        "hmz.daemon",
    },
    # How a tool that is not humanize reaches humanize: the runtime, straight at it, and a run
    # held apart from a terminal, reached over the socket beside it. Nothing below names it,
    # which is what tells a seam somebody outside reaches in through from a seam every way in
    # has to pass through -- it composes nothing and restates nothing, and hands through what
    # the two front doors under it already offer.
    "hmz.sdk": {"hmz.daemon", "hmz.runtime"},
}

#: The pairs the table is allowed to name both ways, and what makes each one a pair rather
#: than a hole. A flow API is the whole of what a flow imports, and a flow that calls another
#: flow writes `load` from it like every other line it writes -- so the façade has to offer a
#: name whose implementation is in the layer above it, `load` being a run of a flow and runs
#: being the runtime's.
#:
#: :mod:`hmz.flows` offers `flow`, `load` and `Outworlder.new`, each of which imports the
#: engine inside the call and hands the call to it; nothing of the runtime is imported at the
#: top of any of its modules, not even for a type checker, which is what
#: :func:`test_the_flow_api_reaches_the_runtime_from_inside_a_call_and_nowhere_else` holds it
#: to. :mod:`hmz._legacy_flows` offers `load` the way it offers everything it does not hold: by
#: name, out of :data:`hmz._legacy_flows._ELSEWHERE`, fetched the moment a flow asks for it
#: and never before, and names the runtime for a type checker alone, which is what
#: :func:`test_the_flow_facade_names_the_runtime_for_types_and_never_at_import` holds it to.
#: So the arrow at import time still points one way, and these stay pairs rather than
#: becoming a habit.
HANDED_THROUGH = {
    ("hmz.flows", "hmz.runtime.flowing"),
    ("hmz._legacy_flows", "hmz.runtime.flowing"),
}

#: What reaching the target half costs besides: the two modules of the command line that route
#: to it, and the front door of the package they route through. All are held to the same bar as
#: the package itself and import their machinery only when it is used. Loaded rather than
#: imported, so this widens what a run may load and not what the serving half may name.
STARTUP = {
    "hmz",
    "hmz.cli",
    "hmz.cli.anchor",
    "hmz.coganchor",
    "hmz.coganchor.anchor",
}


def _module_name(source: Path) -> str:
    """The dotted name a file under ``src/`` is imported as."""
    parts = source.relative_to(SRC).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _imports(source: Path) -> set[str]:
    """Every module of this package a file names in an import.

    Relative spellings are resolved rather than skipped: ``from ..supervisor import Supervisor``
    inside ``serve/`` reaches the agent half just as surely as the absolute spelling, and is the
    form a refactoring tool would write. ``from hmz.coganchor import supervisor`` names that
    module too, so a from-import that resolves to a file on disk counts as naming it.
    """
    package = _module_name(source)
    if source.name != "__init__.py":
        package = package.rpartition(".")[0]

    named: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.Import):
            named.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = importlib.util.resolve_name("." * node.level + module, package)
            named.add(module)
            named.update(f"{module}.{alias.name}" for alias in node.names)
    # A from-import names a module only when one exists on disk; the rest are the objects in it.
    held = {name for name in named if name.split(".")[0] == "hmz" and _is_module(name)}
    # And a package a submodule was taken out of is not a thing named: `from hmz.runtime
    # import telemetry` names the reporter, not everything beside it. The package is there
    # because that is how the spelling reads, and counting it would let one entry in the
    # table say a whole directory the import never touched. Which is the same answer already
    # given to `hmz` itself, whose name prefixes every other -- so that one stays carved out
    # where it is, being the one package nothing is ever imported out of by module.
    return {
        name for name in held if not any(other.startswith(f"{name}.") for other in held)
    }


def _is_module(dotted: str) -> bool:
    """Whether a dotted name is a file or package under ``src/``, rather than a name inside one."""
    path = SRC.joinpath(*dotted.split("."))
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


def _covers(layer: str, name: str) -> bool:
    """Whether naming `layer` is leave to name `name`, which is it or anything inside it."""
    return name == layer or name.startswith(f"{layer}.")


def test_the_package_is_marked_as_typed() -> None:
    """Without the marker, type checking humanize -- here or downstream -- checks nothing."""
    assert (SRC / "hmz" / "py.typed").is_file()


def test_every_layer_imports_only_what_it_may() -> None:
    offenders: dict[str, set[str]] = {}
    for source in sorted(SRC.rglob("*.py")):
        module = _module_name(source)
        layer = max(
            (name for name in ALLOWED if _covers(name, module)), key=len, default=""
        )
        if not layer:
            continue
        bad = {
            name
            for name in _imports(source)
            # `hmz` itself, which is where `home()` is, is every layer's to name. It is
            # answered here rather than written into the table: its name is the prefix of
            # every other, so an entry saying it would silently say all of them.
            if name != "hmz"
            and not any(_covers(allowed, name) for allowed in (layer, *ALLOWED[layer]))
        }
        if bad:
            offenders[module] = bad
    assert not offenders, f"these modules import outside their layer: {offenders}"


def test_no_two_layers_name_each_other() -> None:
    """A table meant to read as a DAG is one: a pair pointing both ways is a packaging error.

    It is what tells a layer that is genuinely below another from two that were put in one
    place and are now holding each other up.
    """
    both = {
        (one, other)
        for one, may in ALLOWED.items()
        for other in may
        if any(_covers(other, named) for named in ALLOWED.get(one, set()))
        and any(_covers(one, named) for named in ALLOWED.get(other, set()))
    }
    assert (
        not both - HANDED_THROUGH - {(other, one) for one, other in HANDED_THROUGH}
    ), f"these layers name each other: {both}"


def test_the_flow_facade_names_the_runtime_for_types_and_never_at_import() -> None:
    """The one pair pointing both ways points one way when anything is actually running.

    What makes :data:`HANDED_THROUGH` a pair rather than a hole in the rule: the façade may
    name the layer above it for a type checker, and must not import it. A flow that never
    calls another flow must not load the runtime by importing the module it writes its own
    `@flow` with, and `hmz exec` reading a line that names no flow must not either.
    """
    tree = ast.parse((SRC / "hmz" / "_legacy_flows" / "__init__.py").read_text())
    typed = {
        node
        for branch in ast.walk(tree)
        if isinstance(branch, ast.If) and ast.unparse(branch.test) == "TYPE_CHECKING"
        for node in ast.walk(branch)
    }
    ran = {
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").startswith("hmz.runtime")
        and node not in typed
    }
    assert not ran, f"the flow façade imports the runtime for real: {ran}"


def test_the_flow_api_reaches_the_runtime_from_inside_a_call_and_nowhere_else() -> None:
    """`hmz.flows` names the engine in the three calls that run, and names nothing else.

    Every import of humanize's own in the package, however it is spelled, is of the package
    itself -- or of `hmz.runtime.flowing` from inside `flow`, `load` or `Outworlder.new` --
    so importing the flow API, which is what every flow does first, costs none of the runtime
    and none of the drivers, and a type checker is given nothing of the runtime either.
    """
    reached: dict[str, set[str]] = {}
    for source in sorted((SRC / "hmz" / "flows").rglob("*.py")):
        package = _module_name(source)
        if source.name != "__init__.py":
            package = package.rpartition(".")[0]
        for node, calls in _imports_within(ast.parse(source.read_text())):
            if isinstance(node, ast.Import):
                named = [alias.name for alias in node.names]
            else:
                module = node.module or ""
                if node.level:
                    module = importlib.util.resolve_name(
                        "." * node.level + module, package
                    )
                named = [module]
            for name in named:
                if name.split(".")[0] != "hmz" or _covers("hmz.flows", name):
                    continue
                if not (calls and calls[0] in HANDING) or not _covers(
                    "hmz.runtime.flowing", name
                ):
                    reached.setdefault(source.name, set()).add(ast.unparse(node))
    assert not reached, f"the flow API reaches past itself: {reached}"


#: The three calls of the flow API that hand their work to the runtime.
HANDING = {"flow", "load", "new"}


def _imports_within(
    tree: ast.AST, calls: tuple[str, ...] = ()
) -> Iterator[tuple[ast.Import | ast.ImportFrom, tuple[str, ...]]]:
    """Every import statement under a node, with the functions it is written inside."""
    for child in ast.iter_child_nodes(tree):
        if isinstance(child, ast.Import | ast.ImportFrom):
            yield child, calls
        inside = (
            (*calls, child.name)
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
            else calls
        )
        yield from _imports_within(child, inside)


def test_importing_the_flow_api_loads_nothing_else_of_humanize() -> None:
    """The static rule again, against what an interpreter importing it actually loads."""
    probe = (
        "import sys\n"
        "import hmz.flows\n"
        "print(' '.join(m for m in sys.modules if m.split('.')[0] == 'hmz'))\n"
    )
    result = subprocess.run(
        [sys.executable, "-X", "importtime", "-c", probe],
        capture_output=True,
        text=True,
        check=True,
    )
    loaded = set(result.stdout.split())
    assert "hmz.flows" in loaded, "the probe imported nothing, so this checks nothing"
    assert loaded <= {"hmz"} | {
        name for name in loaded if _covers("hmz.flows", name)
    }, loaded
    timed = [line for line in result.stderr.splitlines() if " hmz." in line]
    assert all(" hmz.flows" in line for line in timed), timed


def test_every_module_at_the_top_is_a_layer_the_table_governs() -> None:
    """One left out is unchecked, and reads from here exactly like one deliberately exempt.

    A package whose name starts with one underscore is still a package, and is held to the
    table like any other: the old flow API waits at `hmz._legacy_flows` until nothing names it.
    Only the dunder files -- `__init__`, `__main__` and the interpreter's cache -- are not layers.
    """
    named = {
        f"hmz.{path.stem}"
        for path in (SRC / "hmz").iterdir()
        if not path.name.startswith("__")
        and (path.suffix == ".py" or (path / "__init__.py").is_file())
    }
    # The command line joins the layers and so may name any of them.
    assert named - {"hmz.cli"} <= set(ALLOWED)


def test_serving_loads_only_the_permitted_modules(tmp_path: Path) -> None:
    """The static rule again, but against what a real target half actually loads."""
    bundle = build_bundle(tmp_path / "coganchor.pyz")
    probe = (
        "import contextlib, io, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from hmz import cli\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        # A line it reads all the way through rather than `--help`, which now exits before the
        # serving half is reached at all: what is checked is what a run of it loads. The line
        # is refused for its port, which is a return rather than an exit.
        "    cli.main(['internal', 'anchor', 'serve', '--export', '/project:/tmp',\n"
        "              '--listen', 'not-a-port'])\n"
        "print('\\n'.join(m for m in sys.modules if m.split('.')[0] == 'hmz'))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe, str(bundle)],
        capture_output=True,
        text=True,
        # An empty PYTHONPATH proves it all came out of the bundle.
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ""},
        cwd="/",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    loaded = set(result.stdout.split())
    serve = "hmz.coganchor.serve"
    assert f"{serve}.server" in loaded, "the target half did not actually run"
    assert loaded <= ALLOWED[serve] | STARTUP | {
        name for name in loaded if name.startswith(serve)
    }
