"""Whether humanize reports its own failures, and what a report may carry when it does."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import sentry_sdk
import yaml

from hmz.runtime import telemetry
from tests.unit.runtime import doubles_u12 as doubles

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator

#: What answers the question for one process, as the docs name it.
SAYS = "HUMANIZE_SENTRY"


class Scope:
    """One report's scope: the tags it was given and what was attached to it."""

    def __init__(self) -> None:
        self.tags: dict[str, str] = {}
        self.attached: dict[str, bytes] = {}

    def set_tag(self, name: str, value: str) -> None:
        self.tags[name] = value

    def add_attachment(self, *, bytes: bytes, filename: str) -> None:  # noqa: A002 -- the SDK's own keyword
        self.attached[filename] = bytes


class Sentry:
    """The SDK, as far as humanize reaches into it: nothing leaves the process."""

    def __init__(self) -> None:
        self.inits: list[dict[str, Any]] = []
        self.closed = 0
        self.scopes: list[Scope] = []
        self.exceptions: list[BaseException] = []
        self.messages: list[tuple[str, str]] = []
        self.refuses: Exception | None = None

    def init(self, **said: Any) -> None:
        if self.refuses is not None and said.get("dsn"):
            raise self.refuses
        self.inits.append(said)

    def get_client(self) -> Sentry:
        return self

    def close(self, timeout: float = 0.0) -> None:
        self.closed += 1

    @contextlib.contextmanager
    def isolation_scope(self) -> Generator[Scope]:
        scope = Scope()
        self.scopes.append(scope)
        yield scope

    def capture_exception(self, why: BaseException) -> None:
        self.exceptions.append(why)

    def capture_message(self, said: str, level: str = "") -> None:
        self.messages.append((said, level))

    @property
    def before_send(self) -> Callable[[Any, Any], Any]:
        return self.inits[-1]["before_send"]


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> Iterator[Sentry]:
    fake = Sentry()
    for name in (
        "init",
        "get_client",
        "isolation_scope",
        "capture_exception",
        "capture_message",
    ):
        monkeypatch.setattr(sentry_sdk, name, getattr(fake, name))
    try:
        yield fake
    finally:
        # Reporting started here is stopped here, so that no other test finds it on.
        telemetry.stop()


@pytest.fixture
def on(monkeypatch: pytest.MonkeyPatch, sent: Sentry) -> Sentry:
    monkeypatch.setenv(SAYS, "on")
    return sent


@pytest.fixture
def told() -> Iterator[Callable[[str, Callable[[], object]], None]]:
    """Registers something to attach, and leaves it out of every report afterwards."""
    names: list[str] = []

    def registers(name: str, said: Callable[[], object]) -> None:
        names.append(name)
        telemetry.about(name, said)

    def gone() -> object:
        raise LookupError

    yield registers
    for name in names:
        telemetry.about(name, gone)


# ------------------------------------------------------------------ the answer


