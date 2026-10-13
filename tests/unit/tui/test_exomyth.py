"""`hmz.tui.exomyth`: an epic's timeline read for drawing, drawn a row at a time, and weighed."""

from __future__ import annotations

from typing import Any

import pytest
from textual.content import Content

from hmz.runtime.tracing.timeline import VERSION
from hmz.tui.exomyth import (
    Flamed,
    Laid,
    Slice,
    bar,
    described,
    flamed,
    icicle,
    listed,
    portrayed,
    ruler,
    sliced,
    spaced,
    summed,
)

_STRINGS = [
    "",
    "chat",
    "flows",
    "main · s1",
    "main",
    "flow",
    "session",
    "turn",
    "llm",
    "tool",
    "Bash: ls",
    "think",
    "claude-x",
    "agent · s2",
    "threads",
    "NeiKos",
    "coder",
]


def _track(
    process: int, name: int, first: int, *spans: tuple[int, ...]
) -> dict[str, Any]:
    """A track of spans, each `(start, dur, depth, cat, name[, in, out])`."""
    columns: dict[str, list[int]] = {
        key: []
        for key in ("start", "dur", "depth", "cat", "name", "model", "in", "out")
    }
    for start, dur, depth, cat, called, *tokens in spans:
        for key, value in zip(
            ("start", "dur", "depth", "cat", "name"),
            (start, dur, depth, cat, called),
            strict=True,
        ):
            columns[key].append(value)
        held = tokens or [0, 0]
        columns["model"].append(12 if tokens else 0)
        columns["in"].append(held[0])
        columns["out"].append(held[1])
    return {
        "process": process,
        "name": name,
        "first": first,
        "count": len(spans),
        "depths": max((one[2] for one in spans), default=-1) + 1,
        "spans": columns,
    }


def _document(**changed: Any) -> dict[str, Any]:
    """An epic of a flow, a session under it, and a sub-agent under that."""
    tracks = [
        _track(0, 2, 0, (0, 1000, 0, 5, 1)),
        _track(
            1,
            4,
            1,
            (0, 800, 0, 6, 3),
            (0, 800, 1, 7, 7),
            (100, 200, 2, 8, 11, 50, 7),
            (300, 400, 2, 9, 10),
        ),
        _track(2, 4, 5, (500, 100, 0, 9, 10)),
    ]
    document: dict[str, Any] = {
        "version": VERSION,
        "layout": "abc",
        "epic": "e",
        "origin": 0.0,
        "live": False,
        "strings": _STRINGS,
        "processes": [
            {
                "id": 0,
                "kind": "flow",
                "name": 1,
                "parent": -1,
                "tracks": [0],
                "key": "epic:e",
            },
            {
                "id": 1,
                "kind": "session",
                "name": 3,
                "parent": 0,
                "tracks": [1],
                "key": "claude:s1",
                "agent": 15,
                "role": 16,
                "start": 0,
                "end": 800,
            },
            {
                "id": 2,
                "kind": "session",
                "name": 13,
                "parent": 1,
                "tracks": [2],
                "key": "claude:s2",
                "agent": 15,
                "label": 16,
            },
        ],
        "tracks": tracks,
        "spawns": {"span": [], "process": []},
        "summary": {"start": 0, "end": 1000, "spans": 6},
    }
    document.update(changed)
    return document


def _plain(cells: list[Any]) -> str:
    return "".join(one.text for one in cells)


@pytest.mark.parametrize(
    ("us", "said"),
    [
        (0, "0s"),
        (12, "12µs"),
        (3500, "3.5ms"),
        (999_600, "1s"),
        (1_250_000, "1.25s"),
        (125_000_000, "2m05s"),
        (3_840_000_000, "1h04m"),
        (-2_000_000, "-2s"),
    ],
)
def test_a_stretch_of_time_is_said_short(us: float, said: str) -> None:
    assert spaced(us) == said


