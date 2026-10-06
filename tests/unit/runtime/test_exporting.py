"""One run packaged up whole, with every credential struck out of it."""

from __future__ import annotations

import json
import platform
import stat
import subprocess
import tarfile
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor import backends, providers
from hmz.runtime import exporting
from hmz.runtime.epic import RESUME, SESSIONS, TRACES, Drove, Epic
from hmz.runtime.exporting import MANIFEST, REDACTED, TRANSCRIPT, bundle, plain, sized

if TYPE_CHECKING:
    from pathlib import Path


# ------------------------------------------------------------------ plain


@pytest.mark.parametrize(
    ("said", "plainly"),
    [
        ("https://me:pw@host/x", f"https://{REDACTED}@host/x"),
        ("see //nobody here", "see //nobody here"),
        ("https://h/x?sig=abc&b=2", f"https://h/x?sig={REDACTED}&b=2"),
        ("https://h/x?token=abc", f"https://h/x?token={REDACTED}"),
        ("https://h/x?X-Amz-Signature=abc", f"https://h/x?X-Amz-Signature={REDACTED}"),
        ("?max_tokens=5&monkey=3", "?max_tokens=5&monkey=3"),
        ("key sk-ant-abcdefghijklmnop end", f"key {REDACTED} end"),
        ("ghp_abcdefghijklmnopqr", REDACTED),
        ("AIzaabcdefghijklmnopqr", REDACTED),
        ("eyJhbGciOiJI.eyJzdWIiOiIx.abcdefghij", REDACTED),
        (
            "Authorization: Bearer abcdefghijklmnopqrstu",
            f"Authorization: Bearer {REDACTED}",
        ),
        ('{"api_key": "abcdef"}', f'{{"api_key": "{REDACTED}"}}'),
        ("MY_TOKEN=abcdef rest", f"MY_TOKEN={REDACTED} rest"),
        ('{"input_tokens": 1234}', '{"input_tokens": 1234}'),
        ("input_tokens=1234", "input_tokens=1234"),
        ("sk-short", "sk-short"),
        ("nothing to see", "nothing to see"),
    ],
)
def test_credentials_are_struck_out_by_shape(said: str, plainly: str) -> None:
    assert plain(said) == plainly


def test_values_handed_in_are_struck_out_literally_longest_first() -> None:
    assert plain(
        "gateway.example and gateway.example/v1",
        ["gateway.example/v1", "gateway.example"],
    ) == (f"{REDACTED} and {REDACTED}")


@pytest.mark.parametrize(
    ("count", "said"),
    [
        (0, "0 B"),
        (999, "999 B"),
        (1000, "1.0 kB"),
        (1400, "1.4 kB"),
        (912_000, "912 kB"),
        (1_400_000, "1.4 MB"),
        (12_000_000, "12 MB"),
        (5 * 10**12, "5.0 TB"),
        (5 * 10**15, "5000 TB"),
    ],
)
def test_a_size_is_three_digits_and_a_unit(count: int, said: str) -> None:
    assert sized(count) == said


def test_what_is_struck_is_said_in_words() -> None:
    assert all(isinstance(one, str) and one for one in exporting.STRUCK)
    assert exporting.BUNDLE.format(epic="x") == "x.epic.tar.gz"


# ------------------------------------------------------------------ a bundle


@dataclass
class Profile:
    name: str
    logs: tuple[str, ...] = ()

    def logged(self, ident: str) -> tuple[str, ...]:
        return tuple(one.format(ident=ident) for one in self.logs)


@dataclass
class Account:
    env: dict[str, str] = field(default_factory=dict[str, str])


