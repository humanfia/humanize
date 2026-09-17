"""The preload layer under a real `node`, which is the only thing that can confirm any of it.

The other half of this file is `tests/integration/agents/test_preload.py`: a report read out of
one line, the unix socket the reports arrive on, the moments they become, and the variables each
driver composes. Those are this process and a loopback socket, so CI runs them.

What is here runs the layer where it actually lives -- inside somebody else's Node process,
patched in through `NODE_OPTIONS` before the CLI has run a line. Whether a patched `execFile` is
still the function it replaced, whether the layer follows a CLI that re-execs itself and stops at
any other program, and whether a program with nowhere to report runs anyway are all questions
about Node's own module system, and nothing but Node answers them.

They used to sit in the hermetic half behind a bare `pytest.skip("node is not installed here")`,
which is the failure this split is for: on a machine without node they vanished with nobody
counting, and on a machine with it they ran a real external runtime inside the tier everyone
believes is offline. A real binary CI cannot be relied on to have is a system test, so they are
here, and what is left over there is honestly hermetic.

Two gates, and they answer different questions. The directory is what keeps these out of CI,
which never runs this tree. The `node` mark, registered in `tests/conftest.py`, is what keeps
them out of a run on a machine with no `node` to run -- named in the `-ra` summary with the
reason attached, rather than the bare `pytest.skip` in the body they used to carry, which said
nothing a run could be selected on and nothing a reader could see from the outside.
"""

from __future__ import annotations

import json
import subprocess
import time
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import AgentConfig, Hooks, Moment, Occasion
from hmz.coganchor.agents import preload as layer
from hmz.coganchor.agents.preload import Watch, preloaded, runtime
from tests.stubs import ShellAgent

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from hmz.coganchor.agents import AgentBase

#: What the stand-in agents here are configured with, which nothing in this file reads.
CONFIG = AgentConfig(model="m", effort="high")

#: How long the reports of one short program are waited for. They arrive on a thread of their
#: own, after the write that carried them: generous, because what is being waited on is a whole
#: Node process starting, doing four things and exiting.
PATIENCE = 30.0


def _agent(name: str = "worker") -> ShellAgent:
    """One agent with nothing hung on it, which is an agent nobody is listening to."""
    return ShellAgent(CONFIG, name=name)


def _seen(agent: AgentBase) -> list[Occasion]:
    """Has every `PreToolUse` of this agent written down, which is what turns the layer on."""
    said: list[Occasion] = []
    agent.hooks.on(Moment.PRE_TOOL_USE, said.append)
    return said


def _waits(said: list[Occasion], many: int) -> list[Occasion]:
    """Waits for that many reports to arrive, or for the patience to run out.

    Args:
      said: Where the hook is writing them down, which another thread is appending to.
      many: How many are expected.

    Returns:
      What arrived, which is what the test then reads -- short, where they did not.
    """
    ended = time.monotonic() + PATIENCE
    while len(said) < many and time.monotonic() < ended:
        time.sleep(0.05)
    return list(said)


