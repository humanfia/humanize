"""`hmz.daemon.api.fallbacks`: a step written against a place, and what writing one is refused."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from hmz.daemon.api import fallbacks
from hmz.rpc import RpcError


class _Fallbacks:
    default = "exponential-jitter"

    def __init__(self) -> None:
        self.steps: dict[str, tuple[list[str], int, str, float]] = {}

    def reads(self, said: str) -> str:
        return said if "/" in said else ""

    def named(self, policy: str) -> Any:
        return policy if policy in {self.default, "fixed"} else None

    def points(self, place: str, to: list[str]) -> None:
        self.steps[place] = (to, 0, self.default, 0.0)

    def retrying(self, place: str, tries: int, policy: str, timeout: float) -> None:
        self.steps[place] = (self.steps[place][0], tries, policy, timeout)

    def clear(self, place: str) -> bool:
        return self.steps.pop(place, None) is not None

    def all(self) -> list[Any]:
        return [
            SimpleNamespace(spec=spec, to=to, tries=t, policy=p, timeout=s)
            for spec, (to, t, p, s) in self.steps.items()
        ]

    def policies(self) -> list[Any]:
        return [SimpleNamespace(name=self.default, about="backs off")]

    def spec(self, cli: str, model: str, account: str = "") -> str:
        return f"{cli}{'@' + account if account else ''}/{model}"


def _hmz() -> Any:
    return SimpleNamespace(
        fallbacks=_Fallbacks(),
        accounts=SimpleNamespace(all=list),
        installed=lambda: {"claude": (SimpleNamespace(name="opus"),)},
    )


def test_a_step_is_written_with_the_default_way_of_waiting() -> None:
    said = fallbacks.write(_hmz(), "claude/opus", ["codex/gpt"], 2)

    assert said["steps"] == [
        {
            "spec": "claude/opus",
            "to": ["codex/gpt"],
            "tries": 2,
            "policy": "exponential-jitter",
            "timeout": 0.0,
        }
    ]
    assert said["places"] == ["claude/opus"]


_REFUSED: list[tuple[tuple[object, ...], str]] = [
    (("opus",), "opus is not a place: say it as CLI[@ACCOUNT]/MODEL."),
    (("claude/opus", [1]), "Say to as a list of text."),
    (("claude/opus", [], -1), "Say tries as how many more goes, 0 or more."),
    (("claude/opus", [], True), "Say tries as how many more goes, 0 or more."),
    (("claude/opus", [], 0, "never"), "never is no way of waiting."),
    (("claude/opus", [], 0, "", -1), "Say timeout in seconds, or 0 for no limit."),
]


@pytest.mark.parametrize(("args", "why"), _REFUSED)
def test_a_value_fallbacks_refuses_is_refused(args: tuple[Any, ...], why: str) -> None:
    hmz = _hmz()

    with pytest.raises(RpcError) as refused:
        fallbacks.write(hmz, *args)

    assert (refused.value.code, refused.value.message) == (400, why)
    assert hmz.fallbacks.steps == {}


def test_clearing_a_place_with_no_step_is_not_found() -> None:
    hmz = _hmz()
    fallbacks.write(hmz, "claude/opus")

    assert fallbacks.clear(hmz, "claude/opus")["steps"] == []
    with pytest.raises(RpcError) as refused:
        fallbacks.clear(hmz, "claude/opus")
    assert refused.value.code == 404
