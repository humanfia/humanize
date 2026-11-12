"""`hmz.tui.pick.Swarming`: a swarm corrected on its form, and what it keeps of what it was."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from textual.app import App

import hmz.daemon
from hmz.tui import pick

if TYPE_CHECKING:
    from hmz.coganchor.machines.store import SwarmRuntime


class _Runtimes:
    """The store, as far as the form asks it: none taken, and one made as it was told."""

    def all(self, backend: str) -> list[Any]:
        return []

    def new(self, backend: str, name: str, **fields: Any) -> Any:
        return SimpleNamespace(backend=backend, name=name, **fields)


class _Host(App[None]):
    """Puts the form up and keeps what it was answered with."""

    def __init__(self, form: pick.Swarming) -> None:
        super().__init__()
        self.form = form
        self.answers: list[Any] = []

    def on_mount(self) -> None:
        self.push_screen(self.form, self.answers.append)


def _swarm(*, resolve_image: bool) -> SwarmRuntime:
    return cast(
        "SwarmRuntime",
        SimpleNamespace(
            name="gpus",
            endpoint="local",
            tls_dir="",
            image="python:3.12",
            run_args=(),
            cpus=0.0,
            memory=0,
            workdir="",
            fallback=(),
            harness="env",
            name_prefix="",
            constraints=("node.labels.gpu==true",),
            max_tasks=4,
            gpu_resource="",
            nodes={},
            resolve_image=resolve_image,
        ),
    )


@pytest.fixture(autouse=True)
def runtimes(monkeypatch: pytest.MonkeyPatch) -> None:
    here = SimpleNamespace(runtimes=_Runtimes())
    monkeypatch.setattr(hmz.daemon, "Hmz", lambda: here)


@pytest.mark.parametrize("resolve_image", [False, True])
async def test_a_swarm_corrected_keeps_whether_it_resolves_its_image(
    resolve_image: bool,
) -> None:
    host = _Host(pick.Swarming(_swarm(resolve_image=resolve_image)))
    async with host.run_test() as pilot:
        await pilot.pause()
        host.form.action_done()
        await pilot.pause()

    [made] = host.answers
    assert made.name == "gpus"
    assert made.constraints == ["node.labels.gpu==true"]
    assert made.resolve_image is resolve_image
