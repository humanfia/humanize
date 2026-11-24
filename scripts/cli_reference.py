"""Writes the declared commands into the CLI reference: `docs/reference/cli.md`.

A declared command says everything about itself once (`hmz.cli.tree`), and its page of the
reference is one more reading of that: what it takes, lines to type, what it prints, the fields
of its `--json`. So that part of the reference is written from the declarations rather than
beside them, between two marker comments, and so is the list of every command there is, under
what each is about, as `hmz --help` lists them. Everything outside the markers -- the commands
that read their own line, the conventions -- stays as somebody wrote it.

    uv run python scripts/cli_reference.py            # rewrite the part between the markers
    uv run python scripts/cli_reference.py --check    # exit 1 where it is stale

`tests/integration/test_core_cli_reference.py` holds the page to what this writes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from hmz.cli import tree
from hmz.cli.commands import help as top
from hmz.words import t

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs/reference/cli.md"

#: Each part written here: the comment it begins after, and the one it ends before.
LISTED = (
    (
        "<!-- command list: written by scripts/cli_reference.py from the commands there "
        "are; do not edit by hand -->"
    ),
    "<!-- command list: end -->",
)
DECLARED = (
    (
        "<!-- declared commands: written by scripts/cli_reference.py from "
        "src/hmz/cli/commands; do not edit by hand -->"
    ),
    "<!-- declared commands: end -->",
)


def _cell(text: str) -> str:
    """A text as one cell of a table, or a line of prose: no bar, and no tag."""
    return text.replace("|", "\\|").replace("<", "&lt;")


def _sentence(text: str) -> str:
    """A summary as a sentence: a capital first, a full stop last."""
    said = text[:1].upper() + text[1:]
    return said if said.endswith((".", "?", "!")) else f"{said}."


def _table(head: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    return [
        "| " + " | ".join(head) + " |",
        "| " + " | ".join("---" for _ in head) + " |",
        *("| " + " | ".join(_cell(cell) for cell in row) + " |" for row in rows),
        "",
    ]


def _leaves(said: dict[str, Any]) -> list[dict[str, Any]]:
    """Every command under one that takes a line of its own, itself where it is one."""
    if "commands" not in said:
        return [said]
    return [leaf for under in said["commands"] for leaf in _leaves(under)]


def _argument(one: dict[str, Any]) -> tuple[str, str]:
    notes: list[str] = []
    if one["choices"]:
        notes.append("One of " + ", ".join(f"`{choice}`" for choice in one["choices"]))
    if one["default"] not in (None, False, "", [], ()):
        notes.append(f"Default `{one['default']}`")
    if one["repeatable"] and not one["positional"]:
        notes.append("May be given more than once")
    said = _sentence(one["description"])
    return f"`{one['name']}`", " ".join([said, *(f"{note}." for note in notes)])


def _leaf(said: dict[str, Any]) -> list[str]:
    """One command: what it does, takes, is typed as, prints and ends with."""
    does = said["description"]
    if does == said["summary"]:
        does = _sentence(does)
    out = [f"### {said['command']}", "", _cell(does), ""]
    out += ["```text", said["usage"], "```", ""]
    shared = {flag for arg in tree.COMMON for flag in arg.flags}
    taken = {flag for one in said["arguments"] for flag in one["flags"]}
    own = [one for one in said["arguments"] if not set(one["flags"]) & shared]
    if own:
        out += _table(
            ("Argument or option", "What it is"), [_argument(one) for one in own]
        )
    missing = sorted(shared - taken)
    if missing:
        names = ", ".join(f"`{name}`" for name in missing)
        out += [f"Asks no daemon, and takes no {names}.", ""]
    if said["examples"]:
        out += _table(
            ("Example", "What it does"),
            [(f"`{one['line']}`", _sentence(one["does"])) for one in said["examples"]],
        )
    if said["prints"]:
        out += [_cell(said["prints"]), ""]
    if said["json"]:
        out += _table(
            ("`--json` field", "Type", "What it holds"),
            [
                (f"`{one['field']}`", f"`{one['type']}`", _sentence(one["description"]))
                for one in said["json"]
            ],
        )
    return out


def _extra(said: dict[str, Any]) -> list[str]:
    """The statuses a command ends with beyond those every command does.

    One of every command's that this command says more of is its own too: what a refusal is
    where it asks first, what an interrupt leaves going where it follows something.
    """
    common = {str(one.code): t(one.says) for one in tree.EXITS}
    # Said once for every command that asks no daemon, where the page says what one is.
    local = t(tree.LOCALLY.says)
    extra = [
        (f"`{code}`", _sentence(means))
        for code, means in said["exit_status"].items()
        if means not in (common.get(code), local)
    ]
    return _table(("Status", "Meaning"), extra) if extra else []


def section() -> str:
    """The declared commands as the reference writes them, a heading a command."""
    out: list[str] = []
    for name, command in sorted(tree.commands().items()):
        if command.passes is not None:
            continue
        said = tree.described([name], command)
        leaves = _leaves(said)
        if leaves == [said]:
            out += [f"## hmz {name}", ""]
        else:
            out += [f"## hmz {name}", "", _cell(said["description"]), ""]
            out += ["```text", *(leaf["usage"] for leaf in leaves), "```", ""]
        for leaf in leaves:
            body = _leaf(leaf)
            # A command that is its own group is said under the one heading.
            out += body[2:] if leaves == [said] else body
            out += _extra(leaf)
            if leaf["daemon_methods"]:
                calls = ", ".join(f"`{method}`" for method in leaf["daemon_methods"])
                out += [f"Daemon methods: {calls}.", ""]
    return "\n".join(out).rstrip("\n") + "\n"


def listing() -> str:
    """Every command there is with its summary, under what it is about."""
    rows = [
        (title if at == 0 else "", f"`{name}`", _sentence(said))
        for title, held in top.grouped()
        for at, (name, said) in enumerate(held)
    ]
    return "\n".join(_table(("About", "Command", "What it does"), rows))


def _between(page: str, markers: tuple[str, str], body: str) -> str:
    begin, end = markers
    before, found, rest = page.partition(begin)
    _, ended, after = rest.partition(end)
    if not found or not ended:
        raise SystemExit(f"{PAGE}: needs the two markers\n{begin}\n{end}")
    return f"{before}{begin}\n\n{body}\n{end}{after}"


def written() -> str:
    """The whole page, with what is between each pair of markers written anew.

    Raises:
      SystemExit: If the page has not both markers of a pair, in order.
    """
    page = PAGE.read_text(encoding="utf-8")
    page = _between(page, LISTED, listing())
    return _between(page, DECLARED, section())


def main(argv: list[str]) -> int:
    """Rewrites the page, or with `--check` says whether it would change."""
    page = written()
    if page == PAGE.read_text(encoding="utf-8"):
        return 0
    if "--check" in argv:
        print(
            f"{PAGE.relative_to(ROOT)} is stale: "
            "run `uv run python scripts/cli_reference.py`",
            file=sys.stderr,
        )
        return 1
    PAGE.write_text(page, encoding="utf-8")
    print(f"{PAGE.relative_to(ROOT)}: written")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
