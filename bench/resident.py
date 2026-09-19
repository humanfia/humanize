"""What one process tree holds on the cores it is pinned to, in GiB, printed and gone.

Its own program because of where it is called from: a sweep needs this while it is reading
thousands of pipes, and taking it means walking every process on the machine and reading a file
for each. In a thread that is a fifth of a second with the interpreter lock held, which stops
the reading -- and a stall in one sample in twenty is a stall exactly where the ninety-fifth
percentile is read. So it happens over here, where the only thing it can slow down is itself.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    """Prints what the named process and its descendants hold, counting only the pinned ones.

    Ours only, and of ours only what runs where the hub does: the mocked machines are children
    of that process too, and in a real deployment their memory is another machine's.
    """
    root = int(sys.argv[1])
    mine = frozenset(os.sched_getaffinity(root))
    parents: dict[int, int] = {}
    held: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            said = (entry / "status").read_text()
        except OSError:
            continue
        rss, parent = 0, 0
        for line in said.splitlines():
            if line.startswith("VmRSS:"):
                rss = int(line.split()[1])
            elif line.startswith("PPid:"):
                parent = int(line.split()[1])
        parents[int(entry.name)] = parent
        held[int(entry.name)] = rss
    ours, growing = {root}, True
    while growing:
        growing = False
        for pid, parent in parents.items():
            if parent in ours and pid not in ours:
                ours.add(pid)
                growing = True
    total = 0
    for pid in ours:
        try:
            if not frozenset(os.sched_getaffinity(pid)) <= mine:
                continue
        except (OSError, ProcessLookupError):
            continue
        total += held.get(pid, 0)
    print(total / 1024**2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
