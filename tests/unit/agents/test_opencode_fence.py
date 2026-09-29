"""opencode and mimocode under a fence: held from outside, and told where their tools may reach.

Neither CLI confines its shell or its own process, so every scope is held by
``hmz internal fence`` around it; what the driver adds is the permission table's path rules,
which turn a tool call the fence would refuse into a refusal the agent can read. The rules are
checked here the way opencode reads them: each pattern a wildcard in which `*` crosses `/`, the
last rule that matches deciding, and `read` and `edit` asked in paths relative to the checkout.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import sys
from typing import TYPE_CHECKING, cast

import pytest

from hmz.coganchor.agents import (
    MimoCodeAgent,
    MimoCodeAgentConfig,
    OpencodeAgent,
    OpencodeAgentConfig,
    Unserved,
)
from hmz.coganchor.fence import ALL, NONE, READ, Fence

if TYPE_CHECKING:
    from pathlib import Path


def _able(*, net: bool) -> bool:
    del net
    return True


@pytest.fixture
def home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A machine that can fence a process, with a home of the test's own."""
    monkeypatch.setattr("hmz.coganchor.fence.enforceable", _able)
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    return home


def _fence(
    home: Path, work: Path, local: str, user: str, system: str, *, online: bool
) -> Fence:
    return dataclasses.replace(
        Fence.of(
            local=local,
            user=user,
            system=system,
            online=online,
            workdir=work,
            home=home,
        ),
        tmp=str(home.parent / "scratch"),
    )


def _work(home: Path) -> Path:
    work = home / "work"
    work.mkdir(parents=True)
    return work


def _table(
    home: Path,
    local: str,
    user: str,
    system: str,
    *,
    online: bool = True,
    permission: str = "bypass",
    work: Path | None = None,
) -> dict[str, object]:
    work = work or _work(home)
    fence = _fence(home, work, local, user, system, online=online)
    config = OpencodeAgentConfig(
        model="p/m", effort="high", permission=permission, fence=fence
    )
    session = OpencodeAgent(config).new(work)
    return json.loads(session._environment()["OPENCODE_PERMISSION"])


def _decides(rules: object, asked: str) -> str:
    """What opencode answers a permission asked about one pattern, read as it reads them."""
    if isinstance(rules, str):
        return rules
    assert isinstance(rules, dict)
    answer = "ask"
    for pattern, said in cast("dict[str, str]", rules).items():
        wild = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
        if re.fullmatch(wild, asked, flags=re.DOTALL):
            answer = said
    return answer


def _asked(path: Path | str, worktree: str = os.sep) -> str:
    return os.path.relpath(path, worktree)


def test_neither_cli_holds_its_own_fence(home: Path) -> None:
    """No sandbox of either one's reaches the shell or the process, so all of it is outside."""
    work = _work(home)
    fence = _fence(home, work, ALL, READ, NONE, online=False)
    for agent in (
        OpencodeAgent(OpencodeAgentConfig(model="p/m", effort="high", fence=fence)),
        MimoCodeAgent(MimoCodeAgentConfig(model="p/m", effort="high", fence=fence)),
    ):
        assert agent.natively(fence) is fence
        argv = agent.spawned(["opencode", "run"])
        assert argv[:5] == [sys.executable, "-Pm", "hmz", "internal", "fence"]
        assert argv[argv.index("--") + 1 :][-2:] == ["opencode", "run"]


def test_at_the_default_its_edits_stay_in_the_workdir(home: Path) -> None:
    work = _work(home)
    table = _table(home, ALL, READ, READ, work=work)

    edit = table["edit"]
    assert _decides(edit, _asked(work / "src" / "a.py")) == "allow"
    assert _decides(edit, _asked(home / "fence-probe")) == "deny"
    assert _decides(edit, _asked("/etc/hosts")) == "deny"
    # What the fence lets be written besides: its scratch, and the CLI's own state.
    assert _decides(edit, _asked(home.parent / "scratch" / "x")) == "allow"
    assert _decides(edit, _asked(home / ".config" / "opencode" / "x")) == "allow"
    # The whole system may be read, so nothing is said about reading.
    assert "read" not in table
    assert "external_directory" not in table


def test_with_the_system_untouchable_its_tools_read_only_what_the_fence_grants(
    home: Path,
) -> None:
    work = _work(home)
    table = _table(home, ALL, READ, NONE, online=False, work=work)

    outside = table["external_directory"]
    assert _decides(outside, "/etc/*") == "deny"
    assert _decides(outside, f"{home}/*") == "allow"
    assert _decides(outside, "/usr/lib/*") == "allow"
    read = table["read"]
    assert _decides(read, _asked(home / ".bashrc")) == "allow"
    assert _decides(read, _asked("/etc/machine-id")) == "deny"
    assert _decides(table["edit"], _asked(home / "fence-probe")) == "deny"
    # And the network cut is every web tool taken away, whatever the rung said.
    assert (table["webfetch"], table["websearch"]) == ("deny", "deny")


