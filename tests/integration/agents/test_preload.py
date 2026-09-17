"""The preload layer: a coding agent's own runtime, patched from inside, saying what it did.

Four of the CLIs driven here are Node programs, and Node reads `NODE_OPTIONS` before it reads
the program -- so a file of ours is in the process before the CLI has run a line, and the calls
a turn makes are functions to patch. What is checked here is the half of that road this machine
can walk on its own: a report read out of one line, the unix socket they arrive on, the moments
they become, which backends say their runtime takes one, and the variables each driver composes
for an agent somebody is listening to. Nothing here starts a Node program, so CI runs the lot.

The other half is `tests/system/agents/test_preload.py`, where a real `node` loads the runtime
and says what it spawned, read, wrote and opened. Those nine used to live here behind a bare
`pytest.skip`, which is exactly the failure the tiers are drawn against: unmarked, they vanished
on a machine without node with nobody counting, and ran a real external binary inside the tier
everyone takes to be offline on a machine with one.
"""

from __future__ import annotations

import socket

import pytest

from hmz.coganchor.agents import AgentConfig, Hooks, Moment, Occasion
from hmz.coganchor.agents import preload as layer
from hmz.coganchor.agents.preload import RUNTIME, Watch, preloaded, reported, runtime
from hmz.coganchor.backends import named
from tests.agents import preloading
from tests.stubs import HereAnchor, ShellAgent

#: What the anchored stand-in below is configured with, which nothing here reads back.
CONFIG = AgentConfig(model="m", effort="high")


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('{"did": "spawn", "what": "git status"}', ("spawn", "git status")),
        ('{"did": "read", "what": "/work/one.py"}', ("read", "/work/one.py")),
        ('{"did": "quiet"}', ("quiet", "")),
        ('{"did": "connect", "what": 8080}', ("connect", "")),
        ("not json at all", None),
        ("[1, 2, 3]", None),
        ('{"what": "/work/one.py"}', None),
        ('{"did": "", "what": "x"}', None),
        ('{"did": 3, "what": "x"}', None),
    ],
)
def test_what_one_line_a_runtime_wrote_says_its_process_did(
    line: str, expected: tuple[str, str] | None
) -> None:
    """A report is read rather than trusted: what another program wrote may be anything."""
    assert reported(line) == expected


def test_a_runtime_that_says_what_it_did_reaches_the_agents_own_moments() -> None:
    """The whole point: a report becomes a `PreToolUse`, named after what the runtime did."""
    hooks = Hooks(frozenset(Moment), "worker")
    said: list[Occasion] = []
    hooks.on(Moment.PRE_TOOL_USE, said.append)
    watch = Watch(hooks)
    try:
        held = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        held.connect(watch.address())
        with held:
            held.sendall(
                b'{"did": "spawn", "what": "git push"}\n{"did": "write", "what": "/x"}\n'
            )
            arrived = preloading.waits(said, 2)
    finally:
        watch.close()

    assert [(one.tool, one.about) for one in arrived] == [
        ("spawn", "git push"),
        ("write", "/x"),
    ]
    assert {one.moment for one in arrived} == {Moment.PRE_TOOL_USE}
    assert {one.agent for one in arrived} == {"worker"}


def test_a_hook_that_only_watches_one_thing_is_not_told_about_the_others() -> None:
    """Which is what naming a report after what the runtime did is for."""
    hooks = Hooks(frozenset(Moment), "worker")
    said: list[Occasion] = []
    hooks.on(Moment.PRE_TOOL_USE, said.append, tool="spawn")
    watch = Watch(hooks)
    try:
        watch.tells('{"did": "read", "what": "/one"}')
        watch.tells('{"did": "spawn", "what": "ls"}')
    finally:
        watch.close()

    assert [one.about for one in said] == ["ls"]


