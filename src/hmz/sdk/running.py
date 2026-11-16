"""Making, running and following an epic through a daemon, as a program of the SDK does.

:class:`Hmz` is the workspace with everything :class:`hmz.runtime.Hmz` offers, its epics run
by a daemon rather than in the calling process (Section 4.4 of python.md): this machine's,
where every role is given as a spec, and a private daemon of the program's own where any is a
driver object (:mod:`hmz.sdk.private`). :meth:`Hmz.runner` has the daemon check the epic,
and :class:`Run` is that epic held on a new exec slot of the workspace and followed by one
epic subscription of a :class:`hmz.sdk.Client` of its own.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import secrets
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hmz.runtime import Hmz as Workspace
from hmz.runtime import Refused

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from pathlib import Path

    from hmz.flows import Budget, FlowParams, Usage
    from hmz.runtime.flowing import AgentDriver, EnvDriver, OutworlderDriver
    from hmz.runtime.flowing.specs import AgentSpec, EnvSpec
    from hmz.sdk.client import Client
    from hmz.sdk.private import Fakes

__all__ = ["Hmz", "Opened", "Run", "Runner"]

#: Why a run whose daemon cannot be reached again ended.
_WENT = "the daemon went away"

#: How long a call to the epic is given to be answered.
_ANSWERING = 30.0

#: How often a run looks at whether its session is still open.
_LOOKING = 0.5


@dataclass(frozen=True, slots=True)
class Opened:
    """One session of a run, as its `opened` record says it (Section 4.9.2.4 of daemon.md).

    Attributes:
      key: `<agent>/<n>`.
      role: The role its agent fills.
      agent: The agent's own name.
      cli: Its harness.
      model: Its model.
      person: Whether it is a person rather than an agent.
      env: Where it works, or None.
      harness: Where its harness runs.
    """

    key: str
    role: str
    agent: str
    cli: str
    model: str
    person: bool
    env: dict[str, Any] | None
    harness: str


class Runner:
    """An epic as the daemon checked it, and what it is to be started with.

    Attributes:
      workspace: The workspace, as the daemon knows it.
      started: What `epic.start` is called with, but the task.
      checked: What the daemon's `flows.check` answered.
    """

    def __init__(
        self,
        workspace: str,
        started: dict[str, Any],
        checked: dict[str, Any],
        fakes: Fakes | None,
    ) -> None:
        self.workspace = workspace
        self.started = started
        self.checked = checked
        self._fakes = fakes

    @property
    def fakes(self) -> Fakes | None:
        """The private daemon's objects, where it is one that holds the epic."""
        return self._fakes

    def client(self) -> Client:
        """A session of its own with the daemon that holds the epic.

        Raises:
          OSError: If the daemon cannot be reached.
        """
        from hmz.sdk.client import Client

        return (
            self._fakes.client()
            if self._fakes is not None
            else Client.local(kind="sdk")
        )


def _spoken(
    given: Mapping[str, Any] | Iterable[Any], kind: str, flow: str, fakes: Fakes
) -> dict[str, str]:
    """What each role is given as the daemon takes it: a spec, or the name of an object.

    Raises:
      Refused: For a role given twice.
    """
    from collections.abc import Mapping

    from hmz.runtime.flowing.specs import AgentSpec, EnvSpec

    pairs: list[tuple[str, Any]] = (
        list(given.items())  # pyright: ignore[reportUnknownArgumentType]
        if isinstance(given, Mapping)
        else [(one.role, one) for one in given]
    )
    said: dict[str, str] = {}
    for role, one in pairs:
        if role in said:
            raise Refused(f"{flow}: duplicate {kind} role {role!r}")
        if isinstance(one, str):
            said[role] = one
        elif isinstance(one, (AgentSpec, EnvSpec)):
            said[role] = str(one).partition("=")[2]
        else:
            said[role] = fakes.keep(one)
    return said


def _budget(budget: Budget | Mapping[str, Any] | None) -> Any:
    """A budget as JSON, checked as `Budget` checks one.

    Raises:
      Refused: For a mapping that is not one.
    """
    import pydantic

    from hmz.flows import Budget

    if budget is None:
        return None
    if not isinstance(budget, Budget):
        try:
            budget = Budget.model_validate(budget)
        except pydantic.ValidationError as why:
            raise Refused(f"the budget is invalid: {why}") from why
    return json.loads(budget.model_dump_json())


