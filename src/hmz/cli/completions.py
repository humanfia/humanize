"""``hmz help completions`` -- what a shell offers when somebody presses tab after `hmz`.

A completion script is the commands said once more, in a shell's language: which words may
follow which, which options a command takes, which of them take a value and which values. So
it is written from the same declarations the help is (:mod:`hmz.cli.tree`), when it is asked
for, and holds everything it offers: the shell asks `hmz` nothing while somebody types.

Each script is the same three parts. A table says, for every command there is, what may come
next under it, its options, and which of those take a value. A walk reads the words already
typed down that table to the command being written. And what is offered is read off where the
walk ended: the values of an option that was just named, the options where a `-` is being
typed, and otherwise the commands under it, or files where it has none.

A command that reads its own line (`hmz exec`, `hmz web`) is offered by name and files after
it: what it takes is not written anywhere a script can be made from.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from hmz import cli
from hmz.words import t

from . import tree

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .tree import Arg, Command

__all__ = ["SHELLS", "script"]

#: The shells a script can be written for.
SHELLS: Final = ("bash", "zsh", "fish")

#: What `hmz` itself takes before any command.
_TOP: Final = ("-h", "--help", "--version")


@dataclass(frozen=True)
class _Option:
    """One option of a command, as a shell is told of it."""

    flags: tuple[str, ...]
    says: str = ""
    valued: bool = False
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Node:
    """One place a line can have got to: the words of a command, and what may follow."""

    path: str
    """The words after `hmz`, a space between; empty for `hmz` itself."""
    under: tuple[tuple[str, str], ...]
    """Each word that may come next and what it is: a command, or a value it takes by place."""
    options: tuple[_Option, ...]
    group: bool = False
    """Whether what may follow is the commands under it."""


def _option(arg: Arg) -> _Option:
    return _Option(arg.flags, t(arg.says), valued=not arg.switch, choices=arg.choices)


_HELP: Final = _Option(("-h", "--help"), t("show this help and exit"))


def _declared(path: tuple[str, ...], command: Command) -> Iterator[_Node]:
    """A declared command and every one under it."""
    if command.commands:
        under = tuple((one.name, t(one.summary)) for one in command.commands)
        yield _Node(" ".join(path), under, (_HELP,), group=True)
        for one in command.commands:
            yield from _declared((*path, one.name), one)
        return
    if command.passes is not None:
        yield _Node(" ".join(path), (), ())
        return
    taken = tree.taken(command)
    placed = tuple(
        (choice, "") for arg in taken if arg.positional for choice in arg.choices
    )
    named = tuple(_option(arg) for arg in taken if not arg.positional)
    yield _Node(" ".join(path), placed, (*named, _HELP))


def _nodes() -> list[_Node]:
    """Every place a line of `hmz` can have got to, `hmz` itself first."""
    declared = tree.commands()
    top = tuple(cli.summaries().items())
    found = {"": _Node("", top, tuple(_Option((flag,)) for flag in _TOP))}
    for name, _ in top:
        if name not in cli.COMMANDS:
            for node in _declared((name,), declared[name]):
                found[node.path] = node
        else:
            found[name] = _Node(name, (), ())
    if "help" in found:
        # `hmz help` takes the words of any command, so what follows it is what follows
        # `hmz`, one word further in -- and the one word of its own, with the shells after.
        asked = found["help"].options
        # Only the words of a command: what a command takes by place is not asked about.
        mirrored = {
            f"help {path}": _Node(
                f"help {path}", node.under if node.group else (), asked
            )
            for path, node in found.items()
            if path and path.split(" ")[0] != "help"
        }
        mirrored["help"] = _Node("help", (*top, ("completions", "")), asked)
        mirrored["help completions"] = _Node(
            "help completions", tuple((shell, "") for shell in SHELLS), asked
        )
        for shell in SHELLS:
            mirrored[f"help completions {shell}"] = _Node(
                f"help completions {shell}", (), asked
            )
        found.update(mirrored)
    return list(found.values())


def _flags(node: _Node, *, valued: bool = False) -> list[str]:
    return [
        flag
        for option in node.options
        if option.valued or not valued
        for flag in option.flags
    ]


def _choices(nodes: list[_Node]) -> Iterator[tuple[str, tuple[str, ...]]]:
    """Each option that takes only some values, as the words up to it, and the values."""
    for node in nodes:
        for option in node.options:
            if option.choices:
                for flag in option.flags:
                    yield f"{node.path} {flag}".lstrip(), option.choices


_BASH: Final = """\
# bash completion for hmz. Written by `hmz help completions bash`; load it with
#   eval "$(hmz help completions bash)"
# or keep it where bash-completion looks, as `hmz help --help` shows.

_hmz_node() {
    case "$1" in
%(nodes)s
        *) return 1 ;;
    esac
}

_hmz_choices() {
    case "$1" in
%(choices)s
        *) ;;
    esac
}

_hmz() {
    local cur="${COMP_WORDS[COMP_CWORD]}" at="" next word takes="" i
    local under options valued
    _hmz_node ""
    for ((i = 1; i < COMP_CWORD; i++)); do
        word="${COMP_WORDS[i]}"
        if [[ -n "$takes" ]]; then
            takes=""
        elif [[ "$word" == -* ]]; then
            case " $valued " in *" $word "*) takes="$word" ;; esac
        else
            next="${at:+$at }$word"
            if _hmz_node "$next"; then at="$next"; fi
        fi
    done
    if [[ -n "$takes" ]]; then
        COMPREPLY=($(compgen -W "$(_hmz_choices "${at:+$at }$takes")" -- "$cur"))
    elif [[ "$cur" == -* ]]; then
        COMPREPLY=($(compgen -W "$options" -- "$cur"))
    else
        COMPREPLY=($(compgen -W "$under" -- "$cur"))
    fi
}

