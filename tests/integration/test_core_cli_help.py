"""What every declared command says of itself is enough to use it, and is true.

A command's help is the only thing a person or an agent is given to use it by, so each
declaration is held to what makes one usable: a summary that reads in a listing, texts short
enough to read (Section 3.3.2 of cli.md), a line to type that its own parser takes, what it
prints and every field of its JSON, and nothing named that does not exist -- no command to
see, no method of the daemon. These are asked of every command there is, whoever wrote it,
and of the top of the command line that lists them.
"""

from __future__ import annotations

import dataclasses
import json
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from hmz import cli
from hmz.cli import completions, tree
from hmz.cli.commands import help as helping

if TYPE_CHECKING:
    from collections.abc import Iterator

    from hmz.cli.tree import Command

ROOT = Path(__file__).resolve().parents[2]

#: The most words any one text of a help may have (Section 3.3.2 of cli.md).
WORDS = 30

#: What ends the part of an example line that `hmz` reads: the shell takes it from there.
SHELL = frozenset("|&;<>()")


def _under(
    path: tuple[str, ...], command: Command
) -> Iterator[tuple[tuple[str, ...], Command]]:
    yield path, command
    for one in command.commands:
        yield from _under((*path, one.name), one)


#: Every declared command there is, the groups among them, by the words that name it.
EVERY = {
    " ".join(path): (path, command)
    for name, top in tree.commands().items()
    for path, command in _under((name,), top)
    if command.passes is None
}

#: Those that take a line of their own.
LEAVES = sorted(name for name, (_, command) in EVERY.items() if not command.commands)


def _own(command: Command) -> list[str]:
    """The texts a command says itself, without those of the commands under it."""
    return list(dataclasses.replace(command, commands=()).texts())