def _params(params: Mapping[str, Any] | FlowParams | None) -> Any:
    """The params as JSON: a mapping as it is, a model as its JSON."""
    if params is None:
        return None
    if hasattr(params, "model_dump_json"):
        return json.loads(params.model_dump_json())  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownArgumentType]
    return dict(params)


def checked(
    workspace: str,
    flow: object,
    *,
    agents: Mapping[str, Any] | Iterable[Any],
    envs: Mapping[str, Any] | Iterable[Any],
    params: Any,
    budget: Any,
    profile_flow: bool,
    profile_environment: bool,
    resume: bool | str | os.PathLike[str],
    backup: Iterable[str] | None,
    fakes: Fakes,
) -> Runner:
    """Has the daemon that is to hold an epic check it, and holds what it answered.

    Raises:
      Refused: For everything the daemon refuses, a role given twice and a budget that is
        not one.
      OSError: If the daemon cannot be reached.
    """
    from hmz.daemon import where

    # A flow loaded in this process -- what `run_fake` is handed -- is one more object.
    loaded = not isinstance(flow, (str, os.PathLike))
    named = str(getattr(flow, "ref", flow))
    started: dict[str, Any] = {
        "flow": fakes.keep(flow) if loaded else os.fspath(flow),
        "agents": _spoken(agents, "agent", named, fakes),
        "envs": _spoken(envs, "environment", named, fakes),
        "params": _params(params),
        "budget": _budget(budget),
        "profile_flow": profile_flow,
        "profile_environment": profile_environment,
        "resume": resume if isinstance(resume, bool) else str(resume),
        "backup": None if backup is None else list(backup),
    }
    runner = Runner(where.workspace(workspace), started, {}, fakes or None)
    if started["flow"].startswith("git+"):
        # Loaded only once fetched, which a check does not do: `epic.start` checks it there.
        fakes.close()
        return runner
    try:
        with runner.client() as client:
            runner.checked = client.call(
                "flows.check", {"workspace": runner.workspace, **started}
            )
    finally:
        # A private daemon goes once it has checked: the run started of this is held by
        # one started again, and one never started leaves none behind.
        fakes.close()
    return runner


