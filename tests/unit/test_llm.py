"""The mock model endpoint, in the half of it that never opens a socket.

What a body looks like, and which variables an account of a backend is made with, are facts
about the service rather than about the network -- so they are asserted here: a failure in
one of these is a failure in the mock itself, and one found without a port, a thread or a
client is a failure whose message is the whole story.

The other half -- that humanize asks this service exactly the request it says it asks, and
reads back what it answers -- is next door, in the integration tier, where there is a socket.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from hmz.coganchor import backends
from tests import llm

#: Every backend humanize asks an endpoint rather than the CLI, by name. Read off the
#: profiles rather than written out here, so that a backend given an endpoint tomorrow is
#: covered by these on the day it is given one.
POINTED = [profile.name for profile in backends.PROFILES if profile.endpoint]

#: One that names none, whose turns go wherever its own login says. There is no endpoint of
#: its to point at a mock, and saying so beats an account that quietly reaches the vendor.
ELSEWHERE = next(profile.name for profile in backends.PROFILES if not profile.endpoint)

#: A base nothing is listening on. These tests never send anything to it: what is asserted is
#: the account that would be made, which is settled before anybody opens a connection.
NOWHERE = "http://127.0.0.1:1/v1"


def test_a_catalogue_is_the_shape_a_listing_reads() -> None:
    """Ids under `data`, each an object with an `id`, in the order the endpoint offers them.

    Which is what `models._listing` reads, and the whole of what it reads: a mock answering
    some other shape would be one that every catalogue test passed against and no gateway.
    """
    body = llm.catalogue(["one", "two"])

    assert body["object"] == "list"
    assert [one["id"] for one in body["data"]] == ["one", "two"]


def test_the_same_prompt_is_answered_the_same_way_twice() -> None:
    """A body stamped off the clock is a body no test can assert the whole of."""
    said: dict[str, Any] = {
        "model": "mock/first-model",
        "messages": [{"role": "user", "content": "hi"}],
    }

    assert llm.answered(said, "there") == llm.answered(said, "there")
    assert llm.answered(said, "there")["created"] == llm.MADE


def test_an_answer_is_stamped_with_the_model_that_was_asked_for() -> None:
    """A client that reads the model back off the answer reads the one it named."""
    said: dict[str, Any] = {"model": "mock/second-model", "messages": []}

    assert llm.answered(said, llm.SAYS)["model"] == "mock/second-model"
    # And where it named none, one of the ids the endpoint is serving: a turn answered by a
    # model that endpoint does not offer is an answer nothing could have produced.
    assert llm.answered({}, llm.SAYS)["model"] == llm.MODEL
    assert llm.answered({}, llm.SAYS, "mock/third-model")["model"] == "mock/third-model"


def test_a_stream_says_what_one_body_says() -> None:
    """The pieces are the whole, and the last of them is what a client reads as the end.

    Every one of these CLIs streams, so an endpoint whose stream said something other than
    its body would be one that passed every test here and drove nothing.
    """
    said: dict[str, Any] = {"model": "mock/first-model", "messages": []}
    frames = [one.removeprefix("data: ").strip() for one in llm.framed(said, "a line")]
    parts = [json.loads(one) for one in frames[:-1]]

    assert frames[-1] == "[DONE]"
    assert (
        "".join(str(one["choices"][0]["delta"].get("content") or "") for one in parts)
        == llm.answered(said, "a line")["choices"][0]["message"]["content"]
    )
    assert parts[-1]["choices"][0]["finish_reason"] == "stop"


def test_what_a_stream_cost_is_told_to_the_client_that_asked_to_be_told() -> None:
    """A streamed answer carries no usage unless the request asked for it, and this is why.

    An endpoint that sent the count regardless would pass a driver that had stopped setting
    `stream_options.include_usage` -- and that driver reads a real gateway's turns as costing
    nothing at all, which is a bill nobody is shown rather than a test that fails.
    """
    said: dict[str, Any] = {"messages": [{"role": "user", "content": "two words"}]}
    asked: dict[str, Any] = {**said, "stream_options": {"include_usage": True}}

    quiet = json.loads(llm.framed(said, "a line")[-2].removeprefix("data: "))
    counted = json.loads(llm.framed(asked, "a line")[-2].removeprefix("data: "))

    assert "usage" not in quiet
    assert counted["usage"] == llm.answered(asked, "a line")["usage"]


def test_what_a_turn_cost_is_the_whole_conversation_rather_than_the_last_of_it() -> (
    None
):
    """A client sends all of it every time, and all of it is what a gateway bills for.

    A count taken off the last message alone would make the tenth turn of a long
    conversation cost what the first question cost, which is the one thing a test about a
    bill must not be told.
    """
    whole: dict[str, Any] = {
        "messages": [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "the first question"},
            {"role": "assistant", "content": "the first answer"},
            {"role": "user", "content": "the second"},
        ]
    }

    usage = llm.answered(whole, "said")["usage"]

    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 1
    assert usage["total_tokens"] == 11


def test_what_was_asked_is_read_out_of_either_shape_a_client_writes_it_in() -> None:
    """A plain client sends a string; one that could also send an image sends parts."""
    plain = llm.Taken(
        method="POST",
        path="/v1/chat/completions",
        body={"messages": [{"role": "user", "content": "say it"}]},
    )
    parted = llm.Taken(
        method="POST",
        path="/v1/chat/completions",
        body={
            "messages": [
                {"role": "system", "content": "be brief"},
                {"role": "user", "content": [{"type": "text", "text": "say it"}]},
            ]
        },
    )

    assert plain.prompt == "say it"
    assert parted.prompt == "say it"


def test_the_last_thing_the_user_said_is_what_the_turn_asked() -> None:
    """A client sends the whole conversation every time, and this turn is the end of it."""
    took = llm.Taken(
        method="POST",
        path="/v1/chat/completions",
        body={
            "messages": [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "answered"},
                {"role": "user", "content": "second"},
            ]
        },
    )

    assert took.prompt == "second"
    assert llm.Taken(method="GET", path="/v1/models").prompt == ""


@pytest.mark.parametrize(
    ("header", "said"),
    [
        ("authorization", "Bearer the-key"),
        ("authorization", "the-key"),
        ("x-api-key", "the-key"),
        ("x-goog-api-key", "the-key"),
    ],
)
def test_a_key_is_read_out_of_whichever_header_it_is_sent_as(
    header: str, said: str
) -> None:
    """All of them are sent, and which one a gateway reads is the gateway's own business."""
    took = llm.Taken(method="GET", path="/v1/models", headers={header: said})

    assert took.secret == "the-key"


