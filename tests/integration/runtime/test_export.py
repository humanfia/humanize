"""One whole run, packaged up to send to somebody who was not there.

A run points at its sessions rather than holding them, which is right on the machine that ran
it and worth nothing anywhere else: a directory of symlinks into somebody's home is an archive
with nothing in it. So a bundle is the run with every link followed -- and with every
credential taken out, since the one thing a person sending their own run must not also send is
the key it ran on.

`hmz.runtime.exporting` itself, and no command line: there is none any more. What asks for a
bundle now is `/epics` in the interface, on the run under its cursor, and this is the layer
under that -- held to what a bundle holds and what it must never carry rather than to how
anything asked for one.

Every run here is driven by a stand-in CLI -- `claude`, which keeps its conversations where
Claude Code does, and `opencode`, which keeps them to itself -- so the whole file is a real
process, a temporary home and a tarball: nothing CI has not got. The one check that needs
more -- that a run taken as a named account carries none of that account's key, which means a
supervised turn and so a kernel that will hand over a tracee -- is in
`tests/system/runtime/test_export.py`.
"""

from __future__ import annotations

import json
import tarfile
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import providers
from hmz.runtime.epic import epics, sessions
from hmz.runtime.exporting import (
    MANIFEST,
    REDACTED,
    TRANSCRIPT,
    bundle,
    logged,
    plain,
    sized,
)
from hmz.runtime.runner import Runner
from tests.flows import standins
from tests.recording import AGENT, ONE, TASK, held, manifest, standing_in
from tests.recording import logged as kept
from tests.stubs import written

if TYPE_CHECKING:
    from pathlib import Path

#: A flow that opens one session per agent.
FLOW = """
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    actor: Agent
    reviewer: Agent


class Envs(EnvCollection):
    here: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def flow_(task, *, agents, envs, params, ctx):
    for role in ("actor", "reviewer"):
        session = await agents[role].spawn(env=envs["here"])
        await agents[role].run(task, session=session)
"""

#: A flow that calls another, so that a bundle has a record beside the run's own to carry;
#: and calls it twice, so that two calls of one flow are two records and the manifest has to
#: say which of them a session belongs to.
CALLS = """
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow, load


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    here: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams)
async def flow_(task, *, agents, envs, params, ctx):
    for said in TASKS:
        await load("under")(said, agents=agents, envs=envs, params=FlowParams())
"""

#: The one it calls, which opens a session of its own -- one run, more than one record.
UNDER = ONE.replace("async def one(", "async def under(")

#: A flow that keeps something, so that its journal is there to be carried.
KEEPS = """
from hmz.flows import Agent, AgentCollection, EnvCollection, FlowParams, LocalEnv, flow


class Agents(AgentCollection):
    builder: Agent


class Envs(EnvCollection):
    here: LocalEnv


@flow(agents=Agents, envs=Envs, params=FlowParams, resumable=True)
async def flow_(task, *, agents, envs, params, ctx):
    ctx.state["rounds"] = 3
    session = await agents["builder"].spawn(env=envs["here"])
    return await agents["builder"].run(task, session=session)
"""


def _ran(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: str = ONE,
    task: str = TASK,
    **agents: str,
) -> Path:
    """Runs one flow, written into the test's own directory, on the stand-ins; its epic."""
    standing_in(tmp_path, monkeypatch)
    standins.install(tmp_path / "bin", "opencode", standins.OPENCODE)
    monkeypatch.chdir(tmp_path)
    written(tmp_path, "flow", source)
    Runner(
        tmp_path / "flow", agents=agents or {"builder": AGENT}, budget={"cost": 5}
    ).run(task)
    (epic,) = epics()
    return epic


def _log(tmp_path: Path, epic: Path) -> Path:
    """Where the stand-in kept the one conversation of a run."""
    (one,) = sessions(epic)
    return kept(tmp_path / "claude-home", tmp_path.resolve(), one.ident)


