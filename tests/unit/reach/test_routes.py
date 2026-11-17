"""Routes are read by the grammar of Section 3.3 of wire.md, and written back as read."""

import pytest

from hmz.reach import KINDS, TRUSTED, Route


@pytest.mark.parametrize(
    ("text", "route"),
    [
        ("unix:", Route("unix")),
        ("unix:/run/a%20b/daemon.sock", Route("unix", path="/run/a b/daemon.sock")),
        ("stdio:local", Route("local")),
        ("stdio:ssh://box", Route("ssh", host="box")),
        (
            (
                "stdio:ssh://me@box.example:2222?identity=~%2F.ssh%2Fid&jump=j%40hop"
                "&option=ServerAliveInterval=5"
            ),
            Route(
                "ssh",
                host="box.example",
                port=2222,
                user="me",
                options=(
                    ("IdentityFile", "~/.ssh/id"),
                    ("ProxyJump", "j@hop"),
                    ("ServerAliveInterval", "5"),
                ),
            ),
        ),
        ("stdio:ssh://[::1]:22", Route("ssh", host="::1", port=22)),
        ("stdio:wsl", Route("wsl")),
        ("stdio:wsl:Ubuntu-22.04", Route("wsl", name="Ubuntu-22.04")),
        ("tcp://10.0.0.2:7000", Route("tcp", host="10.0.0.2", port=7000)),
        ("tcp://box:65535", Route("tcp", host="box", port=65535)),
        ("tcp://[fe80::1]:7000", Route("tcp", host="fe80::1", port=7000)),
        ("ws://box:80/hmz", Route("ws", url="ws://box:80/hmz")),
        ("wss://box", Route("ws", url="wss://box")),
        ("easytier:home.lab_1-a", Route("easytier", name="home.lab_1-a")),
        ("relay:wss://relay.example/r", Route("relay", url="wss://relay.example/r")),
        ("webrtc:ws://relay:8080", Route("webrtc", url="ws://relay:8080")),
    ],
)
def test_a_route_is_read_into_its_parts_and_written_back_as_it_was(
    text: str, route: Route
) -> None:
    assert Route.parse(text) == route
    assert str(route) == text
    assert route.kind in KINDS


@pytest.mark.parametrize(
    "text",
    [
        "",
        "unix",
        "unix:relative/path",
        "stdio:local:x",
        "stdio:ssh://box?",
        "stdio:ssh://box?port=22",
        "stdio:ssh://box?identity=~/.ssh/id",  # a slash is percent-encoded in a parameter
        "stdio:ssh://box?option=NoEquals",
        "stdio:ssh://box?option=1Bad=x",
        "stdio:ssh://box?option=Quoted=%22x%22",
        "stdio:ssh://box?identity=%0A",
        "stdio:ssh://a@b@c",
        "stdio:wsl:",
        "stdio:wsl:a/b",
        "tcp://box",
        "tcp://box:port",
        "tcp://[not-an-address]:1",
        "tcp://[fe80::1%25eth0]:1",
        "ws://box/a?query",
        "ws://box#fragment",
        "http://box",
        "easytier:",
        "easytier:-starts-badly",
        "relay:http://relay",
        "relay:",
        "webrtc:tcp://relay:1",
        "unix:/%ff",
        # Section 3.3.4: a port from 1 to 65535, and a host that is not empty.
        "tcp://box:",
        "tcp://box:0",
        "tcp://box:65536",
        "tcp://:1",
        "stdio:ssh://",
        "stdio:ssh://box:",
        "stdio:ssh://me@:22",
        "ws://box:0/hmz",
        "wss://:443",
        "relay:ws://relay:99999",
        "webrtc:wss://",
    ],
)
def test_text_the_grammar_does_not_match_is_not_a_route(text: str) -> None:
    with pytest.raises(ValueError, match=r"is not a route\.$") as refused:
        Route.parse(text)
    assert str(refused.value) == f"{text} is not a route."


def test_unix_stdio_ssh_and_wsl_are_trusted_and_every_other_carrier_is_not() -> None:
    assert {"unix", "local", "ssh", "wsl"} == TRUSTED
    for kind in KINDS:
        assert Route(kind).trusted == (kind in TRUSTED)


def test_an_option_naming_an_identity_or_a_jump_is_written_as_that_parameter() -> None:
    route = Route.parse("stdio:ssh://box?option=IdentityFile=k&option=ProxyJump=j")
    assert route.options == (("IdentityFile", "k"), ("ProxyJump", "j"))
    assert str(route) == "stdio:ssh://box?identity=k&jump=j"
    assert Route.parse(str(route)) == route


def test_a_name_holding_a_colon_is_written_encoded_not_as_an_ip_literal() -> None:
    route = Route.parse("tcp://a%3Ab:1")
    assert route.host == "a:b"
    assert str(route) == "tcp://a%3Ab:1"
    assert Route.parse(str(route)) == route
