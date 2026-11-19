"""`hmz.coganchor.nous`: what an agent thinks with, and where a turn goes when it cannot."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pytest
import yaml

from hmz.coganchor import backends, nous, prices, settings
from hmz.coganchor.nous import ANY, Graph, Node, Nous, Run, Wait

if TYPE_CHECKING:
    from collections.abc import Sequence


def test_every_fault_has_exactly_one_answer() -> None:
    faults = [one.fault for one in nous.ANSWERS]
    assert sorted(faults) == sorted(backends.FAULTS)


@pytest.mark.parametrize("answer", nous.ANSWERS, ids=lambda one: one.fault)
def test_every_answer_is_well_formed(answer: nous.Answer) -> None:
    assert answer.about
    assert answer.tries >= 0
    assert answer.least >= 0
    assert not answer.policy or nous.named(answer.policy) is not None
    if answer.held:
        assert answer.tries == 0


@pytest.mark.parametrize("fault", ["", "never-heard-of-it"])
def test_answers_an_unclassified_failure_as_a_turn_always_was(fault: str) -> None:
    assert nous.answers(fault) == nous.Answer(fault, "failed")


def test_a_fenced_turn_is_told_the_permission_field_that_lets_it_through() -> None:
    fix = nous.answers("fenced").fix
    assert "give the role network=True" in fix
    assert "online" not in fix


def test_policies_and_strategies_are_named_once() -> None:
    for names in (
        [one.name for one in nous.POLICIES],
        [one.name for one in nous.strategies()],
    ):
        assert len(names) == len(set(names))
    assert nous.named(nous.DEFAULT) is not None
    assert nous.strategies()[0].name == "shuffle"


@pytest.mark.parametrize(
    ("args", "said"),
    [
        (("claude", "claude-opus-5"), "claude/claude-opus-5"),
        (("claude", "claude-opus-5", "work"), "claude@work/claude-opus-5"),
        (("claude", "claude-opus-5", "work", "high"), "claude@work/claude-opus-5:high"),
        (("claude", "claude-opus-5", "", "auto"), "claude/claude-opus-5"),
        (("kimi", "moonshot/kimi-k3"), "kimi/moonshot/kimi-k3"),
        (("opencode", "ollama/qwen3:latest"), "opencode/ollama/qwen3:latest:auto"),
        (
            ("opencode", "ollama/qwen3:latest", "", "auto"),
            "opencode/ollama/qwen3:latest:auto",
        ),
        (
            ("opencode", "ollama/qwen3:latest", "", "high"),
            "opencode/ollama/qwen3:latest:high",
        ),
    ],
)
def test_spec(args: tuple[str, ...], said: str) -> None:
    assert nous.spec(*args) == said


@pytest.mark.parametrize(
    ("said", "read"),
    [
        ("claude/claude-opus-5", "claude/claude-opus-5"),
        (" claude-code @ work / claude-opus-5:high ", "claude@work/claude-opus-5:high"),
        ("claude/claude-opus-5:auto", "claude/claude-opus-5"),
        ("grok-build/grok-5", "grok/grok-5"),
        ("opencode/ollama/qwen3:8b", "opencode/ollama/qwen3:8b"),
        ("opencode/ollama/qwen3:latest:auto", "opencode/ollama/qwen3:latest:auto"),
        ("opencode/ollama/qwen3:latest:", "opencode/ollama/qwen3:latest:auto"),
        ("smart", "smart"),
        ("claude", ""),
        ("claude/", ""),
        ("claude@/m", ""),
        ("nobody/m", ""),
        ("two words", ""),
        ("", ""),
    ],
)
def test_reads(said: str, read: str) -> None:
    assert nous.reads(said) == read


def test_nothing_written_is_a_nous_that_says_nothing() -> None:
    assert nous.every() == []
    assert nous.rule("claude/m") == Nous("claude/m")
    assert not nous.rule("claude/m").says()


def test_a_concrete_nous_with_an_effort_has_what_is_written_without_it() -> None:
    nous.retrying("claude/m", 2, "constant", 0)
    assert nous.rule("claude/m:high").tries == 2
    nous.retrying("claude/m:high", 5, "constant", 0)
    assert nous.rule("claude/m:high").tries == 5
    assert nous.rule("claude/m:low").tries == 2


def test_a_model_ending_in_a_word_keeps_its_name_where_its_effort_is_dropped() -> None:
    nous.retrying("opencode/ollama/qwen3:latest:auto", 2, "constant", 0)
    assert nous.rule("opencode/ollama/qwen3:latest:high").tries == 2
    assert nous.rule("opencode/ollama/qwen3:latest").tries == 0


def test_then_writes_a_chain_down_as_a_list() -> None:
    made = nous.then("claude/a", ["codex/b", "grok-build/c"])
    assert made.then == nous.chain(["codex/b", "grok/c"])
    assert settings.read()["nous"] == {
        "claude/a": {
            "tries": 0,
            "policy": nous.DEFAULT,
            "timeout": 0.0,
            "then": ["codex/b", "grok/c"],
        }
    }
    nous.then("claude/a", "codex/b")
    assert settings.read()["nous"]["claude/a"]["then"] == "codex/b"


@pytest.mark.parametrize("nowhere", [[], "", "  ", None])
def test_then_nowhere_takes_the_nous_away(nowhere: Sequence[str] | None) -> None:
    nous.then("claude/a", ["codex/b"])
    assert nous.then("claude/a", nowhere) == Nous("claude/a")
    assert nous.every() == []


def _smart() -> Graph:
    return Graph(
        "pool",
        (
            Node(
                "pool",
                balance="least-busy",
                among=(("claude@work/a", 1), ("claude@team/a", 2)),
                on=(("spent", "other"), (ANY, "cheap")),
            ),
            Node("other", use="codex/b", on=((ANY, "cheap"),)),
            Node("cheap", use="grok/c"),
        ),
    )


def test_a_virtual_nous_is_written_whole_and_read_back() -> None:
    made = nous.put(Nous("smart", tries=1, graph=_smart()))
    assert nous.every() == [made]
    assert settings.read()["nous"]["smart"]["graph"] == {
        "start": "pool",
        "nodes": {
            "pool": {
                "balance": "least-busy",
                "among": {"claude@work/a": 1, "claude@team/a": 2},
                "on": {"spent": "other", ANY: "cheap"},
            },
            "other": {"use": "codex/b", "next": "cheap"},
            "cheap": {"use": "grok/c"},
        },
    }
    assert nous.graph_of(nous.shown(made.graph)) == made.graph


def test_a_graph_reads_every_shape_it_is_written_in() -> None:
    assert nous.graph_of("codex/b") == nous.chain(["codex/b"])
    assert nous.graph_of(["codex/b", "grok/c"]) == nous.chain(["codex/b", "grok/c"])
    assert nous.graph_of(None) is None
    listed = nous.graph_of(
        {
            "start": "p",
            "nodes": [
                {
                    "id": "p",
                    "balance": "cost",
                    "among": ["kimi/x", {"nous": "opencode/y", "weight": 3}],
                }
            ],
        }
    )
    assert listed == Graph(
        "p", (Node("p", balance="cost", among=(("kimi/x", 1), ("opencode/y", 3))),)
    )
    with pytest.raises(TypeError):
        nous.graph_of(7)


@pytest.mark.parametrize(
    ("made", "why"),
    [
        (Nous("nobody/a", tries=1), "is not a nous"),
        (Nous("claude/a", graph=nous.chain(["codex/b"])), "has no graph"),
        (Nous("smart"), "needs a graph"),
        (Nous("claude/a", tries=1, policy="sometimes"), "is not a retry policy"),
        (Nous("claude/a", tries=-1), "counts"),
        (Nous("claude/a", tries=1, timeout=math.inf), "counts"),
        (Nous("claude/a", then=nous.chain(["claude-code/a"])), "comes round"),
        (Nous("claude/a", then=nous.chain(["ghost"])), "no nous written down"),
        (Nous("smart", graph=Graph("x", (Node("p", use="codex/b"),))), "is no node"),
        (
            Nous(
                "smart", graph=Graph("p", (Node("p", use="codex/b", on=((ANY, "p"),)),))
            ),
            "come round",
        ),
        (
            Nous(
                "smart",
                graph=Graph("p", (Node("p", use="codex/b"), Node("q", use="grok/c"))),
            ),
            "cannot be reached",
        ),
        (
            Nous(
                "smart",
                graph=Graph("p", (Node("p", use="codex/b", on=(("late", "p"),)),)),
            ),
            "no fault class",
        ),
        (
            Nous(
                "smart",
                graph=Graph("p", (Node("p", balance="dice", among=(("kimi/x", 1),)),)),
            ),
            "no strategy",
        ),
        (
            Nous(
                "smart",
                graph=Graph(
                    "p",
                    (Node("p", balance="cost", among=(("kimi/x", 1), ("kimi/x", 2))),),
                ),
            ),
            "twice",
        ),
        (
            Nous("smart", graph=Graph("p", (Node("p", balance="cost"),))),
            "balances nothing",
        ),
    ],
)
def test_put_refuses_a_nous_that_cannot_be(made: Nous, why: str) -> None:
    with pytest.raises(ValueError, match=why):
        nous.put(made)
    assert nous.every() == []


def test_check_says_what_put_would_without_writing() -> None:
    made = nous.check(Nous("claude-code/a", tries=1))
    assert made == Nous("claude/a", tries=1)
    assert nous.every() == []
    looped = Nous("a", graph=nous.chain(["b"]))
    with pytest.raises(ValueError, match="comes round"):
        nous.check(looped, [Nous("b", graph=nous.chain(["a"]))])
    assert nous.checked(
        "smart", Graph("n1", (Node("n1", use="claude-code/a"),))
    ) == nous.chain(["claude/a"])
    with pytest.raises(ValueError, match="smart: the start"):
        nous.checked("smart", Graph("x", (Node("p", use="codex/b"),)))


def test_nous_that_name_one_another_round_are_refused() -> None:
    nous.put(Nous("a", graph=nous.chain(["codex/b"])))
    nous.put(Nous("b", graph=nous.chain(["a"])))
    with pytest.raises(ValueError, match="comes round"):
        nous.put(Nous("a", graph=nous.chain(["b"])))


def test_a_virtual_nous_another_names_is_not_cleared_and_renames_with_it() -> None:
    nous.put(Nous("inner", graph=nous.chain(["codex/b"])))
    nous.then("claude/a", ["inner"])
    with pytest.raises(ValueError, match="still names inner"):
        nous.clear("inner")
    nous.renamed("inner", "kept")
    assert [one.name for one in nous.every()] == ["kept", "claude/a"]
    assert nous.rule("claude/a").then == nous.chain(["kept"])
    nous.put(Nous("other", graph=nous.chain(["grok/c"])))
    with pytest.raises(ValueError, match="already a nous"):
        nous.renamed("other", "kept")
    assert nous.clear("other")
    assert nous.clear("claude-code/a")
    assert nous.clear("kept")
    assert not nous.clear("kept")


def test_entry_is_where_a_walk_starts() -> None:
    nous.put(Nous("smart", graph=_smart()))
    nous.put(Nous("outer", graph=nous.chain(["smart", "codex/b"])))
    assert nous.entry("outer") == "claude@work/a"
    assert nous.entry("claude/x:high") == "claude/x:high"
    with pytest.raises(ValueError, match="no nous written down"):
        nous.entry("ghost")


def _hand_written(held: object) -> None:
    at = settings.where()
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(yaml.safe_dump(held), encoding="utf-8")


def test_the_old_fallbacks_are_read_as_then_and_dropped_at_the_next_write() -> None:
    _hand_written(
        {
            "fallbacks": [
                "not a row",
                {"spec": "claude/a", "to": ["codex/b"], "tries": 2, "policy": "linear"},
                {"spec": "nobody/a", "to": ["codex/b"]},
            ]
        }
    )
    assert nous.every() == [
        Nous("claude/a", 2, "linear", 0.0, then=nous.chain(["codex/b"]))
    ]
    nous.retrying("grok/c", 1, "constant", 0)
    held = settings.read()
    assert "fallbacks" not in held
    assert list(held["nous"]) == ["claude/a", "grok/c"]


def test_old_fallbacks_that_name_one_another_round_do_not_refuse_the_next_write() -> (
    None
):
    _hand_written(
        {
            "fallbacks": [
                {"spec": "claude/a", "to": ["codex/b"], "tries": 2, "policy": "linear"},
                {"spec": "codex/b", "to": ["claude/a"], "tries": 1, "policy": "linear"},
            ]
        }
    )
    assert nous.every() == [
        Nous("claude/a", 2, "linear", 0.0, then=nous.chain(["codex/b"]))
    ]
    nous.retrying("grok/c", 1, "constant", 0)
    held = settings.read()
    assert "fallbacks" not in held
    assert list(held["nous"]) == ["claude/a", "grok/c"]
    with pytest.raises(ValueError, match="comes round"):
        nous.then("codex/b", ["claude/a"])


def test_an_entry_that_names_those_before_it_round_is_ignored_when_read() -> None:
    _hand_written(
        {
            "nous": {
                "claude/a": {"tries": 1, "then": "codex/b"},
                "codex/b": {"then": "claude/a:high"},
            }
        }
    )
    assert [one.name for one in nous.every()] == ["claude/a"]
    nous.retrying("grok/c", 1, "constant", 0)
    assert list(settings.read()["nous"]) == ["claude/a", "grok/c"]


def test_every_reads_what_somebody_wrote_by_hand_forgivingly() -> None:
    _hand_written(
        {
            "nous": {
                "nobody/a": {"tries": 1},
                "claude/a": {"tries": "3", "timeout": "inf", "policy": "sometimes"},
                "claude/b": {},
                "smart": {"tries": 1},
                "codex/b": {"graph": ["grok/c"]},
                "grok/c": {"tries": -2, "then": {"start": "x", "nodes": "no"}},
                "kimi/d": "not a mapping",
            }
        }
    )
    assert nous.every() == [Nous("claude/a", 3, nous.DEFAULT, 0.0)]


def test_edges_written_by_hand_under_a_plain_on_are_read_and_kept() -> None:
    at = settings.where()
    at.parent.mkdir(parents=True)
    at.write_text(
        "nous:\n"
        "  smart:\n"
        "    graph:\n"
        "      start: first\n"
        "      nodes:\n"
        "        first: {use: claude/a, on: {spent: other, '*': cheap}}\n"
        "        other: {use: codex/b, next: cheap}\n"
        "        cheap: {use: grok/c}\n",
        encoding="utf-8",
    )
    graph = Graph(
        "first",
        (
            Node("first", use="claude/a", on=(("spent", "other"), (ANY, "cheap"))),
            Node("other", use="codex/b", on=((ANY, "cheap"),)),
            Node("cheap", use="grok/c"),
        ),
    )
    assert [(one.name, one.graph) for one in nous.every()] == [("smart", graph)]
    nous.retrying("grok/c", 1, "constant", 0)
    assert list(settings.read()["nous"]) == ["smart", "grok/c"]


def test_an_unreadable_file_is_nothing_and_refuses_a_write() -> None:
    at = settings.where()
    at.parent.mkdir(parents=True)
    at.write_text("nous: [unclosed\n", encoding="utf-8")
    assert nous.every() == []
    with pytest.raises(OSError, match="cannot be read"):
        nous.then("claude/a", ["codex/b"])


@pytest.mark.parametrize(
    ("policy", "waits"),
    [
        ("none", [0, 0, 0, 0, 0]),
        ("constant", [0, 1, 1, 1, 1]),
        ("linear", [0, 1, 2, 3, 4]),
        ("exponential", [0, 1, 2, 4, 8]),
        ("fibonacci", [0, 1, 1, 2, 3]),
    ],
)
def test_waits(policy: str, waits: list[float]) -> None:
    assert [nous.waits(policy, attempt) for attempt in range(1, 6)] == waits


def test_jitter_waits_anywhere_up_to_the_exponential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def highest(_low: float, high: float) -> float:
        return high

    monkeypatch.setattr(random, "uniform", highest)
    assert [nous.waits("exponential-jitter", one) for one in range(1, 6)] == [
        0,
        1,
        2,
        4,
        8,
    ]
    assert nous.waits("exponential-jitter", 10**6) == nous.CEILING


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _walked(
    root: str, faults: dict[str, str], *, memo: dict[str, str] | None = None
) -> list[str]:
    """Every step a walk takes, each concrete nous failing with the fault given for it."""
    clock = _Clock()
    walk = nous.Walk(root, memo=memo, clock=clock)
    steps: list[str] = []
    step = walk.next()
    while step is not None:
        if isinstance(step, Wait):
            clock.now += step.seconds
            steps.append(f"wait {step.seconds:.0f}")
            step = walk.next()
            continue
        assert isinstance(step, Run)
        steps.append(step.nous)
        if step.nous not in faults:
            walk.landed()
            break
        step = walk.next(faults[step.nous])
    return steps


def test_a_nous_with_nothing_written_is_one_step() -> None:
    assert _walked("claude/a", {"claude/a": ""}) == ["claude/a"]


def test_a_concrete_nous_walks_its_then_and_its_then_walks_on() -> None:
    nous.then("claude/a", ["codex/b", "grok/c"])
    nous.then("codex/b", ["kimi/d"])
    assert _walked("claude/a:high", {"claude/a:high": "", "codex/b": ""}) == [
        "claude/a:high",
        "codex/b",
        "kimi/d",
    ]


def test_edges_follow_the_fault() -> None:
    nous.put(Nous("smart", graph=_smart()))
    failing = {"claude@team/a": "spent", "claude@work/a": "spent"}
    # The heavier first where both are as busy, then the other, then the edge for `spent`.
    assert _walked("smart", failing) == ["claude@team/a", "claude@work/a", "codex/b"]
    failing = dict.fromkeys(failing, "refused")
    assert _walked("smart", failing)[2:] == ["grok/c"]


def test_a_balance_node_tries_spread_members_and_keeps_what_answered() -> None:
    nous.put(
        Nous(
            "pool",
            graph=Graph(
                "p",
                (
                    Node(
                        "p",
                        balance="round-robin",
                        among=(("kimi/x", 1), ("opencode/y", 1)),
                        spread=1,
                    ),
                ),
            ),
        )
    )
    first = _walked("pool", {"kimi/x": "", "opencode/y": ""})
    assert len(first) == 1
    memo: dict[str, str] = {}
    landed = _walked("pool", {}, memo=memo)
    assert memo == {"pool>p": landed[0]}
    for _ in range(3):
        assert _walked("pool", {}, memo=memo) == landed


def test_a_virtual_nous_is_walked_again_as_its_envelope_says() -> None:
    nous.put(Nous("v", tries=2, policy="constant", graph=nous.chain(["kimi/x"])))
    assert _walked("v", {"kimi/x": "dropped"}) == [
        "kimi/x",
        "wait 1",
        "kimi/x",
        "wait 1",
        "kimi/x",
    ]
    assert _walked("v", {"kimi/x": "refused"}) == ["kimi/x"]
    nous.put(
        Nous("v", tries=5, policy="constant", timeout=1.5, graph=nous.chain(["kimi/x"]))
    )
    assert _walked("v", {"kimi/x": "dropped"}) == ["kimi/x", "wait 1", "kimi/x"]


def test_a_nous_skipped_past_a_timeout_fails_with_the_fault_before_it() -> None:
    inner = Graph(
        "a",
        (
            Node("a", use="claude/a", on=(("throttled", "b"),)),
            Node("b", use="claude/b", on=(("throttled", "c"),)),
            Node("c", use="claude/c"),
        ),
    )
    nous.put(Nous("v", tries=3, policy="constant", timeout=15, graph=inner))
    _skipped_past_fifteen_seconds()
    late = "claude/never-begun"
    pool = Node("c", balance="round-robin", among=((late, 1), ("claude/d", 1)))
    nous.put(
        Nous(
            "v",
            tries=3,
            policy="constant",
            timeout=15,
            graph=Graph("a", (*inner.nodes[:2], pool)),
        )
    )
    _skipped_past_fifteen_seconds()
    # A member that was never begun was not rate-limited: it is still the first one picked.
    among = ((late, 1), ("claude/e", 1))
    nous.put(Nous("next", graph=Graph("n", (Node("n", balance="cost", among=among),))))
    assert _walked("next", {}) == [late]


def _skipped_past_fifteen_seconds() -> None:
    outer = Graph(
        "x", (Node("x", use="v", on=(("throttled", "y"),)), Node("y", use="codex/o"))
    )
    nous.put(Nous("p", graph=outer))
    clock = _Clock()
    walk = nous.Walk("p", clock=clock)
    steps: list[str] = []
    step = walk.next()
    while isinstance(step, Run):
        steps.append(step.nous)
        clock.now += 10  # ten seconds a turn, so the third is past v's fifteen
        step = walk.next("throttled")
    # claude/c is never begun, and v fails `throttled` as its last turn did: p's edge is taken.
    assert step is None
    assert steps == ["claude/a", "claude/b", "codex/o"]


def test_a_throttled_virtual_nous_waits_at_least_the_throttled_wait() -> None:
    nous.put(Nous("v", tries=1, policy="none", graph=nous.chain(["kimi/x"])))
    assert _walked("v", {"kimi/x": "throttled"}) == ["kimi/x", "wait 30", "kimi/x"]


def test_a_virtual_nous_nobody_wrote_down_fails_where_it_is_named() -> None:
    nous.put(Nous("v", graph=nous.chain(["kimi/x"])))
    _hand_written({"nous": {"v": {"graph": ["ghost", "kimi/x"]}}})
    assert _walked("v", {}) == ["kimi/x"]


def _last(members: Sequence[nous.Member]) -> str:
    return members[-1].name


@pytest.mark.parametrize(
    ("strategy", "expect"),
    [
        ("cost", "opencode/cost-y"),
        ("least-busy", "kimi/least-busy-x"),
        ("latency", "kimi/latency-x"),
        ("mine", "grok/mine-z"),
    ],
)
def test_strategies_pick_by_what_they_say(
    strategy: str, expect: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    nous.strategy("mine", "the last one", _last)
    x, y, z = f"kimi/{strategy}-x", f"opencode/{strategy}-y", f"grok/{strategy}-z"
    priced = {f"{strategy}-x": 9.0, f"{strategy}-y": 1.0}

    def price(model: str) -> prices.Price | None:
        if model not in priced:
            return None
        return prices.Price(model, "", {"input": priced[model], "output": 0.0})

    monkeypatch.setattr(prices, "price", price)
    nous.started([y])
    nous.finished([z], 5.0)
    try:
        nous.put(
            Nous(
                "pool",
                graph=Graph(
                    "p", (Node("p", balance=strategy, among=((x, 1), (y, 1), (z, 1))),)
                ),
            )
        )
        assert _walked("pool", {})[0] == expect
    finally:
        nous.finished([y], 0.0)


def test_a_turn_at_a_member_that_is_a_backend_is_counted_once() -> None:
    plain, inner = "kimi/counted-once", "opencode/counted-inside"
    nous.put(Nous("wrapped", graph=nous.chain([inner])))
    among = ((plain, 1), ("wrapped", 1))
    nous.put(
        Nous("pool", graph=Graph("p", (Node("p", balance="least-busy", among=among),)))
    )
    taken: list[tuple[str, ...]] = []
    try:
        for _ in range(3):
            walk = nous.walk("pool")
            step = walk.next()
            assert isinstance(step, Run)
            taken.append((*walk.picks(), step.nous))
            nous.started(taken[-1])
        # One turn at each member is a tie, which the member written first wins.
        assert [names[0] for names in taken] == [plain, "wrapped", plain]
    finally:
        for names in taken:
            nous.finished(names, 0.0, 100)
    nous.put(Nous("pool", graph=Graph("p", (Node("p", balance="usage", among=among),))))
    nous.finished(("wrapped", inner), 0.0, 150)
    # 200 tokens over two turns at the backend, 250 over two at the other.
    assert _walked("pool", {})[0] == plain


def test_a_member_that_was_rate_limited_is_picked_last() -> None:
    hot, cold = "kimi/rate-limited", "opencode/cool"
    nous.finished([hot], 1.0, fault="throttled")
    among = ((hot, 1), (cold, 1))
    nous.put(Nous("pool", graph=Graph("p", (Node("p", balance="cost", among=among),))))
    assert _walked("pool", {cold: "dropped"}) == [cold, hot]


def test_a_member_that_answered_past_a_rate_limit_inside_it_keeps_its_session() -> None:
    first, second, other = "kimi/inner-hot", "kimi/inner-cool", "opencode/outside"
    nous.put(Nous("chain", graph=nous.chain([first, second])))
    among = (("chain", 1), (other, 1))
    nous.put(Nous("pool", graph=Graph("p", (Node("p", balance="cost", among=among),))))
    memo: dict[str, str] = {}
    walk = nous.walk("pool", memo=memo)
    assert walk.next() == Run(first, None)
    nous.finished((*walk.picks(), first), 1.0, fault="throttled")
    assert walk.next("throttled") == Run(second, None)
    nous.finished((*walk.picks(), second), 1.0)
    walk.landed()
    assert memo == {"pool>p": "chain"}
    assert _walked("pool", {first: "dropped"}, memo=memo) == [first, second]


def test_a_member_that_was_rate_limited_through_and_through_is_picked_last() -> None:
    first, second, other = "kimi/all-hot-a", "kimi/all-hot-b", "opencode/spare"
    nous.put(Nous("spent-chain", graph=nous.chain([first, second])))
    among = (("spent-chain", 1), (other, 1))
    nous.put(Nous("pool", graph=Graph("p", (Node("p", balance="cost", among=among),))))
    memo = {"pool>p": "spent-chain"}
    faults = {first: "throttled", second: "spent", other: "dropped"}
    assert _walked("pool", faults, memo=memo) == [first, second, other]
    assert _walked("pool", {}, memo=memo) == [other]


def test_a_strategy_of_ones_own_cannot_take_a_built_in_name() -> None:
    with pytest.raises(ValueError, match="cannot name"):
        nous.strategy("shuffle", "", _last)
