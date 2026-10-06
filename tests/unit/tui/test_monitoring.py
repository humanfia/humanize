"""`hmz.tui.monitoring`: the run drawn -- boxes, rows and the board -- as markup."""

from __future__ import annotations

import types
from typing import TYPE_CHECKING, cast

import pytest
from textual.content import Content

import hmz.runtime.flowing
from hmz.coganchor.agents import ANYONE, FLOW
from hmz.tui.monitor import Shape, Under
from hmz.tui.monitoring import (
    OUTWORLDER,
    BoardSeen,
    Drawn,
    Entry,
    Line,
    Placed,
    columns,
    declared_places,
    diagram,
    elsewhere,
    fleet,
    floated,
    listed_row,
    needs,
    place_key,
    place_row,
    session_row,
)

if TYPE_CHECKING:
    from hmz.runtime.flowing import EnvRole

_GIB = 1 << 30


def _plain(markup: str) -> str:
    """What a row reads as once its colours are taken off."""
    return Content.from_markup(markup).plain


def _shape(**changed: object) -> Shape:
    held: dict[str, object] = {"turns": {}, "working": frozenset(), "handovers": {}}
    held.update(changed)
    return Shape(**held)  # pyright: ignore[reportArgumentType]


def test_an_outworlders_node_is_read_under_its_own_prefix() -> None:
    assert OUTWORLDER == "outworlder:"


@pytest.mark.parametrize(
    ("placed", "key"),
    [
        (
            {"role": "ws", "kind": "ssh", "target": "box", "workdir": "/w"},
            "ws\x1fssh\x1fbox\x1f/w",
        ),
        ({"role": "ws", "kind": "local"}, "ws\x1flocal\x1f\x1f"),
        ({}, "\x1f\x1f\x1f"),
        ({"role": None, "kind": "docker", "extra": 1}, "\x1fdocker\x1f\x1f"),
    ],
)
def test_place_key_is_role_and_where(placed: dict[str, object], key: str) -> None:
    assert place_key(placed) == key


def test_a_worktree_of_one_role_is_a_place_of_its_own() -> None:
    one = place_key({"role": "ws", "kind": "local", "workdir": "/a"})
    two = place_key({"role": "ws", "kind": "local", "workdir": "/b"})

    assert one != two


def _role(
    cpu_count: int = 1, memory: int = 0, gpu_count: int = 0, gpu_memory: int = 0
) -> EnvRole:
    return cast(
        "EnvRole",
        types.SimpleNamespace(
            cpu_count=cpu_count,
            memory=memory,
            gpu_count=gpu_count,
            gpu_memory=gpu_memory,
        ),
    )


