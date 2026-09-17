"""humanize against the mock model endpoint, over a real socket on the loopback.

The half of the mock that a unit test cannot reach: that the request humanize makes is the
request this service answers, header for header and path for path, and that what it answers
is read back as a catalogue and as a turn. A mock verified only against itself proves
nothing -- so every test here drives `hmz.coganchor.models`, or an HTTP client, rather than
calling the service's own functions and agreeing with them.

Nothing here starts a coding agent. `PATH` is emptied wherever a catalogue is asked for, so
that a service which stopped answering shows up as a backend that could not be started rather
than as a real CLI quietly taking the question and, on a machine where one is installed and
signed in, answering it.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import backends, models, providers
from tests.llm import KEY, MOCKED, POINTED

if TYPE_CHECKING:
    from pathlib import Path

    from tests.llm import Serving

# Every test here is about a backend being asked what it runs, which the suite otherwise
# refuses: `_asks_nothing` puts a raiser in its place so that nothing starts a coding agent
# on whoever's machine is running the tests.
pytestmark = pytest.mark.usefixtures("asking")


def asks(
    at: str, said: dict[str, Any] | None = None, key: str = KEY
) -> tuple[int, str]:
    """One request to the service, as a client of it makes one.

    Read to the end whichever way it was answered: a body that said how long it was ends
    there, and a stream ends where the connection does, which is what a client with no
    length to go on reads as the end.

    Args:
      at: The whole URL.
      said: The body, for a request that has one.
      key: What to send as the credential, or "" to send none.

    Returns:
      What it answered under, and what it answered.
    """
    headers = {"Content-Type": "application/json"} if said is not None else {}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(  # noqa: S310 -- the loopback, in a test
        at,
        data=json.dumps(said).encode() if said is not None else None,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as answer:  # noqa: S310
            body = answer.read().decode()
            return int(answer.status), body
    except urllib.error.HTTPError as refused:
        return int(refused.code), refused.read().decode()


def test_an_account_on_an_endpoint_is_asked_the_endpoint_under_its_own_credential(
    llm: Serving, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The request humanize says it makes, made: the path, the headers and the credential.

    Asserted here rather than taken on trust because this is the whole contract between
    humanize and somebody's gateway. An endpoint that answers `/v1/models` under a bearer is
    one humanize can ask; a mock that answered anything at all would agree with a humanize
    that had stopped sending the key, stopped naming the version, or started asking
    `/v1/v1/models`.
    """
    monkeypatch.setenv("PATH", str(tmp_path))
    llm.account("claude")

    found = models.ask("claude", MOCKED)

    assert [model.name for model in found] == llm.serves
    took = llm.taken[0]
    assert (took.method, took.path) == ("GET", "/v1/models")
    assert took.headers["accept"] == "application/json"
    assert took.headers["user-agent"] == "humanize"
    # All three, because a gateway is asked what it serves without knowing which protocol it
    # would rather be asked in, and each of these is ignored by the half that reads the other.
    assert took.headers["authorization"] == f"Bearer {KEY}"
    assert took.headers["x-api-key"] == KEY
    assert took.headers["anthropic-version"] == models._DATED


