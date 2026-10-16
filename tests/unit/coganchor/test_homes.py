"""A CLI's virtual home: copies of what it rewrites, links to the rest, the flow's skills beside."""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING, Any

import pytest

from hmz.coganchor.backends import named
from hmz.coganchor.homes import (
    Home,
    Virtual,
    build,
    merged,
    merger,
    virtual,
    words,
)

if TYPE_CHECKING:
    from pathlib import Path

CLAUDE = Virtual(
    variable="CLAUDE_CONFIG_DIR",
    default=".claude",
    rewrites=(".claude.json", "settings.json"),
    outside=((".claude.json", ".claude.json"),),
    lodges="skills",
    secures="CLAUDE_SECURESTORAGE_CONFIG_DIR",
    made=("projects", "history.jsonl"),
)


def _user(tmp_path: Path) -> Path:
    """A user's own home with a Claude in it: settings, a sign-in, a skill, a conversation."""
    home = tmp_path / "user"
    real = home / ".claude"
    (real / "skills" / "mine").mkdir(parents=True)
    (real / "skills" / "mine" / "SKILL.md").write_text("theirs\n")
    (real / "skills" / "review").mkdir()
    (real / "skills" / "review" / "SKILL.md").write_text("their review\n")
    (real / "settings.json").write_text('{"theirs": true}\n')
    (real / ".credentials.json").write_text("token\n")
    (real / ".claude.json").write_text('{"inside": true}\n')
    (home / ".claude.json").write_text('{"outside": true}\n')
    return home


@merger
def _settled(home: Path, said: dict[str, Any]) -> None:
    """A driver's merge: what it says, over the copy of the user's `settings.json`."""
    at = home / "settings.json"
    at.write_text(json.dumps(json.loads(at.read_text()) | said))


@merger
def _owned(home: Path, said: None) -> None:
    """A driver's merge putting a directory of its own where the user's is linked."""
    del said
    (home / "agents").unlink()
    (home / "agents").mkdir()
    (home / "agents" / "ours.md").write_text("ours\n")


def _flow(tmp_path: Path) -> Path:
    skill = tmp_path / "flow" / "review"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("the flow's review\n")
    return skill


def test_a_home_copies_what_the_cli_rewrites_and_links_the_rest(tmp_path: Path) -> None:
    user = _user(tmp_path)
    home = build(CLAUDE, {"HOME": str(user)}, under=tmp_path)
    real = user / ".claude"

    assert home.real == real
    assert home.at.parent == tmp_path.resolve()
    settings = home.at / "settings.json"
    assert not settings.is_symlink()
    settings.write_text("rewritten\n")
    assert (real / "settings.json").read_text() == '{"theirs": true}\n'
    # Kept outside the home while the variable is unset, and copied from there.
    assert (home.at / ".claude.json").read_text() == '{"outside": true}\n'
    assert (home.at / ".credentials.json").is_symlink()
    assert (home.at / ".credentials.json").resolve() == real / ".credentials.json"
    # Where conversations go is made in the user's home, so what is written there stays.
    assert (real / "projects").is_dir()
    assert (home.at / "projects").resolve() == real / "projects"
    assert (home.at / "history.jsonl").is_symlink()
    (home.at / "history.jsonl").write_text("said\n")
    assert (real / "history.jsonl").read_text() == "said\n"


def test_the_flows_skills_go_beside_the_users_own(tmp_path: Path) -> None:
    user = _user(tmp_path)
    skill = _flow(tmp_path)
    spec = Virtual(
        variable="CLAUDE_CONFIG_DIR",
        default=".claude",
        lodges="skills",
        skills=(("review", str(skill)),),
    )

    home = build(spec, {"HOME": str(user)}, under=tmp_path)

    skills = home.at / "skills"
    assert sorted(one.name for one in skills.iterdir()) == ["mine", "review"]
    assert (skills / "mine" / "SKILL.md").read_text() == "theirs\n"
    assert (skills / "review" / "SKILL.md").read_text() == "the flow's review\n"
    assert (user / ".claude" / "skills" / "review" / "SKILL.md").read_text() == (
        "their review\n"
    )


