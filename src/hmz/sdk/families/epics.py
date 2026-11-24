"""An epic of a host, as one of its frontends: started, steered, heard (`epic.*`).

A host is attached to (`epic.attach`), which opens an epic subscription: everything after is
asked of that subscription, and what the host says of its epic is told to it. So the family
makes one call of its own, :meth:`Epics.attach`, and hands back the subscription as an
:class:`Attached` -- the calls made on it, and the messages told to it (Section 4.7 to
Section 4.9 of daemon.md).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Self

from . import Family

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence
    from types import TracebackType

    from . import Subscription

__all__ = ["Attached", "Epics", "Face", "Frontend", "Started"]

#: How often a frontend with nothing told it looks at whether its session is still open.
_LOOKING = 0.5

#: How long a frontend leaving waits to be told it has.
_LEAVING = 5.0


@dataclass(frozen=True)
class Started:
    """An epic a host took the start of."""

    run: int
    """Its epic number on that host."""
    slot: str
    """The slot of the host that holds it."""
    workspace: str
    """The workspace it runs in, as the daemon knows it."""


@dataclass(frozen=True)
class Face:
    """A face a flow made known: the page it shows beside a question."""

    html: str
    title: str


class Frontend:
    """The calls of one epic subscription, each a method of `epic.*` asked with its `sub`.

    What a host refuses is raised as :class:`hmz.sdk.Refused` with the host's own words, 409
    but where Section 4.8 of daemon.md states another code, and 410 once the subscription
    has ended.
    """

    def __init__(self, epics: Epics, sub: str) -> None:
        """Holds one subscription of a client. Made by :class:`Epics`.

        Args:
          epics: The family of the client it was opened through.
          sub: The subscription, as `epic.attach` named it.
        """
        self.sub = sub
        self._epics = epics

    def _asks(
        self,
        method: str,
        /,
        *,
        idem: str | None = None,
        wait: float | None = None,
        **params: Any,
    ) -> Any:
        # The family's own call, made with this subscription.
        return self._epics._call(  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
            method, sub=self.sub, idem=idem, wait=wait, **params
        )

    def start(
        self,
        flow: str,
        task: str | None = None,
        *,
        agents: Mapping[str, str] | None = None,
        envs: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        budget: Mapping[str, Any] | None = None,
        profile_flow: bool | None = None,
        profile_environment: bool | None = None,
        resume: bool | str | None = None,
        backup: Sequence[str] | None = None,
        remember: bool | None = None,
        idem: str | None = None,
        wait: float | None = None,
    ) -> Started:
        """Starts an epic on the host, once the daemon has checked it.

        Args:
          flow: The flow, by the name it is offered under, a path of the daemon's machine,
            or a ref.
          task: What it is to do.
          agents: What each agent role runs: an `-a` spec after `<role>=`, by role.
          envs: What each environment role is: an `-e` spec after `<role>=`, by role.
          params: The flow's params, None for its defaults; a text value is read as `-p`
            reads one.
          budget: What the epic may spend, as a `Budget` is as JSON.
          profile_flow: Whether to sample the flow's own Python while it runs.
          profile_environment: Whether to profile the programs its agents start.
          resume: True to pick up the newest epic of the flow in the workspace, or the epic
            directory to pick up.
          backup: The backup targets it goes to, by name, None for the defaults.
          remember: Whether to write all this down as the workspace's set-up of the flow.
          idem: The key this is done once under.
          wait: How many seconds an answer is waited for, None for as long as loading the
            flow takes.

        Raises:
          hmz.sdk.Refused: For everything `flows.check` refuses, and where the host is
            already running or starting an epic, or is not one that runs flows.
        """
        said = self._asks(
            "epic.start",
            flow=flow,
            task=task,
            agents=None if agents is None else dict(agents),
            envs=None if envs is None else dict(envs),
            params=None if params is None else dict(params),
            budget=None if budget is None else dict(budget),
            profile_flow=profile_flow,
            profile_environment=profile_environment,
            resume=resume,
            backup=None if backup is None else list(backup),
            remember=remember,
            idem=idem,
            wait=wait,
        )
        return Started(
            int(said.get("run") or 0),
            str(said.get("slot") or ""),
            str(said.get("workspace") or ""),
        )

    def say(
        self,
        text: str,
        *,
        to: str | None = None,
        idem: str | None = None,
        wait: float | None = None,
    ) -> None:
        """Says a line to the epic going.

        Args:
          text: The line.
          to: An agent's name, a session `<agent>/<n>` or `outworlder:<role>`; None for a
            waiting `listen` question, else the first session with a turn open.
          idem: The key this is done once under.
          wait: How many seconds an answer is waited for.

        Raises:
          hmz.sdk.Refused: For an empty line, and where no epic is going.
        """
        self._asks("epic.say", text=text, to=to, idem=idem, wait=wait)

    def answer(
        self,
        question: str,
        text: str | None = None,
        *,
        value: Any = None,
        idem: str | None = None,
        wait: float | None = None,
    ) -> None:
        """Answers a question waiting on a person, in words or as a value of its schema.

        Args:
          question: The question's id, `q<n>`.
          text: The answer in words; for a question with options, the number of one; for
            one with a schema, the value as JSON.
          value: The answer as a value of the question's schema, in place of `text`.
          idem: The key this is done once under.
          wait: How many seconds an answer is waited for.

        Raises:
          hmz.sdk.Refused: With code 400 and `data["errors"]` for an answer that does not
            fit its schema, the question staying; and where no such question waits, or it
            is another frontend's to answer.
        """
        self._asks(
            "epic.answer",
            question=question,
            text=text,
            value=value,
            idem=idem,
            wait=wait,
        )

    def face(self, digest: str, *, wait: float | None = None) -> Face:
        """Reads a face the flow made known, by the hash an `asked` record names it by.

        Raises:
          hmz.sdk.Refused: With code 404 where the host keeps no face of that hash.
        """
        said = self._asks("epic.face", hash=digest, wait=wait)
        return Face(str(said["html"]), str(said["title"]))

    def stop(self, *, idem: str | None = None, wait: float | None = None) -> None:
        """Stops the epic going: the turn under way is interrupted and the flow unwinds.

        Raises:
          hmz.sdk.Refused: Where none is going, or one is already stopping.
        """
        self._asks("epic.stop", idem=idem, wait=wait)

    def force(self, *, idem: str | None = None, wait: float | None = None) -> int:
        """Stops the epic going and closes every session of it that has a turn open.

        Returns:
          How many sessions were closed.

        Raises:
          hmz.sdk.Refused: Where no epic is going or stopping.
        """
        return int(self._asks("epic.force", idem=idem, wait=wait).get("closed") or 0)

    def afk(
        self,
        on: bool,  # noqa: FBT001 -- away or back is what is said
        role: str | None = None,
        *,
        idem: str | None = None,
        wait: float | None = None,
    ) -> None:
        """Sets a role, or every role, away or back; away outlives this frontend.

        Args:
          on: True for away: its questions are answered with nothing at once.
          role: The role, None for every role.
          idem: The key this is done once under.
          wait: How many seconds an answer is waited for.

        Raises:
          hmz.sdk.Refused: For a role another frontend claims.
        """
        self._asks("epic.afk", on=on, role=role, idem=idem, wait=wait)

    def claim(
        self,
        role: str,
        *,
        take: bool | None = None,
        idem: str | None = None,
        wait: float | None = None,
    ) -> None:
        """Claims a role, so that only this frontend answers for it, until it leaves.

        Args:
          role: The role.
          take: Whether to take it from a frontend that claims it.
          idem: The key this is done once under.
          wait: How many seconds an answer is waited for.

        Raises:
          hmz.sdk.Refused: Without `take`, for a role another frontend claims.
        """
        self._asks("epic.claim", role=role, take=take, idem=idem, wait=wait)

    def release(
        self, role: str, *, idem: str | None = None, wait: float | None = None
    ) -> None:
        """Releases a role this frontend claims.

        Raises:
          hmz.sdk.Refused: For a role it does not claim.
        """
        self._asks("epic.release", role=role, idem=idem, wait=wait)

    def board(
        self,
        key: str,
        value: str | None = None,
        *,
        idem: str | None = None,
        wait: float | None = None,
    ) -> None:
        """Writes a line of the last epic's board as the user, or removes it.

        Args:
          key: The line.
          value: What it says; None or "" removes it.
          idem: The key this is done once under.
          wait: How many seconds an answer is waited for.

        Raises:
          hmz.sdk.Refused: Where the epic has no board, the line is not on it, or it is not
            the user's to change.
        """
        self._asks("epic.board", key=key, value=value, idem=idem, wait=wait)

    def aside(
        self,
        *,
        side: str | None = None,
        prompt: str | None = None,
        key: str | None = None,
        fork: bool | None = None,
        runs: str | None = None,
        recall: str | None = None,
        kept: str | None = None,
        cwd: str | None = None,
        wait: float | None = None,
    ) -> dict[str, Any]:
        """Opens a side conversation of this frontend, or takes one turn of one.

        Args:
          side: A side conversation this frontend has open, to ask `prompt` of.
          prompt: What to ask it.
          key: The session of the last epic, `<agent>/<n>`, a new one is opened on.
          fork: Whether to fork that session, where its harness forks.
          runs: The agent spec of a session an earlier epic kept, to open a new one of.
          recall: The harness's id of that session.
          kept: Where that epic kept it.
          cwd: The directory it worked in.
          wait: How many seconds an answer is waited for.

        Returns:
          `side` and `forked` for one opened; `answer` for a turn taken.

        Raises:
          hmz.sdk.Refused: For a session or an agent there is none of, and a side
            conversation that is not open or is still answering.
        """
        return dict(
            self._asks(
                "epic.aside",
                side=side,
                prompt=prompt,
                key=key,
                fork=fork,
                runs=runs,
                recall=recall,
                kept=kept,
                cwd=cwd,
                wait=wait,
            )
        )

    def unaside(self, side: str, *, wait: float | None = None) -> None:
        """Closes a side conversation.

        Raises:
          hmz.sdk.Refused: Where this frontend has none open by that name.
        """
        self._asks("epic.unaside", side=side, wait=wait)

    def status(self, *, wait: float | None = None) -> dict[str, Any]:
        """The host's status: every key of Section 4.6.4.1 of daemon.md."""
        return dict(self._asks("epic.status", wait=wait))

    def detach(self, *, wait: float | None = None) -> None:
        """Lets this frontend go: its roles are released, and every epic goes on."""
        self._asks("epic.detach", wait=wait)

    def quit(self, *, idem: str | None = None, wait: float | None = None) -> None:
        """Closes the host, stopping the epic it holds."""
        self._asks("epic.quit", idem=idem, wait=wait)


