"""What the core integration tests share: a stand-in `claude` on PATH, and a project to run in.

The stand-in speaks what `claude --print --input-format stream-json` speaks -- one process
held open per session, a JSON line per thing said each way -- and keeps each conversation
where the real one does, under `$CLAUDE_CONFIG_DIR/projects/`, so that humanize drives it as
it drives the real CLI. It answers a prompt as a model would be asked to:

- `fail: <words>` fails the turn saying the words;
- `/goal <words>` answers `goal met: <words>`;
- `silent` answers nothing;
- a turn asked for a JSON schema answers `{"done": true, "notes": "reviewed"}`;
- anything else is answered `did: <prompt>`, after writing the prompt into `landed.txt` in the
  directory it was started in -- the work, wherever the workspace is.

Every turn reports 10 input and 7 output tokens. Each start is written as one JSON line to
`standin.log` in its home, `$CLAUDE_CONFIG_DIR` -- its argv, its working directory and the
session it opened -- since that is where the fence humanize runs a CLI in lets it write.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

#: The model every line here runs the stand-in as.
MODEL = "claude-haiku-4-5"

#: What every line here names an agent as, after its role.
AGENT = f"claude/{MODEL}"

#: The output tokens every turn of the stand-in reports.
TOKENS = 7

CLAUDE = r"""
import json, os, pathlib, re, sys, uuid

argv = sys.argv[1:]
flags = {}
at = 0
while at < len(argv):
    word = argv[at]
    if word.startswith("--") and at + 1 < len(argv) and not argv[at + 1].startswith("--"):
        flags[word] = argv[at + 1]
        at += 2
    else:
        flags[word] = True
        at += 1
if "--version" in flags:
    print("2.1.0 (Claude Code)")
    sys.exit(0)

home = pathlib.Path(os.environ.get("CLAUDE_CONFIG_DIR") or pathlib.Path.home() / ".claude")
projects = home / "projects" / re.sub(r"[^a-zA-Z0-9]", "-", os.getcwd())
projects.mkdir(parents=True, exist_ok=True)
model = flags.get("--model", "m")
schema = flags.get("--json-schema")


def out(said):
    print(json.dumps(said), flush=True)


if "--resume" in flags:
    was = flags["--resume"]
    if not (projects / f"{was}.jsonl").exists():
        out({"type": "result", "subtype": "error_during_execution", "is_error": True,
             "result": f"No conversation found with session ID: {was}"})
        sys.exit(1)
    session = str(uuid.uuid4()) if flags.get("--fork-session") else was
    if session != was:
        (projects / f"{session}.jsonl").write_text((projects / f"{was}.jsonl").read_text())
else:
    session = flags["--session-id"]
transcript = projects / f"{session}.jsonl"
with (home / "standin.log").open("a") as log:
    log.write(json.dumps({"argv": argv, "cwd": os.getcwd(), "session": session}) + "\n")
spent = {"in": 0, "out": 0}


def answer(said):
    if said.startswith("fail: "):
        return None
    if said.startswith("/goal "):
        return "goal met: " + said[len("/goal "):]
    if said == "silent":
        return ""
    if schema:
        return json.dumps({"done": True, "notes": "reviewed"})
    with pathlib.Path("landed.txt").open("a") as landed:
        landed.write(said + "\n")
    return "did: " + said


for line in sys.stdin:
    said = json.loads(line)
    if said.get("type") != "user":
        continue
    text = said["message"]["content"][0]["text"]
    out({"type": "system", "subtype": "init", "session_id": session, "model": model})
    with transcript.open("a") as kept:
        kept.write(json.dumps({"type": "user", "sessionId": session, "cwd": os.getcwd(),
                               "message": {"role": "user", "content": text}}) + "\n")
    answered = answer(text)
    if answered is None:
        out({"type": "result", "subtype": "error_during_execution", "is_error": True,
             "session_id": session, "result": text[len("fail: "):]})
        sys.exit(1)
    spent["in"] += 10
    spent["out"] += TOKENS
    out({"type": "assistant", "message": {"id": str(uuid.uuid4()), "model": model,
         "content": [{"type": "text", "text": answered or " "}],
         "usage": {"input_tokens": 10, "output_tokens": TOKENS}}})
    out({"type": "result", "subtype": "success", "is_error": False, "session_id": session,
         "result": answered, "modelUsage": {model: {"inputTokens": spent["in"],
                                                     "outputTokens": spent["out"]}}})
""".replace("TOKENS", str(TOKENS))


def install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Makes the stand-in the only `claude` on PATH, gives it a home, and moves into a project.

    Args:
      tmp_path: The test's own directory, which everything goes under.
      monkeypatch: What sets PATH, the CLI's home and the working directory back afterwards.

    Returns:
      The project, which is the working directory now.
    """
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "claude"
    fake.write_text(f"#!{sys.executable}\n{CLAUDE}")
    fake.chmod(0o755)
    # Only the system's own directories besides: a real coding agent installed for whoever
    # runs the suite is never on it, so nothing here can start one by mistake.
    monkeypatch.setenv("PATH", os.pathsep.join((str(binaries), "/usr/bin", "/bin")))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    return project


def started(tmp_path: Path) -> list[dict[str, Any]]:
    """Every start of the stand-in `claude` under `tmp_path`, oldest first."""
    log = tmp_path / "claude" / "standin.log"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines()]


def write_flow(under: Path, name: str, source: str) -> str:
    """Writes one flow out as a directory and answers with the path a line names it by."""
    at = under / name
    at.mkdir(parents=True)
    (at / "__init__.py").write_text(source)
    return str(at)


def hmz_exec(*argv: str) -> subprocess.CompletedProcess[str]:
    """Runs `hmz exec` as a program, in the working directory, and answers with how it went."""
    return subprocess.run(
        [sys.executable, "-m", "hmz", "exec", *argv],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=120,
        check=False,
    )