def test_a_home_variable_the_user_set_is_the_home_and_keeps_the_sign_in(
    tmp_path: Path,
) -> None:
    user = _user(tmp_path)
    real = user / ".claude"
    said = {"HOME": str(user), "CLAUDE_CONFIG_DIR": str(real)}

    home = build(CLAUDE, said, under=tmp_path)

    assert (home.at / ".claude.json").read_text() == '{"inside": true}\n'
    assert home.environ(said) == {
        "HOME": str(user),
        "CLAUDE_CONFIG_DIR": str(home.at),
        "CLAUDE_SECURESTORAGE_CONFIG_DIR": str(real),
    }
    unset = build(CLAUDE, {"HOME": str(user)}, under=tmp_path)
    assert dict(unset.sets)["CLAUDE_SECURESTORAGE_CONFIG_DIR"] == ""


def test_a_sign_in_place_the_user_named_is_left_as_they_named_it(
    tmp_path: Path,
) -> None:
    said = {"HOME": str(_user(tmp_path)), "CLAUDE_SECURESTORAGE_CONFIG_DIR": "/x"}

    home = build(CLAUDE, said, under=tmp_path)

    assert home.environ(said)["CLAUDE_SECURESTORAGE_CONFIG_DIR"] == "/x"


def test_a_copy_is_made_of_what_a_provider_answers_the_path_with(
    tmp_path: Path,
) -> None:
    user = _user(tmp_path)
    account = tmp_path / "account.json"
    account.write_text('{"account": true}\n')
    outside = str(user / ".claude.json")

    home = build(
        CLAUDE,
        {"HOME": str(user)},
        under=tmp_path,
        answered=lambda path: str(account) if path == outside else None,
    )

    assert (home.at / ".claude.json").read_text() == '{"account": true}\n'


def test_dropping_a_home_leaves_the_users_own_whole(tmp_path: Path) -> None:
    user = _user(tmp_path)
    home = build(CLAUDE, {"HOME": str(user)}, under=tmp_path)

    home.drop()

    assert not home.at.exists()
    assert (user / ".claude" / ".credentials.json").read_text() == "token\n"
    assert (user / ".claude" / "skills" / "mine" / "SKILL.md").exists()


def test_private_names_are_neither_linked_nor_made(tmp_path: Path) -> None:
    user = _user(tmp_path)
    (user / ".claude" / "sessions").mkdir()
    spec = Virtual(variable="CLAUDE_CONFIG_DIR", default=".claude", private=("sess*",))

    home = build(spec, {"HOME": str(user)}, under=tmp_path)

    assert not (home.at / "sessions").exists()
    assert (home.at / "settings.json").is_symlink()


def test_a_supervisors_paths_are_said_under_the_home_too(tmp_path: Path) -> None:
    real = tmp_path / "real"
    home = Home(
        at=tmp_path / "virtual",
        real=real,
        sets=(),
        rewrites=(".claude.json",),
    )

    spelled = home.spelled(
        [
            (f"{real}/projects", "/kept/projects"),
            (f"{real}/.claude.json", "/account/.claude.json"),
            ("/elsewhere/x", "/y"),
        ]
    )

    assert spelled == (
        (f"{real}/projects", "/kept/projects"),
        (f"{real}/.claude.json", "/account/.claude.json"),
        ("/elsewhere/x", "/y"),
        (f"{tmp_path}/virtual/projects", "/kept/projects"),
    )


def test_a_virtual_home_reads_back_as_itself() -> None:
    spec = Virtual(
        variable="CODEX_HOME",
        default=".codex",
        rewrites=("config.toml",),
        outside=(("config.toml", ".codex.toml"),),
        lodges="skills",
        private=("state_*.sqlite*",),
        made=("sessions",),
        skills=(("review", "/flow/review"),),
        merges=(merged(_settled, {"effort": "high"}),),
        records=(("state_*.sqlite", "threads", "rollout_path"),),
    )

    assert Virtual.loads(spec.dumps()) == spec
    assert words(spec) == [
        "copy=config.toml=.codex.toml",
        "keep=state_*.sqlite*",
        "make=sessions",
        "skill=review",
        "record=state_*.sqlite=threads=rollout_path",
    ]


@pytest.mark.parametrize(
    ("variable", "rewrites", "skills"),
    [
        ("", (), ()),
        ("A-B", (), ()),
        ("X", ("../out",), ()),
        ("X", (), (("/abs", "/flow"),)),
    ],
)
def test_a_virtual_home_naming_outside_itself_is_refused(
    variable: str, rewrites: tuple[str, ...], skills: tuple[tuple[str, str], ...]
) -> None:
    with pytest.raises(ValueError, match=r"unsupported|needs"):
        Virtual(variable=variable, default=".x", rewrites=rewrites, skills=skills)
    with pytest.raises(ValueError, match="not a virtual home"):
        Virtual.loads("{}")