class Attached(Frontend):
    """One frontend attached to a host: its calls, and what the host tells it.

    A context manager, which lets the frontend go as the block ends.
    """

    def __init__(
        self, epics: Epics, said: Mapping[str, Any], events: Subscription
    ) -> None:
        """Holds what `epic.attach` answered. Made by :meth:`Epics.attach`.

        Args:
          epics: The family of the client it was attached through.
          said: What `epic.attach` answered.
          events: What the host tells the subscription.
        """
        super().__init__(epics, str(said["sub"]))
        self.client = str(said.get("client") or "")
        """This frontend's client id, which `owner` and `claims` name it by."""
        self.workspace = str(said.get("workspace") or "")
        """The workspace of the host, as the daemon knows it."""
        self.slot = str(said.get("slot") or "")
        """The host's slot: the one made, for one asked for as `chat:` or `exec:` alone."""
        self.events = events
        """The `params` of each `epic.event` notification: `sub` and `message`."""
        self.over = False
        """Whether nothing more will be told: `gone` was, this was closed, or the session ended."""

    def next(self, seconds: float | None = None) -> dict[str, Any] | None:
        """The next message of the host, or None where none came in time or none will.

        Args:
          seconds: How long to wait for one, None for as long as it takes.
        """
        ending = None if seconds is None else time.monotonic() + seconds
        while not self.over:
            left = _LOOKING if ending is None else ending - time.monotonic()
            said = self.events.next(max(0.0, min(left, _LOOKING)))
            if said is not None:
                message: dict[str, Any] = dict(said.get("message") or {})
                self.over = message.get("type") == "gone"
                return message
            if self._epics.ended():
                # The session ended with no `gone`: the end of every subscription of it,
                # once what it was still handing over has been told.
                last = self.events.next(_LOOKING)
                if last is not None:
                    return dict(last.get("message") or {})
                self.over = True
            elif ending is not None and time.monotonic() >= ending:
                break
        return None

    def __iter__(self) -> Iterator[dict[str, Any]]:
        """Each message of the host from here on, until `gone`, or the session's end.

        A message is one of Section 4.9 of daemon.md, told apart by its `type`: `welcome`,
        the history records, the snapshots, `live`, and `gone`, after which nothing follows.
        """
        while (message := self.next()) is not None:
            yield message

    def close(self) -> None:
        """Lets this frontend go and stops hearing it; the epic goes on."""
        from hmz.runtime import Refused

        self.over = True
        try:
            self.detach(wait=_LEAVING)
        except (Refused, TimeoutError, OSError):
            # Gone already: the host let go of it first, or the session has ended.
            pass
        finally:
            self.events.close()

    def __enter__(self) -> Self:
        """Attached for as long as the block runs."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        why: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Lets go, however the block ended."""
        self.close()


