"""`hmz internal anchor` as a command line: what it refuses, and where it routes what it accepts.

Both halves are here. `serve` is answered first and without loading the agent half at all,
which is what lets one program serve a target of any architecture -- so everything below runs
in this process on any machine, rather than through the zipapp the end-to-end suites push.

Most of what this file is about is refusals, and one of them is the door: a target left
listening on an address anything can reach, with no secret asked for, is a shell on that
machine offered to whoever finds the port.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from hmz.cli.anchor import anchor

if TYPE_CHECKING:
    from pathlib import Path

    from hmz.coganchor.serve.exports import ExportTable


#: The address that is the whole point of the refusal below -- everything that can reach this
#: machine can reach a target left on it, which is why a secret stops being optional there.
EVERYWHERE = "0.0.0.0"  # noqa: S104


class _Listened:
    """What `serve_forever` was asked for, instead of it actually listening."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, ExportTable, str | None]] = []
        self.raises: OSError | None = None

    def __call__(
        self, host: str, port: int, table: ExportTable, token: str | None
    ) -> None:
        self.calls.append((host, port, table, token))
        if self.raises is not None:
            raise self.raises


@pytest.fixture
def listened(monkeypatch: pytest.MonkeyPatch) -> _Listened:
    """Stands in for the listener, which is another tier's to actually run.

    A port bound for real is `tests/integration/coganchor/test_listener.py`; what is
    checked here is only what a command line hands it.
    """
    from hmz.coganchor.serve import listener

    held = _Listened()
    monkeypatch.setattr(listener, "serve_forever", held)
    return held


@pytest.fixture
def exported(tmp_path: Path) -> str:
    """One directory to export, as `--export` takes it."""
    target = tmp_path / "target"
    target.mkdir()
    return f"/project:{target}"


# --------------------------------------------------------------- what it refuses


