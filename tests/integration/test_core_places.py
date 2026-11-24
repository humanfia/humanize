"""Where Humanize keeps its files: the user's base directories, and what a release left behind."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import hmz

#: Each of Humanize's directories, by the variable naming its base and the base otherwise.
BASES = {
    "XDG_CONFIG_HOME": (hmz.config, ".config"),
    "XDG_DATA_HOME": (hmz.data, ".local/share"),
    "XDG_STATE_HOME": (hmz.state, ".local/state"),
    "XDG_CACHE_HOME": (hmz.cache, ".cache"),
}

#: What a release kept in `~/.hmz`, by where it is kept now under the user's home.
KEPT = {
    "settings.yaml": ".config/humanize",
    "providers/claude/a/provider.json": ".local/share/humanize",
    "epics/w/x/epic.jsonl": ".local/share/humanize",
    "chats/w/x/chat.jsonl": ".local/share/humanize",
    "flowverses/v/index/index.yaml": ".local/share/humanize",
    "flows/f/flow.py": ".local/share/humanize",
    "identity/m/key.pem": ".local/share/humanize",
    "ai/m/conversations.yaml": ".local/share/humanize",
    "history.jsonl": ".local/state/humanize",
    "web-port": ".local/state/humanize",
    "envs/e/clones/c/file": ".local/state/humanize",
    "easytier/1/easytier-core": ".cache/humanize",
}


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home directory of the test's own, no base directory moved out of it."""
    mine = tmp_path / "me"
    mine.mkdir()
    monkeypatch.setenv("HOME", str(mine))
    for variable in BASES:
        monkeypatch.delenv(variable, raising=False)
    return mine


def seeded(at: Path, names: list[str] | dict[str, str]) -> None:
    """A former home holding each of these files, each holding its own name."""
    for name in names:
        (at / name).parent.mkdir(parents=True, exist_ok=True)
        (at / name).write_text(name)


def test_each_directory_is_humanize_in_its_base_under_the_home(home: Path) -> None:
    for kept, otherwise in BASES.values():
        assert kept() == home / otherwise / "humanize"
    # Nothing to move, nothing made.
    assert list(home.iterdir()) == []


