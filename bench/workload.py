"""What a coding agent does to a workspace, without a model behind it.

A turn is a handful of tool calls and the tool calls are file operations: read the files the
model asked about, write back the one it changed, list a directory to find the next one, run a
command now and then. Under an anchor every one of those is a stopped syscall and -- the first
time a path is touched -- a round trip to the machine the work lands on. That is the cost this
measures, and it is the cost a real turn pays; what a real turn adds on top is waiting for a
model, which spends nothing of the machine and is left out on purpose.

Run under the anchor as the agent, after the real CLI has been started once so that its own
runtime, its module resolution and its state directories have been paid for through the
mirror. Reports what each round took, so a sweep can read latency rather than only throughput.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

#: Files read per round. A turn's worth: the file the model is working on, the handful it
#: asked to see around it, and whatever an editor of that file touches on the way.
READS = 20

#: And written. Coding agents read far more than they write, which is why the mirror is worth
#: having at all, so the ratio matters more than either number.
WRITES = 2

#: Directories listed per round, which is how one file leads to the next.
LISTS = 2

#: Rounds between spawning something. Every spawn crosses to the machine the work lands on,
#: whatever the anchor does with paths, so this is the other half of what a turn costs.
SPAWN_EVERY = 5


def main() -> int:
    """Runs rounds of a turn's file work until told to stop.

    Named relative to where it was started rather than by an absolute path, which is not a
    detail: an agent under an anchor works in a mirror of the workspace, and the workspace's
    own path is a path on *another* machine. Naming it absolutely reads whatever this machine
    happens to have at that name -- which, where the two are the same box, is the real
    workspace read directly, with the anchor never consulted and nothing measured.

    Returns:
      Zero, having printed one JSON line per round saying when it finished and what it took.
    """
    workspace, rounds = os.getcwd(), int(sys.argv[1])
    names = sorted(name for name in os.listdir(workspace) if name.startswith("src-"))
    if not names:
        print(json.dumps({"failed": "the workspace holds no files to read"}))
        return 1
    at = os.getpid() % len(names)
    for each in range(rounds):
        began = time.monotonic()
        for _ in range(READS):
            at = (at + 1) % len(names)
            with open(names[at], encoding="utf-8") as handle:
                handle.read()
        for which in range(WRITES):
            with open(
                f"out-{os.getpid()}-{which}.txt", "w", encoding="utf-8"
            ) as handle:
                handle.write(f"round {each}\n")
        for _ in range(LISTS):
            os.listdir(".")
        if each % SPAWN_EVERY == 0:
            subprocess.run(["/bin/true"], check=False)
        print(
            json.dumps({"at": time.time(), "took": time.monotonic() - began}),
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
