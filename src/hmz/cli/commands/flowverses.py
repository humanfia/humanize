"""`hmz flowverses`: where flows are installed from, and what is installed out of them."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from hmz.cli.tree import REFUSED, UNREAD, Arg, Command, Example, Field, table
from hmz.words import t

if TYPE_CHECKING:
    from hmz.cli.tree import Call
    from hmz.sdk.families.flowverses import Kept

__all__ = ["COMMANDS"]

#: The code a line that cannot be done as written is answered with under `--json`.
_BAD = 400


def _sure(call: Call, ask: str) -> int | None:
    """Asks at the terminal before something is removed, unless the line said `-y`.

    Never asked of anything but somebody at a terminal, nor under `--json`, whose standard
    error stays empty: a line read off a pipe is not a yes.

    Args:
      call: The command being run.
      ask: The question, as the page asks it.

    Returns:
      None to go on, else the status to end with: nothing was removed.
    """
    if call.yes:
        return None
    if call.json or not sys.stdin.isatty():
        nobody = t("Nobody is at a terminal to ask; run it again with `-y`.")
        if call.json:
            call.answers({"error": {"code": _BAD, "message": nobody}})
            return UNREAD
        line = " ".join(["hmz", *call.path])
        print(f"{line}: {nobody}", file=sys.stderr)
        print(t("Run `{line}` for help.", line=f"{line} --help"), file=sys.stderr)
        return UNREAD
    print(f"{ask} [y/N] ", end="", file=sys.stderr, flush=True)
    if sys.stdin.readline().strip().lower() in ("y", "yes"):
        return None
    print(t("Nothing was changed."), file=sys.stderr)
    return REFUSED


def _changed(call: Call, kept: Kept) -> None:
    """Says what a change did: the daemon's words, or everything it answered."""
    call.answers(kept.answer, [kept.said or t("Done.")])


def _list(call: Call) -> None:
    kept = call.client.flowverses.list()
    newer = {one.flow: one.to for one in kept.updates}
    lines = [t("Flowverses")]
    lines.extend(
        f"  {line}"
        for line in table(
            [
                [
                    one.name,
                    one.url or t("local"),
                    str(one.installed),
                    "" if one.fetched else t("Not fetched yet."),
                ]
                for one in kept.verses
            ]
        )
    )
    lines.append(t("Installed"))
    if kept.installed:
        lines.extend(
            f"  {line}"
            for line in table(
                [
                    [
                        one.flow,
                        one.version,
                        one.verse,
                        t("{version} out", version=newer[one.flow])
                        if one.flow in newer
                        else "",
                    ]
                    for one in kept.installed
                ]
            )
        )
    else:
        lines.append(f"  {t('No flows installed yet.')}")
    call.answers(kept.answer, lines)


def _show(call: Call) -> None:
    index = call.client.flowverses.get(call.name)
    lines = [f"{index.name}  {index.url or t('local')}"]
    if index.edited:
        lines.append(
            t(
                "Something is written into it: fetching resets it to what its "
                "repository says."
            )
        )
    releases = [
        [
            one.flow,
            t("{version} (pre)", version=each.version)
            if each.prerelease
            else each.version,
            t("Installed") if each.version == one.installed else "-",
            each.description,
        ]
        for one in index.flows
        for each in one.releases
    ]
    if releases:
        lines.extend(table(releases))
    else:
        lines.append(
            t("This flowverse lists no flow.")
            if index.fetched
            else t("Not fetched yet.")
        )
    if index.skipped:
        lines.append(t("{n} skipped", n=len(index.skipped)))
        lines.extend(
            f"  {line}" for line in table([[one.at, one.why] for one in index.skipped])
        )
    call.answers(index.answer, lines)


def _add(call: Call) -> None:
    # A repository on this disk written from here is named whole: the daemon stands elsewhere.
    url: str = call.url
    if url.startswith(("./", "../")):
        url = str(Path(url).absolute())
    _changed(call, call.client.flowverses.add(url, call.name))


def _fetch(call: Call) -> None:
    _changed(call, call.client.flowverses.fetch(call.name))


def _remove(call: Call) -> int | None:
    ask = t("Remove {name} and every flow installed out of it?", name=call.name)
    if (status := _sure(call, ask)) is not None:
        return status
    _changed(call, call.client.flowverses.remove(call.name))
    return None


def _install(call: Call) -> None:
    _changed(call, call.client.flowverses.install(call.flow, call.version))


def _uninstall(call: Call) -> int | None:
    if (status := _sure(call, t("Uninstall {name}?", name=call.flow))) is not None:
        return status
    _changed(call, call.client.flowverses.uninstall(call.flow))
    return None


