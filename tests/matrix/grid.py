"""The regression matrix read back as a grid: a row per feature, a column per CLI.

What each cell came to is heard from the reports pytest makes of it -- on the process that draws
the summary, which under xdist is not the one that ran the cell -- and drawn once the run is
over, by the hooks in `tests/conftest.py`: that is the conftest every process of every run
loads, and a hook anywhere deeper would be heard by the workers and never by the controller.

A cell is labelled as it is collected, with the feature and the CLI it is, on its
`user_properties`: those travel with every report it makes, which the node id alone would
make a parse of.

Each cell is one of:

| Mark   | Meaning                                                              |
|--------|----------------------------------------------------------------------|
| `pass` | it passed                                                            |
| `FAIL` | it failed, or its fixture did: humanize's to answer for              |
| `xfail`| a known bug, written on the feature, still there                     |
| `XPASS`| a known bug that is gone: the mark has to come off                   |
| `n/a`  | the CLI cannot do this at all, which is said before it starts        |
| `skip` | this machine could not give the cell what it needs, which is said    |
| `-`    | not run: no `--run-agents`, or not selected                          |
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

if TYPE_CHECKING:
    import pytest

__all__ = ["heard", "labelled", "reported"]

#: The user property a cell is labelled with, and the two it adds as it runs.
LABEL: Final = "matrix"
PLACE: Final = "matrix_place"
SPENT: Final = "matrix_spent"

#: The colours a report is written in, which a one-line reason has no use for.
_ESCAPES: Final = re.compile(r"\x1b\[[0-9;]*m")

#: How much of a failure the JSON report keeps, for whoever triages it: the end, where it
#: says what.
_DETAIL: Final = 20000

#: How much of a reason a line of the report quotes.
_WIDE: Final = 400

#: What `tests/conftest.py` skips every agent test with, when the run did not ask for them.
_UNASKED: Final = "needs --run-agents"


@dataclass
class _Cell:
    """What one cell came to, as far as its reports have said."""

    feature: str
    cli: str
    order: int
    status: str = "-"
    reason: str = ""
    detail: str = ""
    place: str = ""
    seconds: float = 0.0
    spent: dict[str, float] = field(default_factory=dict[str, float])


#: What a cell that did not pass is listed under, worst first.
_TELLING: Final = (
    ("FAIL", "Failed -- humanize's to answer for:"),
    ("XPASS", "Passed although marked as a known bug -- take the mark off:"),
    ("xfail", "Known bugs, still there:"),
    ("skip", "Skipped -- this machine could not give the cell what it needs:"),
    ("n/a", "Not applicable -- the CLI cannot do this at all:"),
)

#: What a cell is that never ran: nothing to draw a grid of.
_UNRUN: Final = frozenset({"-", "n/a"})

#: Every cell heard of this run, by feature and CLI.
_CELLS: dict[tuple[str, str], _Cell] = {}


def labelled(items: list[pytest.Item]) -> None:
    """Labels each cell of the matrix with the feature and the CLI it is.

    Called as the run is collected, on whichever process collects it.

    Args:
      items: Everything collected.
    """
    for item in items:
        mark = item.get_closest_marker("matrix")
        if mark is None:
            continue
        said: list[object] = [*mark.args]
        named = str(said[0]) if said else ""
        order = int(str(said[1])) if len(said) > 1 else 0
        callspec = getattr(item, "callspec", None)
        cli = str(callspec.params.get("cli", "")) if callspec is not None else ""
        # A row run once says which column it is in, having no CLI to be parametrized by.
        cli = str(said[2]) if len(said) > 2 else cli
        item.user_properties.append(
            (LABEL, {"feature": named, "cli": cli, "order": order})
        )


def _reason(report: pytest.TestReport) -> str:
    """Why a report skipped, as its reason reads."""
    said = report.longrepr
    if isinstance(said, tuple):
        return str(said[2]).removeprefix("Skipped: ")
    return str(said or "")


def _skipped(reason: str) -> str:
    if reason.startswith("unsupported"):
        return "n/a"
    if _UNASKED in reason:
        return "-"
    return "skip"


def _failed(report: pytest.TestReport) -> str:
    """What failed, in a line: the message it crashed with, or the last line that says why."""
    crash = getattr(report.longrepr, "reprcrash", None)
    said = _ESCAPES.sub("", str(getattr(crash, "message", "") or report.longrepr or ""))
    lines = [line.strip() for line in said.splitlines() if line.strip()]
    if crash is None:
        wanted = [
            line for line in lines if line.startswith(("E ", "Failed:", "[XPASS"))
        ]
        lines = wanted[-1:] or lines[-1:]
    return (lines or [""])[0][:_WIDE]


def heard(report: pytest.TestReport) -> None:
    """Takes one report of a cell into the grid: its outcome, its place, what it spent.

    Args:
      report: A report of any phase of any test; one that is no cell is passed over.
    """
    props = dict(report.user_properties)
    label = props.get(LABEL)
    if not isinstance(label, dict):
        return
    said = cast("dict[str, Any]", label)
    key = (str(said["feature"]), str(said["cli"]))
    cell = _CELLS.setdefault(key, _Cell(*key, order=int(said.get("order", 0))))
    if PLACE in props:
        cell.place = str(props[PLACE])
    if isinstance(props.get(SPENT), dict):
        cell.spent = cast("dict[str, float]", props[SPENT])
    cell.seconds += float(report.duration)
    known = hasattr(report, "wasxfail")
    if report.skipped:
        if known:
            cell.status, cell.reason = "xfail", str(getattr(report, "wasxfail", ""))
        elif report.when in {"setup", "call"}:
            cell.reason = _reason(report)
            cell.status = _skipped(cell.reason)
    elif report.failed:
        failed = _failed(report)
        cell.status = "XPASS" if "XPASS(strict)" in str(report.longrepr) else "FAIL"
        if report.when == "teardown" and cell.status == "FAIL":
            failed = f"at teardown: {failed}"
        cell.reason = failed
        cell.detail = _ESCAPES.sub("", str(report.longrepr or ""))[-_DETAIL:]
    elif report.when == "call":
        cell.status, cell.reason = ("XPASS", "passed") if known else ("pass", "")


def _columns() -> list[str]:
    from hmz.coganchor import backends

    order = [one.name for one in backends.PROFILES]
    seen = {cli for _, cli in _CELLS}
    return [cli for cli in order if cli in seen] + sorted(seen - set(order))


def _rows() -> list[str]:
    firsts: dict[str, int] = {}
    for (name, _), cell in _CELLS.items():
        firsts[name] = min(firsts.get(name, cell.order), cell.order)
    return sorted(firsts, key=lambda name: (firsts[name], name))


def _table() -> list[str]:
    """The grid, as a markdown table."""
    columns, rows = _columns(), _rows()
    lines = [
        "| feature | " + " | ".join(columns) + " |",
        "|---|" + "|".join(":-:" for _ in columns) + "|",
    ]
    for name in rows:
        marks = [
            _CELLS[name, cli].status if (name, cli) in _CELLS else "-"
            for cli in columns
        ]
        lines.append(f"| {name} | " + " | ".join(marks) + " |")
    return lines


def _places() -> dict[str, str]:
    held: dict[str, str] = {}
    for (_, cli), cell in sorted(_CELLS.items()):
        if cell.place and cli not in held:
            held[cli] = cell.place
    return held


def _bill() -> dict[str, dict[str, float]]:
    """What each CLI's cells spent, and every cell together."""
    held: dict[str, dict[str, float]] = {}
    for (_, cli), cell in _CELLS.items():
        into = held.setdefault(cli, {"cost": 0.0, "output_tokens": 0.0})
        for what in into:
            into[what] += float(cell.spent.get(what, 0.0))
    total = {
        what: sum(one[what] for one in held.values())
        for what in ("cost", "output_tokens")
    }
    held["all"] = total
    return held


