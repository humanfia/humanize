"""`hmz skills`: the skill written from the commands, into the folders a harness reads."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest
import yaml

import hmz.coganchor
from hmz.cli import main, tree
from hmz.cli.tree import Command, Example
from hmz.coganchor import backends

if TYPE_CHECKING:
    from pathlib import Path

SKILLS = tree.commands()["skills"]


def _harness(name: str, home: Path, **globs: tuple[str, ...]) -> Any:
    return SimpleNamespace(
        name=name,
        aliases=(name, f"{name}-code"),
        skills=globs.get("skills", ()),
        config=globs.get("config", ()),
        shared=globs.get("shared", ()),
        directory=lambda: home / f".{name}",
        configuration=lambda: home / ".config",
    )


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A home with four harnesses known and two of them installed."""
    at = tmp_path / "home"
    at.mkdir()
    monkeypatch.setenv("HOME", str(at))
    known = [
        _harness("claude", at, skills=("skills/*/SKILL.md",)),
        _harness(
            "codex",
            at,
            skills=("skills/*/SKILL.md",),
            shared=(".agents/skills/*/SKILL.md",),
        ),
        _harness(
            "opencode",
            at,
            config=("opencode/skills/*/SKILL.md",),
            shared=(".agents/skills/*/SKILL.md",),
        ),
        _harness("litellm", at),
    ]

    def named(name: str) -> Any:
        return next((one for one in known if name in one.aliases), None)

    def program(name: str) -> str | None:
        return f"/bin/{name}" if name in ("claude", "opencode") else None

    monkeypatch.setattr(backends, "profiles", lambda: tuple(known))
    monkeypatch.setattr(backends, "named", named)
    monkeypatch.setattr(backends, "program", program)
    monkeypatch.setattr(hmz.coganchor, "__version__", "1.2.3", raising=False)
    return at


def _front(card: Path) -> dict[str, Any]:
    _, block, _ = card.read_text(encoding="utf-8").split("---\n", 2)
    return yaml.safe_load(block)


def _said(capsys: pytest.CaptureFixture[str]) -> Any:
    return json.loads(capsys.readouterr().out)


def test_the_skill_is_written_for_each_installed_harness(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    claude = home / ".claude/skills/hmz/SKILL.md"
    opencode = home / ".config/opencode/skills/hmz/SKILL.md"

    assert main(["skills", "add"]) == 0

    assert capsys.readouterr().out == (
        f"Installed for claude: {claude}\nInstalled for opencode: {opencode}\n"
    )
    assert not (home / ".codex").exists()
    front = _front(claude)
    assert "hmz" in front.pop("description")
    assert front == {
        "name": "hmz",
        "metadata": {"written-by": "hmz skills add", "hmz-version": "1.2.3"},
    }
    assert claude.read_text(encoding="utf-8") == opencode.read_text(encoding="utf-8")

    assert main(["skills", "add", "--json"]) == 0
    assert _said(capsys) == {
        "version": "1.2.3",
        "written": [
            {"harness": "claude", "path": str(claude), "changed": False},
            {"harness": "opencode", "path": str(opencode), "changed": False},
        ],
    }


def test_the_skill_is_written_for_a_harness_named_and_into_a_folder_given(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    shared = home / ".agents/skills"
    argv = ["skills", "add", "--for", "codex-code", "--dir", str(shared), "--json"]

    assert main(argv) == 0

    assert _said(capsys)["written"] == [
        {
            "harness": "codex",
            "path": str(home / ".codex/skills/hmz/SKILL.md"),
            "changed": True,
        },
        {"harness": None, "path": str(shared / "hmz/SKILL.md"), "changed": True},
    ]
    assert not (home / ".claude").exists()


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (
            ["--for", "nobody"],
            "There is no harness named nobody. `hmz skills list` prints the names.",
        ),
        (
            ["--for", "litellm"],
            (
                "The harness litellm loads no skills from a folder of its own. "
                "Give a folder with `--dir`."
            ),
        ),
    ],
)
def test_a_harness_with_nowhere_to_write_is_refused(
    home: Path, argv: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["skills", "add", *argv]) == 1

    assert capsys.readouterr().err == f"hmz skills add: {message}\n"
    assert list(home.iterdir()) == []