def test_qwen_grok_pi_and_omp_are_started_in_one_with_their_skills_lodged(
    tmp_path: Path,
) -> None:
    skills = [("review", str(tmp_path))]
    rewritten = {
        "qwen": ("settings.json",),
        "grok": ("config.toml",),
        "pi": ("models.json", "settings.json"),
        "omp": (),
    }
    for cli, rewrites in rewritten.items():
        profile = named(cli)
        assert profile is not None
        made = virtual(profile, skills)
        assert made is not None
        assert made.rewrites == rewrites
        assert made.lodges == "skills"
        assert made.skills == (("review", str(tmp_path)),)


def test_claude_and_codex_are_started_in_one_and_others_are_not(
    tmp_path: Path,
) -> None:
    claude, codex, litellm = named("claude"), named("codex"), named("litellm")
    assert claude is not None
    assert codex is not None
    assert litellm is not None
    skills = [("review", str(tmp_path))]

    made = virtual(claude, skills)
    assert made is not None
    assert made.variable == "CLAUDE_CONFIG_DIR"
    assert ".claude.json" in made.rewrites
    assert made.secures == "CLAUDE_SECURESTORAGE_CONFIG_DIR"
    assert made.skills == (("review", str(tmp_path)),)
    assert "projects" in made.made
    linked = virtual(codex, skills)
    assert linked is not None
    assert linked.records == (("state_*.sqlite", "threads", "rollout_path"),)
    held = virtual(codex, skills, private=True)
    assert held is not None
    assert held.rewrites == ("config.toml",)
    assert "state_*.sqlite*" in held.private
    assert held.made == ()
    # Its databases are the home's own, brought back with what they name.
    assert held.records == ()
    assert virtual(litellm, skills) is None


def test_a_home_that_cannot_be_built_leaves_nothing(tmp_path: Path) -> None:
    user = _user(tmp_path)
    (user / ".claude" / "settings.json").chmod(0)
    if os.access(user / ".claude" / "settings.json", os.R_OK):
        pytest.skip("this user reads everything")
    under = tmp_path / "homes"
    under.mkdir()

    with pytest.raises(OSError, match="ermission"):
        build(CLAUDE, {"HOME": str(user)}, under=under)

    assert list(under.iterdir()) == []


def test_what_the_cli_made_for_the_user_to_keep_is_moved_home_as_it_goes(
    tmp_path: Path,
) -> None:
    user = _user(tmp_path)
    (user / ".claude" / "state_1.sqlite").write_text("theirs\n")
    spec = Virtual(
        variable="CLAUDE_CONFIG_DIR", default=".claude", kept=("state_*.sqlite*",)
    )
    home = build(spec, {"HOME": str(user)}, under=tmp_path)
    (home.at / "state_2.sqlite").write_text("new\n")
    (home.at / "scratch.txt").write_text("the CLI's own\n")

    home.drop()

    assert (user / ".claude" / "state_2.sqlite").read_text() == "new\n"
    assert (user / ".claude" / "state_1.sqlite").read_text() == "theirs\n"
    assert not (user / ".claude" / "scratch.txt").exists()


def test_a_directory_the_cli_rewrites_starts_empty(tmp_path: Path) -> None:
    user = _user(tmp_path)
    (user / ".claude" / "backups").mkdir()
    (user / ".claude" / "backups" / "old.json").write_text("theirs\n")
    spec = Virtual(
        variable="CLAUDE_CONFIG_DIR", default=".claude", rewrites=("backups",)
    )

    home = build(spec, {"HOME": str(user)}, under=tmp_path)

    assert (home.at / "backups").is_dir()
    assert not (home.at / "backups").is_symlink()
    assert list((home.at / "backups").iterdir()) == []


def test_a_projected_account_has_none_of_the_users_credentials_beside_it() -> None:
    claude = named("claude")
    assert claude is not None

    held = virtual(claude, private=True)

    assert held is not None
    assert ".credentials.json" in held.private
    assert ".claude.json" in held.private
    assert ".claude.json" not in held.rewrites
    assert held.kept == ()