class Hmz(Workspace):
    """One workspace, and everything Humanize can be asked to do in it, through a daemon."""

    def runner(
        self,
        flow: str | os.PathLike[str],
        *,
        agents: Mapping[str, str | AgentDriver] | Iterable[AgentSpec] = (),
        envs: Mapping[str, str | EnvDriver] | Iterable[EnvSpec] = (),
        params: Mapping[str, Any] | FlowParams | None = None,
        budget: Budget | Mapping[str, Any] | None = None,
        profile_flow: bool = False,
        profile_environment: bool = False,
        resume: bool | str | os.PathLike[str] = False,
        backup: Iterable[str] | None = None,
    ) -> Runner:
        """Has the daemon check the epic these make, and holds what it answered.

        Args:
          flow: The flow, by the name it is offered under, a path, or a ref.
          agents: What each agent role runs, by role -- an `-a` spec after `<role>=`, or a
            driver -- or the specs a line read.
          envs: What each environment role is, likewise with `-e`.
          params: The flow's params, or None for its defaults.
          budget: What the epic may spend; only `chat` runs without one.
          profile_flow: Whether to sample the flow's own Python while it runs.
          profile_environment: Whether to profile the programs its agents start, as well as
            trace them.
          resume: Whether to pick up the newest epic of it here, or the epic to pick up.
          backup: The backup targets the epic goes to, by name, or None for the defaults.

        Returns:
          The epic, checked, and nothing started: this machine's daemon is started where
          none runs, and a private one of this program's where any role is a driver.

        Raises:
          Refused: For everything `hmz exec` refuses before an epic starts.
          OSError: If the daemon cannot be reached.
        """
        from hmz.sdk.private import Fakes

        return checked(
            str(self.workspace),
            flow,
            agents=agents,
            envs=envs,
            params=params,
            budget=budget,
            profile_flow=profile_flow,
            profile_environment=profile_environment,
            resume=resume,
            backup=backup,
            fakes=Fakes(),
        )

    def run(
        self,
        flow: str | os.PathLike[str],
        task: str,
        *,
        agents: Mapping[str, str | AgentDriver] | Iterable[AgentSpec] = (),
        envs: Mapping[str, str | EnvDriver] | Iterable[EnvSpec] = (),
        params: Mapping[str, Any] | FlowParams | None = None,
        budget: Budget | Mapping[str, Any] | None = None,
        profile_flow: bool = False,
        profile_environment: bool = False,
        resume: bool | str | os.PathLike[str] = False,
        outworlder: OutworlderDriver | None = None,
        backup: Iterable[str] | None = None,
    ) -> Run:
        """An epic, checked by the daemon that is to hold it, and not started.

        Args:
          flow: The flow, by the name it is offered under, a path, or a ref.
          task: What it is to do.
          agents: What each agent role runs; see :meth:`runner`.
          envs: What each environment role is; see :meth:`runner`.
          params: The flow's params, or None for its defaults.
          budget: What the epic may spend; only `chat` runs without one.
          profile_flow: Whether to sample the flow's own Python while it runs.
          profile_environment: Whether to profile the programs its agents start, as well as
            trace them.
          resume: Whether to pick up the newest epic of it here, or the epic to pick up.
          outworlder: Whoever answers its `Outworlder` roles, or None for nobody.
          backup: The backup targets the epic goes to, by name, or None for the defaults.

        Raises:
          Refused: For everything `hmz exec` refuses before an epic starts.
          OSError: If the daemon cannot be reached.
        """
        return Run(
            self.runner(
                flow,
                agents=agents,
                envs=envs,
                params=params,
                budget=budget,
                profile_flow=profile_flow,
                profile_environment=profile_environment,
                resume=resume,
                backup=backup,
            ),
            task,
            outworlder=outworlder,
        )

    def exec(self, argv: list[str]) -> Any:
        """Runs the flow one `hmz exec` line names, on what it names, through the daemon.

        Args:
          argv: The line, as `hmz exec` takes it.

        Returns:
          What the flow returned, as its `ended` record says it.

        Raises:
          Refused: If the line was wrong before anything ran.
          OSError: If the daemon cannot be reached.
          SystemExit: If the line is not one argparse accepts.
        """
        line = self.read(argv)
        return self.run(
            line.flow,
            line.task,
            agents=line.agents,
            envs=line.envs,
            params=line.params,
            budget=line.budget,
            profile_flow=line.profile_flow,
            profile_environment=line.profile_environment,
            resume=line.resume,
            backup=line.backup,
        ).run()


