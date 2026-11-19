"""`hmz chat`: one turn of a chat, said from a command line, with nobody at a prompt.

    hmz chat -a claude/MODEL:high "what does this repository do?"
    hmz chat --resume 20261117T100000-ab12cd "and how is it tested?"
    hmz chat --worktree -a claude/MODEL:high "try the other parser"
    hmz chat --list
    hmz chat --rename 20261117T100000-ab12cd "the parser"
    hmz chat --delete 20261117T100000-ab12cd --yes

A chat is not a flow and not an epic (Section 8 of core.md): it has one assistant, one
conversation and no params or budget, and it is held by this machine's daemon -- on a chat slot
of its own, which `chat.start` makes. This starts it there, follows it as one more frontend
while its first turn is taken, and then says the empty next message that ends a chat, since
nobody is at a prompt to say another (Section 8.4.8 of core.md). The turn is drawn as `hmz
exec` draws one, by the same :class:`hmz.cli.output.Shown`, so that a script reading the
answer off standard output reads it the same way from either.

A signal leaves the chat to its host rather than stopping its turn, and one left between turns
folds away on its own, to be carried on with `--resume`.

And the chats written down, by the id each is listed by: `--list` says them, and `--rename`,
`--fork`, `--archive`, `--unarchive` and `--delete` are what `chat.*` does to one (Section 15.4
of cli.md), each asked of the daemon and none read off a file here.
"""

from __future__ import annotations

import contextlib
import secrets
import signal
import sys
import threading
from typing import TYPE_CHECKING, Any, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Generator

    from hmz.sdk import Hmz
    from hmz.sdk.client import Client

    from .output import Out, Shown

__all__ = ["chat"]

#: How long a call that is not the start is given to be answered.
_ANSWERING = 30.0

#: How often the wait for the turn looks up, so that a signal is taken without delay.
_LOOKING = 0.5

#: The prefix of everything this says on standard error that is not the turn.
_PROG = "hmz chat"

#: What is done to a chat written down, by the option that names it, and the method doing it.
_DOES = {
    "rename": "chat.rename",
    "fork": "chat.fork",
    "archive": "chat.archive",
    "unarchive": "chat.unarchive",
    "delete": "chat.delete",
}

#: How much of a chat's title a listing shows, on its one line.
_TITLE = 60


class _Line(NamedTuple):
    """An `hmz chat` line, read.

    Attributes:
      agent: The assistant, as `-a` spells an agent after `<role>=`, or "" for none given.
      resume: The chat to carry on, by its id, or "" for a new chat.
      worktree: Whether a new chat's assistant works in a new git worktree of this directory.
      message: What to say, or the title `--rename` gives.
      does: `list`, or what is done to a chat written down (:data:`_DOES`), or "" for a turn.
      chat: The chat that is done to, by its id.
      archived: Whether `--list` says the archived chats.
      yes: Whether `--delete` goes without asking.
    """

    agent: str
    resume: str
    worktree: bool
    message: str
    does: str = ""
    chat: str = ""
    archived: bool = False
    yes: bool = False


class _Left(BaseException):
    """A signal, taken while the chat is followed: leave it to its host, and exit as it says."""

    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


def chat(argv: list[str]) -> int:
    """Takes one turn of a chat in this directory, and prints the answer.

    Or lists the chats of this directory, or does one thing to a chat written down.

    Args:
      argv: What followed the command name.

    Returns:
      Zero once the turn is done; one where it failed or the daemon could not be reached.

    Raises:
      SystemExit: Two for a line or a chat refused before it started, and 128 plus the
        signal's number for one that ended it.
    """
    try:
        return _chats(argv)
    except KeyboardInterrupt:
        # Before the handlers below were put up, or after they were taken down: nothing of
        # the chat is held here to leave, and it exits as the interrupt would have had it.
        raise SystemExit(128 + signal.SIGINT) from None


