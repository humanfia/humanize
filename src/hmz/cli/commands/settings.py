"""`hmz settings`: what a daemon keeps of its machine's settings, and of a workspace's."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Any, cast

from hmz.cli.tree import Arg, Command, Example, Field, Unread, table, whole
from hmz.words import t

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from hmz.cli.tree import Call
    from hmz.sdk.families.settings import Kept

__all__ = ["COMMANDS"]

#: Every setting `settings.get` answers, in the order it is printed.
KEYS = (
    "workspace",
    "flow",
    "flows",
    "chat",
    "prefer",
    "ai_chan",
    "details",
    "harness_sessions",
    "reports",
    "backup",
    "listen",
    "ice_servers",
)

#: What `on` and `off` are, and their JSON spellings.
_SWITCH = {"on": True, "true": True, "off": False, "false": False}

#: When a backup target is backed up to unasked; `manual` is none of them.
_POLICIES = ("session", "interval", "end")


def _at(said: str | None) -> str | None:
    """A workspace as the daemon takes one: whole, a relative one read from this directory."""
    return None if said is None else whole(said)


def _read(said: str) -> Any:
    """A value written as JSON, `-` being JSON on standard input.

    Raises:
      Unread: If it is not JSON.
    """
    try:
        return json.loads(sys.stdin.read() if said == "-" else said)
    except ValueError:
        raise Unread(t("This is not valid JSON.")) from None


def _shown(value: object) -> str:
    """A setting as a line of text: text as it is, anything else as JSON."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def _get(call: Call) -> int | None:
    if call.key and call.key not in KEYS:
        raise Unread(t("no setting named {name}", name=call.key))
    said = call.client.settings.get(_at(call.workspace)).said
    if call.key:
        call.answers({call.key: said.get(call.key)}, [_shown(said.get(call.key))])
    else:
        call.answers(said, table([[key, _shown(said.get(key))] for key in KEYS]))
    return None


def _saved(call: Call, kept: Kept) -> None:
    call.answers(kept.said, [t("Saved.")])


def _details(call: Call) -> None:
    _saved(call, call.client.settings.set(details=_SWITCH[call.value]))


def _reports(call: Call) -> None:
    _saved(call, call.client.settings.set(reports=_SWITCH[call.value]))


def _harness_sessions(call: Call) -> None:
    _saved(call, call.client.settings.set(harness_sessions=_SWITCH[call.value]))


def _chat(call: Call) -> None:
    _saved(
        call, call.client.settings.set(workspace=_at(call.workspace), chat=call.agent)
    )


def _prefer(call: Call) -> None:
    _saved(call, call.client.settings.set(prefer=call.value))


def _listed(words: Sequence[str], *, objects: bool = False) -> list[Any]:
    """Words as a list: each an item, or one word that is the list whole, as JSON.

    Args:
      words: Them.
      objects: Whether a word beginning `{` is an item written as JSON.

    Raises:
      Unread: If a word written as JSON is not JSON, or the list whole is not a list.
    """
    if len(words) == 1 and (words[0] == "-" or words[0].startswith("[")):
        whole: Any = _read(words[0])
        if not isinstance(whole, list):
            raise Unread(t("This is not valid JSON."))
        return cast("list[Any]", whole)
    return [_read(one) if objects and one.startswith("{") else one for one in words]


def _listen(call: Call) -> int | None:
    specs = _listed(call.spec)
    _saved(call, call.client.settings.set(listen=specs))
    return None


def _servers(words: Sequence[str]) -> list[dict[str, Any]]:
    """The STUN and TURN servers a line writes, a bare URL being a server of that URL.

    Raises:
      Unread: For JSON that is not JSON, and for a credential given on the line: a shell
        wrote that one down, so only standard input brings one.
    """
    servers: list[dict[str, Any]] = []
    for one in _listed(words, objects=True):
        if not isinstance(one, str | dict):
            raise Unread(t("This is not valid JSON."))
        servers.append(
            {"urls": one} if isinstance(one, str) else cast("dict[str, Any]", one)
        )
    if list(words) != ["-"] and any(
        isinstance(one.get("credential"), str) for one in servers
    ):
        raise Unread(
            t(
                "a credential is read from standard input only: give the "
                "servers as JSON with `-`"
            )
        )
    return servers


