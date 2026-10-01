"""What a Codex whose commands land on another machine is started with, and what it is not."""

from __future__ import annotations

import pytest

from hmz.coganchor import AnchorConfig
from hmz.coganchor.agents import CodexAgent, CodexAgentConfig
from hmz.coganchor.agents.config import anchored
from hmz.coganchor.machines import AnchoredConfig

SNAPSHOTS_OFF = ["--disable", "shell_snapshot"]


def _argv(**config: object) -> list[str]:
    """The app server command an agent configured this way starts."""
    return CodexAgent(
        CodexAgentConfig(model="m", effort="high", **config)  # pyright: ignore[reportArgumentType]
    )._argv(())


def _says(argv: list[str], pair: list[str]) -> bool:
    """Whether `pair` is two adjacent words of `argv`."""
    return any(argv[at : at + 2] == pair for at in range(len(argv) - 1))


@pytest.mark.parametrize("target", ["ssh://box", "docker://box", "local:/srv/box"])
def test_a_supervised_codex_does_not_capture_a_shell_its_commands_cannot_read(
    target: str,
) -> None:
    """The capture is written into Codex's home here and sourced by a command run there."""
    assert _says(_argv(machine=anchored(target)), SNAPSHOTS_OFF)


def test_a_codex_on_this_machine_captures_its_shell_as_it_always_has() -> None:
    assert not _says(_argv(), SNAPSHOTS_OFF)


def test_the_target_s_own_codex_captures_its_shell_where_it_runs() -> None:
    """A native Codex keeps its home on the target, where its commands run too."""
    native = AnchoredConfig(anchor=AnchorConfig(target="ssh://box", native=True))
    assert not _says(_argv(machine=native), SNAPSHOTS_OFF)


@pytest.mark.parametrize("on", [True, False])
def test_a_flow_that_names_the_feature_is_taken_at_its_word(on: bool) -> None:
    argv = _argv(machine=anchored("ssh://box"), features=(("shell_snapshot", on),))
    flag = "--enable" if on else "--disable"
    assert [one for one in argv if one == "shell_snapshot"] == ["shell_snapshot"]
    assert _says(argv, [flag, "shell_snapshot"])
