"""How many agents one hub carries at once, for every backend and every arrangement.

The hub is this process and whatever runs on the cores it is pinned to. The machines an
anchored turn reaches are mocked -- they are this box too, on the cores the hub is not using --
but only in *where* they are: the archive is really built and really installed under each
machine's own cache, the serving half is really started there, and two halves on two different
machines are really introduced through the rendezvous. Everything the hub does is the thing
itself.

What a session runs is the real CLI, started once under the anchor so that its own runtime, its
module resolution and its state directories are paid for through the mirror -- which is the
expensive, backend-specific half of a turn and the reason a node CLI is not a native one --
followed by rounds of :mod:`bench.workload`, which is a turn's file work without a model behind
it. No token is spent and no provider is reached: what is being measured is the machine.

Per cell the concurrency is doubled until sessions lag, then the last good level and the first
bad one are bisected until the answer is known closely enough. `LAGGING` is what "lag" means
here and :func:`tightly` is what "closely enough" means.
"""

from __future__ import annotations

import argparse
import contextlib
import gc
import json
import os
import resource
import selectors
import shutil
import statistics
import subprocess
import sys
import threading
import time
from array import array
from concurrent import futures
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mocked import mock

from hmz.coganchor import backends, rendezvous
from hmz.coganchor.anchor import AnchorConfig

mock()

HERE = Path(__file__).resolve().parent
LAB = Path(os.environ.get("HMZ_BENCH_LAB", "/tmp/hmz-capacity"))  # noqa: S108

#: How many rounds of file work one workload turn does.
ROUNDS = int(os.environ.get("HMZ_BENCH_ROUNDS", "40"))

#: And how many turns one session runs before it is done. A session is a loop of turns, which
#: is what driving an agent is; this is how long it goes on for.
TURNS = int(os.environ.get("HMZ_BENCH_TURNS", "3"))

#: How many files the workspace holds for an agent to read around in, and how big each is.
FILES, SIZE = 64, 6144

#: What counts as lagging: the median session taking this much longer than the best the sweep
#: has seen. Measured against the best rather than against one session alone, because one
#: session on an idle machine is a supervisor and a tracee handing syscalls back and forth
#: across cores that keep going to sleep between stops, and measures slower than a busy one.
LAGGING = 1.5

#: And a floor under it, because a ratio is meaningless where both sides are nothing. A hub
#: coordinating sessions it does not run the agents for answers in tenths of a millisecond,
#: and twice nothing is still nothing: without this, a sweep stops at whichever level first
#: wobbled from a tenth to a fifth and calls that a capacity.
FLOOR = float(os.environ.get("HMZ_BENCH_FLOOR", "0.005"))

#: What no session may exceed however good the median is. A fleet whose worst one in twenty is
#: a tenth of a second behind is a fleet somebody is waiting on.
CEILING = float(os.environ.get("HMZ_BENCH_CEILING", "0.1"))

#: The longest one level may take before it is abandoned. A level that has not finished by
#: then is one nobody is going to wait out at the next size up either.
PATIENCE = 900.0

#: And the hub's memory budget, which is the other way it runs out.
BUDGET = float(os.environ.get("HMZ_BENCH_BUDGET", "64"))

#: Whether the far side is there at all. Set by `--free`, which is how the two arrangements
#: that do not run the agent on the hub are measured: what is wanted from those is the hub's
#: own ceiling, and a far side really running a CLI would bound the answer by this box's other
#: cores rather than by anything about the hub.
FREE = False

#: How many sessions are started at a time. A runner bringing a fleet up does not start them
#: one after another and wait for each, and a sweep that did would measure how fast this
#: process can fork rather than how many agents the hub carries. Those are two numbers and
#: only one of them was asked for.
STARTERS = int(os.environ.get("HMZ_BENCH_STARTERS", "64"))

#: How many threads drain the sessions' streams. One is what a sweep naturally writes and it
#: is wrong: a hub reads each agent's three streams as part of driving that agent, so the
#: reading is spread across whatever it drives them with. Left on one thread, a sweep measures
#: how many pipes one core can drain and calls that a capacity -- which it is not, and which
#: is the same number whatever is being compared.
READERS = int(os.environ.get("HMZ_BENCH_READERS", "4"))

