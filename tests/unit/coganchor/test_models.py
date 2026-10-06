"""`hmz.coganchor.models`: what each backend runs, asked of it and kept per account.

Asking starts a coding agent, so every test that asks takes the `asking` fixture and answers
in place of the agent: `subprocess.run` is replaced by a fake that never starts anything, and
an endpoint is answered by a fake opener that never reaches a socket.
"""

from __future__ import annotations

import datetime
import importlib.util
import io
import json
import subprocess
import types
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, Self

import pytest

from hmz import machine
from hmz.coganchor import backends, models
from hmz.coganchor.backends import Model

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


class Ran:
    """What a fake backend was asked, and what it answers."""

    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.argv: list[str] = []
        self.input = ""
        self.env: dict[str, str] = {}
        self.calls = 0

    def __call__(
        self, argv: list[str], **given: Any
    ) -> subprocess.CompletedProcess[str]:
        self.calls += 1
        self.argv = argv
        self.input = given.get("input") or ""
        self.env = given.get("env") or {}
        return subprocess.CompletedProcess(
            argv, self.returncode, self.stdout, self.stderr
        )


@pytest.fixture
def backend(asking: None, monkeypatch: pytest.MonkeyPatch) -> Callable[..., Ran]:
    """Answers for the backend `ask` would start, with every endpoint it could ask unset."""
    for profile in backends.PROFILES:
        if profile.endpoint:
            monkeypatch.delenv(profile.endpoint, raising=False)

    def answering(stdout: str = "", returncode: int = 0, stderr: str = "") -> Ran:
        ran = Ran(stdout, returncode, stderr)
        monkeypatch.setattr(
            models,
            "subprocess",
            types.SimpleNamespace(run=ran, TimeoutExpired=subprocess.TimeoutExpired),
        )
        return ran

    return answering


def _kept(cli: str, said: dict[str, Any], provider: str = "") -> Path:
    at = models.where(cli, provider)
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text(json.dumps(said), encoding="utf-8")
    return at


def _stamp(when: datetime.datetime) -> str:
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_the_suite_never_asks_unless_a_test_says_so() -> None:
    with pytest.raises(AssertionError, match="does not start"):
        models.ask("claude")


@pytest.mark.parametrize(
    ("cli", "provider", "under"),
    [
        ("claude", "", "claude/_local.json"),
        ("claude-code", "", "claude/_local.json"),
        ("codex", "work", "codex/work.json"),
    ],
)
def test_where_is_per_backend_and_account(cli: str, provider: str, under: str) -> None:
    assert models.where(cli, provider) == machine() / "models" / under


@pytest.mark.parametrize(
    ("cli", "provider", "why"),
    [
        ("nobody", "", "no such coding agent"),
        ("claude", "../up", "not a valid account"),
    ],
)
def test_where_refuses_what_is_not_a_backend_or_an_account(
    cli: str, provider: str, why: str
) -> None:
    with pytest.raises(ValueError, match=why):
        models.where(cli, provider)


def test_a_backend_never_asked_offers_nothing_and_is_stale() -> None:
    assert models.offered("claude") == ()
    assert models.asked("claude") == ""
    assert models.stale("claude")


def test_offered_for_an_unknown_backend_is_nothing() -> None:
    assert models.offered("nobody") == ()


@pytest.mark.parametrize("cli", ["dsh", "qwen"])
def test_a_backend_with_an_advisory_list_offers_it_unasked(cli: str) -> None:
    profile = backends.named(cli)
    assert profile is not None
    offered = models.offered(cli)
    assert offered
    assert all(one.efforts == profile.efforts for one in offered)


def test_an_added_cli_offers_one_row_to_be_configured_by() -> None:
    backends.remember("my-agent", ["my-agent", "--acp"])
    assert models.offered("my-agent") == (Model("as configured", ("as configured",)),)


