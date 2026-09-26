"""The skills a flow brings, and the sessions they are mounted onto.

A flow is a directory, and `skills/` inside it is what that flow works by. A role names the
ones its agent is given -- `_skills` where the role is declared -- and every session that agent
opens is given them: copied where that backend reads a project's own skills, for as long as
the session lives, and taken away again after, so a flow carries what it needs rather than
expecting it to be installed on whoever's machine runs it. A role may also name skills that
live in somebody else's repository, which are fetched and then mounted the same way.

Most of what is checked here is the mount, which is the agent's: what the runtime hands a
session's agent -- :func:`~hmz.runtime.flowing.skills.brought`, loaded with `loads` -- and what
the agent does with it. A run through the runtime, with a stand-in CLI, checks that a role is
given the skills it names and no others.
"""

from __future__ import annotations

import contextlib
import gc
import subprocess
import time
from typing import TYPE_CHECKING

import pytest

from hmz.coganchor.agents import AgentBase, AgentConfig
from hmz.coganchor.agents.skills import Loaded
from hmz.runtime.flowing.skills import brought, cached
from hmz.runtime.runner import Refused, Runner
from tests.flows import standins
from tests.stubs import ShellAgent, written

if TYPE_CHECKING:
    from pathlib import Path

CONFIG = AgentConfig(model="m", effort="high")


class ClaudeAgent(ShellAgent):
    """A stand-in whose backend is one that reads a project's own skills.

    The mount is a fact about the CLI -- which directory it reads skills out of -- and a
    stand-in agent named after nothing has no such directory, so there would be nothing to
    watch. Named for the backend, which is how every agent here says which one it drives.
    """


class CodexAgent(ShellAgent):
    """A stand-in named for Codex, which reads the shared project skill directory."""


class KimiAgent(ShellAgent):
    """A stand-in named for Kimi, which reads the shared project skill directory."""


class GrokBuildAgent(ShellAgent):
    """A stand-in named for Grok Build, which reads the shared project skill directory."""


class QwenCodeAgent(ShellAgent):
    """A stand-in named for Qwen Code, which reads the shared project skill directory."""


class OpencodeAgent(ShellAgent):
    """A stand-in named for opencode, which reads the shared project skill directory."""


class MimoCodeAgent(ShellAgent):
    """A stand-in named for mimocode, which reads the shared project skill directory."""


class ZcodeAgent(ShellAgent):
    """A stand-in named for ZCode, which reads the shared project skill directory."""


class PiAgent(ShellAgent):
    """A stand-in named for pi, whose project directories are read only once approved."""


#: A flow that is a directory, which is what brings skills: what it does is not the point.
DOES = '''"""Does the one thing it is told."""

from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    agent: Agent


class Envs(EnvCollection):
    here: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def mine(task, *, agents, envs, params, ctx):
    session = await agents["agent"].spawn(env=envs["here"])
    return await agents["agent"].run(task, session=session)
'''

#: A flow whose role names one of its skills, and reads what its session was given while the
#: session is open. NAMED is filled in per test.
READS = '''"""Reads what its agent's session was given."""

from hmz.flows import (
    Agent,
    AgentCollection,
    EnvCollection,
    FilesEnvMixin,
    FlowParams,
    LocalEnv,
    ShellEnvMixin,
    flow,
)


class Noter(Agent):
    _skills = NAMED


class Here(LocalEnv, FilesEnvMixin, ShellEnvMixin): ...


class Agents(AgentCollection):
    agent: Noter


class Envs(EnvCollection):
    here: Here


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def reads(task, *, agents, envs, params, ctx):
    here = envs["here"]
    session = await agents["agent"].spawn(env=here)
    await agents["agent"].run(task, session=session)
    code, out, _ = await here.exec(["ls", ".claude/skills"])
    said = await here.read(".claude/skills/note-taking/SKILL.md") if "note-taking" in out else b""
    return out.split(), said.decode()
'''