def test_in_a_checkout_the_rules_are_relative_to_its_top(home: Path) -> None:
    """Opencode asks about `edit` in paths relative to the checkout, so the rules are too."""
    top = home / "repo"
    (top / ".git").mkdir(parents=True)
    work = top / "pkg"
    work.mkdir()
    edit = _table(home, ALL, READ, READ, work=work)["edit"]

    assert _decides(edit, _asked(work / "a.py", str(top))) == "allow"
    assert _decides(edit, _asked(home / "fence-probe", str(top))) == "deny"
    assert _decides(edit, _asked(top / "README", str(top))) == "deny"


def test_a_home_that_may_be_written_is_written_from_a_checkout_inside_it(
    home: Path,
) -> None:
    top = _work(home)
    (top / ".git").mkdir()
    edit = _table(home, ALL, ALL, READ, work=top)["edit"]

    assert _decides(edit, _asked(top / "a.py", str(top))) == "allow"
    assert _decides(edit, _asked(home / ".bashrc", str(top))) == "allow"
    assert _decides(edit, _asked("/etc/hosts", str(top))) == "deny"


def test_a_rung_that_denies_editing_stays_denying(home: Path) -> None:
    table = _table(home, READ, READ, READ, permission="read-only")
    assert table["edit"] == "deny"


def test_a_fence_that_grants_everything_says_nothing_about_paths(home: Path) -> None:
    table = _table(home, ALL, ALL, ALL)
    assert table == {
        "edit": "allow",
        "bash": "allow",
        "webfetch": "allow",
        "websearch": "allow",
    }


def test_mimocode_takes_the_same_rules_and_loses_its_third_web_tool(
    home: Path,
) -> None:
    work = _work(home)
    fence = _fence(home, work, ALL, READ, READ, online=False)
    config = MimoCodeAgentConfig(
        model="p/m", effort="high", permission="bypass", fence=fence
    )
    session = MimoCodeAgent(config).new(work)

    table = json.loads(session._environment()["MIMOCODE_PERMISSION"])

    assert [table[one] for one in ("webfetch", "websearch", "codesearch")] == [
        "deny"
    ] * 3
    assert _decides(table["edit"], _asked(home / "fence-probe")) == "deny"


def test_an_offline_fence_takes_the_web_tools_away_whatever_web_search_says(
    home: Path,
) -> None:
    """A web tool that ran at a host the proxy still passes would be a way out of the fence."""
    table = _table(home, ALL, READ, READ, online=False, permission="read-only")
    assert (table["webfetch"], table["websearch"]) == ("deny", "deny")

    fence = _fence(home, home, ALL, READ, READ, online=False)
    with pytest.raises(Unserved, match="cuts the network"):
        OpencodeAgentConfig(
            model="p/m", effort="high", fence=fence, permission_table=False
        )
    # Online, the table may be withheld: the fence is still held whole from outside.
    online = dataclasses.replace(fence, online=True)
    OpencodeAgentConfig(
        model="p/m", effort="high", fence=online, permission_table=False
    )


def test_mimocode_leaves_claude_codes_settings_alone_where_it_may_not_read_them(
    home: Path,
) -> None:
    """It reads `~/.claude.json` as it starts and dies where it may not; that is not granted."""
    work = _work(home)
    for user, told in ((NONE, "1"), (READ, None)):
        fence = _fence(home, work, ALL, user, NONE, online=True)
        session = MimoCodeAgent(
            MimoCodeAgentConfig(model="p/m", effort="high", fence=fence)
        ).new(work)
        assert session._environment().get("MIMOCODE_DISABLE_CLAUDE_CODE") == told
        assert not fence.allows(home / ".claude.json") or told is None


def test_the_fence_loosens_nothing_opencode_asks_about_itself(home: Path) -> None:
    """Its own table asks before a `.env` is read, and the fence's comes after it and wins."""
    work = _work(home)
    table = _table(home, ALL, READ, NONE, work=work)

    read = table["read"]
    assert _decides(read, _asked(work / ".env")) == "ask"
    assert _decides(read, _asked(work / "a.env.local")) == "ask"
    assert _decides(read, _asked(work / ".env.example")) == "allow"
    assert _decides(read, _asked(work / "a.py")) == "allow"
    assert _decides(read, _asked("/etc/app/.env")) == "deny"
    # A single file the fence grants is no directory to reach into.
    outside = table["external_directory"]
    assert isinstance(outside, dict)
    assert "/etc/passwd/*" not in outside