def _typed(line: str) -> list[str]:
    """The words of an example line that `hmz` is given, up to where the shell takes over."""
    lexer = shlex.shlex(line, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    words: list[str] = []
    for word in lexer:
        if word and set(word) <= SHELL:
            break
        words.append(word)
    return words


def test_there_are_commands_to_ask_this_of() -> None:
    assert "devices list" in LEAVES
    assert "help" in LEAVES


@pytest.mark.parametrize("name", sorted(EVERY))
def test_a_summary_reads_in_a_listing(name: str) -> None:
    _, command = EVERY[name]

    assert command.summary
    assert not command.summary[0].isupper(), "a summary starts lower-case"
    assert not command.summary.endswith("."), "a summary has no full stop"


@pytest.mark.parametrize("name", sorted(EVERY))
def test_every_text_is_at_most_thirty_words(name: str) -> None:
    _, command = EVERY[name]

    long = [text for text in _own(command) if len(text.split()) > WORDS]

    assert not long


@pytest.mark.parametrize("name", LEAVES)
def test_an_example_is_a_line_its_own_parser_takes(name: str) -> None:
    path, command = EVERY[name]

    assert command.examples, "a command has at least one example"
    for example in command.examples:
        assert example.line.startswith("hmz "), example.line
        words = _typed(example.line)
        named, found, rest = tree.named(words[1:])
        assert named == path, f"{example.line!r} is an example of another command"
        try:
            tree.parser(named, found).parse_args(rest)
        except SystemExit:
            pytest.fail(f"{example.line!r} is not a line `hmz {name}` takes")


@pytest.mark.parametrize("name", LEAVES)
def test_what_a_command_prints_is_said_and_its_json_has_fields(name: str) -> None:
    _, command = EVERY[name]

    assert command.prints, "what it prints without `--json` is said"
    assert command.output, "its `--json` document has at least one field"
    fields = [one.name for one in command.output]
    assert len(fields) == len(set(fields)), "a field is stated once"


@pytest.mark.parametrize("name", LEAVES)
def test_a_command_to_see_is_a_command_there_is(name: str) -> None:
    _, command = EVERY[name]

    for one in command.see:
        assert one in EVERY, f"`hmz {name}` says to see `hmz {one}`, which is not there"


@pytest.mark.parametrize("name", LEAVES)
def test_a_daemon_method_is_one_of_the_protocol(name: str) -> None:
    _, command = EVERY[name]
    kept = json.loads((ROOT / "protocol/openrpc.json").read_text(encoding="utf-8"))
    methods = {one["name"] for one in kept["methods"]}

    assert set(command.methods) <= methods
    if command.local:
        assert not command.methods, "a command that asks no daemon calls no method"


@pytest.mark.parametrize("name", LEAVES)
def test_no_two_arguments_share_a_flag_or_a_name(name: str) -> None:
    _, command = EVERY[name]
    taken = tree.taken(command)

    flags = [flag for arg in taken for flag in arg.flags] + ["-h", "--help"]
    assert len(flags) == len(set(flags))
    names = [arg.name for arg in taken]
    assert len(names) == len(set(names))


def test_the_top_lists_every_command_there_is_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out

    listed = [name for _, held in helping.grouped() for name, _ in held]
    assert sorted(listed) == sorted({*cli.COMMANDS, *tree.commands()})
    for name, summary in cli.summaries().items():
        assert out.count(f"\n  {name} ") == 1, name
        assert len(summary.split()) <= WORDS
    assert max(len(line) for line in out.splitlines()) <= tree.WIDTH


def test_the_whole_command_line_is_one_document_an_agent_can_load(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["help", "--json"]) == 0
    said = json.loads(capsys.readouterr().out)

    def named(commands: list[dict[str, Any]]) -> Iterator[str]:
        for one in commands:
            yield str(one["command"]).removeprefix("hmz ")
            yield from named(one.get("commands", []))

    found = set(named(said["commands"]))
    assert set(EVERY) <= found
    assert set(cli.COMMANDS) <= found
    assert [one for group in said["groups"] for one in group["commands"]] == [
        str(one["command"]).removeprefix("hmz ") for one in said["commands"]
    ]


def test_all_is_every_help_in_one_stream(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["help", "--all"]) == 0
    out = capsys.readouterr().out

    for name, (path, command) in EVERY.items():
        assert tree.helps(path, command) in out, name
    for name in cli.COMMANDS:
        assert f"usage: hmz {name}" in out, name


def _completed(script: str, *line: str) -> list[str]:
    """What bash offers for a line whose last word is being typed, with a script loaded."""
    asks = (
        'eval "$1"; shift; COMP_WORDS=("$@"); COMP_CWORD=$((${#COMP_WORDS[@]} - 1)); '
        '_hmz; printf "%s\\n" "${COMPREPLY[@]}"'
    )
    done = subprocess.run(
        ["bash", "-c", asks, "bash", script, *line],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert done.stderr == ""
    return done.stdout.split()


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_bash_completes_commands_options_and_choices_from_the_script() -> None:
    script = completions.script("bash")

    assert _completed(script, "hmz", "dev") == ["devices"]
    assert _completed(script, "hmz", "devices", "") == ["list", "revoke", "pair"]
    assert _completed(script, "hmz", "devices", "pair", "--s") == ["--seconds"]
    # The value of an option is not a command: what follows it is still under `pair`.
    assert _completed(script, "hmz", "devices", "pair", "--seconds", "5", "--r") == [
        "--route"
    ]
    assert _completed(script, "hmz", "help", "devices", "re") == ["revoke"]
    assert _completed(script, "hmz", "help", "completions", "") == [
        "bash",
        "zsh",
        "fish",
    ]
    assert _completed(script, "hmz", "help", "completions", "zsh", "") == []
    assert sorted(_completed(script, "hmz", "")) == sorted(cli.summaries())
    assert _completed(script, "hmz", "--v") == ["--version"]


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_a_completion_script_is_one_its_shell_can_read(
    shell: str, tmp_path: Path
) -> None:
    if shutil.which(shell) is None:
        pytest.skip(f"needs {shell}")
    script = tmp_path / f"hmz.{shell}"
    script.write_text(completions.script(shell), encoding="utf-8")

    done = subprocess.run(
        [shell, "-n", str(script)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert (done.returncode, done.stderr) == (0, "")
