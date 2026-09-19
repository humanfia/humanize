"""The three places a harness can run, read off the line each of them renders.

Nothing is started on another machine here: what is being checked is the line, and the line
is what decides everything that happens on the far side. The archive is not pushed either --
the one step that genuinely needs a machine is stood in for, so that what remains is this
repository's own rendering against its own settings.

A real container at each end, with the work landing in a third place and the two ends kept
from reaching each other, is `tests/system/coganchor/test_topologies.py`.
"""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import AnchorConfig
from hmz.coganchor.elsewhere import afar, elsewhere, harnessed
from hmz.coganchor.places import AFAR, NATIVE_CLI, SUPERVISED
from hmz.coganchor.transport import Road, Target

if TYPE_CHECKING:
    from collections.abc import Iterator

#: What the far side would have been given, so that no machine has to be asked for it.
BUNDLE = "/tmp/humanize/humanize-0123456789abcdef.pyz"


@pytest.fixture(autouse=True)
def _without_pushing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The one step that needs a far machine, answered with what it would have said."""

    def instead(_road: Road) -> str:
        return BUNDLE

    monkeypatch.setattr(Road, "installed", instead)


@pytest.fixture
def broker(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A meeting booked without a broker being listened on, and without a half being left."""
    import subprocess

    from hmz.coganchor import rendezvous

    def met(_advertise: str = "") -> tuple[None, str, int]:
        return None, "hmz", 9001

    monkeypatch.setattr(rendezvous, "shared", met)
    started: list[list[str]] = []

    class _Left:
        pid = 1

        def wait(self) -> int:
            return 0

    def instead(argv: list[str], **_: object) -> _Left:
        started.append(argv)
        return _Left()

    monkeypatch.setattr(subprocess, "Popen", instead)
    yield
    assert started, "no serving half was left at the meeting"


def said(config: AnchorConfig, argv: list[str] = ["/bin/true"]) -> list[str]:  # noqa: B006
    """The words of the line the far side's shell ends up running."""
    line = afar(config, argv)
    return shlex.split(line[-1]) if line[0] == "ssh" else line


def test_a_harness_here_is_not_this_module_at_all() -> None:
    """Which is the default, and the arrangement humanize has always had."""
    assert not elsewhere(AnchorConfig(target="ssh://build-box"))
    # Nor is a harness named as this machine under another spelling: a local target stands in
    # for a machine, and standing in for one is not being one.
    assert not elsewhere(AnchorConfig(harness="same", target="local:/srv/project"))
    assert not elsewhere(AnchorConfig(harness="local", target="ssh://build-box"))


def test_same_puts_the_harness_wherever_the_work_lands() -> None:
    """One setting to move both, so a flow that moves its work does not forget the harness."""
    assert harnessed("same", "ssh://build-box") == Target.parse("ssh://build-box")
    assert harnessed("docker://janus", "ssh://build-box") == Target.parse(
        "docker://janus"
    )
    assert elsewhere(AnchorConfig(harness="same", target="docker://janus"))


def test_a_harness_beside_its_work_supervises_a_target_of_its_own_machine() -> None:
    """Nothing is introduced and nothing crosses: the two halves are one machine's."""
    words = said(
        AnchorConfig(harness="same", target="ssh://build-box", workspace="/srv/project")
    )

    assert "--target=local:" in words
    assert "--workspace=/srv/project" in words
    assert "--harness=same" not in words, (
        "the harness is already where it was being sent"
    )
    assert not [word for word in words if word.startswith("--target=peer://")]


def test_a_harness_across_from_its_work_is_sent_to_a_meeting(broker: None) -> None:
    """Which is the only thing either machine is told about the other."""
    words = said(
        AnchorConfig(
            harness="ssh://runner", target="ssh://build-box", workspace="/srv/project"
        )
    )

    targets = [word for word in words if word.startswith("--target=")]
    assert len(targets) == 1
    assert targets[0].startswith("--target=peer://")
    assert targets[0].endswith("@hmz:9001")


def test_the_mirror_a_harness_elsewhere_works_in_is_named_for_what_it_mirrors() -> None:
    """And kept, which is what makes a second turn against a workspace a warm one."""
    config = AnchorConfig(
        harness="same", target="ssh://build-box", workspace="/srv/project"
    )

    line = afar(config, ["/bin/true"])

    script = shlex.split(line[-1])[3]
    assert "HUMANIZE_SHADOW=" in script
    assert "humanize-mirrors/" in script
    # Twice over, the same name: a mirror named for the turn is a mirror thrown away.
    assert script == shlex.split(afar(config, ["/bin/true"])[-1])[3]
    elsewhere_else = AnchorConfig(
        harness="same", target="ssh://build-box", workspace="/srv/other"
    )
    assert script != shlex.split(afar(elsewhere_else, ["/bin/true"])[-1])[3]


def test_a_shadow_somebody_named_is_the_one_used() -> None:
    """A derived name is forced onto its directory; a chosen one must never be."""
    words = said(
        AnchorConfig(
            harness="same",
            target="ssh://build-box",
            workspace="/srv/project",
            shadow="/mirrors/mine",
        )
    )

    assert "--shadow=/mirrors/mine" in words
    assert "--force" not in words


def test_a_harness_elsewhere_says_so_among_its_capabilities() -> None:
    """So a flow that must not send the agent's own process away is able to refuse one."""
    assert AnchorConfig().capabilities == frozenset({SUPERVISED})
    assert AnchorConfig(harness="same", target="ssh://box").capabilities == frozenset(
        {SUPERVISED, AFAR}
    )
    assert AnchorConfig(native=True).capabilities == frozenset({NATIVE_CLI})


def test_a_native_session_has_no_harness_to_put_anywhere() -> None:
    """The CLI on the target is the one that runs, so the two settings ask opposite things."""
    with pytest.raises(ValueError, match="opposite things"):
        AnchorConfig(native=True, harness="ssh://runner", target="ssh://build-box")


def test_a_meeting_is_humanize_to_book_rather_than_a_target_to_name() -> None:
    """Naming both is naming the same introduction twice, and is refused where it is said."""
    with pytest.raises(ValueError, match="twice"):
        AnchorConfig(harness="ssh://runner", target="peer://cafe@broker:9001")


def test_what_reaches_the_far_side_survives_the_shell_that_reads_it() -> None:
    """Every setting, however it was spelled -- a workspace with a space in it included."""
    words = said(
        AnchorConfig(
            harness="ssh://runner",
            target="ssh://runner",
            workspace="/srv/my project",
            private=("ANTHROPIC_API_KEY",),
        ),
        ["claude", "--model", "opus 4"],
    )

    assert "--workspace=/srv/my project" in words
    assert "--private=ANTHROPIC_API_KEY" in words
    assert words[-3:] == ["claude", "--model", "opus 4"]
