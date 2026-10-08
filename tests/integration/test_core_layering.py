"""The layers of `src/hmz`, as `docs/contributing/architecture.md` draws them.

Read off the source with `ast`, and then checked again against what an interpreter actually
loads: a module imports only what its layer may, no two layers name each other but the one
pair `hmz.flows` hands its calls through, and a layer's front door costs no other layer.

`ALLOWED` is the table `docs/.vitepress/theme/components/HmzStack.vue` draws; change both at
once.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.transport import build_bundle

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The tree being read: `src/` beside `tests/`.
SRC = Path(__file__).resolve().parents[2] / "src"

#: What each layer may import besides its own subtree and `hmz` itself. The longest layer a
#: module is under is its layer, and naming a layer covers every module inside it.
ALLOWED: dict[str, set[str]] = {
    "hmz.coganchor": {"hmz.runtime.telemetry"},
    # The target half runs on any architecture with only what the bundle carried.
    "hmz.coganchor.serve": {
        "hmz.coganchor.proto",
        "hmz.coganchor.fence",
        "hmz.coganchor.linux.landlock",
        "hmz.coganchor.linux.seccomp",
        "hmz.coganchor.linux.syscalls",
    },
    "hmz.runtime": set(),
    "hmz.runtime.kept": {"hmz.coganchor.spelling"},
    "hmz.runtime.settings": {
        "hmz.runtime.kept",
        "hmz.coganchor.machines.store",
        "hmz.coganchor.settings",
    },
    "hmz.runtime.telemetry": {"hmz.runtime.settings"},
    "hmz.runtime.epic": {"hmz.coganchor", "hmz.runtime.tracing"},
    "hmz.runtime.tracing": {"hmz.coganchor"},
    # A run read as it happens, which every frontend draws: the same figures in each of them.
    "hmz.runtime.watching": {"hmz.coganchor"},
    "hmz.runtime.exporting": {
        "hmz.coganchor",
        "hmz.runtime.epic",
        "hmz.runtime.tracing",
    },
    "hmz.runtime.runner": {
        "hmz.coganchor",
        "hmz.flows",
        "hmz.runtime.epic",
        "hmz.runtime.flowing",
        "hmz.runtime.kept",
        "hmz.runtime.settings",
        "hmz.runtime.telemetry",
    },
    "hmz.runtime.flowing": {
        "hmz.coganchor",
        "hmz.flows",
        "hmz.runtime.epic",
        "hmz.runtime.telemetry",
    },
    # What a flow imports: it names the engine only from inside `flow`, `load` and
    # `Outworlder.new` (see HANDED_THROUGH).
    "hmz.flows": {"hmz.runtime.flowing"},
    "hmz.runtime.doing": {
        "hmz.coganchor",
        "hmz.flows",
        "hmz.runtime.epic",
        "hmz.runtime.exporting",
        "hmz.runtime.flowing",
        "hmz.runtime.runner",
        "hmz.runtime.settings",
        "hmz.runtime.telemetry",
        "hmz.runtime.tracing",
    },
    "hmz.daemon": {"hmz.runtime"},
    "hmz.tui": {
        "hmz.coganchor",
        "hmz.flows",
        "hmz.runtime.flowing",
        "hmz.runtime.epic",
        "hmz.runtime.exporting",
        "hmz.runtime.kept",
        "hmz.runtime.telemetry",
        "hmz.runtime.watching",
        "hmz.daemon",
    },
    "hmz.sdk": {"hmz.daemon", "hmz.runtime"},
}

#: The one pair allowed to name each other, and only lazily.
HANDED_THROUGH = ("hmz.flows", "hmz.runtime.flowing")

#: The calls of the flow API that hand their work to the engine.
HANDING = {"flow", "load", "new"}


def _module(source: Path) -> str:
    parts = source.relative_to(SRC).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _package(source: Path) -> str:
    """The package a relative import in `source` is resolved against."""
    name = _module(source)
    return name if source.name == "__init__.py" else name.rpartition(".")[0]


def _is_module(dotted: str) -> bool:
    path = SRC.joinpath(*dotted.split("."))
    return path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()


def _covers(layer: str, name: str) -> bool:
    return name == layer or name.startswith(f"{layer}.")


def _layer(module: str) -> str:
    return max((one for one in ALLOWED if _covers(one, module)), key=len, default="")


def _spelled(node: ast.Import | ast.ImportFrom, package: str) -> list[str]:
    """The modules an import statement is written as importing, relative spellings resolved."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not node.level:
        return [node.module or ""]
    return [
        importlib.util.resolve_name("." * node.level + (node.module or ""), package)
    ]


