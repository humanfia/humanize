"""`hmz.tui.pick`: making an account off its form, asking it what it runs, and the terminal."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import pytest
from textual.app import SuspendNotSupported

import hmz.daemon
from hmz.tui import pick
from tests.unit.tui import doubles_u14 as doubles

if TYPE_CHECKING:
    from collections.abc import Generator

    from textual.app import App


@dataclass
class _Way:
    argv: tuple[str, ...] = ()


@dataclass
class _Accounts:
    """The accounts store: ways in by name, and every call made of it."""

    ways: dict[tuple[str, str], _Way] = field(
        default_factory=dict[tuple[str, str], _Way]
    )
    makes: Exception | None = None
    signs: int | OSError = 0
    refuses: frozenset[str] = frozenset()
    runs: tuple[str, ...] | Exception = ()
    calls: list[tuple[Any, ...]] = field(default_factory=list[tuple[Any, ...]])

    def way(self, cli: str, way: str) -> _Way | None:
        return self.ways.get((cli, way))

    def make(self, cli: str, name: str, way: _Way, answers: dict[str, str]) -> str:
        self.calls.append(("make", cli, name, answers))
        if self.makes is not None:
            raise self.makes
        return f"{cli}:{name}"

    def sign_in(self, provider: str, way: _Way, answers: dict[str, str]) -> int:
        self.calls.append(("sign_in", provider))
        if isinstance(self.signs, OSError):
            raise self.signs
        return self.signs

    def copies(self, provider: str, cli: str) -> None:
        if cli in self.refuses:
            raise ValueError(cli)
        self.calls.append(("copies", provider, cli))

    def ask(self, cli: str, name: str) -> tuple[str, ...]:
        if isinstance(self.runs, Exception):
            raise self.runs
        return self.runs


@dataclass
class _Host:
    """The interface: answers the form with what it was given, and hands the terminal over."""

    answer: pick.Signs | None = None
    suspends: bool = True
    held: list[str] = field(default_factory=list[str])

    async def push_screen_wait(self, screen: object) -> pick.Signs | None:
        self.held.append(type(screen).__name__)
        return self.answer

    @contextlib.contextmanager
    def suspend(self) -> Generator[None]:
        if not self.suspends:
            raise SuspendNotSupported
        self.held.append("suspended")
        yield
        self.held.append("resumed")


@dataclass
class _Form:
    """The form an account is made on, which is the host's to answer here."""

    cli: str


@pytest.fixture
def accounts(monkeypatch: pytest.MonkeyPatch) -> _Accounts:
    monkeypatch.setattr(pick, "Signing", _Form)
    held = _Accounts(
        ways={("claude", "key"): _Way(), ("claude", "login"): _Way(("claude", "login"))}
    )
    monkeypatch.setattr(hmz.daemon, "Hmz", doubles.Hmz(accounts=held))
    return held


def _signs(way: str, also: tuple[str, ...] = ()) -> pick.Signs:
    return pick.Signs("work", {"KEY": "k"}, "claude", way, also)


async def _made(host: _Host) -> pick.Made:
    return await pick.made(cast("App[None]", host), "claude")


async def test_made_of_a_form_walked_out_of_is_nothing(accounts: _Accounts) -> None:
    host = _Host()

    assert await _made(host) == pick.Made()
    assert host.held == ["_Form"]
    assert accounts.calls == []


async def test_made_refuses_a_way_the_backend_has_not(accounts: _Accounts) -> None:
    made = await _made(_Host(_signs("sso")))

    assert made == pick.Made(why="sso is not a supported sign-in method for claude")
    assert accounts.calls == []


async def test_made_says_why_an_account_could_not_be_written(
    accounts: _Accounts,
) -> None:
    accounts.makes = ValueError("name taken")

    assert await _made(_Host(_signs("key"))) == pick.Made(why="name taken")


async def test_made_writes_down_a_way_that_runs_nothing_and_copies_it(
    accounts: _Accounts,
) -> None:
    accounts.refuses = frozenset({"codex"})
    host = _Host(_signs("key", ("codex", "opencode")))

    made = await _made(host)

    assert made == pick.Made(provider=cast("Any", "claude:work"), copied=("opencode",))
    assert "suspended" not in host.held
    assert accounts.calls[0] == ("make", "claude", "work", {"KEY": "k"})


@pytest.mark.parametrize(("status", "copied"), [(0, ("codex",)), (3, ())])
async def test_made_signs_in_with_the_terminal_handed_over(
    accounts: _Accounts, status: int, copied: tuple[str, ...]
) -> None:
    accounts.signs = status
    host = _Host(_signs("login", ("codex",)))

    made = await _made(host)

    assert made == pick.Made(
        provider=cast("Any", "claude:work"), status=status, way_runs=True, copied=copied
    )
    assert host.held == ["_Form", "suspended", "resumed"]


async def test_made_says_a_way_whose_command_is_missing(accounts: _Accounts) -> None:
    accounts.signs = FileNotFoundError("not found")

    made = await _made(_Host(_signs("login")))

    assert made == pick.Made(
        provider=cast("Any", "claude:work"), status=127, why="claude: not found"
    )


async def test_asks_counts_what_the_account_runs(accounts: _Accounts) -> None:
    accounts.runs = ("opus", "sonnet")

    assert await pick.asks("claude", "work") == (2, "")


@pytest.mark.parametrize(
    ("raised", "why"),
    [
        (RuntimeError("\x1b[31mlogged out\x1b[0m  "), "logged out"),
        (TimeoutError(), "TimeoutError"),
    ],
)
async def test_asks_says_why_an_account_would_not_say(
    accounts: _Accounts, raised: Exception, why: str
) -> None:
    accounts.runs = raised

    assert await pick.asks("claude", "work") == (0, why)


@pytest.mark.parametrize("suspends", [True, False])
def test_handed_over_runs_what_it_holds_whether_or_not_it_can_suspend(
    suspends: bool,
) -> None:
    host = _Host(suspends=suspends)
    ran: list[bool] = []

    with pick.handed_over(cast("App[None]", host)):
        ran.append(True)

    assert ran == [True]
    assert host.held == (["suspended", "resumed"] if suspends else [])
