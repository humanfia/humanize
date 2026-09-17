"""When a turn says the agent has reached for something, which is not when it has finished.

A tool call's arguments are what it was called with, and for a `Write` they are the file: a
driver that waits for the whole of them before saying anything says nothing for as long as the
model takes to write the file, which on a slow one is minutes of a turn that looks hung. What
is checked here is that the row goes out at the first fragment there is anything to say it
about, and exactly once however many ways the backend then repeats the call.

Against the protocol rather than against live CLIs, for the reason
`tests/integration/agents/test_hooks_gate.py` is written that way: what is owed to the two
ends is exact, and reading it off a real turn would be reading it off whatever that model
happened to do. That one stands a relay and a process up to prove it and this one needs
neither, which is the whole of why they sit in different tiers.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from hmz.coganchor.agents import (
    AgentConfig,
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    PiAgent,
    pi,
)
from hmz.coganchor.agents.hooks import _ROOM, about, arriving

if TYPE_CHECKING:
    from hmz.coganchor.agents.event import Event


def _claude() -> Any:
    """A Claude conversation with no process behind it: `_read` is a reader and nothing more."""
    return ClaudeCodeAgent(ClaudeCodeAgentConfig(model="m", effort="high")).new()


def _pi() -> Any:
    """The same for pi, whose events are read the same way."""
    return PiAgent(AgentConfig(model="m", effort="high")).new()


def _said(session: Any, *lines: dict[str, Any]) -> list[Event]:
    """Everything a session says while it reads those lines, in the order it said it."""
    return [event for line in lines for event in session._read(json.dumps(line) + "\n")]


def _streamed(**event: Any) -> dict[str, Any]:
    """One `stream_event` of Claude's, as `--include-partial-messages` writes it."""
    return {"type": "stream_event", "event": event, "parent_tool_use_id": None}


def test_claude_says_a_write_as_it_starts_rather_than_once_the_file_has_arrived() -> (
    None
):
    """The path is in the first fragments and the file is in the rest of them."""
    session = _claude()

    opening = _said(
        session,
        _streamed(
            type="content_block_start",
            index=0,
            content_block={"type": "tool_use", "id": "toolu_1", "name": "Write"},
        ),
        _streamed(
            type="content_block_delta",
            index=0,
            delta={"type": "input_json_delta", "partial_json": '{"file_pat'},
        ),
    )

    assert opening == []  # half a path is not a row

    said = _said(
        session,
        _streamed(
            type="content_block_delta",
            index=0,
            delta={"type": "input_json_delta", "partial_json": 'h": "hello.py", "cont'},
        ),
    )

    assert [(one.kind, one.text) for one in said] == [("tool", "Write hello.py")]

    # And then the file itself, which is what the row would otherwise have waited for -- and
    # the message that finally carries the whole call, which is the same call and not a
    # second row.
    rest = _said(
        session,
        _streamed(
            type="content_block_delta",
            index=0,
            delta={"type": "input_json_delta", "partial_json": 'ent": "a\\nb\\nc"}'},
        ),
        _streamed(type="content_block_stop", index=0),
        {
            "type": "assistant",
            "message": {
                "id": "msg_1",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "Write",
                        "input": {"file_path": "hello.py", "content": "a\nb\nc"},
                    }
                ],
            },
        },
    )

    assert rest == []


def test_claude_says_a_call_whose_arguments_never_read_as_words_at_its_end() -> None:
    """A tool that takes none, or takes numbers: the name alone is still a reach."""
    session = _claude()

    said = _said(
        session,
        _streamed(
            type="content_block_start",
            index=1,
            content_block={"type": "tool_use", "id": "toolu_2", "name": "TodoWrite"},
        ),
        _streamed(
            type="content_block_delta",
            index=1,
            delta={"type": "input_json_delta", "partial_json": '{"count": 3}'},
        ),
        _streamed(type="content_block_stop", index=1),
    )

    assert [(one.kind, one.text) for one in said] == [("tool", "TodoWrite")]


def test_claude_says_a_call_the_message_got_to_first_only_the_once() -> None:
    """The message carrying the whole call lands a moment before the block it was in closes.

    So a call whose arguments never read as words is said there, and the closing block must
    not say it a second time: one tool call is one row.
    """
    session = _claude()

    said = _said(
        session,
        _streamed(
            type="content_block_start",
            index=0,
            content_block={"type": "tool_use", "id": "toolu_7", "name": "TodoWrite"},
        ),
        _streamed(
            type="content_block_delta",
            index=0,
            delta={
                "type": "input_json_delta",
                "partial_json": '{"todos": [{"content": "fix it"}]}',
            },
        ),
        {
            "type": "assistant",
            "message": {
                "id": "msg_1",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_7",
                        "name": "TodoWrite",
                        "input": {"todos": [{"content": "fix it"}]},
                    }
                ],
            },
        },
        _streamed(type="content_block_stop", index=0),
    )

    assert [(one.kind, one.text) for one in said] == [("tool", "TodoWrite")]


