"""One agent's session: anchored turns, one after another, for as long as it is asked for.

Which is what driving an agent is. humanize spawns a turn, reads its three streams, and spawns
the next one -- so a session is a loop rather than a process, and the thing a hub carries N of
is this. Each iteration is two turns: the real CLI, which pays its own runtime and its module
resolution through the mirror and is the backend-specific half of the cost, and a turn of file
work, which is what the model would have asked for and is the half that crosses to the machine
the work lands on.

Nothing here reaches a provider. The CLI is asked its version, which every one of them answers
offline, and the file work is :mod:`bench.workload` -- so a session costs the machine exactly
what a session costs and costs an account nothing.

Reports one JSON line per turn: which kind it was and how long it took. Run on the hub, one per
agent, by :mod:`bench.capacity`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import capacity
from mocked import mock

mock()


def main() -> int:
    """Runs this session's turns and says how each of them went.

    Returns:
      Zero if every turn ran, or the status of the first that did not.
    """
    arrangement = capacity.ARRANGEMENTS[sys.argv[1]]
    backend, which, rounds = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    project = capacity.workspace(which)
    config = arrangement.config(project, which)
    cli = capacity.commanded(backend)
    for _ in range(rounds):
        for kind, argv in (("cli", [cli, "--version"]), ("work", capacity.working())):
            began = time.monotonic()
            # Rendered per turn rather than once, which is not a nicety: the arrangement whose
            # halves are on two machines books a meeting as it renders, and a meeting is one
            # session's. A line kept and used twice is a second turn sent to a ticket the first
            # one already spent.
            ran = subprocess.run(
                capacity.hubbed(config.command(argv)),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            print(
                json.dumps(
                    {
                        "kind": kind,
                        "took": time.monotonic() - began,
                        "rc": ran.returncode,
                    }
                ),
                flush=True,
            )
            if ran.returncode != 0:
                return ran.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
