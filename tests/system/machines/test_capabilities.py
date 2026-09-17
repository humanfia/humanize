"""The half of what a place comes to that only a running container can answer.

Split from `tests/integration/machines/test_capabilities.py`, which keeps everything a setting
answers on its own -- what a place would come to before anything is brought up, and the
platform read off a `local:` target's handshake. What is left here is the one check that wants
a real image: that `linux`, promised by the setting while the container is still a name, is
the same `linux` the container itself reports once it is running. That needs a docker daemon
and a pulled image, which CI is not given, so it is a system test and CI never runs it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hmz.coganchor.machines import DockerConfig
from tests.machines.fixtures import IMAGE

if TYPE_CHECKING:
    from pathlib import Path


def test_a_container_confirms_the_platform_its_setting_promised(
    daemon: None, tmp_path: Path
) -> None:
    """Declared before the container exists, and made good on by the container itself.

    Which is the pair working as it should: `linux` is refusable before anything is pulled,
    and it is still the running container that is asked whether it is true.
    """
    machine = DockerConfig(image=IMAGE, workspace=str(tmp_path)).create()

    try:
        machine.start()

        assert machine.capabilities == frozenset(
            {"anchor:supervised", "isolated", "linux", "managed", "remote"}
        )
        # And the platform among them came off the wire rather than out of the settings.
        assert machine._seen == frozenset({"linux"})
    finally:
        machine.stop()
