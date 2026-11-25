"""The pictures of `docs/user/command-line.md`: `hmz exec` and `hmz chat` as a script runs them.

Each picture is a command line and what a terminal showed of it: a flow run to its end, the
same run with its two streams sent apart, its events read with `jq`, a line refused before
anything started, a run stopped by a signal, one chat turn, and the chats listed. Run it by
naming it: `uv run pytest tests/system/docs/test_docs_user_command_line.py`.

A line that needs a shell -- a redirect, `$?`, a signal sent -- is run as `sh -c '...'`, which
is what the picture shows typed.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "user-command-line"

_TASK = "Add a discount code to checkout"

_ANSWER = "Checkout takes a discount code now: WELCOME10 is 10% off. All 6 tests pass."

#: The line the page runs, without its task.
_EXEC = f"hmz exec -f goal -a worker={AGENT} -p budget.output_tokens=20000"

_ASK = "What does charge() do with an empty cart?"

_SAID = "charge() raises ValueError for an empty cart, before any total is worked out."


def _worked(world: World, *, after: float = 0.8) -> None:
    """Scripts the agent: it runs the tests, then says what it did."""
    world.says(
        {
            "discount": {
                "text": _ANSWER,
                "tools": [
                    {
                        "name": "Bash",
                        "input": {"command": "pytest -q"},
                        "result": "6 passed in 0.21s",
                        "takes": 0.8,
                    }
                ],
                "after": after,
            }
        }
    )


def test_a_flow_is_run_to_its_end(world: World) -> None:
    _worked(world)
    reel = shots.Reel(f"{_PAGE}-exec")
    reel.cli([*_EXEC.split(), _TASK], rows=9, hold=4.0)
    reel.save()


def test_the_answer_and_the_progress_go_apart(world: World) -> None:
    _worked(world)
    shots.cli(
        [
            "sh",
            "-c",
            (
                f'{_EXEC} "{_TASK}" > answer.txt 2> run.log;'
                ' echo "exit status $?"; cat answer.txt'
            ),
        ],
        f"{_PAGE}-streams",
    )


def test_the_events_are_read_by_a_program(world: World) -> None:
    _worked(world)
    with (world.workspace / "events.ndjson").open("wb") as events:
        ran = subprocess.run(
            [*_EXEC.split(), "--json", _TASK],
            cwd=world.workspace,
            stdout=events,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=300,
        )
    assert ran.returncode == 0, ran.stderr
    shots.cli(
        ["jq", "-c", "{kind, cli, text}", "events.ndjson"],
        f"{_PAGE}-json",
        columns=100,
    )


def test_a_line_with_no_budget_is_refused(world: World) -> None:
    shots.cli(
        [
            "sh",
            "-c",
            f'hmz exec -f goal -a worker={AGENT} "{_TASK}"; echo "exit status $?"',
        ],
        f"{_PAGE}-refused",
    )


def test_a_signal_stops_the_run(world: World) -> None:
    _worked(world, after=30)
    shots.cli(
        [
            "sh",
            "-c",
            (
                f'{_EXEC} "{_TASK}" & sleep 5; kill -TERM $!; wait $!;'
                ' echo "exit status $?"'
            ),
        ],
        f"{_PAGE}-signal",
    )


def test_one_chat_turn_and_the_chats_listed(world: World) -> None:
    world.says({"charge()": {"text": _SAID, "after": 0.5}})
    shots.cli(["hmz", "chat", "start", "-a", AGENT, _ASK], f"{_PAGE}-chat")
    shots.cli(["hmz", "chat", "list"], f"{_PAGE}-chat-list")
