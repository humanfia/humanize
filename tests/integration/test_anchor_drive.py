"""A native turn: the CLI already on the target, driven there through `hmz internal anchor`.

Nothing is traced, so this runs on any machine. Each turn is spawned as the line
`AnchorConfig.command` renders, exactly as a backend spawns one, and runs on a `local:`
target or on a container reached through the fake `docker` -- both this machine, while the
workspace the CLI is given is the target's own copy.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from hmz.coganchor import AnchorConfig
from tests.integration.doubles_anchor import Fakes, fakes

#: Long enough for a pipe, a handshake and a shell; short enough that a hang fails.
PATIENCE = 60

#: The workspace as the agent names it, which exists on neither side.
WORKSPACE = "/coganchor-native"


@dataclass(frozen=True)
class Driven:
    """A target directory, and a way to take one turn on it."""

    target: Path
    settings: AnchorConfig

    def run(
        self, *argv: str, stdin: bytes = b"", **settings: object
    ) -> subprocess.CompletedProcess[str]:
        """Runs `argv` as a native turn on the target and waits for it."""
        line = replace(self.settings, **settings).command(argv)
        done = subprocess.run(
            line, input=stdin, capture_output=True, timeout=PATIENCE, check=False
        )
        return subprocess.CompletedProcess(
            done.args,
            done.returncode,
            done.stdout.decode(errors="replace"),
            done.stderr.decode(errors="replace"),
        )


@pytest.fixture
def driven(tmp_path: Path) -> Driven:
    """A `local:` target holding the project, which the workspace path names on neither side."""
    target = tmp_path / "target"
    target.mkdir()
    return Driven(
        target,
        AnchorConfig(target=f"local:{target}", workspace=WORKSPACE, native=True),
    )


def _creds(tmp_path: Path, said: str = "a token\n") -> Path:
    held = tmp_path / "creds"
    held.mkdir()
    (held / "auth.json").write_text(said)
    (held / "auth.json").chmod(0o600)
    return held


def test_a_turn_runs_in_the_targets_copy_of_the_workspace(driven: Driven) -> None:
    (driven.target / "note.txt").write_text("the target's own\n")

    said = driven.run("/bin/sh", "-c", "pwd; cat note.txt")

    assert said.returncode == 0, said.stderr
    assert said.stdout.splitlines() == [str(driven.target), "the target's own"]


def test_a_turn_answers_with_its_own_status_and_both_its_streams(
    driven: Driven,
) -> None:
    said = driven.run("/bin/sh", "-c", "echo out; echo err >&2; exit 7")

    assert said.returncode == 7
    assert said.stdout == "out\n"
    assert "err" in said.stderr


def test_what_a_turn_is_given_on_stdin_reaches_it(driven: Driven) -> None:
    said = driven.run("/bin/cat", stdin=b"one\ntwo\n")

    assert said.returncode == 0
    assert said.stdout == "one\ntwo\n"


def test_a_turn_starts_in_the_directory_it_was_opened_at(driven: Driven) -> None:
    (driven.target / "sub").mkdir()

    said = driven.run("/bin/sh", "-c", "pwd", chdir=f"{WORKSPACE}/sub")

    assert said.returncode == 0, said.stderr
    assert said.stdout.strip() == str(driven.target / "sub")


def test_a_cli_the_target_lacks_exits_127_with_the_line_that_installs_it(
    driven: Driven,
) -> None:
    said = driven.run("nonesuch-cli", "--print", installs="npm i -g nonesuch")

    assert said.returncode == 127
    assert "nonesuch-cli is not installed" in said.stderr
    assert "npm i -g nonesuch" in said.stderr


def test_a_turn_is_told_where_it_landed(driven: Driven) -> None:
    said = driven.run(
        "/bin/sh", "-c", 'printf "%s %s\\n" "$HUMANIZE_TARGET" "$HUMANIZE_WORKSPACE"'
    )

    assert said.stdout == f"local:{driven.target} {driven.target}\n"


def test_a_hushed_variable_is_unset_on_the_target(
    driven: Driven, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "somebody-elses")

    said = driven.run(
        "/bin/sh",
        "-c",
        'printf "[%s]\\n" "${ANTHROPIC_API_KEY-unset}"',
        hushes=("ANTHROPIC_API_KEY",),
    )

    assert said.stdout == "[unset]\n"


def test_a_projected_credential_is_private_to_the_turn_and_gone_after_it(
    driven: Driven, tmp_path: Path
) -> None:
    creds = _creds(tmp_path)

    said = driven.run(
        "/bin/sh",
        "-c",
        'echo "$CLAUDE_CONFIG_DIR"; cat "$CLAUDE_CONFIG_DIR/auth.json"; '
        'ls -ld "$CLAUDE_CONFIG_DIR"; exit 3',
        projects=(("CLAUDE_CONFIG_DIR", str(creds)),),
    )

    assert said.returncode == 3
    landed, token, listing = said.stdout.splitlines()
    assert token == "a token"
    assert Path(landed) != creds
    assert listing.startswith("drwx------")
    # Taken away even though the turn failed.
    assert not Path(landed).exists()


def test_a_credential_crosses_by_path_and_never_by_value(tmp_path: Path) -> None:
    creds = _creds(tmp_path, "sk-the-actual-secret\n")

    line = AnchorConfig(
        native=True, projects=(("CLAUDE_CONFIG_DIR", str(creds)),)
    ).command(["claude"])

    assert any(str(creds) in word for word in line)
    assert not any("sk-the-actual-secret" in word for word in line)


#: A sign-in as Codex keeps one, before and after the CLI refreshed it.
SIGNED_IN = '{"tokens": {"access_token": "a1", "refresh_token": "r1"}}\n'
REFRESHED = '{"tokens": {"access_token": "a2", "refresh_token": "r2"}}\n'
REFRESHING = (
    'printf %s "$1" > "$CODEX_HOME/auth.json.tmp" && '
    'mv "$CODEX_HOME/auth.json.tmp" "$CODEX_HOME/auth.json"'
)


def test_a_sign_in_refreshed_on_the_target_is_written_back(
    driven: Driven, tmp_path: Path
) -> None:
    creds = _creds(tmp_path, SIGNED_IN)

    said = driven.run(
        "/bin/sh",
        "-c",
        REFRESHING,
        "refreshing",
        REFRESHED,
        projects=(("CODEX_HOME", str(creds)),),
    )

    assert said.returncode == 0, said.stderr
    assert (creds / "auth.json").read_text() == REFRESHED
    assert (creds / "auth.json").stat().st_mode & 0o777 == 0o600
    assert sorted(one.name for one in creds.iterdir()) == ["auth.json"]


def test_a_projected_file_that_is_no_sign_in_is_not_written_back(
    driven: Driven, tmp_path: Path
) -> None:
    creds = _creds(tmp_path, '{"OPENAI_API_KEY": "sk-a"}\n')

    said = driven.run(
        "/bin/sh",
        "-c",
        REFRESHING,
        "refreshing",
        '{"OPENAI_API_KEY": "sk-b"}\n',
        projects=(("CODEX_HOME", str(creds)),),
    )

    assert said.returncode == 0, said.stderr
    assert (creds / "auth.json").read_text() == '{"OPENAI_API_KEY": "sk-a"}\n'


def _skill(tmp_path: Path, said: str = "---\nname: review\n---\n") -> Path:
    held = tmp_path / "review"
    held.mkdir()
    (held / "SKILL.md").write_text(said)
    return held


def test_a_carried_skill_is_there_for_the_turn_and_gone_after_it(
    driven: Driven, tmp_path: Path
) -> None:
    skill = _skill(tmp_path)

    said = driven.run(
        "/bin/sh",
        "-c",
        "cat .claude/skills/review/SKILL.md",
        carries=((str(skill), ".claude/skills/review"),),
    )

    assert said.returncode == 0, said.stderr
    assert "name: review" in said.stdout
    assert not (driven.target / ".claude").exists()


def test_a_carried_skill_never_replaces_the_projects_own(
    driven: Driven, tmp_path: Path
) -> None:
    theirs = driven.target / ".claude" / "skills" / "review"
    theirs.mkdir(parents=True)
    (theirs / "SKILL.md").write_text("the project's own\n")
    skill = _skill(tmp_path, "the flow's\n")

    said = driven.run(
        "/bin/sh",
        "-c",
        "cat .claude/skills/review/SKILL.md",
        carries=((str(skill), ".claude/skills/review"),),
    )

    assert said.stdout == "the project's own\n"
    assert (theirs / "SKILL.md").read_text() == "the project's own\n"


@pytest.fixture
def far(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fakes:
    """Fake `docker` and `ssh` on `PATH`."""
    return fakes(tmp_path, monkeypatch)


@pytest.mark.parametrize(
    "spelled", ["docker://{name}", "apple-container://{name}", "ssh://{name}"]
)
def test_a_turn_on_a_remote_target_is_driven_through_its_road(
    far: Fakes, tmp_path: Path, spelled: str
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "note.txt").write_text("over there\n")
    target = spelled.format(name=f"box-{tmp_path.name}")
    settings = AnchorConfig(target=target, workspace=str(project), native=True)

    said = Driven(project, settings).run("/bin/sh", "-c", "pwd; cat note.txt")

    assert said.returncode == 0, said.stderr
    assert said.stdout.splitlines() == [str(project), "over there"]
    tool = {"docker": "docker", "apple-container": "container", "ssh": "ssh"}[
        target.partition(":")[0]
    ]
    assert far.calls(tool)


def test_a_native_turn_is_rendered_as_the_anchor_line() -> None:
    line = AnchorConfig(target="docker://box", native=True, workspace="/w").command(
        ["claude", "--print"], chdir="/w/sub"
    )

    assert line[1:5] == ["-Pm", "hmz", "internal", "anchor"]
    assert "--native" in line
    assert "--chdir=/w/sub" in line
    assert line[-2:] == ["claude", "--print"]


def test_a_turn_told_not_to_share_ssh_connections_opens_its_own(
    far: Fakes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUMANIZE_SSH_REUSE", "off")
    project = tmp_path / "project"
    project.mkdir()
    settings = AnchorConfig(
        target=f"ssh://box-{tmp_path.name}", workspace=str(project), native=True
    )

    said = Driven(project, settings).run("/bin/sh", "-c", "true")

    assert said.returncode == 0, said.stderr
    assert far.calls("ssh")
    assert not any("ControlMaster=auto" in argv for argv in far.calls("ssh"))