@pytest.mark.parametrize("cli", POINTED)
def test_every_backend_that_names_an_endpoint_is_answered_by_this_one(
    cli: str, llm: Serving, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One service, and all eight accounts that point somewhere are asked it.

    Which is the point of the whole file: a catalogue for any backend, in CI, without a key
    and without a token spent.
    """
    monkeypatch.setenv("PATH", str(tmp_path))
    profile = backends.named(cli)
    assert profile is not None
    llm.account(cli)

    found = models.ask(cli, MOCKED)

    # With the word the session declares the endpoint under written back on, for the CLIs
    # that spell a model `provider/id`: what is offered and what is opened are one string.
    under = f"{profile.fronted}/" if profile.fronted else ""
    assert [model.name for model in found] == [f"{under}{one}" for one in llm.serves]
    assert [(took.method, took.path) for took in llm.taken] == [("GET", "/v1/models")]


def test_an_endpoint_written_with_its_version_is_not_asked_for_a_second_one(
    llm: Serving, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`http://host` and `http://host/v1` are two spellings of one gateway.

    Both are how somebody was told to write theirs down, and `/v1/v1/models` is nowhere -- so
    the service answers the one path either spelling arrives at, and would 404 the other.
    """
    monkeypatch.setenv("PATH", str(tmp_path))
    providers.add(
        "claude",
        "versioned",
        "gateway",
        {"ANTHROPIC_BASE_URL": f"{llm.base}/v1/", "ANTHROPIC_AUTH_TOKEN": KEY},
    )

    found = models.ask("claude", "versioned")

    assert [model.name for model in found] == llm.serves
    assert [took.path for took in llm.taken] == ["/v1/models"]


def test_the_catalogue_is_whatever_the_test_said_it_was(
    llm: Serving, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asked again after the endpoint changed, an account's catalogue is the new one.

    A gateway gains and loses models, and humanize's answer to that is the `r` key. Which is
    a thing to be able to test, so what this service serves is the test's to change while it
    is running.
    """
    monkeypatch.setenv("PATH", str(tmp_path))
    llm.account("claude")
    models.ask("claude", MOCKED)

    llm.serves = ["mock/only-one-now"]
    found = models.ask("claude", MOCKED)

    assert [model.name for model in found] == ["mock/only-one-now"]


def test_an_endpoint_that_was_asked_without_the_key_will_not_say(llm: Serving) -> None:
    """A catalogue is the account's, so a request carrying no account is refused.

    Read back through `_served`, which is what turns a refusal into the CLI's turn to be
    asked: what is checked here is that the refusal arrives as one -- an endpoint that would
    not say -- rather than as an empty catalogue or a crash.
    """
    profile = backends.named("claude")
    assert profile is not None

    assert models._served(profile, {profile.endpoint: llm.base}) is None
    assert llm.taken[-1].secret == ""


def test_nothing_is_served_where_nothing_is_served(llm: Serving) -> None:
    """The mock answers the requests humanize makes, and 404s the ones it does not.

    A service that answered a catalogue at every path would pass a `_listing` that had
    started asking somewhere else, which is the one thing these tests exist to catch.

    `/v1/messages` is here to say where this service stops: turns are served as chat
    completions, and a backend that takes its turns in a protocol of its own is answered for
    its catalogue and refused for its turn. Which is a gap in the mock to fill when somebody
    needs it, and it says so rather than answering something that CLI would misread.
    """
    elsewhere: list[tuple[str, dict[str, Any] | None]] = [
        (f"{llm.base}/v2/models", None),
        (f"{llm.base}/v1/messages", {"messages": []}),
    ]
    for at, sent in elsewhere:
        status, body = asks(at, sent)

        assert status == 404
        assert "nothing is served" in json.loads(body)["error"]["message"]


def test_a_turn_is_answered_with_what_the_test_said_the_model_replies(
    llm: Serving,
) -> None:
    """The other half of an endpoint: where a turn goes, and what comes back from it."""
    llm.says = "it is done"

    status, body = asks(
        f"{llm.base}/v1/chat/completions",
        {
            "model": llm.serves[0],
            "messages": [{"role": "user", "content": "say that it is done"}],
        },
    )

    assert status == 200
    said = json.loads(body)
    assert said["choices"][0]["message"]["content"] == "it is done"
    assert said["model"] == llm.serves[0]
    assert said["usage"]["completion_tokens"] == 3
    # And what was asked is written down, so that a test can be about the prompt a driver
    # built rather than about the answer it got back.
    assert llm.taken[-1].prompt == "say that it is done"
    assert llm.taken[-1].secret == KEY


def test_a_streamed_turn_says_the_same_thing_a_piece_at_a_time(llm: Serving) -> None:
    """Which is how every one of these CLIs takes a turn: read back as it happens."""
    llm.says = "streamed all the same"

    _, body = asks(
        f"{llm.base}/v1/chat/completions",
        {"model": llm.serves[0], "messages": [], "stream": True},
    )

    frames = [
        one.removeprefix("data: ")
        for one in body.splitlines()
        if one.startswith("data: ")
    ]
    assert frames[-1] == "[DONE]"
    assert (
        "".join(
            str(json.loads(one)["choices"][0]["delta"].get("content") or "")
            for one in frames[:-1]
        )
        == "streamed all the same"
    )


def test_a_turn_that_carries_no_key_is_refused(llm: Serving) -> None:
    """The service demands the credential on a turn for the reason it does on a catalogue."""
    status, body = asks(
        f"{llm.base}/v1/chat/completions",
        {"model": llm.serves[0], "messages": []},
        key="",
    )

    assert status == 401
    assert json.loads(body)["error"]["message"]
    # And the refused request is written down too: what was sent is what a test is about.
    assert llm.taken[-1].path == "/v1/chat/completions"
