"""What a run has cost, read from the logs the agents keep for themselves.

A backend says what a turn cost when the turn ends, and a turn is minutes long -- so a number
taken from that alone stands still for most of a run, and moves in one jump at the end of it.
The CLIs write their own usage down as they go, a row per request to the model, and this reads
it there instead: the same tokens, as they are spent rather than once they are done being spent.

Reading is not being told. What is read is what the session has spent all told, so it is
reported as a total rather than as an addition, and a log read twice cannot count a token
twice -- which is also what lets the backends' own reports stand beside it: the two are
counting the same tokens, and whichever has seen more is what has been spent.
"""

from __future__ import annotations

import json
import threading
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from hmz.coganchor import backends

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .monitor import Monitor

__all__ = ["Seen", "Tally", "reported"]

#: The backends whose name for a request is unique across every log, so that a row naming one
#: already counted is that request again wherever it is written. Claude's ids come from the
#: API, and a session it has resumed or forked writes the messages it carried over again under
#: the new name -- which a run reads too, the backend having called the session both. Any other
#: backend's name for a request is only the thread's total so far, which says a row is the one
#: before it said again and nothing more: two threads, or one thread after it has been cut
#: back, can come to the same total over different requests.
_EVERYWHERE = frozenset({"claude"})

#: Past this, a time a log wrote down as a number is in milliseconds rather than seconds:
#: a hundred billion seconds is three thousand years off, and as many milliseconds 1973.
_MILLISECONDS = 1e11

#: How often the logs are looked at. Often enough that a turn's spending shows while the turn
#: is still running, and cheap because only what has been appended since is ever read.
_EVERY = 1.0


#: What each backend's log calls each kind of token. A kind is named the same thing wherever
#: it is counted, so that one flow reading two backends reads one word for one thing -- and
#: so that the prices, which are per kind, can be put against any of them. Codex's rollout is
#: the odd one out: its `input_tokens` has the cached reads inside it, so the read is taken
#: back out rather than paid for twice.
_KINDS: dict[str, tuple[tuple[str, str], ...]] = {
    "claude": (
        ("input", "input_tokens"),
        ("output", "output_tokens"),
        ("cache_read", "cache_read_input_tokens"),
        ("cache_write", "cache_creation_input_tokens"),
    ),
    "dsh": (
        ("input", "inputTokens"),
        ("output", "outputTokens"),
        ("cache_read", "cacheReadTokens"),
        ("cache_write", "cacheWriteTokens"),
    ),
    "codex": (
        ("input", "input_tokens"),
        ("output", "output_tokens"),
        ("cache_read", "cached_input_tokens"),
    ),
    "mcode": (
        ("input", "input"),
        ("output", "output"),
        ("cache_read", "cacheRead"),
        ("cache_write", "cacheWrite"),
    ),
    "litellm": (
        ("input", "input"),
        ("output", "output"),
        ("cache_read", "cache_read"),
        ("cache_write", "cache_write"),
    ),
    "kimi": (
        ("input", "inputOther"),
        ("output", "output"),
        ("cache_read", "inputCacheRead"),
        ("cache_write", "inputCacheCreation"),
    ),
}


def reported(backend: str) -> frozenset[str]:
    """Which kinds of token this backend's own log says, out of the logs read here.

    Beside what its driver reports rather than instead of it: the two are read from two
    places and one may say what the other does not -- Codex's server counts its cached reads
    inside the input and never names them, while the rollout it writes does name them. What
    the interface can show of a backend is what either of them says, and a figure marked as
    short of a kind it can in fact see would be a warning about nothing.

    What this answers is what such a log holds, not that there is one to read. A rollout is
    written wherever the turn ran, so an agent working on another machine leaves none here --
    which is why what is said of an agent is said once one of its logs has actually been
    opened, and not when the run started.

    Args:
      backend: Whose logs.

    Returns:
      The kinds, empty for a backend whose logs are not read here at all -- which is not
      the same as one whose logs say nothing, and reads the same way: nothing claimed.
    """
    return frozenset(kind for kind, _ in _KINDS.get(backend, ()))