def test_a_document_of_another_version_is_refused() -> None:
    with pytest.raises(ValueError, match="version"):
        Laid(_document(version=VERSION + 1))


def test_each_process_is_a_row_per_lane_under_the_one_it_hangs_from() -> None:
    laid = Laid(_document())

    rows = laid.rows(set())

    assert [one.label for one in rows] == [
        "▾ chat",
        "  ▾ main · s1",
        "",
        "",
        "      agent · s2",
    ]
    assert [one.process for one in rows] == [0, 1, 1, 1, 2]
    assert [laid.lanes[one.lane].depth for one in rows] == [0, 0, 1, 2, 0]


def test_a_folded_process_is_one_row_and_hides_what_hangs_from_it() -> None:
    laid = Laid(_document())

    rows = laid.rows({1})

    assert [one.label for one in rows] == ["▾ chat", "  ▸ main · s1"]
    assert laid.folds(1)
    assert not laid.folds(2)


def test_a_span_is_found_by_its_track_lane_and_process() -> None:
    laid = Laid(_document())

    assert (laid.track_of(4), laid.process_of(4)) == (1, 1)
    assert laid.lanes[laid.lane_of(4)].depth == 2
    assert laid.lanes[laid.above(laid.lane_of(4))].depth == 1
    assert laid.parents(2) == [1, 0]


def test_a_span_is_found_again_where_it_is_once_the_epic_is_laid_out_again() -> None:
    laid = Laid(_document())
    place = laid.place(4)
    grown = _document()
    # A span more in the flow's track moves every id after it along by one.
    grown["tracks"][0] = _track(0, 2, 0, (0, 1000, 0, 5, 1), (10, 5, 1, 5, 1))
    for at, one in enumerate(grown["tracks"][1:], start=1):
        one["first"] = [2, 6][at - 1]

    assert place == ("claude:s1", 0, 2, 300)
    assert Laid(grown).placed(place) == 5
    assert Laid(grown).placed(("claude:gone", 0, 0, 0)) == -1
    assert Laid(grown).placed(("claude:s1", 0, 2, 301)) == -1


def test_spans_are_found_by_name_ignoring_case_in_order_of_start() -> None:
    laid = Laid(_document())

    assert laid.found("bash") == [4, 5]
    assert laid.found("nothing") == []


def test_a_bar_is_cut_to_the_eighth_and_says_its_name_where_it_fits() -> None:
    laid = Laid(_document())
    lane = laid.lanes[laid.lane_of(5)]  # the sub-agent's one tool, 500 to 600

    cells = bar(laid, lane, 0, 10, 100)

    assert _plain(cells)[50:60] == " Bash: ls "
    assert {one.how for one in cells[50:60]} == {"fill"}
    assert {one.span for one in cells[50:60]} == {5}
    assert cells[49].how == cells[60].how == ""

    shifted = bar(laid, lane, -5, 10, 100)  # half a cell later

    assert (shifted[50].text, shifted[50].how) == ("▌", "start")
    assert (shifted[60].text, shifted[60].how) == ("▌", "end")
    assert shifted[50].hue == "tool"


def test_a_bar_hard_against_the_one_before_starts_with_an_eighth_of_a_gap() -> None:
    laid = Laid(_document())
    lane = laid.lanes[laid.lane_of(3)]  # 100 to 300, then 300 to 700

    cells = bar(laid, lane, 0, 20, 40)

    assert (cells[15].text, cells[15].how, cells[15].span) == ("▏", "start", 4)
    assert (cells[5].text, cells[5].how) == (" ", "fill")


def test_spans_narrower_than_a_cell_are_one_cell() -> None:
    laid = Laid(_document())
    lane = laid.lanes[laid.lane_of(3)]  # 100 to 300 and 300 to 700

    cells = bar(laid, lane, 0, 1000, 4, chosen=4)

    assert [(one.text, one.how, one.span) for one in cells] == [
        ("▌", "tiny", 4),
        (" ", "", -1),
        (" ", "", -1),
        (" ", "", -1),
    ]