def test_a_bundle_holds_every_record_the_run_wrote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flow that called another is two records, and one run is both of them."""
    written(tmp_path / ".humanize" / "flows", "under", UNDER)
    epic = _ran(tmp_path, monkeypatch, CALLS.replace("TASKS", f"[{TASK!r}]"))

    inside = held(bundle(epic, tmp_path / "out.tar.gz")[0])
    assert "epic.jsonl" in inside
    assert [one for one in inside if one.startswith("epic.under-under_")], inside
    # And the manifest lists what went in, the run's own record first.
    said = json.loads(inside[MANIFEST])
    assert said["held"][0] == "epic.jsonl"
    assert said["held"][-1] == MANIFEST
    # And the run's own record reads back as the run: every line it wrote, not a summary.
    assert '"event": "began"' in inside["epic.jsonl"]


def test_the_manifest_says_the_call_tree_and_whose_each_session_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A flow called twice is two records and two conversations, and the flow name says one."""
    written(tmp_path / ".humanize" / "flows", "under", UNDER)
    epic = _ran(
        tmp_path,
        monkeypatch,
        CALLS.replace(
            "TASKS",
            '["Reply with the single word: once", "Reply with the single word: again"]',
        ),
    )

    said = manifest(bundle(epic, tmp_path / "out.tar.gz")[0])
    # Two calls of one flow, each in a record of its own, each saying which called it.
    assert [one["flow"] for one in said["called"]] == ["under:under", "under:under"]
    assert {one["under"] for one in said["called"]} == {"epic.jsonl"}
    assert len({one["record"] for one in said["called"]}) == 2
    # And each session says which of the two it was opened in, not only which flow.
    assert {one["record"] for one in said["sessions"]} == {
        one["record"] for one in said["called"]
    }
    # And how each call ended, off its own record: a call that raised inside a run which
    # carried on is a call that failed and a run that did not.
    assert {one["how"] for one in said["called"]} == {"done"}


def test_a_session_log_comes_as_its_contents_and_not_as_a_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole point: a link into somebody's home is worth nothing on another machine."""
    epic = _ran(tmp_path, monkeypatch, task="Reply with the single word: hello")
    (one,) = sessions(epic)
    name = f"{one.ident}.jsonl"

    at = bundle(epic, tmp_path / "out.tar.gz")[0]
    with tarfile.open(at) as opened:
        member = opened.getmember(f"{epic.name}/sessions/{one.name}/{name}")
        assert not member.issym()
        assert not member.islnk()
        assert member.isfile()
    assert "single word: hello" in held(at)[f"sessions/{one.name}/{name}"]


def test_a_backend_that_logs_nothing_says_so_rather_than_carrying_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CLI that keeps its sessions in a database logs none, and an absence reads as loss."""
    epic = _ran(tmp_path, monkeypatch, builder="opencode/opencode/big-pickle:high")

    said = manifest(bundle(epic, tmp_path / "out.tar.gz")[0])
    (one,) = said["sessions"]
    assert one["backend"] == "opencode"
    assert one["logs"] == []
    assert "keeps its sessions to itself" in one["because"]
    assert said["backends"]["opencode"]["logs"] is False


def test_what_the_run_says_it_ran_is_not_struck_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An account may say which model to ask for, and Kimi Code's fixture one does.

    A bundle with the model taken out of it because some other account had that name in a
    variable is a bundle saying nothing about what actually ran.
    """
    providers.add("kimi", "elsewhere", "env", {"KIMI_MODEL_NAME": "fixture-model"})
    epic = _ran(tmp_path, monkeypatch, builder="claude/fixture-model:high")

    said = manifest(bundle(epic, tmp_path / "out.tar.gz")[0])
    assert said["agents"][0]["model"] == "fixture-model"
    assert said["agents"][0]["runs"] == "claude/fixture-model:high"


