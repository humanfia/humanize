"""What the stand-in CLIs refuse, which is the half of a stand-in that catches drift.

Every backend here is driven in tests against a stand-in written onto PATH that prints what
the real CLI prints. A stand-in that prints the right events and takes *any* flag at all can
only catch a driver that stopped reading; it cannot catch a driver that goes on saying
something the CLI dropped. Both of the bugs this suite let through were of the second kind:
pi removed `partial` from its wire events in 0.84.0 and the stand-in went on printing the old
shape, and the Antigravity driver carried a comment saying `agy` refuses `--effort` while
1.2.2 requires it -- and the stand-in, which took every flag, had nothing to say about
either. So a stand-in starts by refusing the command line its CLI would refuse.

The tables are read off `--help` of the version named beside each one, which is the version
installed here. A flag carries a trailing `=` when the real parser consumes the next word as
its value, because that is the one case where a word starting with `--` is not a flag at all.
A flag whose value is optional -- `--resume [id]`, which every one of these parsers takes the
next word for only when that word is not itself a flag -- is written without one, so a flag
following it is still read as a flag.

A refusal is said the way that CLI's own parser says it: on stderr, and with the status it
stops on. A driver reading a refusal reads what the CLI wrote, so a stand-in refusing in its
own words would be teaching the suite a diagnostic nobody will ever see.
"""

from __future__ import annotations

#: How each of the five parsers behind these CLIs refuses a flag it has not got: what it
#: writes on stderr, and what it exits with -- given the flag's name with its dashes off,
#: because they do not agree about those either. Node's commander and Rust's clap disagree
#: about the status too -- 1 and 2 -- and a suite that pinned one number for all of them
#: would be pinning something no CLI here promises.
_REFUSALS = {
    "commander": ("error: unknown option '--%s'", 1),
    "clap": ("error: unexpected argument '--%s' found", 2),
    "yargs": ("Unknown argument: %s", 1),
    "goflag": ("flags provided but not defined: -%s", 2),
    "pi": ("Error: Unknown option: --%s", 1),
}