def test_a_home_only_a_flag_moves_is_named_on_the_command_line(tmp_path: Path) -> None:
    user = tmp_path / "user"
    real = user / ".gemini" / "antigravity-cli"
    (real / "conversations").mkdir(parents=True)
    spec = Virtual(
        variable="", default=".gemini/antigravity-cli", flag="--app_data_dir"
    )

    home = build(spec, {"HOME": str(user)}, under=tmp_path)

    assert home.real == real
    assert home.sets == ()
    (said,) = home.argv
    flag, _, where = said.partition("=")
    assert flag == "--app_data_dir"
    # Relative to `~/.gemini`, the one way agy takes it, and naming the home from there.
    assert not where.startswith("/")
    assert os.path.normpath(user / ".gemini" / where) == str(home.at)
    assert (home.at / "conversations").resolve() == real / "conversations"
    with pytest.raises(ValueError, match="needs"):
        Virtual(variable="", default=".x")


def test_every_cli_that_takes_skills_at_its_home_is_started_in_one(
    tmp_path: Path,
) -> None:
    skills = [("review", str(tmp_path))]
    for cli, variable in (
        ("cursor-agent", "CURSOR_CONFIG_DIR"),
        ("kimi", "KIMI_CODE_HOME"),
        ("mcode", "MINIMAX_DATA_DIR"),
    ):
        profile = named(cli)
        assert profile is not None
        made = virtual(profile, skills)
        assert made is not None
        assert (made.variable, made.lodges, made.flag) == (variable, "skills", "")
        assert made.skills == (("review", str(tmp_path)),)
    mcode = named("mcode")
    assert mcode is not None
    assert "config.yaml" in mcode.rewrites
    agy = named("agy")
    assert agy is not None
    made = virtual(agy, skills)
    assert made is not None
    assert (made.variable, made.flag, made.lodges) == ("", "--app_data_dir", "skills")
    # Neither of these: opencode's are named in its config, and dsh takes none.
    for cli in ("opencode", "mimo", "dsh"):
        profile = named(cli)
        assert profile is not None
        assert virtual(profile, skills) is None


def _renamed(at: Path, said: str, *, mtime: int | None = None) -> None:
    """What a CLI saving a file atomically does: writes another beside it, renames it over."""
    beside = at.with_name(f".{at.name}.tmp")
    beside.write_text(said)
    if mtime is not None:
        os.utime(beside, (mtime, mtime))
    beside.replace(at)


def test_a_credential_the_cli_replaced_by_rename_is_written_back(
    tmp_path: Path,
) -> None:
    user = _user(tmp_path)
    real = user / ".claude" / ".credentials.json"
    real.chmod(0o600)
    os.utime(real, (1_000_000, 1_000_000))
    home = build(CLAUDE, {"HOME": str(user)}, under=tmp_path)

    _renamed(home.at / ".credentials.json", "refreshed\n")
    assert not (home.at / ".credentials.json").is_symlink()
    home.drop()

    assert real.read_text() == "refreshed\n"
    assert real.stat().st_mode & 0o777 == 0o600
    assert not home.at.exists()


def test_an_older_replacement_does_not_clobber_a_newer_real_file(
    tmp_path: Path,
) -> None:
    user = _user(tmp_path)
    real = user / ".claude" / ".credentials.json"
    home = build(CLAUDE, {"HOME": str(user)}, under=tmp_path)

    _renamed(home.at / ".credentials.json", "stale\n", mtime=1_000_000)
    real.write_text("another process's newer token\n")
    home.drop()

    assert real.read_text() == "another process's newer token\n"


def test_what_a_cli_rewrites_is_still_discarded(tmp_path: Path) -> None:
    user = _user(tmp_path)
    home = build(CLAUDE, {"HOME": str(user)}, under=tmp_path)

    _renamed(home.at / "settings.json", '{"rewritten": true}\n')
    _renamed(home.at / ".claude.json", '{"rewritten": true}\n')
    home.drop()

    assert (user / ".claude" / "settings.json").read_text() == '{"theirs": true}\n'
    assert (user / ".claude.json").read_text() == '{"outside": true}\n'


def test_a_replaced_directory_is_merged_back_a_new_or_changed_file_at_a_time(
    tmp_path: Path,
) -> None:
    user = _user(tmp_path)
    sessions = user / ".claude" / "projects"
    sessions.mkdir()
    (sessions / "old.jsonl").write_text("theirs\n")
    os.utime(sessions / "old.jsonl", (1_000_000, 1_000_000))
    (sessions / "newer.jsonl").write_text("newer\n")
    home = build(CLAUDE, {"HOME": str(user)}, under=tmp_path)
    replaced = home.at / "projects.tmp"
    replaced.mkdir()
    (replaced / "old.jsonl").write_text("changed\n")
    (replaced / "made.jsonl").write_text("made\n")
    (replaced / "newer.jsonl").write_text("stale\n")
    os.utime(replaced / "newer.jsonl", (1_000_000, 1_000_000))
    (home.at / "projects").unlink()
    replaced.rename(home.at / "projects")

    home.drop()

    assert (sessions / "old.jsonl").read_text() == "changed\n"
    assert (sessions / "made.jsonl").read_text() == "made\n"
    assert (sessions / "newer.jsonl").read_text() == "newer\n"


