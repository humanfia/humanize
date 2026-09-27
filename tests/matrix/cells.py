"""The regression matrix: every feature, driven through every CLI, on the real thing.

A *cell* is one feature and one CLI. A feature is a small scenario written once, as a test
function decorated with :func:`feature`, and it is run for every CLI humanize drives --
`hmz.coganchor.backends.PROFILES`, the one list of them -- with the ids `test_<feature>[<cli>]`.
What a scenario drives is a surface a person or a program actually reaches humanize by: `hmz
exec` as a subprocess, reading its `--json` stream, or `hmz.sdk.Hmz`, running a tiny flow
written into the test's own directory. Never a driver, and never a file humanize keeps for
itself -- what a run left behind is read back through the SDK's `epics`, which is what the
export and the trace readers are too.

Every cell ends one of four ways, and they are kept apart on purpose, because a matrix that
reads the same for "cannot" and "did not" is a matrix nobody can act on:

- **passed**;
- **unsupported** -- skipped before it starts, with a reason beginning `unsupported:`, because
  the CLI cannot do this at all: the harness serves no mixin for it
  (`hmz.runtime.flowing.spi.HARNESS_CAPABILITIES`), its profile says it cannot
  (`Profile.forks`, `Profile.mounts`), its driver has no rung for it, or it is a documented
  limitation written on the feature;
- **environment** -- skipped with a reason beginning `environment:`, because this machine could
  not give the cell what it needs: the CLI is not installed, no account answers, the provider
  refused or throttled the turn, there is no sshd. Said with what was missing;
- **failed** -- anything else, which is humanize's to answer for. A failure that is known and
  not fixed yet is an `xfail(strict=True)` written on the feature, naming the bug, so that the
  day it is fixed the cell goes red until somebody takes the mark off.

Adding a feature is one function::

    @feature(mixin(SteeringAgentMixin))
    def test_steer(cell: Cell) -> None:
        \"\"\"A word put into a turn that is running reaches it.\"\"\"
        ...

and `docs/contributing/regression-matrix.md` says the rest.
"""

from __future__ import annotations

import contextlib
import dataclasses
import json
import os
import re
import signal
import subprocess
import sys
from typing import TYPE_CHECKING, Any, Final, cast

import pytest

from hmz.coganchor import backends
from hmz.flows import HarnessKind, HarnessRefused, HarnessSandboxed, HarnessThrottled
from tests.matrix import places

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping, Sequence
    from pathlib import Path

    from hmz.coganchor.agents import AgentBase, SessionBase
    from hmz.coganchor.agents.event import Event
    from hmz.runtime import Hmz, Run
    from hmz.runtime.flowing import OutworlderDriver

__all__ = [
    "BUDGET",
    "CLIS",
    "FEATURES",
    "Cell",
    "Exec",
    "Unsettled",
    "feature",
    "forks",
    "mixin",
    "mounts",
    "read_only",
]

#: Every CLI humanize drives, in the order humanize lists them: the grid's columns.
CLIS: Final = tuple(one.name for one in backends.PROFILES)

#: Every feature, by name, in the order declared, with the first line of what it checks: the
#: grid's rows.
FEATURES: dict[str, str] = {}

#: What a run of one cell may spend, as `-b` and the SDK take it. Two caps rather than one: a
#: cost cap over a model nobody prices is one nothing can read, and a token cap alone is one a
#: model thinking out loud reaches without having done anything wrong -- so the tokens are
#: generous and the money is small.
BUDGET: Final = "cost=0.5,output_tokens=40000"
_BUDGETED: Final = {"cost": 0.5, "output_tokens": 40000}

#: The failures that are this machine's rather than humanize's: a provider that refused the
#: credential or throttled the account, a sandbox the machine gives no namespace for. A cell
#: that meets one is skipped, saying which.
#:
#: Not a CLI that is not installed, or would not start: a cell has already found its CLI on
#: this machine and had a word out of it, so one humanize then cannot find -- on the far side
#: of an anchor, say -- is humanize's to answer for.
_ENVIRONMENTAL: Final = (HarnessThrottled, HarnessRefused, HarnessSandboxed)

#: The same failures as `hmz exec` prints them, at the foot of the traceback it exits with.
_SAID: Final = re.compile(
    r"\b(" + "|".join(one.__name__ for one in _ENVIRONMENTAL) + r")\b: (.*)"
)

#: How much of a stream a failure quotes: the end, which is where a traceback says what.
_TAIL: Final = 3000

#: Whether one CLI can do a thing: "" where it can, and why not where it cannot.
type Needs = Callable[[str], str]


def _harness(cli: str) -> HarnessKind:
    return HarnessKind(cli)


