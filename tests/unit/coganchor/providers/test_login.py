from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.providers import ENV, add, find, where
from hmz.coganchor.providers.login import asked, make, sign_in, way_of

if TYPE_CHECKING:
    from hmz.coganchor.backends import Way


def way(cli: str, name: str) -> Way:
    found = way_of(cli, name)
    assert found is not None
    return found


def test_a_way_is_found_by_its_name() -> None:
    assert way("claude", "key").name == "key"
    assert way_of("claude", "env") == ENV


@pytest.mark.parametrize(("cli", "name"), [("claude", "nope"), ("nobody", "key")])
def test_a_way_a_backend_does_not_offer_is_none(cli: str, name: str) -> None:
    assert way_of(cli, name) is None


def test_what_is_still_to_be_asked_leaves_out_answers_and_fixed_values() -> None:
    vertex = way("claude", "vertex-gateway")

    left = asked(vertex, {"ANTHROPIC_AUTH_TOKEN": "t", "ANTHROPIC_VERTEX_BASE_URL": ""})

    assert left == ["ANTHROPIC_VERTEX_BASE_URL", "ANTHROPIC_VERTEX_PROJECT_ID"]


def test_a_provider_made_from_answers_holds_what_its_way_keeps() -> None:
    made = make(
        "claude",
        "vx",
        way("claude", "vertex-gateway"),
        {
            "ANTHROPIC_VERTEX_BASE_URL": "https://v.test",
            "ANTHROPIC_AUTH_TOKEN": "t",
            "ANTHROPIC_VERTEX_PROJECT_ID": "p",
        },
    )

    assert made.way == "vertex-gateway"
    assert dict(made.env) == {
        "ANTHROPIC_VERTEX_BASE_URL": "https://v.test",
        "ANTHROPIC_AUTH_TOKEN": "t",
        "ANTHROPIC_VERTEX_PROJECT_ID": "p",
        "CLOUD_ML_REGION": "us-east5",
        "CLAUDE_CODE_USE_VERTEX": "1",
        "CLAUDE_CODE_SKIP_VERTEX_AUTH": "1",
    }
    assert find("claude", "vx") == made


def test_an_answer_a_login_reads_off_stdin_is_not_kept_twice() -> None:
    made = make("codex", "k", way("codex", "key"), {"OPENAI_API_KEY": "sk"})

    assert dict(made.env) == {}


def test_variables_of_your_own_are_all_kept_but_empty_ones() -> None:
    made = make("claude", "mine", ENV, {"A": "1", "B": ""})

    assert dict(made.env) == {"A": "1"}


def test_a_way_that_adds_to_the_command_line_is_filled_in() -> None:
    made = make(
        "codex",
        "gw",
        way("codex", "openai-gateway"),
        {"CODEX_PROVIDER_URL": "https://gw.test", "CODEX_PROVIDER_KEY": "k"},
    )

    assert "model_providers.humanize.base_url=https://gw.test" in made.args


def test_a_way_with_no_command_is_already_signed_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*_: object, **__: object) -> None:
        raise AssertionError("nothing should run")

    monkeypatch.setattr(subprocess, "run", refuse)
    made = add("claude", "k", "key", {"ANTHROPIC_API_KEY": "sk"})

    assert sign_in(made, way("claude", "key")) == 0


def test_signing_in_runs_the_backends_own_login_under_the_providers_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran: list[tuple[list[str], dict[str, Any]]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        ran.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 7)

    monkeypatch.setattr(subprocess, "run", run)
    login = way("codex", "key")
    made = add("codex", "k", "key", {"EXTRA": "1"})
    (where("codex", "k") / "home").rmdir()

    status = sign_in(made, login, {"OPENAI_API_KEY": "sk-typed"})

    assert status == 7
    ((argv, kwargs),) = ran
    assert argv[argv.index("--") + 1 :] == list(login.argv)
    assert any(one.startswith("--map=") for one in argv)
    assert kwargs["input"] == "sk-typed\n"
    assert kwargs["env"]["EXTRA"] == "1"
    assert (where("codex", "k") / "home").is_dir()


def test_a_login_reading_nothing_off_stdin_is_given_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran: list[dict[str, Any]] = []

    def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        ran.append(kwargs)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", run)
    made = add("claude", "sub", "login")

    assert sign_in(made, way("claude", "login")) == 0
    assert ran[0]["input"] is None