def test_a_hook_that_raises_is_a_hook_that_said_nothing() -> None:
    """A flow must not fail because something watching its agent did."""
    hooks = Hooks(frozenset(Moment), "worker")

    def angry(occasion: Occasion) -> None:
        raise RuntimeError(occasion.tool)

    hooks.on(Moment.PRE_TOOL_USE, angry)
    watch = Watch(hooks)
    try:
        watch.tells(
            '{"did": "spawn", "what": "ls"}'
        )  # which is to say: this does not raise
    finally:
        watch.close()


def test_nothing_at_all_is_set_for_an_agent_nobody_is_listening_to() -> None:
    """No socket, no thread and no patched runtime: the turns are the turns they always were."""
    agent = preloading.agent()

    assert preloaded(agent, {"KEPT": "yes"}) == {"KEPT": "yes"}


def test_the_preload_and_where_to_report_are_set_for_an_agent_with_a_hook_hung() -> (
    None
):
    """One variable carries the file, the other says where to say what it saw."""
    agent = preloading.agent()
    preloading.seen(agent)
    added = preloaded(agent, {"KEPT": "yes"})
    try:
        assert added["KEPT"] == "yes"
        assert added["NODE_OPTIONS"] == f"--require {runtime()}"
        assert added["HMZ_PRELOAD_AT"].endswith(".sock")
    finally:
        layer._WATCHED[agent].close()


def test_an_option_somebody_else_set_is_kept_and_added_to() -> None:
    """A `--max-old-space-size` in somebody's shell profile is theirs; this goes after it."""
    agent = preloading.agent()
    preloading.seen(agent)
    added = preloaded(agent, {"NODE_OPTIONS": "--max-old-space-size=2048"})
    try:
        assert (
            added["NODE_OPTIONS"] == f"--max-old-space-size=2048 --require {runtime()}"
        )
    finally:
        layer._WATCHED[agent].close()


def test_nothing_is_set_for_a_turn_that_lands_on_another_machine() -> None:
    """A socket and a file on this machine name nothing at all on that one."""
    agent = _Anchored(CONFIG, HereAnchor(target="ssh://build-box", workspace="/srv"))
    preloading.seen(agent)

    assert preloaded(agent, {"KEPT": "yes"}) == {"KEPT": "yes"}


def test_one_listener_serves_an_agent_however_many_turns_it_takes() -> None:
    """A backend holding every conversation in one server has one runtime for all of them."""
    agent = preloading.agent()
    preloading.seen(agent)
    try:
        first = preloaded(agent, {})["HMZ_PRELOAD_AT"]
        assert preloaded(agent, {})["HMZ_PRELOAD_AT"] == first
    finally:
        layer._WATCHED[agent].close()


def test_the_file_a_runtime_is_told_to_load_is_found_through_the_package() -> None:
    """Through the package rather than beside a module, so an install of any shape answers.

    That it is *in* the wheel is the build backend's to do and `uv build` to show; what is
    checked here is that what asks for it asks the way that finds it either way.
    """
    from pathlib import Path

    file = Path(runtime())

    assert file.name == RUNTIME
    assert file.parent.name == "preload"
    assert file.is_file()
    assert "NODE_OPTIONS" in file.read_text()


def test_the_backends_whose_runtime_takes_one_say_so_where_facts_are_written_down() -> (
    None
):
    """Which is what `anchor:preloaded` is read off, and the only place it is said."""
    for name in ("kimi", "qwen", "mimo", "pi"):
        profile = named(name)
        assert profile is not None
        assert profile.preloads == "NODE_OPTIONS"
        assert "anchor:preloaded" in profile.tags()
    # And the ones with a runtime compiled into them, which read none of this.
    for name in ("claude", "opencode", "codex", "grok"):
        profile = named(name)
        assert profile is not None
        assert profile.preloads == ""
        assert "anchor:preloaded" not in profile.tags()


class _Anchored(ShellAgent):
    """An agent whose turns land on a machine that is not this one."""

    def __init__(self, config: AgentConfig, anchor: HereAnchor) -> None:
        super().__init__(config)
        self._held = anchor

    @property
    def anchor(self) -> HereAnchor:
        return self._held