def test_a_base_named_by_its_variable_is_used_and_a_relative_one_ignored(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for variable, (kept, _) in BASES.items():
        monkeypatch.setenv(variable, str(tmp_path / variable))
        assert kept() == tmp_path / variable / "humanize"
    for variable, (kept, otherwise) in BASES.items():
        monkeypatch.setenv(variable, "relative/base")
        assert kept() == home / otherwise / "humanize"
        monkeypatch.setenv(variable, "")
        assert kept() == home / otherwise / "humanize"


def test_what_a_release_kept_is_moved_where_it_is_kept_now(home: Path) -> None:
    seeded(home / ".hmz", KEPT)
    seeded(home / ".hmz", ["local/x", "server.json"])

    assert hmz.data() == home / ".local/share/humanize"

    for name, into in KEPT.items():
        assert (home / into / name).read_text() == name
    # What nothing reads any more stays where it was, and so does the directory holding it,
    # now marked as moved.
    assert sorted(one.name for one in (home / ".hmz").iterdir()) == [
        hmz.MOVED,
        "local",
        "server.json",
    ]


def test_a_former_home_emptied_is_removed(home: Path) -> None:
    seeded(home / ".hmz", KEPT)

    hmz.config()

    assert not (home / ".hmz").exists()


def test_a_former_home_that_is_a_link_is_emptied_where_it_leads(
    home: Path, tmp_path: Path
) -> None:
    elsewhere = tmp_path / "elsewhere"
    seeded(elsewhere, KEPT)
    (home / ".hmz").symlink_to(elsewhere)
    # What an interrupted `hmz home move` left beside it, which is nobody's to move.
    seeded(home / ".hmz.moving", ["settings.yaml"])

    hmz.state()

    for name, into in KEPT.items():
        assert (home / into / name).read_text() == name
    assert not (home / ".hmz").is_symlink()
    assert not elsewhere.exists()
    assert (home / ".hmz.moving" / "settings.yaml").exists()


def test_nothing_is_merged_into_what_is_already_there(home: Path) -> None:
    seeded(home / ".hmz", ["settings.yaml", "epics/w/old/epic.jsonl", "history.jsonl"])
    seeded(home / ".config/humanize", ["settings.yaml"])
    seeded(home / ".local/share/humanize", ["epics/w/new/epic.jsonl"])
    (home / ".config/humanize/settings.yaml").write_text("mine")

    hmz.cache()

    assert (home / ".config/humanize/settings.yaml").read_text() == "mine"
    assert not (home / ".local/share/humanize/epics/w/old").exists()
    assert (home / ".local/state/humanize/history.jsonl").exists()
    assert sorted(one.name for one in (home / ".hmz").iterdir()) == [
        hmz.MOVED,
        "epics",
        "settings.yaml",
    ]


def test_the_name_before_is_moved_after_the_one_since(home: Path) -> None:
    seeded(home / ".hmz", ["settings.yaml"])
    seeded(home / ".humanize", ["settings.yaml", "history.jsonl"])
    (home / ".hmz/settings.yaml").write_text("newer")

    hmz.config()

    assert (home / ".config/humanize/settings.yaml").read_text() == "newer"
    assert (home / ".local/state/humanize/history.jsonl").exists()
    assert not (home / ".hmz").exists()
    assert sorted(one.name for one in (home / ".humanize").iterdir()) == [
        hmz.MOVED,
        "settings.yaml",
    ]


def test_into_custom_bases(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded(home / ".hmz", KEPT)
    for variable in BASES:
        monkeypatch.setenv(variable, str(tmp_path / variable))

    hmz.data()

    for name, into in KEPT.items():
        base = {
            ".config/humanize": "XDG_CONFIG_HOME",
            ".local/share/humanize": "XDG_DATA_HOME",
            ".local/state/humanize": "XDG_STATE_HOME",
            ".cache/humanize": "XDG_CACHE_HOME",
        }[into]
        assert (tmp_path / base / "humanize" / name).read_text() == name
    assert not (home / ".local").exists()


def test_moved_once_what_is_put_there_since_is_a_projects_own(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded(home / ".hmz", ["history.jsonl", "server.json"])
    hmz.state()
    assert (home / ".hmz" / hmz.MOVED).read_text()

    # The flows of a workspace `~`, and another process asking afresh, of a scratch directory.
    seeded(home / ".hmz", ["flows/mine/flow.py"])
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    hmz.data()

    assert (home / ".hmz/flows/mine/flow.py").exists()
    assert not (tmp_path / "data").exists()


def test_what_could_not_be_moved_is_left_and_moved_by_the_next_process(
    home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded(home / ".hmz", ["epics/w/x/epic.jsonl", "history.jsonl"])
    held = home / ".local/share/humanize"
    held.mkdir(parents=True)
    held.chmod(0o555)
    try:
        hmz.data()
    finally:
        held.chmod(0o755)

    assert (home / ".local/state/humanize/history.jsonl").exists()
    assert (home / ".hmz/epics/w/x/epic.jsonl").exists()
    assert not (home / ".hmz" / hmz.MOVED).read_text()

    # Another process: asked with a set of places of its own.
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    hmz.data()

    assert (held / "epics/w/x/epic.jsonl").exists()
    assert not (home / ".hmz").exists()


def test_a_project_run_from_the_home_directory_is_not_the_home_before(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded(home / ".humanize", ["history.jsonl", "server.json"])
    monkeypatch.chdir(home)

    assert hmz.here() == Path(".hmz")

    assert (home / ".local/state/humanize/history.jsonl").exists()
    assert not (home / ".hmz").exists()
    assert (home / ".humanize" / "server.json").exists()


def test_a_worktree_moved_with_envs_is_one_its_repository_still_finds(
    home: Path, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "init", "-q", str(repo)], check=True)
    subprocess.run(
        [*git, "-C", str(repo), "commit", "-q", "--allow-empty", "-m", "x"], check=True
    )
    was = home / ".hmz/envs/repo-1/worktrees/t"
    subprocess.run(
        [*git, "-C", str(repo), "worktree", "add", "-q", "--detach", str(was)],
        check=True,
    )

    hmz.state()

    now = home / ".local/state/humanize/envs/repo-1/worktrees/t"
    listed = subprocess.run(
        ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert f"worktree {now.resolve()}" in listed or f"worktree {now}" in listed
    assert "prunable" not in listed
