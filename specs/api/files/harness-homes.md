# Harness Homes

## 1. Scope

This document specifies the files and directories **hmz** creates for a **harness** process on
its **harness machine**, and the files of the home directory of a **harness** that **hmz** reads,
keeps elsewhere or never writes: the virtual config homes, the account directories, the
redirection of **sessions** into an **epic**, and the process-private temporary directories of a
**harness** process.

Out of scope:

- The definitions and rules common to `api/files/`: `api/files/home.md` §2 and §3, and
  `api/files/machine.md` §2.
- The layout of an epic directory: `api/files/epics.md`.
- How a **harness** is driven, and which **harness** supports which feature:
  `features/agents.md`.
- How an **account** is created and signed in: `features/accounts.md`.
- Files on a **machine** on which only an **env** runs: `api/files/targets.md`.

## 2. Definitions

**2.1** **Harness home**: the directory in which a **harness** keeps its configuration,
credentials and **sessions**, located for each **harness** as clause 3.1 states.

**2.2** **Real harness home**: the harness home that the environment of the **user** locates,
outside any directory **hmz** creates.

**2.3** **User configuration file**: a file of the real harness home, or a file in the home
directory of the **user** that a **harness** reads as its configuration, that holds settings,
model or provider declarations, agents, commands, skills, hooks or tool servers.

**2.4** The term managed item MUST carry the meaning `features/agents.md` §2.9 gives it.

**2.5** **Virtual config home**: a process-private temporary directory on the **harness machine**
that **hmz** creates for one **harness** process and that the process uses as its harness home.

**2.6** **Kept path**: a path, relative to the harness home, at which a **harness** writes the
files of its **sessions**.

## 3. Real harness homes

**3.1** The real harness home of each **harness** MUST be located by the variable and default
below, where a variable that is set names the directory, `<var>/<sub>` where a sub-directory is
stated, and the default applies under `$HOME` otherwise:

- `claude`: `CLAUDE_CONFIG_DIR`, default `~/.claude`;
- `codex`: `CODEX_HOME`, default `~/.codex`;
- `dsh`: `DSH_HOME`, default `~/.dsh`;
- `grok`: `GROK_HOME`, default `~/.grok`;
- `kimi`: `KIMI_CODE_HOME`, default `~/.kimi-code`;
- `pi`: `PI_CODING_AGENT_DIR`, default `~/.pi/agent`;
- `omp`: `PI_CODING_AGENT_DIR`, default `~/.omp/agent`;
- `qwen`: `QWEN_HOME`, default `~/.qwen`;
- `opencode`: `XDG_DATA_HOME` with sub-directory `opencode`, default `~/.local/share/opencode`;
- `mimo`: `XDG_DATA_HOME` with sub-directory `mimocode`, default `~/.local/share/mimocode`;
- `cursor-agent`: `CURSOR_CONFIG_DIR`, default `~/.cursor`;
- `mcode`: `MINIMAX_DATA_DIR`, default `~/.minimax`;
- `agy`: no variable, default `~/.gemini/antigravity-cli`;
- `litellm`: no variable, default `~/.cache/humanize/litellm`.

**3.2** `hmz` MUST NOT create, modify, replace or remove any user configuration file, on any
**machine**.

**3.3** Clause 3.2 applies in particular to `~/.claude.json`, every file under `~/.claude/`,
`~/.codex/config.toml`, `~/.grok/config.toml`, `~/.pi/agent/models.json`,
`~/.omp/agent/models.yml`, the `config.yaml` of MiniMax Code, every file under
`~/.gemini/antigravity-cli/agents/`, and the settings files of Qwen Code, opencode, MiMo Code,
Kimi Code and Cursor Agent.

**3.4** `hmz` MUST NOT write credentials into a real harness home, except where the **user** signs
a **harness** in outside any **account** and the **harness** itself writes them.

**3.5** Where a **session** is not kept in an **epic** (§5.6), the **harness** MUST write it at its
kept paths in the real harness home, and `hmz` MAY copy into those paths the files of a
**session** that it forks or carries on.

## 4. Account directories

**4.1** The account directory `<home>/providers/<cli>/<name>/` (`api/files/home.md` §7) MUST hold
`provider.json`, and MAY hold the directories `home/`, `user/` and `config/`, each of mode
`0700`.

**4.2** `provider.json` MUST be a JSON object with the keys `cli` (string), `name` (string),
`way` (string, the sign-in way, default `env`), `env` (object mapping a variable name to a string
value), `args` (array of strings) and `made` (string, `YYYY-MM-DDTHH:MM:SSZ`), with mode
`0600`, written by atomic replacement.

**4.3** A reader of `provider.json` MUST take `cli` and `name` from the path where they differ
from the file, and MUST ignore the key `fallback`.

**4.4** `home/<path>` MUST hold a credential file the **harness** writes at `<path>` relative to
its harness home, `user/<path>` one it writes at `<path>` relative to `~`, and `config/<path>`
one it writes at `<path>` relative to `${XDG_CONFIG_HOME:-~/.config}`, each written by the
**harness** itself while it runs under the **account**.

