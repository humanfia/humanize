"""The fake `claude` the composed-layers tests run, and the sandbox it is run in.

`tests/integration/runtime/test_together.py` and `tests/system/runtime/test_together.py` are
the two halves of one subject -- whether the layers fit when a flow drives real agent objects
-- split because one half needs a kernel that will hand over a tracee and the other does not.
They drive the same fake CLI, and a fake CLI written down twice is a streaming protocol that
gets fixed in one copy.

Here rather than in one of the two conftests because neither is the other's parent, and a
conftest reaches only downwards. Each of them imports `sandbox` from here instead, which is
what puts it where pytest looks; imported into a test module directly it would be shadowed by
the very parameter that names it.
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

#: A `claude --print` speaking the streaming protocol: it writes the transcript its session id
#: names, works, and answers, once per turn written to it.
FAKE = """
import datetime, json, os, pathlib, re, sys

flags = dict(zip(sys.argv, sys.argv[1:]))  # every flag paired with what follows it
cwd = pathlib.Path.cwd()
taken = flags.get("--session-id") or flags["--resume"]
print(json.dumps({"type": "system", "session_id": taken}), flush=True)
path = (
    pathlib.Path(os.environ["CLAUDE_CONFIG_DIR"])
    / "projects"
    / re.sub(r"[^a-zA-Z0-9]", "-", str(cwd))
    / f"{taken}.jsonl"
)
path.parent.mkdir(parents=True, exist_ok=True)
for line in sys.stdin:
    now = datetime.datetime.now(datetime.UTC)
    said = json.loads(line)["message"]["content"][0]["text"]
    with pathlib.Path("landed.txt").open("a") as landed:  # the work, wherever the workspace is
        landed.write(taken)
    with path.open("a") as trajectory:
        trajectory.write(
            "".join(
                json.dumps(record | {"cwd": str(cwd), "sessionId": taken}) + "\\n"
                for record in (
                    {
                        "type": "user",
                        "timestamp": now.isoformat(),
                        "message": {"role": "user", "content": said},
                    },
                    {
                        "type": "assistant",
                        "timestamp": (now + datetime.timedelta(seconds=1)).isoformat(),
                        "requestId": taken,
                        "effort": flags["--effort"],
                        "message": {
                            "id": taken,
                            "model": flags["--model"],
                            "content": [{"type": "text", "text": "done"}],
                        },
                    },
                )
            )
        )
    print(json.dumps({"type": "result", "result": "done"}), flush=True)
"""


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Puts a fake `claude` on PATH, hides the real agent homes, and returns the workspace."""
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{FAKE}")
    fake.chmod(0o755)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    for variable in ("CODEX_HOME", "KIMI_CODE_HOME"):
        monkeypatch.delenv(variable, raising=False)  # neither has a home under our HOME
    monkeypatch.chdir(workspace)
    return workspace