def _given(agent: AgentBase, flow: Path, *urls: str) -> AgentBase:
    """What the runtime hands a session's agent: the skills the flow brings, loaded onto it."""
    agent.loads(brought(flow, urls))
    return agent


def skill(name: str, says: str = "Do the thing.") -> str:
    """One `SKILL.md`, as every one of these CLIs lays one out."""
    return f"---\nname: {name}\ndescription: does a thing\n---\n\n{says}\n"


def _repository(at: Path, *names: str) -> Path:
    """Somebody else's repository of skills, to be named by a flow and fetched from."""
    for name in names:
        (at / "skills" / name).mkdir(parents=True)
        (at / "skills" / name / "SKILL.md").write_text(skill(name))
    for said in (
        ["init", "-b", "main"],
        ["config", "user.email", "t@example.com"],
        ["config", "user.name", "t"],
        ["add", "-A"],
        ["commit", "-m", "skills"],
    ):
        subprocess.run(["git", "-C", str(at), *said], check=True, capture_output=True)
    return at


def test_a_flows_own_skills_are_the_ones_in_its_skills_directory(
    tmp_path: Path,
) -> None:
    """Found by looking, since they are in it: a flow does not declare what it holds."""
    at = written(
        tmp_path, "mine", DOES, {"note-taking": skill("note-taking"), "b": skill("b")}
    )

    assert [(one.name, one.whose) for one in brought(at)] == [
        ("b", "this flow"),
        ("note-taking", "this flow"),
    ]
    # And a flow that brings none says so rather than raising about a directory it has not.
    assert brought(written(tmp_path, "bare", DOES)) == []


def test_a_skill_in_somebody_elses_repository_is_named_and_fetched(
    tmp_path: Path,
) -> None:
    """A git URL and, after the `#`, which of that repository's skills is wanted."""
    theirs = _repository(tmp_path / "theirs", "deep-research", "shallow-research")
    at = written(tmp_path / "flows", "mine", DOES)

    (one,) = brought(at, [f"{theirs}#deep-research"])

    assert one.name == "deep-research"
    assert one.at == cached(str(theirs)) / "skills" / "deep-research"
    assert one.whose.endswith("#deep-research")
    # Named without one, every skill in it is brought.
    assert [one.name for one in brought(at, [str(theirs)])] == [
        "deep-research",
        "shallow-research",
    ]


def test_a_skill_named_that_the_repository_does_not_hold_stops_the_run(
    tmp_path: Path,
) -> None:
    """A typo, or a rename upstream: either way the flow has not got what it works by."""
    theirs = _repository(tmp_path / "theirs", "deep-research")
    at = written(tmp_path / "flows", "mine", DOES)

    with pytest.raises(OSError, match="deep-reseach"):
        brought(at, [f"{theirs}#deep-reseach"])  # codespell:ignore reseach


def test_two_repositories_of_the_same_name_are_two_directories(tmp_path: Path) -> None:
    """`acme/skills` on one host is not `acme/skills` on another, and neither is the other."""
    one = _repository(tmp_path / "one/acme/skills", "deep-research")
    other = _repository(tmp_path / "other/acme/skills", "shallow-research")

    assert cached(str(one)) != cached(str(other))
    assert [
        held.name for held in brought(written(tmp_path, "a", DOES), [str(one)])
    ] == ["deep-research"]
    assert [
        held.name for held in brought(written(tmp_path, "b", DOES), [str(other)])
    ] == ["shallow-research"]


def test_the_flows_own_wins_a_name_a_repository_also_uses(tmp_path: Path) -> None:
    """A fork that edited a skill meant the edited one."""
    theirs = _repository(tmp_path / "theirs", "deep-research")
    at = written(
        tmp_path / "flows",
        "mine",
        DOES,
        {"deep-research": skill("deep-research", says="Mine, not theirs.")},
    )

    (one,) = brought(at, [str(theirs)])

    assert one.whose == "this flow"
    assert "Mine, not theirs" in (one.at / "SKILL.md").read_text()


