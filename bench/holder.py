"""A far side that costs nothing, for the arrangements where the hub is only a coordinator.

Under two of the three arrangements the agent does not run on the hub at all: the hub renders
a line, starts one process down a road, and reads three streams -- and for the arrangement
whose halves are on two machines it also books a meeting, leaves a serving half waiting at it,
and introduces the two. What the agent then *does* is the far machine's business and costs the
hub nothing, so a far side that really ran a CLI would only be measuring how many CLIs this box
can run, which is what the first arrangement already answers.

So in that mode the far side is this: a process the hub spawned, holding a pipe, saying when it
is. Where a meeting was booked it completes the introduction first -- by hand, in the few lines
the broker's own protocol takes, and asking to be carried rather than punched, since carrying
is the road that costs the hub something and is therefore the one worth measuring. Everything
the hub does is real; only the work at the other end is not there.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time

#: How often it says when it is. A line a second, which is about what a coding agent's output
#: comes to once it is lines rather than tokens -- and the rate matters to what is being
#: measured: ten times that is a hub whose own reading of the streams is the first thing to
#: run out, which is a fact about how chatty the agents were told to be and not about the hub.
BEAT = float(os.environ.get("HMZ_BENCH_BEAT", "1.0"))


def joined(spec: str) -> socket.socket:
    """Completes an introduction as the anchoring half, in the protocol's own few lines.

    Written out rather than imported so that this stays a process the far machine starts in a
    few milliseconds. What it does is what `hmz.coganchor.rendezvous.dial` does, less the
    punching: it says who it is, hears what the broker saw, waits to be paired, says it could
    not reach the other half, and is spliced onto it.

    Args:
      spec: The meeting, as `TICKET@HOST:PORT`.

    Returns:
      The socket the session is carried on.
    """
    ticket, _, authority = spec.partition("@")
    host, _, port = authority.rpartition(":")
    home = socket.create_connection((host.strip("[]"), int(port)), timeout=120.0)
    home.sendall(
        json.dumps({"ticket": ticket, "role": "anchor", "at": []}).encode() + b"\n"
    )
    reading = home.makefile("rb")
    reading.readline()  # what the broker sees of this half
    reading.readline()  # and where the other half is
    home.sendall(b'{"direct": false}\n')
    reading.readline()  # and the broker's word on how the two are joined
    return home


def main() -> int:
    """Holds a session open for as long as it was asked to, saying when it is throughout."""
    spec, seconds = sys.argv[1], float(sys.argv[2])
    held = joined(spec) if spec != "-" else None
    ends = time.monotonic() + seconds
    while time.monotonic() < ends:
        print(f"{time.time():.6f}", flush=True)
        time.sleep(BEAT)
    if held is not None:
        held.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
