from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest

from hmz.coganchor import backends, providers
from hmz.coganchor.providers import (
    ENV,
    LOCAL,
    Provider,
    add,
    composed,
    copies,
    env_of,
    environ,
    filled,
    find,
    hushed,
    ready,
    remove,
    serves,
    ways,
    where,
)


def humanize() -> Path:
    return Path(os.environ["HUMANIZE_HOME"])


def profile(cli: str) -> backends.Profile:
    found = backends.named(cli)
    assert found is not None
    return found


# ------------------------------------------------------------------------------- where


def test_a_provider_is_kept_under_its_backends_own_name() -> None:
    assert where("claude-code", "work") == humanize() / "providers" / "claude" / "work"


@pytest.mark.parametrize("name", ["", ".hidden", "-dash", "a/b", "..", "a b", "x;y"])
def test_a_name_that_is_not_one_path_component_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match="not a valid account name"):
        where("claude", name)


def test_a_backend_that_is_not_one_is_refused() -> None:
    with pytest.raises(ValueError, match="unknown agent"):
        where("nobody", "work")


# --------------------------------------------------------------------------- add / find


def test_a_provider_is_read_back_as_it_was_written_down() -> None:
    made = add(
        "claude", "work", "key", {"ANTHROPIC_API_KEY": "sk-test"}, ("--flag", "x")
    )

    found = find("claude", "work")

    assert found == made
    assert found is not None
    assert found.cli == "claude"
    assert found.way == "key"
    assert dict(found.env) == {"ANTHROPIC_API_KEY": "sk-test"}
    assert found.args == ("--flag", "x")
    assert found.made.endswith("Z")
    assert found.at == where("claude", "work")


def test_a_provider_made_under_an_alias_is_kept_under_the_backends_name() -> None:
    made = add("claude-code", "work")

    assert made.cli == "claude"
    assert find("claude", "work") == made


def test_what_a_provider_holds_is_replaced_rather_than_merged() -> None:
    add("claude", "work", "key", {"ANTHROPIC_API_KEY": "one", "OTHER": "x"})
    add("claude", "work", "key", {"ANTHROPIC_API_KEY": "two"})

    found = find("claude", "work")

    assert found is not None
    assert dict(found.env) == {"ANTHROPIC_API_KEY": "two"}


def test_correcting_a_provider_keeps_what_its_login_left_beside_it() -> None:
    add("codex", "work")
    left = where("codex", "work") / "home" / "auth.json"
    left.parent.mkdir(parents=True, exist_ok=True)
    left.write_text("{}")

    add("codex", "work", "key", {"OPENAI_API_KEY": "sk-new"})

    assert left.read_text() == "{}"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes")
def test_what_holds_keys_is_readable_by_nobody_else() -> None:
    add("claude", "work", "key", {"ANTHROPIC_API_KEY": "sk-test"})
    at = where("claude", "work")

    for one in (at, at.parent, at.parent.parent):
        assert stat.S_IMODE(one.stat().st_mode) == 0o700
    assert stat.S_IMODE((at / "provider.json").stat().st_mode) == 0o600


def test_the_account_this_machine_is_signed_into_is_always_found() -> None:
    found = find("claude-code", LOCAL)

    assert found == Provider(cli="claude", name=LOCAL, way="")
    assert found is not None
    assert found.swaps() == ()
    assert found.at == profile("claude").directory()


@pytest.mark.parametrize(
    ("cli", "name"),
    [("nobody", "work"), ("nobody", LOCAL), ("claude", "missing"), ("claude", "../x")],
)
def test_nothing_is_found_where_there_is_no_such_account(cli: str, name: str) -> None:
    assert find(cli, name) is None


@pytest.mark.parametrize(
    "said",
    ["not json", "[1, 2]", '"a string"'],
)
def test_a_directory_holding_nothing_readable_is_not_a_provider(said: str) -> None:
    at = humanize() / "providers" / "claude" / "broken"
    at.mkdir(parents=True)
    (at / "provider.json").write_text(said)

    assert find("claude", "broken") is None
    assert providers.providers() == []


def test_a_provider_with_odd_fields_is_read_as_far_as_it_reads() -> None:
    at = humanize() / "providers" / "claude" / "odd"
    at.mkdir(parents=True)
    (at / "provider.json").write_text(
        json.dumps({"cli": "codex", "env": ["x"], "args": "no", "fallback": "old"})
    )

    found = find("claude", "odd")

    assert found == Provider(cli="claude", name="odd", way=ENV.name)


# ----------------------------------------------------------------------------- listing