def _counts() -> dict[str, int]:
    counted: dict[str, int] = {}
    for cell in _CELLS.values():
        counted[cell.status] = counted.get(cell.status, 0) + 1
    return counted


def _markdown() -> list[str]:
    """The whole report: the grid, where each column ran, why each cell that did not pass."""
    lines = [*_table(), ""]
    counts = ", ".join(f"{n} {status}" for status, n in sorted(_counts().items()))
    lines.append(f"Cells: {counts}.")
    bill = _bill()["all"]
    lines.append(
        f"Spent: ${bill['cost']:.4f} and {bill['output_tokens']:.0f} output tokens,"
        " as priced by this machine's price list (unpriced models count as $0)."
    )
    places = _places()
    if places:
        lines += ["", "Where each column ran:", ""]
        lines += [f"- `{cli}`: `{place}`" for cli, place in places.items()]
    columns = _columns()
    for status, heading in _TELLING:
        telling = sorted(
            (cell for cell in _CELLS.values() if cell.status == status),
            key=lambda cell: (cell.order, columns.index(cell.cli)),
        )
        if telling:
            lines += ["", heading, ""]
            lines += [
                f"- `{cell.feature}[{cell.cli}]`: {cell.reason}" for cell in telling
            ]
    return lines


def _document() -> dict[str, Any]:
    """The whole report, as JSON."""
    return {
        "features": _rows(),
        "clis": _columns(),
        "cells": {
            name: {
                cli: {
                    "status": cell.status,
                    "reason": cell.reason,
                    "detail": cell.detail,
                    "place": cell.place,
                    "seconds": round(cell.seconds, 1),
                    "spent": cell.spent,
                }
                for (named, cli), cell in _CELLS.items()
                if named == name
            }
            for name in _rows()
        },
        "places": _places(),
        "spent": _bill(),
        "counts": _counts(),
    }


def reported(terminal: pytest.TerminalReporter, config: pytest.Config) -> None:
    """Draws the grid at the foot of a run that ran any cell, and writes it where asked.

    A run that ran none -- every cell left out for want of `--run-agents`, or none selected --
    draws nothing: a grid of dashes under every `uv run pytest` is noise nobody asked for.

    Args:
      terminal: Where the summary is drawn.
      config: The run's configuration, for `--matrix-report`.
    """
    if all(cell.status in _UNRUN for cell in _CELLS.values()):
        return
    lines = _markdown()
    terminal.write_sep("=", "regression matrix: feature x CLI")
    for line in lines:
        terminal.write_line(line)
    where = cast("str | None", config.getoption("--matrix-report"))
    if not where:
        return
    path = Path(where)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".json":
        path.write_text(json.dumps(_document(), indent=2) + "\n", encoding="utf-8")
    else:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    terminal.write_line(f"matrix report written to {path}")