def test_claude_still_says_a_call_that_arrived_in_no_fragments_at_all() -> None:
    """An anchored turn, or a CLI that was never asked for the pieces, reads as it always did."""
    session = _claude()

    said = _said(
        session,
        {
            "type": "assistant",
            "message": {
                "id": "msg_1",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_3",
                        "name": "Bash",
                        "input": {"command": "ls -la"},
                    }
                ],
            },
        },
    )

    assert [(one.kind, one.text) for one in said] == [("tool", "Bash ls -la")]


def test_claude_says_an_agent_it_started_as_early_as_it_says_a_tool() -> None:
    """A fleet under a turn is agents, and the id is what ends the one that started."""
    session = _claude()

    said = _said(
        session,
        _streamed(
            type="content_block_start",
            index=0,
            content_block={"type": "tool_use", "id": "toolu_4", "name": "Task"},
        ),
        _streamed(
            type="content_block_delta",
            index=0,
            delta={
                "type": "input_json_delta",
                "partial_json": '{"description": "read the notes",',
            },
        ),
    )

    assert [(one.kind, one.text, one.whose) for one in said] == [
        ("subagent", "Task read the notes", "toolu_4")
    ]

    ended = _said(
        session,
        {
            "type": "user",
            "message": {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "toolu_4"}],
            },
        },
    )

    assert [(one.kind, one.whose) for one in ended] == [("subagent-ends", "toolu_4")]


def test_an_agent_under_a_turn_numbers_its_own_blocks_from_zero() -> None:
    """Its messages are written on this same stream, so the index alone names two calls."""
    session = _claude()

    said = _said(
        session,
        _streamed(
            type="content_block_start",
            index=0,
            content_block={"type": "tool_use", "id": "toolu_5", "name": "Read"},
        ),
        {
            "type": "stream_event",
            "parent_tool_use_id": "toolu_4",
            "event": {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "tool_use", "id": "toolu_6", "name": "Grep"},
            },
        },
        {
            "type": "stream_event",
            "parent_tool_use_id": "toolu_4",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": '{"q": "hello"}'},
            },
        },
        _streamed(
            type="content_block_delta",
            index=0,
            delta={"type": "input_json_delta", "partial_json": '{"file_path": "x.py"}'},
        ),
    )

    assert [(one.kind, one.text) for one in said] == [
        ("tool", "Grep hello"),
        ("tool", "Read x.py"),
    ]


def _pi_part(**event: Any) -> dict[str, Any]:
    """One `assistantMessageEvent` of pi's, as it writes one on stdout."""
    return {"type": "message_update", "assistantMessageEvent": event}


def test_pi_says_a_write_while_the_file_is_still_arriving() -> None:
    """The fragments say it as soon as one of them closes a value, and not before.

    Three pieces and no one of them is the call: 0.85.1 puts the id and the name on the
    start, each fragment of the JSON the arguments are written as on a `delta` of its own
    carrying nothing else -- not even the id -- and the call whole on the end. So the row is
    assembled here, which is what the numbered part of the message holds together.
    """
    session = _pi()

    opening = _said(
        session,
        _pi_part(
            type="toolcall_start", contentIndex=0, id="call_1|1", toolName="write"
        ),
        _pi_part(type="toolcall_delta", contentIndex=0, delta='{"path": "hel'),
    )

    # Half a path, which pi's own repaired reading of the fragments would have said whole: a
    # row saying `write hel` would be worse than no row at all.
    assert opening == []

    said = _said(
        session,
        _pi_part(type="toolcall_delta", contentIndex=0, delta='lo.py", "content": "a'),
    )

    assert [(one.kind, one.text) for one in said] == [("tool", "write hello.py")]

    # And the end of the call, which is where the row used to go out and where it must not
    # go out twice.
    ended = _said(
        session,
        _pi_part(
            type="toolcall_end",
            contentIndex=0,
            toolCall={
                "type": "toolCall",
                "id": "call_1|1",
                "name": "write",
                "arguments": {"path": "hello.py", "content": "a\nb\nc"},
            },
        ),
    )

    assert ended == []


def test_pi_tells_two_calls_of_one_message_apart_by_where_they_are_in_it() -> None:
    """Which is all there is to tell them apart by: a fragment carries no id of its own."""
    session = _pi()

    said = _said(
        session,
        _pi_part(type="toolcall_start", contentIndex=1, id="call_a", toolName="read"),
        _pi_part(type="toolcall_start", contentIndex=2, id="call_b", toolName="bash"),
        _pi_part(type="toolcall_delta", contentIndex=2, delta='{"command": "ls"}'),
        _pi_part(type="toolcall_delta", contentIndex=1, delta='{"path": "x.py"}'),
    )

    assert [(one.kind, one.text) for one in said] == [
        ("tool", "bash ls"),
        ("tool", "read x.py"),
    ]