def test_offered_reads_back_what_was_kept() -> None:
    _kept(
        "claude",
        {
            "asked": _stamp(datetime.datetime.now(datetime.UTC)),
            "models": [
                {"name": "claude-opus-5", "efforts": ["max", "high"], "swarms": True},
                {"name": "claude-haiku-5", "efforts": list[str]()},
                {"name": "", "efforts": list[str]()},
                {"name": "no-efforts"},
                "junk",
            ],
        },
    )
    assert models.offered("claude-code") == (
        Model("claude-opus-5", ("max", "high"), swarms=True),
        Model("claude-haiku-5", ()),
    )
    assert not models.stale("claude")


@pytest.mark.parametrize("said", ["not json", "[1, 2]", '{"models": "nope"}'])
def test_a_kept_list_that_cannot_be_read_offers_nothing(said: str) -> None:
    at = models.where("codex")
    at.parent.mkdir(parents=True)
    at.write_text(said, encoding="utf-8")
    assert models.offered("codex") == ()
    assert models.asked("codex") == ""


@pytest.mark.parametrize(
    ("asked", "stale"),
    [
        (datetime.timedelta(days=1), False),
        (models.STALE + datetime.timedelta(minutes=1), True),
    ],
)
def test_stale_after_a_week(asked: datetime.timedelta, stale: bool) -> None:
    when = _stamp(datetime.datetime.now(datetime.UTC) - asked)
    _kept("codex", {"asked": when, "models": []})
    assert models.asked("codex") == when
    assert models.stale("codex") is stale


@pytest.mark.parametrize("asked", ["yesterday", 12345])
def test_an_unreadable_moment_is_stale(asked: object) -> None:
    _kept("codex", {"asked": asked, "models": []})
    assert models.stale("codex")


def test_ask_refuses_a_backend_there_is_not(backend: Callable[..., Ran]) -> None:
    with pytest.raises(ValueError, match="no such coding agent"):
        models.ask("nobody")


def test_ask_refuses_an_added_cli_that_cannot_be_asked(
    backend: Callable[..., Ran],
) -> None:
    backends.remember("my-agent", ["my-agent"])
    with pytest.raises(ValueError, match="no way of being asked"):
        models.ask("my-agent")


def test_ask_refuses_an_account_the_backend_does_not_have(
    backend: Callable[..., Ran],
) -> None:
    with pytest.raises(ValueError, match="no account called"):
        models.ask("codex", "nobody-made-me")


def _claude_says(*answers: dict[str, Any]) -> str:
    lines = ["not json", json.dumps(["a list"]), json.dumps({"type": "other"})]
    lines += [
        json.dumps({"type": "control_response", "response": one}) for one in answers
    ]
    return "\n".join(lines) + "\n"


