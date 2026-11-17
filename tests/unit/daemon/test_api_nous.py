"""`hmz.daemon.api.nous`: a nous written whole, renamed and cleared, and what is refused."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from hmz.daemon.api import nous
from hmz.rpc import RpcError


class _Book:
    default = "exponential-jitter"

    def __init__(self) -> None:
        self.held: dict[str, Any] = {}

    def reads(self, said: str) -> str:
        return said if said.isidentifier() or "/" in said else ""

    def named(self, policy: str) -> Any:
        return policy if policy in {self.default, "fixed"} else None

    def graph(self, said: object) -> object:
        return said

    def shown(self, graph: object) -> object:
        return graph

    def write(self, name: str, **said: Any) -> None:
        if said["graph"] == "broken":
            raise ValueError("the edges come round")
        self.held[name] = SimpleNamespace(name=name, virtual="/" not in name, **said)

    def renamed(self, said: str, name: str) -> None:
        if said not in self.held:
            raise ValueError(f"{said!r} is no virtual nous written down")
        self.held[name] = self.held.pop(said)
        self.held[name].name = name

    def clear(self, said: str) -> bool:
        if said == "named":
            raise ValueError("other still names named")
        return self.held.pop(said, None) is not None

    def all(self) -> list[Any]:
        return list(self.held.values())

    def policies(self) -> list[Any]:
        return [SimpleNamespace(name=self.default, about="backs off")]

    def strategies(self) -> list[Any]:
        return [SimpleNamespace(name="shuffle", about="at random")]

    def faults(self) -> tuple[str, ...]:
        return ("throttled", "*")

    def spec(self, cli: str, model: str, account: str = "") -> str:
        return f"{cli}{'@' + account if account else ''}/{model}"


def _hmz() -> Any:
    return SimpleNamespace(
        nous=_Book(),
        accounts=SimpleNamespace(all=list),
        installed=lambda: {"claude": (SimpleNamespace(name="opus"),)},
    )


def test_a_nous_is_written_with_the_default_way_of_waiting() -> None:
    said = nous.write(
        _hmz(), {"name": "claude/opus", "then": ["codex/gpt"], "tries": 2}
    )

    assert said["nous"] == [
        {
            "name": "claude/opus",
            "virtual": False,
            "tries": 2,
            "policy": "exponential-jitter",
            "timeout": 0.0,
            "graph": None,
            "then": ["codex/gpt"],
        }
    ]
    assert said["concrete"] == ["claude/opus"]
    assert said["faults"] == ["throttled", "*"]
    assert said["strategies"] == [{"name": "shuffle", "about": "at random"}]


_REFUSED: list[tuple[dict[str, Any], str]] = [
    (
        {"name": "op us"},
        "op us is not a nous: say it as HARNESS[@ACCOUNT]/MODEL[:EFFORT] or a name.",
    ),
    ({"name": "a/b", "tries": -1}, "Say tries as how many more goes, 0 or more."),
    ({"name": "a/b", "tries": True}, "Say tries as how many more goes, 0 or more."),
    ({"name": "a/b", "policy": "never"}, "never is no way of waiting."),
    ({"name": "a/b", "timeout": -1}, "Say timeout in seconds, or 0 for no limit."),
    ({"name": "smart", "graph": "broken"}, "the edges come round"),
]


@pytest.mark.parametrize(("said", "why"), _REFUSED)
def test_a_value_the_book_refuses_is_refused(said: dict[str, Any], why: str) -> None:
    hmz = _hmz()

    with pytest.raises(RpcError) as refused:
        nous.write(hmz, said)

    assert (refused.value.code, refused.value.message) == (400, why)
    assert hmz.nous.held == {}


def test_renaming_and_clearing() -> None:
    hmz = _hmz()
    nous.write(hmz, {"name": "smart", "graph": ["claude/opus"]})

    assert [one["name"] for one in nous.rename(hmz, "smart", "clever")["nous"]] == [
        "clever"
    ]
    with pytest.raises(RpcError) as refused:
        nous.rename(hmz, "ghost", "other")
    assert refused.value.code == 400
    with pytest.raises(RpcError) as refused:
        nous.clear(hmz, "named")
    assert refused.value.code == 400
    assert nous.clear(hmz, "clever")["nous"] == []
    with pytest.raises(RpcError) as refused:
        nous.clear(hmz, "clever")
    assert refused.value.code == 404
