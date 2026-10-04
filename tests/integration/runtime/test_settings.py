"""Two holders of the settings at once, neither putting back what the other has written.

Two `hmz` on one home, a menu saving while the interface goes on remembering flows, an `hmz
exec` beside an interface: each holds the file as it read it, and each writes. What one of
them wrote must still be there after the other writes, whichever workspace and whichever key
it was.
"""

from __future__ import annotations

import fcntl
import multiprocessing
import os
from typing import TYPE_CHECKING

import yaml

from hmz import home
from hmz.runtime import settings
from hmz.runtime.kept import Runs
from hmz.runtime.settings import Settings

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

#: How many processes write at once, and how many times each.
WRITERS = 6
ROUNDS = 15


def test_two_holders_of_one_workspace_keep_each_others_changes(tmp_path: Path) -> None:
    mine, theirs = Settings(tmp_path), Settings(tmp_path)

    mine.remember("rlar", {"actor": Runs("codex/n:low")}, profile=True)
    theirs.remember("chat", {"assistant": Runs("claude/m:high")})

    again = Settings(tmp_path)
    assert again.profile("rlar") is True
    assert again.flow == "chat"
    assert again.agents("chat") == {"assistant": Runs("claude/m:high")}


def test_a_stale_copy_of_another_workspace_is_never_put_back(tmp_path: Path) -> None:
    one, other = tmp_path / "one", tmp_path / "other"
    Settings(one).remember("chat", {"assistant": Runs("claude/m:high")})
    # Both open now, each holding the first workspace as it is now.
    here, there = Settings(one), Settings(other)

    here.remember("rlar", {"actor": Runs("codex/n:low")})
    there.remember("chat", {"assistant": Runs("kimi/k:max")})

    assert Settings(one).flow == "rlar"
    assert Settings(one).agents("rlar") == {"actor": Runs("codex/n:low")}
    assert Settings(other).flow == "chat"


def test_what_was_not_handed_in_is_read_from_the_file_as_it_is_now(
    tmp_path: Path,
) -> None:
    """Choosing the agents again keeps the params somebody else set, not the ones before."""
    Settings(tmp_path).remember(
        "humanize1", {"builder": Runs("claude/m:high")}, params={"max": 1}
    )
    mine, theirs = Settings(tmp_path), Settings(tmp_path)

    theirs.remember("humanize1", {"builder": Runs("claude/m:high")}, params={"max": 9})
    mine.remember("humanize1", {"builder": Runs("codex/n:low")})

    again = Settings(tmp_path)
    assert again.params("humanize1") == {"max": 9}
    assert again.agents("humanize1") == {"builder": Runs("codex/n:low")}


def test_choosing_the_agents_again_leaves_whether_a_run_is_profiled(
    tmp_path: Path,
) -> None:
    """Kept per flow beside the budget, and left alone by what does not hand it in."""
    kept = Settings(tmp_path)
    kept.remember("humanize1", {"builder": Runs("claude/m:high")}, profile=True)
    kept.remember("humanize1", {"builder": Runs("codex/n:low")})

    assert Settings(tmp_path).profile("humanize1") is True
    assert Settings(tmp_path).profile("chat") is False

    kept.remember("humanize1", {"builder": Runs("codex/n:low")}, profile=False)

    assert Settings(tmp_path).profile("humanize1") is False


def test_the_settings_of_this_machine_survive_each_other(tmp_path: Path) -> None:
    mine, theirs = Settings(tmp_path), Settings(tmp_path)

    mine.detailing(on=True)
    theirs.btw = "claude/m:high"
    theirs.answers(enable_sentry=False)

    again = Settings(tmp_path)
    assert again.details is True
    assert again.btw == "claude/m:high"
    assert again.enable_sentry is False


def test_forgetting_a_workspace_takes_only_that_one(tmp_path: Path) -> None:
    one, other = tmp_path / "one", tmp_path / "other"
    Settings(one).remember("chat", {"assistant": Runs("claude/m:high")})
    here = Settings(one)
    Settings(other).remember("rlar", {"actor": Runs("codex/n:low")})

    assert here.forget() is True
    assert here.forget() is False

    assert Settings(one).flow == ""
    assert Settings(other).flow == "rlar"


def test_a_holder_sees_what_others_wrote_once_it_has_written(tmp_path: Path) -> None:
    mine, theirs = Settings(tmp_path), Settings(tmp_path)

    theirs.remember("chat", {"assistant": Runs("claude/m:high")})
    mine.detailing(on=True)

    assert mine.flow == "chat"


def test_forgetting_an_empty_entry_is_still_forgetting_one(tmp_path: Path) -> None:
    home().mkdir(parents=True)
    (home() / "settings.yaml").write_text(f"workspaces:\n  {tmp_path}:\n")

    assert Settings(tmp_path).forget() is True


def test_a_file_broken_since_it_was_read_is_not_written_back_as_one_change(
    tmp_path: Path,
) -> None:
    """What this holds goes back with the change, rather than the change alone."""
    Settings(tmp_path).remember("chat", {"assistant": Runs("claude/m:high")})
    kept = Settings(tmp_path)
    (home() / "settings.yaml").write_text("workspaces: [unclosed\n")

    kept.detailing(on=True)

    again = Settings(tmp_path)
    assert again.details is True
    assert again.agents("chat") == {"assistant": Runs("claude/m:high")}


def test_a_writer_that_never_lets_go_is_waited_for_and_then_gone_round(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "_PATIENCE", 0.2)
    kept = Settings(tmp_path)
    home().mkdir(parents=True, exist_ok=True)
    held = os.open(home() / ".settings.yaml.lock", os.O_CREAT | os.O_RDONLY, 0o600)
    try:
        fcntl.flock(held, fcntl.LOCK_EX)
        kept.detailing(on=True)
    finally:
        os.close(held)

    assert Settings(tmp_path).details is True


def test_many_processes_writing_at_once_keep_every_change(tmp_path: Path) -> None:
    """Every write of every process is there afterwards, and the file is whole throughout."""
    spawning = multiprocessing.get_context("spawn")
    workers = [
        spawning.Process(target=_writes, args=(str(tmp_path), n))
        for n in range(WRITERS)
    ]
    try:
        for one in workers:
            one.start()
        for one in workers:
            one.join(timeout=120)
    finally:
        for one in workers:
            one.kill()
    assert [one.exitcode for one in workers] == [0] * WRITERS

    held = yaml.safe_load((home() / "settings.yaml").read_text(encoding="utf-8"))
    for n in range(WRITERS):
        # A workspace of its own, and one it shares with every other.
        assert str(tmp_path / f"own{n}") in held["workspaces"]
        own = Settings(tmp_path / f"own{n}")
        assert own.flow == f"flow{ROUNDS - 1}"
        shared = Settings(tmp_path / "shared")
        for r in range(ROUNDS):
            assert shared.agents(f"w{n}r{r}") == {"actor": Runs("claude/m:high")}
    assert not list(home().glob(".settings.yaml.*.new"))


def _writes(workspace: str, n: int) -> None:
    """One process's writes: to a workspace of its own, and to one every process shares."""
    from pathlib import Path

    root = Path(workspace)
    own, shared = Settings(root / f"own{n}"), Settings(root / "shared")
    for r in range(ROUNDS):
        own.remember(f"flow{r}", {"actor": Runs("claude/m:high")})
        shared.remember(f"w{n}r{r}", {"actor": Runs("claude/m:high")})