**4.5** The credential files of each **harness** MUST be these, and no others:

- `claude`: `home/.credentials.json`, `home/.claude.json`, `user/.claude.json`,
  `config/anthropic`;
- `codex`: `home/auth.json`;
- `agy`: `home/antigravity-oauth-token`;
- `grok`: `home/auth.json`, `home/mcp_credentials.json`;
- `kimi`: `home/credentials`, `home/oauth`;
- `pi`: `home/auth.json`, `home/auth.json.lock`;
- `opencode`, `mimo`: `home/auth.json`, `home/mcp-auth.json`;
- `cursor-agent`: `home/cli-config.json`, `config/cursor/auth.json`, `user/.cursor/auth.json`;
- `mcode`: `home/config.yaml`, `home/auth`;
- `dsh`, `omp`, `qwen`, `litellm`: none.

**4.6** Where `hmz` stages copies of credential files for a **harness** process on Linux, it MUST
place them in `/dev/shm/hmz-<pid>-<16 hexadecimal digits>-<random>/` of mode `0700`, as files
`<n>.<name>` of mode `0600` no larger than 1 MiB each, where `<pid>` is the process that staged
them.

**4.7** `hmz` MUST use a staged copy of clause 4.6 only to answer a read of the **harness** process,
and MUST take it afresh from the credential file of the **account** once that file changes.

**4.8** Every write of a **harness** process to a credential file of which `hmz` staged a copy MUST
reach the credential file of the **account** at once, and MUST NOT reach the staged copy.

**4.9** `hmz` MUST NOT write a staged copy back to the credential file of the **account**.

**4.10** `hmz` MUST remove a staging directory of clause 4.6 when the process that staged it ends,
and MUST remove every such directory of the **user** whose `<pid>` no longer runs before it
creates another.

**4.11** Where a **harness** runs under an **account** under harness location env on a **machine**
other than **this machine**, `hmz` MUST place copies of the credential files on that **machine**
as `api/files/targets.md` §8 states.

**4.12** Under harness location standalone, `hmz` MUST NOT place any credential file of an
**account** on the **harness machine** (`features/placements.md` §5.3.3).

## 5. Sessions kept in an epic

**5.1** For a **session** kept in an **epic**, `hmz` MUST make the **harness** process read and
write each kept path at `<epic>/sessions/<cli>/<kept path>` instead of in its harness home.

**5.2** The kept paths of each **harness** MUST be these:

- `claude`: `projects`, `sessions`, `file-history`, `session-env`, `tasks`, `todos`, `plans`;
- `codex`: `sessions`, `archived_sessions`, `session_index.jsonl`, `state_*.sqlite*`,
  `thread_history_*.sqlite*`, `goals_*.sqlite*`, `queue_*.sqlite*`, `memories_*.sqlite*`,
  `thread-writer-locks`, `shell_snapshots`;
- `agy`: `conversations`, `brain`, `annotations`, `implicit`, `presence`,
  `conversation_summaries.db*`, `jetbox_summaries_proto.pb`, `cache/last_conversations.json`;
- `dsh`: the whole harness home, named to the **harness** in `DSH_HOME`;
- `grok`: `sessions`, `active_sessions.*`;
- `kimi`: `sessions`, `session_index.jsonl`, `workspaces.json`, `server/events`,
  `search-index`, `file-history`;
- `pi`, `omp`: `sessions`;
- `qwen`: `projects`, `tmp`, `file-history`;
- `opencode`: `opencode.db*`, `storage`;
- `mimo`: `mimocode.db*`, `storage`;
- `cursor-agent`: `chats`, `projects/*/agent-transcripts`;
- `mcode`: `v2/sqlite`, `v2/sessions`, `background-tasks`;
- `litellm`: `sessions`, written by **hmz** as `api/files/machine.md` clause 9.9 states.

**5.3** `hmz` MUST NOT change the paths of a **harness** process other than its kept paths, its
harness home (§6) and its credential files (§4).

**5.4** Where a fenced `mcode` process runs whose **session** is not kept, `hmz` MUST place the
lock file of MiniMax Code in `<mdir>/mcode/`.

**5.5** For a side question that recalls a **session** of an earlier **epic**, `hmz` MUST keep its
**sessions** in the directory of `api/files/machine.md` clause 7.5, and MUST NOT write them into
the earlier **epic**.

**5.6** `hmz` MUST NOT keep a **session** in an **epic**, other than one of `dsh` or `litellm`,
where the **harness machine** can neither supervise the **harness** process nor link its kept
paths as clause 5.7 states, where the **harness machine** is not **this machine**, where
`HUMANIZE_SESSIONS` is `off`, `0` or `no`, or where the **agent** is driven outside any
**epic**.

**5.7** Where **this machine** cannot supervise a **harness** process that runs in a virtual config
home (§6) and whose kept paths are each a name directly under its harness home, `hmz` MUST keep
its **session** in the **epic** through that virtual config home instead:

