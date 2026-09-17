"""What an account runs, asked of that account, which is a turn only a supervisor can take.

The rest of it is `tests/integration/backends/test_models.py`, which asks a bare CLI and a
loopback gateway and needs nothing CI has not got. What is here is every test that starts a CLI
under an account, and a turn taken as an account is one whose reads are answered by others --
a seccomp filter and a ptrace supervisor around a real process. A container without
`CAP_SYS_PTRACE` imports every module here and can supervise nothing, so these are a tier of
their own rather than a skip inside a file CI runs.

One of them is parametrised over having no account at all, which is the control the account
case is read against and so stays beside it rather than being read in another tier. The
converse also holds: a test that names an account the CLI is never started under -- because the
gateway answered, or because the backend has no endpoint to ask -- is in the other half, since
nothing is ever supervised in it.

What the two halves share -- the stand-in backends, the loopback gateway, and the fixture that
leaves nobody's real endpoint for a test to reach -- is in `tests/answering.py`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor import models, providers
from tests.answering import (
    CLAUDE,
    CODEX,
    OPENCODE,
    SERVED,
    endpoint,
    no_endpoint,  # pyright: ignore[reportUnusedImport]  # noqa: F401
    seen,
    stands_in,
)
from tests.supervising import traced

if TYPE_CHECKING:
    from pathlib import Path

#: Asking a backend what it runs is what this module is about, so it is put back for all of it.
pytestmark = pytest.mark.usefixtures("asking")


@traced
@pytest.mark.parametrize("provider", ["", "subscribed"])
def test_claude_is_never_asked_about_a_model_humanize_thought_of(
    provider: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Claude lists a custom model without checking the account can run it.

    So naming one to get a hidden model listed would put a model in the catalogue for every
    account that cannot run it -- which is the one thing a catalogue asked for rather than
    written down exists to avoid.
    """
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "claude", CLAUDE)
    if provider:
        providers.add("claude", provider, "login", {})

    found = models.ask("claude", provider)

    assert [model.name for model in found] == ["claude-nine", "claude-quick"]
    environment = seen(bin_, "claude")["env"]
    assert isinstance(environment, dict)
    assert "ANTHROPIC_CUSTOM_MODEL_OPTION" not in environment


@traced
def test_two_accounts_of_one_backend_are_two_catalogues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which models a turn may name is the account's, so what is kept is the account's."""
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "codex", CODEX)
    providers.add("codex", "mine", "key", {"OPENAI_API_KEY": "sk-x"})
    models.ask("codex")

    stands_in(monkeypatch, bin_, "codex", json.dumps({"models": []}))
    models.ask("codex", "mine")

    assert [model.name for model in models.offered("codex")] == [
        "gpt-nine",
        "gpt-eight",
    ]
    assert models.offered("codex", "mine") == ()


@traced
def test_what_an_account_runs_is_kept_with_the_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """So that taking the account away takes what it runs with it: they are one fact."""
    stands_in(monkeypatch, tmp_path / "bin", "codex", CODEX)
    provider = providers.add("codex", "mine", "key", {"OPENAI_API_KEY": "sk-x"})
    models.ask("codex", "mine")

    assert models.where("codex", "mine").parent == provider.at
    assert providers.remove("codex", "mine")
    assert models.offered("codex", "mine") == ()


@traced
def test_an_account_is_asked_under_its_own_credentials_and_without_anybody_elses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """As a turn of it is run: what it sets, and none of what its backend would rather have."""
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "claude", CLAUDE)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "somebody-elses")
    # A gateway with nothing listening at it, so this is about the environment the CLI is
    # run under rather than about the endpoint being asked -- which nothing answers.
    at = "http://127.0.0.1:1"
    providers.add("claude", "mine", "gateway", {"ANTHROPIC_BASE_URL": at})

    models.ask("claude", "mine")

    environ = seen(bin_, "claude")["env"]
    assert isinstance(environ, dict)
    assert environ["ANTHROPIC_BASE_URL"] == at
    assert "ANTHROPIC_API_KEY" not in environ


@traced
def test_an_account_that_names_no_endpoint_is_asked_of_its_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A subscription is not a gateway: there is nothing to ask but the CLI, and it knows."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)
    providers.add("claude", "subscribed", "token", {"CLAUDE_CODE_OAUTH_TOKEN": "mine"})

    found = models.ask("claude", "subscribed")

    assert [model.name for model in found] == ["claude-nine", "claude-quick"]


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ('{"error": {"message": "key not allowed to access model"}}', 403),
        (json.dumps({"object": "error", "message": "no catalogue here"}), 200),
        ("<html>somebody else's login page</html>", 200),
    ],
)
@traced
def test_an_endpoint_that_will_not_say_leaves_the_cli_to_answer(
    body: str, status: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It refused, it answered something else, or it answered nothing that is a list.

    None of them is a reason to have no catalogue: an account with no models is an account
    nothing can be run as, and the CLI's own answer is better than that.
    """
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)
    with endpoint(body, status=status) as (base, _):
        providers.add("claude", "gateway", "gateway", {"ANTHROPIC_BASE_URL": base})

        found = models.ask("claude", "gateway")

    assert [model.name for model in found] == ["claude-nine", "claude-quick"]


