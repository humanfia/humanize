"""Nous: what an agent thinks with, and where a turn goes when it cannot think there.

A nous is either concrete or virtual. A concrete nous is an agent spec without its role:
`<harness>[@<account>]/<model>[:<effort>]`, the harness, the account it runs as, the model and
how hard that model is asked to think. A virtual nous is a name, `smart` or `cheap`, that stands
for a graph of other nous and answers to an agent exactly as a concrete one does: `-a
coder=smart` is an agent like any other.

Every nous has the same envelope. Its body -- one turn of the harness for a concrete nous, a walk
of its graph for a virtual one -- is tried again `tries` times, waiting as `policy` says, for no
longer than `timeout`; and once those tries are spent, the turn is carried to `then`, a graph
of its own that is walked the same way. A nous's envelope and its `then` go with it wherever it
is named: a nous is a black box, and a graph naming one gets it whole.

A graph has two kinds of node. A `use` node takes the turn at one nous, which may be virtual and
so a graph of its own. A `balance` node picks one nous out of several by a strategy, carries the
turn to another of them when it fails, and gives up once `spread` of them have failed. A node
that fails follows the edge named after the fault it failed with -- `throttled`, `retired`, the
fault classes of :data:`hmz.coganchor.backends.FAULTS` -- or else its `*` edge, and a node with
neither is the graph failing with that fault. The first nous to answer ends the walk.

What is lost when a turn moves from one concrete nous to another is the conversation: no harness
takes another's session id, so the turn is taken in a new session there. Which is why a nous's
own tries come first, and why a balance node keeps, for each conversation, the nous it last
answered with and tries it first next time.
"""

from __future__ import annotations

import math
import random
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, cast

from hmz.coganchor import backends, settings

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterable, Mapping, Sequence

__all__ = [
    "ANSWERS",
    "ANY",
    "BASE",
    "CEILING",
    "DEFAULT",
    "POLICIES",
    "STRATEGIES",
    "THROTTLED",
    "Answer",
    "Graph",
    "Member",
    "Node",
    "Nous",
    "Policy",
    "Run",
    "Strategy",
    "Wait",
    "Walk",
    "answers",
    "chain",
    "check",
    "checked",
    "clear",
    "entry",
    "every",
    "finished",
    "graph_of",
    "named",
    "put",
    "reads",
    "renamed",
    "retrying",
    "rule",
    "shown",
    "spec",
    "started",
    "strategies",
    "strategy",
    "then",
    "virtual",
    "waits",
    "walk",
    "written",
]

#: Where in Humanize's settings every nous is written down, by name.
_HELD = "nous"

#: Where versions before nous wrote the chains a failed turn fell back along, read once and
#: carried over as `then` at the next write.
_WAS = "fallbacks"

#: The first wait, which every policy is written in terms of.
BASE = 1.0

#: The longest any single wait may be, however far the backoff has climbed.
CEILING = 60.0

#: How far a backoff is worked out before the answer is the ceiling anyway.
_CLIMBED = 64

#: The edge a node follows for a fault no edge of its own names.
ANY = "*"

#: How deep one nous may name another before the walk stops going in: a graph that names a
#: nous whose graph names the first is refused where it is written, and this is what stops one
#: written by hand.
_DEEPEST = 32


@dataclass(frozen=True, slots=True)
class Policy:
    """One way of waiting between tries.

    Attributes:
      name: What it is called, which is what a nous is written down with.
      about: One line saying what it is and when to reach for it.
    """

    name: str
    about: str


#: Every way a turn may be waited over, plainest first.
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

#: What a nous is retried by where it says nothing.
DEFAULT = "exponential-jitter"

#: The least a turn waits after being told there have been too many requests.
THROTTLED = CEILING / 2

#: How many goes a turn gets at a store another turn had open.
_BUSY = 3


@dataclass(frozen=True, slots=True)
class Answer:
    """What a turn does about one kind of failure.

    Attributes:
      fault: The kind, as `hmz.coganchor.backends.FAULTS` names them, and "" for one nobody
        classified.
      about: What happened, as the clause an event narrating the recovery is built round.
      tries: The fewest goes at a concrete nous, whatever the nous says.
      held: Whether that is also the most, which is none.
      policy: A wait of its own to put under the nous's, or "" to wait only the way it says.
      least: The shortest any of those waits may be.
      reopen: Whether the harness process is let go of before the next go.
      fix: What a person does about it, in a few words.
    """

    fault: str
    about: str
    tries: int = 0
    held: bool = False
    policy: str = ""
    least: float = 0.0
    reopen: bool = False
    fix: str = ""


