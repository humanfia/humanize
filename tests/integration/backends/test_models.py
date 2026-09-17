"""What each backend runs, asked of that backend, where the asking needs no supervisor.

Every backend here is a stand-in first on PATH printing what the real one prints, and every
gateway is a loopback server this file started: the point of the module is that nothing is
written down, so what is checked is that each backend's own way of being asked is read the way
that backend answers it. A process of its own and a socket on 127.0.0.1 is all of what it
takes, which is why this half is the one CI runs.

The other half is `tests/system/backends/test_models.py`: asking a backend *as an account* runs
its turn under a provider, and a turn under a provider is a seccomp filter and a ptrace
supervisor, which CI cannot be relied on to hand over. What the two share -- the stand-ins, the
loopback gateway, and the fixture that leaves nobody's real endpoint for a test to reach -- is
in `tests/answering.py`.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import models, providers
from hmz.coganchor.backends import named
from tests.answering import (
    AGY,
    CLAUDE,
    CLAUDE_CUSTOM,
    CODEX,
    KIMI,
    MIMO,
    OPENCODE,
    PI,
    SERVED,
    ZCODE,
    endpoint,
    no_endpoint,  # pyright: ignore[reportUnusedImport]  # noqa: F401
    seen,
    stands_in,
)

if TYPE_CHECKING:
    from pathlib import Path

#: Asking a backend what it runs is what this module is about, so it is put back for all of it.
pytestmark = pytest.mark.usefixtures("asking")


@pytest.mark.parametrize(
    ("cli", "prints", "wanted"),
    [
        ("claude", CLAUDE, ["claude-nine", "claude-quick"]),
        ("codex", CODEX, ["gpt-nine", "gpt-eight"]),
        ("kimi", KIMI, ["kimi-code/kthree", "kimi-code/kold"]),
        ("pi", PI, ["openai-codex/gpt-nine", "anthropic/opus-ten"]),
        ("opencode", OPENCODE, ["opencode/big-pickle", "opencode/small-pickle"]),
        ("mimo", MIMO, ["mimo/mimo-auto", "openai/gpt-nine"]),
        ("agy", AGY, ["gemini-nine-high", "gemini-nine-low", "claude-sonnet-nine"]),
        ("zcode", ZCODE, ["zai/glm-nine", "zai/glm-quick"]),
    ],
)
def test_every_backend_is_asked_the_way_that_backend_answers(
    cli: str,
    prints: str,
    wanted: list[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A control request, a debug command, a provider dump, a table, a list of lines."""
    stands_in(monkeypatch, tmp_path / "bin", cli, prints)

    found = models.ask(cli)

    assert [model.name for model in found] == wanted


def test_claude_keeps_the_alias_of_a_custom_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The alias is what Claude accepts, even though its response has a canonical id too."""
    monkeypatch.setenv("ANTHROPIC_CUSTOM_MODEL_OPTION", "fable")
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "claude", CLAUDE_CUSTOM)

    found = models.ask("claude")

    assert [model.name for model in found] == ["fable"]
    environment = seen(bin_, "claude")["env"]
    assert isinstance(environment, dict)
    # Passed through as it was set, rather than replaced by one of humanize's own choosing.
    assert environment["ANTHROPIC_CUSTOM_MODEL_OPTION"] == "fable"


def test_an_antigravity_model_takes_the_effort_its_own_name_carries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It lists one model at three efforts as three models, and refuses a fourth beside them.

    `--model gemini-nine-high --effort low` is `conflicts with --effort=low`, and a model
    whose name carries no effort is `--effort is not supported for model` -- so the effort is
    chosen by choosing the model, and the catalogue is what says so.
    """
    stands_in(monkeypatch, tmp_path / "bin", "agy", AGY)

    found = {one.name: one.efforts for one in models.ask("agy")}

    assert found["gemini-nine-high"] == ("high",)
    assert found["gemini-nine-low"] == ("low",)
    # And one whose name carries none runs at its own level whatever it is asked for.
    assert found["claude-sonnet-nine"] == named("agy").efforts  # pyright: ignore[reportOptionalMemberAccess]


def test_grok_takes_the_efforts_it_says_it_takes() -> None:
    """The ladder written down is the one its own refusal enumerates.

    `unknown effort level 'max'; use one of: xhigh, high, medium, low` -- said before it does
    anything else, so a rung it has not got is a turn that never starts.
    """
    held = named("grok")
    assert held is not None
    assert held.efforts == ("xhigh", "high", "medium", "low")


