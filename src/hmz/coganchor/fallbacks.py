"""Where a turn goes when the place taking it cannot take it at all.

A model that has been retired, a CLI that will not start, a region that has gone dark, a rate
limit on the whole of an account rather than one request: none of those is answered by trying
the same place again. What answers it is another place to run -- another CLI, another account,
another model -- and the turn is taken there.

A place is three things and no more: the CLI, the account it runs as, and the model it runs.
`claude@work/claude-opus-5` to `codex@key/gpt-5.6-sol`, which is a step from one to another.
It is not a step between agents. How hard an agent thinks, what it may reach for, which of a
flow's skills it carries and what it is called are what that agent *is*, settled where it was
made, and they come across the step unchanged: what failed was the place, so the place is what
moves.

A place falls back along a chain rather than to one other place: `claude@work/claude-opus-5`
to `codex@key/gpt-5.6-sol` and then to `gemini/gemini-3-pro`, each tried when the one before it
has failed too. The chain is the place's own and is only ever started from it. A turn begun at
a place that is somebody else's fallback but has no chain written against it has nowhere to go,
and a place reached as a stand-in carries on along the chain it was reached by -- never along
one of its own, which would be two chains spliced together that nobody wrote down.

Trying again is written down here too, for the same reason. A turn fails for two kinds of
reason and only one of them is worth another go -- a gateway that answered 503, a socket that
closed mid-stream, a service that said `too many requests` are each the same call away from
working -- and how many goes it gets is a thing about the place rather than about the agent
standing in it. One place says both: how often a turn under it is tried again, and where it
goes once those tries are spent.

What is lost across such a step is the conversation, and nothing here pretends otherwise: no
backend can be handed another backend's session id, so the turn that moves is taken in a new
session at the place it moved to. Which is why the tries come first: they are taken inside
the conversation that was running, and only a turn with no tries left leaves it.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, cast

from hmz import home
from hmz.coganchor import atomic, backends

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

__all__ = [
    "ANSWERS",
    "BASE",
    "CEILING",
    "DEFAULT",
    "POLICIES",
    "THROTTLED",
    "Answer",
    "Falls",
    "Policy",
    "answers",
    "chain",
    "clear",
    "falls",
    "named",
    "points",
    "reads",
    "retrying",
    "spec",
    "tried",
    "waits",
]

#: What the file every step is written down in is called. One file rather than one per step:
#: a chain is read whole every time it is read at all -- a turn that failed asks where it
#: goes, and the answer is the walk rather than the step -- and a directory of one-line files
#: would be a directory to walk to answer it.
_HELD = "fallbacks.json"

#: The first wait, which every policy is written in terms of. A second is short enough that a
#: turn nobody is watching is not held up by it and long enough that a service which has just
#: refused one call is not immediately asked again.
BASE = 1.0

#: The longest any single wait may be, however far the backoff has climbed. A turn is minutes
#: long, and a wait longer than the turn it is waiting for is a run that looks hung.
CEILING = 60.0

#: How far a backoff is worked out before the answer is the ceiling anyway. Doubling a second
#: passes a minute at the seventh, and Fibonacci at the eleventh; anything past this is a
#: number to stop computing rather than one to compute.
_CLIMBED = 64


@dataclass(frozen=True, slots=True)
class Policy:
    """One way of waiting between tries.

    Attributes:
      name: What it is called, which is what a step is written down with.
      about: One line saying what it is and when to reach for it.
    """

    name: str
    about: str


#: Every way a turn may be waited over, in the order they are offered: the plainest first, and
#: the one to reach for when several agents are failing at once marked as such. `none` is here
#: because "try again at once" is a real answer for a transport that dropped a connection.
POLICIES = (
    Policy("none", "try again at once, with no wait at all"),
    Policy("constant", "the same wait every time: 1s, 1s, 1s"),
    Policy("linear", "one second longer each time: 1s, 2s, 3s"),
    Policy("exponential", "twice as long each time: 1s, 2s, 4s, 8s"),
    Policy(
        "exponential-jitter",
        "exponential, each wait anywhere up to it -- for agents failing at once",
    ),
    Policy("fibonacci", "the Fibonacci sequence: 1s, 1s, 2s, 3s, 5s"),
)

#: What a place is retried by where it says nothing, and what a menu starts a new one on:
#: exponential backoff with full jitter is what every one of these services documents, and the
#: jitter is what keeps a flow's agents from retrying in lockstep.
DEFAULT = "exponential-jitter"

#: The least a turn waits after being told there have been too many requests. Half the longest
#: wait there is, which is long enough that a per-minute window has moved on and short enough
#: that a flow does not read as hung -- and long whatever the place's policy says, since the
#: first second of an exponential backoff is a second the service has already refused.
THROTTLED = CEILING / 2

#: How many goes a turn gets at a store another turn had open. Three, because the contention
#: is one process holding a file lock for the length of one write: it is gone by the second
#: try nearly always and by the third all but never not.
_BUSY = 3


@dataclass(frozen=True, slots=True)
class Answer:
    """What a turn does about one kind of failure, which is a different thing for each.

    A place says how many times over a failed turn is taken again and how long to wait between
    them, and that is the right thing for a place to say -- but it is one answer, and what
    stopped the turn is not one question. A rate limit wants a long wait and then another
    place; a credential that was refused wants no wait at all; a model that has been retired
    wants no wait either, the next call naming the same model. Retried the same way, three of
    those are a flow that makes no progress and one is a flow that hammers a service which has
    just told it to stop.

    So the place says the shape and this says what the failure does to it: how few goes it is
    worth, how long the shortest of them waits, and what to tell whoever is watching.

    Attributes:
      fault: The kind, as `hmz.coganchor.backends.FAULTS` names them, and "" for the one nobody
        classified -- whose answer is the one a turn has always had.
      about: What happened, as the clause an event narrating the recovery is built round.
      tries: The fewest goes here, whatever the place says. A place that asked for more gets
        more: this is a floor under a failure that is worth another go and not a ceiling on
        what somebody asked for.
      held: Whether that is also the most, which is none: a failure the same call cannot come
        out of differently is one to walk away from rather than to schedule.
      policy: A wait of its own to put under the place's, or "" to wait only the way the
        place says. Under rather than instead of: a place that asked for a longer backoff
        asked for it, and a row that shortened one would be this file overruling somebody --
        in the one direction that hammers whatever has just failed.
      least: The shortest any of those waits may be, however short both policies made it.
      reopen: Whether whatever was holding the conversation open is let go of before the next
        go. The conversation is the backend's own and is named by an id, so a new transport
        resumes it: what was lost was the socket and not the session.
      fix: What a person does about it, in a few words, for the failures where there is
        something to do. It goes on the event that narrates the recovery and on the turn's own
        failure, so that an account needing attention says so rather than reading as a bug.
    """

    fault: str
    about: str
    tries: int = 0
    held: bool = False
    policy: str = ""
    least: float = 0.0
    reopen: bool = False
    fix: str = ""


#: What every kind of failure gets. One row per kind, and the kind nobody recognised is not
#: among them: a failure this cannot name is a turn tried again exactly as it always was,
#: which is the only answer that cannot be wrong about something it has not understood.
ANSWERS: tuple[Answer, ...] = (
    # Waited out first and then walked away from, in that order: the service has said the
    # account is asking too fast, so the next call under the same account is the same
    # answer -- and the place after it is not rate-limited at all. Said as a limit on how
    # fast and not as a quota: a plain `429` is the service asking for room, and nothing a
    # person has to top up.
    Answer(
        "throttled",
        "is rate-limited",
        tries=1,
        least=THROTTLED,
        fix="the service asks it to slow down, with no quota spent; a wait is what answers it",
    ),
    # Answered as a rate limit is -- a wait, then another account -- because the service
    # gives it the same `429`, and a quota that renews by the hour is one a wait does answer.
    # Said as what it is, though, since the account rather than the moment is what somebody
    # attends to.
    Answer(
        "spent",
        "has spent its quota",
        tries=1,
        least=THROTTLED,
        fix="this account has spent its quota; another one, or a wait, is what answers it",
    ),
    # Not waited out at all. A key that was refused is refused a minute later, and five goes
    # on a schedule is five minutes spent finding that out.
    Answer(
        "refused",
        "was refused the credentials",
        held=True,
        fix="that account needs signing in again",
    ),
    # The model rather than the credential: what an account may name is that account's, and
    # the next place on the chain has a catalogue of its own. Not waited out: the list of what
    # this account runs will not have changed by the next call, and it is the list rather than
    # the moment that is wrong.
    # What a person does about it is said by the turn that failed, which is the only place
    # that knows which id was named and what humanize was last told this account runs.
    Answer(
        "unlisted",
        "was refused that model",
        held=True,
        fix="that model is not this account's to name; ask it what it runs and name one of those",
    ),
    # Not waited out either: every account of this CLI is offered the same catalogue, so the
    # model that is gone is gone at the next call too.
    Answer(
        "retired",
        "has no such model",
        held=True,
        fix="the model is gone or was never this account's; another place is what answers it",
    ),
    # Two turns at one local store, which is nobody's account and nothing to walk to. It
    # clears itself in the time it takes the other turn to finish writing.
    Answer(
        "contended",
        "found its own store busy",
        tries=_BUSY,
        policy="constant",
        fix="two turns of it are sharing one database",
    ),
    # The socket rather than the session. Reopened and resumed, and given whatever wait the
    # place asks for and no more: there is nothing here to wait out, the thing that failed
    # having already gone, and a place that asked for a backoff against a gateway that is
    # down asked for it.
    Answer(
        "dropped",
        "lost the connection",
        tries=1,
        reopen=True,
        fix="",
    ),
    # The process rather than the socket. Reopened too, and given a moment first: a machine
    # that has just killed something for memory has not got it back yet.
    Answer(
        "killed",
        "was killed rather than answered",
        tries=1,
        policy="constant",
        reopen=True,
        fix="the machine it runs on may be out of memory",
    ),
    # Nothing to run, and no account of a CLI that is not here. What answers it is a line in
    # a terminal, or a step to a CLI this machine actually has.
    Answer(
        "missing",
        "is not installed here",
        held=True,
        fix="",
    ),
    # This machine's filesystem, and nobody's account: the copy of another machine's work a
    # harness here works in has a path that cannot be made here. The next go is the same
    # path.
    Answer(
        "unmirrored",
        "could not keep its copy of the work here",
        held=True,
        fix="that path cannot be made here; use a workdir whose path you can create here, "
        "or put self in the affinity of the runtime the work is on",
    ),
    # The run rather than the account: the fence it was started under keeps it off a host,
    # and the same fence keeps the next go off it too. Another place may need no such host,
    # so it is walked away from rather than scheduled.
    Answer(
        "fenced",
        "was kept off a host by this run's fence",
        held=True,
        fix="the run's network fence keeps it off that host, which no sign-in answers; "
        "give the role online of ALL to let it through",
    ),
    # The machine rather than anything a turn named. A CLI that confines its own tool calls
    # asks the kernel for the confinement, and a kernel that has just said no says no to the
    # next go: an unprivileged container is not somewhere bubblewrap works under a different
    # key. What answers it is the machine, the CLI asked for no sandbox, or another place.
    Answer(
        "sandboxed",
        "could not start its sandbox",
        held=True,
        fix="this machine will not let it sandbox itself; run it without one, or somewhere it can",
    ),
)


def answers(fault: str) -> Answer:
    """What to do about one kind of failure.

    Args:
      fault: The kind, as `hmz.coganchor.backends.FAULTS` names them.

    Returns:
      Its row, or the one a failure nobody classified gets: no goes beyond the ones the place
      asked for, the place's own wait, and the place's chain after them -- which is what every
      failed turn got before there was a taxonomy to read one by. So whoever is recovering a
      turn reads a row rather than a row and a special case.
    """
    return next((one for one in ANSWERS if one.fault == fault), Answer(fault, "failed"))


@dataclass(frozen=True, slots=True)
class Falls:
    """One place: how a turn under it is tried again, and where it goes once they are spent.

    Attributes:
      spec: The place, as `CLI[@ACCOUNT]/MODEL` -- three things and no more, because those
        are what a turn can fail for having named. How hard the agent thinks and what it may
        reach for are what that agent is rather than where it runs.
      to: The places that take the turn instead, in the same spelling and in the order they
        are tried -- each when every one before it has failed too -- or none at all for a
        place that falls back nowhere, which is a turn that fails as a turn has always failed.
        Never this place and never one place twice.
      tries: How many times over a failed turn is tried again here before the step is taken.
        Zero is the first try and no more, which is what a turn has always had.
      policy: How long to wait between those tries, as :data:`POLICIES` names them.
      timeout: The longest the trying again may go on for, in seconds, or 0.0 for no limit.
    """

    spec: str
    to: tuple[str, ...] = ()
    tries: int = 0
    policy: str = DEFAULT
    timeout: float = 0.0

    def says(self) -> bool:
        """Whether this says anything at all, which is what keeps it written down.

        A place that falls back nowhere and is tried once is a place nobody has said anything
        about, and a file holding a row of those is a file that grows for nothing.

        Returns:
          True if it names somewhere to go or asks for a turn to be tried again.
        """
        return bool(self.to) or self.tries > 0


def spec(backend: str, model: str, provider: str = "") -> str:
    """One place as a step names it, which is three things and no more.

    Written down once, here, because two places spelling a place is two places to drift: an
    agent asks where it falls back to by this name, and a person writes one down by it.

    Args:
      backend: The CLI, by the name a command line calls it.
      model: The model it runs.
      provider: The account its turns run as, or "" for the one this machine is signed into.

    Returns:
      The spec, with the account in it only where there is one to name.
    """
    return f"{backend}{'@' + provider if provider else ''}/{model}"


def reads(said: str) -> str:
    """One place as it is written down, or "" for one that is not a place at all.

    Read through `hmz.coganchor.backends` for the CLI rather than pattern-matched here, so that a
    name no backend answers to is refused where it is written rather than found by the turn that
    needed it. A model may hold slashes of its own -- Kimi Code's and opencode's are `provider/id`
    -- and a CLI never does, so the first slash is the one that separates them.

    Args:
      said: What was written.

    Returns:
      The spec as this module spells it, or "" where it cannot be read as one.
    """
    backend, slash, model = said.strip().partition("/")
    if not slash:
        return ""
    backend, at, account = backend.partition("@")
    if at and not account.strip():
        return ""
    profile = backends.named(backend.strip())
    model = model.strip()
    if profile is None or not model:
        return ""
    return spec(profile.name, model, account.strip())


def falls() -> list[Falls]:
    """Every place written down, in the order they were written.

    Returns:
      One apiece. Empty where nothing has been written down, where the file has gone, and
      where what is there cannot be read -- a file somebody edited by hand into something
      else is a file to correct rather than the end of every run on this machine.
    """
    at = home() / _HELD
    try:
        held = json.loads(at.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(held, list):
        return []
    rows = [
        cast("dict[str, Any]", one)
        for one in cast("list[object]", held)
        if isinstance(one, dict)
    ]
    # The steps an older humanize wrote, one place to the next, which it walked from one row
    # to the row of the place it named. Read as the chain they came to, so that a file written
    # before chains were lists still reaches every place it reached -- and is written back as
    # one the next time anything is.
    linked = {
        reads(str(one.get("spec") or "")): reads(one["to"])
        for one in rows
        if isinstance(one.get("to"), str)
    }
    found: list[Falls] = []
    seen: set[str] = set()
    for one in rows:
        # Read back through the same reading that wrote them: a file edited by hand holds
        # whatever somebody typed, and a step naming a CLI there is none of is a step that
        # could only fail the turn it was asked about.
        said = reads(str(one.get("spec") or ""))
        if not said or said in seen:
            continue
        step = Falls(
            said,
            _onwards(said, one.get("to"), linked),
            tries=_counted(one.get("tries")),
            policy=str(one.get("policy") or DEFAULT),
            timeout=_seconds(one.get("timeout")),
        )
        if not step.says():
            continue
        seen.add(said)
        found.append(step)
    return found


def tried(said: str) -> Falls:
    """What is written down about one place, which is nothing at all for most of them.

    Args:
      said: The place, as `-a` or a step would name it.

    Returns:
      Its step, or one that falls back nowhere and is tried once -- so that whoever is
      walking a chain reads a step rather than a step and a special case.
    """
    from_ = reads(said) or said.strip()
    return next((one for one in falls() if one.spec == from_), Falls(from_))


def points(said: str, to: Sequence[str]) -> Falls:
    """Says where one place's turns go when it cannot take them, and writes it down.

    Args:
      said: The place that fails, as `CLI[@ACCOUNT]/MODEL`.
      to: The places that take the turn instead, in the order they are tried, or none at all
        to say it falls back nowhere -- which is a turn that fails as a turn has always
        failed. A single string is one place rather than a list of its letters, and an empty
        one is none -- which is how this was called when a place fell back to one other.

    Returns:
      The step as it now stands, whose `to` is empty for one that was taken away.

    Raises:
      ValueError: If any of them cannot be read as a place, if one of the places it falls
        back to is this place, or if one is named twice. A chain that came back to itself
        would be a turn that could never run out of places to go, and one naming a place
        twice is a place tried twice for nothing; each is refused where it is written rather
        than found by the turn that needed it.
    """
    if isinstance(to, str):
        to = [to] if to.strip() else []
    from_ = reads(said)
    if not from_:
        raise ValueError(f"{said!r} is not a place: expected CLI[@ACCOUNT]/MODEL")
    onwards: list[str] = []
    for at in to:
        one = reads(at)
        if not one:
            raise ValueError(f"{at!r} is not a place: expected CLI[@ACCOUNT]/MODEL")
        if one == from_:
            raise ValueError(f"{from_} cannot fall back to itself")
        if one in onwards:
            raise ValueError(
                f"{one} is already one of the places {from_} falls back to"
            )
        onwards.append(one)
    return _keeps(replace(tried(from_), spec=from_, to=tuple(onwards)))


def retrying(said: str, tries: int, policy: str, timeout: float) -> Falls:
    """Says how many times over a failed turn at one place is taken again, and how.

    Written down beside where that place falls back to, both being answers to the one thing
    that happened: the turn did not land. The tries come first -- the same call may yet
    work -- and the step is what is left when they are spent.

    Args:
      said: The place, as `CLI[@ACCOUNT]/MODEL`.
      tries: How many goes beyond the first.
      policy: How long to wait between them, as :data:`POLICIES` names them.
      timeout: The longest the trying again may go on for, in seconds, or 0.0 for no limit.

    Returns:
      The step as it now stands.

    Raises:
      ValueError: If the place cannot be read, the policy is not one there is, or either
        number is one no waiting can be made of -- a negative, or seconds that are infinite
        or not a number. All of them are a line to correct rather than something for the
        turn that needed it to find out about.
    """
    from_ = reads(said)
    if not from_:
        raise ValueError(f"{said!r} is not a place: expected CLI[@ACCOUNT]/MODEL")
    if named(policy) is None:
        raise ValueError(
            f"{policy!r} is not a retry policy: "
            f"{', '.join(one.name for one in POLICIES)}"
        )
    # `inf` and `nan` are both greater than nothing as far as `< 0` is concerned, and both
    # go into the file as a bare `Infinity` or `NaN` -- a token JSON does not have, so a
    # step written with one is a file no strict reader takes back. No limit at all is 0.0.
    if (
        tries < 0
        or not math.isfinite(tries)
        or not math.isfinite(timeout)
        or timeout < 0
    ):
        raise ValueError("tries and seconds are counts, not debts or infinities")
    return _keeps(
        replace(
            tried(from_), spec=from_, tries=tries, policy=policy, timeout=float(timeout)
        )
    )


def clear(said: str) -> bool:
    """Takes one place's whole step away, tries and destination alike.

    Args:
      said: The place it was written down against.

    Returns:
      Whether there was one to take away.
    """
    from_ = reads(said)
    kept = [one for one in falls() if one.spec != from_]
    if not from_ or len(kept) == len(falls()):
        return False
    _writes(kept)
    return True


def chain(said: str) -> list[str]:
    """The places one turn walks, this one first and each falling back to the next.

    Args:
      said: The place the turn is being taken at.

    Returns:
      The specs, in the order they are tried. The first is always this place, whether or not
      anything was written down about it, so that whoever is walking one walks a list rather
      than a list and a special case; the rest are the chain written against it, and only
      against it. A place that is nobody's main -- however many chains it is a step of --
      is a chain of one, and the places after this one are never walked on to their own
      chains: the chain is the one somebody wrote down, read whole, and a list read whole
      is one that cannot come round on itself.
    """
    from_ = reads(said) or said.strip()
    return [from_, *tried(from_).to]


def named(policy: str) -> Policy | None:
    """The policy of that name, or None for a name none answers to."""
    return next((one for one in POLICIES if one.name == policy), None)


def waits(policy: str, attempt: int, base: float = BASE) -> float:
    """How long to wait before one try, given how many have already failed.

    The waits are the ones everybody uses, under the names everybody uses them by, and nothing
    here invents one. What each of them is for is written beside it: the shape of the failure
    decides the shape of the wait, and a queue of agents retrying in lockstep is what jitter
    is for.

    Args:
      policy: The policy, as :data:`POLICIES` names them. One that is not among them waits
        the way the default does: a name nobody recognises is a setting to correct, and
        waiting nothing at all because of it would hammer whatever has just failed.
      attempt: Which try this is going to be, counting the first as 1 -- so the wait before
        the second try is `waits(policy, 2)`.
      base: The first wait, which every policy is written in terms of.

    Returns:
      The seconds to wait, never negative and never longer than :data:`CEILING`.
    """
    over = max(attempt - 1, 0)  # how many waits have already been taken
    if not over:
        return 0.0
    # Held to where the ceiling has long since been reached: `2 ** 4000` is a number Python
    # is happy to build and `float` will not take, and a retry count is somebody's to set.
    over = min(over, _CLIMBED)
    if policy == "none":
        return 0.0
    if policy == "constant":
        held = base
    elif policy == "linear":
        held = base * over
    elif policy == "fibonacci":
        held = base * _fibonacci(over)
    elif policy == "exponential":
        held = base * 2 ** (over - 1)
    else:
        # Full jitter, which is what "exponential backoff with jitter" means everywhere it is
        # documented: anywhere between nothing and the exponential wait. Two agents that
        # failed on the same second do not come back on the same second.
        held = random.uniform(0.0, base * 2 ** (over - 1))  # noqa: S311 -- a wait, not a key
    return min(held, CEILING)


def _fibonacci(over: int) -> int:
    """The nth Fibonacci number, counting 1, 1, 2, 3, 5 from n = 1."""
    before, held = 0, 1
    for _ in range(over - 1):
        before, held = held, before + held
    return held


def _onwards(said: str, to: object, linked: dict[str, str]) -> tuple[str, ...]:
    """The places one place falls back to, as they were written down.

    A list, in the order they are tried -- or a single string, which is how a step was written
    before a place could fall back along more than one: the place it names, and then each place
    the older steps went on to from there, which is the chain such a file always meant. Whatever
    of it cannot be read as a place, names this place, or names one a second time is dropped
    rather than the whole step: a file edited by hand holds whatever somebody typed, and the
    places that are readable are still where somebody meant the turn to go.

    Args:
      said: The place it is written against, already read.
      to: What was written as where it goes.
      linked: Every step written as a single string, by the place it was written against.

    Returns:
      The places, readable, distinct and none of them this one.
    """
    if isinstance(to, str):
        held: list[object] = [reads(to)]
        # Walked until it comes round or runs out, and only through steps of the same older
        # spelling: a chain written as a list is a chain somebody wrote whole.
        while (after := linked.get(cast("str", held[-1]), "")) and after not in held:
            held.append(after)
    else:
        held = cast("list[object]", to) if isinstance(to, list) else []
    onwards: list[str] = []
    for one in held:
        at = reads(one) if isinstance(one, str) else ""
        if at and at != said and at not in onwards:
            onwards.append(at)
    return tuple(onwards)


def _counted(said: object) -> int:
    """One count as it was written down, and none at all for anything that is not one."""
    try:
        # OverflowError beside the rest because a file holds whatever somebody typed, and a
        # number too big to be a count is one of the things they can type: `Infinity`, which
        # `json` reads, and `1e400`, which is JSON and comes back as the same infinity. A
        # count nothing can be made of is no count rather than the end of every run here.
        held = int(cast("int", said))
    except (OverflowError, TypeError, ValueError):
        return 0
    return max(held, 0)


def _seconds(said: object) -> float:
    """One length of time as it was written down, and none at all for anything that is not."""
    try:
        # And a 400-digit integer is the same hole from the other side: `float` will not
        # take one either.
        held = float(cast("float", said))
    except (OverflowError, TypeError, ValueError):
        return 0.0
    # A limit of `inf` or `nan` is a limit that never arrives -- both are something rather
    # than nothing, and neither is ever passed -- and `max` cannot floor a `nan`, which
    # loses every comparison it is in. No limit at all is 0.0, as it is written everywhere.
    return max(held, 0.0) if math.isfinite(held) else 0.0


def _keeps(step: Falls) -> Falls:
    """Writes one step down in place of whatever was written against that place.

    Args:
      step: The step as it now stands.

    Returns:
      It, so that whoever asked for the change is holding what was written.
    """
    kept = [one for one in falls() if one.spec != step.spec]
    if step.says():
        kept.append(step)
    _writes(kept)
    return step


def _writes(steps: Iterable[Falls]) -> None:
    """Writes every step out whole, so that a file read while it is written is one of the two.

    Args:
      steps: What to write down.
    """
    at = home() / _HELD
    at.parent.mkdir(parents=True, exist_ok=True)
    said = (
        json.dumps(
            [
                {
                    "spec": one.spec,
                    "to": list(one.to),
                    "tries": one.tries,
                    "policy": one.policy,
                    "timeout": one.timeout,
                }
                for one in steps
            ],
            indent=2,
        )
        + "\n"
    )
    atomic.writes(at, said, mode=0o600)
