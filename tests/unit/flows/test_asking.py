"""`hmz.flows.asking`: the blocks of context an outworlder is shown, and their wire forms."""

from __future__ import annotations

import base64
import dataclasses
import json
from typing import Any, get_args

import pytest

from hmz.flows import Block, Chart, Code, Diff, Image, Json, Markdown, Table

PNG = b"\x89PNG\r\n\x1a\n"

#: One block of each kind, with nothing but what it must have.
BARE: dict[type, Block] = {
    Markdown: Markdown(text=""),
    Code: Code(text=""),
    Diff: Diff(patch=""),
    Table: Table(columns=(), rows=()),
    Image: Image(data=b"", mime="image/png"),
    Json: Json(value=None),
    Chart: Chart(spec={}),
}


@pytest.mark.parametrize(
    ("block", "form"),
    [
        (Markdown(text="**hi**"), {"kind": "markdown", "text": "**hi**"}),
        (
            Code(text="x = 1", language="python"),
            {"kind": "code", "text": "x = 1", "language": "python"},
        ),
        (Code(text="ls"), {"kind": "code", "text": "ls", "language": ""}),
        (Diff(patch="--- a\n+++ b\n"), {"kind": "diff", "patch": "--- a\n+++ b\n"}),
        (
            Table(columns=("name", "n"), rows=(("a", 1), ("b", 2))),
            {"kind": "table", "columns": ["name", "n"], "rows": [["a", 1], ["b", 2]]},
        ),
        (
            Image(data=PNG, mime="image/png", alt="a dot"),
            {
                "kind": "image",
                "mime": "image/png",
                "data": base64.b64encode(PNG).decode(),
                "alt": "a dot",
            },
        ),
        (Json(value={"a": [1, None]}), {"kind": "json", "value": {"a": [1, None]}}),
        (
            Chart(spec={"mark": "bar", "data": {"values": [{"x": 1}]}}),
            {"kind": "chart", "spec": {"mark": "bar", "data": {"values": [{"x": 1}]}}},
        ),
    ],
)
def test_each_block_has_its_wire_form(block: Block, form: dict[str, Any]) -> None:
    assert block.as_json() == form
    assert json.loads(json.dumps(block.as_json())) == form


@pytest.mark.parametrize(
    "block",
    [
        Markdown(text="t", title="Notes"),
        Code(text="t", title="main.py"),
        Diff(patch="p", title="the change"),
        Table(columns=(), rows=(), title="Runs"),
        Image(data=PNG, mime="image/png", title="Shot"),
        Json(value=1, title="Config"),
        Chart(spec={}, title="Progress"),
    ],
)
def test_a_title_goes_with_the_block_where_set(block: Block) -> None:
    assert block.as_json()["title"] == block.title


@pytest.mark.parametrize("kind", get_args(Block))
def test_no_title_is_sent_where_none_is_set(kind: type) -> None:
    assert BARE[kind].title == ""
    assert "title" not in BARE[kind].as_json()


@pytest.mark.parametrize("kind", get_args(Block))
def test_blocks_are_frozen_and_keyword_only(kind: type) -> None:
    assert all(one.kw_only for one in dataclasses.fields(kind))
    with pytest.raises(dataclasses.FrozenInstanceError):
        BARE[kind].title = "changed"  # pyright: ignore[reportAttributeAccessIssue]


def test_block_is_every_kind() -> None:
    assert set(get_args(Block)) == {Markdown, Code, Diff, Table, Image, Json, Chart}
    assert isinstance(Diff(patch=""), Block)


def test_a_row_must_fit_the_columns() -> None:
    with pytest.raises(ValueError, match="row 1 has 1 cells for 2 columns"):
        Table(columns=("a", "b"), rows=((1, 2), (3,)))


def test_an_image_is_at_most_four_mebibytes() -> None:
    Image(data=bytes(4 * 1024 * 1024), mime="image/png")
    with pytest.raises(ValueError, match="at most 4 MiB"):
        Image(data=bytes(4 * 1024 * 1024 + 1), mime="image/png")


def test_an_image_is_of_an_image_type() -> None:
    with pytest.raises(ValueError, match="not an image"):
        Image(data=b"%PDF", mime="application/pdf")


def test_a_charts_wire_form_is_a_copy_of_its_spec() -> None:
    spec = {"mark": "line"}
    form = Chart(spec=spec).as_json()
    form["spec"]["mark"] = "bar"
    assert spec == {"mark": "line"}