def _named(node: ast.Import | ast.ImportFrom, package: str) -> set[str]:
    """The `hmz` modules one import statement names.

    `from hmz.runtime import telemetry` names `hmz.runtime.telemetry` and not the package it
    was taken out of; `from hmz.runtime import Hmz, telemetry` names both.
    """
    if isinstance(node, ast.Import):
        named = set(_spelled(node, package))
    else:
        (module,) = _spelled(node, package)
        inside = {f"{module}.{alias.name}" for alias in node.names}
        named = {one for one in inside if _is_module(one)}
        if len(named) < len(inside):
            named.add(module)
    return {one for one in named if one.split(".")[0] == "hmz" and _is_module(one)}


def _within(
    tree: ast.AST, calls: tuple[str, ...] = ()
) -> Iterator[tuple[ast.Import | ast.ImportFrom, tuple[str, ...]]]:
    """Every import under a node, with the functions it is written inside."""
    for child in ast.iter_child_nodes(tree):
        if isinstance(child, ast.Import | ast.ImportFrom):
            yield child, calls
        inside = calls
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            inside = (*calls, child.name)
        yield from _within(child, inside)


@cache
def _imports() -> dict[str, frozenset[str]]:
    """Every `hmz` module each module of the tree names, however it is spelled."""
    return {
        _module(source): frozenset(
            one
            for node, _ in _within(ast.parse(source.read_text()))
            for one in _named(node, _package(source))
        )
        for source in sorted(SRC.rglob("*.py"))
    }


def test_the_tree_is_read_at_all() -> None:
    """A moved test reading an empty tree would pass every rule below."""
    assert "hmz.runtime.flowing.engine" in _imports()
    assert (SRC / "hmz" / "py.typed").is_file()


def test_every_module_imports_only_what_its_layer_may() -> None:
    offenders: dict[str, set[str]] = {}
    for module, named in _imports().items():
        if not (layer := _layer(module)):
            continue
        may = (layer, *ALLOWED[layer])
        bad = {
            one
            for one in named
            if one != "hmz" and not any(_covers(allowed, one) for allowed in may)
        }
        if bad:
            offenders[module] = bad
    assert not offenders, f"these import outside their layer: {offenders}"


def test_every_top_level_package_but_the_command_line_is_a_layer() -> None:
    tops = {
        f"hmz.{path.stem}"
        for path in (SRC / "hmz").iterdir()
        if not path.name.startswith("__")
        and (path.suffix == ".py" or (path / "__init__.py").is_file())
    }
    assert tops - {"hmz.cli"} <= set(ALLOWED)


def _may_name(layer: str, other: str) -> bool:
    """Whether the table lets `layer` name `other`, or any module inside it."""
    return any(_covers(one, other) or _covers(other, one) for one in ALLOWED[layer])


def test_no_two_layers_name_each_other_but_the_flow_api_and_its_engine() -> None:
    both = {
        (one, other)
        for one in ALLOWED
        for other in ALLOWED
        if one < other
        and not _covers(one, other)
        and not _covers(other, one)
        and _may_name(one, other)
        and _may_name(other, one)
    }
    assert both <= {HANDED_THROUGH}, both