def test_pi_holds_no_more_of_the_arguments_than_a_row_could_ever_be_drawn_from() -> (
    None
):
    """The rest of a `write` is the file, and joining it to itself per fragment is quadratic.

    Which is what pi took its own cumulative message out of `message_update` to be rid of,
    and what this would put back on the near side of the pipe.
    """
    session = _pi()

    said = _said(
        session,
        _pi_part(type="toolcall_start", contentIndex=0, id="call_1", toolName="write"),
        _pi_part(type="toolcall_delta", contentIndex=0, delta='{"content": "'),
        *(
            _pi_part(type="toolcall_delta", contentIndex=0, delta="x" * 1000)
            for _ in range(20)
        ),
    )

    assert said == []  # the file is not a path, however much of it arrives
    (_, _, sofar) = session._calling[0]
    assert len(sofar) <= _ROOM
    # And what it holds is exactly what `arriving` would have read, no less: a shorter buffer
    # would lose a value that closes late and a row with it.
    assert pi._SCANNED == _ROOM


def test_pi_says_nothing_more_about_a_call_it_has_already_said() -> None:
    """The row went out at the fragment that closed the path; the file after it is noise."""
    session = _pi()

    said = _said(
        session,
        _pi_part(type="toolcall_start", contentIndex=0, id="call_1", toolName="write"),
        _pi_part(type="toolcall_delta", contentIndex=0, delta='{"path": "x.py", "c'),
        _pi_part(type="toolcall_delta", contentIndex=0, delta='ontent": "a\\nb"}'),
    )

    assert [(one.kind, one.text) for one in said] == [("tool", "write x.py")]
    # And not held on to either: nothing after the row is ever read again.
    assert session._calling[0][2] == '{"path": "x.py", "c'


def test_pi_says_no_row_at_all_for_an_end_that_carries_no_call() -> None:
    """A bare `tool` row would tell a hook the agent reached for something unnamed."""
    session = _pi()

    assert _said(session, _pi_part(type="toolcall_end", contentIndex=0)) == []


def test_pi_says_nothing_for_fragments_of_a_call_it_never_saw_the_start_of() -> None:
    """A row naming `tool` and a command would say less than the row that never came."""
    session = _pi()

    assert (
        _said(session, _pi_part(type="toolcall_delta", contentIndex=0, delta="{}"))
        == []
    )


def test_pi_says_a_call_whose_arguments_said_nothing_at_its_end() -> None:
    """The end says it whatever the arguments came to: a reach is a reach."""
    session = _pi()

    said = _said(
        session,
        {
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "toolcall_end",
                "contentIndex": 0,
                "toolCall": {"id": "call_2|2", "name": "list_todos", "arguments": {}},
            },
        },
    )

    assert [(one.kind, one.text) for one in said] == [("tool", "list_todos")]


def test_a_row_says_what_the_whole_of_the_call_would_have_said() -> None:
    """One call reads as one row, whichever of the two ways of reading it got there first.

    A hook is told what the agent reached for off that row, so a reader that dug into a
    nested argument the whole-message one never looks at would be telling a flow two
    different things about one tool call depending on how its CLI happened to send it.
    """
    for called in (
        {"file_path": "hello.py", "content": "a\nb\nc"},
        {"count": 3, "path": "x.py"},
        {"path": "   ", "command": "ls -la"},
        {"todos": [{"content": "fix the bug"}]},
        {"edits": [{"old": "a"}], "note": "second pass"},
        {"command": 'echo "a": "b"', "path": "x"},
        {"command": "grep -r {a} ."},
        {"nested": {"key": "value"}, "path": "/x"},
        {},
    ):
        assert arriving(json.dumps(called)) == about(called), called


def test_half_an_argument_is_not_a_row() -> None:
    """A row saying `Write /tmp/se` would be worse than the row that has not come yet."""
    assert arriving('{"file_path": "/tmp/se') == ""
    assert arriving('{"file_path": ') == ""
    assert arriving("") == ""
    assert arriving('{"file_path": "/tmp/sea.py"') == "/tmp/sea.py"
    # And an escape JSON does not have is not a value this can name: whatever wrote that is
    # not writing what this is here to read.
    assert arriving(r'{"file_path": "\q"}') == ""


def test_a_payload_that_never_ends_is_not_read_again_for_every_fragment_of_it() -> None:
    """The file being written is not the path it is being written to, however long it gets."""
    assert arriving('{"content": "' + "x" * (_ROOM * 4)) == ""
