"""What the runtimes page says once a runtime has been asked what it has.

A docker daemon lists every GPU its CDI specs were written for, which is every one the driver
was bound to then; one that has failed since is listed still and handed to nobody. So what is
said is how many of those it lists answer, beside them and in yellow, and what detecting writes
in is those that do.
"""

from __future__ import annotations

from hmz.coganchor.machines.store import DockerRuntime
from hmz.runtime.doing.runtimes import Checked
from hmz.tui.pick import _answered, _failed

_HERE = DockerRuntime(name="local")


def _checked(usable: tuple[str, ...] | None) -> Checked:
    return Checked(
        reached=True,
        cpus=64,
        memory=64 << 30,
        gpus=("0", "1"),
        usable=usable,
        runtimes=("nvidia",),
        version="29.4.3",
    )


def test_a_gpu_that_does_not_answer_is_said_in_yellow_beside_what_is_listed() -> None:
    said = _answered(_HERE, _checked(("0",)))

    first, second = said.splitlines()
    assert "docker/local answers: docker 29.4.3; 64 CPUs, 64G, GPUs 0, 1" in first
    assert "[yellow]" in second
    assert "1 of 2 GPUs answer; GPU 1 does not" in second


def test_every_gpu_answering_or_nobody_asking_says_nothing_more() -> None:
    assert _failed(_checked(("0", "1"))) == ""
    assert _failed(_checked(None)) == ""
    assert len(_answered(_HERE, _checked(None)).splitlines()) == 1


def test_none_answering_is_every_one_named() -> None:
    assert _failed(_checked(())) == "0 of 2 GPUs answer; GPU 0, 1 do not"
