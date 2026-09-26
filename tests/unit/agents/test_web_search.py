"""Whether an agent may search the web, and how each backend is told it.

One switch, and it has to mean one thing wherever it is read: an agent that may search the
web searches the web, on a CLI whose own web search is on until it is taken away and on one
whose own is off until it is asked for. So it is sent in both directions where a backend can
be told both, and a backend that cannot be told refuses it off rather than going on searching
under a setting that says it is not.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from hmz.coganchor import backends
from hmz.coganchor.agents import (
    ClaudeCodeAgent,
    ClaudeCodeAgentConfig,
    DshAgentConfig,
    GrokBuildAgent,
    GrokBuildAgentConfig,
    KimiCodeCLIAgent,
    KimiCodeCLIAgentConfig,
    OpencodeAgent,
    OpencodeAgentConfig,
    PiAgent,
    PiAgentConfig,
    QwenCodeAgent,
    QwenCodeAgentConfig,
)

# : The backends that can be told, and the ones that cannot. Read off `hmz.coganchor.backends` here
# as : everything else reads it, so a backend that gains a way of being told is a backend this :
# notices rather than a list to remember.
TELLABLE = (
    "claude",
    "codex",
    "dsh",
    "grok",
    "kimi",
    "qwen",
    "opencode",
    "mimo",
    "zcode",
)


def test_an_agent_nobody_has_been_asked_about_is_told_neither_way() -> None:
    """Whether it reads the internet is then the CLI's own answer rather than humanize's."""
    assert ClaudeCodeAgentConfig(model="m", effort="high").web_search is None


def test_which_backends_can_be_told_is_read_off_the_one_place_a_cli_is_written_down() -> (
    None
):
    """One list of what a CLI is, so a switch and a driver cannot come to disagree."""
    told = {one.name for one in backends.profiles() if one.searches}

    assert told == set(TELLABLE)


def test_claude_is_refused_the_two_tools_that_reach_the_web() -> None:
    """A tool call is a tool call, and `--disallowedTools` is that call written as a rule."""
    config = ClaudeCodeAgentConfig(model="m", effort="high", web_search=True)
    searching = ClaudeCodeAgent(config).new()._command()

    assert "--disallowedTools" not in searching

    argv = ClaudeCodeAgent(replace(config, web_search=False)).new()._command()

    assert argv[argv.index("--disallowedTools") + 1] == "WebSearch,WebFetch"


def test_claude_is_left_the_two_where_nobody_said_anything_about_the_web() -> None:
    """Silence is not a no, and the flag takes rules rather than an answer to a question.

    An agent whose flow never said is one Claude ships `WebSearch` and `WebFetch` to, so a
    rule written for it would be humanize taking a tool away in the name of a question it was
    never asked -- which is the one thing `not web_search` would have done with the third
    state, `None` being falsy the way `False` is.
    """
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="m", effort="high", web_search=None)
    )

    assert "--disallowedTools" not in agent.new()._command()


def test_claude_says_both_things_it_says_with_that_flag_in_the_one_list() -> None:
    """The flag takes one list, so goals switched off and no web search are one list."""
    agent = ClaudeCodeAgent(
        ClaudeCodeAgentConfig(model="m", effort="high", web_search=False, goals=False)
    )
    argv = agent.new()._command()

    assert argv.count("--disallowedTools") == 1
    assert argv[argv.index("--disallowedTools") + 1] == (
        "Agent,ScheduleWakeup,CronCreate,CronDelete,CronList,Workflow,WebSearch,WebFetch"
    )


@pytest.mark.parametrize(
    ("kind", "config", "flag"),
    [
        (QwenCodeAgent, QwenCodeAgentConfig, "--exclude-tools"),
    ],
)
def test_a_backend_that_withholds_tools_withholds_the_two_that_reach_the_web(
    kind: type, config: type, flag: str
) -> None:
    """At every rung rather than only at the one whose own ladder already refuses them."""
    session = kind(config(model="m", effort="high", web_search=False)).new()
    argv = session._turn("hi")[0]

    assert set(argv[argv.index(flag) + 1].split(",")) >= {"web_search", "web_fetch"}


def test_an_agent_nobody_said_either_way_about_is_left_where_its_cli_leaves_it() -> (
    None
):
    """None is not False: silence takes nothing away, and `qwen` goes on as `qwen` does."""
    session = QwenCodeAgent(
        QwenCodeAgentConfig(model="m", effort="high", web_search=None)
    ).new()

    assert "--exclude-tools" not in session._turn("hi")[0]


def test_grok_says_it_with_the_flag_its_cli_has_for_exactly_that() -> None:
    """`--disable-web-search` is the CLI's own word for the two tools, so it is the word."""
    session = GrokBuildAgent(
        GrokBuildAgentConfig(model="m", effort="high", web_search=False)
    ).new()

    argv = session._turn("hi")[0]

    assert "--disable-web-search" in argv
    # And nothing is spelled out under the general flag that the named one already says.
    assert "--disallowed-tools" not in argv