@pytest.mark.parametrize("said", ["on", "1", "true", "YES", " On "])
def test_the_environment_says_yes_for_one_process(
    said: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    doubles.store(monkeypatch, {"enable_sentry": False})
    monkeypatch.setenv(SAYS, said)

    assert telemetry.enabled() is True


@pytest.mark.parametrize("said", ["off", "0", "false", "No"])
def test_the_environment_says_no_for_one_process(
    said: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    doubles.store(monkeypatch, {"enable_sentry": True})
    monkeypatch.setenv(SAYS, said)

    assert telemetry.enabled() is False


@pytest.mark.parametrize(
    ("stored", "answer"),
    [({}, None), ({"enable_sentry": True}, True), ({"enable_sentry": False}, False)],
)
def test_otherwise_what_was_written_down_is_the_answer(
    stored: dict[str, Any], answer: bool | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    doubles.store(monkeypatch, stored)
    monkeypatch.setenv(SAYS, "maybe")

    assert telemetry.enabled() is answer


def test_what_was_written_down_is_read_once_until_forgotten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(SAYS)
    held = doubles.store(monkeypatch, {"enable_sentry": True})
    assert telemetry.enabled() is True

    held.held["enable_sentry"] = False
    assert telemetry.enabled() is True

    telemetry.again()
    assert telemetry.enabled() is False


def test_answering_yes_writes_it_down_and_starts_reporting(
    monkeypatch: pytest.MonkeyPatch, sent: Sentry
) -> None:
    monkeypatch.delenv(SAYS)
    held = doubles.store(monkeypatch)

    telemetry.asked(enable_sentry=True)

    assert held.held["enable_sentry"] is True
    assert telemetry.enabled() is True
    assert len(sent.inits) == 1
    assert sent.inits[0]["dsn"].startswith("https://")


def test_answering_no_writes_it_down_and_stops_what_was_reporting(
    monkeypatch: pytest.MonkeyPatch, sent: Sentry
) -> None:
    monkeypatch.delenv(SAYS)
    held = doubles.store(monkeypatch, {"enable_sentry": True})
    assert telemetry.start() is True

    telemetry.asked(enable_sentry=False)

    assert held.held["enable_sentry"] is False
    assert sent.closed == 1
    assert sent.inits[-1] == {"dsn": ""}
    telemetry.crash(RuntimeError("after"))
    assert sent.exceptions == []


def test_the_promise_is_said_in_words() -> None:
    assert all(isinstance(one, str) and one for one in telemetry.SENT)


# ------------------------------------------------------------------ starting


def test_nothing_starts_where_the_answer_is_no_or_nobody_asked(
    monkeypatch: pytest.MonkeyPatch, sent: Sentry
) -> None:
    assert telemetry.start() is False

    monkeypatch.delenv(SAYS)
    doubles.store(monkeypatch)
    telemetry.again()
    assert telemetry.start() is False
    assert sent.inits == []


def test_reporting_starts_once_with_nothing_about_the_person(on: Sentry) -> None:
    assert telemetry.start() is True
    assert telemetry.start() is True

    assert len(on.inits) == 1
    said = on.inits[0]
    assert said["send_default_pii"] is False
    assert said["include_local_variables"] is False
    assert said["enable_logs"] is False
    assert said["server_name"] == ""
    assert said["release"].startswith("hmz@")
    assert [type(one).__name__ for one in said["disabled_integrations"]] == [
        "ArgvIntegration"
    ]


def test_an_sdk_that_will_not_start_reports_nothing(on: Sentry) -> None:
    on.refuses = RuntimeError("no transport")

    assert telemetry.start() is False
    telemetry.snag("dead-key")
    assert on.messages == []


def test_stopping_what_never_started_does_nothing(sent: Sentry) -> None:
    telemetry.stop()

    assert sent.closed == 0
    assert sent.inits == []


# ------------------------------------------------------------------ reports


def test_a_crash_is_reported_with_its_tags_made_plain(on: Sentry) -> None:
    why = RuntimeError("boom")

    telemetry.crash(why, doing="a flow at /Users/alice/secret", key="sk-abcdefghijk1")

    assert on.exceptions == [why]
    assert on.scopes[0].tags == {"doing": "a flow at ~/secret", "key": "…"}


def test_a_snag_is_a_warning_named_for_what_happened(on: Sentry) -> None:
    telemetry.snag("dead-key", sheet="flows", where="/home/bob/x")

    assert on.messages == [("snag: dead-key", "warning")]
    assert on.scopes[0].tags == {"snag": "dead-key", "sheet": "flows", "where": "~/x"}


def test_nothing_is_reported_while_reporting_is_off(sent: Sentry) -> None:
    telemetry.crash(RuntimeError("boom"))
    telemetry.snag("dead-key")

    assert sent.scopes == []
    assert sent.exceptions == []
    assert sent.messages == []


def test_what_the_layers_said_is_attached_scrubbed_as_yaml(
    on: Sentry, told: Callable[[str, Callable[[], object]], None]
) -> None:
    told(
        "u12-run",
        lambda: {
            "flow": "ralph",
            "at": "/Users/carol/work",
            "keys": ["ghp_abcdefghijklmnop", 3],
            "/home/dan": ("x" * 600,),
        },
    )

    telemetry.crash(RuntimeError("boom"))

    said = yaml.safe_load(on.scopes[0].attached["u12-run.yaml"])
    assert said["flow"] == "ralph"
    assert said["at"] == "~/work"
    assert said["keys"] == ["…", 3]
    assert len(said["~"][0]) == 501
    assert said["~"][0].endswith("…")


def test_whatever_cannot_say_is_left_out_of_what_is_held(
    told: Callable[[str, Callable[[], object]], None],
) -> None:
    def cannot() -> object:
        raise RuntimeError("no")

    told("u12-fine", lambda: {"one": 1})
    told("u12-broken", cannot)

    found = telemetry.held()
    assert found["u12-fine"] == {"one": 1}
    assert "u12-broken" not in found


def test_registering_a_name_again_replaces_it(
    told: Callable[[str, Callable[[], object]], None],
) -> None:
    told("u12-twice", lambda: 1)
    told("u12-twice", lambda: 2)

    assert telemetry.held()["u12-twice"] == 2


# ------------------------------------------------------------- the last word


def _event(**more: Any) -> dict[str, Any]:
    return {
        "server_name": "alices-laptop",
        "user": {"ip_address": "10.0.0.1"},
        "request": {},
        "modules": {"x": "1"},
        "extra": {"sys.argv": ["hmz", "exec", "the task"]},
        "breadcrumbs": {"values": [{"message": "a log line"}]},
        **more,
    }


def test_what_is_sent_carries_nothing_about_the_machine(on: Sentry) -> None:
    telemetry.start()

    said = on.before_send(_event(), None)

    assert set(said) == set()


def test_an_exception_is_sent_without_its_frames_variables_or_paths(
    on: Sentry, tmp_path: Path
) -> None:
    telemetry.start()
    ours = Path(telemetry.__file__).resolve()
    theirs = tmp_path / "my-secret-project" / "flow.py"
    event = _event(
        exception={
            "values": [
                {
                    "value": "Command 'claude -p do the secret thing' returned non-zero"
                    " exit status 1 under /Users/eve/x",
                    "stacktrace": {
                        "frames": [
                            {
                                "abs_path": str(ours),
                                "filename": "telemetry.py",
                                "module": "hmz.runtime.telemetry",
                                "function": "crash",
                                "vars": {"task": "secret"},
                                "context_line": "secret()",
                                "pre_context": ["a"],
                                "post_context": ["b"],
                                "lineno": 3,
                            },
                            {
                                "abs_path": str(theirs),
                                "module": "my_secret_project",
                                "function": "secret_step",
                                "lineno": 9,
                            },
                            {"lineno": 1},
                        ]
                    },
                }
            ]
        }
    )

    said = on.before_send(event, None)

    one = said["exception"]["values"][0]
    assert one["value"] == "A command returned non-zero exit status 1 under ~/x"
    ours_frame, theirs_frame, nameless = one["stacktrace"]["frames"]
    assert ours_frame == {
        "abs_path": "hmz/runtime/telemetry.py",
        "filename": "hmz/runtime/telemetry.py",
        "module": "hmz.runtime.telemetry",
        "function": "crash",
        "lineno": 3,
    }
    assert theirs_frame == {
        "abs_path": "<not humanize>",
        "filename": "<not humanize>",
        "lineno": 9,
    }
    assert nameless["filename"] == "<not humanize>"


def test_a_credential_in_a_url_is_taken_out(on: Sentry) -> None:
    telemetry.crash(RuntimeError("x"), url="https://me:hunter2@example.com/repo")

    assert on.scopes[0].tags["url"] == "https://…@example.com/repo"