def _kinds(backend: str, usage: dict[str, Any]) -> dict[str, float]:
    """One row's usage, under the names every kind is counted by here.

    Args:
      backend: Whose log the row came out of.
      usage: The usage as that backend wrote it.

    Returns:
      Tokens by kind, holding only the kinds this backend actually reported -- a kind that is
      not here is one it does not report, which is not the same as one it reports as nothing.
    """
    broken = {
        kind: float(usage.get(named) or 0)
        for kind, named in _KINDS.get(backend, ())
        if usage.get(named)
    }
    if backend == "codex" and "cache_read" in broken:
        # Codex counts its cached reads inside the input rather than beside it, and a token
        # priced as an input and again as a cached read is a token billed twice. A prompt
        # that was wholly cached leaves no plain input at all, and is written down as having
        # none rather than as having nought of it.
        rest = broken.get("input", 0.0) - broken["cache_read"]
        if rest > 0:
            broken["input"] = rest
        else:
            broken.pop("input", None)
    return broken


def _spent(
    backend: str, row: dict[str, Any]
) -> tuple[str | None, int, dict[str, float], str | None]:
    """What one row of a log says was spent, read as that backend writes it.

    Every one of them is per request rather than a running total, so a session's spending is
    what its rows come to. Claude writes an assistant message with the usage of the request
    that produced it, and names the model on it -- which is how a sub-agent's cheaper model is
    counted as itself. Codex writes a `token_count` event whose `last_token_usage` is the
    request that just came back, the `total_token_usage` beside it being the thread so far.
    Kimi writes a `turn.step.completed` whose usage is that step's. MiniMax Code writes each
    answer with the usage of the request it came back on.

    Two of them say one request more than once. Claude writes a row per block of a message --
    its thinking, its words, each tool it calls -- and puts the whole of the request's usage
    on every one of them, under the one request id. Codex writes a `token_count` again where
    nothing new was spent, with the same `last_token_usage` and the thread's total unmoved.
    Either, added up row by row, is a run counted two or three times over; so each says which
    request a row is of, and a request said again is counted once.

    Args:
      backend: Whose log this row came out of.
      row: The row, as read.

    Returns:
      The model it names, or None to leave that to whoever asked; how many tokens the request
      cost -- zero for a row that is not one of these -- and what those tokens were, kind by
      kind, which is the only reckoning a price can be put against; and which request it is,
      or None where the row does not say and is a request of its own -- a name that holds
      across every log for a backend in `_EVERYWHERE`, and only beside the row before it in
      the same log for any other.
    """
    if backend == "claude":
        message: dict[str, Any] = row.get("message") or {}
        usage: dict[str, Any] = message.get("usage") or {}
        broken = _kinds(backend, usage)
        return (
            str(message.get("model") or "") or None,
            int(sum(broken.values())),
            broken,
            # The message, which every row of it carries and every copy of it keeps, and the
            # request where a row names no message.
            str(message.get("id") or row.get("requestId") or "") or None,
        )
    if backend == "dsh":
        if row.get("type") != "assistant/message":
            return None, 0, {}, None
        data: dict[str, Any] = row.get("data") or {}
        message = data.get("message") or {}
        source: dict[str, Any] = message.get("source") or {}
        usage = data.get("usage") or {}
        broken = _kinds(backend, usage)
        return (
            str(source.get("model") or "") or None,
            int(sum(broken.values())),
            broken,
            None,
        )
    if backend in ("mcode", "litellm"):
        # One record per message of the conversation, and an answer carries what the request
        # it came back on cost, under pi's names -- the cache beside the input, not inside it
        # -- and the provider and model that answered, which is what it is counted against.
        # litellm's conversations are written by humanize in the same shape, its model
        # already carrying the provider in front.
        said: dict[str, Any] = row.get("message") or {}
        if said.get("role") != "assistant":
            return None, 0, {}, None
        broken = _kinds(backend, said.get("usage") or {})
        answering = f"{said.get('provider') or ''}/{said.get('model') or ''}".strip("/")
        return answering or None, int(sum(broken.values())), broken, None
    envelope: dict[str, Any] = row.get("envelope") or {}
    payload: dict[str, Any] = row.get("payload") or envelope.get("payload") or {}
    if backend == "codex":
        info: dict[str, Any] = payload.get("info") or {}
        counted: dict[str, Any] = info.get("last_token_usage") or {}
        # The thread so far, which is what names the request: it rises with every one that
        # comes back, and a row that says it again unmoved is the last request said again.
        thread: object = info.get("total_token_usage")
        # The total is Codex's own rather than what the kinds add up to: a rollout row naming
        # only the total still says what that request cost, and that is what is counted.
        return (
            None,
            int(counted.get("total_tokens") or 0),
            _kinds(backend, counted),
            json.dumps(thread, sort_keys=True) if thread else None,
        )
    spent: dict[str, Any] = payload.get("usage") or {}
    broken = _kinds("kimi", spent)
    return None, int(sum(broken.values())), broken, None


