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
from typing import Any

import pytest

from hmz import cli
from hmz.coganchor import AnchorConfig
from hmz.coganchor.argv import parser

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
    assert rendered[:5] == [sys.executable, "-m", "hmz", "internal", "anchor"]

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