@dataclass
class World:
    """What a bundle asks of other packages and of the machine, answered here."""

    accounts: list[Account] = field(default_factory=list[Account])
    programs: dict[str, str] = field(default_factory=dict[str, str])
    ran: list[list[str]] = field(default_factory=list[list[str]])
    head: str = "abc123"
    version: str = "claude 1.2.3\nmore"


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    made = World()
    profiles = {
        "claude": Profile("claude", ("projects/*/{ident}.jsonl",)),
        "opencode": Profile("opencode"),
    }
    monkeypatch.setattr(backends, "named", profiles.get)
    monkeypatch.setattr(backends, "program", made.programs.get)
    monkeypatch.setattr(providers, "providers", lambda cli="": made.accounts)

    def run(argv: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        made.ran.append(argv)
        if argv[0] == "git":
            return subprocess.CompletedProcess(
                argv, 0 if made.head else 128, made.head + "\n", ""
            )
        return subprocess.CompletedProcess(argv, 0, made.version, "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(platform, "platform", lambda: "TestOS-1.0")
    return made


@pytest.fixture
def ran(tmp_path: Path) -> Path:
    workspace = tmp_path / "project"
    workspace.mkdir()
    with Epic(
        "ralph",
        "fix it with sk-ant-abcdefghijklmnopq",
        workspace,
        agents=[Drove("builder", "claude", "fixture/fixture-model", "high", "work")],
        envs=["box=local/x"],
        resumable=True,
    ) as one:
        one.session("builder", "claude", "work", "s1")
        one.session("other", "opencode", "", "s2")
        one.session("ghost", "nobody", "", "s3")
        inner = one.called("inner", "a part")
        inner.ended()
        (one.resume).write_text('{"t": "call"}\n')
        logs = one.keeps / "claude" / "projects" / "p"
        logs.mkdir(parents=True)
        (logs / "s1.jsonl").write_text(
            '{"secret": "SECRETVALUE-123", "input_tokens": 9}\n'
        )
        (one.path / TRACES).mkdir()
        (one.path / TRACES / "t.trace.json").write_text("{}")
    return one.path


def _members(at: Path) -> dict[str, bytes]:
    with tarfile.open(at) as reading:
        held: dict[str, bytes] = {}
        for one in reading.getmembers():
            assert one.uname == ""
            assert one.uid == 0
            extracted = reading.extractfile(one)
            assert extracted is not None
            held[one.name] = extracted.read()
        return held


def test_a_whole_run_goes_in_one_archive(
    world: World, ran: Path, tmp_path: Path
) -> None:
    world.accounts = [
        Account({"KEY": "SECRETVALUE-123", "SHORT": "1", "MODEL": "fixture-model"})
    ]
    world.programs["claude"] = str(tmp_path / "claude-bin")
    (tmp_path / "claude-bin").write_bytes(b"#!binary")

    landed, manifest = bundle(ran, tmp_path / "out.tar.gz")

    assert landed == tmp_path / "out.tar.gz"
    assert stat.S_IMODE(landed.stat().st_mode) == 0o600
    members = _members(landed)
    name = ran.name
    inner = next(one for one in members if one.startswith(f"{name}/epic.inner_"))
    assert set(members) == {
        f"{name}/epic.jsonl",
        inner,
        f"{name}/{RESUME}",
        f"{name}/{TRACES}/t.trace.json",
        f"{name}/{SESSIONS}/builder-claude@work-s1/projects/p/s1.jsonl",
        f"{name}/{MANIFEST}",
    }
    log = members[
        f"{name}/{SESSIONS}/builder-claude@work-s1/projects/p/s1.jsonl"
    ].decode()
    assert "SECRETVALUE-123" not in log
    assert '"input_tokens": 9' in log
    assert "sk-ant-" not in members[f"{name}/epic.jsonl"].decode()
    assert json.loads(members[f"{name}/{MANIFEST}"]) == manifest

    assert manifest["epic"] == name
    assert manifest["run"]["flow"] == "ralph"
    assert manifest["run"]["how"] == "done"
    assert manifest["run"]["task"] == f"fix it with {REDACTED}"
    assert manifest["workspace"]["head"] == "abc123"
    # What the run says it ran is never struck, though an account holds it.
    assert manifest["agents"][0]["model"] == "fixture/fixture-model"
    assert manifest["agents"][0]["runs"] == "claude@work/fixture/fixture-model:high"
    assert manifest["envs"] == ["box=local/x"]
    assert [one["flow"] for one in manifest["called"]] == ["inner"]
    assert manifest["called"][0]["how"] == "done"
    sessions = {one["session"]: one for one in manifest["sessions"]}
    assert sessions["s1"]["logs"] == ["projects/p/s1.jsonl"]
    assert "because" not in sessions["s1"]
    assert "keeps its sessions to itself" in sessions["s2"]["because"]
    assert "knows no backend called 'nobody'" in sessions["s3"]["because"]
    claude = manifest["backends"]["claude"]
    assert claude["version"] == "claude 1.2.3"
    assert len(claude["sha256"]) == 64
    assert claude["logs"] is True
    assert manifest["backends"]["opencode"]["executable"] == ""
    assert manifest["backends"]["nobody"] == {
        "command": "nobody",
        "executable": "",
        "version": "",
        "sha256": "",
    }
    assert manifest["held"][-1] == MANIFEST
    assert manifest["redacted"] == list(exporting.STRUCK)


def test_a_transcript_handed_in_goes_in_scrubbed(
    world: World, ran: Path, tmp_path: Path
) -> None:
    landed, manifest = bundle(ran, tmp_path, transcript="said ghp_abcdefghijklmnopqr")

    assert landed == tmp_path / f"{ran.name}.epic.tar.gz"
    members = _members(landed)
    assert members[f"{ran.name}/{TRANSCRIPT}"].decode() == f"said {REDACTED}"
    assert TRANSCRIPT in manifest["held"]


def test_a_directory_not_made_yet_is_one_to_write_into(
    world: World, ran: Path, tmp_path: Path
) -> None:
    landed, _ = bundle(ran, f"{tmp_path}/out/")

    assert landed == tmp_path / "out" / f"{ran.name}.epic.tar.gz"
    assert landed.is_file()


def test_exporting_twice_replaces_the_first(
    world: World, ran: Path, tmp_path: Path
) -> None:
    first, _ = bundle(ran, tmp_path)
    second, _ = bundle(ran, tmp_path)

    assert first == second
    assert [one.name for one in tmp_path.iterdir() if one.name.endswith(".new")] == []


def test_a_workspace_that_is_no_repository_has_no_head(
    world: World, ran: Path, tmp_path: Path
) -> None:
    world.head = ""

    _, manifest = bundle(ran, tmp_path)

    assert manifest["workspace"]["head"] == ""


def test_a_directory_holding_no_run_is_nothing_to_export(
    world: World, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="is not a run"):
        bundle(tmp_path, tmp_path / "out.tar.gz")


def test_a_home_nobody_has_is_nowhere_to_write(world: World, ran: Path) -> None:
    with pytest.raises(ValueError, match="no home directory"):
        bundle(ran, "~u12-nobody-at-all/out.tar.gz")


def test_what_each_session_was_logged_to_is_found(world: World, ran: Path) -> None:
    found = exporting.logged(ran)

    assert found == {
        "builder-claude@work-s1": {
            "projects/p/s1.jsonl": ran
            / SESSIONS
            / "claude"
            / "projects"
            / "p"
            / "s1.jsonl"
        }
    }