def test_a_replaced_credential_goes_back_to_the_account_a_provider_answers_with(
    tmp_path: Path,
) -> None:
    user = _user(tmp_path)
    account = tmp_path / "account" / ".credentials.json"
    account.parent.mkdir()
    account.write_text("the account's\n")
    os.utime(account, (1_000_000, 1_000_000))
    named_ = str(user / ".claude" / ".credentials.json")
    home = build(
        CLAUDE,
        {"HOME": str(user)},
        under=tmp_path,
        answered=lambda path: str(account) if path == named_ else None,
    )

    _renamed(home.at / ".credentials.json", "refreshed\n")
    home.drop()

    assert account.read_text() == "refreshed\n"
    assert (user / ".claude" / ".credentials.json").read_text() == "token\n"


def test_what_a_driver_manages_is_merged_into_the_copies(tmp_path: Path) -> None:
    user = _user(tmp_path)
    spec = Virtual(
        variable="CLAUDE_CONFIG_DIR",
        default=".claude",
        rewrites=("settings.json",),
        merges=(merged(_settled, {"effort": "high"}),),
    )

    home = build(Virtual.loads(spec.dumps()), {"HOME": str(user)}, under=tmp_path)

    assert json.loads((home.at / "settings.json").read_text()) == {
        "theirs": True,
        "effort": "high",
    }
    assert (user / ".claude" / "settings.json").read_text() == '{"theirs": true}\n'


def test_what_a_merge_made_its_own_is_never_written_back(tmp_path: Path) -> None:
    user = _user(tmp_path)
    (user / ".claude" / "agents").mkdir()
    spec = Virtual(
        variable="CLAUDE_CONFIG_DIR", default=".claude", merges=(merged(_owned),)
    )

    home = build(spec, {"HOME": str(user)}, under=tmp_path)
    home.drop()

    assert "agents" not in home.linked
    assert list((user / ".claude" / "agents").iterdir()) == []


def test_a_merge_humanize_has_no_merger_for_leaves_no_home(tmp_path: Path) -> None:
    user = _user(tmp_path)
    spec = Virtual(
        variable="CLAUDE_CONFIG_DIR",
        default=".claude",
        merges=(("hmz.nowhere:_merge", "null"), ("os:system", '"true"')),
    )

    with pytest.raises(ValueError, match="no merger"):
        build(spec, {"HOME": str(user)}, under=tmp_path)

    assert [one.name for one in tmp_path.iterdir()] == ["user"]


def test_only_a_merger_is_merged() -> None:
    with pytest.raises(ValueError, match="is not a merger"):
        merged(print)


def test_a_path_of_the_home_the_cli_wrote_down_is_followed_as_it_goes(
    tmp_path: Path,
) -> None:
    import sqlite3

    real = tmp_path / "user" / ".codex"
    (real / "sessions").mkdir(parents=True)
    state = real / "state_5.sqlite"
    with sqlite3.connect(state) as connection:
        connection.execute("create table threads (id text, rollout_path text)")
    connection.close()
    spec = Virtual(
        variable="CODEX_HOME",
        default=".codex",
        rewrites=("config.toml",),
        made=("sessions",),
        records=(("state_*.sqlite", "threads", "rollout_path"),),
    )
    home = build(spec, {"HOME": str(tmp_path / "user")}, under=tmp_path)
    (home.at / "sessions" / "a.jsonl").write_text("{}\n")
    rows = [
        ("kept", f"{home.at}/sessions/a.jsonl"),
        # Nothing there to follow to: left as it was.
        ("gone", f"{home.at}/sessions/b.jsonl"),
        ("other", f"{real}/sessions/c.jsonl"),
    ]
    with sqlite3.connect(home.at / "state_5.sqlite") as connection:
        connection.executemany("insert into threads values (?, ?)", rows)
    connection.close()

    home.drop()

    with sqlite3.connect(state) as connection:
        said = dict(connection.execute("select id, rollout_path from threads"))
    connection.close()
    assert said == {
        "kept": os.path.realpath(real / "sessions" / "a.jsonl"),
        "gone": rows[1][1],
        "other": rows[2][1],
    }
