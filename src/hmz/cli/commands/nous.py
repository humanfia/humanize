"""`hmz nous`: every nous a daemon knows, scanned, written, renamed and cleared."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any

from hmz.cli.tree import Arg, Command, Example, Field, Unread, table
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hmz.cli.tree import Call
    from hmz.sdk.families.nous import Book, Graph

__all__ = ["COMMANDS"]


def _document(book: Book) -> dict[str, Any]:
    """What a daemon answers of its nous, less what only a scan answers."""
    return {name: value for name, value in book.said.items() if name != "failed"}


def _chain(graph: Graph | None) -> str:
    """A graph as a cell of text: the nous of a chain in turn, anything else as JSON."""
    if graph is None:
        return ""
    at, seen, chain = graph.start, set[str](), list[str]()
    nodes = {one.id: one for one in graph.nodes}
    while at in nodes and at not in seen:
        one = nodes[at]
        if not one.use or set(one.on) - {"*"}:
            break
        seen.add(at)
        chain.append(one.use)
        at = one.on.get("*", "")
    if at or len(seen) != len(nodes):
        return json.dumps(graph.sent(), ensure_ascii=False, separators=(",", ":"))
    return ",".join(chain)


def _list(call: Call) -> None:
    book = call.client.nous.list()
    if call.concrete:
        lines = list(book.concrete)
    else:
        lines = table(
            [
                [
                    one.name,
                    t("Virtual") if one.virtual else t("Concrete"),
                    t("{n} more goes, {policy}", n=one.tries, policy=one.policy),
                    t("at most {time}", time=f"{one.timeout:g}s")
                    if one.timeout
                    else t("no limit"),
                    _chain(one.graph) or "-",
                    _chain(one.then) or t("nowhere"),
                ]
                for one in book.nous
            ]
        )
    call.answers(_document(book), lines)


def _scan(call: Call) -> None:
    book = call.client.nous.scan()
    harnesses = {one.partition("/")[0].partition("@")[0] for one in book.concrete}
    call.answers(
        {
            **_document(book),
            "failed": [
                {"cli": one.cli, "account": one.account, "why": one.why}
                for one in book.failed
            ],
        },
        [
            t(
                "{n} concrete nous of {m} harnesses.",
                n=len(book.concrete),
                m=len(harnesses),
            )
        ],
    )
    if not call.json:
        for one in book.failed:
            harness = f"{one.cli}@{one.account}" if one.account else one.cli
            said = t("{harness} would not answer: {why}", harness=harness, why=one.why)
            print(said, file=sys.stderr)


def _graph(words: Sequence[str]) -> Any:
    """A graph as a line writes one: nous tried in turn, or one word of JSON.

    Raises:
      Unread: If a word written as JSON is not JSON.
    """
    if len(words) == 1 and words[0][:1] in ("{", "[", '"'):
        try:
            return json.loads(words[0])
        except ValueError:
            raise Unread(t("This is not valid JSON.")) from None
    names = [name for word in words for name in word.split(",") if name]
    return names[0] if len(names) == 1 else names


def _set(call: Call) -> int | None:
    """Writes one nous, what the line does not say of it staying as it was written."""
    nous = call.client.nous
    was = nous.list().entry(call.name)
    graph = _graph(call.graph) if call.graph else was and was.graph
    then = _graph(call.then) if call.then else was and was.then
    book = nous.set(
        call.name,
        tries=call.tries if call.tries is not None else was and was.tries,
        policy=call.policy or (was.policy if was else None),
        timeout=call.timeout if call.timeout is not None else was and was.timeout,
        graph=graph or None,
        then=None if call.no_then else then or None,
    )
    call.answers(_document(book), [t("Saved.")])
    return None


def _rename(call: Call) -> None:
    book = call.client.nous.rename(call.name, call.to)
    call.answers(_document(book), [t("Renamed")])


def _clear(call: Call) -> None:
    book = call.client.nous.clear(call.name)
    call.answers(_document(book), [t("Removed")])


NOUS = (
    Field("nous", "list", "every nous that has something written of it"),
    Field(
        "nous[].name",
        "string",
        "the nous: `HARNESS[@ACCOUNT]/MODEL[:EFFORT]` for a concrete one, a "
        "name for a virtual one",
    ),
    Field(
        "nous[].virtual",
        "boolean",
        "whether it is a virtual nous, a name for a graph of other nous",
    ),
    Field(
        "nous[].tries", "integer", "how many more goes a turn that fails there is given"
    ),
    Field(
        "nous[].policy", "string", "how long is waited between tries, one of `policies`"
    ),
    Field("nous[].timeout", "number", "the limit of a turn in seconds, 0 for no limit"),
    Field(
        "nous[].graph",
        "object|null",
        "the graph a virtual nous stands for, null for a concrete nous",
    ),
    Field("nous[].graph.start", "string", "id of the node a turn starts at"),
    Field(
        "nous[].graph.nodes",
        "list",
        "the nodes, each `id`, `use` (a nous) or `balance` (a strategy) with "
        "`among` (each `nous` and `weight`) and `spread`, and `on` (fault to "
        "node id, `*` for any other)",
    ),
    Field(
        "nous[].then",
        "object|null",
        "the graph a turn goes to once its tries are spent, in the same "
        "shape, or null for nowhere",
    ),
    Field(
        "policies", "list", "the ways of waiting between tries, each `name` and `about`"
    ),
    Field("default", "string", "the policy used where none is given"),
    Field(
        "strategies",
        "list",
        "the ways a balance node picks among its members, each `name` and `about`",
    ),
    Field(
        "faults",
        "list",
        "every fault an edge of a graph can be for, and `*` for any other",
    ),
    Field(
        "concrete",
        "list",
        "every concrete nous the installed harnesses and the accounts run, "
        "without an effort",
    ),
    Field("scanning", "boolean", "whether a scan of the harnesses is going on"),
)

_NAME = Arg(("name",), "the nous, as `hmz nous list` prints it")

COMMANDS = (
    Command(
        "nous",
        "list, scan and write nous: models, tries and fallbacks",
        says="A concrete nous is a model of a harness, written "
        "`HARNESS[@ACCOUNT]/MODEL[:EFFORT]`. A virtual nous is a name for "
        "a graph of other nous: a turn that fails there is tried again, "
        "on the same model or on another. An agent is given either with "
        "`-a`.",
        commands=(
            Command(
                "list",
                "list the nous written, or every concrete nous",
                args=(
                    Arg(
                        ("--concrete",),
                        "print every concrete nous the harnesses run instead, one "
                        "per line",
                    ),
                ),
                examples=(
                    Example(
                        "hmz nous list",
                        "list every nous that has tries, a limit or a graph written",
                    ),
                    Example(
                        "hmz nous list --concrete",
                        "list every model an agent can be given",
                    ),
                    Example(
                        "hmz nous list --json | jq -r '.policies[].name'",
                        "print the names of the ways of waiting with jq",
                    ),
                ),
                prints="One line per nous written: name, `Virtual` or "
                "`Concrete`, tries and policy, limit, graph, and where a "
                "turn goes once its tries are spent. A graph that is a "
                "chain is printed as its nous separated by commas, any "
                "other as JSON.",
                output=NOUS,
                methods=("nous.list",),
                see=("nous scan", "nous set"),
                run=_list,
            ),
            Command(
                "scan",
                "ask every installed harness which models it runs",
                says="Asks every harness installed on the daemon's machine "
                "which models it runs, as the machine's own sign-in and "
                "as each account. This starts each harness and can take a "
                "minute. A harness that does not answer is reported and "
                "does not fail the command.",
                examples=(
                    Example(
                        "hmz nous scan",
                        "ask every harness what it runs and print how many "
                        "concrete nous were found",
                    ),
                    Example(
                        "hmz nous scan --json | jq '.failed'",
                        "print the harnesses that would not answer, with jq",
                    ),
                ),
                prints="How many concrete nous were found, on standard output; "
                "one line per harness that would not answer, on standard "
                "error.",
                output=(
                    *NOUS,
                    Field("failed", "list", "the harnesses that would not answer"),
                    Field("failed[].cli", "string", "the harness"),
                    Field(
                        "failed[].account",
                        "string",
                        "the account it was asked as, empty for the machine's "
                        "own sign-in",
                    ),
                    Field("failed[].why", "string", "why it would not answer"),
                ),
                methods=("nous.scan",),
                see=("nous list", "accounts models"),
                run=_scan,
            ),
            Command(
                "set",
                "write the tries, limit and graph of a nous",
                says="Writes what is kept of one nous. What is not given stays "
                "as it was written. A name with no `/` is a virtual nous "
                "and needs `--graph`. A graph is one or more nous tried "
                "in turn, or one JSON object of `start` and `nodes` as "
                "`hmz nous list --json` prints one.",
                args=(
                    Arg(
                        ("name",),
                        "the nous: `HARNESS[@ACCOUNT]/MODEL[:EFFORT]` for a "
                        "concrete one, any other name for a virtual one",
                    ),
                    Arg(
                        ("--tries",),
                        "how many more goes a turn that fails there is given",
                        metavar="N",
                        kind=int,
                    ),
                    Arg(
                        ("--policy",),
                        "how long is waited between tries: one of the "
                        "`policies` of `hmz nous list --json`, such as "
                        "`exponential-jitter` or `constant`",
                        metavar="POLICY",
                    ),
                    Arg(
                        ("--timeout",),
                        "the limit of a turn in seconds, 0 for no limit",
                        metavar="SECONDS",
                        kind=float,
                    ),
                    Arg(
                        ("--graph",),
                        "what a virtual nous stands for: a nous, or a JSON "
                        "graph; given more than once, the nous are tried in "
                        "turn",
                        metavar="GRAPH",
                        many=True,
                    ),
                    Arg(
                        ("--then",),
                        "where a turn goes once its tries are spent: a nous, "
                        "or a JSON graph; given more than once, the nous are "
                        "tried in turn",
                        metavar="GRAPH",
                        many=True,
                    ),
                    Arg(
                        ("--no-then",),
                        "send a turn nowhere once its tries are spent, so "
                        "that it fails",
                    ),
                ),
                examples=(
                    Example(
                        "hmz nous set claude/claude-opus-4-1 --tries 3 --timeout 600",
                        "give turns on that model three more goes and ten minutes each",
                    ),
                    Example(
                        "hmz nous set careful --graph claude/claude-opus-4-1 "
                        "--graph codex/gpt-6-sol --tries 1",
                        "make the virtual nous `careful`, which tries one "
                        "model and then the other",
                    ),
                    Example(
                        "hmz nous set claude/claude-haiku-4-5 --then careful",
                        "send a turn to `careful` once its tries on that "
                        "model are spent",
                    ),
                    Example(
                        'hmz nous set fast --graph \'{"start": "a", '
                        '"nodes": [{"id": "a", "balance": '
                        '"round-robin", "among": [{"nous": '
                        '"claude/claude-haiku-4-5", "weight": 1}, '
                        '{"nous": "codex/gpt-6-luna", "weight": 1}]}]}\'',
                        "make the virtual nous `fast`, which balances turns "
                        "between two models",
                    ),
                ),
                prints="The line `Saved.`.",
                output=NOUS,
                methods=("nous.list", "nous.set"),
                see=("nous list", "nous clear"),
                run=_set,
            ),
            Command(
                "rename",
                "rename a virtual nous",
                says="Gives a virtual nous another name, in every graph that "
                "names it too.",
                args=(
                    Arg(("name",), "the virtual nous to rename"),
                    Arg(("to",), "its new name"),
                ),
                examples=(
                    Example(
                        "hmz nous rename careful slow",
                        "rename the virtual nous `careful` to `slow`",
                    ),
                ),
                prints="The line `Renamed`.",
                output=NOUS,
                methods=("nous.rename",),
                see=("nous list",),
                run=_rename,
            ),
            Command(
                "clear",
                "forget what is written of a nous",
                says="Removes the tries, limit and graph written of a nous; a "
                "virtual nous is removed whole. A nous that another nous "
                "names in its graph is refused.",
                args=(_NAME,),
                examples=(
                    Example(
                        "hmz nous clear careful", "remove the virtual nous `careful`"
                    ),
                ),
                prints="The line `Removed`.",
                output=NOUS,
                methods=("nous.clear",),
                see=("nous list",),
                run=_clear,
            ),
        ),
    ),
)