def test_a_rung_that_already_withholds_them_does_not_withhold_them_twice() -> None:
    """The two say the same thing here, and it is a switch rather than a list."""
    argv = (
        GrokBuildAgent(
            GrokBuildAgentConfig(
                model="m", effort="high", permission="workspace-write", web_search=False
            )
        )
        .new()
        ._turn("hi")[0]
    )

    assert argv.count("--disable-web-search") == 1


def test_grok_is_told_nothing_where_nobody_said_anything_about_the_web() -> None:
    """None is the agent nobody was asked about, which `grok` answers for itself.

    The flag is the one that takes searching away, so an agent that said nothing must not be
    given it: `not None` is true, and the shorter test would have switched off the search of
    every agent nobody had an opinion about.
    """
    argv = (
        GrokBuildAgent(GrokBuildAgentConfig(model="m", effort="high", web_search=None))
        .new()
        ._turn("hi")[0]
    )

    assert "--disable-web-search" not in argv


def test_opencode_denies_every_reaching_out_tool_it_names() -> None:
    """Its permission table is where each tool is allowed or denied, so it is said there.

    Every one of them and not just the page fetcher: it searches the web as well as reads it,
    and an agent left the second way out is an agent still searching.
    """
    config = OpencodeAgentConfig(
        model="p/m", effort="high", permission="bypass", web_search=True
    )
    session = OpencodeAgent(config).new()
    permits, reaches = type(session).permits, type(session).reaches

    assert reaches == ("webfetch", "websearch")
    allowed = json.loads(session._environment()[permits])
    assert [allowed[tool] for tool in reaches] == ["allow", "allow"]

    session = OpencodeAgent(replace(config, web_search=False)).new()
    allowed = json.loads(session._environment()[permits])

    assert [allowed[tool] for tool in reaches] == ["deny", "deny"]


def test_a_switch_nobody_stated_is_not_a_table_saying_it_is_on() -> None:
    """The variable is left alone, so the turn reaches the web however that machine does.

    Which is the one reading of a switch nobody touched that does not put words in somebody's
    mouth: a table saying `allow` would be humanize switching it on for a person who had
    switched it off, and the rung beside it says nothing to write either.
    """
    config = OpencodeAgentConfig(
        model="p/m", effort="high", permission="", web_search=None
    )
    session = OpencodeAgent(config).new()

    assert type(session).permits not in session._environment()

    # Stated, it goes back in -- with the rung still unsaid, so the table holds the two ways
    # out and nothing about editing or running commands.
    session = OpencodeAgent(replace(config, web_search=True)).new()
    allowed = json.loads(session._environment()[type(session).permits])

    assert allowed == dict.fromkeys(type(session).reaches, "allow")