def test_no_import_cycle_crosses_a_layer_but_the_handed_through_pair() -> None:
    """No module imported from another layer reaches back to the module importing it."""
    flows, engine = HANDED_THROUGH
    edges = {
        module: {
            one
            for one in named
            if one in _imports()
            and not (_covers(flows, module) and _covers(engine, one))
        }
        for module, named in _imports().items()
    }
    cycles: list[tuple[str, str]] = []
    for module, named in edges.items():
        for one in named:
            if _layer(one) == _layer(module):
                continue
            seen, stack = {one}, [one]
            while stack:
                for nxt in edges[stack.pop()] - seen:
                    seen.add(nxt)
                    stack.append(nxt)
            if module in seen:
                cycles.append((module, one))
    assert not cycles, f"these cross-layer imports are part of a cycle: {cycles}"


def test_the_flow_api_names_the_engine_only_inside_the_calls_that_hand_to_it() -> None:
    reached: dict[str, set[str]] = {}
    for source in sorted((SRC / "hmz" / "flows").rglob("*.py")):
        for node, calls in _within(ast.parse(source.read_text())):
            for name in _spelled(node, _package(source)):
                if name.split(".")[0] != "hmz" or _covers("hmz.flows", name):
                    continue
                lazy = bool(calls) and calls[0] in HANDING
                if not (lazy and _covers(HANDED_THROUGH[1], name)):
                    reached.setdefault(source.name, set()).add(ast.unparse(node))
    assert not reached, f"the flow API reaches past itself: {reached}"


def _loaded(*statements: str) -> set[str]:
    """Every `hmz` module a fresh interpreter has loaded after running `statements`."""
    probe = "\n".join(
        [
            "import sys",
            *statements,
            "print(' '.join(m for m in sys.modules if m.split('.')[0] == 'hmz'))",
        ]
    )
    ran = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return set(ran.stdout.split())


@pytest.mark.parametrize(
    "front",
    ["hmz.flows", "hmz.runtime", "hmz.coganchor", "hmz.daemon", "hmz.sdk", "hmz.cli"],
)
def test_importing_a_layer_loads_no_other_layer(front: str) -> None:
    """Every cross-layer import is made inside the call that needs it, not at import."""
    loaded = _loaded(f"import {front}")
    assert front in loaded, "the probe imported nothing, so this checks nothing"
    assert loaded <= {"hmz"} | {one for one in loaded if _covers(front, one)}, loaded


def test_reading_an_exec_line_loads_neither_the_interface_nor_the_daemon() -> None:
    loaded = _loaded(
        "import contextlib, io",
        "from hmz.cli import main",
        "with contextlib.redirect_stdout(io.StringIO()), contextlib.suppress(SystemExit):",
        "    main(['exec', '--help'])",
    )
    assert "hmz.cli" in loaded
    assert not {one for one in loaded if _covers("hmz.tui", one)}, loaded
    assert not {one for one in loaded if _covers("hmz.daemon", one)}, loaded


def test_the_target_half_loads_only_what_it_may(tmp_path: Path) -> None:
    """What a real target half loads out of the bundle, against what its layer may name."""
    bundle = build_bundle(tmp_path / "coganchor.pyz")
    # A line read all the way to the serving half, and refused there for its port.
    probe = (
        "import contextlib, io, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from hmz import cli\n"
        "with contextlib.redirect_stdout(io.StringIO()):\n"
        "    cli.main(['internal', 'anchor', 'serve', '--export', '/project:/tmp',\n"
        "              '--listen', 'not-a-port'])\n"
        "print(' '.join(m for m in sys.modules if m.split('.')[0] == 'hmz'))\n"
    )
    ran = subprocess.run(
        [sys.executable, "-c", probe, str(bundle)],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ""},
        cwd="/",
        check=False,
        timeout=60,
    )
    assert ran.returncode == 0, ran.stderr
    loaded = set(ran.stdout.split())
    serve = "hmz.coganchor.serve"
    assert f"{serve}.server" in loaded, "the target half did not actually run"
    startup = {
        "hmz",
        "hmz.cli",
        "hmz.cli.anchor",
        "hmz.coganchor",
        "hmz.coganchor.anchor",
    }
    assert loaded <= ALLOWED[serve] | startup | {
        one for one in loaded if _covers(serve, one)
    }
