"""CI runs a topic when what its tests import changed, as `docs/contributing/ci.md` says.

`.github/workflows/ci.yml`'s `changes` job lists, a topic at a time, the paths a change has to
touch for `tests/integration/test_<topic>_*.py` to run. Read here against what those tests
import, with `ast`: the `hmz` packages they name, the doubles beside them, and what those
doubles import in turn. A path a filter leaves out is a change that merges with the topic's
tests never run on it.

A unit package's filter is read the same way against the `conftest.py` files above it.
"""

from __future__ import annotations

import ast
import re
from functools import cache
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

#: The tree being read: the repository `tests/` is in.
ROOT = Path(__file__).resolve().parents[2]

#: The tests of every topic, and the doubles they share.
HERE = Path(__file__).parent

#: The topics the `tests` job runs, one at a time.
TOPICS = ("core", "agents", "tui", "daemon", "anchor", "web", "reach", "relay")


def _pattern(glob: str) -> re.Pattern[str]:
    """A filter's glob as the action reads it: `*` in a segment, `**` across, `{a,b}`."""
    out = ""
    at = 0
    while at < len(glob):
        if glob.startswith("**", at):
            out += ".*"
            at += 2
            continue
        out += {"*": "[^/]*", "{": "(?:", "}": ")", ",": "|"}.get(
            glob[at], re.escape(glob[at])
        )
        at += 1
    return re.compile(out)


def _globs(listed: Any) -> list[str]:
    """A filter's globs, the lists a YAML alias nested inside it laid flat."""
    if isinstance(listed, str):
        return [listed]
    return [glob for item in cast("list[Any]", listed) for glob in _globs(item)]


@cache
def _filters() -> dict[str, list[re.Pattern[str]]]:
    """Every filter of the `changes` job, by name."""
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    step = next(
        s for s in workflow["jobs"]["changes"]["steps"] if s.get("id") == "filter"
    )
    filters = cast("dict[str, Any]", yaml.safe_load(step["with"]["filters"]))
    return {
        name: [_pattern(glob) for glob in _globs(listed)]
        for name, listed in filters.items()
    }


def _imported(file: Path, seen: set[Path]) -> set[str]:
    """The paths `file` runs: an `hmz` package's directory, or a file beside this one."""
    if file in seen:
        return set()
    seen.add(file)
    paths: set[str] = set()
    for node in ast.walk(ast.parse(file.read_text())):
        names: list[str] = []
        if isinstance(node, ast.ImportFrom):
            module = ".".join(
                ["tests.integration"] * bool(node.level) + [node.module or ""]
            )
            names = [module, *(f"{module}.{alias.name}" for alias in node.names)]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        for name in names:
            parts = name.strip(".").split(".")
            if (
                parts[0] == "hmz"
                and len(parts) > 1
                and (ROOT / "src/hmz" / parts[1]).is_dir()
            ):
                paths.add(f"src/hmz/{parts[1]}/module.py")
            beside = HERE / f"{parts[-1]}.py"
            if (
                parts[:2] == ["tests", "integration"]
                and len(parts) == 3
                and beside.exists()
            ):
                paths.add(f"tests/integration/{beside.name}")
                paths |= _imported(beside, seen)
    return paths


@pytest.mark.parametrize("topic", TOPICS)
def test_a_topic_runs_when_what_its_tests_import_changed(topic: str) -> None:
    filters = _filters()[f"integration-{topic}"]
    # pytest loads the directory's conftest.py for every topic, and it copies the stand-in loops.
    runs = {"tests/integration/conftest.py", "tests/integration/flows/loop/__init__.py"}
    seen: set[Path] = set()
    for test in HERE.glob(f"test_{topic}_*.py"):
        runs.add(f"tests/integration/{test.name}")
        runs |= _imported(test, seen)

    skipped = sorted(
        path for path in runs if not any(f.fullmatch(path) for f in filters)
    )

    assert not skipped, f"a change to {skipped} would not run the {topic} topic"


@pytest.mark.parametrize(
    "package",
    # The directories that hold tests: a run leaves a `__pycache__` beside them.
    sorted({p.parent.name for p in (ROOT / "tests/unit").glob("*/test_*.py")}),
)
def test_a_package_runs_when_what_every_unit_test_starts_from_changed(
    package: str,
) -> None:
    filters = _filters()[f"unit-{package}"]
    # pytest loads both for every package: their fixtures are under every unit test.
    runs = ["tests/conftest.py", "tests/unit/conftest.py"]

    skipped = [path for path in runs if not any(f.fullmatch(path) for f in filters)]

    assert not skipped, f"a change to {skipped} would not run tests/unit/{package}"