def test_every_provider_is_listed_by_backend_and_then_by_name() -> None:
    add("codex", "b")
    add("codex", "a")
    add("claude", "z")

    listed = [(one.cli, one.name) for one in providers.providers()]

    assert listed == [("claude", "z"), ("codex", "a"), ("codex", "b")]


def test_one_backends_providers_are_listed_on_their_own() -> None:
    add("codex", "a")
    add("claude", "z")

    assert [one.name for one in providers.providers("claude-code")] == ["z"]


def test_nothing_is_listed_where_nothing_was_ever_written_down() -> None:
    assert providers.providers() == []


def test_directories_no_backend_answers_to_are_passed_over() -> None:
    stray = humanize() / "providers" / "nobody" / "work"
    stray.mkdir(parents=True)
    (stray / "provider.json").write_text("{}")
    badly = humanize() / "providers" / "claude" / ".named"
    badly.mkdir(parents=True)
    (badly / "provider.json").write_text("{}")

    assert providers.providers() == []


# ------------------------------------------------------------------------------ remove


def test_a_provider_taken_away_is_gone_with_its_credentials() -> None:
    add("claude", "work")
    (where("claude", "work") / "home").mkdir(exist_ok=True)

    assert remove("claude", "work") is True
    assert not where("claude", "work").exists()
    assert find("claude", "work") is None
    assert remove("claude", "work") is False


def test_taking_away_a_name_that_is_not_one_is_refused() -> None:
    with pytest.raises(ValueError, match="not a valid account name"):
        remove("claude", "../escape")


# ---------------------------------------------------------------------- swaps / ready


def test_a_turn_is_answered_at_every_path_the_backend_keeps_a_credential_at(
    user: Path,
) -> None:
    made = add("claude", "work")
    at = where("claude", "work")

    swaps = dict(made.swaps())

    assert swaps[str(user / ".claude" / ".credentials.json")] == str(
        at / "home" / ".credentials.json"
    )
    assert swaps[str(user / ".claude.json")] == str(at / "user" / ".claude.json")
    assert swaps[str(user / ".config" / "anthropic")] == str(
        at / "config" / "anthropic"
    )


def test_a_credential_reached_through_a_link_is_answered_under_both_names(
    user: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = tmp_path / "real-codex"
    real.mkdir()
    linked = user / "linked-codex"
    linked.symlink_to(real)
    monkeypatch.setenv("CODEX_HOME", str(linked))

    made = add("codex", "work")
    instead = str(where("codex", "work") / "home" / "auth.json")

    assert made.swaps() == (
        (str(linked / "auth.json"), instead),
        (os.path.realpath(linked / "auth.json"), instead),
    )


def test_making_a_provider_makes_the_places_its_credentials_will_land() -> None:
    made = add("claude", "work")

    for _, instead in made.swaps():
        assert Path(instead).parent.is_dir()


def test_ready_makes_again_what_was_taken_away() -> None:
    made = add("codex", "work")
    landing = where("codex", "work") / "home"
    landing.rmdir()

    ready(made)

    assert landing.is_dir()


def test_a_backend_that_keeps_no_credentials_needs_no_supervisor() -> None:
    made = add("dsh", "work", "key", {"DEEPSEEK_API_KEY": "sk"})

    assert made.swaps() == ()
    assert made.command(["dsh", "-p", "hi"]) == ["dsh", "-p", "hi"]


def test_the_command_a_turn_is_spawned_as_names_every_path_it_is_answered_at() -> None:
    made = add("codex", "work")

    command = made.command(["codex", "exec"])

    assert command[-3:] == ["--", "codex", "exec"]
    for named, instead in made.swaps():
        assert f"--map={os.path.normpath(named)}={os.path.normpath(instead)}" in command


def test_held_is_what_is_written_down() -> None:
    made = Provider(cli="codex", name="w", way="key", env={"A": "1"}, args=("-x",))

    assert made.held() == {
        "cli": "codex",
        "name": "w",
        "way": "key",
        "env": {"A": "1"},
        "args": ["-x"],
        "made": "",
    }


# --------------------------------------------------------------------------------- ways


def test_a_backend_offers_its_own_ways_and_then_variables_of_your_own() -> None:
    offered = ways("claude-code")

    assert offered[-1] == ENV
    assert offered[:-1] == profile("claude").ways


@pytest.mark.parametrize("cli", ["dsh", "litellm"])
def test_some_backends_offer_only_the_ways_they_name(cli: str) -> None:
    assert ENV not in ways(cli)
    assert ways(cli) == profile(cli).ways


def test_a_backend_there_is_not_offers_nothing() -> None:
    assert ways("nobody") == ()


# ------------------------------------------------------------------ env_of / filled


def test_variables_of_your_own_are_read_off_the_lines_they_were_typed_as() -> None:
    said = "\n# a comment\n A = 1 \nB=two=three\n\nEMPTY=\n"

    assert env_of(said) == {"A": "1", "B": "two=three", "EMPTY": ""}


@pytest.mark.parametrize("said", ["NOEQUALS", "=value", "  = x"])
def test_a_line_that_is_not_a_variable_is_refused(said: str) -> None:
    with pytest.raises(ValueError, match="is not NAME=VALUE"):
        env_of(said)


def test_an_answer_is_filled_into_whatever_a_way_wrote_it_into() -> None:
    assert filled("url={URL} key={KEY} {OTHER}", {"URL": "u", "KEY": "k"}) == (
        "url=u key=k {OTHER}"
    )


# ----------------------------------------------------- environ / hushed / composed


def test_a_turn_with_no_provider_is_given_nothing_on_top() -> None:
    assert environ(None) == {}


def test_what_a_turn_is_run_with_is_a_copy_of_what_the_provider_holds() -> None:
    held = {"A": "1"}
    made = Provider(cli="claude", name="w", env=held)

    given = environ(made)
    given["B"] = "2"

    assert dict(made.env) == {"A": "1"}


def test_a_turn_under_a_provider_is_run_without_every_other_account() -> None:
    claude = profile("claude")
    made = Provider(cli="claude", name="w", env={"ANTHROPIC_API_KEY": "mine"})

    gone = hushed(made, claude)

    assert "ANTHROPIC_AUTH_TOKEN" in gone
    assert "CLAUDE_CODE_OAUTH_TOKEN" in gone
    assert "ANTHROPIC_API_KEY" not in gone


@pytest.mark.parametrize("which", ["provider", "profile"])
def test_nothing_is_hushed_without_a_provider_or_a_backend(which: str) -> None:
    made = Provider(cli="claude", name="w")
    claude = profile("claude")

    if which == "provider":
        assert hushed(None, claude) == frozenset()
    else:
        assert hushed(made, None) == frozenset()


def test_the_composed_environment_drops_what_is_hushed_and_adds_what_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "somebody-elses")
    monkeypatch.setenv("UNRELATED", "kept")
    made = Provider(cli="claude", name="w", env={"ANTHROPIC_API_KEY": "mine"})

    said = composed(made, profile("claude"))

    assert "ANTHROPIC_AUTH_TOKEN" not in said
    assert said["UNRELATED"] == "kept"
    assert said["ANTHROPIC_API_KEY"] == "mine"


