"""What humanize says about an agent nobody configured, which is nothing at all.

A run that names a model and an effort has said what it wants thought about and nothing about
what may be done. So humanize says nothing either: the CLI is started with no rung, no sandbox,
no approval policy, none of the flags that skip the asking and neither half of the web-search
switch, and answers all of those out of the settings whoever installed it already has. A run
nobody configured and that CLI's own headless mode, typed at a shell, are then the same run --
which is the promise, and the only place it can be read is a command line.

Here rather than beside each driver because the promise is about all of them at once. One
backend that went on sending a default of humanize's own would be exactly the setting nobody
chose, and none of that backend's own tests -- each written around a rung it was given -- would
have anything to say about it.
"""

from __future__ import annotations

import itertools
import sys
from typing import TYPE_CHECKING, Any, cast

import pytest

from hmz.coganchor.agents import DRIVEN, UNSAID

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

#: Every flag by which one of these CLIs is told what its agent may do or whether it may read
#: the internet, across all twelve of them. A command line carrying any of these is humanize
#: having answered a question nobody asked it. Written out rather than read off the drivers,
#: because a driver that stopped emitting a flag by forgetting it is the bug this is for.
_GATING = frozenset(
    {
        "--always-approve",
        "--approval-mode",
        "--auto",
        "--dangerously-skip-permissions",
        "--disable-web-search",
        "--disallowed-tools",
        "--disallowedTools",
        "--exclude-tools",
        "--force",
        "--permission-mode",
        "--permission-prompt-tool",
        "--sandbox",
        "--tools",
    }
)

#: The one `-c` key Codex is told about the web on, which is a word rather than a flag: the
#: flag before it is the same `-c` that carries every other override.
_SEARCHING = "tools.web_search="


def _table(driver: type) -> dict[str, Any]:
    """How one driver spells the rungs, as the table it looks them up in.

    Args:
      driver: The agent class that drives the backend.

    Returns:
      Its `_PERMITTED`, or nothing for a backend whose rung never reaches a table -- one with
      no ladder of its own, and one driven through another backend's driver.
    """
    return getattr(sys.modules[driver.__module__], "_PERMITTED", {})


def _rungs() -> frozenset[str]:
    """Every word any of these CLIs has for a rung, read off the tables that hold them.

    Read rather than listed because it is wanted for one thing only: `--mode` is two flags
    under one spelling -- agy's rung and pi's transport -- so it has to be read with the word
    after it, and what makes that word a rung is that some driver maps a rung onto it.
    """
    return frozenset(
        said
        for driver, _ in DRIVEN.values()
        for said in _table(driver).values()
        if isinstance(said, str)
    )


def _words(holder: object, named: str, *given: object) -> list[str]:
    """One command line this backend composes, or nothing where it composes none.

    Args:
      holder: The agent or the session, whichever holds the method.
      named: The method that composes it.
      given: What that method takes.

    Returns:
      Every word of it. A method answering with the command and what goes to its standard
      input is read for the command alone.
    """
    # What one of these composes: the words, or the words and what goes to the process's
    # standard input. Said here because it is read off whichever object has the method.
    composes = cast(
        "Callable[..., Sequence[str] | tuple[Sequence[str], str | None]] | None",
        getattr(holder, named, None),
    )
    if composes is None:
        return []
    made = composes(*given)
    return list(made[0] if isinstance(made, tuple) else made)


@pytest.mark.parametrize("backend", sorted(DRIVEN))
def test_a_backend_nobody_configured_is_started_as_the_bare_cli_would_be(
    backend: str,
) -> None:
    """The whole of what a default that says nothing is for, asked of every CLI there is.

    Every word humanize would put on a command line for such an agent, taken from wherever
    that backend composes one -- the app server it holds open, the process one turn runs in --
    together with the environment it would run in and the row its rung table answers with.
    None of it may be about permissions, and none of it about the web.
    """
    driver, config = DRIVEN[backend]
    try:
        agent = driver(config(model="m", effort="high"))
        session = agent.new()
    except (OSError, RuntimeError) as why:
        # An account rather than a setting: a backend that cannot be built without one says so
        # here rather than failing as though it had sent something.
        pytest.skip(f"{backend} cannot be started on this machine -- {why}")

    assert agent.config.permission == UNSAID  # the premise: nobody said anything
    assert agent.config.web_search is None

    argv = [
        *_words(agent, "_argv", ()),
        *_words(session, "_command"),
        *_words(session, "_turn", "hi"),
    ]
    environment: Mapping[str, str] = getattr(session, "_environment", dict)()

    assert not _GATING.intersection(argv)
    assert not [word for word in argv if word.startswith(_SEARCHING)]
    # Opencode and mimo carry their table in the environment rather than in argv, each under
    # its own name for the same variable.
    assert not [key for key in environment if key.endswith("_PERMISSION")]
    assert not [
        said
        for flag, said in itertools.pairwise(argv)
        if flag == "--mode" and said in _rungs()
    ]
    # And the rung table, since for the three backends whose rung reaches the CLI as a
    # parameter of a thread no command line of theirs would show it. Read with `.get`, because
    # a driver has two honest ways of saying nothing: hold a row for the silence that is empty,
    # which is what the app servers do, or keep the table to the four rungs and guard the
    # lookup, which is what Claude and qwen do. Either way there is nothing here to send.
    assert not _table(driver).get(agent.config.permission)