- each kept path that is not a glob MUST be a symbolic link to `<epic>/sessions/<cli>/<kept
  path>`, that directory being created where the kept path is one, and no file being created
  where it is one;
- each entry of the real harness home or of `<epic>/sessions/<cli>/` whose name matches a kept
  path that is a glob MUST be a symbolic link to `<epic>/sessions/<cli>/<name>`, whether or not
  that file exists there;
- where the process creates a file in the virtual config home whose name matches a kept path
  that is a glob, `hmz` MUST move it into `<epic>/sessions/<cli>/` when it removes the virtual
  config home, unless a file of that name is there already.

## 6. Virtual config homes

**6.1** For each process of the **harnesses** `claude`, `codex` and `qwen`, and for each process
of the **harnesses** `grok`, `pi`, `omp`, `mcode`, `agy`, `cursor-agent` and `kimi` to which
**hmz** adds a managed item, `hmz` MUST create a virtual config home on the **harness machine**
before the process starts, as `features/agents.md` §5.2 states.

**6.2** A virtual config home MUST be a directory under the temporary directory of the **harness
machine**, of mode `0700`, owned by the **user** the **harness** process runs as.

**6.3** A virtual config home MUST hold a copy of each configuration file of the real harness home
that the **harness** rewrites while running, merged with the managed items of the process, a
user-level skills directory holding the **user**'s skills and the flow's, the symbolic links of
clause 5.7 where that clause applies, and a symbolic link to each other entry of the real harness
home.

**6.4** `hmz` MUST NOT copy a credential file into a virtual config home; the virtual config home
MUST reach each credential file of the **account** through a symbolic link or through the
redirection of §4.

**6.5** `hmz` MUST make the **harness** process use the virtual config home as its harness home,
through the variable of clause 3.1 or a command-line argument of the **harness**.

**6.6** `hmz` MUST remove a virtual config home when its **harness** process exits, and MUST NOT
reuse it for another process.

**6.7** A change a **harness** process makes to a copied user configuration file MUST remain in
the virtual config home and MUST NOT reach the real harness home.

**6.8** A write a **harness** process makes through a symbolic link of clause 6.3 MUST reach the
real harness home, or the **epic** where the link is one of clause 5.7.

**6.9** Where a **harness** process replaces a symbolic link of clause 6.3 with a file or a
directory, `hmz` MUST, when the process exits, write that file, or each new or changed file of
that directory, to the entry the link named, or to the **account**'s file where §4 redirects it,
unless that entry is at least as new.

**6.10** `hmz` MUST deliver every managed item to a **harness** process only through its virtual
config home, its command-line arguments, its environment, or a process-private temporary
directory of §7.

## 7. Process-private temporary directories of a harness process

**7.1** `hmz` MUST create the directories of this section on the **harness machine** with mode
`0700`, and MUST remove each when the **agent** or **session** it serves ends. A directory of
§7.2 to §7.5 MUST be created in `/tmp` rather than `<tmp>` where the path of its socket would
otherwise be longer than 103 bytes and `/tmp` is writable.

**7.2** A directory with the prefix `humanize-hook-` MUST hold the Unix-domain socket `hook.sock`
on which the hooks of a **harness** process report to **hmz**.

**7.3** A directory with the prefix `humanize-tools-` MUST hold the Unix-domain socket
`tools.sock` through which a **harness** process calls the tools a **flow** defines.

**7.4** A directory with the prefix `humanize-preload-` MUST hold the Unix-domain socket
`said.sock` on which a **harness** process reports what it does.

**7.5** A directory with the prefix `humanize-clis-` MUST hold the Unix-domain socket `cli.sock`
and the directory `bin/`, holding one executable shell script of mode `0700` for each command
line a **flow** defines; `hmz` MUST prepend `bin/` to the `PATH` of the **harness** process.

**7.6** A directory with the prefix `hmz-dsh-` MUST hold `humanize.patch.yml`, the configuration
patch of one `dsh` process.

**7.7** A directory with the prefix `hmz-gateway-` MUST hold `config.yaml`, of mode `0600`, the
configuration of one LiteLLM gateway process, including the credentials of its **account**.

**7.8** A directory with the prefix `hmz-fence-` MUST be the temporary directory of a fenced
process, named to it in `TMPDIR`, `TMP` and `TEMP`, and MAY hold `cache/<variable>/` for each
cache variable whose usual location the fence does not let the process write.

**7.9** A directory with the prefix `hmz-homes-` MUST hold, for each turn of a **harness** that runs
under harness location env on another **machine** under an **account**, one file named by 32 lowercase
hexadecimal digits whose lines are `<VARIABLE>=<path>`, naming the directory on that **machine** in
which each harness home variable of the turn points; `hmz` MUST remove each such file when its turn
ends.

**7.10** The **user** MUST NOT delete a directory of §6 or §7 while its process runs, and MAY
delete it after that process ends.
