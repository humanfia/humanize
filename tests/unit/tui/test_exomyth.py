"""`hmz.tui.exomyth`: an epic's timeline read for drawing, drawn a row at a time, and weighed."""

from __future__ import annotations

from typing import Any

import pytest
from textual.content import Content

from hmz.runtime.tracing.timeline import VERSION
from hmz.tui.exomyth import (
    Laid,
    bar,
    described,
    flamed,
    icicle,
    listed,
    ruler,
    spaced,
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
            },
            {
                "id": 2,
                "kind": "session",
                "name": 13,
                "parent": 1,
                "tracks": [2],
                "key": "claude:s2",
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


def test_the_flame_weighs_each_spans_own_time_in_the_window() -> None:
    laid = Laid(_document())

    whole = flamed(laid, 0, 1000)

    kinds = {one.name: one for one in whole.children}
    assert kinds["flow"].weight == 1000
    session = kinds["session"]
    cats = {one.name: (one.weight, one.count) for one in session.children}
    # The banner and the turn hold each other and the two below: only what is their own.
    assert cats == {"turn": (200.0, 1), "llm": (200.0, 1), "tool": (500.0, 2)}
    assert [one.name for one in whole.children] == ["flow", "session"]
    assert session.children[0].name == "tool"


def test_the_flame_weighs_only_what_is_inside_the_window() -> None:
    laid = Laid(_document())

    whole = flamed(laid, 550, 1000)

    session = next(one for one in whole.children if one.name == "session")
    assert {one.name: one.weight for one in session.children} == {
        "tool": 200.0,
        "turn": 100.0,
    }
    assert next(one for one in whole.children if one.name == "flow").weight == 450


def test_the_flame_weighs_tokens_where_asked() -> None:
    laid = Laid(_document())

    whole = flamed(laid, 0, 1000, tokens=True)

    assert [(one.name, one.weight) for one in whole.children] == [("session", 57)]
    assert [(level, one.name) for level, one in listed(whole)] == [
        (0, "session"),
        (1, "llm"),
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
