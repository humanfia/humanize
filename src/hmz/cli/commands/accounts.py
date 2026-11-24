"""`hmz accounts`: the accounts an agent is run as, made and corrected without showing one.

What an account holds is a credential, so nothing here prints one and nothing here takes one
where it would be kept: an answer that is a credential is read from this process's
environment or from standard input, never from the command line, which a shell writes down
and every process of the machine can read (Section 4.3 of cli.md).
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

from hmz.cli.tree import UNREAD, Arg, Command, Example, Field, table
from hmz.words import t

if TYPE_CHECKING:
    from hmz.cli.tree import Call
    from hmz.sdk.families.accounts import Account, Listing, Way

__all__ = ["COMMANDS"]


class _Unread(Exception):  # noqa: N818 -- named for what happened
    """A line that parsed and still cannot be read: said as a usage error is."""


def _unread(call: Call, why: _Unread) -> int:
    """Says what is wrong with the line as the tree says a usage error, and its status."""
    line = " ".join(["hmz", *call.path])
    print(f"{line}: {why}", file=sys.stderr)
    print(t("Run `{line}` for help.", line=f"{line} --help"), file=sys.stderr)
    return UNREAD


def _account(one: Account) -> dict[str, Any]:
    return {
        "cli": one.cli,
        "name": one.name,
        "way": one.way,
        "sets": list(one.sets),
        "made": one.made,
        "models": list(one.models),
        "asked": one.asked,
        "serves": list(one.serves),
    }


def _document(listing: Listing) -> dict[str, Any]:
    """Every account, by its names: what each command that changes one answers."""
    return {
        "gateway": listing.gateway,
        "accounts": [_account(one) for one in listing.accounts],
    }


def _list(call: Call) -> None:
    listing = call.client.accounts.list()
    call.answers(
        _document(listing),
        table(
            [
                [
                    one.cli,
                    one.name or t("Local"),
                    one.way,
                    ",".join(one.sets),
                    t("{n} models", n=len(one.models)),
                ]
                for one in listing.accounts
            ]
        ),
    )


def _ways(call: Call) -> None:
    listing = call.client.accounts.list()
    backends = [one for one in listing.backends if call.cli in ("", one.cli)]
    lines: list[str] = []
    for backend in backends:
        for way in backend.ways:
            name = (
                t("{name} (at a terminal)", name=way.name) if way.terminal else way.name
            )
            lines.append(f"{backend.cli}  {name}  {way.about}".rstrip())
            for ask in way.asks:
                left = t(" Left empty, it is {value}.", value=ask.fixed)
                about = f"{ask.about}{left if ask.fixed else ''}"
                lines.append(f"    {ask.env}  {about}".rstrip())
    call.answers(
        {
            "gateway": listing.gateway,
            "backends": [
                {
                    "cli": backend.cli,
                    "wants": backend.wants,
                    "ways": [
                        {
                            "name": way.name,
                            "about": way.about,
                            "group": way.group,
                            "terminal": way.terminal,
                            "asks": [
                                {
                                    "env": ask.env,
                                    "about": ask.about,
                                    "secret": ask.secret,
                                    "fixed": ask.fixed,
                                }
                                for ask in way.asks
                            ],
                        }
                        for way in backend.ways
                    ],
                }
                for backend in backends
            ],
        },
        lines,
    )


def _answers(call: Call, secret: frozenset[str]) -> dict[str, str]:
    """What the line answers a way of signing in with, by the variable each answer is for.

    Args:
      call: The command, with its `--set`, `--env` and `--stdin`.
      secret: The variables that are credentials, which `--set` does not take.

    Raises:
      _Unread: For a `--set` that is no `NAME=VALUE` or names a credential, an `--env`
        naming a variable this process has not got, and an answer brought from the
        environment or standard input that is empty -- which a daemon would take for an
        answer not given, and say it had saved.
    """
    answers: dict[str, str] = {}
    brought: list[str] = []
    for said in call.set or ():
        name, equals, value = said.partition("=")
        if not equals or not name:
            # Not said back: a word with no name before it may be the credential itself.
            raise _Unread(t("`--set` takes an answer as NAME=VALUE"))
        if name in secret:
            raise _Unread(
                t(
                    "{name} is a credential: give it with `--env` or "
                    "`--stdin`, not on the command line",
                    name=name,
                )
            )
        answers[name] = value
    for said in call.env or ():
        name, _, held = said.partition("=")
        held = held or name
        if held not in os.environ:
            raise _Unread(t("the environment variable {name} is not set", name=held))
        answers[name] = os.environ[held]
        brought.append(name)
    if call.stdin:
        answers[call.stdin] = sys.stdin.read().rstrip("\r\n")
        brought.append(call.stdin)
    for name in brought:
        if not answers[name]:
            raise _Unread(t("the answer given for {name} is empty", name=name))
    return answers


def _secret(way: Way | None, sets: tuple[str, ...] = ()) -> frozenset[str]:
    """The variables that are credentials: a way's own, or every one where no way says."""
    if way is None:
        return frozenset(sets)
    return frozenset(ask.env for ask in way.asks if ask.secret)