def test_with_no_provider_the_composed_environment_is_this_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "kept")

    assert composed(None, profile("claude")) == dict(os.environ)


# ----------------------------------------------------------------- serves / copies


def test_a_key_is_an_account_other_backends_could_be_run_as() -> None:
    made = Provider(cli="claude", name="w", env={"ANTHROPIC_API_KEY": "sk"})

    others = serves(made)

    assert "claude" not in others
    assert {"pi", "opencode"} <= set(others)


def test_a_subscription_signed_into_travels_nowhere() -> None:
    assert serves(Provider(cli="claude", name="w")) == ()


def test_a_copy_is_written_down_for_the_other_backend_under_its_names() -> None:
    made = add("claude", "work", "key", {"ANTHROPIC_API_KEY": "sk"})

    copied = copies(made, "pi")

    assert (copied.cli, copied.name, copied.way) == ("pi", "work", "anthropic-key")
    assert dict(copied.env) == {"ANTHROPIC_API_KEY": "sk"}
    assert find("pi", "work") == copied


def test_a_copy_may_be_called_something_else() -> None:
    made = add("claude", "work", "key", {"ANTHROPIC_API_KEY": "sk"})

    assert copies(made, "opencode", "other").name == "other"


def test_a_copy_carries_what_its_way_adds_to_the_command_line() -> None:
    made = add(
        "claude",
        "gw",
        "anthropic-gateway",
        {"ANTHROPIC_BASE_URL": "https://gw.test", "ANTHROPIC_API_KEY": "sk"},
    )

    copied = copies(made, "qwen")

    assert copied.way == "anthropic-gateway"
    assert copied.args == ("--auth-type", "anthropic")


def test_a_copy_with_no_matching_way_is_variables_of_your_own() -> None:
    made = Provider(
        cli="claude",
        name="mixed",
        env={"ANTHROPIC_API_KEY": "sk", "OPENAI_API_KEY": "sk2"},
    )

    assert copies(made, "pi").way == ENV.name


def test_a_copy_to_a_backend_that_cannot_run_as_it_is_refused() -> None:
    made = Provider(cli="claude", name="w", env={"ANTHROPIC_API_KEY": "sk"})

    with pytest.raises(ValueError, match="cannot be used with codex"):
        copies(made, "codex")