#: How many times a level is run before it is believed. This machine is shared, and about one
#: run in four picks up a stall of a few hundred milliseconds from something that is not this
#: -- concurrency does not change how often it happens, and it has survived being chased out
#: of the ramp, the readers, the memory sampler, the collector and the punching. A single run
#: therefore reports a knee wherever that stall happened to land. Three runs and the middle
#: verdict does not.
TRIES = int(os.environ.get("HMZ_BENCH_TRIES", "3"))

#: The most of a session's life that may be spent bringing the others up. Past this the level
#: is refused: the first sessions are ending before the last have started, so whatever it holds
#: it is not the number asked for.
RAMPING = 0.4

#: How long after the last session is up before lateness starts counting. Bringing a fleet up
#: is real work and is reported as `up`, but it is not what a fleet that is *running* looks
#: like, and a number that mixed the two would be a number about starting.
SETTLING = 2.0

#: How often a held session says when it is. A line a second, which is about what a coding
#: agent's output comes to once it is lines rather than tokens.
BEAT = float(os.environ.get("HMZ_BENCH_BEAT", "1.0"))

#: How long a free-remote session is held open, in seconds. Long enough that the levels
#: overlap properly rather than being a queue of startups.
HOLDING = float(os.environ.get("HMZ_BENCH_HOLDING", "120"))

#: How many mocked machines the sessions share. A real fleet has far fewer machines than it
#: has agents -- a runner hosts several -- and one machine per session would charge every
#: session for installing the archive, which is a cost a machine pays once.
MACHINES = int(os.environ.get("HMZ_BENCH_MACHINES", "64"))

#: What the workspace is called to the agent. Deliberately not a path this machine has, so
#: that a read which somehow skipped the anchor fails loudly instead of quietly succeeding.
VIRTUAL = "/coganchor-capacity"

#: The backends whose CLI is on this machine, which is the only kind that can be measured.
INSTALLED = tuple(
    profile.name
    for profile in backends.PROFILES
    if shutil.which(profile.command or profile.name)
)


