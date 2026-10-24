"""Whether Humanize reports its own failures, and what a report may carry when it does."""

from __future__ import annotations

import contextlib
import time
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
    """The SDK, as far as Humanize reaches into it: nothing leaves the process."""

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
        "ArgvIntegration",
        "LoggingIntegration",
    ]
    assert said["auto_enabling_integrations"] is False


def test_nothing_is_timed_or_profiled(on: Sentry) -> None:
    telemetry.start()

    said = on.inits[0]
    assert said["traces_sample_rate"] == 0.0
    assert not {
        "profile_session_sample_rate",
        "profiles_sample_rate",
        "before_send_transaction",
        "transport",
    } & set(said)


def test_an_sdk_that_will_not_start_reports_nothing(on: Sentry) -> None:
    on.refuses = RuntimeError("no transport")

    assert telemetry.start() is False
    telemetry.crash(RuntimeError("boom"))
    assert on.exceptions == []


def test_stopping_what_never_started_does_nothing(sent: Sentry) -> None:
    telemetry.stop()

    assert sent.closed == 0
    assert sent.inits == []


# ------------------------------------------------------------------ reports


def test_a_crash_is_reported_with_its_tags_made_plain(on: Sentry) -> None:
    telemetry.start()
    why = RuntimeError("boom")

    telemetry.crash(why, doing="a flow at /Users/alice/secret", key="sk-abcdefghijk1")

    assert on.exceptions == [why]
    assert on.scopes[0].tags == {"doing": "a flow at ~/secret", "key": "…"}


def test_nothing_is_reported_while_reporting_is_off(sent: Sentry) -> None:
    telemetry.crash(RuntimeError("boom"))

    assert sent.scopes == []
    assert sent.exceptions == []
    assert sent.messages == []


def test_nothing_is_reported_by_a_process_that_never_started_reporting(
    on: Sentry,
) -> None:
    telemetry.crash(RuntimeError("boom"))

    assert on.inits == []
    assert on.exceptions == []
    assert on.messages == []


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

    telemetry.start()
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
        "abs_path": "<not Humanize>",
        "filename": "<not Humanize>",
        "lineno": 9,
    }
    assert nameless["filename"] == "<not Humanize>"


def test_a_credential_in_a_url_is_taken_out(on: Sentry) -> None:
    telemetry.start()
    telemetry.crash(RuntimeError("x"), url="https://me:hunter2@example.com/repo")

    assert on.scopes[0].tags["url"] == "https://…@example.com/repo"


@pytest.mark.parametrize(
    "key",
    [
        "ghs_abcdefghijklmnop",
        "glpat-abcdefghijklmnop",
        "hf_abcdefghijklmnopqr",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N",
        "Bearer abcdefghijklmnopqrstuvwxyz",
        "https://up.example/x?X-Amz-Signature=abcdef0123",
    ],
)
def test_every_credential_a_bundle_strikes_a_report_strikes(
    key: str, on: Sentry
) -> None:
    telemetry.start()

    telemetry.crash(RuntimeError("x"), said=f"failed with {key} here")

    tag = on.scopes[0].tags["said"]
    assert tag.startswith("failed with ")
    assert tag.endswith("… here")
    assert "abcdef" not in tag
    assert "dozjg" not in tag


def test_struck_out_is_said_by_whoever_asks() -> None:
    said = telemetry.scrubbed(
        'auth: Bearer abcdefghijklmnopqrstuvwx, "api_key": "s3cr3tv4lue"',
        "[gone]",
    )

    assert said == 'auth: Bearer [gone], "api_key": "[gone]"'


# ------------------------------------------------------------- once apiece


def _crash(kind: str, line: int) -> dict[str, Any]:
    ours = str(Path(telemetry.__file__).resolve())
    frame = {"abs_path": ours, "lineno": line}
    return {
        "exception": {"values": [{"type": kind, "stacktrace": {"frames": [frame]}}]}
    }


def test_a_crash_is_sent_once_per_kind_and_place(on: Sentry) -> None:
    telemetry.start()

    assert on.before_send(_crash("UniqueOneError", 11), None) is not None
    assert on.before_send(_crash("UniqueOneError", 11), None) is None
    assert on.before_send(_crash("UniqueOneError", 12), None) is not None
    assert on.before_send(_crash("UniqueTwoError", 11), None) is not None


def test_what_is_not_a_crash_is_never_held_back(on: Sentry) -> None:
    telemetry.start()

    assert on.before_send({"message": "halt: no progress"}, None) is not None
    assert on.before_send({"message": "halt: no progress"}, None) is not None


# ------------------------------------------------------------- standing still


@pytest.fixture
def quick(monkeypatch: pytest.MonkeyPatch) -> float:
    """A halt measured in hundredths of a second rather than minutes."""
    monkeypatch.setattr(telemetry, "HALT", 0.05)
    return 0.05


def _waits(until: Callable[[], bool], *, seconds: float = 2.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if until():
            return True
        time.sleep(0.01)
    return until()


def test_a_run_that_stands_still_is_reported_once(on: Sentry, quick: float) -> None:
    telemetry.start()

    with telemetry.Still("a flow"):
        assert _waits(lambda: bool(on.messages))
        time.sleep(quick * 4)

    assert on.messages == [("halt: no progress", "error")]
    assert on.scopes[0].tags["doing"] == "a flow"
    assert int(on.scopes[0].tags["still"]) >= 0


def test_a_run_that_keeps_moving_is_not_reported(
    on: Sentry, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A whole second to stand still in, against stirs a few hundredths apart: a runner that
    # oversleeps by tenfold still stirs in time.
    monkeypatch.setattr(telemetry, "HALT", 1.0)
    telemetry.start()

    with telemetry.Still("a flow") as still:
        for _ in range(12):
            time.sleep(0.05)
            still.stirred()

    assert on.messages == []


def test_a_run_waiting_on_a_person_is_not_reported(on: Sentry, quick: float) -> None:
    telemetry.start()

    with telemetry.Still("a flow") as still, still.away():
        time.sleep(quick * 4)

    assert on.messages == []


def test_nothing_watches_a_run_where_reporting_never_started(
    on: Sentry, quick: float
) -> None:
    with telemetry.Still("a flow"):
        time.sleep(quick * 3)

    assert on.messages == []
