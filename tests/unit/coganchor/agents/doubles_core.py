"""A coding agent the core tests drive: its turns are whatever the test scripted.

The smallest public subclasses of `AgentBase` and `SessionBase` there are -- an agent that opens
one kind of session, and a session that implements the one abstract hook a backend must
(`_stream`), saying what the test said it says. Everything else a turn goes through -- the
moments, the budget, the watchers, the meters, the shapes -- is the base classes' own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from hmz.coganchor.agents.base import AgentBase, SessionBase
from hmz.coganchor.agents.config import AgentConfig
from hmz.coganchor.agents.event import Event

if TYPE_CHECKING:
    import os
    from collections.abc import Callable, Iterable, Iterator

    from pydantic import BaseModel

#: One turn, as a test scripts it: given the session and what it was told, what it says.
type Script = Callable[[Turns, str], Iterable[Event]]


def answering(text: str = "done", *, named: str = "") -> Script:
    """A script whose every turn says `text`, naming the session `named` once it lands."""

    def said(session: Turns, prompt: str) -> Iterable[Event]:
        del prompt
        if named:
            session.names(named)
        return [Event(kind="result", text=text)]

    return said


class Turns(SessionBase):
    """A conversation whose turns are the agent's script."""

    shapes: ClassVar[bool] = False

    def __init__(
        self, agent: Scripted, cwd: str | os.PathLike[str] | None = None
    ) -> None:
        super().__init__(agent, cwd)
        self.script: Script = agent.script
        #: Every prompt this conversation's backend was handed, as it was handed it.
        self.told: list[str] = []
        #: The shape each of those turns was asked for, or None.
        self.shaped: list[type[BaseModel] | None] = []

    def names(self, session: str) -> None:
        """Has the backend name this conversation, as a driver does once a turn lands."""
        self._adopt(session)

    def _stream(
        self, prompt: str, *, schema: type[BaseModel] | None = None
    ) -> Iterator[Event]:
        self.told.append(prompt)
        self.shaped.append(schema)
        for event in self.script(self, prompt):
            if event.spent.total:
                self._spends(event.spent)
            yield event


class Steered(Turns):
    """A conversation whose backend takes tools, goals and words mid-turn."""

    takes_tools: ClassVar[bool] = True
    steers: ClassVar[bool] = True
    shapes: ClassVar[bool] = True

    def _pursue(self, objective: str) -> str:
        return f"pursued {objective}"


class Scripted(AgentBase):
    """An agent whose sessions say what `script` says, under whichever backend it is told."""

    def __init__(
        self,
        config: AgentConfig | None = None,
        *,
        name: str | None = None,
        backend: str = "double",
        script: Script | None = None,
        session: type[Turns] = Turns,
    ) -> None:
        self._backend = backend
        self.script: Script = script or answering()
        self.session = session
        super().__init__(config or AgentConfig(model="m", effort=""), name=name)

    @property
    def backend(self) -> str:
        return self._backend

    def _remade(self, config: AgentConfig, name: str | None) -> Any:
        return type(self)(
            config,
            name=name,
            backend=self._backend,
            script=self.script,
            session=self.session,
        )

    def new(self, cwd: str | os.PathLike[str] | None = None) -> Turns:
        return self.session(self, cwd)


def heard(agent: AgentBase) -> list[Event]:
    """Everything an agent's turns say from now on, as a watcher hears it."""
    said: list[Event] = []
    agent.watch(lambda _agent, _session, event: said.append(event))
    return said
