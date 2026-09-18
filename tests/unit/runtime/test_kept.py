"""An agent as it goes into a file and comes back out of one.

Three answers apiece and two of them may be withheld: what an agent may do without being
asked, and whether it may search the web, are things a place may simply not have said. A file
that turned either silence into an answer would be the interface deciding, on somebody's
behalf and without saying so, what every agent it wrote down is allowed.
"""

from __future__ import annotations

from hmz.runtime.kept import Runs, read_back, written


def test_an_agent_nobody_narrowed_is_written_down_as_the_silence_it_is() -> None:
    """A rung nobody chose is a key that is not there, and comes back as no rung at all."""
    runs = Runs("claude/m:high")

    held = written(runs)

    assert "permission" not in held
    # And web search is written even so, because here the silence has to be told from a file
    # older than the question: a key that is there and empty is this run saying nobody was
    # asked, and no key at all is a file written before anybody could be.
    assert held["web_search"] is None

    back = read_back(held)

    assert back == runs
    assert back is not None
    assert back.permission == ""


def test_an_answer_somebody_gave_is_written_down_and_comes_back_as_itself() -> None:
    """Which is the whole of what the silence beside it is for: the two are different."""
    runs = Runs("claude/m:high", permission="read-only", web_search=False)

    held = written(runs)

    assert held["permission"] == "read-only"
    assert held["web_search"] is False
    assert read_back(held) == runs


def test_a_file_older_than_the_question_reads_as_what_every_agent_did_then() -> None:
    """Every agent of every flow searched the web, and none of them was ever asked."""
    older = read_back({"cli": "claude", "model": "m", "effort": "high"})

    assert older is not None
    assert older.web_search is True
    assert older.permission == ""