def test_a_span_of_no_length_at_the_start_of_the_window_is_drawn() -> None:
    laid = Laid(_document())
    lane = laid.lanes[laid.lane_of(5)]  # 500 to 600

    cells = bar(laid, lane, 600, 10, 4)

    assert [one.how for one in cells] == ["", "", "", ""]
    assert bar(laid, laid.lanes[laid.lane_of(0)], 1000, 10, 2)[0].how == ""

    instant = Laid(_document(tracks=[_track(0, 2, 0, (0, 0, 0, 5, 1))]))
    drawn = bar(instant, instant.lanes[0], 0, 10, 3)

    assert (drawn[0].text, drawn[0].how, drawn[0].span) == ("▌", "tiny", 0)


def test_a_name_too_long_for_its_bar_is_cut_with_an_ellipsis() -> None:
    laid = Laid(_document())
    lane = laid.lanes[laid.lane_of(5)]

    assert _plain(bar(laid, lane, 0, 20, 50))[25:30] == " Bas…"


def test_the_ruler_ticks_at_round_times_and_says_only_whole_ones() -> None:
    said = ruler(0, 100_000, 60)

    assert said.startswith("│0s")
    assert "│2s" in said
    assert len(said) == 60
    assert ruler(0, 100_000, 22).rstrip().endswith("│")


def _named(whole: Flamed) -> dict[str, Flamed]:
    return {one.name: one for one in whole.children}


def test_the_flame_is_each_agent_its_sessions_merged_then_its_spans_as_they_nest() -> (
    None
):
    laid = Laid(_document())

    whole = flamed(laid, 0, 1000)

    # The session and the sub-agent fill one agent's role: one stack, the flow's beside it.
    assert [(one.name, one.weight) for one in whole.children] == [
        ("chat", 1000),
        ("NeiKos (coder)", 900),
    ]
    agent = _named(whole)["NeiKos (coder)"]
    assert (agent.own, agent.count, agent.hue) == (800, 5, "~session")
    assert [(one.name, one.weight) for one in agent.children] == [
        ("turn", 800),
        ("Bash: ls", 100),
    ]
    assert [(one.name, one.hue) for one in agent.children[0].children] == [
        ("Bash: ls", "tool"),
        ("think", "llm"),
    ]


def test_sessions_apart_are_each_a_stack_of_their_own_under_their_agent() -> None:
    laid = Laid(_document())

    agent = _named(flamed(laid, 0, 1000, apart=True))["NeiKos (coder)"]

    assert [(one.name, one.weight) for one in agent.children] == [
        ("main · s1", 800),
        ("agent · s2", 100),
    ]
    assert agent.own == 0


def test_the_flame_weighs_only_what_is_inside_the_window() -> None:
    laid = Laid(_document())

    whole = flamed(laid, 550, 1000)

    agent = _named(whole)["NeiKos (coder)"]
    assert agent.weight == 300
    assert {one.name: one.weight for one in agent.children} == {
        "turn": 250,
        "Bash: ls": 50,
    }
    assert _named(whole)["chat"].weight == 450


@pytest.mark.parametrize(
    ("weight", "weighed"),
    [("in", 50), ("out", 7), ("count", 5)],
)
def test_the_flame_weighs_tokens_in_or_out_or_spans_where_asked(
    weight: str, weighed: int
) -> None:
    laid = Laid(_document())

    whole = flamed(laid, 0, 1000, weight=weight)

    assert _named(whole)["NeiKos (coder)"].weight == weighed
    if weight != "count":
        assert [(level, one.name) for level, one in listed(whole)] == [
            (0, "NeiKos (coder)"),
            (1, "turn"),
            (2, "think"),
        ]


