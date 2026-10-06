"""`hmz internal fence`: a program run inside the fence its flow's permission draws."""

from __future__ import annotations

from unittest import mock

import pytest

import hmz.coganchor.fence.wrap
from hmz.cli.fence import fence


@pytest.fixture
def wrap(monkeypatch: pytest.MonkeyPatch) -> mock.Mock:
    """`hmz.coganchor.fence.wrap.main`, mocked."""
    held = mock.Mock(return_value=0)
    monkeypatch.setattr(hmz.coganchor.fence.wrap, "main", held)
    return held


@pytest.mark.parametrize(
    ("argv", "policy", "command"),
    [
        (["--policy", '{"a": 1}', "--", "claude", "-p"], '{"a": 1}', ["claude", "-p"]),
        (["--policy=@/p.json", "codex"], "@/p.json", ["codex"]),
        (["--policy", "{}", "--", "x", "--", "y"], "{}", ["x", "--", "y"]),
    ],
)
def test_fence_hands_the_policy_and_the_program_to_the_fence(
    wrap: mock.Mock, argv: list[str], policy: str, command: list[str]
) -> None:
    wrap.return_value = 5
    assert fence(argv) == 5
    wrap.assert_called_once_with(policy, command)


@pytest.mark.parametrize(
    ("argv", "said"),
    [
        (["--policy", "{}"], "no program given"),
        (["--policy", "{}", "--"], "no program given"),
        (["--", "claude"], "--policy"),
    ],
)
def test_fence_refuses_a_line_missing_a_part(
    wrap: mock.Mock, argv: list[str], said: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        fence(argv)
    assert raised.value.code == 2
    assert said in capsys.readouterr().err
    wrap.assert_not_called()