def _ice_servers(call: Call) -> int | None:
    servers = _servers(call.server)
    _saved(call, call.client.settings.set(ice_servers=servers))
    return None


def _backup(call: Call) -> int | None:
    backup = _read(call.value)
    _saved(call, call.client.settings.set(backup=backup))
    return None


def _target(call: Call) -> int | None:
    """Writes one backup target among the others, which are sent back as they were read."""
    settings = call.client.settings
    backup: Mapping[str, Any] = settings.get().said["backup"]
    targets = [dict(one) for one in backup["targets"]]
    defaults = list(backup["defaults"])
    was = next((one for one in targets if one["name"] == call.name), None)
    if call.remove:
        if was is None:
            raise Unread(t("no backup target named {name}", name=call.name))
        targets = [one for one in targets if one["name"] != call.name]
        defaults = [one for one in defaults if one != call.name]
    else:
        one = was or {"name": call.name, "branch": "main", "policies": [], "every": 30}
        if call.url is not None:
            one["url"] = call.url
        if call.branch is not None:
            one["branch"] = call.branch
        if call.policy is not None:
            one["policies"] = [each for each in _POLICIES if each in call.policy]
        if call.every is not None:
            one["every"] = call.every
        if was is None:
            targets.append(one)
        if call.no_default:
            defaults = [one for one in defaults if one != call.name]
        elif call.default and call.name not in defaults:
            defaults.append(call.name)
    _saved(call, settings.set(backup={"targets": targets, "defaults": defaults}))
    return None


def _defaults(call: Call) -> None:
    settings = call.client.settings
    backup: Mapping[str, Any] = settings.get().said["backup"]
    _saved(
        call,
        settings.set(backup={"targets": backup["targets"], "defaults": call.name}),
    )


def _forget(call: Call) -> None:
    kept = call.client.settings.forget(_at(call.workspace) or "~")
    call.answers(
        kept.said, [t("Forgotten.") if kept.forgot else t("Nothing to forget.")]
    )


FIELDS = (
    Field(
        "workspace",
        "string",
        "the workspace these settings are of, the home folder where none was named",
    ),
    Field("flow", "string", "the flow the workspace was last set up to run, or empty"),
    Field("flows", "list", "names of the flows set up in the workspace"),
    Field(
        "chat",
        "string",
        "the chat agent remembered for the workspace, as `-a` spells one, or empty",
    ),
    Field(
        "prefer",
        "string",
        "what `$NAME` in a chat means where it names both a native skill and "
        "a flow: `native` or `flow`",
    ),
    Field(
        "ai_chan",
        "string",
        "the nous the last Ai-chan conversation was made with, or empty",
    ),
    Field("details", "boolean", "whether tool calls and thinking are shown"),
    Field(
        "harness_sessions",
        "boolean",
        "whether harness sessions are listed in the sidebar",
    ),
    Field(
        "reports",
        "boolean|null",
        "whether Humanize reports its own failures, or null if never answered",
    ),
    Field("backup", "object", "the backup targets and the defaults"),
    Field("backup.targets", "list", "the git repositories epics are backed up to"),
    Field("backup.targets[].name", "string", "name of the backup target"),
    Field(
        "backup.targets[].url",
        "string",
        "URL of the repository, with its credentials removed",
    ),
    Field("backup.targets[].branch", "string", "the branch pushed to"),
    Field(
        "backup.targets[].policies",
        "list",
        "when it is backed up to unasked: any of `session`, `interval`, "
        "`end`; empty means by hand only",
    ),
    Field(
        "backup.targets[].every",
        "integer",
        "minutes between backups under the `interval` policy",
    ),
    Field("backup.defaults", "list", "names of the targets a new epic is backed up to"),
    Field("listen", "list", "the listener specs the daemon opens"),
    Field("ice_servers", "list", "the STUN and TURN servers"),
    Field("ice_servers[].urls", "string|list", "URL or URLs of the server"),
    Field(
        "ice_servers[].username",
        "string",
        "username of a TURN server, where it has one",
    ),
    Field(
        "ice_servers[].credential",
        "boolean",
        "`true` where a credential is kept; its value is never printed",
    ),
)

