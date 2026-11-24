"""The pictures of `docs/reference/events.md`: one event of the stream, and an epic's record.

A flow is run once with `hmz exec --json`; the pictures are what `jq` prints of the stream it
wrote and of the record the epic left in the home. Run it by naming it:
`uv run pytest tests/system/docs/test_docs_reference_events.py`.

The record is read from inside the epic's own directory, so the picture shows no path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from tests.system.docs import shots
from tests.system.docs.conftest import AGENT

if TYPE_CHECKING:
    from tests.system.docs.conftest import World

#: What every picture of the page is named after.
_PAGE = "reference-events"

_TASK = "Add a discount code to checkout"

_ANSWER = "Checkout takes a discount code now: WELCOME10 is 10% off. All 6 tests pass."

#: The line the page runs, without its task.
_EXEC = f"hmz exec -f goal -a worker={AGENT} -p budget.output_tokens=20000 --json"


def _ran(world: World) -> None:
    """Runs the flow once, its events written to `events.ndjson` in the project."""
    world.says(
        {
            "discount": {
                "text": _ANSWER,
                "tools": [
                    {
                        "name": "Bash",
                        "input": {"command": "pytest -q"},
                        "result": "6 passed in 0.21s",
                        "takes": 0.4,
                    }
                ],
                "after": 0.4,
            }
        }
    )
    with (world.workspace / "events.ndjson").open("wb") as events:
        ran = subprocess.run(
            [*_EXEC.split(), _TASK],
            cwd=world.workspace,
            stdout=events,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=300,
        )
    assert ran.returncode == 0, ran.stderr
    if kept := os.environ.get("HMZ_EVENTS_KEEP"):
        # For whoever writes the page: the stream and the record, to read whole.
        shutil.copy(world.workspace / "events.ndjson", kept)
        for record in (world.data / "epics").glob("*/*/epic*.jsonl"):
            shutil.copy(record, Path(kept) / record.name)


def test_the_stream_and_the_record(world: World) -> None:
    _ran(world)
    shots.cli(
        ["jq", "-c", "[.kind, .agent, .text[:48]]", "events.ndjson"],
        f"{_PAGE}-kinds",
        columns=92,
    )
    shots.cli(
        ["jq", 'select(.kind == "result")', "events.ndjson"],
        f"{_PAGE}-result",
        columns=92,
    )
    (record,) = (world.data / "epics").glob("*/*/epic.jsonl")
    shots.cli(
        ["jq", "-c", "del(.workspace, .agents, .budget, .name)", "epic.jsonl"],
        f"{_PAGE}-record",
        cwd=record.parent,
        columns=100,
    )
