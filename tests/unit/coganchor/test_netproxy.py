"""Which of the agent's own connections are sent through the target, with no socket opened."""

from __future__ import annotations

import selectors
import socket
import threading
import types
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.netproxy import NetProxy

if TYPE_CHECKING:
    from collections.abc import Iterator


class Sock:
    """A socket that is never one: it records what it was told, and is given a port."""

    ports = iter(range(40000, 50000))

    def __init__(self, family: int = socket.AF_INET, kind: int = 0) -> None:
        self.family = family
        self.bound: tuple[str, int] | None = None
        self.closed = False
        self.woke = threading.Event()

    def setsockopt(self, *args: Any) -> None:
        pass

    def bind(self, address: tuple[str, int]) -> None:
        self.bound = (address[0], next(Sock.ports))

    def listen(self, backlog: int) -> None:
        pass

    def setblocking(self, flag: bool) -> None:
        pass

    def getsockname(self) -> tuple[str, int]:
        assert self.bound is not None
        return self.bound

    def send(self, data: bytes) -> int:
        self.woke.set()
        return len(data)

    def recv(self, size: int) -> bytes:
        return b""

    def close(self) -> None:
        self.closed = True


class Selector:
    """Waits for nothing but the proxy being told to stop."""

    def __init__(self) -> None:
        self.registered: list[Any] = []
        self.closed = threading.Event()
        self.stopping = threading.Event()

    def register(self, fileobj: Any, events: int, data: Any = None) -> None:
        self.registered.append((fileobj, data))

    def unregister(self, fileobj: Any) -> None:
        pass

    def select(self, timeout: float | None = None) -> list[Any]:
        self.stopping.wait(timeout)
        return []

    def close(self) -> None:
        self.closed.set()


class World:
    """What the proxy has been given in place of sockets, selectors and a resolver."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.made: list[Sock] = []
        self.selector = Selector()
        self.wake = Sock()
        self.names: dict[str, list[str]] = {
            "api.example": ["203.0.113.5", "2001:db8::5"]
        }

        def make(family: int = socket.AF_INET, kind: int = 0) -> Sock:
            one = Sock(family, kind)
            self.made.append(one)
            return one

        def resolve(host: str, *args: Any, **kwargs: Any) -> list[Any]:
            if host not in self.names:
                raise socket.gaierror(socket.EAI_NONAME, "unknown")
            return [(0, 0, 0, "", (one, 0)) for one in self.names[host]]

        # The proxy's own names for the two modules, so that nothing else in this process
        # -- another thread included -- is handed these in place of the real ones.
        sockets = types.SimpleNamespace(**vars(socket))
        sockets.socket = make
        sockets.socketpair = lambda: (Sock(), self.wake)
        sockets.getaddrinfo = resolve
        selecting = types.SimpleNamespace(**vars(selectors))
        selecting.DefaultSelector = lambda: self.selector
        monkeypatch.setattr("hmz.coganchor.netproxy.socket", sockets)
        monkeypatch.setattr("hmz.coganchor.netproxy.selectors", selecting)

    def stop(self, proxy: NetProxy) -> None:
        proxy.close()
        assert self.wake.woke.wait(5)
        self.selector.stopping.set()
        assert self.selector.closed.wait(5)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    return World(monkeypatch)


@pytest.fixture
def running(world: World) -> Iterator[NetProxy]:
    proxy = NetProxy(object(), ("api.example", "198.51.100.7:443", "nowhere.invalid"))  # pyright: ignore[reportArgumentType]
    proxy.start()
    yield proxy
    world.stop(proxy)


def test_nothing_is_redirected_before_it_starts(world: World) -> None:
    proxy = NetProxy(object())  # pyright: ignore[reportArgumentType]
    assert proxy.redirect("203.0.113.9", 80, socket.AF_INET) is None
    assert world.made == []


@pytest.mark.parametrize(
    ("host", "port"),
    [
        ("127.0.0.1", 80),
        ("::1", 80),
        ("169.254.1.1", 80),
        ("fe80::1", 80),
        ("0.0.0.0", 80),  # noqa: S104 -- a destination, not a bind
        ("203.0.113.5", 443),
        ("2001:db8::5", 443),
        ("198.51.100.7", 443),
        ("api.example", 1),
    ],
)
def test_what_must_stay_here_is_left_alone(
    running: NetProxy, host: str, port: int
) -> None:
    assert running.redirect(host, port, socket.AF_INET) is None


def test_an_allowed_host_is_allowed_on_its_port_alone(running: NetProxy) -> None:
    assert running.redirect("198.51.100.7", 80, socket.AF_INET) is not None


def test_a_connection_elsewhere_is_sent_to_a_listener_of_its_own(
    running: NetProxy, world: World
) -> None:
    first = running.redirect("203.0.113.9", 80, socket.AF_INET)
    again = running.redirect("203.0.113.9", 80, socket.AF_INET)
    other = running.redirect("203.0.113.9", 81, socket.AF_INET)
    assert first is not None
    assert other is not None
    assert first == again
    assert first[0] == "127.0.0.1"
    assert first[1] != other[1]
    assert len(world.made) == 2
    destinations = [data for _, data in world.selector.registered if data is not None]
    assert destinations == [("203.0.113.9", 80), ("203.0.113.9", 81)]


def test_the_listener_is_in_the_callers_own_family(running: NetProxy) -> None:
    found = running.redirect("2001:db8::9", 80, socket.AF_INET6)
    assert found is not None
    assert found[0] == "::1"


def test_stopping_closes_every_listener(world: World) -> None:
    proxy = NetProxy(object())  # pyright: ignore[reportArgumentType]
    proxy.start()
    proxy.redirect("203.0.113.9", 80, socket.AF_INET)
    world.stop(proxy)
    assert all(one.closed for one in world.made)
    assert proxy.redirect("203.0.113.9", 80, socket.AF_INET) is None