def _moment(said: object) -> float | None:
    """A time a log wrote down, in seconds since the epoch, however that log spells it.

    Args:
      said: What the row says: an ISO 8601 string, or a count of milliseconds -- or of
        seconds, for a count too small to be milliseconds of any year a log was written in.

    Returns:
      The moment, or None for a row that says none or says it in a way not read here. A
      time that names no zone is read as UTC, which is what every one of these logs writes.
    """
    try:
        if isinstance(said, bool):
            return None
        if isinstance(said, int | float):
            return said / 1000 if said > _MILLISECONDS else float(said)
        if isinstance(said, str) and said:
            moment = datetime.fromisoformat(said)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=UTC)
            return moment.timestamp()
    except (ValueError, OverflowError, OSError):
        # A time nobody could have meant: the row is counted as one nobody can place, and
        # the thread reading the logs goes on reading them.
        return None
    return None


def _written(backend: str, row: dict[str, Any]) -> float | None:
    """When one row of a log says the request in it came back, as that backend writes it.

    What tells a row of this run from a row of the conversation it was picked up from. A
    session carried on from one an earlier run held has that one's rows in its log, and a
    fork may write the conversation it was cut from out again -- Claude and pi each copy
    every row as it was, its time included -- and those are tokens somebody else spent.

    Args:
      backend: Whose log the row came out of.
      row: The row, as read.

    Returns:
      The moment, or None where the row does not say -- which is counted, a row nobody can
      place being more likely this run's than not.
    """
    if backend == "dsh":
        return _moment(row.get("time"))
    if backend in ("mcode", "litellm"):
        said: dict[str, Any] = row.get("message") or {}
        return _moment(said.get("timestamp") or row.get("timestamp"))
    envelope: dict[str, Any] = row.get("envelope") or {}
    return _moment(row.get("timestamp") or envelope.get("timestamp"))


@dataclass
class Seen:
    """One session of a run, as what is said about it says it: whose it is and its logs.

    Read off the records of the run rather than off the agent behind it, which a run held
    somewhere else does not hand over. What the backend calls the session is only known once
    a turn of it has said so, and a backend may call one session by more than one name, so
    the names are gathered as the records bring them.

    Attributes:
      id: The role it was opened for, which is what its spending is reported under.
      backend: The CLI that runs it, which is whose logs are read and how.
      model: What it runs at, for a row of a log that does not say for itself.
      counts: The kinds of token its backend reports, whether or not it has spent any.
      idents: What the backend has called it so far, each a log to read. Replaced rather
        than added to, since the logs are read on a thread of their own.
      kept: The directory its logs are under, laid out as its CLI lays out its home, or ""
        for the CLI's own home.
      since: When the run opened it, in seconds since the epoch. A row its log wrote down
        before then is not this run's spending: a conversation carried on from an earlier
        run, or cut from another one, comes with that one's rows.
    """

    id: str
    backend: str
    model: str
    counts: frozenset[str] = frozenset()
    idents: frozenset[str] = frozenset()
    kept: str = ""
    since: float = 0.0


@dataclass
class _Reading:
    """One log being read: how far into it we are, and what it has come to so far.

    Kept by model and then by kind, a bill needing the kinds and a sub-agent on a cheaper
    model being its own line. The kind called `` is what a row counted without saying what
    kind of token it was, which is the one part of a total that cannot be priced.
    """

    at: int = 0
    spent: dict[str, Counter[str]] = field(default_factory=dict[str, Counter[str]])
    #: What the last row that named its request named, for a backend whose name for one says
    #: only that a row is the one before it said again.
    last: str | None = None