def test_a_repository_that_cannot_be_reached_stops_the_run_before_it_starts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: None
) -> None:
    """A flow that works by a skill it has not got is not one to start and find out later."""
    monkeypatch.chdir(tmp_path)
    written(
        tmp_path / ".humanize/flows",
        "reads",
        READS.replace("NAMED", '("/nowhere/at/all#note-taking",)'),
    )
    run = Runner(
        "reads", agents={"agent": "claude/claude-haiku-4-5:low"}, budget={"cost": 1}
    )

    with pytest.raises(Refused, match="cannot be fetched"):
        run.run("Reply with the single word: hi")


def test_a_session_is_given_them_where_its_backend_reads_a_projects_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mounted as the session opens, and gone once the session it was for has ended."""
    monkeypatch.chdir(tmp_path)
    at = written(
        tmp_path / ".humanize/flows",
        "mine",
        DOES,
        {"note-taking": skill("note-taking")},
    )

    _given(ClaudeAgent(CONFIG), at)(
        "ls .claude/skills > listed.txt; cat .claude/skills/note-taking/SKILL.md > read.txt"
    )
    gc.collect()  # the session the turn ran in, let go of by the flow

    assert (tmp_path / "listed.txt").read_text().split() == ["note-taking"]
    assert "does a thing" in (tmp_path / "read.txt").read_text()
    # Mounted rather than installed: what the flow brought is not left on the machine.
    assert not (tmp_path / ".claude").exists()


@pytest.mark.parametrize(
    "agent_type",
    [
        CodexAgent,
        KimiAgent,
        GrokBuildAgent,
        QwenCodeAgent,
        OpencodeAgent,
        MimoCodeAgent,
        ZcodeAgent,
    ],
)
def test_a_shared_skill_backend_is_given_flow_skills_in_the_project_directory(
    agent_type: type[ShellAgent],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every backend that reads the shared project directory is given the flow's skills."""
    monkeypatch.chdir(tmp_path)
    at = written(
        tmp_path / ".humanize/flows",
        "mine",
        DOES,
        {"note-taking": skill("note-taking")},
    )

    _given(agent_type(CONFIG), at)(
        "ls .agents/skills > listed.txt; "
        "cat .agents/skills/note-taking/SKILL.md > read.txt"
    )
    gc.collect()

    assert (tmp_path / "listed.txt").read_text().split() == ["note-taking"]
    assert "does a thing" in (tmp_path / "read.txt").read_text()
    assert not (tmp_path / ".agents").exists()


def test_a_backend_that_would_not_read_them_there_is_given_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mount is a fact about the CLI, so a backend that reads no such directory gets none.

    pi is the case: it reads `.agents/skills` under the workspace, but only for a project it
    has been told to trust, which a driven turn never is. Copying a flow's skills there would
    leave a directory in somebody's project that no turn of that flow would ever read.
    """
    monkeypatch.chdir(tmp_path)
    at = written(
        tmp_path / ".humanize/flows",
        "mine",
        DOES,
        {"note-taking": skill("note-taking")},
    )

    _given(PiAgent(CONFIG), at)("ls -a > listed.txt")
    gc.collect()

    assert ".agents" not in (tmp_path / "listed.txt").read_text().split()
    assert not (tmp_path / ".agents").exists()


def test_a_projects_own_skill_of_that_name_is_left_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the project keeps is the project's, and a flow does not write over it."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude" / "skills" / "note-taking").mkdir(parents=True)
    (tmp_path / ".claude" / "skills" / "note-taking" / "SKILL.md").write_text(
        skill("note-taking", says="The project's own.")
    )
    at = written(
        tmp_path / ".humanize/flows",
        "mine",
        DOES,
        {"note-taking": skill("note-taking")},
    )

    _given(ClaudeAgent(CONFIG), at)(
        "cat .claude/skills/note-taking/SKILL.md > read.txt"
    )
    gc.collect()

    assert "The project's own" in (tmp_path / "read.txt").read_text()
    # And it is still there afterwards: nothing of the project's was taken away with the mount.
    assert (tmp_path / ".claude" / "skills" / "note-taking" / "SKILL.md").is_file()


def test_two_sessions_of_one_flow_share_the_mount_until_the_last_is_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One closing must not take out from under the other what both were given."""
    monkeypatch.chdir(tmp_path)
    at = written(tmp_path, "twice", DOES, {"note-taking": skill("note-taking")})
    agent = _given(ClaudeAgent(CONFIG), at)

    one, other = agent.new(), agent.new()
    one("true")
    other("true")
    one.close()
    # The other is still open, so what they share is still there for it.
    other("ls .claude/skills > while-one-is-shut.txt")
    other.close()
    gc.collect()

    assert (tmp_path / "while-one-is-shut.txt").read_text().split() == ["note-taking"]
    assert not (tmp_path / ".claude").exists()