_NAME = Arg(("name",), "the name of the flowverse, as `hmz flowverses list` prints it")
_YES = Arg(
    ("-y", "--yes"),
    "remove without asking first; needed when nobody is at a "
    "terminal to answer, and with `--json`",
)

#: What `flowverses.list` answers, which every change answers too.
_KEPT = (
    Field("verses", "list", "the flowverses"),
    Field("verses[].name", "string", "the name of the flowverse"),
    Field(
        "verses[].url",
        "string",
        "where it is fetched from, without credentials; empty for a local one",
    ),
    Field("verses[].fetched", "boolean", "whether its index has been fetched"),
    Field("verses[].fixed", "boolean", "whether it is built in and cannot be removed"),
    Field(
        "verses[].edited",
        "boolean",
        "whether something is written into its index, which fetching resets",
    ),
    Field("verses[].installed", "integer", "how many flows are installed from it"),
    Field("installed", "list", "the installed flows"),
    Field(
        "installed[].flow",
        "string",
        "the name the flow is started by, and the name `hmz "
        "flowverses install` and `uninstall` take",
    ),
    Field("installed[].verse", "string", "the flowverse it was installed from"),
    Field("installed[].listed", "string", "the name its flowverse lists it under"),
    Field("installed[].version", "string", "the release installed"),
    Field("installed[].repo", "string", "the repository the release came from"),
    Field("installed[].ref", "string", "the git ref of the release"),
    Field("updates", "list", "the installed flows that have a newer release"),
    Field("updates[].flow", "string", "the name of the flow"),
    Field("updates[].from", "string", "the release installed"),
    Field("updates[].to", "string", "the newest release"),
)

#: What a change answers: what it did, and the flowverses as they are after it.
_CHANGED = (Field("said", "string", "what was done, in words"), *_KEPT)