@pytest.mark.parametrize("verb", ["add", "list", "remove"])
def test_a_folder_named_by_nothing_is_no_folder(
    home: Path, verb: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        main(["skills", verb, "--dir", ""])

    assert raised.value.code == tree.UNREAD
    assert "--dir" in capsys.readouterr().err
    assert list(home.iterdir()) == []


def test_a_folder_reached_by_two_names_is_written_once(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (home / ".agents").mkdir()
    (home / ".agents/skills").symlink_to(home / ".codex/skills")
    argv = ["--for", "codex", "--dir", str(home / ".agents/skills"), "--json"]

    assert main(["skills", "add", *argv]) == 0
    (written,) = _said(capsys)["written"]
    assert written["harness"] == "codex"

    assert main(["skills", "remove", "--yes", *argv]) == 0
    assert len(_said(capsys)["removed"]) == 1


def test_adding_with_no_harness_installed_is_refused(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(backends, "program", mock.Mock(return_value=None))

    assert main(["skills", "add", "--json"]) == 1

    assert _said(capsys) == {
        "error": {
            "code": 0,
            "message": "No harness is installed here. Name a harness with `--for` or "
            "a folder with `--dir`.",
        }
    }
    assert list(home.iterdir()) == []


def test_a_skill_hmz_did_not_write_is_neither_replaced_nor_removed(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    theirs = home / ".config/opencode/skills/hmz"
    theirs.mkdir(parents=True)
    (theirs / "SKILL.md").write_text("---\nname: hmz\n---\nmine\n", encoding="utf-8")
    refusal = (
        f"{theirs} holds a skill named hmz that hmz did not write, so it was left as "
        "it is.\n"
    )

    assert main(["skills", "add"]) == 1
    assert capsys.readouterr().err == f"hmz skills add: {refusal}"
    # Refused before anything was written, the harness before it included.
    assert not (home / ".claude").exists()

    assert main(["skills", "remove", "--for", "opencode", "--yes"]) == 1
    assert capsys.readouterr().err == f"hmz skills remove: {refusal}"

    # Unnamed, it is not hmz's to remove, and nothing is.
    assert main(["skills", "remove", "--yes"]) == 0
    assert capsys.readouterr().out == "No hmz skill is installed.\n"
    assert (theirs / "SKILL.md").read_text(encoding="utf-8").endswith("mine\n")


def test_the_list_says_where_each_harness_reads_and_what_is_there(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["skills", "add", "--for", "claude", "--for", "codex"]) == 0
    foreign = home / ".config/opencode/skills/hmz"
    foreign.mkdir(parents=True)
    (foreign / "notes.txt").write_text("mine", encoding="utf-8")
    monkeypatch.setattr(hmz.coganchor, "__version__", "1.3.0", raising=False)
    assert main(["skills", "add", "--for", "claude"]) == 0
    capsys.readouterr()

    assert main(["skills", "list", "--json"]) == 0

    assert _said(capsys) == {
        "version": "1.3.0",
        "harnesses": [
            {
                "harness": "claude",
                "installed": True,
                "directory": str(home / ".claude/skills"),
                "path": str(home / ".claude/skills/hmz/SKILL.md"),
                "state": "current",
                "version": "1.3.0",
            },
            {
                "harness": "codex",
                "installed": False,
                "directory": str(home / ".codex/skills"),
                "path": str(home / ".codex/skills/hmz/SKILL.md"),
                "state": "older",
                "version": "1.2.3",
            },
            {
                "harness": "opencode",
                "installed": True,
                "directory": str(home / ".config/opencode/skills"),
                "path": str(foreign / "SKILL.md"),
                "state": "foreign",
                "version": None,
            },
        ],
    }

    assert main(["skills", "list", "--dir", str(home / "none")]) == 0
    assert capsys.readouterr().out == f"-  {home / 'none'}  Not installed\n"

    # A harness named twice, by whichever of its names, is one harness.
    assert main(["skills", "list", "--for", "codex", "--for", "codex-code"]) == 0
    assert capsys.readouterr().out.count("\n") == 1

    assert main(["skills", "list"]) == 0
    assert capsys.readouterr().out == (
        f"claude                 {home / '.claude/skills'}           Current\n"
        f"codex (not installed)  {home / '.codex/skills'}            Older\n"
        f"opencode               {home / '.config/opencode/skills'}  Not written by hmz\n"
    )

    # A folder harnesses share is listed once the skill is in it, and is nobody's own.
    shared = home / ".agents/skills"
    assert main(["skills", "add", "--dir", str(shared)]) == 0
    capsys.readouterr()
    assert main(["skills", "list"]) == 0
    last = capsys.readouterr().out.splitlines()[-1]
    assert last.split() == ["-", str(shared), "Current"]
    assert main(["skills", "remove", "--yes", "--json"]) == 0
    removed = _said(capsys)["removed"]
    assert {"harness": None, "path": str(shared / "hmz/SKILL.md")} in removed


def test_removing_takes_what_add_wrote_and_leaves_what_is_beside_it(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["skills", "add", "--for", "claude", "--for", "codex"]) == 0
    claude = home / ".claude/skills/hmz"
    codex = home / ".codex/skills/hmz"
    (codex / "notes.txt").write_text("mine", encoding="utf-8")
    capsys.readouterr()

    assert main(["skills", "remove", "--yes", "--json"]) == 0

    assert _said(capsys) == {
        "removed": [
            {"harness": "claude", "path": str(claude / "SKILL.md")},
            {"harness": "codex", "path": str(codex / "SKILL.md")},
        ]
    }
    assert not claude.exists()
    assert (home / ".claude/skills").is_dir()
    assert [one.name for one in codex.iterdir()] == ["notes.txt"]


class _Terminal(io.StringIO):
    """What somebody at a terminal types."""

    def isatty(self) -> bool:
        return True


def test_removing_asks_first(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["skills", "add", "--for", "claude", "--for", "codex"]) == 0
    claude = home / ".claude/skills/hmz"
    codex = home / ".codex/skills/hmz"
    capsys.readouterr()

    # Nobody to ask, and a document to answer with, are both nobody asked.
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert main(["skills", "remove"]) == 1
    assert capsys.readouterr().err == (
        "hmz skills remove: Removing asks first. Run it again with `--yes`.\n"
    )
    monkeypatch.setattr("sys.stdin", _Terminal("n\ny\n"))
    assert main(["skills", "remove", "--json"]) == 1
    assert _said(capsys)["error"]["message"].startswith("Removing asks first.")
    assert claude.exists()

    assert main(["skills", "remove"]) == 0

    said = capsys.readouterr()
    assert said.err == f"Remove {claude}? [y/N] Remove {codex}? [y/N] "
    assert said.out == f"Removed: {codex / 'SKILL.md'}\n"
    assert claude.exists()
    assert not codex.exists()


def _fake(name: str, methods: tuple[str, ...], line: str = "") -> Command:
    return Command(
        name,
        "Open",
        examples=(Example(line, "Search"),) if line else (),
        methods=methods,
        run=lambda _: None,
    )


@pytest.mark.usefixtures("home")
def test_the_skill_says_what_the_commands_declare(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    chat = Command(
        "chat",
        "Back",
        commands=(
            # One that calls the method too, which the command made for it comes before.
            _fake("peek", ("chat.list", "chat.get"), "hmz chat peek"),
            _fake("new", ("chat.start",), "hmz chat new hello"),
            _fake("show", ("chat.get",)),
        ),
    )
    runs = Command("runs", "Close", commands=(_fake("list", ("runs.list",)),))
    held = {"chat": chat, "runs": runs, "help": _fake("help", ()), "skills": SKILLS}
    monkeypatch.setattr(tree, "commands", lambda: held)

    assert main(["skills", "show"]) == 0

    text = capsys.readouterr().out
    assert text.startswith("---\nname: hmz\ndescription: ")
    assert "- `hmz help --json`: " in text
    assert (
        "- `hmz chat COMMAND ...`: Back\n"
        "  - `hmz chat peek`: Open\n"
        "  - `hmz chat new`: Open\n"
        "  - `hmz chat show`: Open\n"
        "- `hmz runs COMMAND ...`: Close\n"
        "  - `hmz runs list`: Open\n"
        "- `hmz help`: Open\n"
        "- `hmz skills COMMAND ...`: "
    ) in text
    assert "  - `2`: the command line could not be read\n" in text
    assert text.count("`--daemon`, never exit with status 3") == 1
    assert (
        "when they refuse: `hmz skills add`, `hmz skills list`, `hmz skills remove`, "
        "`hmz skills show`\n"
    ) in text
    # A job is written where there is a command for each of its steps, and only there.
    assert text.endswith(
        "## Common sequences\n"
        "\n"
        "Each step is a line as the command's own help gives it; replace its values "
        "with your own.\n"
        "\n"
        "### Start a chat and read the answer\n"
        "\n"
        "1. `hmz chat new hello`: Search\n"
        "2. `hmz chat show`: Open\n"
    )
    assert "List the runs" not in text

    monkeypatch.setattr(tree, "commands", lambda: {"skills": SKILLS})
    assert main(["skills", "show"]) == 0
    text = capsys.readouterr().out
    assert "hmz help --json" not in text
    assert "Common sequences" not in text


def test_a_skill_too_long_for_one_file_keeps_its_commands_beside_it(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    many = Command(
        "many", "Back", commands=tuple(_fake(f"n{at}", ()) for at in range(600))
    )
    monkeypatch.setattr(tree, "commands", lambda: {"many": many, "skills": SKILLS})

    assert main(["skills", "show", "--json"]) == 0

    card, reference = _said(capsys)["files"]
    assert (card["name"], reference["name"]) == ("SKILL.md", "reference.md")
    assert card["text"].count("\n") < 100
    assert "[reference.md](reference.md)" in card["text"]
    assert "- `hmz many COMMAND ...`: Back\n" in card["text"]
    assert "hmz many n599" not in card["text"]
    assert "  - `hmz many n599`: Open\n" in reference["text"]

    assert main(["skills", "add", "--for", "claude"]) == 0
    skill = home / ".claude/skills/hmz"
    assert sorted(one.name for one in skill.iterdir()) == ["SKILL.md", "reference.md"]

    # Written again by an hmz of fewer commands, it is one file again; and removed whole.
    monkeypatch.setattr(tree, "commands", lambda: {"skills": SKILLS})
    assert main(["skills", "add", "--for", "claude"]) == 0
    assert [one.name for one in skill.iterdir()] == ["SKILL.md"]
    (skill / "reference.md").write_text("old", encoding="utf-8")
    assert main(["skills", "remove", "--for", "claude", "-y"]) == 0
    assert not skill.exists()
