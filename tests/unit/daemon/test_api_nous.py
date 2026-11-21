"""`hmz.daemon.api.nous`: a nous written whole, renamed and cleared, and what is refused."""

from __future__ import annotations

import threading
import time
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


class _Accounts:
    """Accounts that say what they are asked, each harness answering as it is told to."""

    def __init__(self, fresh: tuple[str, ...] = ()) -> None:
        self.asks: list[tuple[str, str]] = []
        self.fresh = fresh
        self.held = threading.Event()
        self.held.set()

    def all(self, cli: str = "") -> list[Any]:
        return [SimpleNamespace(cli="claude", name="work")] if cli == "claude" else []

    def models(self, cli: str, name: str = "") -> tuple[Any, ...]:
        return ()

    def stale(self, cli: str, name: str = "") -> bool:
        return cli not in self.fresh

    def ask(self, cli: str, name: str = "") -> tuple[Any, ...]:
        self.held.wait(5)
        self.asks.append((cli, name))
        if cli == "codex":
            raise OSError("codex is not signed in")
        return ()


def _scanned(accounts: _Accounts) -> Any:
    return SimpleNamespace(
        nous=_Book(),
        accounts=accounts,
        installed=lambda: {"claude": (), "codex": ()},
    )


def test_a_scan_asks_every_harness_as_every_account_and_says_who_would_not() -> None:
    accounts = _Accounts()

    said = nous.scan(_scanned(accounts))

    assert sorted(accounts.asks) == [("claude", ""), ("claude", "work"), ("codex", "")]
    assert said["failed"] == [
        {"cli": "codex", "account": "", "why": "codex is not signed in"}
    ]
    assert said["scanning"] is False
    assert said["concrete"] == []


def test_a_scan_of_the_stale_alone_leaves_what_was_asked_lately() -> None:
    accounts = _Accounts(fresh=("claude",))

    assert nous.scan(_scanned(accounts), stale=True)["failed"] == [
        {"cli": "codex", "account": "", "why": "codex is not signed in"}
    ]
    assert accounts.asks == [("codex", "")]


def test_a_scan_asked_for_while_one_is_going_waits_for_it_and_asks_nobody() -> None:
    accounts = _Accounts()
    accounts.held.clear()
    hmz = _scanned(accounts)
    answers: list[dict[str, Any]] = []
    first = threading.Thread(target=lambda: answers.append(nous.scan(hmz)))
    first.start()
    while not nous.listed(hmz)["scanning"]:
        time.sleep(0.01)
    second = threading.Thread(target=lambda: answers.append(nous.scan(hmz)))
    second.start()
    time.sleep(0.05)

    accounts.held.set()
    first.join(5)
    second.join(5)

    assert len(accounts.asks) == 3
    assert [one["failed"] for one in answers] == [answers[0]["failed"]] * 2
    assert nous.listed(hmz)["scanning"] is False


def test_the_scan_a_daemon_starts_with_is_turned_off_by_its_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[str] = []

    def starts(thread: threading.Thread) -> None:
        started.append(thread.name)

    monkeypatch.setattr(threading.Thread, "start", starts)

    for said in ("off", "0", "No", ""):
        monkeypatch.setenv("HUMANIZE_SCAN", said)
        nous.scans()
    assert started == []

    monkeypatch.delenv("HUMANIZE_SCAN")
    nous.scans()
    assert started == ["humanize-scan"]