def test_a_called_flows_skill_does_not_take_over_the_name_from_the_flow_that_called_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two flows may each bring a `review`, and one of those is not the other.

    A mount is one directory per name, shared between the sessions holding it. Shared by name
    alone, a flow calling another flow whose skills happen to be named the same would have the
    called flow's session reading the caller's skill -- and, worse, the caller's session
    reading the called one's after it ended and the count fell. Each flow's sessions are
    their own agent's, given that flow's skills.
    """
    monkeypatch.chdir(tmp_path)
    outer = written(
        tmp_path / "flows",
        "outer",
        DOES,
        {"note-taking": skill("note-taking", says="The outer flow's.")},
    )
    inner = written(
        tmp_path / "flows",
        "inner",
        DOES,
        {"note-taking": skill("note-taking", says="The inner flow's.")},
    )

    held = _given(ClaudeAgent(CONFIG), outer).new()
    held(
        "true"
    )  # a turn, so the outer flow's session is open and its skills are mounted
    _given(ClaudeAgent(CONFIG), inner)(
        "cat .claude/skills/note-taking/SKILL.md > read.txt"
    )
    held.close()
    gc.collect()

    # The one that was there first is the one both read: a name is one skill to the CLI, and
    # writing over it would change what the session still holding it is working by.
    assert "The outer flow's" in (tmp_path / "read.txt").read_text()
    assert not (tmp_path / ".claude").exists()  # and both of them are taken away after


def test_a_session_opened_after_one_was_closed_is_given_them_too(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What a closing takes away is the closing session's, not the flow's for the rest of it."""
    monkeypatch.chdir(tmp_path)
    at = written(tmp_path, "again", DOES, {"note-taking": skill("note-taking")})
    agent = _given(ClaudeAgent(CONFIG), at)

    one = agent.new()
    one("true")
    one.close()
    agent.new()("cat .claude/skills/note-taking/SKILL.md > read.txt")
    gc.collect()

    assert "Do the thing" in (tmp_path / "read.txt").read_text()
    assert not (
        tmp_path / ".claude"
    ).exists()  # and the last one to end takes them away