def _read(argv: list[str]) -> _Line:
    """Reads an `hmz chat` line (Section 15.1 of cli.md).

    Raises:
      SystemExit: For a line argparse does not accept, or an empty message.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog=_PROG,
        description="Say one message to an agent in this directory, and print its answer.",
    )
    parser.add_argument(
        "-a",
        "--agent",
        default="",
        metavar="SPEC",
        help="the agent to talk to: CLI[@PROVIDER]/MODEL[:EFFORT]; the one this directory "
        "remembers when not given",
    )
    parser.add_argument(
        "--resume",
        default="",
        metavar="CHAT",
        help="carry on the chat of this id here",
    )
    parser.add_argument(
        "--worktree",
        action="store_true",
        help="start the chat in a new git worktree of this directory",
    )
    doing = parser.add_mutually_exclusive_group()
    doing.add_argument(
        "--list",
        action="store_true",
        help="list the chats of this directory, newest first, each by its id",
    )
    doing.add_argument(
        "--rename",
        metavar="CHAT",
        help="give the chat of this id the title that follows",
    )
    doing.add_argument(
        "--fork", metavar="CHAT", help="make a new chat that goes on from this one"
    )
    doing.add_argument(
        "--archive", metavar="CHAT", help="take the chat of this id out of the lists"
    )
    doing.add_argument(
        "--unarchive",
        metavar="CHAT",
        help="put an archived chat back among the others",
    )
    doing.add_argument(
        "--delete", metavar="CHAT", help="delete the chat of this id, for good"
    )
    parser.add_argument(
        "--archived", action="store_true", help="with --list, the archived chats alone"
    )
    parser.add_argument(
        "--yes", action="store_true", help="with --delete, delete without asking"
    )
    parser.add_argument(
        "message",
        nargs="?",
        help="what to say, after -- if it starts with a dash; with --rename, the title",
    )
    args = parser.parse_args(argv)
    does = (
        "list" if args.list else next((one for one in _DOES if getattr(args, one)), "")
    )
    if args.archived and does != "list":
        parser.error("--archived goes with --list")
    if args.yes and does != "delete":
        parser.error("--yes goes with --delete")
    if does:
        if args.agent or args.resume or args.worktree:
            parser.error(
                f"--{does} says nothing to a chat: -a, --resume and --worktree do"
            )
        if does == "rename" and not (args.message or "").strip():
            parser.error("--rename takes the chat and then its title")
        if does != "rename" and args.message is not None:
            parser.error(f"--{does} takes no message")
    elif args.message is None:
        parser.error("the following arguments are required: message")
    elif not args.message:
        parser.error("the message is empty; a chat starts with something said")
    if args.worktree and args.resume:
        parser.error("--worktree starts a chat; one carried on works where it worked")
    return _Line(
        agent=args.agent,
        resume=args.resume,
        worktree=args.worktree,
        message=args.message or "",
        does=does,
        chat="" if does in ("", "list") else getattr(args, does),
        archived=args.archived,
        yes=args.yes,
    )


def _refuse(why: str) -> SystemExit:
    """Says why a chat was refused before it started, and answers the exit that follows."""
    print(f"{_PROG}: error: {why}", file=sys.stderr)
    return SystemExit(2)


def _kept(hmz: Hmz, message: str) -> str:
    """Why a message is not one `hmz chat` can say, or "" for one it can (Section 15.1.6).

    A `/` name hmz keeps is a frontend's to serve and a `$` that names a flow starts one, and
    neither has a frontend here to serve it. The harness's catalogue is not known before its
    conversation opens, so a `$` name is read as a flow wherever one answers to it.

    Args:
      hmz: The workspace, whose flows a `$` name is looked up among.
      message: What was to be said.
    """
    from hmz.runtime.chatting import resolve

    said = message.strip()
    sigil, name = said[:1], said[1:].partition(" ")[0]
    flows = {name} if sigil == "$" and name and hmz.flows.find(name) else set[str]()
    read = resolve(said, catalog=(), flows=flows, prefer="flow")
    if read.kind == "reserved":
        return f"{sigil}{name} is kept for hmz's interfaces, which serve it in a chat"
    if read.kind == "flow":
        return f"{sigil}{name} names a flow; run it with hmz exec -f {name}"
    return ""


def _chats(argv: list[str]) -> int:
    """What :func:`chat` does, before an interrupt anywhere in it is made an exit status."""
    from hmz.runtime import Refused
    from hmz.sdk import Hmz

    line = _read(argv)
    hmz = Hmz()
    # As `hmz exec` does: only where it has been answered yes.
    hmz.reports()
    if line.does:
        return _manages(hmz, line)
    agent = line.agent
    if not agent and not line.resume:
        from hmz.runtime.kept import written

        remembered = hmz.settings.chat_agent
        if remembered is None:
            raise _refuse("no chat agent is remembered here; give one with -a")
        agent = written(remembered)
    if why := _kept(hmz, line.message):
        raise _refuse(why)

    from hmz.daemon import where
    from hmz.sdk.client import Client

    from .output import Out, Shown, unreached

    asked: dict[str, Any] = {
        "workspace": where.workspace(hmz.workspace),
        "slot": "chat:",
        "task": line.message,
        # A line on a command line is not a choice made for the next one.
        "remember": False,
    }
    if agent:
        # Left out, rather than null, for a chat carried on with its own agent.
        asked["agent"] = agent
    if line.resume:
        asked["resume"] = line.resume
    if line.worktree:
        asked["worktree"] = True
    try:
        client = Client.local(kind="cli")
    except OSError as error:
        print(unreached(error), file=sys.stderr)
        return 1
    with client, Out() as out, Shown(out) as shown, _leaving() as left:
        follower = _Follower(out, shown)
        client.heard(follower.heard)
        try:
            started = client.call("chat.start", asked, idem=secrets.token_urlsafe(12))
        except Refused as error:
            if error.code == _GONE:
                print(unreached(OSError(str(error))), file=sys.stderr)
                return 1
            raise _refuse(str(error)) from error
        # The id it is carried on by, and listed by: on standard error, as the turn is.
        out.aside(f"{_PROG}: chat {started['chat']}")
        at = {"workspace": asked["workspace"], "slot": str(started["slot"])}
        try:
            follower.follows(client, at)
        except (Refused, TimeoutError) as error:
            follower.ended = ("failed", f"{_PROG}: {error}")
        if follower.ended is None:
            # The turn is done and the chat between turns: nobody is here to say the next
            # message, so the next message is the empty one that ends it. The turn is what
            # was asked for, so a chat that folded away meanwhile is no failure.
            with contextlib.suppress(Refused, TimeoutError):
                client.call(
                    "chat.say",
                    {**at, "text": ""},
                    idem=secrets.token_urlsafe(12),
                    seconds=_ANSWERING,
                )
    if left:
        raise SystemExit(128 + left[0])
    how, why = follower.ended or ("", "")
    if how in ("failed", "crashed"):
        print(why, file=sys.stderr)
        return 1
    if follower.failed:
        # A later turn that failed is said in the conversation and the chat goes on
        # (Section 8.4.10 of core.md), but it is still the one turn this was asked for.
        print(follower.failed, file=sys.stderr)
        return 1
    return 0


def _manages(hmz: Hmz, line: _Line) -> int:
    """Lists the chats of this directory, or does one thing to a chat written down.

    Each asked of this machine's daemon (Section 4.25 of daemon.md), which is started where
    none runs.

    Args:
      hmz: The workspace.
      line: The line, read.

    Returns:
      Zero once it is done; one where the daemon could not be reached, or a chat was not
      deleted for want of a yes.

    Raises:
      SystemExit: Two for what the daemon refused.
    """
    from hmz.daemon import where
    from hmz.runtime import Refused
    from hmz.sdk.client import Client

    from .output import unreached

    try:
        client = Client.local(kind="cli")
    except OSError as error:
        print(unreached(error), file=sys.stderr)
        return 1
    with client:

        def asks(method: str, **params: Any) -> dict[str, Any]:
            # A reading writes nothing, and carries no `idem`.
            reads = method in ("chat.list", "chat.get")
            idem = None if reads else secrets.token_urlsafe(12)
            return dict(
                client.call(method, params, idem=idem, seconds=_ANSWERING) or {}
            )

        try:
            if line.does == "list":
                chats: list[dict[str, Any]] = []
                while True:
                    said = asks(
                        "chat.list",
                        workspace=where.workspace(hmz.workspace),
                        archived=line.archived,
                        offset=len(chats),
                        limit=200,
                    )
                    page: list[dict[str, Any]] = said.get("chats") or []
                    chats += page
                    if not page or len(chats) >= int(said.get("total") or 0):
                        break
                for one in chats:
                    print(_row(one))
            elif line.does == "delete":
                if not line.yes and not _sure(asks("chat.get", chat=line.chat)):
                    print(f"{_PROG}: chat {line.chat} was not deleted", file=sys.stderr)
                    return 1
                asks("chat.delete", chat=line.chat)
            elif line.does == "fork":
                print(asks("chat.fork", chat=line.chat)["chat"])
            else:
                title = {"title": line.message} if line.does == "rename" else {}
                print(_row(asks(_DOES[line.does], chat=line.chat, **title)))
        except Refused as error:
            if error.code == _GONE:
                print(unreached(OSError(str(error))), file=sys.stderr)
                return 1
            raise _refuse(str(error)) from error
        except TimeoutError as error:
            print(f"{_PROG}: {error}", file=sys.stderr)
            return 1
    return 0


def _row(chat: dict[str, Any]) -> str:
    """One chat on one line: its id, how it stands and its title (Section 15.4 of cli.md)."""
    title = " ".join(str(chat.get("title") or "").split())
    title = title if len(title) <= _TITLE else f"{title[: _TITLE - 1]}…"
    return f"{chat.get('id')}  {chat.get('state')}  {title}"


def _sure(chat: dict[str, Any]) -> bool:
    """Asks on the terminal whether one chat is to be deleted for good, and answers.

    Never asked of anything but somebody at a terminal: a line read off a pipe is not a yes.

    Args:
      chat: The chat, as `chat.get` answers it.

    Returns:
      Whether `y` or `yes` was typed.
    """
    if not sys.stdin.isatty():
        print(f"{_PROG}: nobody is at a terminal to ask; say --yes", file=sys.stderr)
        return False
    print(
        f"{_PROG}: delete {_row(chat)}\nfor good? It cannot be brought back. [y/N] ",
        end="",
        file=sys.stderr,
        flush=True,
    )
    return sys.stdin.readline().strip().lower() in ("y", "yes")


#: The code a call is refused with where the daemon's session has gone.
_GONE = 503

#: How a host's `gone` begins for a frontend that fell behind, which attaches again.
_BEHIND = "too far behind"


class _Follower:
    """The chat as its subscription tells it, drawn, until its turn is done or it ends."""

    def __init__(self, out: Out, shown: Shown) -> None:
        self._out = out
        self._shown = shown
        self._wake = threading.Event()
        self._lock = threading.Lock()
        # Whether the line has been seen taken -- a turn going or answering, or the chat
        # asking for its next line: a `turn` of `done` before any is a chat whose first turn
        # has not opened yet, not one whose turn is done. Kept apart from the latest `turn`,
        # since a replay may say the snapshot first.
        self._going = False
        # Whether a turn has said how it went, which is then not said again as the chat
        # asks for its next line.
        self._answered = False
        # What a turn answered, which the chat says back as it asks for its next line.
        self._answer: str | None = None
        self._turn = ""
        # Where the subscription has got to, to attach again from where it was left.
        self._since: dict[str, Any] | None = None
        self._behind = False
        self.done = False
        self.failed = ""
        self.ended: tuple[str, str] | None = None

    def follows(self, client: Client, at: dict[str, Any]) -> None:
        """Attaches to the chat's slot and waits for its turn to be done, or for it to end.

        Attached again where the host let go of this for falling behind; a session that ends
        with no word from the host is the daemon gone, which ends the wait.

        Args:
          client: The session with the daemon, which this listens to.
          at: The chat's workspace and slot.

        Raises:
          Refused: If attaching was refused.
          TimeoutError: If attaching was not answered.
        """
        while True:
            with self._lock:
                self._behind = False
                since = None if self._since is None else dict(self._since)
            client.call("epic.attach", {**at, "since": since}, seconds=_ANSWERING)
            while not self._wake.wait(_LOOKING):
                if client.wait(0):
                    self.ended = ("failed", f"{_PROG}: the daemon went away")
                    return
            with self._lock:
                if not self._behind:
                    return
                self._wake.clear()

    def heard(self, method: str, params: dict[str, Any]) -> None:
        """Takes one message of the chat's subscription, from the client's thread."""
        said: Any = params.get("message")
        if method != "epic.event" or not isinstance(said, dict):
            return
        message: dict[str, Any] = said  # pyright: ignore[reportUnknownVariableType]
        kind, seq = message.get("type"), message.get("seq")
        with self._lock:
            if kind == "welcome":
                self._since = {"epoch": message.get("epoch"), "seq": 0}
            elif isinstance(seq, int) and self._since is not None:
                self._since["seq"] = seq
        if kind == "event":
            self._shown.heard(
                str(message.get("agent")), message.get("session") or None, message
            )
            if message.get("kind") == "result":
                self._going = self._answered = True
                self._answer = str(message.get("text") or "").strip()
                self._settles()
            elif message.get("kind") == "failed":
                self._answered = True
                self.failed = str(message.get("text") or "")
        elif kind == "opened":
            from hmz.sdk.running import Opened

            self._shown.opened(
                str(message.get("role") or ""),
                Opened(
                    key=str(message.get("key") or ""),
                    role=str(message.get("role") or ""),
                    agent=str(message.get("agent") or ""),
                    cli=str(message.get("cli") or ""),
                    model=str(message.get("model") or ""),
                    person=bool(message.get("person")),
                    env=message.get("env"),
                    harness=str(message.get("harness") or ""),
                ),
            )
        elif kind == "notice":
            self._out.aside(f"{_PROG}: {message.get('text') or ''}")
        elif kind == "printed":
            self._out.printed(str(message.get("text") or ""))
        elif kind == "shell":
            self._shell(message)
        elif kind == "asked" and message.get("mode") == "listen":
            # The chat asks for its next line, so the one it was said is taken, by a turn
            # or by none: a `!` command it ran, or a line it refused, which it says why of
            # here alone (Section 8.9.1 and Section 8.9.6 of core.md). Ahead of what a turn
            # answered it says what only the conversation says: that this is a new one, the
            # one carried on being gone (Section 8.7.6 of core.md).
            said = str(message.get("text") or "").strip()
            if self._answer is not None:
                said = said.removesuffix(self._answer).strip()
            elif self._answered:
                said = ""
            if said:
                self._out.aside(f"{_PROG}: {said}")
            self._going = True
            self._settles()
        elif kind == "run":
            self._turn = str(message.get("turn") or "")
            if self._turn == "running":
                self._going = True
            self._settles()
        elif kind == "ended":
            self.ended = (str(message.get("how") or ""), str(message.get("why") or ""))
            self._wake.set()
        elif kind == "gone":
            self._goes(str(message.get("why") or ""))

    def _shell(self, record: dict[str, Any]) -> None:
        """Shows a `!` command run for the chat as a shell would: its output on stdout.

        The command, what it wrote as errors and how it exited where that was not well are
        drawn on stderr, where the turn is.
        """
        self._out.line(("! ", "yellow"), (str(record.get("command") or ""), ""))
        if out := str(record.get("out") or "").rstrip("\n"):
            self._out.answer(out)
        if err := str(record.get("err") or "").rstrip("\n"):
            self._out.line((err, "red"))
        status = record.get("status")
        if isinstance(status, int) and status:
            self._out.line((f"exit {status}", "dim"))

    def _goes(self, why: str) -> None:
        """Takes the host letting go of this: to attach again, or as the end of the wait."""
        with self._lock:
            if why.startswith(_BEHIND) and not self.done and self.ended is None:
                self._behind = True
            elif self.ended is None and not self.done:
                self.ended = ("failed", f"{_PROG}: {why or 'the host went away'}")
        self._wake.set()

    def _settles(self) -> None:
        """Wakes the wait where the turn has been taken and the chat is between turns."""
        if self._turn == "done" and self._going:
            self.done = True
            self._wake.set()


@contextlib.contextmanager
def _leaving() -> Generator[list[int]]:
    """Leaves the chat to its host on an interrupt, a terminate or a hangup.

    Raised from the signal's own frame, which is this thread waiting on the turn or a call:
    there is nothing to unwind but this process's session, which closing lets go of, and the
    chat goes on without it (Section 15.3.5 of cli.md).

    Yields:
      Where the signal that ended it is written, once one has.
    """

    def leaves(signum: int, _frame: object) -> None:
        raise _Left(signum)

    was: dict[int, Any] = {}
    for one in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        with contextlib.suppress(ValueError):  # off the main thread, where none reaches
            # A signal somebody chose to have ignored stays so, as it does for `hmz exec`.
            if signal.getsignal(one) != signal.SIG_IGN:
                was[one] = signal.signal(one, leaves)
    left: list[int] = []
    try:
        yield left
    except _Left as signalled:
        left.append(signalled.signum)
    finally:
        for one, before in was.items():
            signal.signal(one, signal.SIG_DFL if before is None else before)