def _add(call: Call) -> int | None:
    accounts = call.client.accounts
    backend = accounts.list().backend(call.cli)
    way = backend.way(call.way) if backend is not None else None
    try:
        answers = _answers(call, _secret(way))
    except _Unread as why:
        return _unread(call, why)
    listing = accounts.create(call.cli, call.name, call.way, answers)
    call.answers(
        _document(listing),
        [t("Made {account}.", account=f"{call.cli}@{call.name}")],
    )
    return None


def _correct(call: Call) -> int | None:
    accounts = call.client.accounts
    listing = accounts.list()
    one = listing.account(call.cli, call.name)
    backend = listing.backend(call.cli)
    way = backend.way(one.way) if backend is not None and one is not None else None
    try:
        answers = _answers(call, _secret(way, one.sets if one is not None else ()))
    except _Unread as why:
        return _unread(call, why)
    call.answers(
        _document(accounts.correct(call.cli, call.name, answers)), [t("Saved.")]
    )
    return None


def _remove(call: Call) -> None:
    listing = call.client.accounts.remove(call.cli, call.name)
    call.answers(_document(listing), [t("Removed")])


def _models(call: Call) -> None:
    client = call.client
    listing = client.accounts.models(call.cli, call.name)
    one = listing.account(call.cli, call.name)
    if one is not None or call.name:
        models = list(one.models) if one is not None else []
        asked = one.asked if one is not None else ""
    else:
        # The machine's own sign-in is listed only beside accounts made for its harness;
        # without one, what the harness just said is among the concrete nous.
        under = f"{call.cli}/"
        models = [
            nous.removeprefix(under)
            for nous in client.nous.list().concrete
            if nous.startswith(under)
        ]
        asked = ""
    call.answers(
        {"cli": call.cli, "name": call.name, "models": models, "asked": asked},
        models or [t("No models listed")],
    )


def _copy(call: Call) -> None:
    listing = call.client.accounts.copy(call.cli, call.name, call.into)
    call.answers(_document(listing), [t("Copied to {name}", name=call.into)])


_CLI = Arg(("cli",), "the harness the account is for, such as `claude` or `codex`")
_NAME = Arg(("name",), "name of the account, as `hmz accounts list` prints it")

_SET = Arg(
    ("--set",),
    "an answer that is not a credential, as NAME=VALUE, NAME being the "
    "variable the way asks for",
    metavar="NAME=VALUE",
    many=True,
)
_ENV = Arg(
    ("--env",),
    "take the answer NAME from the environment variable of the same name, or "
    "from VAR where written NAME=VAR; for credentials",
    metavar="NAME[=VAR]",
    many=True,
)
_STDIN = Arg(
    ("--stdin",),
    "read the answer NAME from standard input, without its trailing line "
    "feed; for a credential",
    metavar="NAME",
)

ACCOUNTS = (
    Field(
        "gateway",
        "string",
        "name of the local gateway some ways of signing in go through",
    ),
    Field(
        "accounts",
        "list",
        "every account, the machine's own sign-in listed with an empty name",
    ),
    Field("accounts[].cli", "string", "the harness the account is for"),
    Field(
        "accounts[].name",
        "string",
        "name of the account, empty for the machine's own sign-in",
    ),
    Field("accounts[].way", "string", "the sign-in method it was made by"),
    Field(
        "accounts[].sets",
        "list",
        "names of the environment variables it sets, never their values",
    ),
    Field(
        "accounts[].made",
        "string",
        "when it was made, ISO 8601, or empty for the machine's own sign-in",
    ),
    Field(
        "accounts[].models",
        "list",
        "the models its harness last said it runs as this account",
    ),
    Field(
        "accounts[].asked",
        "string",
        "when the harness was last asked for its models, ISO 8601, or empty if never",
    ),
    Field(
        "accounts[].serves", "list", "the other harnesses the account can be copied to"
    ),
)

