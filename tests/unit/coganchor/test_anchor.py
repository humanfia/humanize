"""The Python call and the command line, which are one thing said twice.

Everything the parser reads is a field of :class:`AnchorConfig`, and everything a config renders
is read back by that parser -- a flow spawns what an operator types. The rest of this suite runs
through both, so what is left to check here is that the two spellings still mean the same.

This is the half of that file which needs nothing but the parser: a config is rendered, the
words are read back, and the settings no session could run under are refused where they are
written. Nothing here spawns anything, so it runs on any machine at all. The half that starts
a supervised process to prove :func:`connect` and :func:`check` reach a target -- ptrace,
seccomp and a subprocess -- is `tests/system/coganchor/test_anchor.py`, which a kernel that
will not hand over a tracee skips whole.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

import pytest

from hmz import cli
from hmz.coganchor import AnchorConfig
from hmz.coganchor.argv import parser
from hmz.coganchor.fence import ALL, READ, Fence

if TYPE_CHECKING:
    from pathlib import Path

#: Every setting at once, none of them left at its default. The token is spelled the way one
#: in eighty of `secrets.token_urlsafe`'s are, and the paths hold a space, because a setting
#: that reads as an option of ours is the way this crossing breaks.
FULL = AnchorConfig(
    target="ssh://build-box",
    workspace="/srv/a project",
    chdir="/srv/a project/packages/one",
    remote_path="/mnt/data/a project",
    shadow="/tmp/mirror",
    local_paths=("/home/me/.secrets", "/home/me/.cache"),
    local_execs=("/usr/local/bin/here",),
    redirects=(("/home/me/.claude/.credentials.json", "/srv/a provider/creds.json"),),
    net="remote",
    net_allow=("api.anthropic.com:443",),
    token="-Vx9nQs3cret",
    force=True,
    fence=Fence.of(
        local=ALL,
        user=READ,
        system=READ,
        online=True,
        workdir="/srv/a project",
        home="/home/me",
    ),
)


def test_a_rendered_command_is_parsed_back_as_the_settings_it_came_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A setting that did not survive the round trip would be dropped in silence."""
    seen: dict[str, Any] = {}

    def record(command: list[str], config: AnchorConfig) -> int:
        seen.update(command=command, config=config)
        return 0

    monkeypatch.setattr("hmz.coganchor.anchor.connect", record)
    rendered = FULL.command(["claude", "--print"])
    # The interpreter running the flow, so the child is the one humanize is installed in.
    assert rendered[:5] == [sys.executable, "-Pm", "hmz", "internal", "anchor"]

    assert cli.main(rendered[3:]) == 0

    assert seen["config"] == FULL
    assert seen["command"] == ["claude", "--print"]


def test_an_agent_argument_is_never_read_as_one_of_ours() -> None:
    """A kimi turn carries its prompt in argv, and a prompt can be worded like anything."""
    argv = ["kimi", "--prompt", "--force the issue, and mind the gap", "--model", "k3"]

    rendered = AnchorConfig(target="ssh://build-box", force=True).command(argv)

    assert parser().parse_args(rendered[5:]).command == argv


def test_a_default_anchor_says_only_where_the_work_lands() -> None:
    assert AnchorConfig().command(["claude"])[5:] == [
        "--target=local",
        "--net=local",
        "claude",
    ]


def test_the_help_names_every_target_the_parser_takes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A `peer://` target is one humanize renders, so the help says it is one."""
    with pytest.raises(SystemExit) as stopped:
        cli.main(["internal", "anchor", "--help"])
    assert stopped.value.code == 0
    shown = " ".join(capsys.readouterr().out.split())
    assert all(
        scheme in shown
        for scheme in ("ssh://", "docker://", "tcp://", "peer://", "local[:DIR]")
    )


def test_a_target_nobody_can_read_is_refused_the_way_argparse_refuses_an_argument() -> (
    None
):
    with pytest.raises(SystemExit) as refused:
        cli.main(["internal", "anchor", "--target", "rsync://build-box", "claude"])
    assert refused.value.code == 2


@pytest.mark.parametrize(
    ("settings", "complaint"),
    [
        ({"target": "rsync://build-box"}, "unsupported target"),
        ({"net": "Remote"}, "unsupported net"),
    ],
    ids=["a target nobody can read", "a net that is neither"],
)
def test_settings_no_session_could_run_under_are_refused_as_they_are_written(
    settings: dict[str, Any], complaint: str
) -> None:
    """Both spellings refuse the same thing: the command line by parsing, this by construction."""
    with pytest.raises(ValueError, match=complaint):
        AnchorConfig(**settings)


def test_a_harness_elsewhere_answers_the_workspaces_own_path_with_its_mirror() -> None:
    """The workspace's own path reaches the mirror for a harness reaching its work as a peer.

    Which is a harness on another machine: a CLI told to work at the target's path of the
    workspace would otherwise start every command in a directory that harness never had.
    """
    from hmz.coganchor.anchor import _aliases
    from hmz.coganchor.transport import Target

    peer = Target.parse("peer://0123456789abcdef0123456789abcdef@10.0.0.1:4242")
    mirror, workspace = "/cache/humanize-mirrors/abc", "/srv/project"

    assert _aliases(peer, mirror, workspace) == ((workspace, mirror),)
    # A harness beside its work, or here, has the workspace at its own path, or is told the
    # mirror's.
    for other in ("local:/srv/project", "docker://box", "ssh://build-box"):
        assert _aliases(Target.parse(other), mirror, workspace) == ()
    # A mirror at the workspace's own path, or nested in it or it in the mirror, has no
    # second name that could be answered.
    assert _aliases(peer, workspace, workspace) == ()
    assert _aliases(peer, f"{workspace}/mirror", workspace) == ()
    assert _aliases(peer, mirror, f"{mirror}/project") == ()


def test_a_mirror_that_cannot_be_made_here_says_so_rather_than_what_it_failed_with(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A path that cannot be made is this machine's filesystem, and says it in its own words.

    Read as the error underneath says it, `Permission denied` is a credential refused, and a
    turn failing for it is a person sent to sign an account in that nothing was wrong with.
    """
    from hmz.coganchor import backends

    (tmp_path / "work").mkdir()
    (tmp_path / "taken").write_text("a file, where the mirror's parent was to be\n")
    status = cli.main(
        [
            "internal",
            "anchor",
            f"--target=local:{tmp_path / 'work'}",
            f"--workspace={tmp_path / 'work'}",
            f"--shadow={tmp_path / 'taken' / 'mirror'}",
            "sh",
        ]
    )

    said = capsys.readouterr().err
    assert status == 1
    assert f"cannot keep the local copy of the work at {tmp_path}/taken/mirror" in said
    assert backends.trouble("claude", said) == "unmirrored"