def test_dsh_uses_the_official_adapter_catalogue_without_starting_a_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def started(*args: object, **kwargs: object) -> None:
        raise AssertionError("dsh model discovery must not start a CLI")

    monkeypatch.setattr(subprocess, "run", started)

    found = models.ask("deepseek-harness")

    assert [model.name for model in found] == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    ]
    assert all(model.efforts == ("max", "high", "low", "off") for model in found)
    assert models.offered("dsh") == found


def test_dsh_offers_the_official_catalogue_before_it_has_been_asked() -> None:
    found = models.offered("deepseek-harness")

    assert [model.name for model in found] == [
        "deepseek-v4-flash",
        "deepseek-v4-pro",
    ]
    assert all(model.efforts == ("max", "high", "low", "off") for model in found)


def test_a_model_takes_the_efforts_its_backend_said_that_model_takes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which differ between the models of one backend, and are hardest first either way."""
    stands_in(monkeypatch, tmp_path / "bin", "codex", CODEX)

    found = {model.name: model.efforts for model in models.ask("codex")}

    assert found["gpt-nine"] == ("ultra", "high", "low")
    assert found["gpt-eight"] == ("high", "low")


def test_a_model_its_backend_says_nothing_about_takes_the_whole_ladder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A turn has to be asked for at some effort, and it said nothing to narrow them by."""
    stands_in(monkeypatch, tmp_path / "bin", "kimi", KIMI)

    found = {model.name: model.efforts for model in models.ask("kimi")}
    profile = named("kimi")
    assert profile is not None

    assert found["kimi-code/kthree"] == (
        "max",
        "high",
        "low",
    )  # no `medium`, as it said
    assert found["kimi-code/kold"] == profile.efforts


def test_the_rung_a_backend_does_not_document_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No listing of Claude Code's own will ever name `ultracode`, and it takes it."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)

    found = {model.name: model.efforts for model in models.ask("claude")}

    assert found["claude-nine"] == ("ultracode", "max", "high", "low")


def test_a_model_named_twice_is_one_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Claude Code offers its default under `default` as well as under its own name."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)

    found = models.ask("claude")

    assert [model.name for model in found].count("claude-nine") == 1


def test_the_window_on_the_end_of_an_id_is_not_part_of_the_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`[1m]` is a way of running the model; the backend asked for one under it says no."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)

    assert all("[" not in model.name for model in models.ask("claude"))


def test_a_swarm_is_the_backends_own_rather_than_a_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every model Kimi runs takes a turn wide as well as hard, and no other backend does."""
    stands_in(monkeypatch, tmp_path / "bin", "kimi", KIMI)
    stands_in(monkeypatch, tmp_path / "bin", "codex", CODEX)

    assert all(model.swarms for model in models.ask("kimi"))
    assert not any(model.swarms for model in models.ask("codex"))


def test_what_was_asked_for_is_kept_and_read_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reading it back is one file read, which is what lets a prompt do it."""
    stands_in(monkeypatch, tmp_path / "bin", "codex", CODEX)

    asked = models.ask("codex")

    assert models.offered("codex") == asked
    assert models.asked("codex").endswith("Z")


def test_a_backend_nobody_has_asked_offers_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty rather than guessed at: a model nobody can run is worse than a list to fill."""
    assert models.offered("codex") == ()
    assert models.asked("codex") == ""


def test_a_catalogue_written_by_something_else_is_no_catalogue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prompt reads this, and a file it cannot read is a list to fill rather than a crash."""
    at = models.where("codex")
    at.parent.mkdir(parents=True, exist_ok=True)
    at.write_text("not json at all")

    assert models.offered("codex") == ()