def test_a_stop_ends_the_turns_process_and_takes_the_skills_after_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stop ends the turn under way -- the process included -- and the skills go after it.

    In that order and not the other: taking the skills away as the stop lands would delete a
    directory the agent's own process may still be in the middle of reading, which is not
    stopping it, only breaking it. So the turn lets go of them as it unwinds, which is the
    first moment nothing is working by them.
    """
    import threading

    from hmz.coganchor.agents import Stopped

    monkeypatch.chdir(tmp_path)
    at = written(tmp_path, "slowly", DOES, {"note-taking": skill("note-taking")})
    agent = _given(ClaudeAgent(CONFIG), at)

    began = time.monotonic()
    threading.Timer(0.2, agent.stop).start()
    with contextlib.suppress(Stopped):
        agent("cat .claude/skills/note-taking/SKILL.md > read.txt; sleep 30")
    took = time.monotonic() - began
    gc.collect()

    assert took < 10  # the stop ended the command rather than waiting out its sleep
    assert "Do the thing" in (tmp_path / "read.txt").read_text()
    assert not (
        tmp_path / ".claude"
    ).exists()  # and they go once the turn is done with them


def test_a_directory_the_project_already_had_is_left_where_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even an empty one: what humanize takes away is what humanize made."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    at = written(
        tmp_path / ".humanize/flows",
        "mine",
        DOES,
        {"note-taking": skill("note-taking")},
    )

    _given(ClaudeAgent(CONFIG), at)("true")
    gc.collect()

    assert (tmp_path / ".claude" / "skills").is_dir()
    assert not (tmp_path / ".claude" / "skills" / "note-taking").exists()


def test_a_copy_that_stopped_partway_is_not_left_to_be_taken_for_the_projects_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing would ever remove it: it is not in the table of what humanize planted."""
    import shutil

    from hmz.coganchor.agents.skills import Loaded, mount

    at = written(tmp_path, "mine", DOES, {"note-taking": skill("note-taking")})

    def stops(*_: object, **__: object) -> None:
        raise OSError("the disk filled up")

    monkeypatch.setattr(shutil, "copytree", stops)
    mounted = mount(
        "claude", tmp_path, [Loaded("note-taking", at / "skills/note-taking")]
    )

    assert mounted.at == ()
    assert not (tmp_path / ".claude" / "skills" / "note-taking").exists()


def test_a_backend_that_reads_no_such_directory_carries_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flow that brings skills brings that backend none, rather than failing to start."""
    monkeypatch.chdir(tmp_path)
    written(
        tmp_path / ".humanize/flows",
        "mine",
        DOES,
        {"note-taking": skill("note-taking")},
    )
    # A backend with nowhere a skill of a flow's could go.
    agent = _given(ShellAgent(CONFIG), tmp_path / ".humanize/flows/mine")

    agent("ls -a > listed.txt")

    assert agent.loaded == (
        Loaded(
            name="note-taking",
            at=tmp_path / ".humanize/flows/mine/skills/note-taking",
            whose="this flow",
        ),
    )
    assert ".claude" not in (tmp_path / "listed.txt").read_text().split()


def test_a_flow_is_copied_whole_into_this_projects_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which is what a flow being a directory buys: a copy of one is a flow, skills and all."""
    from hmz.runtime.flowing import find, fork

    monkeypatch.chdir(tmp_path)
    (tmp_path / "theirs").mkdir()
    written(tmp_path / "theirs", "mine", DOES, {"note-taking": skill("note-taking")})

    at = fork(str(tmp_path / "theirs" / "mine"))

    assert (tmp_path / at / "__init__.py").read_text() == DOES
    assert (tmp_path / at / "skills" / "note-taking" / "SKILL.md").is_file()
    # And your own are looked in first, so the name now means the copy.
    assert find("mine") == str(tmp_path / ".humanize/flows/mine/__init__.py")
    # One already copied is one to edit rather than one to write over.
    with pytest.raises(ValueError, match="already a flow of your own"):
        fork(str(tmp_path / "theirs" / "mine"))