def mixin(capability: type) -> Needs:
    """Needs the harness to serve a mixin, as its protocol in `hmz.flows` declares."""
    from hmz.runtime.flowing.spi import HARNESS_CAPABILITIES

    def needs(cli: str) -> str:
        if capability in HARNESS_CAPABILITIES[_harness(cli)]:
            return ""
        return f"{cli} serves no {capability.__name__}"

    return needs


def forks(cli: str) -> str:
    """Needs the CLI to carry a conversation into a second one, as its profile says."""
    profile = backends.named(cli)
    if profile is not None and profile.forks:
        return ""
    return f"{cli} cannot fork a conversation (Profile.forks is False)"


def mounts(cli: str) -> str:
    """Needs the CLI to read a flow's skills from somewhere a session can be given them."""
    profile = backends.named(cli)
    if profile is not None and profile.mounts:
        return ""
    return f"{cli} reads no skill a flow brings (Profile.mounts is empty)"


def read_only(cli: str) -> str:
    """Needs the CLI's driver to have a rung that holds an agent to reading."""
    from hmz.coganchor.agents import driver

    if "read-only" in driver(cli)[0].rungs:
        return ""
    return f"{cli} can be held to nothing but bypass, so READ is never enforced"


@dataclasses.dataclass(frozen=True)
class Unsettled:
    """A known humanize bug a cell cannot be strict about.

    Two kinds: one that fails some runs and not others -- a race, which a strict mark would
    turn into a red cell every time it happened not to happen -- and one whose fix is
    somebody else's change, not yet landed. Marked `xfail` without `strict`: the cell reads
    `xfail` while the bug bites and `XPASS`, said rather than failed, when it does not.

    Attributes:
      reason: The bug, and what fixes it where that is known.
    """

    reason: str


def _summary(doc: str | None) -> str:
    return (doc or "").strip().splitlines()[0] if doc else ""


def feature[F: Callable[..., object]](
    *needs: Needs,
    limits: Mapping[str, str] | None = None,
    xfail: Mapping[str, str | Unsettled] | None = None,
    timeout: float = 900,
) -> Callable[[F], F]:
    """Makes one test function a row of the matrix: the same scenario, for every CLI.

    The function takes `cell`, the fixture handing it a CLI and the place that CLI is run at,
    and anything else pytest can give it. Its name is the feature's, less `test_`.

    Args:
      needs: What a CLI must be able to do for the scenario to mean anything; a CLI that
        cannot is skipped as unsupported, saying why, before anything starts.
      limits: Documented limitations of particular CLIs, by name: the same skip, for what no
        table in humanize says -- with where it is documented in the reason.
      xfail: Known humanize bugs, by CLI, each with the bug it is. Strict, so a fix turns the
        cell red until the mark comes off -- but for an :class:`Unsettled` one.
      timeout: The most one cell of it may take, in seconds.

    Returns:
      What marks the function: parametrized over every CLI, gated behind `--run-agents`,
      grouped by CLI for xdist, and selectable with `-m matrix`.
    """

    def decorate(test: F) -> F:
        name = test.__name__.removeprefix("test_")
        if name in FEATURES:
            raise ValueError(f"the matrix already has a feature called {name}")
        order = len(FEATURES)
        FEATURES[name] = _summary(test.__doc__)
        cells: list[Any] = []
        for cli in CLIS:
            marks: list[pytest.MarkDecorator] = [pytest.mark.xdist_group(cli)]
            why = next((said for said in (one(cli) for one in needs) if said), "")
            why = why or (limits or {}).get(cli, "")
            if why:
                marks.append(pytest.mark.skip(reason=f"unsupported: {why}"))
            elif (known := (xfail or {}).get(cli)) is not None:
                loose = isinstance(known, Unsettled)
                marks.append(
                    pytest.mark.xfail(
                        strict=not loose,
                        reason=known.reason if isinstance(known, Unsettled) else known,
                        run=True,
                    )
                )
            cells.append(pytest.param(cli, id=cli, marks=marks))
        marked = pytest.mark.parametrize("cli", cells)(test)
        marked = pytest.mark.matrix(name, order)(marked)
        marked = pytest.mark.agent(marked)
        return pytest.mark.timeout(timeout)(marked)

    return decorate


def _told(why: str) -> str:
    """What a CLI said about a turn it would not take, without the command line before it."""
    said = why.partition(" exit status ")[2] or why
    return said.strip()[:600]


def _tail(said: str | bytes | None) -> str:
    if isinstance(said, bytes):
        said = said.decode("utf-8", "replace")
    return (said or "")[-_TAIL:]