#: Every flag each CLI takes, per command line it is reached on: "" is the CLI with no
#: subcommand, and any other key is the subcommand that comes first in argv. A command line
#: under a subcommand this says nothing about is left alone rather than refused -- what is
#: written here is what has been read off a real `--help`, and a stand-in must not refuse on
#: a guess.
_FLAGS: dict[str, tuple[str, dict[str, str]]] = {
    # agy 1.2.3, which is what is installed here; the driver was aligned to 1.2.2, and this
    # is the list as 1.2.3 prints it. Its Go parser stops reading flags at the first word
    # that is not one. The driver's reason for being here at all: `--effort` is documented,
    # and a model whose name carries no rung fails every turn without it.
    "agy": (
        "goflag",
        {
            "": """
            --add-dir= --agent= --continue --conversation= --dangerously-skip-permissions
            --disable-slash-commands --effort= --input-format= --json-schema= --log-file=
            --mode= --model= --new-project --output-format= --print= --print-timeout=
            --project= --prompt= --prompt-interactive= --sandbox
            """,
        },
    ),
    # claude 2.1.273. `--permission-prompt-tool` is not in the options list and is taken all
    # the same -- the help names it only inside the text of `--permission-prompts`, and
    # 2.1.273 runs a turn given it. A flag left out of a table it belongs in is a red test
    # nobody caused, so a flag the help does not list is checked against the CLI itself.
    "claude": (
        "commander",
        {
            "": """
            --add-dir= --agent= --agents= --allow-dangerously-skip-permissions
            --allowed-tools= --allowedTools= --append-system-prompt= --autocompact=
            --ax-screen-reader --background --bare --betas= --bg --brief --chrome --cloud
            --continue --dangerously-skip-permissions --debug --debug-file=
            --disable-slash-commands --disallowed-tools= --disallowedTools= --effort=
            --environment= --exclude-dynamic-system-prompt-sections --fallback-model=
            --file= --fork-session --forward-subagent-text --from-pr --help --ide
            --include-hook-events --include-partial-messages --input-format= --json-schema=
            --max-budget-usd= --mcp-config= --model= --name= --no-chrome
            --no-session-persistence --output-format= --permission-mode=
            --permission-prompt-tool= --permission-prompts= --plugin-dir= --plugin-url=
            --print --prompt-suggestions --remote-control
            --remote-control-session-name-prefix= --replay-user-messages --restricted
            --resume --safe-mode --session-id= --setting-sources= --settings=
            --strict-mcp-config --system-prompt= --system-prompt-snapshot= --teleport --tmux
            --tools= --verbose --version --worktree
            """,
        },
    ),
    # codex-cli 0.153.4, as its app server rather than as `codex exec`: the app server is the
    # only command line humanize builds, and the two do not share an option.
    "codex": (
        "clap",
        {
            "app-server": """
            --analytics-default-enabled --code-mode-host= --config= --disable= --enable=
            --help --listen= --stdio --strict-config --ws-audience= --ws-auth= --ws-issuer=
            --ws-max-clock-skew-seconds= --ws-shared-secret-file= --ws-token-file=
            --ws-token-sha256=
            """,
        },
    ),
    # cursor-agent 2026.09.08.
    "cursor-agent": (
        "commander",
        {
            "": """
            --add-dir= --api-key= --approve-mcps --auto-review --continue --endpoint=
            --force --header= --help --list-models --mode= --model= --output-format= --plan
            --plugin-dir= --print --resume --sandbox= --skip-worktree-setup
            --stream-partial-output --trust --version --workspace= --worktree
            --worktree-base= --yolo
            """,
        },
    ),
    # grok 1.0.24. `grok agent` is a command of its own with options of its own: `--tools`
    # and `--disable-web-search` are refused there, which is the whole reason the driver
    # sends the rungs that need them to the command line instead. `--yolo` is on neither
    # help and taken by both, which is why the driver says `--always-approve`.
    "grok": (
        "clap",
        {
            "": """
            --agent= --agents= --allow= --allowedTools= --always-approve --continue --cwd=
            --debug --debug-file= --deny= --disable-web-search --disallowed-tools=
            --disallowedTools= --effort= --fork-session --fullscreen --help
            --include-partial-messages --json-schema= --leader-socket= --max-turns=
            --minimal --model= --no-alt-screen --no-plan --no-subagents --oauth
            --output-format= --permission-mode= --prompt-file= --prompt-json=
            --reasoning-effort= --ref= --restore-code --resume --rules= --sandbox=
            --session-id= --single= --system-prompt= --system-prompt-override= --tools=
            --verbatim --version --worktree --worktree-ref= --yolo
            """,
            "agent": """
            --agent-profile= --always-approve --cli-chat-proxy-base-url= --debug
            --debug-file= --effort= --grok-ws-origin= --grok-ws-url= --help --leader
            --leader-socket= --model= --no-leader --plugin-dir= --reasoning-effort=
            --reauth --xai-api-base-url= --yolo
            """,
        },
    ),
    # kimi 0.42.0. Only the fork is driven through a stand-in installed from here; the web
    # server and the updater have stand-ins of their own, under the tests that drive them.
    "kimi": (
        "commander",
        {
            "": """
            --add-dir= --agent= --agent-file= --auto --continue --help --model=
            --output-format= --plan --prompt= --session --skills-dir= --version --yolo
            """,
            "fork": "--cwd= --help --yes",
        },
    ),
    # mimo 0.1.14, which is opencode's CLI under Xiaomi's name and not the same list: it has
    # `--dangerously-skip-permissions` where opencode has `--auto`, and has neither
    # `--interactive` nor `--username`. One stand-in script stands in for both, so each is
    # installed knowing which of the two it is -- that difference is a rung's whole saying.
    "mimo": (
        "yargs",
        {
            "run": """
            --agent= --attach= --command= --continue --dangerously-skip-permissions --dir=
            --file= --fork --format= --help --log-level= --model= --password= --port
            --print-logs --pure --role= --session= --share --thinking --title --variant=
            --version --yolo
            """,
        },
    ),
    # opencode 1.18.30.
    "opencode": (
        "yargs",
        {
            "run": """
            --agent= --attach= --auto --command= --continue --dir= --file= --fork --format=
            --help --interactive --log-level= --model= --password= --port --print-logs
            --pure --session= --share --thinking --title --username= --variant= --version
            """,
        },
    ),
    # pi 0.85.1. Extensions register flags of their own -- `--plan` comes from one -- so
    # this is what a pi with none loaded takes, which is what a turn here is run against.
    "pi": (
        "pi",
        {
            "": """
            --api-key= --append-system-prompt= --approve --continue --exclude-tools=
            --export= --extension= --fork= --help --list-models --mode= --model= --models=
            --name= --no-approve --no-builtin-tools --no-context-files --no-extensions
            --no-prompt-templates --no-session --no-skills --no-themes --no-tools --offline
            --print --prompt-template= --provider= --resume --session= --session-dir=
            --session-id= --skill= --system-prompt= --theme= --thinking= --tools=
            --tui-mode= --use-theme= --verbose --version
            """,
        },
    ),
    # qwen 0.23.1.
    "qwen": (
        "yargs",
        {
            "": """
            --acp --add-dir= --allowed-mcp-server-names= --allowed-tools=
            --append-system-prompt= --approval-mode= --auth-type= --bare --chat-recording
            --continue --core-tools= --debug --disabled-slash-commands= --exclude-tools=
            --experimental-lsp --extensions= --fallback-model= --fork-session --help
            --include-directories= --include-partial-messages --input-file= --input-format=
            --insecure --json-fd= --json-file= --json-schema= --list-extensions
            --max-session-turns= --max-subagent-depth= --max-tool-calls= --max-wall-time=
            --mcp-config= --model= --openai-api-key= --openai-base-url= --openai-logging
            --openai-logging-dir= --output-format= --output-style= --prompt=
            --prompt-interactive= --proxy= --restore-ask-user-question --resume=
            --safe-mode --sandbox --sandbox-image= --screen-reader --session-id=
            --system-prompt= --telemetry --telemetry-log-prompts --telemetry-otlp-endpoint=
            --telemetry-otlp-protocol= --telemetry-outfile= --telemetry-target= --version
            --worktree --yolo
            """,
        },
    ),
}