COMMANDS = (
    Command(
        "accounts",
        "list, add and remove the accounts agents run as",
        says="An account is a named set of credentials for one harness, kept "
        "apart from the harness's own sign-in. An agent is given one as "
        "`-a` spells it: `HARNESS@ACCOUNT/MODEL`. No command prints a "
        "credential, and a credential is never taken from the command "
        "line.",
        commands=(
            Command(
                "list",
                "list the accounts",
                examples=(
                    Example("hmz accounts list", "list the accounts"),
                    Example(
                        "hmz accounts list --json | jq -r '.accounts[] | "
                        '"\\(.cli)@\\(.name)"\'',
                        "print each account as `HARNESS@ACCOUNT` with jq",
                    ),
                ),
                prints="One line per account: harness, name (`Local` for the "
                "machine's own sign-in), sign-in method, the variables it "
                "sets, how many models it runs.",
                output=ACCOUNTS,
                methods=("accounts.list",),
                see=("accounts ways", "accounts add", "accounts models"),
                run=_list,
            ),
            Command(
                "ways",
                "list the sign-in methods of each harness and what each asks for",
                says="Lists how an account can be made for each harness. A "
                "method marked `(at a terminal)` runs the harness's own "
                "sign-in and can only be used from `/settings` in `hmz`; "
                "any other is made by `hmz accounts add` from the answers "
                "it asks for.",
                args=(
                    Arg(
                        ("cli",),
                        "list the sign-in methods of this harness only",
                        default="",
                    ),
                ),
                examples=(
                    Example(
                        "hmz accounts ways claude",
                        "list the sign-in methods of `claude` and the "
                        "variables each asks for",
                    ),
                    Example(
                        "hmz accounts ways --json | jq '.backends[].ways[] | "
                        "select(.terminal | not) | .name'",
                        "print the sign-in methods `hmz accounts add` can use with jq",
                    ),
                ),
                prints="One line per sign-in method: harness, method, what it "
                "is. Under it, indented, one line per answer it asks for: "
                "the variable and what it is.",
                output=(
                    Field(
                        "gateway",
                        "string",
                        "name of the local gateway some ways of signing in go through",
                    ),
                    Field("backends", "list", "every harness of the daemon"),
                    Field("backends[].cli", "string", "name of the harness"),
                    Field(
                        "backends[].wants",
                        "string",
                        "the command that installs what its gateway sign-in "
                        "methods need, or empty",
                    ),
                    Field("backends[].ways", "list", "its sign-in methods"),
                    Field(
                        "backends[].ways[].name",
                        "string",
                        "name of the sign-in method, as `--way` takes it",
                    ),
                    Field(
                        "backends[].ways[].about",
                        "string",
                        "what the sign-in method is",
                    ),
                    Field(
                        "backends[].ways[].group",
                        "string",
                        "the gateway it goes through, or empty",
                    ),
                    Field(
                        "backends[].ways[].terminal",
                        "boolean",
                        "whether it needs a terminal and so cannot be used by "
                        "`hmz accounts add`",
                    ),
                    Field("backends[].ways[].asks", "list", "the answers it asks for"),
                    Field(
                        "backends[].ways[].asks[].env",
                        "string",
                        "the variable the answer is given as",
                    ),
                    Field(
                        "backends[].ways[].asks[].about", "string", "what the answer is"
                    ),
                    Field(
                        "backends[].ways[].asks[].secret",
                        "boolean",
                        "whether the answer is a credential, taken by `--env` "
                        "or `--stdin` only",
                    ),
                    Field(
                        "backends[].ways[].asks[].fixed",
                        "string",
                        "its value where left unanswered, or empty where it "
                        "must be answered",
                    ),
                ),
                methods=("accounts.list",),
                see=("accounts add",),
                run=_ways,
            ),
            Command(
                "add",
                "make an account from the answers to a sign-in method",
                says="Makes an account for a harness. `hmz accounts ways CLI` "
                "lists the sign-in methods and the answers each asks for. "
                "Give an answer that is a credential with `--env` or "
                "`--stdin`; `--set` refuses one, and no answer is ever "
                "printed.",
                args=(
                    _CLI,
                    Arg(("name",), "name for the new account, such as `work`"),
                    Arg(
                        ("--way",),
                        "the sign-in method, as `hmz accounts ways` names it",
                        metavar="WAY",
                        required=True,
                    ),
                    _SET,
                    _ENV,
                    _STDIN,
                ),
                examples=(
                    Example(
                        "hmz accounts add claude work --way key --env "
                        "ANTHROPIC_API_KEY",
                        "make `claude@work` from the API key in the "
                        "environment variable `ANTHROPIC_API_KEY`",
                    ),
                    Example(
                        "pass show anthropic | hmz accounts add claude work "
                        "--way key --stdin ANTHROPIC_API_KEY",
                        "read the API key from standard input instead",
                    ),
                    Example(
                        "hmz accounts add claude proxy --way "
                        "anthropic-gateway --set "
                        "ANTHROPIC_BASE_URL=https://llm.example.org --env "
                        "ANTHROPIC_AUTH_TOKEN=PROXY_TOKEN",
                        "give a URL on the command line and a credential from "
                        "the environment variable `PROXY_TOKEN`",
                    ),
                ),
                prints="The line `Made HARNESS@ACCOUNT.`.",
                output=ACCOUNTS,
                methods=("accounts.list", "accounts.create"),
                see=("accounts ways", "accounts list", "accounts correct"),
                run=_add,
            ),
            Command(
                "correct",
                "write an account again with new answers",
                says="Changes the answers an account was made from. An answer "
                "not given stays as it was. Give a credential with "
                "`--env` or `--stdin`.",
                args=(_CLI, _NAME, _SET, _ENV, _STDIN),
                examples=(
                    Example(
                        "hmz accounts correct claude work --env ANTHROPIC_API_KEY",
                        "replace the API key of `claude@work` with the one in "
                        "the environment",
                    ),
                    Example(
                        "hmz accounts correct claude proxy --set "
                        "ANTHROPIC_BASE_URL=https://llm2.example.org",
                        "change the URL of `claude@proxy` and keep its credential",
                    ),
                ),
                prints="The line `Saved.`.",
                output=ACCOUNTS,
                methods=("accounts.list", "accounts.correct"),
                see=("accounts ways", "accounts list"),
                run=_correct,
            ),
            Command(
                "remove",
                "remove an account, credentials and all",
                args=(_CLI, _NAME),
                examples=(
                    Example(
                        "hmz accounts remove claude work",
                        "remove the account `claude@work`",
                    ),
                ),
                prints="The line `Removed`.",
                output=ACCOUNTS,
                methods=("accounts.remove",),
                see=("accounts list",),
                run=_remove,
            ),
            Command(
                "models",
                "ask a harness which models it runs as an account",
                says="Asks the harness which models it runs as the account, "
                "and keeps the answer: it is what `hmz accounts list` and "
                "`hmz nous list` show from then on.",
                args=(
                    _CLI,
                    Arg(
                        ("name",),
                        "name of the account; the machine's own sign-in where "
                        "not given",
                        default="",
                    ),
                ),
                examples=(
                    Example(
                        "hmz accounts models claude work",
                        "ask `claude` which models it runs as the account `work`",
                    ),
                    Example(
                        "hmz accounts models codex",
                        "ask `codex` which models it runs as the machine's own sign-in",
                    ),
                ),
                prints="One model per line, or `No models listed`.",
                output=(
                    Field("cli", "string", "the harness that was asked"),
                    Field(
                        "name",
                        "string",
                        "name of the account, empty for the machine's own sign-in",
                    ),
                    Field(
                        "models", "list", "the models the harness runs as the account"
                    ),
                    Field(
                        "asked",
                        "string",
                        "when the harness was asked, ISO 8601, or empty where "
                        "the daemon does not say",
                    ),
                ),
                methods=("accounts.models", "nous.list"),
                see=("accounts list", "nous scan"),
                run=_models,
            ),
            Command(
                "copy",
                "copy an account to another harness",
                says="Writes an account down again for another harness its "
                "credentials can run. The `serves` field of `hmz accounts "
                "list --json` names the harnesses an account can be "
                "copied to.",
                args=(
                    _CLI,
                    _NAME,
                    Arg(("into",), "the harness to copy it to"),
                ),
                examples=(
                    Example(
                        "hmz accounts copy claude work pi",
                        "copy the account `claude@work` to the harness `pi`",
                    ),
                ),
                prints="The line `Copied to HARNESS`.",
                output=ACCOUNTS,
                methods=("accounts.copy",),
                see=("accounts list",),
                run=_copy,
            ),
        ),
    ),
)
