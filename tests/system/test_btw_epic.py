"""The Epic asks a conversation of a real epic, by `hmz-ask`, and answers with what it heard.

A chat is told a code word and nothing else is: the snapshot The Epic is given holds no
observation of it. Asked for the code word, The Epic can only answer by asking that
conversation -- through its `ask-conversation` skill and `hmz-ask`, caught by the host where
it runs -- and the test checks that the ask was carried out and its answer used.

`HMZ_SYSTEM_MODEL_<HARNESS>` swaps the model a harness runs at, as `MODEL[:EFFORT]`.
"""

from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING, Any

import pytest

from hmz.daemon.link import linked
from hmz.runtime.doing.core import Hmz
from hmz.runtime.doing.hosting import Host
from hmz.runtime.watching.btw import Btw, FlowSnapshot
from tests.system.real import needs

if TYPE_CHECKING:
    from pathlib import Path

#: What the chat is told, and nobody else is.
CODE = "PURPLE-HIPPO-47"

#: Each harness The Epic is tried on, at its cheapest model.
CHEAPEST = {
    "claude": "claude-haiku-4-5-20251001:low",
    "codex": "gpt-5.5:low",
}


def _spec(harness: str) -> str:
    needs(harness)
    model = os.environ.get(f"HMZ_SYSTEM_MODEL_{harness.upper()}") or CHEAPEST[harness]
    return f"{harness}/{model}"


@pytest.mark.timeout(900)
@pytest.mark.parametrize("epic", sorted(CHEAPEST))
def test_the_epic_asks_the_conversation_that_knows(epic: str, workspace: Path) -> None:
    runs = _spec(epic)
    chat = _spec("claude")
    host = Host(Hmz(workspace))
    link = linked(host, "system")
    idle = threading.Event()
    keys: list[str] = []

    def heard(message: dict[str, Any]) -> None:
        if message.get("type") == "sessions" and message["open"]:
            keys[:] = message["open"]
            if not message["working"]:
                idle.set()

    link.heard(heard)
    told: list[tuple[str, str]] = []
    try:
        link.start(
            "chat",
            f"Remember the code word {CODE}: anyone may ask you for it later. Do not "
            "write it to any file or memory; just remember it. Reply with just OK.",
            agents={"assistant": chat},
        )
        assert idle.wait(300), "the chat never finished its turn"
        # Let the chat's CLI finish writing its conversation down, which a fork reads.
        time.sleep(5)
        (key,) = keys
        mode = Btw(
            "",
            aside=link.aside,
            unaside=lambda side: link.asked({"do": "unaside", "side": side}),
            sessions=lambda: list(keys),
            source=lambda: {"runs": runs},
            asking=lambda to, question: told.append((to, question)),
        )
        answer = mode.ask(
            "What code word was the chat told? You cannot know it without asking that "
            "conversation; answer with the code word.",
            FlowSnapshot(
                flow="chat",
                task="(withheld)",
                workspace=str(workspace),
                elapsed=1.0,
                finished=False,
                sessions=((key, "the chat's assistant"),),
            ),
        )
        mode.close()
    finally:
        link.close()
        host.close()

    assert told, "The Epic asked nothing"
    assert {to for to, _ in told} == {key}, told
    assert CODE in answer, answer