_WORKSPACE = Arg(
    ("-w", "--workspace"),
    "the workspace folder, as a path; the home folder where not given",
    metavar="PATH",
)

_SWITCHED = Arg(
    ("value",),
    "`on` or `off`; `true` and `false` are taken too",
    choices=tuple(_SWITCH),
)

_PRINTS_SAVED = "The line `Saved.`."


def _set(name: str, summary: str, **more: Any) -> Command:
    """One setting written: a command of `hmz settings set`, answering the settings after."""
    return Command(
        name,
        summary,
        prints=_PRINTS_SAVED,
        output=FIELDS,
        methods=more.pop("methods", ("settings.set",)),
        see=("settings get",),
        **more,
    )


COMMANDS = (
    Command(
        "settings",
        "read and write the settings this daemon keeps",
        says="The settings a daemon keeps for its machine (details, error "
        "reports, harness sessions, what `$NAME` means in a chat, backup "
        "targets, listeners, STUN and TURN servers) and for one workspace "
        "(its chat agent and the flows set up there).",
        commands=(
            Command(
                "get",
                "print the settings, or one of them",
                args=(
                    Arg(
                        ("key",),
                        "the one setting to print, a field of the JSON "
                        "document such as `details` or `backup`; every "
                        "setting where not given",
                        default="",
                    ),
                    _WORKSPACE,
                ),
                examples=(
                    Example(
                        "hmz settings get",
                        "print every setting of this machine and of the home folder",
                    ),
                    Example(
                        "hmz settings get chat -w ~/project",
                        "print the chat agent remembered for the workspace `~/project`",
                    ),
                    Example(
                        "hmz settings get backup --json | jq -r "
                        "'.backup.targets[].name'",
                        "print the names of the backup targets with jq",
                    ),
                ),
                prints="One line per setting: its name and its value, text as it "
                "is and anything else as JSON. With KEY, the value alone.",
                output=FIELDS,
                methods=("settings.get",),
                see=("settings set", "settings forget"),
                run=_get,
            ),
            Command(
                "set",
                "write one setting",
                says="Writes one setting and prints `Saved.`; with `--json`, "
                "prints every setting as it is afterwards. Each setting "
                "is a command of its own: run `hmz settings set COMMAND "
                "--help` for the values it takes.",
                commands=(
                    _set(
                        "details",
                        "show or hide tool calls and thinking",
                        args=(_SWITCHED,),
                        examples=(
                            Example(
                                "hmz settings set details on",
                                "show tool calls and thinking",
                            ),
                        ),
                        run=_details,
                    ),
                    _set(
                        "reports",
                        "turn error reports on or off",
                        says="Whether Humanize sends a report of its own "
                        "crashes. Nothing anybody typed, no file and no "
                        "credential is ever sent.",
                        args=(_SWITCHED,),
                        examples=(
                            Example(
                                "hmz settings set reports off",
                                "stop Humanize reporting its own failures",
                            ),
                        ),
                        run=_reports,
                    ),
                    _set(
                        "harness_sessions",
                        "list or hide harness sessions in the sidebar",
                        says="The sessions each harness had of its own in a "
                        "folder, which Humanize did not run, listed after "
                        "its chats. They are only read: continuing one "
                        "copies it into a chat, and the harness’s own "  # noqa: RUF001 -- the page's
                        "files are never changed.",
                        args=(_SWITCHED,),
                        examples=(
                            Example(
                                "hmz settings set harness_sessions on",
                                "list harness sessions after the chats of a folder",
                            ),
                        ),
                        run=_harness_sessions,
                    ),
                    _set(
                        "chat",
                        "set the chat agent remembered for a workspace",
                        args=(
                            Arg(
                                ("agent",),
                                "the agent, as `-a` spells one: "
                                "`HARNESS[@ACCOUNT]/MODEL[:EFFORT]` or the "
                                "name of a nous",
                            ),
                            _WORKSPACE,
                        ),
                        examples=(
                            Example(
                                "hmz settings set chat claude/claude-opus-4-1",
                                "make new chats in the home folder start with "
                                "that agent",
                            ),
                            Example(
                                "hmz settings set chat "
                                "codex@work/gpt-6-sol:high -w ~/project",
                                "set the chat agent of the workspace "
                                "`~/project`, with an account and an effort",
                            ),
                        ),
                        run=_chat,
                    ),
                    _set(
                        "prefer",
                        "set what `$NAME` in a chat means when a skill and flow match",
                        says="Sets the preference of every chat of this "
                        "machine: whether `$NAME` typed in a chat runs "
                        "the harness's own skill of that name or the flow "
                        "of that name, where both exist. One chat can "
                        "override it with `/prefer`.",
                        args=(
                            Arg(
                                ("value",),
                                "`native` for the harness's own skill, "
                                "`flow` for the flow",
                                choices=("native", "flow"),
                            ),
                        ),
                        examples=(
                            Example(
                                "hmz settings set prefer flow",
                                "make `$NAME` in a chat run the flow "
                                "where a skill has the same name",
                            ),
                        ),
                        run=_prefer,
                    ),
                    _set(
                        "listen",
                        "set the listeners the daemon opens",
                        says="Writes every listener the daemon opens, "
                        "replacing the ones written; listeners open and "
                        "close at once. Give none to listen nowhere.",
                        args=(
                            Arg(
                                ("spec",),
                                "a listener spec such as "
                                "`tcp://0.0.0.0:7000`, `ws://0.0.0.0:7001`, "
                                "`relay:URL`, `webrtc:URL` or "
                                "`easytier:NAME`; or one JSON list of them",
                                many=True,
                            ),
                        ),
                        examples=(
                            Example(
                                "hmz settings set listen tcp://0.0.0.0:7000 "
                                "ws://0.0.0.0:7001",
                                "listen on a TCP port and a WebSocket port",
                            ),
                            Example("hmz settings set listen", "close every listener"),
                        ),
                        run=_listen,
                    ),
                    _set(
                        "ice_servers",
                        "set the STUN and TURN servers",
                        says="Writes every STUN and TURN server, replacing the "
                        "ones written. They are only used where this "
                        "daemon is reached over a `webrtc:` route. A TURN "
                        "server's credential is read from JSON on "
                        "standard input, never from the command line; "
                        '`"credential": true` keeps the one written.',
                        args=(
                            Arg(
                                ("server",),
                                "a server's URL such as "
                                "`stun:stun.example.org:3478`, a JSON object "
                                "of `urls`, `username` and `credential`, one "
                                "JSON list of them, or `-` to read that list "
                                "from standard input",
                                many=True,
                            ),
                        ),
                        examples=(
                            Example(
                                "hmz settings set ice_servers "
                                "stun:stun.example.org:3478",
                                "use one STUN server",
                            ),
                            Example(
                                "hmz settings set ice_servers - < servers.json",
                                "read the servers, credentials included, from "
                                "a JSON file",
                            ),
                        ),
                        run=_ice_servers,
                    ),
                    _set(
                        "backup",
                        "write every backup target and the defaults from JSON",
                        says="Writes the whole `backup` setting, replacing "
                        "every target and the defaults. A target whose "
                        "`url` is the one `hmz settings get backup` "
                        "printed keeps the URL written, credentials "
                        "included.",
                        args=(
                            Arg(
                                ("value",),
                                "a JSON object of `targets` and `defaults`, "
                                "as `hmz settings get backup --json` prints "
                                "under `backup`; `-` reads it from standard "
                                "input",
                            ),
                        ),
                        examples=(
                            Example(
                                'hmz settings set backup \'{"targets": [], '
                                '"defaults": []}\'',
                                "remove every backup target",
                            ),
                            Example(
                                "hmz settings set backup - < backup.json",
                                "write the backup targets from a JSON file",
                            ),
                        ),
                        run=_backup,
                    ),
                    _set(
                        "backup.target",
                        "add, change or remove one backup target",
                        says="Adds a backup target, or changes the one of that "
                        "name; what is not given stays as it was, and a "
                        "new target starts on the branch `main`, backed "
                        "up by hand only. The other targets are kept.",
                        args=(
                            Arg(("name",), "name of the backup target"),
                            Arg(
                                ("--url",),
                                "the git repository, as a URL git pushes to; "
                                "needed for a new target",
                                metavar="URL",
                            ),
                            Arg(
                                ("--branch",), "the branch pushed to", metavar="BRANCH"
                            ),
                            Arg(
                                ("--policy",),
                                "when it is backed up to unasked: `session` "
                                "on session close, `interval` every N "
                                "minutes, `end` on epic end, or `manual` for "
                                "by hand only",
                                metavar="POLICY",
                                many=True,
                                choices=(*_POLICIES, "manual"),
                            ),
                            Arg(
                                ("--every",),
                                "minutes between backups under the `interval` policy",
                                metavar="N",
                                kind=int,
                            ),
                            Arg(
                                ("--default",),
                                "back new epics up to it unless they say otherwise",
                            ),
                            Arg(
                                ("--no-default",),
                                "stop backing new epics up to it by default",
                            ),
                            Arg(("--remove",), "remove the target instead"),
                        ),
                        examples=(
                            Example(
                                "hmz settings set backup.target lab --url "
                                "git@github.com:you/epics.git --policy "
                                "session --policy end --default",
                                "add the target `lab`, backed up to on "
                                "session close and on epic end, as a default",
                            ),
                            Example(
                                "hmz settings set backup.target lab --policy "
                                "interval --every 30",
                                "back `lab` up every 30 minutes instead",
                            ),
                            Example(
                                "hmz settings set backup.target lab --remove",
                                "remove the target `lab`",
                            ),
                        ),
                        methods=("settings.get", "settings.set"),
                        run=_target,
                    ),
                    _set(
                        "backup.defaults",
                        "set the backup targets a new epic goes to",
                        args=(
                            Arg(
                                ("name",),
                                "name of a backup target; none given means a new "
                                "epic is backed up nowhere by default",
                                many=True,
                            ),
                        ),
                        examples=(
                            Example(
                                "hmz settings set backup.defaults lab",
                                "back new epics up to the target `lab`",
                            ),
                            Example(
                                "hmz settings set backup.defaults",
                                "back new epics up to no target by default",
                            ),
                        ),
                        methods=("settings.get", "settings.set"),
                        run=_defaults,
                    ),
                ),
            ),
            Command(
                "forget",
                "forget what a workspace was set up with",
                says="Forgets the flow a workspace opens on and how every flow "
                "was set up there. Where no epic ran there, the workspace "
                "also stops being offered.",
                args=(
                    Arg(
                        ("-w", "--workspace"),
                        "the workspace folder, as a path",
                        metavar="PATH",
                        required=True,
                    ),
                ),
                examples=(
                    Example(
                        "hmz settings forget -w ~/project",
                        "forget how the flows of `~/project` were set up",
                    ),
                ),
                prints="`Forgotten.`, or `Nothing to forget.` where nothing was "
                "set up there.",
                output=(
                    Field("forgot", "boolean", "whether there was anything to forget"),
                    *FIELDS,
                ),
                methods=("settings.forget",),
                see=("settings get",),
                run=_forget,
            ),
        ),
    ),
)
