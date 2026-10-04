"""Every `--help` reads at a glance: nothing in one runs past thirty words.

A flag's help says what it takes and what it defaults to, and a command's description and
epilog say what the command is in a sentence or two. Anything longer is reference, which is
`docs/reference/cli.md`'s to say -- a help that has to be scrolled is one nobody reads.

Every parser is found the way a person reaches it, through `hmz.cli.main`: whatever `COMMANDS`
and `INTERNAL` route is held to this without anybody remembering to add it. Only the anchor's
own two subcommands, which it routes by hand, are named here.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, NoReturn

import pytest

from hmz import cli

if TYPE_CHECKING:
    from collections.abc import Iterator

#: The most words a flag's help, a command's summary, a description or an epilog may run to.
LIMIT = 30

#: Every line that reaches a parser of its own.
ROUTES = [
    ["--help"],
    *([name] for name in cli.COMMANDS),
    *(["internal", name] for name in cli.INTERNAL),
    ["internal", "anchor", "serve"],
    ["internal", "anchor", "rendezvous"],
]


def _reached(
    route: list[str], monkeypatch: pytest.MonkeyPatch
) -> argparse.ArgumentParser:
    """The parser a line reaches, caught as it is asked to parse rather than parsing.

    Caught at `parse_known_args`, which every other way of parsing goes through.
    """
    reached: list[argparse.ArgumentParser] = []

    def parses(parser: argparse.ArgumentParser, *_: object) -> NoReturn:
        reached.append(parser)
        raise SystemExit(0)

    monkeypatch.setattr(argparse.ArgumentParser, "parse_known_args", parses)
    with pytest.raises(SystemExit):
        cli.main(route)
    (parser,) = reached
    return parser


def _prose(parser: argparse.ArgumentParser) -> Iterator[tuple[str, str]]:
    """Everything a parser's help says in words, each with what says it."""
    yield "description", parser.description or ""
    yield "epilog", parser.epilog or ""
    for action in parser._actions:
        yield (action.option_strings or [action.dest])[0], action.help or ""
        if isinstance(action, argparse._SubParsersAction):
            for command in action._choices_actions:
                yield command.dest, command.help or ""


@pytest.mark.parametrize("route", ROUTES, ids=" ".join)
def test_every_help_says_it_in_thirty_words_or_fewer(
    route: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    parser = _reached(route, monkeypatch)
    wordy = {
        said: len(words.split())
        for said, words in _prose(parser)
        if len(words.split()) > LIMIT
    }
    assert not wordy, f"{parser.prog}: over {LIMIT} words"