#: The refusal itself, which runs before the stand-in has read a byte or written a line --
#: the real CLI has started neither by the time its parser gives up. A word is read as a flag
#: only while it opens with two dashes and nothing before it has ended option parsing, which
#: is what a bare `--` does on every one of these.
_SOURCE = """
import sys as _refusing_sys


def _refusing(tables, saying, status):
    argv = _refusing_sys.argv[1:]
    known = tables.get(argv[0] if argv and not argv[0].startswith("-") else "")
    if known is None:
        return  # a command line no table here was read off a --help for
    index = 0
    while index < len(argv):
        word, index = argv[index], index + 1
        if word == "--":
            return
        if not word.startswith("--"):
            continue
        name = word.partition("=")[0]
        if name not in known:
            print(saying % name.lstrip("-"), file=_refusing_sys.stderr)
            raise SystemExit(status)
        if known[name] and "=" not in word:
            index += 1  # the next word is this flag's value, whatever it starts with
"""


def refusing(cli: str) -> str:
    """The Python a stand-in for `cli` opens with, refusing what that CLI refuses.

    Args:
      cli: What the stand-in is installed on PATH as, which for opencode and mimocode is the
        only thing telling their one script which of the two CLIs it is standing in for.

    Returns:
      Source to put above the stand-in's own, which exits the way that CLI exits on a flag it
      has not got and returns quietly on a command line it would take.
    """
    parser, tables = _FLAGS[cli]
    saying, status = _REFUSALS[parser]
    taken = {
        where: {word.rstrip("="): word.endswith("=") for word in flags.split()}
        for where, flags in tables.items()
    }
    return f"{_SOURCE}\n_refusing({taken!r}, {saying!r}, {status!r})\n"