def test_the_manifest_is_scrubbed_like_everything_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It holds the task, which is a line somebody typed and may hold anything."""
    providers.add("claude", "work", "key", {"ANTHROPIC_AUTH_TOKEN": "hunter2-hunter2"})
    epic = _ran(
        tmp_path,
        monkeypatch,
        task="push to https://bob:ghp_abcdefghijklmnopqrst@example.com with "
        "hunter2-hunter2",
    )

    at, handed = bundle(epic, tmp_path / "out.tar.gz")
    said = held(at)[MANIFEST]
    assert "hunter2" not in said
    assert "ghp_abcdefghijklmnopqrst" not in said
    assert "bob" not in said
    # And what comes back is what was written, not what was about to be.
    assert "hunter2" not in json.dumps(handed)
    # Nor anywhere else in it: the session's own log said the task too.
    assert not any("hunter2" in one for one in held(at).values())


def test_where_a_bundle_lands_beside_two_of_them_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two exports of one run must not be two gzip streams into one file."""
    epic = _ran(tmp_path, monkeypatch)

    at = bundle(epic)[0]
    assert bundle(epic)[0] == at
    assert MANIFEST in held(at)
    # And nothing half-written is left beside it.
    assert [one.name for one in at.parent.iterdir()] == [at.name]


def test_a_directory_to_fill_that_is_not_there_yet_is_still_a_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`-o out/` is somewhere to put it rather than a file called `out`.

    Answering it with the file would have the next run write over the last.
    """
    epic = _ran(tmp_path, monkeypatch)

    at = bundle(epic, f"{tmp_path / 'bundles'}/")[0]

    assert at.parent == tmp_path / "bundles"
    assert at.name == f"{epic.name}.epic.tar.gz"


def test_the_manifest_says_which_run_on_what_and_by_whom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Everything a reader needs to know what they are looking at, and nothing secret."""
    epic = _ran(
        tmp_path,
        monkeypatch,
        FLOW,
        task="Reply with the single word: fixed",
        actor=AGENT,
        reviewer=AGENT,
    )

    said = manifest(bundle(epic, tmp_path / "out.tar.gz")[0])
    assert said["epic"] == epic.name
    assert said["run"]["task"] == "Reply with the single word: fixed"
    assert said["run"]["how"] == "done"
    assert said["workspace"]["at"] == str(tmp_path.resolve())
    assert [one["agent"] for one in said["agents"]] == ["actor", "reviewer"]
    assert said["agents"][0]["runs"] == "claude/claude-haiku-4-5:low"
    assert "claude" in said["backends"]
    assert MANIFEST in said["held"]
    assert said["humanize"]
    assert said["redacted"]


def test_what_a_resumable_flow_kept_is_in_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run picked up again is picked up from its journal, so a report of one needs it."""
    epic = _ran(tmp_path, monkeypatch, KEEPS)

    inside = held(bundle(epic, tmp_path / "out.tar.gz")[0])
    kept_: list[dict[str, Any]] = [
        json.loads(line) for line in inside["resume.jsonl"].splitlines()
    ]
    assert {"t": "set", "id": 1, "key": "rounds", "value": 3} in kept_


def test_a_trace_gathered_of_the_run_goes_with_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A trace belongs with the run, and so belongs in the bundle of that run."""
    epic = _ran(tmp_path, monkeypatch)
    (epic / "traces").mkdir()
    (epic / "traces" / "a.trace.json").write_text('{"traceEvents": []}', "utf-8")

    inside = held(bundle(epic, tmp_path / "out.tar.gz")[0])
    assert inside["traces/a.trace.json"] == '{"traceEvents": []}'


def test_the_transcript_goes_in_as_it_was_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the interface hands over is the text, not the rows. There is none from a line."""
    epic = _ran(tmp_path, monkeypatch)

    with_screen = held(
        bundle(epic, tmp_path / "a.tar.gz", transcript="a long line\n")[0]
    )
    assert with_screen[TRANSCRIPT] == "a long line\n"
    assert TRANSCRIPT not in held(bundle(epic, tmp_path / "b.tar.gz")[0])


def test_a_bundle_is_readable_by_whoever_made_it_and_nobody_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What is in it is their prompts and their agents' output."""
    epic = _ran(tmp_path, monkeypatch)

    assert bundle(epic)[0].stat().st_mode & 0o777 == 0o600