def test_a_directory_that_is_not_an_export_is_a_bad_argument(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert anchor(["serve", "--export", "", "--stdio"]) == 2

    assert "hmz:" in capsys.readouterr().err


@pytest.mark.parametrize(
    "listen",
    [
        "not-a-port",
        "127.0.0.1:not-a-port",
        "127.0.0.1:70000",
        "127.0.0.1:-1",
        "127.0.0.1:",
    ],
)
def test_an_address_that_is_not_one_is_a_bad_argument(
    listen: str, exported: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert anchor(["serve", "--export", exported, "--listen", listen]) == 2

    assert "malformed listen address" in capsys.readouterr().err


def test_listening_where_anything_can_reach_it_without_a_secret_is_refused(
    exported: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An `hmz internal anchor` port is equivalent to a shell on that machine."""
    monkeypatch.delenv("HUMANIZE_TOKEN", raising=False)

    assert anchor(["serve", "--export", exported, f"--listen={EVERYWHERE}:8080"]) == 2

    assert "refusing to listen" in capsys.readouterr().err


def test_serving_over_a_pipe_and_over_a_port_at_once_is_refused(exported: str) -> None:
    """One session or many, and the far end has already been started for one of the two."""
    with pytest.raises(SystemExit) as stopped:
        anchor(["serve", "--export", exported, "--stdio", "--listen", "8080"])

    assert stopped.value.code == 2


def test_serving_neither_way_is_refused(exported: str) -> None:
    with pytest.raises(SystemExit) as stopped:
        anchor(["serve", "--export", exported])

    assert stopped.value.code == 2


def test_serving_nothing_at_all_is_refused() -> None:
    """There is no default export: what a session may name is the whole of what it may do."""
    with pytest.raises(SystemExit) as stopped:
        anchor(["serve", "--stdio"])

    assert stopped.value.code == 2


# ------------------------------------------------------------ what it accepts


def test_a_port_on_its_own_is_listened_for_on_the_loopback(
    exported: str, listened: _Listened
) -> None:
    """Which is the address nothing off this machine can reach, so it needs no secret."""
    assert anchor(["serve", "--export", exported, "--listen", "8080"]) == 0

    (host, port, _, token) = listened.calls[0]
    assert (host, port, token) == ("127.0.0.1", 8080, None)


def test_an_address_given_whole_is_the_one_listened_on(
    exported: str, listened: _Listened
) -> None:
    assert anchor(["serve", "--export", exported, "--listen", "127.0.0.1:9000"]) == 0

    assert listened.calls[0][:2] == ("127.0.0.1", 9000)


def test_an_ipv6_address_is_unwrapped_from_the_brackets_it_is_written_in(
    exported: str, listened: _Listened
) -> None:
    """`[::1]:9000` is how a host with colons in it is told apart from the port."""
    assert anchor(["serve", "--export", exported, "--listen", "[::1]:9000"]) == 0

    assert listened.calls[0][:2] == ("::1", 9000)


def test_an_address_anything_can_reach_is_listened_on_once_a_secret_is_asked_for(
    exported: str, listened: _Listened
) -> None:
    assert (
        anchor(
            [
                "serve",
                "--export",
                exported,
                f"--listen={EVERYWHERE}:8080",
                "--token",
                "not-a-real-shared-secret",
            ]
        )
        == 0
    )

    assert listened.calls[0][0] == EVERYWHERE
    assert listened.calls[0][3] == "not-a-real-shared-secret"


def test_the_secret_is_taken_from_the_environment_where_the_line_does_not_say(
    exported: str, listened: _Listened, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A secret on a command line is a secret in whatever reads that machine's processes."""
    monkeypatch.setenv("HUMANIZE_TOKEN", "out-of-the-environment")

    assert anchor(["serve", "--export", exported, f"--listen={EVERYWHERE}:8080"]) == 0

    assert listened.calls[0][3] == "out-of-the-environment"


def test_a_port_zero_asks_for_whichever_one_is_free(
    exported: str, listened: _Listened
) -> None:
    assert anchor(["serve", "--export", exported, "--listen", "0"]) == 0

    assert listened.calls[0][1] == 0


def test_an_address_that_cannot_be_listened_on_is_reported_rather_than_raised(
    exported: str, listened: _Listened, capsys: pytest.CaptureFixture[str]
) -> None:
    import errno

    listened.raises = OSError(errno.EADDRINUSE, "Address already in use")

    assert anchor(["serve", "--export", exported, "--listen", "8080"]) == 1

    said = capsys.readouterr().err
    assert "cannot listen on 127.0.0.1:8080" in said
    assert "Address already in use" in said


# ------------------------------------------------------------- the agent half


def test_running_no_agent_at_all_is_a_bad_argument() -> None:
    with pytest.raises(SystemExit) as stopped:
        anchor([])

    assert stopped.value.code == 2


def test_settings_a_session_could_not_be_run_under_are_bad_arguments_too() -> None:
    """Exit 2 the way argparse's own rejections do, rather than as a session that failed."""
    with pytest.raises(SystemExit) as stopped:
        anchor(["--target", "nonsense://nowhere", "bash"])

    assert stopped.value.code == 2


def test_a_target_that_cannot_be_reached_is_reported_rather_than_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from hmz.coganchor import anchor as connecting

    def refuses(*_: Any, **__: Any) -> dict[str, Any]:
        raise ConnectionRefusedError("nothing is listening there")

    monkeypatch.setattr(connecting, "check", refuses)

    assert anchor(["--target", f"local:{tmp_path}", "--check"]) == 1

    assert "nothing is listening there" in capsys.readouterr().err


def test_what_a_target_answers_is_printed_a_line_at_a_time(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--check` is for a person reading it, so it is lines rather than the reply itself."""
    from hmz.coganchor import anchor as connecting

    def answers(*_: Any, **__: Any) -> dict[str, Any]:
        return {
            "target": "local:/somewhere",
            "hostname": "a-machine",
            "python": "3.12.3",
            "pid": 4321,
            "exports": [{"virtual": "/project", "real": "/somewhere/project"}],
            "workspace": "/project",
            "entries": 7,
        }

    monkeypatch.setattr(connecting, "check", answers)

    assert anchor(["--target", f"local:{tmp_path}", "--check"]) == 0

    said = capsys.readouterr().out
    assert "target      local:/somewhere" in said
    assert "hostname    a-machine" in said
    assert "python      3.12.3 (pid 4321)" in said
    assert "export      /project -> /somewhere/project" in said
    assert "workspace   /project (7 entries)" in said


def test_a_target_that_answers_nothing_about_itself_is_still_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """An older target says less about itself, which is a shorter report and not a crash."""
    from hmz.coganchor import anchor as connecting

    def sparsely(*_: Any, **__: Any) -> dict[str, Any]:
        return {"target": "local:/somewhere", "workspace": "/project", "entries": 0}

    monkeypatch.setattr(connecting, "check", sparsely)

    assert anchor(["--target", f"local:{tmp_path}", "--check"]) == 0

    said = capsys.readouterr().out
    assert "hostname    None" in said
    assert "workspace   /project (0 entries)" in said


def test_a_session_interrupted_at_the_keyboard_says_so_the_way_a_shell_does(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """128 plus SIGINT, which is what every program a person stops exits with."""
    from hmz.coganchor import anchor as connecting

    def interrupted(*_: Any, **__: Any) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(connecting, "connect", interrupted)

    assert anchor(["--target", f"local:{tmp_path}", "bash"]) == 130


# ------------------------------------------------------- the third way one is served


def test_serving_to_a_meeting_is_one_of_the_three_ways_and_only_one(
    exported: str,
) -> None:
    """A half already spoken for is spoken for once: a pipe, a port, or a ticket."""
    for also in (["--stdio"], ["--listen", "8080"]):
        with pytest.raises(SystemExit) as stopped:
            anchor(["serve", "--export", exported, "--peer", "cafe@broker:9001", *also])
        assert stopped.value.code == 2


def test_a_meeting_that_is_not_one_is_reported_rather_than_raised(
    exported: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """The ticket and the broker are one word, so half of one is a line that cannot run."""
    assert anchor(["serve", "--export", exported, "--peer", "cafe@broker"]) == 1

    assert "TICKET@HOST:PORT" in capsys.readouterr().err


# ------------------------------------------------------------ the meeting place


class _Held:
    """What a broker was built with, instead of one actually listening."""

    def __init__(self) -> None:
        self.made: list[tuple[str, int, float]] = []

    def __call__(self, host: str, port: int, *, punching: float) -> _Held:
        self.made.append((host, port, punching))
        return self

    def start(self) -> tuple[str, int]:
        return self.made[-1][0], self.made[-1][1] or 40404

    def serve_forever(self) -> None:
        """Answered by returning, a broker under test having nobody to introduce."""


@pytest.fixture
def broker(monkeypatch: pytest.MonkeyPatch) -> _Held:
    """Stands in for the broker, which is another tier's to actually run."""
    from hmz.coganchor import rendezvous

    held = _Held()
    monkeypatch.setattr(rendezvous, "Broker", held)
    return held


def test_a_rendezvous_listens_where_both_halves_can_reach_it(broker: _Held) -> None:
    """Every interface by default, unlike `serve`: the halves are on other machines."""
    assert anchor(["rendezvous"]) == 0

    assert broker.made[0][:2] == (EVERYWHERE, 0)


def test_a_rendezvous_needs_no_secret_to_be_reachable(
    broker: _Held, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pairing is by a ticket nobody can guess, and there is nothing else to be let into.

    Which is the opposite of `serve` on the same address, and deliberately: a serving half is
    a shell on that machine, and a broker is two sockets it splices for whoever holds one
    secret it never issued.
    """
    assert anchor(["rendezvous", "--listen", f"{EVERYWHERE}:9001"]) == 0

    assert broker.made[0][:2] == (EVERYWHERE, 9001)
    # Announced rather than logged, so a port of 0 is usable from whatever started this.
    assert "rendezvous listening" in capsys.readouterr().err


def test_a_rendezvous_address_that_is_not_one_is_a_bad_argument(
    broker: _Held, capsys: pytest.CaptureFixture[str]
) -> None:
    assert anchor(["rendezvous", "--listen", "not-a-port"]) == 2

    assert "malformed listen address" in capsys.readouterr().err
    assert not broker.made


def test_how_long_two_halves_are_given_is_the_line_s_to_say(broker: _Held) -> None:
    """A window worth spending is a question about the network, not about humanize."""
    assert anchor(["rendezvous", "--punching", "0.5"]) == 0

    assert broker.made[0][2] == 0.5