def test_a_backend_that_exits_badly_says_what_it_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CLI that is not signed in cannot say what it runs, and that is worth reading."""
    stands_in(
        monkeypatch, tmp_path / "bin", "codex", "", code=3, says="not logged in\n"
    )

    with pytest.raises(ValueError, match="not logged in"):
        models.ask("codex")


def test_a_backend_that_answers_with_nothing_readable_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stream with no answer in it is a backend that did not answer the question."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", '{"type": "system"}\n')

    with pytest.raises(ValueError, match="said nothing"):
        models.ask("claude")


def test_a_backend_that_refuses_the_question_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Claude Code answers a control request it will not carry out with the reason."""
    stands_in(
        monkeypatch,
        tmp_path / "bin",
        "claude",
        json.dumps(
            {
                "type": "control_response",
                "response": {
                    "subtype": "error",
                    "request_id": "models",
                    "error": "no catalogue here",
                },
            }
        ),
    )

    with pytest.raises(ValueError, match="no catalogue here"):
        models.ask("claude")


def test_a_backend_nobody_has_heard_of_is_refused() -> None:
    """Every caller of this names a backend, and one that is not one is a caller's mistake."""
    with pytest.raises(ValueError, match="no such coding agent"):
        models.ask("emacs")
    with pytest.raises(ValueError, match="no such coding agent"):
        models.where("emacs")
    assert models.offered("emacs") == ()


def test_an_account_that_is_not_that_backends_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asking as an account that does not exist would be asking as this machine instead."""
    stands_in(monkeypatch, tmp_path / "bin", "codex", CODEX)

    with pytest.raises(ValueError, match="no account called"):
        models.ask("codex", "nobody")


def test_a_backend_is_asked_by_the_name_it_is_installed_as(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whichever of its spellings was used: `kimi-code` and `kimi` are one backend."""
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "kimi", KIMI)

    found = models.ask("kimi-code")

    assert [model.name for model in found] == ["kimi-code/kthree", "kimi-code/kold"]
    assert models.offered("kimi") == found
    assert seen(bin_, "kimi")["argv"] == ["provider", "list", "--json"]


def test_an_account_on_an_endpoint_is_asked_the_endpoint_and_not_its_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CLI pointed at somebody's gateway answers with the models it ships.

    Which are the models the gateway refuses -- so the catalogue is fresh and wrong, and
    asking again changes nothing. What a turn of that account may name is what is at the
    other end of the base URL it sets.
    """
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "claude", CLAUDE)
    profile = named("claude")
    assert profile is not None
    with endpoint(SERVED) as (base, asked):
        providers.add(
            "claude",
            "gateway",
            "gateway",
            {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": "the-secret"},
        )

        found = models.ask("claude", "gateway")

    assert [model.name for model in found] == [
        "azure/anthropic/claude-haiku-4-5",
        "azure/openai/gpt-5.6-sol",
    ]
    # The whole ladder: a catalogue says nothing about how hard a model may be asked to
    # think, and a model nothing narrowed is one its backend will take any rung for.
    assert found[0].efforts == profile.efforts
    assert [path for path, _ in asked] == ["/v1/models"]
    # And the CLI was never started. It has nothing to add and costs the seconds.
    assert not (bin_ / "claude.seen").exists()


def test_an_endpoint_written_with_its_version_is_not_asked_for_a_second_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`https://host` and `https://host/v1` are two spellings of one gateway."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)
    with endpoint(SERVED) as (base, asked):
        providers.add(
            "claude", "gateway", "gateway", {"ANTHROPIC_BASE_URL": f"{base}/v1/"}
        )

        models.ask("claude", "gateway")

    assert [path for path, _ in asked] == ["/v1/models"]


def test_the_accounts_own_credential_is_sent_and_never_written_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The endpoint is asked as that account, and what makes it that account goes no further.

    It reaches the request and nothing else: not the catalogue, not a log, not a message.
    """
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "somebody-elses")
    with endpoint(SERVED) as (base, asked):
        providers.add(
            "claude",
            "gateway",
            "gateway",
            {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": "the-secret"},
        )

        models.ask("claude", "gateway")

    assert [sent for _, sent in asked] == ["Bearer the-secret"]
    assert "the-secret" not in models.where("claude", "gateway").read_text("utf-8")


def test_an_endpoint_that_moves_its_own_path_is_followed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same host over the same scheme is where the credential already was."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)
    with endpoint(SERVED, moved="/models") as (base, asked):
        providers.add(
            "claude",
            "gateway",
            "gateway",
            {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": "the-secret"},
        )

        found = models.ask("claude", "gateway")

    assert [model.name for model in found] == [
        "azure/anthropic/claude-haiku-4-5",
        "azure/openai/gpt-5.6-sol",
    ]
    assert [path for path, _ in asked] == ["/v1/models", "/models"]