def test_the_flame_is_drawn_a_level_a_row_each_stack_its_share_wide() -> None:
    laid = Laid(_document())
    whole = flamed(laid, 0, 1000)

    rows = icicle(whole, 19)

    assert len(rows) == 3
    assert [len(one) for one in rows] == [19, 19, 19]
    # The flow is a thousand of the nineteen hundred: ten cells of the nineteen.
    assert {one.span for one in rows[0][:10]} == {0}
    assert rows[0][0].how == "start"
    assert rows[0][0].hue == "~flow"
    assert all(one.hue == "~session" for one in rows[0][10:])


def test_nothing_weighed_draws_no_flame() -> None:
    laid = Laid(_document())

    rows = icicle(flamed(laid, 5000, 6000), 10)

    assert all(not one.how for row in rows for one in row)


def test_a_lane_of_nested_slices_on_any_process_is_drawn_and_weighed() -> None:
    # A flow sampled into a lane of its own: a call, and one inside it.
    document = _document()
    document["tracks"].append(_track(0, 14, 6, (0, 600, 0, 5, 4), (100, 200, 1, 5, 11)))
    document["processes"][0]["tracks"] = [0, 3]
    laid = Laid(document)

    rows = laid.rows(set())

    assert [one.label for one in rows[:3]] == ["▾ chat", "  threads", ""]
    assert _plain(bar(laid, laid.lanes[rows[2].lane], 0, 10, 100))[10:17] == " think "
    flow = _named(flamed(laid, 0, 1000))["chat"]
    assert [
        (one.name, [two.name for two in one.children]) for one in flow.children
    ] == [("main", ["think"])]


def test_slices_sum_every_name_in_the_stretch() -> None:
    laid = Laid(_document())

    slices = sliced(laid, 0, 1000)

    assert [one.name for one in slices] == [
        "chat",
        "main · s1",
        "turn",
        "Bash: ls",
        "think",
    ]
    assert slices[3] == Slice("Bash: ls", "tool", 2, 500, 500, 250, 100, 400, 400, 0, 0)
    # A turn's own time is what its model call and its tool leave of it; tokens are summed.
    assert (slices[2].own, slices[1].own) == (200, 0)
    assert (slices[4].ins, slices[4].outs) == (50, 7)


def test_a_range_is_summed_by_category() -> None:
    laid = Laid(_document())

    said = Content.from_markup(summed(laid, 0, 1000)).plain.splitlines()

    assert said[:3] == [
        "Range",
        "from 0s · to 1ms · lasted 1ms",
        "6 spans · 50 in · 7 out",
    ]
    assert said[3].split() == ["category", "spans", "time", "in", "out"]
    assert [one.split() for one in said[4:]] == [
        ["flow", "1", "1ms", "0", "0"],
        ["session", "1", "800µs", "0", "0"],
        ["turn", "1", "800µs", "0", "0"],
        ["llm", "1", "200µs", "50", "7"],
        ["tool", "2", "500µs", "0", "0"],
    ]


def test_a_process_pane_says_what_it_is_whose_and_when() -> None:
    laid = Laid(_document())

    said = Content.from_markup(portrayed(laid, 1)).plain

    assert said.splitlines() == [
        "main · s1",
        "session · claude:s1",
        "agent NeiKos · role coder",
        "parent chat",
        "start 0s · lasted 800µs · 1 track · 4 spans",
    ]


def test_a_spans_pane_says_what_it_is_where_it_is_and_what_it_carried() -> None:
    laid = Laid(_document())

    said = Content.from_markup(
        described(
            laid,
            {
                "id": 3,
                "process": 1,
                "track": 1,
                "start": 100,
                "dur": 200,
                "depth": 2,
                "cat": "llm",
                "name": "think",
                "at": "2026-10-12T09:30:00+00:00",
                "args": {"text": "a\nb", "n": [1, 2]},
            },
        )
    ).plain

    assert said.splitlines() == [
        "think",
        "llm · main · s1 · main · depth 2",
        "start 100µs · lasted 200µs · 2026-10-12T09:30:00+00:00",
        "claude-x · 50 in · 7 out",
        "text a b",
        "n [1, 2]",
    ]
