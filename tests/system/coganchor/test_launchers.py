"""What an agent installed as a script runs on its way up, and what it is told on its stdin.

Both are about a target whose files are not this machine's -- a container, a host over ssh --
and both are shown here against a `local:` one, which is enough: a command run on the target
runs in the target's copy of the workspace, and one run here runs in the mirror, so `/bin/pwd`
says which of the two ran it.

A launcher script that asks `realpath` where it was installed is asking about this machine, and
the target need have no such path; cursor-agent's does exactly that. And a command the agent
starts as it comes up, leaving its stdin to it, must not read the agent's first request off the
pipe its driver speaks on -- which is what froze codex's app-server on its `initialize`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.supervising import traced

if TYPE_CHECKING:
    from pathlib import Path

    from tests.coganchor.fixtures import Anchorage

pytestmark = traced

#: An agent installed as a bash script: it asks a helper where it is, as a launcher does, and
#: becomes the "agent", which asks the same of a command of its own.
_LAUNCHER = """#!/bin/bash
here=$(/bin/pwd)
exec python3 -c '
import subprocess, sys
there = subprocess.run(["/bin/pwd"], capture_output=True, text=True).stdout.strip()
print(sys.argv[1])
print(there)
' "$here"
"""


def test_a_launcher_runs_its_helpers_here_and_the_agent_its_commands_there(
    anchorage: Anchorage, tmp_path: Path
) -> None:
    launcher = tmp_path / "bin" / "agent"
    launcher.parent.mkdir()
    launcher.write_text(_LAUNCHER)
    launcher.chmod(0o755)

    result = anchorage.run(str(launcher))

    assert result.returncode == 0, result.stderr
    helper, command = result.stdout.split()
    assert helper == str(anchorage.mirror), "the launcher's helper ran on the target"
    assert command == str(anchorage.target), "the agent's command ran here"


def test_a_command_the_agent_starts_leaves_the_agents_stdin_to_it(
    anchorage: Anchorage,
) -> None:
    result = anchorage.run(
        "python3",
        "-c",
        "import subprocess, sys\n"
        "subprocess.run(['/bin/true'])\n"
        "print('got', sys.stdin.readline().strip())\n",
        stdin=b"the first request\n",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "got the first request"


@pytest.mark.parametrize("given", [b"", b"piped\n"])
def test_a_command_given_its_own_stdin_still_reads_it(
    anchorage: Anchorage, tmp_path: Path, given: bytes
) -> None:
    fed = tmp_path / "fed"
    fed.write_bytes(given)

    result = anchorage.shell(f"/bin/cat < {fed}")

    assert result.returncode == 0, result.stderr
    assert result.stdout == given.decode()