class Tally:
    """The logs of the sessions a flow has open, read as the agents write them."""

    def __init__(self, sessions: Sequence[Seen], monitor: Monitor) -> None:
        """Initializes a tally that has read nothing yet.

        Args:
          sessions: The sessions of the flow, whose logs are the ones to read.
          monitor: What to tell, as the total each model has cost.
        """
        self._sessions = list(sessions)
        self._monitor = monitor
        self._read: dict[Path, _Reading] = {}
        #: What each request has been counted as so far, by kind and by the backend that
        #: named it, for a backend whose names hold across every log: a request said again
        #: adds only what it says beyond what was already counted of it.
        self._requests: dict[tuple[str, str], Counter[str]] = {}
        #: Which roles this has actually opened a log of, so that what the monitor is told a
        #: backend reports is what the interface can in fact see. A rollout written on another
        #: machine, or in a container, is one nothing here reads -- and a kind claimed off a
        #: log nobody read would be a nought drawn as a fact.
        self._reading: set[str] = set()
        self._stop = threading.Event()

    def add(self, session: Seen) -> None:
        """Reads the logs of one more session, which a run opens one at a time.

        Args:
          session: The session the run has just opened.
        """
        self._sessions.append(session)

    def watch(self) -> None:
        """Reads the logs for as long as the flow runs, on a thread of its own.

        Its own, because this reads files: a log a turn has just written a tool's whole
        output to is not something to parse on the thread drawing the screen.
        """

        def reading() -> None:
            while not self._stop.wait(_EVERY):
                self.read()
            self.read()  # once more, for what the last turn wrote on its way out

        threading.Thread(target=reading, daemon=True).start()

    def stops(self) -> None:
        """Stops reading, once the run this was watching is over."""
        self._stop.set()

    def read(self) -> None:
        """Reads whatever has been appended since the last read, and says what it comes to.

        Every failure here is somebody else's: a log that is not there yet, one this has no
        business reading, a row half written. What a run costs is worth nothing at the price
        of the run, so anything that goes wrong is left for the next read to find gone.
        """
        for seen in list(self._sessions):
            profile = backends.named(seen.backend)
            if profile is None:
                continue
            # Where this session's logs are, which is the run's own directory for them rather
            # than the CLI's home wherever its turns keep them there.
            home = Path(seen.kept) if seen.kept else profile.directory()
            # Every name the backend has given this session, which it does as the turn starts
            # rather than when the turn lands -- and a session let go of keeps its names, its
            # last rows being still worth reading.
            opened = False
            for ident in sorted(seen.idents):
                for pattern in profile.logged(ident):
                    for path in sorted(home.glob(pattern)):
                        opened |= self._take(path, profile.name, seen.model, seen.since)
            if opened and seen.id not in self._reading:
                # Said once a log has been read rather than when the run started: what this
                # reads is beside what the driver says, and only a log that is actually being
                # read is a kind the interface can show.
                self._reading.add(seen.id)
                self._monitor.reporting(seen.id, seen.counts | reported(profile.name))
        totals: dict[str, Counter[str]] = {}
        for reading in self._read.values():
            for model, broken in reading.spent.items():
                totals.setdefault(model, Counter()).update(broken)
        for model, broken in totals.items():
            # The kind with no name goes along with the rest: it is what a row counted
            # without saying what it went on, and leaving it out here would price the whole
            # of a total against the part of it somebody did break down.
            kinds = {kind: float(count) for kind, count in broken.items()}
            self._monitor.counted(
                "read", model, sum(broken.values()), kinds=kinds or None
            )

    def _take(self, path: Path, backend: str, model: str, since: float) -> bool:
        """Reads one log on from wherever this last left it.

        Args:
          path: The log.
          backend: Whose it is, which is how its rows are read.
          model: What to count a row against when the row does not say for itself.
          since: When the run opened the session the log is of, before which a row is
            somebody else's spending.

        Returns:
          Whether the log was there to be read, which is what says this backend's own
          reckoning is one the interface can show.
        """
        reading = self._read.setdefault(path, _Reading())
        try:
            with path.open("rb") as stream:
                stream.seek(reading.at)
                written = stream.read()
        except OSError:
            return False  # not there yet, or not ours to read
        # To the last full line: a row being written is a row to read next time round.
        written = written[: written.rfind(b"\n") + 1]
        reading.at += len(written)
        for line in written.splitlines():
            try:
                loaded: object = json.loads(line)
            except ValueError:
                continue
            if not isinstance(loaded, dict):
                continue
            row = cast("dict[str, Any]", loaded)
            named, tokens, broken, request = _spent(backend, row)
            if tokens <= 0:
                continue
            counted = Counter({kind: int(count) for kind, count in broken.items()})
            # Whatever the kinds did not account for still cost something, and is put under
            # no kind at all rather than guessed at as one.
            if (rest := tokens - int(sum(broken.values()))) > 0:
                counted[""] += rest
            if request is not None and backend in _EVERYWHERE:
                # A request said again counts for the most any row of it has said, kind by
                # kind, and not for every row it was said on.
                before = self._requests.setdefault((backend, request), Counter[str]())
                grown = counted - before
                before |= counted
                counted = grown
            elif request is not None:
                if request == reading.last:
                    continue  # the row before said again
                reading.last = request
            # After the request is noted rather than before: a row of an earlier run is still
            # the one a row of this run may be saying again.
            if (when := _written(backend, row)) is not None and when < since:
                continue  # an earlier run's, or the conversation this one was cut from
            reading.spent.setdefault(named or model, Counter()).update(counted)
        return True
