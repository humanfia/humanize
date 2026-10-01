"""What a run has spent, said in four places on the monitor that must all say the same thing.

The readout over the prompt, the `Tokens` row under the graph, an agent's box and the row of
each of its sessions are one count of one run's tokens. Two sources feed them -- what the
backend reports of each turn, and the log the CLI writes as it goes -- and the readout is
the higher of the two, so a log read wrong is a readout that disagrees with every box under it.

Driven headlessly, against a `claude` that writes its transcript the way Claude Code does: a
row per block of a message, every one of them carrying the whole of the request's usage.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest

from hmz.tui import Humanize
from tests.integration.tui.test_app import up
from tests.stubs import written
from tests.tui.fixtures import ONE, set_up, until

if TYPE_CHECKING:
    from pathlib import Path

#: The model the fake answers as, on the transcript and in the turn's own result alike.
MODEL = "claude-haiku-4-5"

#: A `claude` that answers in two requests, each a message of two blocks -- its thinking and
#: then its words -- written to its transcript and said on stdout a block at a time, as the
#: real one does, every block carrying the whole usage of its request.
BLOCKS = """
import json, os, pathlib, sys

MODEL = "claude-haiku-4-5"
flags = dict(zip(sys.argv, sys.argv[1:]))
ident = flags["--session-id"]
under = pathlib.Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "-a-project"
under.mkdir(parents=True, exist_ok=True)
log = under / (ident + ".jsonl")
print(json.dumps({"type": "system", "session_id": ident}), flush=True)
for line in sys.stdin:
    total = {"inputTokens": 0, "outputTokens": 0, "cacheReadInputTokens": 0}
    for number, output in ((1, 300), (2, 40)):
        usage = {"input_tokens": 2, "output_tokens": output,
                 "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 0}
        total["inputTokens"] += 2
        total["outputTokens"] += output
        total["cacheReadInputTokens"] += 1000
        for block in ({"type": "thinking", "thinking": "hmm"},
                      {"type": "text", "text": "done"}):
            said = {"type": "assistant", "message": {
                "id": "msg_" + ident + str(number), "model": MODEL,
                "content": [block], "usage": usage}}
            with log.open("a") as stream:
                stream.write(json.dumps(said) + "\\n")
            print(json.dumps(said), flush=True)
    print(json.dumps({"type": "result", "result": "done",
                      "modelUsage": {MODEL: total}}), flush=True)
"""

#: What those two requests came to: two in, three hundred and forty out, two thousand read.
WHOLE = 2 * 2 + 300 + 40 + 2 * 1000


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hosting: None) -> Path:
    """Puts the fake `claude` on PATH, gives it a home of its own and works beside it."""
    del hosting
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{BLOCKS}")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.timeout(60)
async def test_the_readout_the_boxes_and_the_sessions_say_one_bill(
    workspace: Path,
) -> None:
    """A log written a block at a time is read as the requests it is, not the rows."""
    written(workspace, "flow", ONE)
    app = Humanize()
    async with app.run_test() as driver:
        set_up(app, "flow")
        await driver.press(*"start")
        await driver.press("enter")
        await until(lambda: (workspace / "said.txt").exists(), driver)
        # The log is read on a clock of its own, and the run ends with one more read of it.
        await until(lambda: ("read", MODEL) in app._monitor.totals, driver)
        assert app._monitor.totals[("read", MODEL)] == WHOLE

        said = await up(app, driver)
        monitor = app._monitor
        (spending,) = monitor.spending()

    assert "flow" in said
    assert spending.tokens == WHOLE
    assert sum(monitor.shape().used.values()) == WHOLE
    assert sum(monitor.shape(sessions=True).used.values()) == WHOLE
    # And the kinds, which are the same tokens again -- the cache written to being a column
    # Claude reports whether or not anything went on it.
    assert {one.kind: one.tokens for one in monitor.reckoning()} == {
        "input": 4,
        "output": 340,
        "cache_read": 2000,
        "cache_write": 0,
    }
