"""The runtime reads structured answers through coganchor's Markdown block reader."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from hmz.runtime.flowing.harnessing import read_shape


class Answer(BaseModel):
    value: int
    note: str = ""


@pytest.mark.parametrize(
    ("opening", "closing"),
    [
        ("```JSON", "```"),
        ("```jsonc", "```"),
        ("``` json", "```"),
        ("~~~json", "~~~"),
        ("````json", "````"),
    ],
)
def test_the_first_valid_block_wins(opening: str, closing: str) -> None:
    said = (
        f'Result:\n{opening}\n{{"value": 1}}\n{closing}\n'
        'Previous result:\n```json\n{"value": 2}\n```'
    )
    assert read_shape(said, Answer) == Answer(value=1)


def test_prose_braces_do_not_hide_a_valid_fenced_answer() -> None:
    said = 'I set {value}:\n```JSON\n{"value": 1}\n```'
    assert read_shape(said, Answer) == Answer(value=1)


def test_backticks_inside_json_do_not_close_a_longer_fence() -> None:
    said = 'The {result}:\n````json\n{"value": 1, "note": "```"}\n````'
    assert read_shape(said, Answer) == Answer(value=1, note="```")


def test_an_invalid_block_is_skipped() -> None:
    said = '```JSON\n{"note": "missing value"}\n```\n~~~json\n{"value": 2}\n~~~'
    assert read_shape(said, Answer) == Answer(value=2)