complete -o default -F _hmz hmz
"""

_ZSH: Final = """\
#compdef hmz
# zsh completion for hmz. Written by `hmz help completions zsh`; load it with
#   source <(hmz help completions zsh)
# after `compinit`, or keep it as `_hmz` in a directory of `fpath`.

_hmz_node() {
    case "$1" in
%(nodes)s
        *) return 1 ;;
    esac
}

_hmz_choices() {
    case "$1" in
%(choices)s
        *) reply=() ;;
    esac
}

_hmz() {
    local at="" next word takes="" i
    local -a under options valued reply
    _hmz_node ""
    for ((i = 2; i < CURRENT; i++)); do
        word="${words[i]}"
        if [[ -n "$takes" ]]; then
            takes=""
        elif [[ "$word" == -* ]]; then
            if (( ${valued[(Ie)$word]} )); then takes="$word"; fi
        else
            next="${at:+$at }$word"
            if _hmz_node "$next"; then at="$next"; fi
        fi
    done
    if [[ -n "$takes" ]]; then
        _hmz_choices "${at:+$at }$takes"
        if (( ${#reply} )); then compadd -- $reply; else _files; fi
    elif [[ "${words[CURRENT]}" == -* ]]; then
        _describe -o option options
    elif (( ${#under} )); then
        _describe command under
    else
        _files
    fi
}

if [[ "${funcstack[1]}" == _hmz ]]; then
    _hmz "$@"
else
    compdef _hmz hmz
fi
"""

_FISH: Final = """\
# fish completion for hmz. Written by `hmz help completions fish`; keep it as
# ~/.config/fish/completions/hmz.fish, or load it with
#   hmz help completions fish | source

function __hmz_at
    set -l nodes %(paths)s
    set -l valued %(valued)s
    set -l words (commandline -opc)
    set -l at ''
    set -l takes ''
    for word in $words[2..-1]
        if test -n "$takes"
            set takes ''
        else if string match -q -- '-*' $word
            if contains -- (string trim "$at $word") $valued
                set takes $word
            end
        else
            set -l next (string trim "$at $word")
            if contains -- "$next" $nodes
                set at $next
            end
        end
    end
    test "$at" = "$argv[1]"
end

%(lines)s
"""


def _quoted(words: list[str]) -> str:
    """Words as one shell word that reads back as them with spaces between."""
    return shlex.quote(" ".join(words))


def _bash(nodes: list[_Node]) -> str:
    cases = [
        f"        {shlex.quote(node.path)}) "
        f"under={_quoted([name for name, _ in node.under])}; "
        f"options={_quoted(_flags(node))}; "
        f"valued={_quoted(_flags(node, valued=True))} ;;"
        for node in nodes
    ]
    choices = [
        f"        {shlex.quote(at)}) echo {_quoted(list(values))} ;;"
        for at, values in _choices(nodes)
    ]
    return _BASH % {"nodes": "\n".join(cases), "choices": "\n".join(choices)}


def _described(name: str, says: str) -> str:
    """One thing zsh offers, as `_describe` reads it: the word, a colon, what it is."""
    word = name.replace("\\", "\\\\").replace(":", "\\:")
    return shlex.quote(f"{word}:{says}" if says else word)


def _zsh(nodes: list[_Node]) -> str:
    def listed(words: list[str]) -> str:
        return "(" + " ".join(words) + ")"

    cases = [
        f"        {shlex.quote(node.path)}) "
        f"under={listed([_described(name, says) for name, says in node.under])}; "
        "options="
        + listed(
            [
                _described(flag, option.says)
                for option in node.options
                for flag in option.flags
            ]
        )
        + f"; valued={listed([shlex.quote(flag) for flag in _flags(node, valued=True)])} ;;"
        for node in nodes
    ]
    choices = [
        f"        {shlex.quote(at)}) reply={listed([shlex.quote(one) for one in values])} ;;"
        for at, values in _choices(nodes)
    ]
    return _ZSH % {"nodes": "\n".join(cases), "choices": "\n".join(choices)}


def _fished(text: str) -> str:
    """A word as fish reads it back: in single quotes, which escape only themselves."""
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _fish(nodes: list[_Node]) -> str:
    lines: list[str] = []
    for node in nodes:
        at = f"complete -c hmz -n {_fished(f'__hmz_at {_fished(node.path)}')}"
        for name, says in node.under:
            described = f" -d {_fished(says)}" if says else ""
            lines.append(f"{at} -f -a {_fished(name)}{described}")
        for option in node.options:
            named = "".join(
                f" -l {_fished(flag[2:])}"
                if flag.startswith("--")
                else f" -s {_fished(flag[1:])}"
                for flag in option.flags
            )
            takes = ""
            if option.choices:
                takes = f" -x -a {_fished(' '.join(option.choices))}"
            elif option.valued:
                takes = " -r"
            described = f" -d {_fished(option.says)}" if option.says else ""
            lines.append(f"{at}{named}{takes}{described}")
    return _FISH % {
        "paths": " ".join(_fished(node.path) for node in nodes),
        "valued": " ".join(
            _fished(f"{node.path} {flag}".lstrip())
            for node in nodes
            for flag in _flags(node, valued=True)
        )
        or "''",
        "lines": "\n".join(lines),
    }


def script(shell: str) -> str:
    """The completion script of `hmz` for a shell, written from the commands there are.

    Args:
      shell: One of `SHELLS`.

    Returns:
      The script, to be sourced by that shell or kept where it loads completions from.

    Raises:
      KeyError: For a shell that is none of `SHELLS`.
    """
    return {"bash": _bash, "zsh": _zsh, "fish": _fish}[shell](_nodes())
