"""`chat`: one agent, one session, and every line the person says back is the next turn."""

from __future__ import annotations

import typing
from typing import TYPE_CHECKING, Any
from unittest import mock

import pydantic
import pytest

from hmz.flows import (
    AskUserHookParams,
    AskUserHookResult,
    CapabilityNotGranted,
    HarnessRefused,
    HarnessThrottled,
    Outworlder,
    SessionError,
)
from tests.unit.flows import doubles_flows as doubles

if TYPE_CHECKING:
    from types import ModuleType


@pytest.fixture
def chat(engine: mock.Mock, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    return doubles.builtin(monkeypatch, "chat")


def test_chat_declares_two_sides_and_the_workspace(chat: Any) -> None:
    declared = chat.chat.declared
    assert declared["agents"].__required_keys__ == {"assistant", "human"}
    assert declared["envs"].__required_keys__ == {"workspace"}
    assert declared["resumable"] is True
    assert declared["hidden"] is False
    assert chat.chat.fn.__doc__.startswith("Talks to one agent")


def test_chat_takes_no_params(chat: Any) -> None:
    with pytest.raises(pydantic.ValidationError):
        chat.Params.model_validate({"rounds": 1})


async def test_each_answer_is_said_to_the_person_and_their_reply_is_the_next_turn(
    chat: Any,
) -> None:
    assistant = doubles.agent("hello", "bye")
    human = doubles.agent("how are you?", "")

    await doubles.call(
        chat.chat, "hi", ctx=doubles.context({}), assistant=assistant, human=human
    )

    assert doubles.prompts(assistant) == ["hi", "how are you?"]
    assert doubles.prompts(human) == ["hello", "bye"]
    assert {call.kwargs["env"] for call in assistant.run.await_args_list} == {
        doubles.WORKSPACE
    }


async def test_the_conversation_is_one_session_on_each_side(chat: Any) -> None:
    assistant = doubles.agent("a", "b", "c")
    human = doubles.agent("one", "two", "")

    await doubles.call(
        chat.chat, "hi", ctx=doubles.context({}), assistant=assistant, human=human
    )

    assistant.spawn.assert_awaited_once()
    human.spawn.assert_awaited_once()
    assert len(set(map(id, doubles.sessions(assistant)))) == 1
    assert len(set(map(id, doubles.sessions(human)))) == 1
    assert doubles.sessions(assistant)[0] is not doubles.sessions(human)[0]


async def test_an_away_person_ends_it_after_one_turn(chat: Any) -> None:
    assistant = doubles.agent("done")
    human = doubles.agent("")

    await doubles.call(
        chat.chat, "do it", ctx=doubles.context({}), assistant=assistant, human=human
    )

    assert doubles.prompts(assistant) == ["do it"]


async def test_nothing_said_is_nothing_to_answer(chat: Any) -> None:
    assistant, human = doubles.agent(), doubles.agent()

    await doubles.call(
        chat.chat, "", ctx=doubles.context({}), assistant=assistant, human=human
    )

    assistant.run.assert_not_awaited()
    human.run.assert_not_awaited()


async def test_a_first_turn_that_fails_ends_the_run(chat: Any) -> None:
    assistant = doubles.agent(HarnessRefused("logged out"))
    human = doubles.agent()

    with pytest.raises(HarnessRefused, match="logged out"):
        await doubles.call(
            chat.chat, "hi", ctx=doubles.context({}), assistant=assistant, human=human
        )
    human.run.assert_not_awaited()


async def test_a_later_turn_that_fails_is_said_and_the_conversation_goes_on(
    chat: Any,
) -> None:
    assistant = doubles.agent("hello", HarnessThrottled("slow down"), "better")
    human = doubles.agent("again", "and again", "")

    await doubles.call(
        chat.chat, "hi", ctx=doubles.context({}), assistant=assistant, human=human
    )

    assert doubles.prompts(human) == [
        "hello",
        "That turn could not be taken: slow down",
        "better",
    ]


async def test_a_question_the_agent_asks_is_put_to_the_person(chat: Any) -> None:
    assistant = doubles.agent("hello")
    human = doubles.agent("", "blue", "")

    await doubles.call(
        chat.chat, "hi", ctx=doubles.context({}), assistant=assistant, human=human
    )
    (hook,) = assistant.on_ask_user.call_args.args
    person = doubles.sessions(human)[0]

    asked = AskUserHookParams(
        ctx=mock.sentinel.ctx,
        session=mock.sentinel.session,
        question="which colour?",
        options=("red", "blue"),
    )
    assert await hook(asked) == AskUserHookResult(answer="blue")
    assert human.run.await_args.args == ("which colour? (red / blue)",)
    assert human.run.await_args.kwargs["session"] is person

    plain = AskUserHookParams(
        ctx=mock.sentinel.ctx, session=mock.sentinel.session, question="why?"
    )
    assert await hook(plain) == AskUserHookResult(answer=None)
    assert human.run.await_args.args == ("why?",)


async def test_an_agent_that_cannot_ask_is_talked_to_all_the_same(chat: Any) -> None:
    assistant = doubles.agent("hello")
    assistant.on_ask_user.side_effect = CapabilityNotGranted("no asking")
    human = doubles.agent("")

    await doubles.call(
        chat.chat, "hi", ctx=doubles.context({}), assistant=assistant, human=human
    )

    assert doubles.prompts(assistant) == ["hi"]


def test_the_person_is_an_outworlder(chat: Any) -> None:
    assert typing.get_type_hints(chat.Agents)["human"] is Outworlder


async def test_the_conversation_is_kept_as_it_ends_for_one_carrying_it_on(
    chat: Any,
) -> None:
    assistant, human = doubles.agent("hello"), doubles.agent("")
    kept: dict[str, Any] = {}

    await doubles.call(
        chat.chat, "hi", ctx=doubles.context(kept), assistant=assistant, human=human
    )

    assert kept == {"conversation": doubles.sessions(assistant)[0]}


async def test_a_chat_picked_up_carries_its_conversation_on(chat: Any) -> None:
    assistant, human = doubles.agent("still here"), doubles.agent("")
    kept = {"conversation": mock.sentinel.conversation}

    await doubles.call(
        chat.chat,
        "are you there?",
        ctx=doubles.context(kept, resumed=True),
        assistant=assistant,
        human=human,
    )

    assistant.spawn.assert_not_awaited()
    assert doubles.sessions(assistant) == [mock.sentinel.conversation]
    assert doubles.prompts(human) == ["still here"]


async def test_one_that_was_not_kept_says_so_and_starts_a_new_one(chat: Any) -> None:
    assistant, human = doubles.agent("hello"), doubles.agent("")

    await doubles.call(
        chat.chat,
        "hi",
        ctx=doubles.context({}, resumed=True),
        assistant=assistant,
        human=human,
    )

    assistant.spawn.assert_awaited_once()
    (said,) = doubles.prompts(human)
    assert said.startswith("This conversation could not be carried on")
    assert said.endswith("so this is a new one.\n\nhello")


async def test_one_that_will_not_carry_on_says_so_and_the_next_line_starts_anew(
    chat: Any,
) -> None:
    assistant = doubles.agent(SessionError("gone"), "fresh")
    human = doubles.agent("again", "")
    kept = {"conversation": mock.sentinel.conversation}

    await doubles.call(
        chat.chat,
        "hi",
        ctx=doubles.context(kept, resumed=True),
        assistant=assistant,
        human=human,
    )

    assert doubles.prompts(human) == [
        (
            "This conversation could not be carried on (gone), so what you say next "
            "starts a new one."
        ),
        "fresh",
    ]
    assistant.spawn.assert_awaited_once()
    assert doubles.sessions(assistant)[1] is not mock.sentinel.conversation