COMMANDS = (
    Command(
        "flowverses",
        "add flowverses and install, update and uninstall their flows",
        says="A flowverse is an index of flows kept in a git repository. "
        "These commands list the flowverses and the flows installed "
        "from them, show the flows and releases one lists, add, "
        "fetch and remove a flowverse, and install, update, switch "
        "and uninstall a flow. Flows cannot be installed, "
        "uninstalled or removed while an epic is running.",
        commands=(
            Command(
                "list",
                "list the flowverses, the installed flows and their newer releases",
                examples=(
                    Example(
                        "hmz flowverses list",
                        "list the flowverses and the installed flows",
                    ),
                    Example(
                        "hmz flowverses list --json "
                        "| jq -r '.updates[] | \"\\(.flow) \\(.to)\"'",
                        "print each installed flow that has a newer release and that "
                        "release, with jq",
                    ),
                ),
                prints="Under Flowverses, one line per flowverse: its name, its "
                "URL, how many flows are installed from it; under Installed, "
                "one line per installed flow: its name, its release, its "
                "flowverse, and the newer release where there is one.",
                output=_KEPT,
                methods=("flowverses.list",),
                see=("flowverses show", "flowverses install", "flows list"),
                run=_list,
            ),
            Command(
                "show",
                "show the flows one flowverse lists and every release of each",
                args=(_NAME,),
                examples=(
                    Example(
                        "hmz flowverses show official",
                        "show the flows and releases the flowverse `official` lists",
                    ),
                    Example(
                        "hmz flowverses show official --json "
                        "| jq -r '.flows[] | select(.installed == \"\") | .flow'",
                        "print the flows of `official` that are not installed, with jq",
                    ),
                ),
                prints="Prints the flowverse's name and URL, then one line per "
                "release, newest first under each flow: the flow as `hmz "
                "flowverses install` takes it, the release, whether it is "
                "installed, and its description; then what its index skipped "
                "and why.",
                output=(
                    Field("name", "string", "the name of the flowverse"),
                    Field(
                        "url",
                        "string",
                        "where it is fetched from, without credentials; empty for a "
                        "local one",
                    ),
                    Field("fetched", "boolean", "whether its index has been fetched"),
                    Field(
                        "fixed",
                        "boolean",
                        "whether it is built in and cannot be removed",
                    ),
                    Field(
                        "edited",
                        "boolean",
                        "whether something is written into its index, which fetching "
                        "resets",
                    ),
                    Field("flows", "list", "the flows its index lists"),
                    Field(
                        "flows[].listed",
                        "string",
                        "the name the flowverse lists the flow under",
                    ),
                    Field(
                        "flows[].flow",
                        "string",
                        "the name `hmz flowverses install` takes for it",
                    ),
                    Field(
                        "flows[].installed", "string", "the release installed, or empty"
                    ),
                    Field(
                        "flows[].releases",
                        "list",
                        "every release, newest first, each `version`, `description`, "
                        "`prerelease`, `license`, `repo` and `dependencies`",
                    ),
                    Field(
                        "skipped",
                        "list",
                        "what in the index could not be read, each `at` and `why`",
                    ),
                ),
                methods=("flowverses.get",),
                see=("flowverses install", "flowverses fetch", "flowverses list"),
                run=_show,
            ),
            Command(
                "add",
                "add a flowverse by its repository",
                args=(
                    Arg(
                        ("url",),
                        "the flowverse's git repository, as `owner/repo` on GitHub "
                        "or a URL",
                    ),
                    Arg(
                        ("--name",),
                        "the name to keep the flowverse under; the name its URL "
                        "gives when not given",
                        metavar="NAME",
                    ),
                ),
                examples=(
                    Example(
                        "hmz flowverses add acme/flows",
                        "add the flowverse kept in the GitHub repository `acme/flows`",
                    ),
                    Example(
                        "hmz flowverses add https://git.example.com/team/flows.git "
                        "--name team",
                        "add a flowverse from a git URL and keep it under the name "
                        "`team`",
                    ),
                ),
                prints="Prints what was done, in one line.",
                output=_CHANGED,
                methods=("flowverses.add",),
                see=("flowverses show", "flowverses install", "flowverses remove"),
                run=_add,
            ),
            Command(
                "fetch",
                "fetch a flowverse's index again to see its new releases",
                says="Fetches the flowverse's index from its repository, so that "
                "`hmz flowverses list` shows the newer releases. Fetching "
                "resets anything written into the index.",
                args=(_NAME,),
                examples=(
                    Example(
                        "hmz flowverses fetch official",
                        "fetch the index of the flowverse `official`",
                    ),
                    Example(
                        "hmz flowverses fetch official --json | jq -r '.updates[].flow'",
                        "fetch `official` and print the flows that now have a newer "
                        "release, with jq",
                    ),
                ),
                prints="Prints what was done, in one line.",
                output=_CHANGED,
                methods=("flowverses.fetch",),
                see=("flowverses list", "flowverses install"),
                run=_fetch,
            ),
            Command(
                "remove",
                "remove a flowverse and every flow installed from it",
                says="Removes the flowverse and uninstalls every flow installed "
                "from it. Asks first unless `-y` is given; any answer other than "
                "yes changes nothing and exits with status 1. Refused while an "
                "epic is running.",
                args=(_NAME, _YES),
                examples=(
                    Example(
                        "hmz flowverses remove team",
                        "remove the flowverse `team` after confirming",
                    ),
                    Example(
                        "hmz flowverses remove team -y",
                        "remove the flowverse `team` without asking",
                    ),
                ),
                prints="Prints what was done, in one line.",
                output=_CHANGED,
                methods=("flowverses.remove",),
                see=("flowverses list", "flowverses uninstall"),
                run=_remove,
            ),
            Command(
                "install",
                "install a flow, or update or switch its release",
                says="Installs the newest release of a flow, or the release "
                "`--version` names. For a flow already installed this "
                "updates it or switches its release. Refused while an epic "
                "is running.",
                args=(
                    Arg(
                        ("flow",),
                        "the flow, as `hmz flowverses show` prints it: bare for the "
                        "official flowverse, `@FLOWVERSE/FLOW` for another",
                    ),
                    Arg(
                        ("--version",),
                        "the release to install; the newest when not given",
                        metavar="VERSION",
                    ),
                ),
                examples=(
                    Example(
                        "hmz flowverses install ralph_loop",
                        "install the newest release of `ralph_loop`, or update it to "
                        "that release",
                    ),
                    Example(
                        "hmz flowverses install @team/review --version 1.2.0",
                        "install release 1.2.0 of the flow `review` from the "
                        "flowverse `team`",
                    ),
                ),
                prints="Prints what was done, in one line.",
                output=_CHANGED,
                methods=("flowverses.install",),
                see=("flowverses show", "flowverses list", "flows show"),
                run=_install,
            ),
            Command(
                "uninstall",
                "uninstall a flow",
                says="Uninstalls a flow installed from a flowverse. Asks first "
                "unless `-y` is given; any answer other than yes changes nothing "
                "and exits with status 1. Refused while an epic is running.",
                args=(
                    Arg(
                        ("flow",),
                        "the installed flow, as `hmz flowverses list` prints it",
                    ),
                    _YES,
                ),
                examples=(
                    Example(
                        "hmz flowverses uninstall ralph_loop",
                        "uninstall the flow `ralph_loop` after confirming",
                    ),
                    Example(
                        "hmz flowverses uninstall @team/review -y",
                        "uninstall the flow `review` of the flowverse `team` without "
                        "asking",
                    ),
                ),
                prints="Prints what was done, in one line.",
                output=_CHANGED,
                methods=("flowverses.uninstall",),
                see=("flowverses list", "flowverses install"),
                run=_uninstall,
            ),
        ),
    ),
)
