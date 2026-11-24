"""`hmz.cli.completions`: a shell told which words may follow which, from the declarations."""

from __future__ import annotations

import pytest

import hmz.cli
from hmz.cli import completions, tree
from hmz.cli.commands import help as helping
from hmz.cli.tree import Arg, Call, Command


def _runs(_: Call) -> None:
    """Nothing: only what the command takes is read here."""


GREET = Command(
    "greet",
    "Open",
    commands=(
        Command(
            "say",
            'it\'s "Back": $HOME',
            args=(
                Arg(("who",), "Close", choices=("you", "them")),
                Arg(("-t", "--to"), "Search", metavar="WHO", many=True),
                Arg(("--kind",), "Open", choices=("a", "b")),
            ),
            run=_runs,
        ),
    ),
)


@pytest.fixture(autouse=True)
def commands(monkeypatch: pytest.MonkeyPatch) -> None:
    """One group of declared commands, `hmz help`, and one that reads its own line."""
    declared = {"greet": GREET, "help": helping.COMMANDS[0]}
    monkeypatch.setattr(tree, "commands", lambda: declared)
    monkeypatch.setattr(hmz.cli, "COMMANDS", {"old": (hmz.cli.main, "an old command")})


def test_the_shells_are_these_and_no_other_has_a_script() -> None:
    assert completions.SHELLS == ("bash", "zsh", "fish")
    with pytest.raises(KeyError):
        completions.script("tcsh")


def test_bash_is_told_what_follows_each_command_and_which_options_take_a_value() -> (
    None
):
    script = completions.script("bash")

    assert (
        "        '') under='old greet help'; options='-h --help --version'; valued='' ;;\n"
        in script
    )
    assert "        greet) under=say; options='-h --help'; valued='' ;;\n" in script
    assert (
        "        'greet say') under='you them'; "
        "options='-t --to --kind --json --daemon --no-color -h --help'; "
        "valued='-t --to --kind --daemon' ;;\n"
    ) in script
    assert "        old) under=''; options=''; valued='' ;;\n" in script
    assert "        'greet say --kind') echo 'a b' ;;\n" in script
    assert script.endswith("complete -o default -F _hmz hmz\n")


def test_what_follows_hmz_help_is_what_follows_hmz_and_the_shells() -> None:
    script = completions.script("bash")

    asked = "options='--all --json --no-color -h --help'; valued=''"
    assert f"        help) under='old greet help completions'; {asked} ;;\n" in script
    assert f"        'help greet') under=say; {asked} ;;\n" in script
    # Only the words of a command follow: what it takes by place is not asked about.
    assert f"        'help greet say') under=''; {asked} ;;\n" in script
    assert f"        'help completions') under='bash zsh fish'; {asked} ;;\n" in script
    assert f"        'help completions zsh') under=''; {asked} ;;\n" in script
    assert "'help help" not in script


def test_zsh_is_told_what_each_word_is_quoted_as_a_shell_reads_it() -> None:
    script = completions.script("zsh")

    assert script.startswith("#compdef hmz\n")
    assert "'') under=('old:an old command' greet:Open " in script
    # What a word is may hold anything a shell would read: it is one quoted word.
    assert """greet) under=('say:it'"'"'s "Back": $HOME'); """ in script
    assert " --kind:Open " in script
    assert "valued=(-t --to --kind --daemon) ;;" in script
    assert "        'greet say --kind') reply=(a b) ;;\n" in script
    assert "compdef _hmz hmz" in script


def test_fish_is_told_each_word_and_option_under_the_command_it_follows() -> None:
    script = completions.script("fish")

    assert "set -l nodes '' 'old' 'greet' 'greet say' 'help' " in script
    assert (
        "set -l valued 'greet say -t' 'greet say --to' 'greet say --kind' 'greet say --daemon'\n"
        in script
    )
    assert (
        "complete -c hmz -n '__hmz_at \\'\\'' -f -a 'old' -d 'an old command'\n"
    ) in script
    assert (
        "complete -c hmz -n '__hmz_at \\'greet\\'' -f -a 'say' "
        "-d 'it\\'s \"Back\": $HOME'\n"
    ) in script
    assert (
        "complete -c hmz -n '__hmz_at \\'greet say\\'' -s 't' -l 'to' -r -d 'Search'\n"
    ) in script
    assert (
        "complete -c hmz -n '__hmz_at \\'greet say\\'' -l 'kind' -x -a 'a b' -d 'Open'\n"
    ) in script
    assert "complete -c hmz -n '__hmz_at \\'greet say\\'' -f -a 'you'\n" in script
