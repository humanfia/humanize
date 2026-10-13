"""Chats held apart: each on a host of its own beside the workspace's, folding away when idle.

A workspace's own host runs its flows one at a time; every chat is a host of its own beside it,
so two conversations and a flow go at once in one workspace. A chat nobody reads between turns
folds away -- its host goes, the epic reads done -- and saying something in it again carries it
on in the same epic, the stand-in `claude` resuming the session it had.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from hmz import daemon
from hmz.daemon import where
from hmz.runtime.doing import hosting as hosted
from hmz.runtime.epic import every, read
from tests.integration.doubles_core import AGENT, install, started
from tests.integration.doubles_daemon import WAITS, Heard, hosting, until, written

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

pytestmark = [
    pytest.mark.timeout(120),
    pytest.mark.filterwarnings("ignore:.*use of fork.*:DeprecationWarning"),
]


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    at = install(tmp_path, monkeypatch)
    monkeypatch.delenv("HUMANIZE_DAEMON", raising=False)
    # Inherited by every host forked from here: a chat nobody reads folds in a moment.
    monkeypatch.setattr(hosted, "FOLD", 1.0)
    with hosting():
        yield at


def _listening(heard: Heard) -> Callable[[], bool]:
    """Whether a chat has answered and waits on what to say next."""
    return lambda: any(
        one.get("mode") == "listen"
        for said in heard.of("pending")[-1:]
        for one in said["pending"]
    )


def _epic(heard: Heard) -> str:
    """The epic a host said its run writes."""
    return next(
        (str(one["epic"]) for one in reversed(heard.of("run")) if one.get("epic")), ""
    )


def _chat(workspace: Path, said: str, **given: Any) -> tuple[daemon.Link, Heard, str]:
    slot = where.chat()
    link = daemon.attach("sdk", workspace=workspace, slot=slot)
    heard = Heard()
    link.heard(heard)
    link.start("chat", said, agents={"assistant": AGENT}, **given)
    return link, heard, slot


def test_two_chats_and_a_flow_go_at_once_in_one_workspace(workspace: Path) -> None:
    written(workspace, "waits", WAITS)
    with daemon.attach("sdk", workspace=workspace) as flow:
        flow.start("./waits", "forever", budget={"cost": 1})
        first, heard_first, slot_first = _chat(workspace, "first")
        second, heard_second, slot_second = _chat(workspace, "second")
        try:
            assert until(_listening(heard_first))
            assert until(_listening(heard_second))
            hosts = {one.slot: one.status() for one in daemon.daemons()}
            assert set(hosts) == {"", slot_first, slot_second}
            assert {one["state"] for one in hosts.values()} == {"running"}
            assert (hosts[slot_first]["turn"], hosts[slot_second]["turn"]) == (
                "done",
                "done",
            )
            # Each its own epic, and the flow's another.
            assert len({one["epic"] for one in hosts.values()}) == 3
            # A second flow is still one too many on the workspace's own host.
            with pytest.raises(daemon.Refused, match="already running"):
                flow.start("./waits", "again", budget={"cost": 1})
        finally:
            first.close()
            second.close()
            flow.stop()


def test_a_chat_nobody_reads_folds_away_and_is_carried_on_in_its_epic(
    workspace: Path, tmp_path: Path
) -> None:
    link, heard, slot = _chat(workspace, "remember teal")
    assert until(_listening(heard))
    name = _epic(heard)
    assert name
    link.close()

    # Between turns with nobody reading: it folds, its host goes, and its epic reads done.
    assert until(lambda: daemon.running(workspace, slot=slot) is None)
    (epic,) = [one for one in every() if one.name == name]
    folded = read(epic)
    assert folded is not None
    assert folded.how == "done"

    again, heard_again, _ = _chat(workspace, "what was it?", resume=str(epic))
    try:
        assert until(_listening(heard_again))
        # The same epic, opened again rather than a new one beside it.
        assert _epic(heard_again) == name
        assert [one.name for one in every()] == [name]
        going = read(epic)
        assert going is not None
        assert (going.how, going.reopened != "") == ("", True)
        # The agent carries on the session it had: a fork of it, resumed.
        first, *_, last = started(tmp_path)
        assert last["argv"][last["argv"].index("--resume") + 1] == first["session"]
        assert "--fork-session" in last["argv"]
        events = [
            json.loads(line)["event"]
            for line in (epic / "epic.jsonl").read_text().splitlines()
        ]
        assert events.count("began") == 1
        assert "reopened" in events
    finally:
        again.close()