@traced
def test_an_endpoint_nothing_is_listening_at_leaves_the_cli_to_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gateway that is down is a gateway to ask again, not a catalogue to throw away."""
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)
    providers.add(
        "claude", "gateway", "gateway", {"ANTHROPIC_BASE_URL": "http://127.0.0.1:1"}
    )

    found = models.ask("claude", "gateway")

    assert [model.name for model in found] == ["claude-nine", "claude-quick"]


@traced
def test_a_gateway_that_is_down_keeps_the_catalogue_it_served_rather_than_the_clis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a CLI ships with is a stand-in for an account that has nothing, and no more.

    It is not an older version of what the endpoint serves, it is a list from somewhere else:
    the ids that CLI was built with, none of which a gateway fronting several clouds has heard
    of. Written over 244 real ones because the gateway was briefly down, every id humanize
    then offers is refused -- and nothing asks again on its own, so it stays refused.
    """
    bin_ = tmp_path / "bin"
    stands_in(monkeypatch, bin_, "claude", CLAUDE)
    with endpoint(SERVED) as (base, _asked):
        providers.add("claude", "gateway", "gateway", {"ANTHROPIC_BASE_URL": base})

        served = models.ask("claude", "gateway")

    # And now there is nothing listening where that account points, which is the same account
    # asked again on the morning its gateway is down.
    found = models.ask("claude", "gateway")

    assert [model.name for model in found] == [one.name for one in served]
    assert models.offered("claude", "gateway") == served
    # Unasked as well as unwritten: the CLI has nothing to say about this account, so there
    # is no reason to spend the better part of a minute starting it to hear it.
    assert not (bin_ / "claude.seen").exists()


@traced
def test_a_backend_whose_ids_are_a_providers_is_never_asked_an_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """opencode, mimocode, pi and zcode name a model `provider/id`, out of several at once.

    An endpoint would answer with the ids of the one it fronts, without the provider that
    says which of them serves it -- a list of models that CLI cannot name, which is the
    failure being fixed rather than the fix.
    """
    stands_in(monkeypatch, tmp_path / "bin", "opencode", OPENCODE)
    with endpoint(SERVED) as (base, asked):
        providers.add("opencode", "gateway", "env", {"ANTHROPIC_BASE_URL": base})

        found = models.ask("opencode", "gateway")

    assert [model.name for model in found] == [
        "opencode/big-pickle",
        "opencode/small-pickle",
    ]
    assert asked == []


@traced
def test_the_credential_does_not_follow_a_redirect_to_another_host(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A machine only asking what models there are does not hand its key to a third party.

    urllib sends the headers it was given again wherever it is sent, so an endpoint that
    answers `302 somewhere-else` would be handing the account's own key to somewhere the
    account never named. Refused, which reads here as an endpoint that would not say.
    """
    stands_in(monkeypatch, tmp_path / "bin", "claude", CLAUDE)
    with endpoint(SERVED) as (elsewhere, theirs):
        with endpoint("", moved=f"{elsewhere}/v1/models") as (base, ours):
            providers.add(
                "claude",
                "gateway",
                "gateway",
                {"ANTHROPIC_BASE_URL": base, "ANTHROPIC_AUTH_TOKEN": "the-secret"},
            )

            found = models.ask("claude", "gateway")

        assert [sent for _, sent in ours] == ["Bearer the-secret"]
        # The other host was never asked at all, so it never saw the key.
        assert theirs == []
    assert [model.name for model in found] == ["claude-nine", "claude-quick"]