class Epics(Family):
    """An epic of a host, as one of its frontends: started, steered, heard."""

    METHODS: ClassVar = (
        "epic.attach",
        "epic.start",
        "epic.say",
        "epic.answer",
        "epic.face",
        "epic.stop",
        "epic.force",
        "epic.afk",
        "epic.claim",
        "epic.release",
        "epic.board",
        "epic.aside",
        "epic.unaside",
        "epic.status",
        "epic.detach",
        "epic.quit",
    )

    def attach(
        self,
        workspace: str | None = None,
        *,
        slot: str | None = None,
        replay: bool | None = None,
        since: Mapping[str, Any] | None = None,
        figures: bool | None = None,
        scratch: bool | None = None,
        wait: float | None = None,
    ) -> Attached:
        """Attaches to a host as one frontend, starting the host where the slot has none.

        Args:
          workspace: The workspace, an absolute path of the daemon's machine.
          slot: None or "" for the workspace's own host, `exec:<hex>` for an exec slot's,
            `exec:` alone for a new exec slot.
          replay: False to be told no history record kept, only what happens from here on.
          since: `{"epoch": ..., "seq": ...}`, to be told only the records after that one.
          figures: Whether to be told `figures` too: what the epic has done and spent.
          scratch: True to attach in a new folderless workspace, in place of `workspace`.
          wait: How many seconds an answer is waited for.

        Returns:
          The frontend: the calls of its subscription, and what the host tells it.

        Raises:
          hmz.sdk.Refused: For a workspace that is no directory, and with code 409 for an
            exec slot whose epic has ended.
          RuntimeError: If the client was given a listener of its own.
        """
        from . import _hub  # pyright: ignore[reportPrivateUsage]

        # Before the call, so that what the host says while it is answered is kept.
        _hub(self._client)
        said = self._call(
            "epic.attach",
            workspace=workspace,
            slot=slot,
            replay=replay,
            since=None if since is None else dict(since),
            figures=figures,
            scratch=scratch,
            wait=wait,
        )
        return Attached(self, said, self._heard("epic.event", str(said["sub"])))

    def ended(self) -> bool:
        """Whether the client's session has ended, and with it every subscription of it."""
        return bool(self._client.wait(0))

    def of(self, sub: str) -> Frontend:
        """The calls of an epic subscription opened by other means, which hears it itself."""
        return Frontend(self, sub)