@pytest.mark.parametrize(
    ("role", "said"),
    [
        (_role(), ()),
        (_role(cpu_count=4), ("4 CPUs",)),
        (_role(memory=_GIB // 2), ("0.5 GiB memory",)),
        (_role(gpu_count=1), ("1 GPU",)),
        (
            _role(cpu_count=8, memory=16 * _GIB, gpu_count=2, gpu_memory=80 * _GIB),
            ("8 CPUs", "16 GiB memory", "2 GPUs", "80 GiB per GPU"),
        ),
    ],
)
def test_needs_says_what_a_role_asks_of_its_machine(
    role: EnvRole, said: tuple[str, ...]
) -> None:
    assert needs(role) == said


def test_declared_places_reads_a_flow_once(monkeypatch: pytest.MonkeyPatch) -> None:
    loads: list[str] = []
    envs = (_role(), _role(cpu_count=2))

    def resolved(flow: str) -> object:
        loads.append(flow)
        description = types.SimpleNamespace(envs=list(envs))
        return types.SimpleNamespace(describe=lambda: description)

    monkeypatch.setattr(hmz.runtime.flowing, "resolved", resolved)
    declared_places.cache_clear()

    assert declared_places("u15-flow") == envs
    assert declared_places("u15-flow") == envs
    assert loads == ["u15-flow"]


def test_a_flow_that_will_not_load_declares_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def resolved(flow: str) -> object:
        raise ValueError(flow)

    monkeypatch.setattr(hmz.runtime.flowing, "resolved", resolved)
    declared_places.cache_clear()

    assert declared_places("u15-broken") == ()


def test_the_board_holds_its_lines_in_the_order_said() -> None:
    board = BoardSeen(
        [
            {"key": "goal", "value": "ship it", "whose": FLOW, "unknown": 1},
            {"key": "note"},
        ],
        lambda key, value: None,
    )

    assert board.items() == [
        Line("goal", "ship it", whose=FLOW),
        Line("note", whose=ANYONE),
    ]
    assert board.held("note") == Line("note")
    assert board.held("nothing") is None


def test_the_board_asks_for_a_line_to_change_or_come_off() -> None:
    asked: list[tuple[str, str]] = []
    board = BoardSeen([], lambda key, value: asked.append((key, value)))

    board.put("goal", "ship it")
    board.drop("goal")

    assert asked == [("goal", "ship it"), ("goal", "")]
    assert board.items() == []


def test_the_board_hands_out_a_copy_of_its_lines() -> None:
    board = BoardSeen([{"key": "a"}], lambda key, value: None)

    board.items().clear()

    assert board.items() == [Line("a")]


@pytest.mark.parametrize(
    ("key", "label", "about"),
    [
        ("", "next", "name the entry, then say what it is"),
        ("goal", "save", "write the entry on the board; an empty one is taken off"),
    ],
)
def test_an_entry_names_a_line_first_unless_it_has_one(
    key: str, label: str, about: str
) -> None:
    entry = Entry(key, "", BoardSeen([], lambda key, value: None))

    [action] = entry.actions()

    assert entry.crumb() == "board entry"
    assert (action.key, action.label, action.about) == ("onward", label, about)


def test_a_node_and_a_place_default_to_saying_nothing() -> None:
    assert Drawn("a") == Drawn("a", "", "", working=False, reading=False, unread=False)
    assert Placed("k", "ws", "local").sessions == ()


def test_a_diagram_is_a_box_per_agent_in_order() -> None:
    drawn = [Drawn("builder", runs="claude · opus", working=True), Drawn("reviewer")]
    shape = _shape(
        turns={"builder": 1, "reviewer": 2},
        working=frozenset({"builder"}),
        handovers={("builder", "reviewer"): 2, ("reviewer", "builder"): 1},
        since={"builder": 75.0, "reviewer": 5.0},
        latest=("builder", "reviewer"),
        used={"reviewer": 1500},
    )

    first, second = diagram(drawn, shape, 80)

    plain = [_plain(line) for line in first]
    assert plain[0].strip().startswith("┌")
    assert "▸ ● builder" in plain[1]
    assert plain[1].rstrip().endswith("1m15s │")
    assert "claude · opus · 1 turn" in plain[2]
    assert plain[-1].strip().startswith("└")
    # The arrows say which way and how often, lit for the handover taken last.
    assert "↓ 2 · ↑ 1" in _plain(second[0])
    assert "$secondary" in second[0]
    assert "○ reviewer" in _plain(second[2])
    assert "idle 5s" in _plain(second[2])
    assert "2 turns · 1.5k tokens" in _plain(second[3])


def test_every_row_of_a_box_is_as_wide_as_the_last() -> None:
    drawn = [Drawn("x" * 200, runs="y" * 200)]

    [block] = diagram(drawn, _shape(), 60)

    assert len({len(_plain(line)) for line in block}) == 1
    assert "…" in _plain(block[2])


def test_two_agents_never_handed_between_are_joined_by_a_dotted_spine() -> None:
    _, second = diagram([Drawn("a"), Drawn("b")], _shape(), 80)

    assert _plain(second[0]).strip() == "┆"


def test_the_cursor_is_marked_beside_the_name_of_its_box() -> None:
    [block] = diagram([Drawn("a")], _shape(), 80, here="a")

    marked = [at for at, line in enumerate(block) if "$primary]❯" in line]
    assert marked == [1]


@pytest.mark.parametrize(
    ("drawn", "flag"),
    [
        (Drawn("a", reading=True), "reading"),
        (Drawn("a", unread=True), "unread"),
        (Drawn("a"), ""),
    ],
)
def test_a_box_says_whether_it_is_being_read(drawn: Drawn, flag: str) -> None:
    [block] = diagram([drawn], _shape(), 80)

    assert (flag in _plain(block[2])) if flag else "read" not in _plain(block[2])


def test_an_opened_agent_has_its_sessions_and_places_said() -> None:
    places = {"a": [Placed("k", "ws", "docker"), Placed("k2", "", "local")]}
    shape = _shape(under={"a": (Under("s", "sub"),)})

    [shut] = diagram([Drawn("a")], shape, 80, sessions={"a": 3}, places=places)
    [opened] = diagram([Drawn("a")], shape, 80, opened={"a"})

    assert "3 sessions" in _plain(shut[2])
    assert "▤ ws docker · ▤ local" in _plain(shut[3])
    assert any("sub" in line for line in shut)
    assert "▾" in _plain(opened[1])
    assert not any("sub" in line for line in opened)


def test_a_fleet_hangs_under_a_box_and_is_cut_when_long() -> None:
    under = [Under(f"s{at}", f"task {at}", working=at == 0) for at in range(6)]

    lines = [_plain(line) for line in fleet(under, 60)]

    assert lines[0] == "  ├╴◆ task 0"
    assert lines[1] == "  ├╴◇ task 1"
    assert len(lines) == 5
    assert lines[-1] == "  └╴◇ and 2 more"


def test_a_short_fleet_ends_its_branch_and_none_draws_nothing() -> None:
    assert [_plain(line) for line in fleet([Under("s", "only")], 60)] == ["  └╴◆ only"]
    assert fleet([], 60) == []


def test_a_session_row_hangs_under_its_agent() -> None:
    shape = _shape(
        turns={"a/1": 2},
        since={"a/1": 3.0},
        used={"a/1": 2000},
        under={"a/1": (Under("x", "sub"),)},
    )

    row = session_row(Drawn("a/1", working=True, reading=True), shape, 80, last=True)

    first, sub = (_plain(line) for line in row.splitlines())
    assert "└╴● a/1 · 2 turns · 2.0k tokens" in first
    assert first.rstrip().endswith("reading · 3s")
    assert sub.endswith("└╴◆ sub")


def test_a_session_row_is_called_by_the_last_part_of_its_name() -> None:
    row = session_row(Drawn("a/1", named="builder · first"), _shape(), 80)

    assert "├╴○ first" in _plain(row)
    assert "idle 0s" in _plain(row)


def test_a_place_row_says_its_role_and_where_it_is() -> None:
    place = Placed("k", "ws", "ssh", target="box", workdir="/w")

    assert _plain(place_row(place, 80)) == "     │   ▤ ws · ssh · box · /w"
    assert _plain(place_row(place, 80, last=True)).startswith("         ▤")
    assert "❯" in place_row(place, 80, here=True)


def test_the_list_has_its_columns_named() -> None:
    said = _plain(columns(120))

    for name in ("node", "runs · where", "turns", "time", "tokens"):
        assert name in said


def test_a_listed_row_puts_each_figure_in_its_column() -> None:
    row = _plain(
        listed_row(
            120,
            mark="●",
            named="builder",
            what="claude · opus",
            turns="3 turns",
            clock="1m00s",
            tokens="1.2k",
            working=True,
            fold="▸",
            flag=("unread", "$secondary"),
        )
    )

    assert row.startswith("   ▸ ● builder unread")
    assert row.endswith("3 turns       1m00s      1.2k")
    assert len(row) == len(_plain(columns(120)))


def test_a_listed_row_cuts_a_long_name() -> None:
    row = _plain(
        listed_row(
            120,
            mark="○",
            named="n" * 50,
            what="",
            turns="",
            clock="",
            tokens="",
            working=False,
        )
    )

    assert "n" * 22 + "…" in row
    assert "n" * 24 not in row


def test_floated_puts_whatever_is_working_first_and_keeps_order() -> None:
    nodes = [(False, "a"), (True, "b"), (False, "c"), (True, "d")]

    assert floated(nodes) == ["b", "d", "a", "c"]
    assert floated([]) == []


def test_elsewhere_says_the_handovers_no_arrow_was_drawn_for() -> None:
    drawn = [Drawn("a"), Drawn("b"), Drawn("c")]
    shape = _shape(
        handovers={("a", "b"): 1, ("a", "c"): 2, ("c", "zed"): 1, ("b", "c"): 4}
    )

    assert [_plain(line) for line in elsewhere(drawn, shape)] == [
        "a → c · ×2",
        "c → zed · ×1",
    ]


def test_a_one_after_another_flow_has_nothing_said_elsewhere() -> None:
    drawn = [Drawn("a"), Drawn("b")]

    assert elsewhere(drawn, _shape(handovers={("a", "b"): 3, ("b", "a"): 1})) == []
