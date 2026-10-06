"""Where the harness runs, and the line that puts it there -- with nothing reached."""

from __future__ import annotations

import shlex
import subprocess
from typing import Any

import pytest

from hmz.coganchor import rendezvous, transport
from hmz.coganchor.anchor import AnchorConfig
from hmz.coganchor.elsewhere import HERE, SAME, afar, elsewhere, harnessed
from hmz.coganchor.transport import REMOTE_MIRRORS, Target


def test_the_two_words_are_local_and_same() -> None:
    assert (HERE, SAME) == ("local", "same")


@pytest.mark.parametrize(
    ("where", "target", "harness"),
    [
        ("local", "ssh://box", Target("local")),
        ("same", "ssh://box", Target("ssh", host="box")),
        ("same", "local", Target("local")),
        ("docker://c", "ssh://box", Target("docker", host="c")),
    ],
)
def test_the_harness_is_read_as_a_target(
    where: str, target: str, harness: Target
) -> None:
    assert harnessed(where, target) == harness


def test_a_misspelled_harness_is_refused() -> None:
    with pytest.raises(ValueError, match="unsupported target"):
        harnessed("box", "local")


@pytest.mark.parametrize(
    ("harness", "target", "away"),
    [
        ("local", "ssh://box", False),
        ("same", "local:/srv", False),
        ("local:/x", "ssh://box", False),
        ("same", "ssh://box", True),
        ("ssh://other", "ssh://box", True),
        ("docker://c", "local", True),
    ],
)
def test_a_harness_is_elsewhere_only_on_another_machine(
    harness: str, target: str, away: bool
) -> None:
    assert elsewhere(AnchorConfig(harness=harness, target=target)) is away


ARCHIVE = "$HOME/.cache/humanize/humanize-test.pyz"


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every road already holds the archive, so that none is built or pushed."""

    def held(road: transport.Road) -> str:
        return ARCHIVE

    monkeypatch.setattr(transport.Road, "installed", held)


class Started:
    pid = 4242

    def __init__(self, argv: list[str], **kwargs: Any) -> None:
        Started.lines.append(argv)

    def wait(self, timeout: float | None = None) -> int:
        return 0

    lines: list[list[str]] = []  # noqa: RUF012 -- a record shared by every one started


@pytest.fixture
def broker(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """A broker at `hub:7000` that is never listened on, and serving halves never started."""
    Started.lines = []

    def shared(advertise: str = "") -> tuple[None, str, int]:
        return None, "hub", 7000

    monkeypatch.setattr(rendezvous, "shared", shared)
    monkeypatch.setattr(rendezvous, "ticket", lambda: "t0")
    monkeypatch.setattr(subprocess, "Popen", Started)
    return Started.lines


def options_of(line: list[str]) -> list[str]:
    """What the harness's machine is told to run, read back out of an ssh line."""
    return shlex.split(line[-1])


def test_the_same_machine_supervises_its_own_work_as_a_local_target(
    installed: None, broker: list[list[str]]
) -> None:
    config = AnchorConfig(harness="same", target="ssh://box", remote_path="/srv/w")
    line = afar(config, ["claude", "-p"])
    assert line[0] == "ssh"
    assert line[-2] == "box"
    words = options_of(line)
    assert words[-2:] == ["claude", "-p"]
    assert "--target=local:/srv/w" in words
    assert not any(word.startswith("--harness") for word in words)
    assert "--force" in words
    assert ARCHIVE in words[3]
    assert f'HUMANIZE_SHADOW="{REMOTE_MIRRORS}/' in words[3]
    assert broker == []


def test_a_named_mirror_is_used_as_it_is(
    installed: None, broker: list[list[str]]
) -> None:
    config = AnchorConfig(harness="same", target="ssh://box", shadow="/m")
    words = options_of(afar(config, ["a"]))
    assert "--shadow=/m" in words
    assert "--force" not in words
    assert "HUMANIZE_SHADOW" not in words[3]


def test_one_workspace_on_one_target_keeps_one_mirror(
    installed: None, broker: list[list[str]]
) -> None:
    def mirror(config: AnchorConfig) -> str:
        script = options_of(afar(config, ["a"]))[3]
        return script.split('HUMANIZE_SHADOW="', 1)[1].split('"', 1)[0]

    first = mirror(AnchorConfig(harness="same", target="ssh://box", workspace="/w"))
    again = mirror(AnchorConfig(harness="same", target="ssh://box", workspace="/w"))
    other = mirror(AnchorConfig(harness="same", target="ssh://box", workspace="/v"))
    assert first == again
    assert first != other


def test_two_machines_meet_through_the_broker(
    installed: None, broker: list[list[str]]
) -> None:
    config = AnchorConfig(
        harness="ssh://runner", target="docker://work", workspace="/w"
    )
    words = options_of(afar(config, ["claude"]))
    assert "--target=peer://t0@hub:7000" in words
    assert len(broker) == 1
    started = broker[0]
    assert started[:4] == ["docker", "exec", "-i", "work"]
    assert started[-5:] == ["serve", "--peer", "t0@hub:7000", "--export", "/w"]