def test_kimi_withholds_the_two_tools_its_daemon_reaches_the_web_with() -> None:
    """Withheld through the prompt body, which is the one of the two routes that takes them.

    `disabled_tools` is a key of the daemon's prompt schema and not of its session profile's,
    and the profile route would accept it and drop it -- so it has to be on the body the turn
    is submitted with rather than on the one the session is set up with.
    """
    config = KimiCodeCLIAgentConfig(model="m", effort="high")
    profile, prompt = KimiCodeCLIAgent(replace(config, web_search=False)).new()._told()

    assert prompt["disabled_tools"] == ["WebSearch", "FetchURL"]
    # And nothing of it reaches the profile, where the daemon has nowhere to put it.
    assert "disabled_tools" not in profile


def test_kimi_says_it_in_both_directions_because_its_deny_list_is_kept() -> None:
    """The daemon writes the session's disabled tools to disk, so on has to be said too.

    A session resumed or forked from one that had the web withheld comes back with it still
    withheld, and an agent that may search would then be an agent that quietly does not.
    """
    searching = KimiCodeCLIAgent(
        KimiCodeCLIAgentConfig(model="m", effort="high", web_search=True)
    ).new()

    assert searching._told()[1]["disabled_tools"] == []


def test_kimi_says_nothing_about_the_web_for_an_agent_nobody_was_asked_about() -> None:
    """The way it sends no rung for one at no rung: the session is left where it was."""
    unasked = KimiCodeCLIAgent(
        KimiCodeCLIAgentConfig(model="m", effort="high", web_search=None)
    ).new()

    assert "disabled_tools" not in unasked._told()[1]


def test_dsh_is_told_by_the_plugins_its_composition_carries() -> None:
    """It has no flag and no deny-list: what a turn may reach for is what is mounted.

    Both directions, because the harness's own composition mounts no web at all -- so on is
    mounted rather than assumed, the way Codex is asked for a search it does not do unasked.
    """
    from hmz.coganchor.agents.dsh import _WEB, _composed

    mounted = [plugin["name"] for plugin in _WEB]
    config = DshAgentConfig(model="m", effort="high", web_search=True)

    searching = _composed(config)
    assert all(name in searching for name in mounted)

    quiet = _composed(replace(config, web_search=False))
    assert not any(name in quiet for name in mounted)
    # And an agent nobody was asked about is left where the bare SDK leaves one.
    assert not any(
        name in _composed(replace(config, web_search=None)) for name in mounted
    )


def test_a_backend_with_no_way_of_being_told_refuses_it_off() -> None:
    """An agent that quietly went on searching would be a setting that lies."""
    with pytest.raises(ValueError, match="no way of being told"):
        PiAgent(PiAgentConfig(model="m", effort="high", web_search=False))


def test_it_is_refused_wherever_the_config_arrives() -> None:
    """Where the agent is made, and where a running one is set up as something else."""
    agent = PiAgent(PiAgentConfig(model="m", effort="high"))

    with pytest.raises(ValueError, match="no way of being told"):
        agent.reconfigure(replace(agent.config, web_search=False))

    assert agent.config.web_search is None  # and the agent is left as it was


def test_an_agent_that_may_not_search_is_another_agent_at_the_same_model() -> None:
    """The config is frozen: this is a second agent rather than the first one changed."""
    config = ClaudeCodeAgentConfig(model="m", effort="high")

    assert replace(config, web_search=False) != config
    assert config.web_search is None


def test_a_backend_that_cannot_be_told_takes_the_silence() -> None:
    """Off is what it refuses. Nothing said is not an off.

    An agent nobody was asked about goes on reaching the web exactly as its own CLI lets it,
    which is the thing the refusal is honest about rather than the thing it forbids -- and
    reading the silence as a no would refuse every backend that cannot be told, which is most
    of them, the moment a config stopped answering this on anybody's behalf.
    """
    quiet = PiAgent(PiAgentConfig(model="m", effort="high", web_search=None))

    assert quiet.config.web_search is None
    pi = backends.named("pi")

    assert pi is not None
    assert not pi.searches  # so there is nothing to tell it with
    with pytest.raises(ValueError, match="no way of being told not to search the web"):
        PiAgent(PiAgentConfig(model="m", effort="high", web_search=False))