def _ran(
    script: str, where: Path, env: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    """Runs one Node program with the environment the layer composed.

    Args:
      script: The program, as source.
      where: A directory of the test's own to write it in.
      env: What to run it with, on top of nothing: the variables here are the whole of it.

    Returns:
      What it came to.
    """
    import os

    file = where / "program.js"
    file.write_text(script)
    return subprocess.run(
        ["node", str(file)],
        capture_output=True,
        text=True,
        check=False,
        timeout=PATIENCE,
        env={**os.environ, **env},
    )


@pytest.mark.node
def test_a_node_program_says_what_it_spawned_wrote_read_and_opened(
    tmp_path: Path,
) -> None:
    """Against the real runtime, which is the only thing that can confirm any of this."""
    agent = _agent()
    said = _seen(agent)
    added = preloaded(agent, {})
    touched = tmp_path / "what-the-turn-wrote.txt"
    program = f"""
const child = require("node:child_process");
const fs = require("node:fs");
const net = require("node:net");

child.execFileSync("/bin/echo", ["hello", "from", "the", "turn"]);
fs.writeFileSync({json.dumps(str(touched))}, "what the turn wrote\\n");
fs.readFileSync({json.dumps(str(touched))}, "utf8");
const socket = net.connect({{ host: "127.0.0.1", port: 9 }});
socket.on("error", () => {{}});
socket.destroy();
"""
    try:
        ran = _ran(program, tmp_path, added)
        assert ran.returncode == 0, ran.stderr
        _waits(said, 4)
    finally:
        layer._WATCHED[agent].close()

    did = {(one.tool, one.about) for one in said}
    assert ("spawn", "/bin/echo hello from the turn") in did
    assert ("write", str(touched)) in did
    assert ("read", str(touched)) in did
    assert ("connect", "127.0.0.1:9") in did


@pytest.mark.node
def test_the_preload_does_not_follow_a_program_into_another_program(
    tmp_path: Path,
) -> None:
    """`NODE_OPTIONS` is inherited by every process the CLI starts, and this must not be.

    Every Node program under a turn -- a package manager, a language server, a script the
    agent wrote -- reporting its own reads as the agent's work is noise, and the agent running
    it was already reported by the spawn that ran it. What that program runs in turn finds
    nothing at all, which is what the variables it was handed being taken away means.
    """
    agent = _agent()
    said = _seen(agent)
    added = preloaded(agent, {"NODE_OPTIONS": "--max-old-space-size=2048"})
    install, elsewhere = tmp_path / "install", tmp_path / "elsewhere"
    install.mkdir()
    elsewhere.mkdir()
    inherited = tmp_path / "what-the-other-program-had.json"
    (elsewhere / "theirs.js").write_text(f"""
const child = require("node:child_process");
require("node:fs").writeFileSync({json.dumps(str(inherited))}, JSON.stringify({{
  options: process.env.NODE_OPTIONS || "",
  at: process.env.HMZ_PRELOAD_AT || "",
  in: process.env.HMZ_PRELOAD_IN || "",
}}));
child.execFileSync("/bin/echo", ["the", "other", "program's", "own", "work"]);
""")
    program = f"""
const child = require("node:child_process");
child.execFileSync(process.execPath, [{json.dumps(str(elsewhere / "theirs.js"))}]);
"""
    try:
        ran = _ran(program, install, added)
        assert ran.returncode == 0, ran.stderr
        _waits(said, 1)
    finally:
        layer._WATCHED[agent].close()

    other = json.loads(inherited.read_text())
    # What somebody else put in the variable is still there; only the `--require` is gone.
    assert other["options"] == "--max-old-space-size=2048"
    assert other["at"] == ""
    assert other["in"] == ""
    # The spawn that started it was reported, which is how its work is accounted for -- and
    # nothing it did itself was.
    did = [one.about for one in said if one.tool == "spawn"]
    assert any("theirs.js" in one for one in did)
    assert not any("other program" in one for one in did)


@pytest.mark.node
def test_the_preload_follows_a_cli_that_re_execs_itself(tmp_path: Path) -> None:
    """Which is the difference between watching a turn and watching a launcher.

    qwen's entry point starts a second `node` on the bundle beside it and takes the whole turn
    there. The rule is the program rather than the process: a process started from the same
    install is still the CLI, and goes on reporting.
    """
    agent = _agent()
    said = _seen(agent)
    added = preloaded(agent, {})
    (tmp_path / "again.js").write_text("""
require("node:child_process").execFileSync("/bin/echo", ["the", "turn", "itself"]);
""")
    program = f"""
const child = require("node:child_process");
child.execFileSync(process.execPath, [{json.dumps(str(tmp_path / "again.js"))}]);
"""
    try:
        ran = _ran(program, tmp_path, added)
        assert ran.returncode == 0, ran.stderr
        _waits(said, 2)
    finally:
        layer._WATCHED[agent].close()

    did = [one.about for one in said if one.tool == "spawn"]
    assert any("again.js" in one for one in did)
    assert "/bin/echo the turn itself" in did


@pytest.mark.node
def test_one_thing_the_program_did_is_one_report(tmp_path: Path) -> None:
    """`exec` reaches for `execFile`, which reaches for `spawn`: one command, not three."""
    agent = _agent()
    said = _seen(agent)
    added = preloaded(agent, {})
    program = """
const child = require("node:child_process");
child.execSync("/bin/echo once");
"""
    try:
        ran = _ran(program, tmp_path, added)
        assert ran.returncode == 0, ran.stderr
        _waits(said, 1)
        time.sleep(
            0.5
        )  # long enough for a second report to have arrived, had there been one
    finally:
        layer._WATCHED[agent].close()

    assert [one.about for one in said if one.tool == "spawn"] == ["/bin/echo once"]


@pytest.mark.node
def test_a_patched_call_is_the_call_it_replaced_in_every_other_way(
    tmp_path: Path,
) -> None:
    """A patch is not allowed to change what the program it is inside of does.

    `util.promisify` reads a symbol off `exec` and `execFile` saying what their promised form
    answers with -- `{ stdout, stderr }` rather than the first thing the callback was given --
    and a patch that dropped it would leave `const { stdout } = await exec(...)` undefined,
    which is a CLI broken by something that was only supposed to be watching it.
    """
    agent = _agent()
    said = _seen(agent)
    added = preloaded(agent, {})
    answered = tmp_path / "what-the-promise-answered.json"
    program = f"""
const child = require("node:child_process");
const fs = require("node:fs");
const promised = require("node:util").promisify(child.exec);
promised("/bin/echo promised").then((answer) => {{
  fs.writeFileSync({json.dumps(str(answered))}, JSON.stringify({{
    stdout: answer.stdout,
    named: child.exec.name,
  }}));
}});
"""
    try:
        ran = _ran(program, tmp_path, added)
        assert ran.returncode == 0, ran.stderr
        _waits(said, 1)
    finally:
        layer._WATCHED[agent].close()

    answer = json.loads(answered.read_text())
    assert answer["stdout"] == "promised\n"
    assert answer["named"] == "exec"
    assert [one.about for one in said if one.tool == "spawn"] == ["/bin/echo promised"]


@pytest.mark.node
def test_a_program_whose_preload_has_nowhere_to_report_runs_as_it_would_have(
    tmp_path: Path,
) -> None:
    """Fail open. This file runs inside somebody else's program, and must never end one."""
    ran = _ran(
        'console.log("the turn ran");',
        tmp_path,
        {
            "NODE_OPTIONS": f"--require {runtime()}",
            "HMZ_PRELOAD_AT": str(tmp_path / "nothing" / "is" / "listening.sock"),
        },
    )

    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.strip() == "the turn ran"


@pytest.mark.node
def test_a_program_that_was_never_meant_to_report_loads_it_and_says_nothing(
    tmp_path: Path,
) -> None:
    """Any Node program on the machine may find this file; one with nowhere named is silent.

    Which is what keeps a `node` somebody runs by hand, with this still in their environment
    from a flow that has ended, from connecting to anything.
    """
    hooks = Hooks(frozenset(Moment), "worker")
    said: list[Occasion] = []
    hooks.on(Moment.PRE_TOOL_USE, said.append)
    watch = Watch(hooks)
    try:
        at = watch.address()
        ran = _ran(
            'require("node:child_process").execFileSync("/bin/echo", ["unwatched"]);',
            tmp_path,
            {"NODE_OPTIONS": f"--require {runtime()}"},
        )
        assert ran.returncode == 0, ran.stderr
        assert at  # there was somewhere to report to, and nothing was told where it was
        time.sleep(0.5)  # long enough for a report to have arrived, had one been made
    finally:
        watch.close()

    assert said == []


@pytest.mark.node
def test_a_cli_that_re_execs_itself_out_of_another_install_is_still_the_cli(
    tmp_path: Path,
) -> None:
    """The rule is the package rather than the path, because the path is not stable.

    qwen's entry point runs whichever copy of itself its own updater has put under the user's
    home in preference to the one beside it -- a different directory entirely, and the same
    program. A rule written in paths would stop watching there, which is the half of the turn
    that does the work.
    """
    agent = _agent()
    said = _seen(agent)
    added = preloaded(agent, {})
    install, updated = tmp_path / "install", tmp_path / "updated"
    install.mkdir()
    updated.mkdir()
    for where in (install, updated):
        (where / "package.json").write_text(json.dumps({"name": "@some/cli"}))
    (updated / "newer.js").write_text("""
require("node:child_process").execFileSync("/bin/echo", ["the", "newer", "copy"]);
""")
    program = f"""
const child = require("node:child_process");
child.execFileSync(process.execPath, [{json.dumps(str(updated / "newer.js"))}]);
"""
    try:
        ran = _ran(program, install, added)
        assert ran.returncode == 0, ran.stderr
        _waits(said, 2)
    finally:
        layer._WATCHED[agent].close()

    assert "/bin/echo the newer copy" in [
        one.about for one in said if one.tool == "spawn"
    ]


@pytest.mark.node
def test_what_a_cli_reads_and_writes_of_its_own_install_is_not_the_turns_work(
    tmp_path: Path,
) -> None:
    """What the CLI is is not what the CLI did.

    A bundle loading itself is thousands of reads and not one of them is the agent doing
    anything; a file beside the work is the turn.
    """
    agent = _agent()
    said = _seen(agent)
    added = preloaded(agent, {})
    install, work = tmp_path / "install", tmp_path / "work"
    install.mkdir()
    work.mkdir()
    (install / "package.json").write_text(json.dumps({"name": "@some/cli"}))
    (install / "its-own.txt").write_text("part of the program\n")
    (work / "the-turns.txt").write_text("part of the work\n")
    program = f"""
const fs = require("node:fs");
fs.readFileSync({json.dumps(str(install / "its-own.txt"))}, "utf8");
fs.readFileSync({json.dumps(str(work / "the-turns.txt"))}, "utf8");
"""
    try:
        ran = _ran(program, install, added)
        assert ran.returncode == 0, ran.stderr
        _waits(said, 1)
        time.sleep(
            0.5
        )  # long enough for the other read to have arrived, had it been said
    finally:
        layer._WATCHED[agent].close()

    read = [one.about for one in said if one.tool == "read"]
    assert str(work / "the-turns.txt") in read
    assert str(install / "its-own.txt") not in read
