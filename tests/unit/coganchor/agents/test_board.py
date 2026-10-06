"""`hmz.coganchor.agents.board`: the lines a flow and a person both write on."""

from __future__ import annotations

import pytest

from hmz.coganchor.agents.board import (
    ANYONE,
    FLOW,
    USER,
    WHOSE,
    Board,
    Item,
    Refused,
)


def test_whose_names_every_side() -> None:
    assert WHOSE == (ANYONE, USER, FLOW)


@pytest.mark.parametrize(
    ("whose", "by", "writable"),
    [
        (ANYONE, USER, True),
        (ANYONE, FLOW, True),
        (USER, USER, True),
        (USER, FLOW, False),
        (FLOW, FLOW, True),
        (FLOW, USER, False),
    ],
)
def test_an_item_is_writable_by_its_own_side(
    whose: str, by: str, writable: bool
) -> None:
    assert Item(key="k", whose=whose).writable(by) is writable


def test_an_item_defaults_to_anyones_line_written_by_the_flow() -> None:
    one = Item(key="k")
    assert (one.value, one.about, one.whose, one.by) == ("", "", ANYONE, FLOW)


def test_a_board_starts_with_what_it_was_given_in_order() -> None:
    board = Board([Item(key="b", value="2"), Item(key="a", value="1")])
    assert [one.key for one in board.items()] == ["b", "a"]
    assert board.get("a") == "1"


def test_get_falls_back_for_a_missing_line() -> None:
    board = Board()
    assert board.get("nope") == ""
    assert board.get("nope", "x") == "x"
    assert board.held("nope") is None


def test_put_makes_a_line_and_keeps_its_about_and_whose_on_rewrite() -> None:
    board = Board()
    made = board.put(" todo ", "one", about="what is left", whose=FLOW)
    assert made.key == "todo"
    assert (made.value, made.about, made.whose, made.by) == (
        "one",
        "what is left",
        FLOW,
        FLOW,
    )
    again = board.put("todo", "two")
    assert (again.value, again.about, again.whose) == ("two", "what is left", FLOW)
    assert board.held("todo") == again


def test_put_may_clear_the_about_and_change_whose() -> None:
    board = Board()
    board.put("k", "v", about="a")
    one = board.put("k", "w", about="", whose=USER)
    assert (one.about, one.whose) == ("", USER)


def test_put_records_which_side_wrote() -> None:
    board = Board()
    assert board.put("k", "v", by=USER).by == USER


@pytest.mark.parametrize("key", ["", "   "])
def test_put_refuses_an_unnamed_line(key: str) -> None:
    with pytest.raises(ValueError, match="named"):
        Board().put(key, "v")


def test_put_refuses_an_unknown_side() -> None:
    with pytest.raises(ValueError, match="not one of"):
        Board().put("k", "v", whose="nobody")


@pytest.mark.parametrize(("whose", "by"), [(USER, FLOW), (FLOW, USER)])
def test_the_other_sides_line_is_refused(whose: str, by: str) -> None:
    board = Board([Item(key="k", value="v", whose=whose)])
    with pytest.raises(Refused, match="k is"):
        board.put("k", "w", by=by)
    with pytest.raises(Refused):
        board.drop("k", by=by)
    with pytest.raises(Refused):
        board.moves("k", to="j", by=by)
    assert board.get("k") == "v"


def test_refused_is_a_permission_error() -> None:
    assert issubclass(Refused, PermissionError)


def test_drop_says_whether_there_was_a_line() -> None:
    board = Board([Item(key="k")])
    assert board.drop("k") is True
    assert board.drop("k") is False
    assert board.items() == ()


def test_moves_renames_in_place() -> None:
    board = Board([Item(key="a", value="1"), Item(key="b", value="2")])
    moved = board.moves("a", to=" c ", by=USER)
    assert (moved.key, moved.value, moved.by) == ("c", "1", USER)
    assert [one.key for one in board.items()] == ["c", "b"]
    assert board.held("a") is None


def test_moves_to_its_own_name_is_allowed() -> None:
    board = Board([Item(key="a", value="1")])
    assert board.moves("a", to="a").key == "a"


@pytest.mark.parametrize(
    ("key", "to", "error"),
    [("a", "", ValueError), ("a", "b", ValueError), ("x", "y", KeyError)],
)
def test_moves_refuses(key: str, to: str, error: type[Exception]) -> None:
    board = Board([Item(key="a"), Item(key="b")])
    with pytest.raises(error):
        board.moves(key, to=to)


def test_watchers_hear_every_move_and_a_failing_one_is_ignored() -> None:
    board = Board()
    heard: list[tuple[str, ...]] = []

    def broken(_: Board) -> None:
        raise RuntimeError

    board.watch(broken)
    board.watch(lambda b: heard.append(tuple(one.key for one in b.items())))
    board.put("a", "1")
    board.moves("a", to="b")
    board.drop("b")
    board.drop("b")  # nothing there: nobody is told
    assert heard == [("a",), ("b",), ()]