#: What every kind of failure gets (Section 4.11.3.2 of the core protocol).
ANSWERS: tuple[Answer, ...] = (
    Answer(
        "throttled",
        "is rate-limited",
        tries=1,
        least=THROTTLED,
        fix="the service asks it to slow down, with no quota spent; a wait is what answers it",
    ),
    Answer(
        "spent",
        "has spent its quota",
        tries=1,
        least=THROTTLED,
        fix="this account has spent its quota; another one, or a wait, is what answers it",
    ),
    Answer(
        "refused",
        "was refused the credentials",
        held=True,
        fix="that account needs signing in again",
    ),
    Answer(
        "unlisted",
        "was refused that model",
        held=True,
        fix="that model is not this account's to name; ask it what it runs and name one of those",
    ),
    Answer(
        "retired",
        "has no such model",
        held=True,
        fix="the model is gone or was never this account's; another nous is what answers it",
    ),
    Answer(
        "contended",
        "found its own store busy",
        tries=_BUSY,
        policy="constant",
        fix="two turns of it are sharing one database",
    ),
    Answer("dropped", "lost the connection", tries=1, reopen=True),
    Answer(
        "killed",
        "was killed rather than answered",
        tries=1,
        policy="constant",
        reopen=True,
        fix="the machine it runs on may be out of memory",
    ),
    Answer("missing", "is not installed here", held=True),
    Answer(
        "unmirrored",
        "could not keep its copy of the work here",
        held=True,
        fix="that path cannot be made here; use a workdir whose path you can create here, "
        "or set the harness of the runtime the work is on to env",
    ),
    Answer(
        "fenced",
        "was kept off a host by this run's fence",
        held=True,
        fix="the run's network fence keeps it off that host, which no sign-in answers; "
        "give the role online of ALL to let it through",
    ),
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
      Its row, or the one a failure nobody classified gets: the goes the nous asked for and
      its own wait.
    """
    return next((one for one in ANSWERS if one.fault == fault), Answer(fault, "failed"))


@dataclass(frozen=True, slots=True)
class Strategy:
    """One way a balance node picks the nous a turn is taken at.

    Attributes:
      name: What it is called, which is what a balance node is written down with.
      about: One line saying what it picks.
    """

    name: str
    about: str


#: Every strategy built in, the default first: the routing strategies LiteLLM's router offers,
#: and the round robin of every load balancer there is.
STRATEGIES = (
    Strategy("shuffle", "at random, each as often as its weight says"),
    Strategy("round-robin", "each in turn, each as often as its weight says"),
    Strategy("least-busy", "the one taking the fewest turns right now"),
    Strategy("latency", "the one whose turns have answered fastest lately"),
    Strategy("usage", "the one that has spent the fewest tokens in the last minute"),
    Strategy("cost", "the one whose model is cheapest per token"),
)


@dataclass(frozen=True, slots=True)
class Member:
    """One nous a balance node may pick, as a strategy is shown it.

    Attributes:
      name: The nous.
      weight: How much more often it is picked than a member of weight 1.
      busy: How many turns are being taken at it in this process right now.
      latency: How many seconds its turns have lately taken to answer, 0.0 for none yet.
      tokens: How many tokens its turns spent in the last minute.
      price: US dollars per million tokens in and out, or None for no price known.
      cooling: Whether it was rate-limited or out of quota in the last minute.
    """

    name: str
    weight: int = 1
    busy: int = 0
    latency: float = 0.0
    tokens: int = 0
    price: float | None = None
    cooling: bool = False


#: Strategies a program added, by name: `(members) -> the name of the one to pick`.
_ADDED: dict[str, tuple[Strategy, Callable[[Sequence[Member]], str]]] = {}


def strategy(
    name: str, about: str, picks: Callable[[Sequence[Member]], str]
) -> Strategy:
    """Adds a strategy of one's own, for every balance node in this process that names it.

    Args:
      name: What a balance node names it by; not one of :data:`STRATEGIES`.
      about: One line saying what it picks.
      picks: Given the members still to try, the name of the one to try next. A name that is
        none of them is the first of them.

    Returns:
      The strategy.

    Raises:
      ValueError: For a name already built in, or one that is not a word.
    """
    if not _WORD.fullmatch(name) or any(one.name == name for one in STRATEGIES):
        raise ValueError(f"{name!r} cannot name a strategy of your own")
    made = Strategy(name, about)
    _ADDED[name] = (made, picks)
    return made


def strategies() -> tuple[Strategy, ...]:
    """Every strategy, built in and added, built in first."""
    return STRATEGIES + tuple(made for made, _ in _ADDED.values())


@dataclass(frozen=True, slots=True)
class Node:
    """One node of a graph.

    Attributes:
      id: What the graph's edges call it.
      use: The nous it takes the turn at, for a use node, or "".
      balance: The strategy it picks by, for a balance node, or "".
      among: The nous it picks out of, each with its weight, in the order written.
      spread: How many of them it tries before it fails, 0 for all of them.
      on: Where a fault goes next, by fault class or :data:`ANY`.
    """

    id: str
    use: str = ""
    balance: str = ""
    among: tuple[tuple[str, int], ...] = ()
    spread: int = 0
    on: tuple[tuple[str, str], ...] = ()

    def after(self, fault: str) -> str:
        """The node a failure with this fault goes to, or "" for none."""
        edges = dict(self.on)
        return (edges.get(fault, "") if fault else "") or edges.get(ANY, "")

    def names(self) -> tuple[str, ...]:
        """Every nous this node may take a turn at."""
        return (self.use,) if self.use else tuple(name for name, _ in self.among)


@dataclass(frozen=True, slots=True)
class Graph:
    """Nodes and the edges a failure follows between them.

    Attributes:
      start: The node a walk begins at.
      nodes: Every node, in the order written.
    """

    start: str
    nodes: tuple[Node, ...]

    def node(self, id_: str) -> Node | None:
        """The node of that id, or None."""
        return next((one for one in self.nodes if one.id == id_), None)

    def names(self) -> tuple[str, ...]:
        """Every nous any node names, each once, in the order written."""
        return tuple(dict.fromkeys(name for one in self.nodes for name in one.names()))

    def chained(self) -> tuple[str, ...] | None:
        """The nous in order, for a graph that is one chain of use nodes, or None."""
        found: list[str] = []
        at = self.node(self.start)
        while at is not None:
            if not at.use or [fault for fault, _ in at.on] not in ([], [ANY]):
                return None
            found.append(at.use)
            at = self.node(at.after(""))
        return tuple(found) if len(found) == len(self.nodes) else None


@dataclass(frozen=True, slots=True)
class Nous:
    """One nous as it is written down.

    Attributes:
      name: A concrete nous `<harness>[@<account>]/<model>[:<effort>]`, or a virtual one's name.
      tries: How many times over its body is taken again before `then`.
      policy: How long to wait between those tries, as :data:`POLICIES` names them.
      timeout: The longest the trying again may go on for, in seconds, 0.0 for no limit.
      graph: What a virtual nous is, or None for a concrete one.
      then: Where a turn goes once those tries are spent, or None for nowhere.
    """

    name: str
    tries: int = 0
    policy: str = DEFAULT
    timeout: float = 0.0
    graph: Graph | None = None
    then: Graph | None = None

    @property
    def virtual(self) -> bool:
        """Whether it is a graph rather than a harness."""
        return self.graph is not None

    def says(self) -> bool:
        """Whether it says anything at all, which is what keeps it written down."""
        return self.virtual or self.then is not None or self.tries > 0


#: How a virtual nous, a node and an added strategy may be called.
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*")


def spec(backend: str, model: str, provider: str = "", effort: str = "") -> str:
    """One concrete nous, out of the four things it is.

    Args:
      backend: The harness.
      model: The model it runs.
      provider: The account its turns run as, or "" for this machine's own sign-in.
      effort: How hard it thinks, or "" for the harness's default.

    Returns:
      `<backend>[@<provider>]/<model>[:<effort>]`: no effort is left off, but written `:auto`
      after a model whose own name ends in `:` and a word, which would be read as its effort.
    """
    from hmz.coganchor.spelling import parted

    account = f"@{provider}" if provider else ""
    if not effort or effort == backends.AUTO:
        effort = backends.AUTO if parted(model)[1] else ""
    rung = f":{effort}" if effort else ""
    return f"{backend}{account}/{model}{rung}"


def reads(said: str) -> str:
    """One nous as it is written down, or "" for a text that is no nous.

    Args:
      said: What was written: a concrete nous or a virtual one's name.

    Returns:
      The concrete nous in its canonical spelling, a virtual one's name as it is, or "".
    """
    said = said.strip()
    if "/" not in said:
        return said if virtual(said) else ""
    try:
        _, profile, model, effort, provider = backends.read(said)
    except ValueError:
        return ""
    return spec(profile.name, model, provider, effort)


def virtual(name: str) -> bool:
    """Whether a text can name a virtual nous: a word that is no harness's name."""
    return bool(_WORD.fullmatch(name)) and backends.named(name) is None


def _bare(name: str) -> str:
    """A concrete nous without its effort, or "" for one that has none to drop."""
    if "/" not in name:
        return ""
    backend, _, rest = name.partition("/")
    from hmz.coganchor.spelling import parted

    model, effort = parted(rest)
    return spec(backend, model) if effort else ""


def every() -> list[Nous]:
    """Every nous written down, in the order written."""
    return _read(settings.read())


def rule(said: str) -> Nous:
    """What is written down about one nous.

    A concrete nous with an effort that nothing is written against has whatever is written
    against it without its effort: `claude/opus` is every effort of it.

    Args:
      said: The nous.

    Returns:
      Its entry, or one that says nothing.
    """
    name = reads(said) or said.strip()
    held = {one.name: one for one in every()}
    found = held.get(name) or held.get(_bare(name))
    return replace(found, name=name) if found is not None else Nous(name)


def chain(names: Iterable[str]) -> Graph | None:
    """The graph of nous tried one after another, or None for none."""
    names = tuple(names)
    if not names:
        return None
    ids = [f"n{at}" for at in range(1, len(names) + 1)]
    return Graph(
        ids[0],
        tuple(
            Node(id_, use=name, on=((ANY, ids[at + 1]),) if at + 1 < len(ids) else ())
            for at, (id_, name) in enumerate(zip(ids, names, strict=True))
        ),
    )


def check(nous: Nous, among: Iterable[Nous] | None = None) -> Nous:
    """One nous as :func:`put` would write it, without writing it.

    Args:
      nous: The nous, whole.
      among: Every other nous it is to be written beside, or None for those written down.

    Returns:
      It, as it would be written: its name and the nous of its graphs canonical.

    Raises:
      ValueError: As :func:`put` does.
    """
    name = reads(nous.name)
    if not name:
        raise ValueError(
            f"{nous.name!r} is not a nous: expected HARNESS[@ACCOUNT]/MODEL[:EFFORT] or a name"
        )
    if "/" in name and nous.graph is not None:
        raise ValueError(f"{name} is a concrete nous, and has no graph")
    if "/" not in name and nous.graph is None:
        raise ValueError(f"{name} is a virtual nous, and needs a graph")
    if named(nous.policy) is None:
        raise ValueError(
            f"{nous.policy!r} is not a retry policy: "
            f"{', '.join(one.name for one in POLICIES)}"
        )
    if (
        nous.tries < 0
        or not math.isfinite(nous.tries)
        or not math.isfinite(nous.timeout)
        or nous.timeout < 0
    ):
        raise ValueError("tries and seconds are counts, not debts or infinities")
    made = replace(
        nous,
        name=name,
        timeout=float(nous.timeout),
        graph=_checked(name, nous.graph),
        then=_checked(name, nous.then),
    )

    others = {one.name: one for one in (every() if among is None else among)}
    others.pop(name, None)
    _loops(others | ({name: made} if made.says() else {}))
    return made


def checked(name: str, graph: Graph) -> Graph:
    """One graph of a nous as it would be written, without writing it.

    Raises:
      ValueError: For a graph that does not hold together, naming `name` in why.
    """
    return cast("Graph", _checked(name, graph))


def put(nous: Nous) -> Nous:
    """Writes one nous down in place of whatever was written under its name.

    Args:
      nous: The nous, whole.

    Returns:
      It, as written: its name canonical.

    Raises:
      ValueError: For a nous that cannot be: a name that is no nous, a concrete one with a
        graph or a virtual one without one, a policy or a number nothing waits by, a graph
        that does not hold together, or one that comes round to a nous on its way.
      OSError: If the settings cannot be read, or written.
    """
    made = check(nous)
    name = made.name

    def change(held: dict[str, Any]) -> None:
        kept = {one.name: one for one in _read(held)}
        kept.pop(name, None)
        if made.says():
            kept[name] = made
        _loops(kept)
        _write(held, kept.values())

    settings.changes(change)
    return made


def retrying(said: str, tries: int, policy: str, timeout: float) -> Nous:
    """Says how many times over a failed turn at one nous is taken again, and how.

    Raises:
      ValueError: As :func:`put` does.
      OSError: If the settings cannot be read, or written.
    """
    was = rule(said)
    return put(replace(was, tries=tries, policy=policy, timeout=timeout))


def then(said: str, to: Graph | Sequence[str] | None) -> Nous:
    """Says where one nous's turns go once its tries are spent.

    Args:
      said: The nous.
      to: A graph, the nous tried one after another, or None or nothing for nowhere. A
        single string is one nous rather than a list of its letters.

    Raises:
      ValueError: As :func:`put` does.
      OSError: If the settings cannot be read, or written.
    """
    if isinstance(to, str):
        to = [to] if to.strip() else []
    graph = to if isinstance(to, Graph) or to is None else chain(to)
    return put(replace(rule(said), then=graph))


def clear(said: str) -> bool:
    """Takes one nous away, envelope, graph and `then` alike.

    Returns:
      Whether there was one to take away.

    Raises:
      ValueError: For a nous another nous's graph still names.
      OSError: If the settings cannot be read, or written.
    """
    name = reads(said) or said.strip()
    if all(one.name != name for one in every()):
        return False

    def change(held: dict[str, Any]) -> None:
        kept = {one.name: one for one in _read(held)}
        kept.pop(name, None)
        if "/" not in name:
            for one in kept.values():
                if name in _named(one):
                    raise ValueError(f"{one.name} still names {name}")
        _write(held, kept.values())

    settings.changes(change)
    return True


def renamed(said: str, name: str) -> Nous:
    """Gives a virtual nous another name, every graph that names it following.

    Returns:
      The nous under its new name.

    Raises:
      ValueError: For a name that is no virtual nous written down, a new name that cannot
        name one, or one already taken.
      OSError: If the settings cannot be read, or written.
    """
    was, name = said.strip(), name.strip()
    if not virtual(name):
        raise ValueError(f"{name!r} cannot name a virtual nous")
    found: list[Nous] = []

    def change(held: dict[str, Any]) -> None:
        kept = {one.name: one for one in _read(held)}
        if was not in kept or "/" in was:
            raise ValueError(f"{was!r} is no virtual nous written down")
        if name in kept and name != was:
            raise ValueError(f"{name} is already a nous")

        def moved(graph: Graph | None) -> Graph | None:
            if graph is None:
                return None
            return replace(
                graph,
                nodes=tuple(
                    replace(
                        one,
                        use=name if one.use == was else one.use,
                        among=tuple(
                            (name if member == was else member, weight)
                            for member, weight in one.among
                        ),
                    )
                    for one in graph.nodes
                ),
            )

        made = {
            (name if one.name == was else one.name): replace(
                one,
                name=name if one.name == was else one.name,
                graph=moved(one.graph),
                then=moved(one.then),
            )
            for one in kept.values()
        }
        found.append(made[name])
        _write(held, made.values())

    settings.changes(change)
    return found[0]


def entry(name: str) -> str:
    """The concrete nous a walk of a nous would try first, as far as it can be told now.

    What an agent configured at a virtual nous is built as: its first `use`, and the first
    member of its first `balance`.

    Raises:
      ValueError: For a name that is no nous, or a virtual one with no concrete nous in it.
    """
    seen: set[str] = set()
    at = reads(name) or name
    while "/" not in at:
        graph = rule(at).graph
        if at in seen or graph is None:
            raise ValueError(f"{name!r} is no nous written down")
        seen.add(at)
        first = graph.node(graph.start)
        names = first.names() if first is not None else ()
        if not names:
            raise ValueError(f"{name!r} names no nous to start at")
        at = names[0]
    return at


def named(policy: str) -> Policy | None:
    """The policy of that name, or None for a name none answers to."""
    return next((one for one in POLICIES if one.name == policy), None)


def waits(policy: str, attempt: int, base: float = BASE) -> float:
    """How long to wait before one try, given how many have already failed.

    Args:
      policy: The policy, as :data:`POLICIES` names them; an unknown one waits as the
        default does.
      attempt: Which try this is going to be, counting the first as 1.
      base: The first wait.

    Returns:
      The seconds to wait, never negative and never longer than :data:`CEILING`.
    """
    over = max(attempt - 1, 0)
    if not over:
        return 0.0
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
        held = random.uniform(0.0, base * 2 ** (over - 1))  # noqa: S311 -- a wait, not a key
    return min(held, CEILING)


def _fibonacci(over: int) -> int:
    """The nth Fibonacci number, counting 1, 1, 2, 3, 5 from n = 1."""
    before, held = 0, 1
    for _ in range(over - 1):
        before, held = held, before + held
    return held


@dataclass(frozen=True, slots=True)
class Run:
    """A turn to take at one concrete nous, with that nous's own tries.

    Attributes:
      nous: The concrete nous.
      deadline: The `time.monotonic()` past which no try is begun, or None for none.
    """

    nous: str
    deadline: float | None = None


@dataclass(frozen=True, slots=True)
class Wait:
    """A wait before a virtual nous is walked again.

    Attributes:
      seconds: How long.
      about: The line that narrates it.
    """

    seconds: float
    about: str


@dataclass
class _Stats:
    """What this process has seen of each nous lately, for the strategies to pick by."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    busy: dict[str, int] = field(default_factory=dict[str, int])
    latency: dict[str, float] = field(default_factory=dict[str, float])
    tokens: dict[str, deque[tuple[float, int]]] = field(
        default_factory=dict[str, "deque[tuple[float, int]]"]
    )
    cooling: dict[str, float] = field(default_factory=dict[str, float])
    turned: dict[str, dict[str, float]] = field(
        default_factory=dict[str, "dict[str, float]"]
    )


_SEEN = _Stats()

#: How far back the tokens and the cooling of a nous are remembered, in seconds.
_LATELY = 60.0


def started(names: Iterable[str]) -> None:
    """Counts a turn begun at each of these nous: the concrete one and every pick above it.

    A nous named twice, as a concrete one a balance node picked is, is counted once.
    """
    with _SEEN.lock:
        for name in dict.fromkeys(names):
            _SEEN.busy[name] = _SEEN.busy.get(name, 0) + 1


def finished(
    names: Iterable[str], seconds: float, tokens: int = 0, fault: str | None = None
) -> None:
    """Counts a turn ended at each of these nous: how long it took, what it spent, and how.

    Args:
      names: As :func:`started` was given them, the concrete one last.
      seconds: How long the turn took.
      tokens: How many tokens it spent.
      fault: The fault it failed with, "" for an unclassified failure, or None for none.
    """
    now = time.monotonic()
    names = tuple(names)
    with _SEEN.lock:
        for name in dict.fromkeys(names):
            _SEEN.busy[name] = max(_SEEN.busy.get(name, 0) - 1, 0)
            if fault is None:
                was = _SEEN.latency.get(name)
                _SEEN.latency[name] = (
                    seconds if was is None else 0.7 * was + 0.3 * seconds
                )
            if tokens:
                _SEEN.tokens.setdefault(name, deque()).append((now, tokens))
        if names and fault in ("throttled", "spent"):
            # Only the concrete one failed so: a pick above it may yet answer elsewhere, and
            # its balance node cools it once it has not.
            _SEEN.cooling[names[-1]] = now + _LATELY


def _members(among: Sequence[tuple[str, int]]) -> list[Member]:
    """The members as a strategy is shown them."""
    now = time.monotonic()
    found: list[Member] = []
    with _SEEN.lock:
        for name, weight in among:
            spent = _SEEN.tokens.get(name, deque[tuple[float, int]]())
            while spent and spent[0][0] < now - _LATELY:
                spent.popleft()
            found.append(
                Member(
                    name,
                    weight,
                    _SEEN.busy.get(name, 0),
                    _SEEN.latency.get(name, 0.0),
                    sum(one for _, one in spent),
                    _price(name),
                    _SEEN.cooling.get(name, 0.0) > now,
                )
            )
    return found


def _price(name: str) -> float | None:
    """What a concrete nous's model costs per million tokens in and out, or None."""
    if "/" not in name:
        return None
    from hmz.coganchor import prices
    from hmz.coganchor.spelling import parted

    model, _ = parted(name.partition("/")[2])
    try:
        found = prices.price(model)
    except Exception:  # noqa: BLE001 -- a list that cannot be read prices nothing
        return None
    if found is None:
        return None
    per = found.per_million
    return per.get("input", 0.0) + per.get("output", 0.0)


def _pick(how: str, key: str, members: list[Member]) -> str:
    """The member a strategy picks, out of those still to try."""
    if how in _ADDED:
        said = _ADDED[how][1](tuple(members))
        return said if any(one.name == said for one in members) else members[0].name
    weights = [max(one.weight, 1) for one in members]
    if how == "round-robin":
        # Smooth weighted round robin, as nginx does it: every member gains its weight, the
        # one furthest ahead is picked, and it gives the whole of the weights back.
        with _SEEN.lock:
            held = _SEEN.turned.setdefault(key, {})
            total = sum(weights)
            for one, weight in zip(members, weights, strict=True):
                held[one.name] = held.get(one.name, 0.0) + weight
            best = max(members, key=lambda one: held[one.name])
            held[best.name] -= total
        return best.name
    if how == "least-busy":
        return min(members, key=lambda one: (one.busy, -one.weight)).name
    if how == "latency":
        return min(members, key=lambda one: (one.latency, -one.weight)).name
    if how == "usage":
        return min(members, key=lambda one: one.tokens / max(one.weight, 1)).name
    if how == "cost":
        return min(
            members, key=lambda one: math.inf if one.price is None else one.price
        ).name
    return random.choices(members, weights)[0].name  # noqa: S311 -- a pick, not a key


class Walk:
    """One turn's walk of a nous: the concrete nous to try, in order, and the waits between.

    Asked :meth:`next` for the first step, and again after each with the fault that step
    failed with; None once there is nowhere left to go. :meth:`landed` once a step answered.
    """

    def __init__(
        self,
        root: str,
        *,
        memo: dict[str, str] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Begins a walk of one nous.

        Args:
          root: The nous the agent was configured at.
          memo: What each balance node picked the last time a turn of this conversation
            answered, kept between its turns and tried first.
          clock: The clock deadlines are read off.
        """
        self._memo = memo if memo is not None else {}
        self._clock = clock
        self._picks: list[tuple[str, str]] = []
        self._held = {one.name: one for one in every()}
        self._steps = self._nous(reads(root) or root, (), None)
        self._begun = False

    def next(self, fault: str = "") -> Run | Wait | None:
        """The next step, given the fault the last one failed with.

        Returns:
          A turn to take, a wait to sit out, or None where the walk has nowhere left.
        """
        try:
            if not self._begun:
                self._begun = True
                return next(self._steps)
            return self._steps.send(fault)
        except StopIteration:
            return None

    def picks(self) -> tuple[str, ...]:
        """The members the balance nodes walked into are now at, outermost first."""
        return tuple(member for _, member in self._picks)

    def landed(self) -> None:
        """Keeps what each balance node picked, for the next turn to try first."""
        self._memo.update(dict(self._picks))

    def _rule(self, name: str) -> Nous:
        found = self._held.get(name) or self._held.get(_bare(name))
        return found if found is not None else Nous(name)

    def _nous(
        self, name: str, above: tuple[str, ...], deadline: float | None
    ) -> Generator[Run | Wait, str, str]:
        """Walks one nous: its body under its envelope, then its `then`; answers its fault."""
        if name in above or len(above) >= _DEEPEST:
            return "missing"
        own = self._rule(name)
        if "/" not in name and own.graph is None:
            return "missing"  # a virtual nous nobody wrote down, or one taken away
        inside = (*above, name)
        fault = ""
        if own.graph is None:
            if deadline is not None and self._clock() >= deadline:
                return fault
            fault = yield Run(name, deadline)
        else:
            since, attempt = self._clock(), 0
            while True:
                attempt += 1
                if attempt > 1:
                    answer = answers(fault)
                    if answer.held or attempt - 1 > own.tries:
                        break
                    waiting = max(waits(own.policy, attempt), answer.least)
                    ends = self._clock() + waiting
                    if (own.timeout and ends - since > own.timeout) or (
                        deadline is not None and ends > deadline
                    ):
                        break
                    yield Wait(
                        waiting,
                        f"{name} failed; walking it again in {waiting:.0f}s "
                        f"({attempt - 1} of {own.tries})",
                    )
                ends = since + own.timeout if own.timeout else None
                inner = ends if deadline is None else min(deadline, ends or deadline)
                fault = yield from self._graph(own.graph, inside, inner)
        if own.then is not None:
            fault = yield from self._graph(own.then, inside, deadline)
        return fault

    def _graph(
        self, graph: Graph, above: tuple[str, ...], deadline: float | None
    ) -> Generator[Run | Wait, str, str]:
        """Walks one graph from its start; answers the fault it failed with."""
        fault, at, been = "", graph.node(graph.start), 0
        while at is not None and been <= len(graph.nodes):
            been += 1
            if at.use:
                fault = yield from self._nous(at.use, above, deadline)
            else:
                fault = yield from self._balance(at, above, deadline)
            at = graph.node(at.after(fault))
        return fault

    def _balance(
        self, node: Node, above: tuple[str, ...], deadline: float | None
    ) -> Generator[Run | Wait, str, str]:
        """Tries the members of a balance node, picked by its strategy, until one answers."""
        key = ">".join((*above, node.id))
        left: list[tuple[str, int]] = list(node.among)
        fault = ""
        for _ in range(node.spread or len(left)):
            if not left:
                break
            members = _members(left)
            # Cooling members only once no other is left: a rate limit a minute ago is the
            # likeliest rate limit now.
            warm = [one for one in members if not one.cooling] or members
            kept = self._memo.get(key, "")
            pick = (
                kept
                if any(one.name == kept for one in warm)
                else _pick(node.balance, key, warm)
            )
            left = [one for one in left if one[0] != pick]
            self._picks.append((key, pick))
            try:
                fault = yield from self._nous(pick, above, deadline)
            finally:
                self._picks.pop()
            if fault in ("throttled", "spent"):
                with _SEEN.lock:
                    _SEEN.cooling[pick] = time.monotonic() + _LATELY
        return fault


def walk(root: str, *, memo: dict[str, str] | None = None) -> Walk:
    """A walk of one nous, for one turn; see :class:`Walk`."""
    return Walk(root, memo=memo)


def _named(one: Nous) -> set[str]:
    """Every nous one nous names, in its graph and its `then`."""
    graphs = [graph for graph in (one.graph, one.then) if graph is not None]
    return {name for graph in graphs for name in graph.names()}


def _checked(name: str, graph: Graph | None) -> Graph | None:
    """A graph as it is written down, refused where it does not hold together."""
    if graph is None:
        return None
    ids = [one.id for one in graph.nodes]
    if not ids:
        raise ValueError(f"{name}: a graph needs a node")
    if len(set(ids)) < len(ids):
        raise ValueError(f"{name}: a node id is used twice")
    if graph.start not in ids:
        raise ValueError(f"{name}: the start {graph.start!r} is no node")
    known = {*backends.FAULTS, ANY}
    nodes: list[Node] = []
    for one in graph.nodes:
        if not _WORD.fullmatch(one.id):
            raise ValueError(f"{name}: {one.id!r} cannot name a node")
        if bool(one.use) == bool(one.balance):
            raise ValueError(f"{name}: node {one.id} is a use node or a balance node")
        for fault, to in one.on:
            if fault not in known:
                raise ValueError(f"{name}: node {one.id}: {fault!r} is no fault class")
            if to not in ids:
                raise ValueError(
                    f"{name}: node {one.id} goes to {to!r}, which is no node"
                )
        if one.use:
            use = reads(one.use)
            if not use:
                raise ValueError(f"{name}: node {one.id}: {one.use!r} is not a nous")
            nodes.append(replace(one, use=use))
            continue
        if one.balance not in {made.name for made in strategies()}:
            raise ValueError(
                f"{name}: node {one.id}: {one.balance!r} is no strategy: "
                f"{', '.join(made.name for made in strategies())}"
            )
        among: list[tuple[str, int]] = []
        for member, weight in one.among:
            said = reads(member)
            if not said:
                raise ValueError(f"{name}: node {one.id}: {member!r} is not a nous")
            if said in dict(among):
                raise ValueError(f"{name}: node {one.id} names {said} twice")
            if weight < 1:
                raise ValueError(f"{name}: node {one.id}: a weight is 1 or more")
            among.append((said, weight))
        if not among:
            raise ValueError(f"{name}: node {one.id} balances nothing")
        if one.spread < 0:
            raise ValueError(f"{name}: node {one.id}: spread is 0 or more")
        nodes.append(replace(one, among=tuple(among)))
    made = Graph(graph.start, tuple(nodes))
    reached: set[str] = set()
    _acyclic(name, made, graph.start, (), reached)
    if unreached := [one for one in ids if one not in reached]:
        raise ValueError(
            f"{name}: {', '.join(unreached)} cannot be reached from the start"
        )
    return made


def _acyclic(
    name: str, graph: Graph, at: str, path: tuple[str, ...], reached: set[str]
) -> None:
    """Refuses a graph whose edges come round, noting every node reached."""
    if at in path:
        raise ValueError(f"{name}: the edges come round at node {at}")
    reached.add(at)
    node = graph.node(at)
    for to in dict(node.on).values() if node is not None else ():
        _acyclic(name, graph, to, (*path, at), reached)


def _loops(held: Mapping[str, Nous]) -> None:
    """Refuses nous that name one another round, and virtual ones nobody wrote down."""
    for one in held.values():
        for name in _named(one):
            if "/" not in name and name not in held:
                raise ValueError(
                    f"{one.name} names {name}, which is no nous written down"
                )
    for one in held.values():
        _round(held, one.name)


def _round(held: Mapping[str, Nous], name: str, path: tuple[str, ...] = ()) -> None:
    """Refuses a nous that comes round to itself through those held."""
    if name in path:
        raise ValueError(f"{' -> '.join((*path, name))} comes round")
    found = held.get(name) or held.get(_bare(name))
    for onward in sorted(_named(found)) if found is not None else ():
        _round(held, onward, (*path, name))


def _holds(found: dict[str, Nous], one: Nous | None) -> None:
    """Holds one entry read, unless its name is taken or it names those held round."""
    if one is None or one.name in found:
        return
    try:
        _round({**found, one.name: one}, one.name)
    except ValueError:
        return
    found[one.name] = one


def _read(held: Mapping[str, Any]) -> list[Nous]:
    """Every nous one reading of the settings holds, and the old chains carried over."""
    found: dict[str, Nous] = {}
    said = held.get(_HELD)
    for name, row in cast(
        "dict[object, object]", said if isinstance(said, dict) else {}
    ).items():
        _holds(found, _readone(str(name), row))
    was = held.get(_WAS)
    for row in cast("list[object]", was if isinstance(was, list) else []):
        if not isinstance(row, dict):
            continue
        row = cast("dict[str, Any]", row)
        to: object = row.get("to")
        old: dict[str, object] = {
            "tries": row.get("tries"),
            "policy": row.get("policy"),
            "timeout": row.get("timeout"),
            "then": cast("list[object]", to) if isinstance(to, list) else [],
        }
        _holds(found, _readone(str(row.get("spec") or ""), old))
    return list(found.values())


def _readone(name: str, row: object) -> Nous | None:
    """One entry as it was written, or None for one that cannot be read."""
    said = reads(name)
    if not said or not isinstance(row, dict):
        return None
    row = cast("dict[str, Any]", row)
    policy = str(row.get("policy") or DEFAULT)
    try:
        one = Nous(
            said,
            tries=_counted(row.get("tries")),
            policy=policy if named(policy) else DEFAULT,
            timeout=_seconds(row.get("timeout")),
            graph=_checked(said, graph_of(row.get("graph"))),
            then=_checked(said, graph_of(row.get("then"))),
        )
    except (TypeError, ValueError):
        return None
    if ("/" in said) == one.virtual or not one.says():
        return None
    return one


def graph_of(said: object) -> Graph | None:
    """A graph as it was written: a nous, a list of them, or `start` and `nodes`.

    `nodes` is a mapping from each node's id to the node, as the settings file has it, or a
    list of nodes each with its `id`, as the daemon's methods carry it. A node is `use` or
    `balance` with `among` -- a mapping from nous to weight, a list of nous, or a list of
    `{nous, weight}` -- and `spread`; its edges are `on`, by fault class or `*`, and `next`
    for `*` alone.

    Raises:
      TypeError: For a shape that is none of those.
    """
    if said in (None, "", []):
        return None
    if isinstance(said, str):
        return chain([said])
    if isinstance(said, list):
        return chain(str(one) for one in cast("list[object]", said))
    if not isinstance(said, dict):
        raise TypeError("a graph is a nous, a list of them, or start and nodes")
    said = cast("dict[str, Any]", said)
    nodes: object = said.get("nodes")
    if isinstance(nodes, list):
        rows = [
            cast("dict[str, Any]", one)
            for one in cast("list[object]", nodes)
            if isinstance(one, dict)
        ]
        nodes = {str(one.get("id") or ""): one for one in rows}
    if not isinstance(nodes, dict):
        raise TypeError("a graph's nodes are a mapping or a list")
    made: list[Node] = []
    for id_, row in cast("dict[object, object]", nodes).items():
        if not isinstance(row, dict):
            raise TypeError("a node is a mapping")
        row = cast("dict[object, Any]", row)
        # YAML 1.1, which the settings file is read as, takes a plain `on` for true.
        on: object = row.get("on") or row.get(True) or {}
        edges = (
            [
                (str(fault), str(to))
                for fault, to in cast("dict[object, object]", on).items()
            ]
            if isinstance(on, dict)
            else []
        )
        if row.get("next"):
            edges = [edge for edge in edges if edge[0] != ANY] + [
                (ANY, str(row["next"]))
            ]
        among: object = row.get("among") or {}
        if isinstance(among, list):
            among = {
                str(cast("dict[str, Any]", one).get("nous") or "")
                if isinstance(one, dict)
                else str(one): cast("dict[str, Any]", one).get("weight", 1)
                if isinstance(one, dict)
                else 1
                for one in cast("list[object]", among)
            }
        made.append(
            Node(
                str(id_),
                use=str(row.get("use") or ""),
                balance=str(row.get("balance") or ""),
                among=tuple(
                    (str(member), _counted(weight) or 1)
                    for member, weight in cast("dict[object, object]", among).items()
                )
                if isinstance(among, dict)
                else (),
                spread=_counted(row.get("spread")),
                on=tuple(edges),
            )
        )
    return Graph(str(said.get("start") or (made[0].id if made else "")), tuple(made))


def shown(graph: Graph | None) -> dict[str, Any] | None:
    """A graph as the daemon's methods carry it: whole, its nodes a list, or None."""
    if graph is None:
        return None
    return {
        "start": graph.start,
        "nodes": [
            {
                "id": one.id,
                "use": one.use,
                "balance": one.balance,
                "among": [
                    {"nous": name, "weight": weight} for name, weight in one.among
                ],
                "spread": one.spread,
                "on": dict(one.on),
            }
            for one in graph.nodes
        ],
    }


def written(graph: Graph) -> object:
    """A graph as the settings hold it: a chain as a list, anything else whole."""
    chained = graph.chained()
    if chained is not None:
        return chained[0] if len(chained) == 1 else list(chained)
    nodes: dict[str, Any] = {}
    for one in graph.nodes:
        row: dict[str, Any] = (
            {"use": one.use}
            if one.use
            else {"balance": one.balance, "among": dict(one.among)}
            | ({"spread": one.spread} if one.spread else {})
        )
        edges = dict(one.on)
        if list(edges) == [ANY]:
            row["next"] = edges[ANY]
        elif edges:
            row["on"] = edges
        nodes[one.id] = row
    return {"start": graph.start, "nodes": nodes}


def _write(held: dict[str, Any], every: Iterable[Nous]) -> None:
    """Every nous into one reading of the settings, the old chains gone."""
    rows: dict[str, Any] = {}
    for one in every:
        row: dict[str, Any] = {
            "tries": one.tries,
            "policy": one.policy,
            "timeout": one.timeout,
        }
        if one.graph is not None:
            row["graph"] = written(one.graph)
        if one.then is not None:
            row["then"] = written(one.then)
        rows[one.name] = row
    held[_HELD] = rows
    held.pop(_WAS, None)


def _counted(said: object) -> int:
    """One count as it was written down, and none at all for anything that is not one."""
    try:
        held = int(cast("int", said))
    except (OverflowError, TypeError, ValueError):
        return 0
    return max(held, 0)


def _seconds(said: object) -> float:
    """One length of time as it was written down, and none for anything that is not."""
    try:
        held = float(cast("float", said))
    except (OverflowError, TypeError, ValueError):
        return 0.0
    return max(held, 0.0) if math.isfinite(held) else 0.0