def test_a_bundle_carries_nothing_about_whoever_made_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A tar records its writer by default, and a login name is not a thing to hand over."""
    epic = _ran(tmp_path, monkeypatch)

    with tarfile.open(bundle(epic, tmp_path / "out.tar.gz")[0]) as opened:
        assert {one.uname for one in opened.getmembers()} == {""}
        assert {one.uid for one in opened.getmembers()} == {0}


def test_where_a_bundle_lands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A file outright, a directory to fill, or `.humanize/` here -- it is a thing to send."""
    epic = _ran(tmp_path, monkeypatch)

    # Where somebody is standing rather than in humanize's own home the way a trace of a
    # run goes, and named whole: it is a thing to attach to something.
    assert bundle(epic)[0] == tmp_path / ".humanize" / f"{epic.name}.epic.tar.gz"
    assert bundle(epic)[0].is_file()
    (tmp_path / "somewhere").mkdir()
    assert bundle(epic, tmp_path / "somewhere")[0].parent == tmp_path / "somewhere"
    assert bundle(epic, tmp_path / "named.tgz")[0].name == "named.tgz"


def test_a_directory_holding_no_run_is_nothing_to_export(tmp_path: Path) -> None:
    """Which is a thing to correct rather than an archive of nothing."""
    with pytest.raises(ValueError, match="is not a run"):
        bundle(tmp_path, tmp_path / "out.tar.gz")


def test_a_link_whose_log_has_gone_is_left_out_rather_than_carried_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A log rolls over, a home is thrown away: a name with nothing behind it is not a log."""
    epic = _ran(tmp_path, monkeypatch)
    _log(tmp_path, epic).unlink()

    said = manifest(bundle(epic, tmp_path / "out.tar.gz")[0])
    assert said["sessions"][0]["logs"] == []
    assert "has since gone" in said["sessions"][0]["because"]


def test_what_each_session_was_logged_to_is_read_through_the_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The files themselves, since what a bundle carries is what is behind each link."""
    epic = _ran(tmp_path, monkeypatch)
    (one,) = sessions(epic)
    log = _log(tmp_path, epic)

    assert logged(epic) == {one.name: {log.name: log.resolve()}}


@pytest.mark.parametrize(
    ("said", "wanted"),
    [
        (
            "https://x-access-token:ghs_abcdefgh@github.com/o/f",
            f"https://{REDACTED}@github.com/o/f",
        ),
        ("key sk-ant-api03-abcdefghijklmnop here", f"key {REDACTED} here"),
        ("ghp_abcdefghijklmnopqrst", REDACTED),
        ("AIzaSyAbcdefghijklmnopqrstuvwxyz01", REDACTED),
        (
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NX0.dBjftJeZ4CVPmB92K27uhbUJU1p1r",
            REDACTED,
        ),
        (
            "Authorization: Bearer abcdefghijklmnopqrst",
            f"Authorization: Bearer {REDACTED}",
        ),
        ('{"api_key": "abcdefgh"}', f'{{"api_key": "{REDACTED}"}}'),
        ("ANTHROPIC_AUTH_TOKEN=abcdefgh", f"ANTHROPIC_AUTH_TOKEN={REDACTED}"),
        (
            "https://s3/x?X-Amz-Signature=deadbeef",
            f"https://s3/x?X-Amz-Signature={REDACTED}",
        ),
    ],
)
def test_what_is_struck_out_of_everything_a_bundle_carries(
    said: str, wanted: str
) -> None:
    assert plain(said) == wanted


@pytest.mark.parametrize(
    "said",
    [
        '{"input_tokens": 4211, "output_tokens": 12}',
        "/v1/messages?max_tokens=4096&model=x",
        "/search?monkey=hello",
        "https://github.com/humanfia/humanize",
        "ask-the-reviewer-about-it",
        "the password is wrong",
    ],
)
def test_what_is_left_alone(said: str) -> None:
    """A bundle nobody can read is a bundle nobody develops against."""
    assert plain(said) == said


def test_a_value_is_struck_wherever_it_appears() -> None:
    """A gateway's key is whatever somebody pasted, and no pattern would know it."""
    assert (
        plain("ran with wobbly-elephant", ["wobbly-elephant"]) == f"ran with {REDACTED}"
    )


@pytest.mark.parametrize(
    ("count", "said"),
    [
        (0, "0 B"),
        (999, "999 B"),
        (1000, "1.0 kB"),
        (91234, "91 kB"),
        (5_400_000, "5.4 MB"),
    ],
)
def test_how_big_it_came_out(count: int, said: str) -> None:
    assert sized(count) == said
