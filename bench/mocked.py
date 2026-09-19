"""Every `docker://` target, mocked as this machine on the cores the hub is not using.

Everything about a real road is kept but the machine: the archive is really built and really
installed under a cache of that machine's own, the serving half is really started there, the
mirror is really a directory of its own, and two `docker://` names really are two machines
that have to be introduced. What is mocked is only *where* -- the far side runs here, on cores
the hub is pinned away from, so the hub pays for the pipe and for nothing else.
"""

from __future__ import annotations

import os

LAB = os.environ.get("HMZ_BENCH_LAB", "/tmp/hmz-capacity")  # noqa: S108
CORES = os.environ.get("HMZ_BENCH_REMOTE_CORES", "16-63")


def mock() -> None:
    """Points `Road.to` at the mocked machines, in whichever process calls this."""
    from hmz.coganchor.transport import Road, Target

    def road_to(target: Target) -> Road:
        if target.scheme == "local":
            return Road(target, (), quotes=False, cache="", mirrors="")
        under = f"{LAB}/{target.host}"
        return Road(
            target,
            ("taskset", "-c", CORES),
            quotes=False,
            cache=f"{under}/cache",
            mirrors=f"{under}/mirrors",
        )

    Road.to = road_to