class Run:
    """One epic, held by a daemon on a new exec slot of the workspace, and followed."""

    def __init__(
        self, runner: Runner, task: str, *, outworlder: OutworlderDriver | None = None
    ) -> None:
        """Holds the epic as the daemon checked it; nothing is started.

        Args:
          runner: The epic, checked.
          task: What it is to do.
          outworlder: Whoever answers its `Outworlder` roles, or None for nobody.
        """
        self._runner = runner
        self._task = task
        self._outworlder = outworlder
        self._lock = threading.Lock()
        self._ended = threading.Event()
        self._client: Client | None = None
        self._started = False
        self._slot = "exec:"
        self._since: dict[str, Any] | None = None
        self._watching: list[Callable[[str, str | None, dict[str, Any]], None]] = []
        self._opening: list[Callable[[str, Opened], None]] = []
        self._noticing: list[Callable[[str], None]] = []
        self._printing: list[Callable[[str], None]] = []
        self._opened: dict[str, Opened] = {}
        self._open: list[str] = []
        self._names: dict[str, str] = dict(runner.checked.get("names") or {})
        self._epic = ""
        self._usage: Any = None
        self._sub = ""
        self._over = False
        self._claimed: set[str] = set()
        self._raised: BaseException | None = None
        self._result: Any = None

    # ----------------------------------------------------------------------- what it is

    @property
    def flow(self) -> str:
        """The flow, as it was named."""
        return str(self._runner.checked.get("flow") or self._runner.started["flow"])

    @property
    def ref(self) -> str:
        """The flow's canonical ref, as the daemon's check answered it."""
        return str(self._runner.checked.get("ref") or "")

    @property
    def chats(self) -> bool:
        """Whether the flow is the built-in `chat`, as the daemon's check answered it."""
        return bool(self._runner.checked.get("chats"))

    @property
    def task(self) -> str:
        """What it was asked to do."""
        return self._task

    @property
    def declaration(self) -> dict[str, Any]:
        """What the flow declares, as the daemon's check answered it."""
        return dict(self._runner.checked.get("declared") or {})

    @property
    def budget(self) -> Budget:
        """What the epic may spend."""
        from hmz.flows import Budget

        return Budget.model_validate(self._runner.checked.get("budget") or {})

    @property
    def profile_flow(self) -> bool:
        """Whether the epic samples the flow's own Python while it runs."""
        return bool(self._runner.started["profile_flow"])

    @property
    def profile_environment(self) -> bool:
        """Whether the epic profiles the programs its agents start."""
        return bool(self._runner.started["profile_environment"])

    @property
    def backup(self) -> tuple[str, ...]:
        """The backup targets the epic goes to, by name."""
        return tuple(self._runner.checked.get("backup") or ())

    @property
    def usage(self) -> Usage:
        """What the epic has spent so far, as the latest `usage` snapshot says."""
        from hmz.flows import Usage

        with self._lock:
            usage = self._usage
        return Usage() if usage is None else Usage.model_validate(usage)

    @property
    def agents(self) -> tuple[Opened, ...]:
        """Each session still open, oldest first."""
        with self._lock:
            return tuple(one for key, one in self._opened.items() if key in self._open)

    @property
    def names(self) -> dict[str, str]:
        """The name of the agent filling each agent role, by role."""
        with self._lock:
            return dict(self._names)

    @property
    def epic(self) -> Path | None:
        """The epic directory, once the `run` snapshot names it."""
        from hmz.runtime.doing.epics import Epics

        with self._lock:
            name = self._epic
        return Epics(self._runner.workspace).under() / name if name else None

    @property
    def running(self) -> bool:
        """Whether it is going: from `start()` until its `ended` record."""
        return self._started and not self._ended.is_set()

    @property
    def raised(self) -> BaseException | None:
        """What it raised, once its `ended` record has come."""
        return self._raised

    @property
    def result(self) -> Any:
        """What it returned, once its `ended` record has come."""
        return self._result

    def unreadable(self) -> str:
        """Every limit of the budget nothing the epic drives can enforce, in words, or ""."""
        return str(self._runner.checked.get("unreadable") or "")

    # ------------------------------------------------------------------------ observing

    def watch(
        self, listener: Callable[[str, str | None, dict[str, Any]], None]
    ) -> None:
        """Has every `event` record told to `listener`: the agent, its session's key, the record.

        Args:
          listener: What to tell, from whichever thread.
        """
        self._watching.append(listener)

    def opened(self, callback: Callable[[str, Opened], None]) -> None:
        """Has every `opened` record told to `callback`, before any event of that session.

        Args:
          callback: What to tell: the role, and the session.
        """
        self._opening.append(callback)

    def noticed(self, callback: Callable[[str], None]) -> None:
        """Has every `notice` record of the epic told to `callback`.

        Args:
          callback: What to tell.
        """
        self._noticing.append(callback)

    def printed(self, callback: Callable[[str], None]) -> None:
        """Has every line the host printed while it held the epic told to `callback`.

        Args:
          callback: What to tell.
        """
        self._printing.append(callback)

    # -------------------------------------------------------------------------- driving

    def run(self) -> Any:
        """Starts the epic, waits for its `ended` record, and answers what it returned.

        Raises:
          BaseException: What it raised, as :attr:`raised` says it.
        """
        self.start()
        self.wait()
        if self._raised is not None:
            raise self._raised
        return self._result

    def start(self) -> None:
        """Attaches to a new exec slot, sets away or claims its roles, and starts the epic.

        Raises:
          Refused: If `epic.start` was refused.
          RuntimeError: If it has already been started.
          OSError: If the daemon cannot be reached.
        """
        with self._lock:
            if self._started:
                raise RuntimeError("this run has already been started")
            self._started = True
        fakes = self._runner.fakes
        try:
            client = self._attaches(self._runner.client())
            outworlder = self._outworlder
            if outworlder is None:
                self._asks(client, "epic.afk", on=True)
            else:
                for role in self._outworlders():
                    self._asks(client, "epic.claim", role=role)
                    self._claimed.add(role)
                    if outworlder.away_for(role):
                        self._asks(client, "epic.afk", on=True, role=role)
            # As long as loading the flow takes, a fetch of it included.
            self._asks(
                client,
                "epic.start",
                seconds=None,
                task=self._task,
                **self._runner.started,
            )
        except BaseException:
            with self._lock:
                client, self._client = self._client, None
            if client is not None:
                client.close()
            if fakes is not None:
                fakes.close()
            raise
        threading.Thread(target=self._follows, daemon=True, name="hmz-run").start()

    def _outworlders(self) -> list[str]:
        """The `Outworlder` roles of the flow, as the daemon's check declared them."""
        declared: list[dict[str, Any]] = self.declaration.get("agents") or []
        return [str(one["name"]) for one in declared if one.get("auto")]

    def _attaches(self, client: Client) -> Client:
        """Attaches a session to the epic's slot, following it from where it was left."""
        client.heard(self._heard)
        with self._lock:
            self._client = client
            slot, since = self._slot, self._since
        try:
            said = client.call(
                "epic.attach",
                {"workspace": self._runner.workspace, "slot": slot, "since": since},
            )
        except BaseException:
            client.close()
            raise
        with self._lock:
            self._slot = str(said.get("slot") or slot)
            self._sub = str(said["sub"])
        return client

    def _asks(
        self,
        client: Client,
        method: str,
        *,
        seconds: float | None = _ANSWERING,
        **params: Any,
    ) -> Any:
        """Makes one write to the epic of this run's subscription."""
        with self._lock:
            sub = self._sub
        return client.call(
            method,
            {"sub": sub, **params},
            idem=secrets.token_urlsafe(12),
            seconds=seconds,
        )

    def _follows(self) -> None:
        """Attaches again where the session ends before the `ended` record (Section 3.6)."""
        while not self._ended.wait(_LOOKING):
            with self._lock:
                client = self._client
            if client is None or not client.wait(0):
                continue
            if self._runner.fakes is not None:
                self._ends(RuntimeError(_WENT), None)
                return
            try:
                self._attaches(self._runner.client())
            except (OSError, Refused):
                self._ends(RuntimeError(_WENT), None)
                return

    def _heard(self, method: str, params: dict[str, Any]) -> None:
        """Takes one message of the epic's subscription."""
        said: Any = params.get("message")
        if method != "epic.event" or not isinstance(said, dict):
            return
        message: dict[str, Any] = said  # pyright: ignore[reportUnknownVariableType]
        kind = message.get("type")
        seq = message.get("seq")
        with self._lock:
            if kind == "welcome":
                self._since = {"epoch": message.get("epoch"), "seq": 0}
            elif isinstance(seq, int) and self._since is not None:
                self._since["seq"] = seq
        if kind == "event":
            for one in tuple(self._watching):
                one(str(message.get("agent")), message.get("session") or None, message)
        elif kind == "opened":
            self._opens(message)
        elif kind == "notice":
            for one in tuple(self._noticing):
                one(str(message.get("text") or ""))
        elif kind == "printed":
            for one in tuple(self._printing):
                one(str(message.get("text") or ""))
        elif kind == "asked":
            self._answers(message)
        elif kind in ("started", "run", "sessions", "usage"):
            self._snapshot(message)
        elif kind == "ended":
            self._ended_as(message)

    def _opens(self, message: dict[str, Any]) -> None:
        opened = Opened(
            key=str(message.get("key") or ""),
            role=str(message.get("role") or ""),
            agent=str(message.get("agent") or ""),
            cli=str(message.get("cli") or ""),
            model=str(message.get("model") or ""),
            person=bool(message.get("person")),
            env=message.get("env"),
            harness=str(message.get("harness") or ""),
        )
        with self._lock:
            self._opened[opened.key] = opened
            if opened.key not in self._open:
                self._open.append(opened.key)
        for one in tuple(self._opening):
            one(opened.role, opened)

    def _snapshot(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        with self._lock:
            if kind == "started":
                self._names = dict(message.get("names") or self._names)
            elif kind == "run" and message.get("epic"):
                self._epic = str(message["epic"])
            elif kind == "sessions":
                self._open = [str(one) for one in message.get("open") or ()]
            elif kind == "usage" and message.get("usage") is not None:
                self._usage = message["usage"]

    def _answers(self, message: dict[str, Any]) -> None:
        """Answers a question of a role the outworlder claims, on a thread of its own."""
        role, outworlder = str(message.get("role") or ""), self._outworlder
        if outworlder is None or role not in self._claimed:
            return

        def answers() -> None:
            with self._lock:
                client = self._client
            if client is None:
                return
            try:
                said = asyncio.run(
                    outworlder.run(str(message.get("text") or ""), None, role)
                )
            except Exception:  # noqa: BLE001 -- answered with nothing, as away is
                said = ""
            text = said if isinstance(said, str) else _spelled(said)
            with contextlib.suppress(Refused, TimeoutError):
                if text:
                    self._asks(
                        client,
                        "epic.answer",
                        question=message.get("question"),
                        text=text,
                    )
                else:
                    # Nothing to say is the question answered as an away role's is.
                    self._asks(client, "epic.afk", on=True, role=role)
                    if not outworlder.away_for(role):
                        self._asks(client, "epic.afk", on=False, role=role)

        threading.Thread(target=answers, daemon=True, name="hmz-answers").start()

    def _ended_as(self, message: dict[str, Any]) -> None:
        """Takes the `ended` record: what the epic returned or raised."""
        how, why = str(message.get("how") or ""), str(message.get("why") or "")
        with self._lock:
            client, named = self._client, self._epic
        if client is not None and not named:
            # Named by the `run` snapshot that follows; asked now, before letting go.
            with contextlib.suppress(Refused, TimeoutError):
                said = client.call(
                    "epic.status", {"sub": self._sub}, seconds=_ANSWERING
                )
                with self._lock:
                    self._epic = str(said.get("epic") or "")
        fakes = self._runner.fakes
        if fakes is not None and fakes.ran:
            # In this process: the very object the flow returned or raised.
            last = fakes.ran[-1]
            self._ends(last.raised, last.result)
            return
        raised: BaseException | None = None
        if how == "stopped":
            raised = asyncio.CancelledError()
        elif how == "budget":
            from hmz.flows import BudgetExceeded

            raised = BudgetExceeded(why)
        elif how == "refused":
            raised = Refused(why, code=409)
        elif how != "done":
            raised = RuntimeError(why)
        self._ends(raised, message.get("result") if how == "done" else None)

    def _ends(self, raised: BaseException | None, result: Any) -> None:
        """Says how the epic ended, and lets go of the daemon."""
        with self._lock:
            if self._over:
                return
            self._over = True
            self._raised, self._result = raised, result
            client, self._client = self._client, None
        if client is not None:
            client.close()
        # A private daemon goes before the end is said, its home and its epic with it.
        if self._runner.fakes is not None:
            self._runner.fakes.close()
        self._ended.set()

    def wait(self, timeout: float | None = None) -> bool:
        """Waits for the `ended` record, and says whether it has come.

        Args:
          timeout: How long to wait, or None for as long as it takes.
        """
        return self._ended.wait(timeout)

    def stop(self) -> None:
        """Stops the epic (`epic.stop`), without waiting for it to unwind. From any thread."""
        with self._lock:
            client = self._client
        if client is not None:
            with contextlib.suppress(Refused, TimeoutError):
                self._asks(client, "epic.stop")

    def close(self) -> None:
        """Stops the epic, forces it where it is stopping, and lets go of the daemon."""
        self.stop()
        with self._lock:
            client = self._client
        if client is not None and not self._ended.is_set():
            with contextlib.suppress(Refused, TimeoutError):
                self._asks(client, "epic.force")
        # Let go of before its end came: it ended, for this run, as a stopped one does.
        self._ends(asyncio.CancelledError(), None)


def _spelled(said: Any) -> str:
    """An answer that is not text, as its JSON."""
    if hasattr(said, "model_dump_json"):
        return str(said.model_dump_json())
    return json.dumps(said, default=str)