def test_a_key_is_found_in_the_header_that_carries_it_and_not_the_first_one_there_is() -> (
    None
):
    """A client with a session on `Authorization` sends its key in the other header."""
    took = llm.Taken(
        method="GET",
        path="/v1/models",
        headers={"authorization": "Basic bm90LXRoZS1rZXk=", "x-api-key": "the-key"},
    )

    assert took.secret == "the-key"


@pytest.mark.parametrize("cli", POINTED)
def test_a_backend_is_pointed_by_the_variable_its_own_profile_names(cli: str) -> None:
    """Which variable routes a turn is the backend's own fact, read here rather than typed.

    A table of these in the suite would be a ninth copy of eight facts, and on the day one of
    them is renamed it would say nothing: the account would still be made, the variable it
    set would be one the CLI no longer reads, and the turn would reach the vendor and answer
    exactly as it should.
    """
    profile = backends.named(cli)
    assert profile is not None

    way, env = llm.pointing(cli, NOWHERE)

    assert env[profile.endpoint] == NOWHERE
    # A way the backend itself offers, since an account is made under one of those or under
    # none: a way of this suite's own invention is an account nothing would run.
    assert way in profile.ways
    # And a credential, asking an endpoint what it serves being asking it as this account.
    assert llm.KEY in env.values()


@pytest.mark.parametrize("cli", POINTED)
def test_what_a_way_already_answers_for_itself_is_not_left_unanswered(cli: str) -> None:
    """A question whose answer is usually right is not one a test should have to answer.

    kimi's gateway way asks which protocol the endpoint speaks and answers `openai` for
    itself, which is what this service is. An account made without it would be one kimi drove
    against the wrong protocol.

    The endpoint's own variable and any credential are left out: those are answered before
    whatever the way wrote down for them, which is the order `pointing` fills them in and the
    order this reads them back.
    """
    profile = backends.named(cli)
    assert profile is not None
    way, env = llm.pointing(cli, NOWHERE)

    for one in way.asks:
        if one.fixed and not one.secret and one.env != profile.endpoint:
            assert env[one.env] == one.fixed


def test_what_the_caller_answers_is_what_the_account_is_made_with() -> None:
    """The questions nobody here can answer -- which model to run -- are the caller's."""
    _, env = llm.pointing("kimi", NOWHERE, also={"KIMI_MODEL_NAME": "mock/first-model"})

    assert env["KIMI_MODEL_NAME"] == "mock/first-model"


def test_a_backend_that_names_no_endpoint_is_not_pointed_anywhere() -> None:
    """Said rather than quietly done: an account that names nowhere reaches the vendor."""
    with pytest.raises(ValueError, match="names no endpoint"):
        llm.pointing(ELSEWHERE, NOWHERE)


def test_a_backend_there_is_no_such_thing_as_is_refused() -> None:
    """The same refusal `models.ask` gives, in the same words, for the same reason."""
    with pytest.raises(ValueError, match="no such coding agent"):
        llm.pointing("nothing-of-the-sort", NOWHERE)