@dataclasses.dataclass(frozen=True)
class Exec:
    """One `hmz exec`, as it came back: its status, both streams, and the objects it wrote.

    Attributes:
      argv: The line it ran.
      status: What it exited with.
      out: Its stdout.
      err: Its stderr.
      events: Every object of a `--json` run, in order.
    """

    argv: tuple[str, ...]
    status: int
    out: str
    err: str
    events: tuple[dict[str, Any], ...]

    def said(self, kind: str) -> list[str]:
        """The text of every event of one kind, in order."""
        return [
            str(one.get("text") or "") for one in self.events if one["kind"] == kind
        ]

    @property
    def answer(self) -> str:
        """What the last turn answered: its `result` event, or stdout for a plain run."""
        results = self.said("result")
        return results[-1] if results else self.out

    def __str__(self) -> str:
        return (
            f"$ {' '.join(self.argv[2:])}\n-> exit {self.status}\n"
            f"--- stdout (tail)\n{_tail(self.out)}\n--- stderr (tail)\n{_tail(self.err)}"
        )


class Cell:
    """One feature, run through one CLI: where it works, and the two ways in it drives.

    Attributes:
      cli: The backend this cell is about.
      place: Where its turns are taken: the account, the model and the effort.
      workspace: The project directory the run is started in, empty but for what the
        scenario puts there. Flows are kept outside it, so an agent looking around its
        workspace finds nothing of the test.
      flows: Where the scenario's flows are written, one directory apiece.
      root: The test's own temporary directory, which both of those are under.
    """

    def __init__(self, cli: str, place: places.Place, root: Path) -> None:
        self.cli = cli
        self.place = place
        self.root = root
        self.workspace = root / "work"
        self.flows = root / "flows"
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.flows.mkdir(parents=True, exist_ok=True)
        self._hmz: Hmz | None = None

    @property
    def hmz(self) -> Hmz:
        """humanize, held on this cell's workspace through the SDK."""
        if self._hmz is None:
            from hmz.sdk import Hmz

            self._hmz = Hmz(self.workspace)
        return self._hmz

    def agent(self, role: str = "worker", place: places.Place | None = None) -> str:
        """One `-a`: a role, filled by this cell's place or the one given."""
        return f"{role}={(place or self.place).spec()}"

    def flow(
        self, name: str, source: str, skills: Mapping[str, str] | None = None
    ) -> Path:
        """Writes one flow out as a directory of its own, with the skills it brings.

        Args:
          name: What the flow and its directory are called.
          source: Its `__init__.py`.
          skills: Each skill it brings, by name, as the `SKILL.md` that is its whole.

        Returns:
          The directory, which `-f` and the SDK both take as the flow's ref.
        """
        from tests.stubs import written

        return written(self.flows, name, source, skills)

    def exec(
        self,
        flow: Path | str,
        task: str,
        *,
        agents: Sequence[str] = (),
        envs: Sequence[str] = (),
        params: Sequence[str] = (),
        budget: str = BUDGET,
        resume: bool = False,
        as_json: bool = True,
        check: bool = True,
        timeout: float = 600,
    ) -> Exec:
        """Runs `hmz exec` in the workspace, as its own process, and reads back what it said.

        A run that failed for a reason that is the machine's -- see :data:`_ENVIRONMENTAL`
        -- skips the cell, saying which. Any other failure fails it when `check` is set.

        Args:
          flow: The flow, by the directory it was written to or a name `-f` takes.
          task: What it is to do.
          agents: Each `-a`, or none for `worker` filled by this cell's place.
          envs: Each `-e`.
          params: Each `-p`.
          budget: The `-b`, or "" for none.
          resume: Whether to pick up the newest run of the flow here.
          as_json: Whether to read the run as NDJSON, which is how its events are checked.
          check: Whether a run that exits non-zero fails the cell.
          timeout: How long the run may take, in seconds.

        Returns:
          What it came to. Under `as_json`, every stdout line has been read as an object
          already: a line that is not one fails the cell, since `--json` promises nothing else.
        """
        argv = [sys.executable, "-m", "hmz", "exec", "-f", str(flow)]
        for one in agents or (self.agent(),):
            argv += ["-a", one]
        for one in envs:
            argv += ["-e", one]
        for one in params:
            argv += ["-p", one]
        if budget:
            argv += ["-b", budget]
        if resume:
            argv.append("--resume")
        if as_json:
            argv.append("--json")
        argv.append(task)
        # A session of its own, so that a run which has to be put down takes everything it
        # started with it -- the CLI, and the anchor a turn on another machine is run under.
        running = subprocess.Popen(
            argv,
            cwd=self.workspace,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            out, err = running.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(running.pid, signal.SIGKILL)
            _, err = running.communicate()
            pytest.fail(
                f"hmz exec did not return within {timeout:.0f}s\n"
                f"--- stderr (tail)\n{_tail(err)}"
            )
        done = subprocess.CompletedProcess(argv, running.returncode, out, err)
        events: list[dict[str, Any]] = []
        if as_json:
            for line in done.stdout.splitlines():
                try:
                    events.append(cast("dict[str, Any]", json.loads(line)))
                except ValueError:
                    pytest.fail(f"--json wrote a line that is no object: {line!r}")
        held = Exec(
            tuple(argv), done.returncode, done.stdout, done.stderr, tuple(events)
        )
        if done.returncode:
            self._environmental(done.stderr)
            if check:
                pytest.fail(f"hmz exec failed\n{held}")
        return held

    def _environmental(self, err: str) -> None:
        """Skips the cell where what `hmz exec` died of is the machine's, saying which."""
        found = _SAID.findall(err)
        if found:
            kind, why = found[-1]
            pytest.skip(f"environment: {self.place} -- {kind}: {_told(why)}")

    def run(
        self,
        flow: Path | str,
        task: str,
        *,
        agents: Mapping[str, str] | None = None,
        envs: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        budget: Mapping[str, Any] | None = None,
        outworlder: OutworlderDriver | None = None,
        watch: Callable[[AgentBase, SessionBase | None, Event], None] | None = None,
    ) -> Any:
        """Runs a flow through `hmz.sdk.Hmz`, here, to its return.

        Args:
          flow: The flow, by the directory it was written to or a name.
          task: What it is to do.
          agents: What fills each agent role, or `worker` filled by this cell's place.
          envs: What each environment role is.
          params: The flow's params.
          budget: What it may spend, or :data:`BUDGET`.
          outworlder: Whoever is outside the run, or nobody.
          watch: What hears every event of every session, as `Run.watch` hands it.

        Returns:
          What the flow returned. A failure that is the machine's skips the cell.
        """
        running = self.start(
            flow,
            task,
            agents=agents,
            envs=envs,
            params=params,
            budget=budget,
            outworlder=outworlder,
        )
        if watch is not None:
            running.watch(watch)
        with self.environmental():
            return running.run()

    def start(
        self,
        flow: Path | str,
        task: str,
        *,
        agents: Mapping[str, str] | None = None,
        envs: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        budget: Mapping[str, Any] | None = None,
        outworlder: OutworlderDriver | None = None,
    ) -> Run:
        """A run of a flow through the SDK, loaded and not started: see :meth:`run`."""
        return self.hmz.run(
            str(flow),
            task,
            agents=agents or {"worker": self.place.spec()},
            envs=envs or {},
            params=params,
            budget=budget or _BUDGETED,
            outworlder=outworlder,
        )

    @contextlib.contextmanager
    def environmental(self) -> Generator[None]:
        """Skips the cell where what the block raised is the machine's, saying which."""
        try:
            yield
        except _ENVIRONMENTAL as why:
            pytest.skip(
                f"environment: {self.place} -- {type(why).__name__}: {_told(str(why))}"
            )

    @contextlib.contextmanager
    def named(self) -> Generator[places.Place]:
        """An account made through the SDK's accounts facade, and the place to run it at.

        Made out of one of this machine's own accounts for this CLI -- the first whose place
        answers -- under the name `matrix`, in the test's home, and taken off disk after.

        Yields:
          The place, under the account `matrix`.
        """
        found = places.settled(self.cli, account=True)
        if isinstance(found, str):
            pytest.skip(
                f"environment: no account this machine keeps for {self.cli} answers, so"
                f" there is none to make a named account from without a login -- {found}"
            )
        with places.borrowed(self.cli, found.provider, "matrix") as name:
            yield dataclasses.replace(found, provider=name)

    def spent(self) -> dict[str, float]:
        """What every run of this cell spent, in dollars and output tokens, for the grid.

        Read off each run's record of what it used. What the cell *checks* is read through
        the SDK; this is the bill, and a bill it cannot read is a bill of nothing.
        """
        from hmz.runtime.epic import JOURNAL

        cost = tokens = 0.0
        with contextlib.suppress(Exception):
            for epic in self.hmz.epics.all():
                record = epic / JOURNAL
                if not record.is_file():
                    continue
                for line in record.read_text(encoding="utf-8").splitlines():
                    if '"usage"' not in line:
                        continue
                    said = cast("dict[str, Any]", json.loads(line))
                    if said.get("event") == "usage":
                        cost += float(said.get("cost") or 0)
                        tokens += float(said.get("output_tokens") or 0)
        return {"cost": cost, "output_tokens": tokens}