def test_a_copy_does_not_take_the_name_of_a_flow_of_yours_that_is_one_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory wins the name a file also uses, so a copy would shadow yours silently."""
    from hmz.runtime.flowing import fork

    monkeypatch.chdir(tmp_path)
    (tmp_path / "theirs").mkdir()
    written(tmp_path / "theirs", "mine", DOES)
    (tmp_path / ".humanize/flows").mkdir(parents=True)
    (tmp_path / ".humanize/flows/mine.py").write_text(DOES)

    with pytest.raises(ValueError, match="already a flow of your own"):
        fork(str(tmp_path / "theirs" / "mine"))

    assert (tmp_path / ".humanize/flows/mine.py").is_file()
    assert not (tmp_path / ".humanize/flows/mine").exists()


def test_a_copy_that_fails_partway_leaves_the_name_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Half a flow under the name is one that will not run and cannot be copied again."""
    import shutil

    from hmz.runtime.flowing import fork

    monkeypatch.chdir(tmp_path)
    (tmp_path / "theirs").mkdir()
    written(tmp_path / "theirs", "mine", DOES, {"note-taking": skill("note-taking")})

    def fails(*_: object, **__: object) -> None:
        raise OSError("the disk filled up")

    monkeypatch.setattr(shutil, "copytree", fails)
    with pytest.raises(OSError, match="disk filled"):
        fork(str(tmp_path / "theirs" / "mine"))

    monkeypatch.undo()
    monkeypatch.chdir(tmp_path)
    assert not (tmp_path / ".humanize/flows/mine").exists()
    assert sorted(one.name for one in (tmp_path / ".humanize/flows").iterdir()) == []
    fork(str(tmp_path / "theirs" / "mine"))  # and the name is free to try again
    assert (tmp_path / ".humanize/flows/mine/__init__.py").is_file()


def test_a_copy_is_yours_to_change_and_is_what_then_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A fetched flowverse is fetched over, so an edit that is to keep is an edit to a copy."""
    from pathlib import Path

    from hmz.runtime.flowing import find, fork

    monkeypatch.chdir(tmp_path)
    (tmp_path / "theirs").mkdir()
    written(tmp_path / "theirs", "mine", DOES, {"note-taking": skill("note-taking")})
    fork(str(tmp_path / "theirs" / "mine"))
    at = tmp_path / ".humanize/flows/mine/skills/note-taking/SKILL.md"
    at.write_text(skill("note-taking", says="Changed, and mine."))

    _given(ClaudeAgent(CONFIG), Path(find("mine")).parent)(
        "cat .claude/skills/note-taking/SKILL.md > read.txt"
    )
    gc.collect()

    assert "Changed, and mine" in (tmp_path / "read.txt").read_text()


@pytest.fixture
def claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stand-in Claude Code on PATH, with a home of its own."""
    standins.install(tmp_path / "bin", "claude", standins.CLAUDE)
    monkeypatch.setenv("PATH", standins.path_with(tmp_path / "bin"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-home"))


def test_a_role_is_given_the_skills_it_names_through_a_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: None
) -> None:
    """What the runtime hands a session: the role's own skills, mounted while it is open."""
    monkeypatch.chdir(tmp_path)
    written(
        tmp_path / ".humanize/flows",
        "reads",
        READS.replace("NAMED", '("note-taking",)'),
        {"note-taking": skill("note-taking"), "other": skill("other")},
    )

    listed, said = Runner(
        "reads",
        agents={"agent": "claude/claude-haiku-4-5:low"},
        budget={"cost": 1},
    ).run("Reply with the single word: hi")

    # The one the role named, and not the flow's other skill.
    assert listed == ["note-taking"]
    assert "does a thing" in said
    assert not (tmp_path / ".claude").exists()  # and gone once the run is over


def test_a_role_naming_a_skill_the_flow_has_not_got_stops_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, claude: None
) -> None:
    monkeypatch.chdir(tmp_path)
    written(
        tmp_path / ".humanize/flows",
        "reads",
        READS.replace("NAMED", '("nowhere",)'),
        {"note-taking": skill("note-taking")},
    )
    run = Runner(
        "reads", agents={"agent": "claude/claude-haiku-4-5:low"}, budget={"cost": 1}
    )

    with pytest.raises(Refused, match="nowhere"):
        run.run("Reply with the single word: hi")