def tightly(good: int) -> int:
    """How close the answer has to be before a sweep stops narrowing it.

    Tighter than a hundred everywhere and much tighter where the numbers are small, which
    costs nothing: a sweep that doubled its way to fifty has already bracketed it to within
    twenty-five, and the rounds that take it to within one are the cheapest rounds it runs.
    The rule is a fiftieth of where it is, which never exceeds the hundred asked for until the
    answer is five thousand, and is capped there so it never does.
    """
    return max(1, min(99, good // 50))


@dataclass(frozen=True)
class Arrangement:
    """One of the three places a harness can run, as a session's settings."""

    name: str
    what: str

    def config(self, workspace: Path, which: int) -> AnchorConfig:
        """The settings one session of this arrangement runs under.

        The workspace is named by a path that does not exist on this machine and the target is
        told where it really is. That is not decoration: where the two are the same box, a
        workspace named by its real path is one the agent can open without the anchor being
        consulted at all -- and a measurement that read the files directly would be a
        measurement of this machine's page cache.
        """
        if self.name == "harness-here":
            return AnchorConfig(
                target="docker://env",
                workspace=VIRTUAL,
                remote_path=str(workspace),
                shadow=str(LAB / "mirrors" / str(which)),
                force=True,
            )
        if self.name == "harness-beside":
            return AnchorConfig(
                harness="same",
                target=f"docker://box{which % MACHINES}",
                workspace=VIRTUAL,
                remote_path=str(workspace),
            )
        return AnchorConfig(
            harness=f"docker://a{which % MACHINES}",
            target=f"docker://b{which % MACHINES}",
            workspace=VIRTUAL,
            remote_path=str(workspace),
        )


ARRANGEMENTS = {
    one.name: one
    for one in (
        Arrangement("harness-here", "harness on the hub, work elsewhere"),
        Arrangement("harness-beside", "harness on the machine its work is on"),
        Arrangement("harness-apart", "harness on one machine, work on another"),
    )
}


def workspace(which: int) -> Path:
    """The project one session works in, made once and kept.

    One apiece rather than one shared: sessions write as well as read, and a workspace several
    were writing into would be one whose mirrors kept going out of date -- which is a real
    thing an anchor does and a useless thing to be measuring, since how often it happened would
    be set by the concurrency being varied.
    """
    where = LAB / "workspaces" / str(which)
    if where.is_dir() and len(list(where.iterdir())) >= FILES:
        return where
    where.mkdir(parents=True, exist_ok=True)
    for n in range(FILES):
        (where / f"src-{n:03d}.py").write_text(
            f"# file {n}\n" + "x = 1\n" * (SIZE // 6)
        )
    return where


def commanded(backend: str) -> str:
    """The command a backend is installed as, which is what an anchored turn of it runs."""
    return backends.named(backend).command or backend


def working() -> list[str]:
    """The turn that does a turn's file work, as the agent rather than as something it spawns.

    Which matters more than it looks. An anchor sends everything the agent *spawns* to the
    machine the work lands on, so a workload started with `exec` from a shell would run over
    there, untraced, against the real directory -- fast, and measuring nothing. The agent is
    the thing the supervisor traces, so the agent has to be the thing doing the reading.
    """
    return [sys.executable, str(HERE / "workload.py"), str(ROUNDS)]


def freely(arrangement: Arrangement, backend: str, which: int) -> list[str]:
    """One session whose far side costs nothing, with every bit of the hub's work still real.

    The line is rendered -- which is what pushes the archive, books the meeting and leaves a
    serving half waiting at it -- and then, instead of the harness that line names, the hub
    spawns a holder down the same road. What the hub does per session is unchanged; what the
    other machine does is not there, which is the point: under these two arrangements the agent
    is not the hub's to run, and a far side that really ran one would only re-measure the first
    arrangement on fewer cores.

    Args:
      arrangement: Which of the two.
      backend: Whose settings the line is rendered from.
      which: This session's number.

    Returns:
      The command the hub spawns.
    """
    config = arrangement.config(workspace(which), which)
    line = config.command([commanded(backend), "--version"])
    met = "-"
    for word in line:
        if word.startswith("--target=peer://"):
            met = word[len("--target=peer://") :]
    cores = os.environ.get("HMZ_BENCH_REMOTE_CORES", "16-63")
    if met == "-":
        # No meeting to keep, so nothing on the far side needs an interpreter. A shell saying
        # the time on a loop is a megabyte and a millisecond, which is what "the far side costs
        # nothing" has to mean if the far side is not to be the thing that runs out first.
        return [
            "taskset",
            "-c",
            cores,
            "/bin/sh",
            "-c",
            (
                f"n=0; while [ $n -lt {int(HOLDING / max(BEAT, 0.001))} ]; do "
                f"date +%s.%N; sleep {BEAT}; n=$((n+1)); done"
            ),
        ]
    return [
        "taskset",
        "-c",
        cores,
        sys.executable,
        "-S",
        str(HERE / "holder.py"),
        met,
        str(HOLDING),
    ]


def hubbed(line: list[str]) -> list[str]:
    """Runs a harness that lives on the hub through the shim that mocks its road.

    A harness put on another machine needs none of it: the line reaching that machine already
    goes through a mocked road, and what it runs over there derives no `docker://` road of its
    own.
    """
    if line[:2] == [sys.executable, "-m"]:
        return [sys.executable, str(HERE / "hub.py"), *line[3:]]
    return line


def once(arrangement: Arrangement, backend: str, concurrency: int) -> dict[str, float]:
    """Runs that many sessions at once and answers with how each round of each one went."""
    complaints = open(  # noqa: SIM115
        os.environ.get("HMZ_BENCH_STDERR", os.devnull), "ab"
    )
    began = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_SELF)
    before_kids = resource.getrusage(resource.RUSAGE_CHILDREN)

    # Rendered and spawned one at a time, which is what a driver does: rendering is not free of
    # consequences, since for the arrangement whose halves are on two machines it books a
    # meeting and leaves the serving half waiting at it.
    def starting(which: int) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            freely(arrangement, backend, which)
            if FREE
            else [
                sys.executable,
                str(HERE / "driver.py"),
                arrangement.name,
                backend,
                str(which),
                str(TURNS),
            ],
            stdout=subprocess.PIPE,
            stderr=complaints,
        )

    with futures.ThreadPoolExecutor(max_workers=STARTERS) as starters:
        running = list(starters.map(starting, range(concurrency)))
    complaints.close()
    # Raw descriptors and our own line buffering, not `readline` on the file object: a selector
    # asks the kernel whether there is anything to read, and a buffered reader keeps what it
    # has already pulled -- so a second line that arrived in the same read sits there unnoticed
    # until fresh bytes turn up, and every hub measures one beat late for reasons of its own.
    # Two flat arrays of doubles rather than a list of tuples, and the collector off while
    # they fill. A level at a few thousand sessions gathers millions of samples, and as
    # objects that is a heap the collector walks -- which it does for a fifth of a second at a
    # time, with every reader stopped, often enough to land on the ninety-fifth percentile and
    # rarely enough to look like a capacity that moves between runs. Doubles in an array are
    # not objects and are not walked.
    when_read = array("d")
    what_read = array("d")
    began_up: dict[int, float] = {}
    speaking = threading.Lock()
    gc.disable()
    watched = {"rss": 0.0, "stop": 0.0}

    def sampling() -> None:
        # In a process of its own, and this is the third place it has lived. Taking it walks
        # every process on the machine and reads a file for each, which at a few thousand
        # sessions is a couple of hundred milliseconds -- and in a thread that is a couple of
        # hundred milliseconds with the interpreter lock held, so the readers stop too. Every
        # other second that puts a stall into about one sample in twenty, which is exactly
        # where the ninety-fifth percentile is read: the sweep then reports a tail that is its
        # own, wanders in and out of it between runs, and calls whichever level it happened to
        # land on a capacity. Three runs of one level gave 0.5 ms, 0.5 ms and 148 ms.
        while not watched["stop"]:
            said = subprocess.run(
                [sys.executable, str(HERE / "resident.py"), str(os.getpid())],
                capture_output=True,
                text=True,
                check=False,
            )
            with contextlib.suppress(ValueError):
                watched["rss"] = max(watched["rss"], float(said.stdout))
            time.sleep(5.0)

    def reading(mine: list[subprocess.Popen[bytes]]) -> None:
        watching = selectors.DefaultSelector()
        holding: dict[int, bytearray] = {}
        for each in mine:
            assert each.stdout is not None  # noqa: S101
            watching.register(each.stdout.fileno(), selectors.EVENT_READ, each)
            holding[each.stdout.fileno()] = bytearray()
        when_here = array("d")
        what_here = array("d")
        up_here: dict[int, float] = {}
        live = len(mine)
        while live:
            for key, _ in watching.select(timeout=1.0):
                fd = int(key.fileobj)  # pyright: ignore[reportArgumentType]
                try:
                    arrived = os.read(fd, 1 << 16)
                except OSError:
                    arrived = b""
                if not arrived:
                    watching.unregister(fd)
                    live -= 1
                    continue
                buffered = holding[fd]
                buffered += arrived
                while b"\n" in buffered:
                    line, _, rest = buffered.partition(b"\n")
                    buffered[:] = rest
                    try:
                        measured = (
                            time.time() - float(line)
                            if FREE
                            else float(json.loads(line)["took"])
                        )
                    except (ValueError, KeyError, TypeError):
                        continue
                    now = time.monotonic()
                    when_here.append(now)
                    what_here.append(measured)
                    up_here.setdefault(key.data.pid, now)
            if time.monotonic() - began > PATIENCE:
                break
        watching.close()
        with speaking:
            when_read.extend(when_here)
            what_read.extend(what_here)
            began_up.update(up_here)

    threading.Thread(target=sampling, daemon=True).start()
    readers = [
        threading.Thread(target=reading, args=(running[at::READERS],), daemon=True)
        for at in range(min(READERS, len(running)))
    ]
    for one in readers:
        one.start()
    for one in readers:
        one.join()
    wall = time.monotonic() - began
    watched["stop"] = 1.0
    gc.enable()
    gc.collect()
    # After the waits, not before: a child's CPU is only accounted to its parent once the
    # parent has reaped it, so reading this while the sessions are still running reads nought.
    failed = sum(1 for each in running if each.wait() != 0)
    after = resource.getrusage(resource.RUSAGE_SELF)
    after_kids = resource.getrusage(resource.RUSAGE_CHILDREN)
    own = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
    # The drivers, the anchors and the CLIs under them. For the arrangement whose harness is on
    # the hub these are the hub's own cores; for the other two they are the mocked machines'.
    kids = (after_kids.ru_utime - before_kids.ru_utime) + (
        after_kids.ru_stime - before_kids.ru_stime
    )
    if not what_read:
        return {"at": concurrency, "failed": float(concurrency), "median": float("inf")}
    up_by = (max(began_up.values()) if began_up else began) - began
    settled = began + up_by + SETTLING
    ordered = sorted(
        what for when, what in zip(when_read, what_read, strict=True) if when >= settled
    ) or sorted(what_read)
    return {
        "at": concurrency,
        "failed": float(failed),
        "median": statistics.median(ordered),
        "p95": ordered[int(len(ordered) * 0.95)],
        "rounds": float(len(ordered)),
        "up_by": up_by,
        "wall": wall,
        "rounds_per_s": len(ordered) / wall,
        "hub_cores": own / wall,
        "kid_cores": kids / wall,
        "rss": watched["rss"],
        "threads": float(len(os.listdir("/proc/self/task"))),
    }


def steadily(
    arrangement: Arrangement, backend: str, at: int, best: float
) -> tuple[dict[str, float], str]:
    """Runs one level until its verdict is the same twice, and answers with that.

    Two agreeing out of at most :data:`TRIES` rather than an average, because the thing being
    filtered is not noise around a value -- it is an occasional stall that turns a level's
    answer from one number into another. A middle verdict is the right statistic for that; a
    mean of the two would be a number neither run saw.
    """
    seen: list[tuple[dict[str, float], str]] = []
    for _ in range(TRIES):
        got = once(arrangement, backend, at)
        mark = lagging(got, best)
        say(arrangement.name, backend, got, mark)
        seen.append((got, mark))
        agreeing = [one for one in seen if one[1] == mark]
        if len(agreeing) > TRIES // 2:
            return agreeing[0]
    return seen[0]


def lagging(got: dict[str, float], best: float) -> str:
    """Why this level is not a level that worked, or `ok`.

    `RAMP` first, because it invalidates the rest: if bringing the sessions up took an
    appreciable share of how long they are held, the ones started first were gone before the
    ones started last arrived and the level never had that many running at once. Whatever it
    then measured, it did not measure that concurrency -- so it is refused rather than read.
    """
    if got["median"] == float("inf"):
        return "NOTHING"
    if got.get("up_by", 0.0) > HOLDING * RAMPING:
        return "RAMP"
    if got["failed"]:
        return "FAILED"
    if got["rss"] > BUDGET:
        return "MEMORY"
    if got["p95"] > CEILING:
        return "TAIL"
    if best < float("inf") and got["median"] > best * LAGGING and got["median"] > FLOOR:
        return "SLOW"
    return "ok"


def say(arrangement: str, backend: str, got: dict[str, float], mark: str) -> None:
    """One line per level, so a sweep is readable while it runs."""
    if got["median"] == float("inf"):
        print(f"  {arrangement}/{backend} {int(got['at']):5d}: nothing came back")
        return
    print(
        f"  {arrangement}/{backend} {int(got['at']):5d}: "
        f"round median {got['median'] * 1000:7.1f} ms  p95 {got['p95'] * 1000:8.1f} ms  "
        f"up {got['up_by']:5.1f}s {got['rounds_per_s']:7.1f}/s  "
        f"cpu {got['hub_cores']:4.2f}+{got['kid_cores']:6.2f} cores {got['rss']:6.2f} GiB "
        f"{int(got.get('threads', 0)):6d} thr  "
        f"failed {int(got['failed']):4d}  {mark}",
        flush=True,
    )


def named_levels(
    arrangement: Arrangement, backend: str, levels: list[int]
) -> dict[str, object]:
    """Runs exactly the levels asked for and reads an answer off them.

    For a cell whose neighbours have been searched already, where the answer is is known to
    within a step; what is left is to check that this backend agrees, and two levels a hair
    apart say so at a cost of two rounds rather than a dozen.
    """
    best, good, bad, why = float("inf"), 0, 0, "ok"
    for at in sorted(levels):
        got, mark = steadily(arrangement, backend, at, best)
        if mark == "ok":
            best, good = min(best, got["median"]), at
        elif not bad:
            bad, why = at, mark
    print(
        f"  >>> {arrangement.name}/{backend}: {good} at once "
        f"({bad or 'nothing'} {why}), +/-{bad - good if bad else 'unbounded'}",
        flush=True,
    )
    return {"good": good, "bad": bad or None, "why": why, "best": best}


def sweep(
    arrangement: Arrangement, backend: str, ceiling: int, opening: int
) -> dict[str, object]:
    """Doubles until it lags, then bisects until the answer is known closely enough."""
    best = float("inf")
    good, bad, why = 0, 0, "ok"
    at = max(1, opening)
    while at <= ceiling:
        got, mark = steadily(arrangement, backend, at, best)
        if mark != "ok":
            bad, why = at, mark
            break
        best = min(best, got["median"])
        good = at
        at *= 2
    if not bad:
        return {"good": good, "bad": None, "why": "ceiling", "best": best}
    if not good:  # even the opening level lagged; walk back down
        at = max(1, bad // 2)
        while at >= 1:
            got, mark = steadily(arrangement, backend, at, best)
            if mark == "ok":
                best, good = min(best, got["median"]), at
                break
            bad, why, at = at, mark, at // 2
        if not good:
            return {"good": 0, "bad": bad, "why": why, "best": best}
    while bad - good > tightly(good):
        middle = (good + bad) // 2
        got, mark = steadily(arrangement, backend, middle, best)
        if mark == "ok":
            best, good = min(best, got["median"]), middle
        else:
            bad, why = middle, mark
    print(
        f"  >>> {arrangement.name}/{backend}: {good} at once "
        f"({bad} {why}), +/-{bad - good}",
        flush=True,
    )
    return {"good": good, "bad": bad, "why": why, "best": best}


def main() -> int:
    """Runs whichever cells of the matrix were asked for, narrowing each until it is known."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arrangement", action="append", default=[])
    parser.add_argument("--backend", action="append", default=[])
    parser.add_argument("--ceiling", type=int, default=16384)
    parser.add_argument("--opening", type=int, default=1)
    parser.add_argument("--relay", action="store_true", help="carry every meeting")
    parser.add_argument(
        "--free", action="store_true", help="a far side that costs nothing"
    )
    parser.add_argument("--out", default="", help="where to write the results as JSON")
    parser.add_argument(
        "--at",
        default="",
        help="run exactly these levels rather than searching, as a comma list. For a cell "
        "whose neighbours have already been searched, two levels a hair apart are the whole "
        "of the answer and cost two rounds instead of a dozen.",
    )
    args = parser.parse_args()

    global FREE  # noqa: PLW0603 -- one run is one mode
    FREE = args.free
    LAB.mkdir(parents=True, exist_ok=True)
    broker, host, port = rendezvous.shared()
    if args.relay:
        broker._punching = 0.0  # noqa: SLF001
    cores = sorted(os.sched_getaffinity(0))
    print(
        f"hub on {len(cores)} cores ({cores[0]}-{cores[-1]}), {BUDGET:.0f} GiB budget, "
        f"{'a far side that costs nothing' if FREE else str(ROUNDS) + ' rounds a session'}, "
        f"rendezvous at {host}:{port}"
        f"{' (carrying everything)' if args.relay else ''}",
        flush=True,
    )
    asked = [int(one) for one in args.at.split(",") if one.strip()]
    found: dict[str, dict[str, object]] = {}
    for name in args.arrangement or list(ARRANGEMENTS):
        opening = args.opening
        for backend in args.backend or INSTALLED:
            got = (
                named_levels(ARRANGEMENTS[name], backend, asked)
                if asked
                else sweep(ARRANGEMENTS[name], backend, args.ceiling, opening)
            )
            found[f"{name}/{backend}"] = got
            # The next backend of the same arrangement starts where the last one landed, which
            # is most of what makes a matrix this size finish: the doubling is the expensive
            # part and every cell of a column lands within a factor or two of its neighbours.
            opening = max(1, int(got["good"] or 1))
            if args.out:
                Path(args.out).write_text(json.dumps(found, indent=2))
    print(f"\nbroker carried {broker.carried} sessions", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