def test_ask_claude_reads_its_control_response(backend: Callable[..., Ran]) -> None:
    ran = backend(
        _claude_says(
            {"request_id": "someone-else", "subtype": "error"},
            {
                "request_id": "models",
                "subtype": "success",
                "response": {
                    "models": [
                        {
                            "value": "opus",
                            "resolvedModel": "claude-opus-5[1m]",
                            "supportedEffortLevels": ["high", "low", "nonsense"],
                        },
                        {"value": "default", "resolvedModel": "claude-opus-5"},
                        {
                            "value": "my-alias",
                            "resolvedModel": "claude-sonnet-5",
                            "description": "Custom model from the environment",
                        },
                        {"value": "haiku", "supportedEffortLevels": ["nonsense"]},
                        "junk",
                    ]
                },
            },
        )
    )
    profile = backends.named("claude")
    assert profile is not None

    found = models.ask("claude")

    # The rung it takes but never lists is kept on a ladder that was narrowed.
    assert found == (
        Model("claude-opus-5", ("ultracode", "high", "low")),
        Model("my-alias", profile.efforts),
        Model("haiku", ("ultracode",)),
    )
    assert ran.argv[1:] == [
        "-p",
        "--input-format",
        "stream-json",
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    assert json.loads(ran.input)["request"] == {"subtype": "list_models"}
    assert models.offered("claude") == found
    assert not models.stale("claude")


@pytest.mark.parametrize(
    ("said", "why"),
    [
        (
            _claude_says({"request_id": "models", "subtype": "error", "error": "nope"}),
            "nope",
        ),
        (_claude_says({"request_id": "models", "subtype": "error"}), "would not say"),
        ("nothing at all\n", "said nothing"),
    ],
)
def test_ask_claude_refused_says_why(
    backend: Callable[..., Ran], said: str, why: str
) -> None:
    backend(said)
    with pytest.raises(ValueError, match=why):
        models.ask("claude")
    assert models.offered("claude") == ()


def test_ask_codex_reads_the_listed_models(backend: Callable[..., Ran]) -> None:
    ran = backend(
        json.dumps(
            {
                "models": [
                    {
                        "slug": "gpt-5.6-sol",
                        "visibility": "list",
                        "supported_reasoning_levels": [
                            {"effort": "high"},
                            {"effort": "low"},
                        ],
                    },
                    {"slug": "review-only", "visibility": "hide"},
                    {"slug": "gpt-5", "visibility": "list"},
                ]
            }
        )
    )
    profile = backends.named("codex")
    assert profile is not None
    assert models.ask("codex") == (
        Model("gpt-5.6-sol", ("high", "low")),
        Model("gpt-5", profile.efforts),
    )
    assert ran.argv[1:] == ["debug", "models"]


@pytest.mark.parametrize(
    ("said", "error"), [("not json", ValueError), ("[1]", TypeError)]
)
def test_ask_codex_that_says_something_else(
    backend: Callable[..., Ran], said: str, error: type[Exception]
) -> None:
    backend(said)
    with pytest.raises(error):
        models.ask("codex")


def test_ask_kimi_reads_its_providers(backend: Callable[..., Ran]) -> None:
    backend(
        json.dumps(
            {
                "models": {
                    "kimi-k3": {"supportEfforts": ["max", "low"]},
                    "moonshot/other": {},
                }
            }
        )
    )
    profile = backends.named("kimi")
    assert profile is not None
    assert models.ask("kimi-code") == (
        Model("kimi-k3", ("max", "low"), swarms=True),
        Model("moonshot/other", profile.efforts, swarms=True),
    )


def test_ask_pi_reads_its_table(backend: Callable[..., Ran]) -> None:
    profile = backends.named("pi")
    assert profile is not None
    backend(
        "provider  model           context\n"
        "anthropic claude-opus-5   1M\n"
        "\n"
        "lonely\n"
        "openai    gpt-5.6-sol     400K\n"
    )
    assert [one.name for one in models.ask("pi")] == [
        "anthropic/claude-opus-5",
        "openai/gpt-5.6-sol",
    ]


def test_ask_agy_reads_the_effort_off_the_name(backend: Callable[..., Ran]) -> None:
    profile = backends.named("agy")
    assert profile is not None
    backend(
        "gemini-3.7-flash-high  Gemini 3.7 Flash (High)\n"
        "gemini-3-pro           Gemini 3 Pro\n"
        "gateway-model          gateway-model\n"
        "Unauthenticated\n"
        "\n"
    )
    assert models.ask("antigravity") == (
        Model("gemini-3.7-flash-high", ("high",)),
        Model("gemini-3-pro", profile.efforts),
        Model("gateway-model", ()),
    )


def test_ask_grok_reads_the_marked_lines(backend: Callable[..., Ran]) -> None:
    backend(
        "Signed in with an API key.\n"
        "Default model: grok-5\n"
        "* grok-5 (default)\n"
        "- grok-5-mini\n"
        "- \n"
    )
    assert [one.name for one in models.ask("grok")] == ["grok-5", "grok-5-mini"]


def test_ask_cursor_offers_the_rungs_its_list_spells(
    backend: Callable[..., Ran],
) -> None:
    backend(
        "Available models\n"
        "\n"
        "\x1b[1mauto\x1b[0m - Auto (current)\n"
        "gpt-5.2 - GPT-5.2\n"
        "gpt-5.2-low - GPT-5.2 Low\n"
        "gpt-5.2-xhigh - GPT-5.2 Extra High\n"
        "gpt-5-low-fast - GPT-5 Low Fast\n"
        "gpt-5-extra-high (default)\n"
        "composer-2.5\n"
        "Tip: use --model to choose one\n"
    )
    assert models.ask("cursor-agent") == (
        Model("auto", ()),
        Model("gpt-5.2", ("xhigh", "low")),
        Model("gpt-5.2-low", ("low",)),
        Model("gpt-5.2-xhigh", ("xhigh",)),
        Model("gpt-5-low-fast", ("low",)),
        Model("gpt-5-extra-high", ("extra-high",)),
        Model("composer-2.5", ()),
    )


@pytest.mark.parametrize("cli", ["opencode", "mimo"])
def test_ask_opencode_and_mimo_read_provider_ids(
    backend: Callable[..., Ran], cli: str
) -> None:
    backend("Some banner\nanthropic/claude-opus-5 — 1M\nopenai/gpt-5\n\nwarning\n")
    assert [one.name for one in models.ask(cli)] == [
        "anthropic/claude-opus-5",
        "openai/gpt-5",
    ]


def test_ask_mcode_puts_the_selected_model_first(backend: Callable[..., Ran]) -> None:
    backend(
        json.dumps(
            {
                "providers": [
                    {
                        "providerId": "gw",
                        "models": [
                            {"modelId": "a"},
                            {"modelId": "b", "selected": True},
                        ],
                    },
                    {
                        "providerId": "off",
                        "enabled": False,
                        "models": [{"modelId": "c"}],
                    },
                    {"providerId": "x", "models": [{"modelId": ""}]},
                ]
            }
        )
    )
    found = models.ask("minimax")
    assert [one.name for one in found[:2]] == ["gw/b", "gw/a"]
    assert all(one.efforts == () for one in found[:2])
    assert "off/c" not in [one.name for one in found]
    assert len(found) > 2  # MiniMax's own after what was added


@pytest.mark.parametrize("cli", ["dsh", "qwen"])
def test_ask_an_advisory_backend_starts_nothing(
    backend: Callable[..., Ran], cli: str
) -> None:
    ran = backend()
    assert models.ask(cli) == models.offered(cli)
    assert ran.calls == 0
    assert models.where(cli).exists()


def test_ask_litellm_reads_its_shipped_catalogue(
    backend: Callable[..., Ran], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = tmp_path / "litellm"
    package.mkdir()
    (package / "model_prices_and_context_window_backup.json").write_text(
        json.dumps(
            {
                "gpt-5": {
                    "litellm_provider": "openai",
                    "mode": "chat",
                    "supports_reasoning": True,
                },
                "anthropic/claude-opus-5": {
                    "litellm_provider": "anthropic",
                    "mode": "chat",
                },
                "gemini-3-pro": {
                    "litellm_provider": "vertex_ai-language-models",
                    "mode": "chat",
                },
                "text-embedding-3": {"litellm_provider": "openai", "mode": "embedding"},
                "somebody/else": {"litellm_provider": "nobody", "mode": "chat"},
                "sample_spec": "junk",
            }
        ),
        encoding="utf-8",
    )

    def found(name: str) -> types.SimpleNamespace:
        return types.SimpleNamespace(origin=str(package / "__init__.py"))

    monkeypatch.setattr(importlib.util, "find_spec", found)
    profile = backends.named("litellm")
    assert profile is not None
    assert models.ask("litellm") == (
        Model("openai/gpt-5", profile.efforts),
        Model("anthropic/claude-opus-5", ()),
        Model("vertex_ai/gemini-3-pro", ()),
    )


def test_ask_litellm_not_installed(
    backend: Callable[..., Ran], monkeypatch: pytest.MonkeyPatch
) -> None:
    def nowhere(name: str) -> None:
        return None

    monkeypatch.setattr(importlib.util, "find_spec", nowhere)
    with pytest.raises(ValueError, match="not installed"):
        models.ask("litellm")


def test_ask_a_backend_that_fails_says_its_last_line(
    backend: Callable[..., Ran],
) -> None:
    backend(returncode=3, stderr="starting\n  not signed in  \n")
    with pytest.raises(ValueError, match=r"codex exited 3: not signed in$"):
        models.ask("codex")


def test_ask_a_backend_that_fails_silently(backend: Callable[..., Ran]) -> None:
    backend(returncode=1)
    with pytest.raises(ValueError, match=r"grok exited 1$"):
        models.ask("grok")


def test_ask_names_each_model_once(backend: Callable[..., Ran]) -> None:
    backend("- grok-5\n- grok-5\n- grok-5-mini\n")
    assert [one.name for one in models.ask("grok")] == ["grok-5", "grok-5-mini"]


class _Answer(io.BytesIO):
    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class Endpoint:
    """Stands in for every endpoint: keeps what it was sent and answers `answer`."""

    def __init__(self) -> None:
        self.sent: list[urllib.request.Request] = []
        self.answer: object = None

    def open(self, asked: urllib.request.Request) -> _Answer:
        self.sent.append(asked)
        if isinstance(self.answer, Exception):
            raise self.answer
        return _Answer(json.dumps(self.answer).encode())


@pytest.fixture
def endpoint(monkeypatch: pytest.MonkeyPatch) -> Endpoint:
    held = Endpoint()

    def opening(
        _: urllib.request.OpenerDirector, asked: urllib.request.Request, **__: Any
    ) -> _Answer:
        return held.open(asked)

    monkeypatch.setattr(urllib.request.OpenerDirector, "open", opening)
    return held


def test_an_account_naming_an_endpoint_is_answered_by_it(
    backend: Callable[..., Ran],
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran = backend()
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://gw.example/")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    endpoint.answer = {"data": [{"id": "gw-one"}, {"id": ""}, "junk", {"id": "gw-two"}]}
    profile = backends.named("claude")
    assert profile is not None

    assert models.ask("claude") == (
        Model("gw-one", profile.efforts),
        Model("gw-two", profile.efforts),
    )
    assert ran.calls == 0
    (sent,) = endpoint.sent
    assert sent.full_url == "https://gw.example/v1/models"
    assert sent.get_header("Authorization") == "Bearer sk-test"


def test_an_endpoint_with_its_version_is_asked_under_it(
    backend: Callable[..., Ran],
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend()
    monkeypatch.setenv("OPENAI_BASE_URL", "http://gw.example/api/v1")
    endpoint.answer = {"data": [{"id": "q"}]}
    assert [one.name for one in models.ask("qwen")] == ["q"]
    assert endpoint.sent[0].full_url == "http://gw.example/api/v1/models"
    assert endpoint.sent[0].get_header("Authorization") is None


@pytest.mark.parametrize(
    "answer",
    [urllib.error.URLError("down"), {"data": "nope"}, ["a list"], {"data": []}],
)
def test_an_endpoint_that_will_not_say_leaves_what_it_said_before(
    backend: Callable[..., Ran],
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
    answer: object,
) -> None:
    ran = backend("- grok-shipped\n")
    _kept(
        "grok",
        {
            "asked": "2020-01-01T00:00:00Z",
            "models": [{"name": "kept", "efforts": list[str]()}],
        },
    )
    monkeypatch.setenv("GROK_XAI_API_BASE_URL", "https://gw.example")
    endpoint.answer = answer

    assert models.ask("grok") == (Model("kept", ()),)
    assert ran.calls == 0
    assert models.asked("grok") == "2020-01-01T00:00:00Z"


def test_an_endpoint_that_will_not_say_asks_the_cli_for_a_new_account(
    backend: Callable[..., Ran],
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend("- grok-shipped\n")
    monkeypatch.setenv("GROK_XAI_API_BASE_URL", "https://gw.example")
    endpoint.answer = urllib.error.URLError("down")
    assert [one.name for one in models.ask("grok")] == ["grok-shipped"]


def test_an_endpoint_that_is_not_http_asks_the_cli(
    backend: Callable[..., Ran],
    endpoint: Endpoint,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend("- grok-shipped\n")
    monkeypatch.setenv("GROK_XAI_API_BASE_URL", "file:///etc")
    assert [one.name for one in models.ask("grok")] == ["grok-shipped"]
    assert endpoint.sent == []
