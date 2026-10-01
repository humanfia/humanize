---
pageClass: hmz-feature
---

# Remote execution

Reference for anchoring: how a turn whose work lands on another machine is run, where each
part of it runs, what crosses between machines, and what is refused. The layer is
`hmz.coganchor.anchor` and its command line is `hmz internal anchor`. Where an agent's turns
land is set per agent by [`machine=`](/reference/machines) and per flow session by its
[environment](/reference/machines#where-a-flow-s-agents-work); where the harness runs is set per
run by `-H` ([below](#where-the-harness-runs)).

## Terms

| Term | Definition |
| --- | --- |
| **Anchor** | The settings that send one agent's turns to another machine: an [`AnchorConfig`](#anchorconfig). An agent with no anchor runs its turns on this machine as ordinary processes. |
| **Target** | The machine the work lands on: the files the agent reads and writes and the commands it runs. Named by a [target spelling](#targets). |
| **Serving half** | `hmz internal anchor serve`, running on the target. It answers file operations and runs commands inside the directories it exports. |
| **Harness** | The agent's own process (the coding agent CLI) and, when supervised, the supervisor tracing it. |
| **Supervisor** | A seccomp-filtered ptrace tracer that stops the agent's path, exec and connect syscalls and answers them from the target. |
| **Mirror** (shadow) | A directory on the harness's machine that reproduces the target's workspace, filled lazily. The supervised agent works in it. |
| **Arrangement** | Which of supervised, afar or native a turn is: where the harness runs relative to the target. |
| **Broker** (rendezvous) | A TCP server that introduces a harness and a serving half on two machines that cannot dial each other, and relays their bytes when no direct connection can be made. |
| **Ticket** | A 128-bit secret naming one meeting at a broker. |
| **Export** | A directory the serving half exposes, as `VIRTUAL[:REAL]`: the path the agent names, and where it really is on the target. |
| **Fence** | What an agent's processes may reach ([Agents › The fence](/reference/agents#the-fence)). Under an anchor it is held on both machines ([below](#a-fence-on-both-machines)). |

## Arrangements {#the-arrangements}

Two fields decide the arrangement: `native` and `harness`.

| | Supervised | Afar, beside the work | Afar, third machine | Native |
| --- | --- | --- | --- | --- |
| **Setting** | `harness="local"` (default), `native=False` | `harness="same"`, or a harness target equal to `target` | `harness=` an `ssh://` or `docker://` target other than `target` | `native=True` |
| **Agent process and supervisor** | this machine | the target | the harness machine | none: the target's installed CLI runs there |
| **Mirror** | this machine, at `shadow` (default: the workspace's own path) | the target, in its mirror cache, kept between turns | the harness machine, in its mirror cache, kept between turns | none |
| **Account, CLI state, model connection** | this machine | the target | the harness machine | the target, for each turn |
| **What crosses to this machine** | one request per trapped syscall, file contents, command I/O | the agent's stdin, stdout, stderr | the agent's stdin, stdout, stderr; file work goes between the other two through a [rendezvous](#being-introduced) | the CLI's stdin, stdout, stderr, signals, exit status |
| **Capabilities** | `anchor:supervised` | `anchor:supervised`, `anchor:afar` | `anchor:supervised`, `anchor:afar` | `anchor:native-cli` |

- `native=True` with a harness that parses to a non-`local` machine is refused (see
  [Validation](#validation)).
- A `harness` whose spelling resolves to a `local` target (`local`, `local:DIR`, or `same` with
  a `local` target) is the supervised arrangement: `AnchorConfig(target="local:/x",
  harness="same").capabilities` is `{"anchor:supervised"}`.
- `AnchorConfig.capabilities` is computed from the settings alone; nothing connects.

```text
supervised                          native
this machine        target          this machine          target
+-------------+     +-----------+    +---------------+    +-------------+
| agent CLI   |     |           |    | hmz internal  |    | agent CLI   |
|  | syscalls |     | anchor    |    | anchor        |--->|  files,     |
| supervisor -+---->| serve     |    | --native      |    |  commands,  |
| mirror      |     | files,    |    |  3 streams    |    |  network    |
+-------------+     | commands  |    +---------------+    +-------------+
                    +-----------+

afar, third machine
this machine            harness machine            target
+----------------+      +-------------------+      +--------------+
| hmz internal   |----->| agent CLI         |      | anchor serve |
| anchor         | ssh/ | supervisor -------+----->| files,       |
|  3 streams     |docker| mirror (kept)     | peer | commands     |
| broker         |<-----+-------------------+------+              |
+----------------+      +-------------------+      +--------------+
```

<small>Defined in [`src/hmz/coganchor/anchor.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/anchor.py) (`AnchorConfig.capabilities`), [`src/hmz/coganchor/places.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/places.py), [`src/hmz/coganchor/elsewhere.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/elsewhere.py).</small>

## Targets {#targets}

A target spelling names the machine the work lands on. The same grammar names a harness
machine in `AnchorConfig.harness`.

| Spelling | Machine | How it is reached | Something started on it | Requirements there |
| --- | --- | --- | --- | --- |
| `local` | this machine, standing in for another | the serving half is a child process here | yes | none |
| `local:DIR` | this machine, with `DIR` standing in for the far side's copy of the workspace | as `local` | yes | none |
| `ssh://[USER@]HOST[:PORT][?KEYWORD=VALUE&...]` | a host reached with the system `ssh` | the serving half is bootstrapped over `ssh` and spoken to on its pipes | yes | POSIX `/bin/sh`, Python >= 3.12 |
| `docker://CONTAINER[@ENDPOINT]` | a running container | the serving half is bootstrapped with `docker exec -i`, running as the container's user | yes | `docker` here; `/bin/sh` and Python >= 3.12 in the container |
| `tcp://HOST:PORT` | a serving half [left listening](#serving-a-target) | a TCP connection, `TCP_NODELAY`, 30 s connect timeout | no | a served target and its token |
| `peer://TICKET@HOST:PORT` | a serving half waiting at a broker | the broker at `HOST:PORT`, presenting `TICKET` | no | written by humanize only |

Parsing rules:

- `ssh://`: the authority is split at its last `:` into host and port when the part after it is
  all digits; otherwise the whole authority is the host (`user@host` included). After `?`,
  options are `KEYWORD=VALUE` pairs separated by `&`, URL-quoted, parsed strictly. `KEYWORD`
  matches `[A-Za-z][A-Za-z0-9]*`; `VALUE` must be non-empty and must not contain a newline,
  carriage return, NUL or `"`. Each option is passed to `ssh` as `-o KEYWORD=VALUE` (the value
  double-quoted where it contains whitespace), except `F`, passed as `-F VALUE`.
- `docker://`: the container name ends at the first `@`; the rest is a docker
  [endpoint](/reference/machines#endpoints). An endpoint of `local` is the same target as none.
- `tcp://`: `HOST:PORT` split at the last `:`; the port must be digits.
- `peer://`: `TICKET@HOST:PORT`; brackets around an IPv6 host are stripped.

| Input | `ValueError` message |
| --- | --- |
| an unknown scheme | `unsupported target 'bogus://x'; expected ssh://HOST, docker://CONTAINER[@ENDPOINT], tcp://HOST:PORT, peer://TICKET@HOST:PORT or local[:PATH]` |
| `tcp://` without a numeric port | `malformed target 'tcp://h'; expected tcp://HOST:PORT` |
| an ssh option that is not one | `malformed target 'ssh://h?Bad-Key=1'; Bad-Key='1' is not an ssh option` |
| an ssh query that does not parse | `malformed target '<spec>'; expected ssh://HOST?KEYWORD=VALUE&...` |
| a bad docker endpoint | `unsupported docker endpoint 'weird'; expected local, unix:///PATH, tcp://HOST:PORT[?tls=DIR], ssh://[USER@]HOST[:PORT][?KEYWORD=VALUE&...] or context:NAME` |
| a malformed meeting | `malformed meeting '<spec>'; expected TICKET@HOST:PORT` |

### Bootstrapping the serving half

For `local`, `ssh://` and `docker://`, humanize starts `hmz internal anchor serve --stdio
--export WORKSPACE[:REAL]` on the far side and speaks the protocol over its stdin and stdout.

| Step | Behaviour |
| --- | --- |
| Archive | A zipapp of `hmz.coganchor` and the command line reaching it, built once per source tree into `$TMPDIR/humanize-<uid>/humanize-<digest>.pyz` (directory `0700`, refused if anyone else can write it), beside a `<stamp>.digest` naming the archive each source tree (by path, file sizes and modification times) built. Two checkouts or versions never share an archive. A run touches the archive it uses at least hourly; a build removes anything in the directory, and the `$TMPDIR/humanize-<uid>.pyz` an earlier humanize shared, untouched for 14 days. A directory anyone else can write fails the install with `ConnectionError: could not install humanize on <target>: …`. The driving half (`agents`, `providers`, `machines`, `backends.py`, `models.py`, `fallbacks.py`, `prices.py`) is left out. Pure standard library; runs on any architecture. |
| Name on the target | `humanize-<digest>.pyz`, `<digest>` the first 16 hex digits of the archive's SHA-256. |
| Cache on the target | `$HOME/.cache/humanize/` over ssh, `/tmp/humanize/` in a container. |
| Install | Run with the interpreter below, `HUMANIZE_BUNDLES` set to the cache and `mkdir -p`'d by the far side's shell, the archive on stdin: refuse it (`humanize: <n> bytes arrived that are not humanize-<digest>.pyz`) unless its SHA-256 starts with `<digest>`; keep a file already there only if its own SHA-256 does too, touching it; otherwise write `<file>.<pid>` and move it into place. Then remove other `humanize-*.pyz*` in the cache untouched for 14 days. Every line that runs the archive first `touch -c`es it. Concurrent installs are safe. Each (target, digest) pair is pushed at most once per process. |
| Interpreter | The first candidate that exists and reports a version >= 3.12, tried in order: `python3`, `python3.14`, `python3.13`, `python3.12`, `/opt/homebrew/bin/python3`, `/usr/local/bin/python3`, `/Library/Frameworks/Python.framework/Versions/Current/bin/python3`, `/usr/bin/python3`. |
| No interpreter | Exit 127, stderr `humanize: no python 3.12 or newer on this machine; looked for: <candidates>`. |
| Install failure | `ConnectionError: could not install humanize on <target>: <stderr>`; for a container, `; the container said: <last 3 log lines>` is appended. |
| Protocol | Both halves send `PROTOCOL_VERSION` (currently `1`). A mismatch fails the handshake with `EPROTO`, `client speaks protocol <n>, this humanize speaks 1`, and closes the connection. |

The handshake reply (`Op.HELLO`) carries `version`, `hostname`, `platform` (`sys.platform`),
`python`, `pid`, `exports` (`[{virtual, real}]`) and `fence` (`{fs: bool, net: bool}`, see
[below](#a-fence-on-both-machines)). A token mismatch fails it with `EACCES`, `invalid token`.

### ssh connections

Every `ssh` humanize runs is:

```text
ssh <target options> -T -o BatchMode=no -o ServerAliveInterval=30 <reuse options> [-p PORT] HOST '<quoted command>'
```

- The target's own options come first; `ssh` keeps the first value it is given for a keyword.
- Reuse options, unless `HUMANIZE_SSH_REUSE` is `off`, `0`, `no` or `false` (trimmed,
  case-insensitive) or set and empty:
  `-o ControlMaster=auto -o ControlPersist=120 -o ControlPath=<dir>/%C[-<8 hex>]`, where
  `<dir>` is `$XDG_RUNTIME_DIR/humanize-ssh-<uid>` (else the system temporary directory), mode
  `0700`. The `-<8 hex>` suffix is a digest of the target's options, so two targets at one host
  with different options use different master connections.
- The command is sent as one string, each word shell-quoted, prefixed with `exec`.

<small>Defined in [`src/hmz/coganchor/transport.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/transport.py) (`Target`, `Road`, `python_command`, `build_bundle`), [`src/hmz/coganchor/proto.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/proto.py), [`src/hmz/coganchor/serve/server.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/serve/server.py).</small>

## `AnchorConfig` {#anchorconfig}

`hmz.coganchor.AnchorConfig` is a frozen, keyword-only dataclass. Every field is an option of
`hmz internal anchor`, and every option but `--check` and `--log-level` is a field;
`hmz.coganchor.argv` reads one into the other and renders it back
(`python -Pm hmz internal anchor <options> AGENT ARGS...`).

| Field | Type | Default | Option | Option default | Meaning |
| --- | --- | --- | --- | --- | --- |
| `target` | `str` | `"local"` | `--target URL` | `$HUMANIZE_TARGET`, else `local` | Where the work lands. See [Targets](#targets). |
| `harness` | `str` | `"local"` | `--harness WHERE` | `$HUMANIZE_HARNESS`, else `local` | Where the harness runs: `local`, `same` (the machine `target` names), or a target spelling. |
| `broker` | `str` | `""` | `--broker HOST` | `$HUMANIZE_RENDEZVOUS`, else `""` | The address both halves dial to be introduced. `""`: `$HUMANIZE_RENDEZVOUS`, else this machine's outward-facing IPv4 address. |
| `workspace` | `str \| None` | `None` | `--workspace PATH` | `None` | The project directory as the target names it. `None`: this process's working directory. |
| `chdir` | `str \| None` | `None` | `--chdir PATH` | `None` | Where inside the workspace the agent starts, as the target names it. Must be the workspace or under it. |
| `remote_path` | `str \| None` | `None` | `--remote-path PATH` | `None` | Where the workspace really is on the target, where that differs from `workspace` (the export's `REAL`). |
| `shadow` | `str \| None` | `None` | `--shadow PATH` | `$HUMANIZE_SHADOW` | The mirror directory on the harness's machine. `None`: the workspace path itself; for a harness elsewhere, a kept mirror under that machine's mirror cache. |
| `local_paths` | `tuple[str, ...]` | `()` | `--local-path PATH` (repeatable) | | Paths kept on this machine even inside the workspace. |
| `local_execs` | `tuple[str, ...]` | `()` | `--local-exec PATH` (repeatable) | | Programs under these paths run here, not on the target. |
| `private` | `tuple[str, ...]` | `()` | `--private NAME` (repeatable) | | Variables the agent has and the commands it runs on the target do not. |
| `redirects` | `tuple[tuple[str, str], ...]` | `()` | `--redirect FROM=TO` (repeatable) | | Paths answered with other paths, kept on this machine. A directory covers everything under it. |
| `net` | `str` | `"local"` | `--net {local,remote}` | `local` | Where the agent's own TCP connections go. Commands always use the target's network. |
| `net_allow` | `tuple[str, ...]` | `()` | `--net-allow HOST[:PORT]` (repeatable) | | With `net="remote"`, destinations kept local. |
| `token` | `str \| None` | `None` | `--token TOKEN` | `$HUMANIZE_TOKEN` | The secret a `tcp://` target requires. |
| `force` | `bool` | `False` | `--force` | | Use a mirror directory that holds unrelated files or was last used for another target. |
| `native` | `bool` | `False` | `--native` | | Run the CLI installed on the target. See [Native](#native-the-target-s-own-cli). |
| `hushes` | `tuple[str, ...]` | `()` | `--hush NAME` (repeatable) | | Native: variables removed from the CLI's environment on the target. |
| `projects` | `tuple[tuple[str, str], ...]` | `()` | `--project NAME=DIR` (repeatable) | | Native: credential directories written to the target for the turn; `NAME` is set to where each landed. |
| `carries` | `tuple[tuple[str, str], ...]` | `()` | `--carry DIR=PATH` (repeatable) | | Native: directories put into the target's workspace at `PATH` for the turn. |
| `installs` | `str` | `""` | `--installs LINE` | `""` | Native: the install line quoted when the CLI is missing on the target. |
| `fence` | `Fence \| None` | `None` | `--fence JSON` | `None` | What the agent may reach, held on both machines. `--fence` takes `Fence.dumps()` output. |

- `--log-level {debug,info,warning,error}` defaults to `$HUMANIZE_LOG`, else `warning`, and
  logs to stderr.
- The environment-variable defaults apply to the command line only. `check()`, `connect()` and
  `drive()` called in-process do not read `$HUMANIZE_TOKEN` or `$HUMANIZE_SHADOW`; a spawned
  turn is the rendered command line and does.
- A turn spawned from an agent is `AnchorConfig.command(argv, swaps=…, private=…, chdir=…)`:
  the provider's credential paths and kept session paths are added as `redirects`, the
  provider's variables as `private`, and the session's directory as `chdir`.

### Variables the agent is given

| Variable | Value | Arrangements |
| --- | --- | --- |
| `HUMANIZE` | the `hmz.coganchor` version | supervised, native |
| `HUMANIZE_TARGET` | the target, as `Target.describe()` spells it | supervised, native |
| `HUMANIZE_WORKSPACE` | the workspace, as `workspace` names it (absolute) | supervised, native |
| `PWD` | the mirror directory the agent starts in | supervised |

### Validation {#validation}

`AnchorConfig.__post_init__` raises `ValueError`; `hmz internal anchor` reports the same message
as a usage error and exits 2.

| Refused | Message |
| --- | --- |
| `target` or `harness` not a [target spelling](#targets) | the target parse message |
| `native=True` with a harness on another machine | `a native session has no harness to put anywhere: the CLI on the target is the one that runs, so --harness and --native ask for opposite things` |
| a `peer://` target with any `harness` but `local` | `a peer:// target is a meeting humanize books for a harness it is placing; naming both is naming the same introduction twice` |
| `net` not `local` or `remote` | `unsupported net 'X'; expected local or remote` (the option: `argument --net: invalid choice: …`) |
| a redirect that is not two absolute paths | `unsupported redirect 'a=b'; expected two absolute paths` |
| an empty hush, or one containing `=` | `unsupported hush 'A=B'; expected a variable name` |
| a projection without a variable name and an absolute path | `unsupported projection X='rel'; expected a variable name and an absolute path` |
| a carry whose source is not absolute | `unsupported carry rel='b'; expected an absolute path` |
| a carry whose destination is empty, absolute or contains `..` | `unsupported carry /a='../b'; expected a path inside the workspace` |
| a non-open `fence` with no `scopes` (drawn path by path) | `a fence drawn path by path cannot be held on another machine; draw it from its levels with Fence.of` |
| a non-open `fence` with a harness on another machine | `a fence is drawn around this machine's paths, and cannot hold a harness on another machine` |
| a `fence` with `online=False` and `net="remote"` | `a fence that cuts the network keeps the agent's own connections here; --net remote would send them past it` |

The command line also refuses no agent and no `--check` with
`` no agent given; try `hmz internal anchor claude` `` (exit 2).

Refused only when a turn is started:

| Condition | Error |
| --- | --- |
| no agent named | `ValueError: no agent given` (native), `ValueError: no agent command given` (supervised) |
| a harness on a `tcp://` or `peer://` machine, or `same` with such a target | `ValueError: nothing is started on the far side of tcp://h:1` |
| `chdir` outside the workspace | `ValueError: <chdir> is not inside <workspace>` |
| the agent not on this machine's `PATH` (supervised) | `FileNotFoundError: <name>: not found on PATH` |

### Exit status of `hmz internal anchor`

| Status | Meaning |
| --- | --- |
| the agent's own | the agent ran; a signal-killed CLI under `--native` is `128 + signal` |
| `0` | `--check` succeeded |
| `1` | `ConnectionError`, `ProtocolError`, `OSError` or `ValueError` while reaching the target or running the turn, printed as `hmz: <message>` |
| `2` | refused settings (usage error) |
| `127` | `--native` and the CLI is not installed on the target: `` hmz: <cli> is not installed on <target>[; install it there with `<installs>`] `` |
| `130` | interrupted |

`--check` prints, without running anything on the target:

```text
target      ssh://build-box
hostname    build-box
python      3.12.3 (pid 41207)
export      /srv/project -> /srv/project
workspace   /srv/project (184 entries)
```

<small>Defined in [`src/hmz/coganchor/anchor.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/anchor.py), [`src/hmz/coganchor/argv.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/argv.py), [`src/hmz/cli/anchor.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/cli/anchor.py).</small>

## Where the harness runs {#where-the-harness-runs}

Placement is decided at two levels: `AnchorConfig.harness` for one anchor, and `-H` for every
agent of a flow run, which the flow runtime turns into anchor settings per session.

### `AnchorConfig.harness`

| Value | Harness machine | Mirror | Notes |
| --- | --- | --- | --- |
| `local` | this machine | `shadow`, else the workspace path | the supervised arrangement |
| `same` | the machine `target` names | kept, on that machine | afar; nothing is introduced, the serving half is started beside the harness with a `local:` target |
| an `ssh://` or `docker://` spelling equal to `target` (scheme, host, port, path and options) | that machine | kept, on that machine | as `same` |
| any other `ssh://` or `docker://` spelling | that machine | kept, on that machine | afar; a [rendezvous](#being-introduced) introduces the harness to the serving half on the target |
| `local:DIR` | this machine | as `local` | not afar |

A turn with the harness elsewhere is spawned as `hmz internal anchor` on the harness machine
(bootstrapped as a [target](#bootstrapping-the-serving-half) is), with `harness` rewritten to
`local` and `target` rewritten to `local:<remote_path>` (same machine) or `peer://<ticket>@<broker>`
(third machine). This machine runs only the process carrying the three streams.

Where `shadow` is unset, the mirror on the harness machine is
`<mirrors>/<name>`, where `<mirrors>` is `$HOME/.cache/humanize-mirrors` over ssh or
`/tmp/humanize-mirrors` in a container, and `<name>` is the first 16 hex digits of
`sha256(workspace \0 remote_path \0 target)`. It is passed as `HUMANIZE_SHADOW` with `force`
set, and kept between turns.

The driver still names the workspace by its own path: a CLI told where to work over its
protocol (Codex's `thread/start` `cwd`, an ACP `session/new` `cwd`, and so on) is told
`workspace`. On a harness reaching its work as a `peer://` target (a third machine), the
supervisor answers `workspace` and everything under it with the mirror, as another
[spelling](#interception) of it, whatever the harness machine holds at that path; it is never
created there. A `--local-path` under `workspace` is kept here by either name. Not for a
mirror nested in the workspace or the other way round.

### `-H`: placement for a flow run

```text
-H adaptive | local | env | standalone:<backend>@<provider>[/<workdir>] | standalone:<name>
```

| Mode | Work in a `local` environment | Work in an `ssh` or `docker` environment |
| --- | --- | --- |
| `adaptive` (default) | spawned here | native on the environment's machine where the [conditions](#adaptive-resolution) hold; otherwise supervised here |
| `local` | spawned here | supervised here, anchored to the environment's machine |
| `env` | spawned here | native on the environment's machine; refused where the CLI is missing or the machine cannot hold the fence |
| `standalone:<env>` | supervised on `<env>`'s machine, reaching this machine's workdir as a `local` target | supervised on `<env>`'s machine, reaching the environment's machine through the anchor |

- `hmz exec` without `-H` runs `adaptive`. The TUI keeps a placement per flow per workspace in
  its settings (`flows.<flow>.harness`, `""` for adaptive) and passes it to each run.
- `standalone:<env>` names the machine as `-e` names one after `ROLE=`:
  `standalone:ssh@gpu-box/~/scratch`, `standalone:docker@gpubox/srv/scratch`. A bare name is a
  saved [environment provider](/reference/machines#environment-providers), looked up as ssh
  first, then docker. A missing workdir becomes the provider's own, else `~` over ssh, else
  `$HUMANIZE_HOME/harness` for `docker@local` (created by the run). The standalone machine is
  opened, probed and closed as an environment of the run. A container for it is started with
  `--cap-add SYS_PTRACE`: without it, docker's default seccomp profile refuses the
  `pidfd_getfd` the supervisor borrows each command's descriptors with, and a command whose
  output goes to a socket (opencode's, Claude Code's stdin) is run with that output lost.
- A standalone machine may not be this machine.

| `-H` value | `HarnessSpecError` (exit 2 from `hmz exec`) |
| --- | --- |
| anything else, `standalone:` with nothing after it, `env:x` | `-H 'bogus': expected adaptive, local, env or standalone:<backend>@<provider>[/<workdir>]` |
| `standalone:local@…` | `-H 'standalone:local@/tmp': a standalone harness runs on another machine; -H local runs it on this one` |
| a bare name nothing is saved under | `-H 'standalone:bogus': no environment provider is saved as 'bogus'; expected standalone:<backend>@<provider>[/<workdir>] or standalone:<saved name>` |
| an unknown backend | `-H 'standalone:bogus@x': 'bogus' is not a backend; one of ssh, docker` |
| a docker provider nobody saved, with no workdir | `-H 'standalone:docker@gpubox': docker@gpubox is not saved with a workdir of its own; expected standalone:docker@gpubox/<workdir>` |
| `ssh@` with no host | `-H 'standalone:ssh@': ssh needs a host, as in ssh@host/workdir` |

### Adaptive resolution {#adaptive-resolution}

The decision is made in `HarnessDriver.open` (`hmz.runtime.flowing.harnesses`) for every session
a role opens, before the session's agent is built. With the session's machine `M` (from its
environment), its fence, and the set `H` of hooks hung on the flow agent among `PreToolUse`
and `PermissionRequest` (an `AskUser` hook is not among them: a question comes back down the
CLI's own stream wherever the CLI runs):

1. `standalone:<env>`: the result is the work's anchor (for work here,
   `AnchorConfig(target="local", workspace=<cwd>)`) with `harness` set to `<env>`'s target and
   `shadow=None`. No probe is made. (If `<env>`'s own placement is not anchored, `M` is used
   unchanged.)
2. `M` is this machine, or the mode is `local`: `M` unchanged.
3. `adaptive` and `H` is non-empty: `M` unchanged. The CLI's own hook table names a program on
   this machine, so a gating hook is kept here.
4. Otherwise the machine is asked, once per role and target, whether the CLI is there; then,
   for a session with a non-open fence, once per role, target and `online` value, whether the
   machine can hold the fence.
5. Both answers yes: `M` with `native=True` and `shadow=None`.
6. Otherwise: `adaptive` returns `M` unchanged; `env` raises the refusal from step 4.

| Probe | How | Result |
| --- | --- | --- |
| CLI present | The native road itself: `AnchorConfig(native=True, shadow=None, fence=None).command(["/bin/sh", "-c", 'command -v -- "$1" >/dev/null 2>&1 \|\| command -v -- "$2" >/dev/null 2>&1 \|\| exit 69', "humanize", PROGRAM, basename(PROGRAM)])`, in a new process session, stdin `/dev/null`, 300 s limit. `PROGRAM` is the CLI's name, or an added CLI's configured command. | exit 0: present; exit 69: absent; other exit, spawn failure or timeout: cannot be asked |
| Fence holdable | `hmz.coganchor.check(anchor)`; the handshake's `fence.fs` (and `fence.net` where the fence cuts the network) | both true: holdable |

Answers are cached on the role's driver for the rest of the run; concurrent sessions wait for
one answer. The probes are asked one at a time.

Under `env` and `standalone`, `Runner.arun` asks the same of every agent (`HarnessDriver.placeable`)
against every environment, the workspace included, with the role's declared permission, once
the environments are probed and before the flow is called; a refusal there is `Refused`, which
`hmz exec` prints as `hmz exec: error: <message>` with exit 2, and the answers are kept for
the sessions. A session opened later is still refused as it opens, raised from its `spawn`.
Refusals (`<where>` is `<backend>@<provider>` of the environment, e.g. `ssh@gpu-box`):

| Error | Message | When |
| --- | --- | --- |
| `HarnessNotInstalled` | `<cli> is not installed on <where>: <install line> there, or run its harness here with -H local` | `env`, probe exit 69 |
| `HarnessUnrecoverable` | `<where> could not be asked whether <cli> is there: <last stderr line \| exit status N>` | `env`, probe failed |
| `HarnessUnrecoverable` | `<where> did not say within 300s whether <cli> is there` | `env`, probe timed out |
| `HarnessUnrecoverable` | `<where> could not be asked whether it can fence: <error>` | `env`, handshake failed |
| `HarnessSandboxed` | `<where> cannot fence the agent to its permission: it needs Landlock; grant the agent everything, or run its harness here with -H local` | `env`, the machine cannot hold the fence |
| `HarnessNotInstalled` | `<cli> is not installed here: <install line>` | the harness is here and the CLI is not on this machine |
| `HarnessSandboxed` | `<role>=<cli>[@<account>]/<model>:<effort>: <AgentClass>: a fence cannot hold a harness that runs on another machine` | `standalone`, and the role's `Permission` is anything but every scope `ALL` |

### Recording

The placement each session got is written with it: the epic's session record carries
`harness` (`local`, `env`, or `standalone:<target>`; `""` for work on this machine), and so does
the daemon's `opened` record. See [Tracing](/reference/tracing).

### Limitations

- **A fence cannot follow a harness elsewhere.** A fence names this machine's paths. Under
  `standalone`, and under an `AnchorConfig.harness` elsewhere, any non-open fence is refused;
  a flow role must grant `local`, `user`, `system` and `online` all `ALL`. The default
  `Permission` (`local=ALL, user=READ, system=READ, online=ALL`) is refused.
- **Accounts do not follow a harness elsewhere.** See [Where the account lives](#where-the-account-lives).
- **Gating hooks keep `adaptive` here.** A role with a `PreToolUse` or `PermissionRequest`
  hook hung is never placed natively by `adaptive`; `env` places it natively anyway. An
  `AskUser` hook does not keep it here.
  An anchored turn gets no hook table, so there `PreToolUse` is read off the CLI's stream and
  cannot stop a tool ([Agents › Refusing a tool](/reference/agents#refusing-a-tool)).
- **Callbacks do not cross.** A native turn on a non-`local` target offered the flow's tool
  callbacks is refused: `<cli>: a turn driven on <target> cannot be offered the flow's own
  callbacks -- the bridge that carries them is a program on this machine, and the CLI that
  would start it is on that one`.
- **Sessions of a native or afar turn stay where that CLI keeps them**, on the other machine; a
  run cannot keep them in its epic ([Providers › Where sessions are kept](/reference/providers#where-sessions-are-kept)).
- **Forks stay on one machine.** A fork into a session on another machine is refused with
  `UnsupportedOperation: <cli> cannot fork a session onto another machine`.

<small>Defined in [`src/hmz/runtime/flowing/harnesses.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/harnesses.py) (`HarnessDriver._harnessed`, `_native_on`, `_has_cli`, `_fenceable`), [`src/hmz/runtime/flowing/specs.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/specs.py) (`parse_harness`), [`src/hmz/runtime/runner.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/runner.py), [`src/hmz/runtime/epic.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/epic.py) (`harnessed`), [`specs/runtime/flowing.md`](https://github.com/humanfia/humanize/blob/main/specs/runtime/flowing.md) (Where the harness runs).</small>

## Supervised arrangement {#supervised-the-default}

`connect(command, config)` with `harness` here and `native=False`. The agent process runs on
this machine, unchanged, under a supervisor. Everything it does to files, programs and the
network is answered from the target.

### Interception

- A seccomp filter traps exactly the syscalls that name a path, start a program or open a
  connection; every other syscall (`read`, `write`, `mmap`, `futex`, `getdents64`, …) runs
  natively.
- Trapped on x86-64 (34): `access`, `chdir`, `chmod`, `connect`, `creat`, `execve`,
  `execveat`, `faccessat`, `faccessat2`, `fchmodat`, `link`, `linkat`, `lstat`, `mkdir`,
  `mkdirat`, `newfstatat`, `open`, `openat`, `openat2`, `readlink`, `readlinkat`, `rename`,
  `renameat`, `renameat2`, `rmdir`, `stat`, `statx`, `symlink`, `symlinkat`, `truncate`,
  `unlink`, `unlinkat`, `utimensat`, `utimes`. On aarch64 the 14 legacy forms do not exist and
  20 are trapped.
- A path is resolved as text: `.` and `..` are collapsed, doubled `/` removed, and
  `/proc/self/fd/<n>`, `/proc/<pid>/fd/<n>`, `/proc/self/cwd`, `/proc/self/root` and
  `/proc/self/exe` are followed to what they name. An ordinary symlink in the middle of a path
  is not walked. A link that cannot be read back fails the call.
- A path the mirror is also reached by is rewritten onto the mirror's own path before the call
  runs: `/private/tmp/…` for a mirror under `/tmp` on a Mac target, any case on a target that
  ignores case, and `workspace/…` for a `peer://` target
  ([a harness elsewhere](#where-the-harness-runs)).
- Only x86-64 and aarch64 Linux are supported. Any other platform fails at start-up with
  `RuntimeError`, naming where the supervisor can run instead.

### The mirror

- The mirror is prepared before the target is reached. Its guard, recorded outside the
  directory in `~/.cache/humanize/shadows/<sha256(path)[:16]>.json` (or under
  `$HUMANIZE_SHADOWS`):

  | Condition | Without `force` |
  | --- | --- |
  | the directory was last used for another target | `FileExistsError: <path> mirrors <old>, not <new>. humanize replaces this directory with the new target's contents and would delete everything only the old one has. Use a different directory, or pass --force.` |
  | the directory holds files and was never a mirror | `FileExistsError: <path> already contains files and is not an humanize mirror. humanize replaces this directory with the target's contents and would delete them. Use an empty directory, or pass --force.` |
  | the path exists and is not a directory | `Unmirrored: … shadow root is not a directory` (always) |
  | the path cannot be created here | `Unmirrored: … <reason>`, e.g. `Permission denied: /home/me` (always) |

  `Unmirrored` (an `OSError`) is printed by `hmz internal anchor` as
  `hmz: cannot keep the local copy of the work at <path>: <reason>`, with exit 1. A turn that
  fails with it is classified `unmirrored`
  ([Agents › Failures](/reference/agents#failures)), not as a refused credential.
  The target's identity for this check is its spelling without ssh options.
- Structure is materialised on first access: real directories and symlinks, and sparse
  placeholder files carrying the target's size, mode and mtime. `stat`, `getdents64`, `read`,
  `write`, `mmap` and `lseek` then run locally.
- Content is pulled the first time a file is opened for reading.
- A file the agent modifies is pushed in full before any command runs on the target, and again
  when the session ends.
- Creating, removing, renaming, linking and mode changes are replayed on the target first; the
  target's error is the agent's error.
- Completing a remote command invalidates every cached directory listing.
- The mirror is authoritative: what the target does not have is deleted from it.

### What stays on this machine

A path is answered from the target unless it is one of these:

| Kept here | Source |
| --- | --- |
| The agent program as resolved on `PATH`, and its real path | `statepaths.resolve` |
| For a script, its `#!` interpreter, and for `#!/usr/bin/env NAME` every `PATH` candidate for `NAME` | `statepaths._interpreter` |
| Codex's native binary and `codex-code-mode-host` | `statepaths._codex_runtime_programs` |
| Every executable beside the program inside its own `node_modules` package (e.g. mimo's `bin/.mimocode`) | `statepaths._beside` |
| The CLI's state paths (table below), as files and as programs | `statepaths.PROFILES` |
| `~/.humanize`, `~/.cache/humanize`, `~/.config/humanize` | `statepaths.COMMON_STATE_PATHS` |
| `local_paths`, `local_execs`, and what every `redirects` entry is answered with | `AnchorConfig` |
| The program that bridges the flow's tool callbacks, when offered | added to `local_execs` |

| CLI | State paths kept here |
| --- | --- |
| `agy` | `~/.gemini` |
| `claude` | `~/.claude`, `~/.claude.json`, `~/.local/share/claude`, `~/.cache/claude-cli-nodejs` |
| `codex` | `~/.codex` |
| `cursor-agent` | `~/.cursor`, `~/.local/share/cursor-agent` |
| `dsh` | `~/.dsh` (also for `dsh-jsonrpc-agent-*`) |
| `grok` | `~/.grok` |
| `kimi` | `~/.kimi-code`, `~/.kimi` |
| `mcode` | `~/.minimax`, `~/.mavis` |
| `mimo` | `~/.mimocode`, `~/.config/mimocode`, `~/.local/share/mimocode`, `~/.cache/mimocode`, `~/.local/state/mimocode` |
| `opencode` | `~/.opencode`, `~/.config/opencode`, `~/.local/share/opencode`, `~/.cache/opencode`, `~/.local/state/opencode` |
| `pi` | `~/.pi` |
| `qwen` | `~/.qwen` |
| any other program | none beyond the common paths; state inside the workspace must be named with `--local-path` |

### Commands, network and signals

- Every program the agent starts that is not kept here runs on the target, in the target's
  copy of the working directory, work helpers such as a bundled `ripgrep` included. It gets
  the agent's descriptors, output and exit status; its parent is released as soon as it
  starts, so commands run concurrently.
- A command that inherited the pipe the agent's driver speaks on gets an empty stdin on the
  target. An agent that is a shell hands its stdin on as a shell does.
- Variables in `private` are removed from the environment commands run with on the target.
- `net="local"`: the agent's own TCP connections leave from this machine. `net="remote"`: they
  are tunnelled and opened from the target, except destinations in `net_allow`.
- `SIGINT`, `SIGTERM` and the other common signals are forwarded both ways. A repeated signal
  and the rarer signals are not reproduced.
- A command that cannot be started, or that the supervisor loses track of, fails. Nothing it
  started is left running when the session ends.

<small>Defined in [`src/hmz/coganchor/supervisor.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/supervisor.py), [`src/hmz/coganchor/linux/syscalls.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/linux/syscalls.py), [`src/hmz/coganchor/shadow.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/shadow.py), [`src/hmz/coganchor/statepaths.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/statepaths.py), [`src/hmz/coganchor/policy.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/policy.py).</small>

## Native arrangement {#native-the-target-s-own-cli}

`drive(command, config)`, reached through `connect` when `native=True`. Nothing is mirrored,
traced or supervised. The sequence per turn:

1. Handshake with the serving half.
2. Find the CLI on the target: `command -v -- NAME` from the workspace, then by the last
   component of `NAME`. Not found: `NotInstalled` (exit 127 on the command line).
3. If a fence is set and not open, require the handshake's `fence` capability; otherwise
   `PermissionError: the target cannot fence the CLI: it needs Landlock[ ABI 4 and seccomp]`.
4. If `projects` is non-empty, make a private directory on the target (`umask 077`,
   `mktemp -d`, `chmod 700`) and write each credential file into
   `<dir>/<variable lowercased>/...` through a command's stdin, mode `0600`. The variable is
   set to that directory. A failure raises `OSError: could not put <VAR> on the target: …` and
   the turn does not run.
5. Put each `carries` directory into the target's workspace (below).
6. Start the CLI as `env [-u HUSHED]... NAME=VALUE... PROGRAM ARGS...` in `chdir` (default the
   workspace), with this process's environment layered on the target's.
7. Relay stdin, stdout and stderr byte for byte; forward the first `SIGINT`/`SIGTERM` to the
   CLI and restore the previous handler, so a second one reaches this process.
8. Remove the credential directory and release carried directories, whatever happened.

| What does not follow the CLI | How it crosses |
| --- | --- |
| The account's variables | Sent as the turn's environment. Every variable the provider [hushes](/reference/providers#variables-taken-away) is removed on the target with `env -u`, since the target's own shell profile would otherwise supply it. |
| The account's credential files | `--project NAME=DIR`, written through stdin, never argv. |
| The flow's skills | `--carry DIR=PATH`. An existing path not planted by humanize is left alone. A planted one holds a claim file per turn under `PATH/.humanize-carried/`; it is removed when the last claim is released. Directories created above it are removed if empty. |

Credential files cross only where a variable of the backend's own moves the directory they are
in:

| Credential root | Crosses as | Backends |
| --- | --- | --- |
| the backend's home | its home variable | `claude` (`CLAUDE_CONFIG_DIR`), `codex` (`CODEX_HOME`), `cursor-agent` (`CURSOR_CONFIG_DIR`), `grok` (`GROK_HOME`), `kimi` (`KIMI_CODE_HOME`), `mcode` (`MINIMAX_DATA_DIR`), `pi` (`PI_CODING_AGENT_DIR`), `qwen` (`QWEN_HOME`) |
| `$XDG_CONFIG_HOME` | `XDG_CONFIG_HOME` | files written `config/…`, e.g. Claude's `anthropic/` |
| the backend's home, no own variable | does not cross | `agy`, `opencode`, `mimo` |
| the user's home (`~/…`) | does not cross | e.g. Claude's `~/.claude.json`, Cursor's `~/.cursor/auth.json` |

An account some of whose credential files cannot cross, with nothing else to carry it, is
refused rather than run as whatever account the target is signed into.

- There is no `net`: the CLI's connections are the target's. A gateway at `127.0.0.1` is the
  target's loopback.
- The CLI keeps its sessions on the target.

<small>Defined in [`src/hmz/coganchor/anchor.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/anchor.py) (`drive`, `_installed`, `_projected`, `_carried`, `_swept`), [`src/hmz/coganchor/agents/base.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/base.py) (`_reaching`, `_projecting`).</small>

## Afar arrangement and the rendezvous {#being-introduced}

With the harness on the target (`same`), nothing is introduced: the harness machine runs
`hmz internal anchor --target local:<remote_path>` against itself. With the harness on a third
machine, humanize books a meeting:

1. This process starts (once, for its lifetime) a broker listening on `0.0.0.0`, port
   `$HUMANIZE_RENDEZVOUS_PORT` (default `0`, any free port).
2. It mints a ticket (`secrets.token_hex(16)`, 128 bits) and starts, on the target,
   `hmz internal anchor serve --peer TICKET@HOST:PORT --export …`, where `HOST` is `broker`,
   else `$HUMANIZE_RENDEZVOUS`, else this machine's outward-facing IPv4 address (the source
   address of a route to `192.0.2.1`; `127.0.0.1` if there is none).
3. It spawns `hmz internal anchor --target peer://TICKET@HOST:PORT` on the harness machine.
4. Both halves dial the broker with the ticket and their role (`anchor` or `serve`).

| Phase | Behaviour | Time limit |
| --- | --- | --- |
| Pairing | a half waits at the broker for the other | 120 s |
| Discovery | each half is told the address its connection arrived from, and the other half's addresses | 30 s per broker answer |
| Punching | both halves connect to each other's candidates from the port they dialled the broker from, and listen on it; each punched socket must present `HMZ1` and a digest of the ticket; the anchor half says `GO` on the socket it keeps and the serving half answers `OK` | 4 s (`--punching` on a standalone broker) |
| Greeting | a punched socket that does not prove itself is dropped | 3 s |
| Relay | if punching fails, the two connections already held to the broker are spliced, 64 KiB at a time | none |

- The broker remembers pairs of external addresses it failed to introduce (up to 1024 pairs).
  After 3 failures a pair is relayed without punching, except when its failure count is a
  multiple of 16.
- A broker holds at most 65,536 meetings at once; beyond that a half is refused with
  `this rendezvous is already holding 65536 meetings`.
- Addresses are IPv4 only; a machine reachable only over IPv6 is relayed.
- Neither half is told whether it was relayed.
- `hmz internal anchor rendezvous [--listen [HOST:]PORT] [--punching SECONDS]` runs a broker on
  its own (default `0.0.0.0:0`) and prints `hmz internal anchor rendezvous listening HOST PORT`
  on stderr.

<small>Defined in [`src/hmz/coganchor/elsewhere.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/elsewhere.py), [`src/hmz/coganchor/rendezvous.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/rendezvous.py).</small>

## A fence on both machines {#a-fence-on-both-machines}

`AnchorConfig.fence` is held by the anchor on each machine around that machine's own paths,
never by a wrapper around the anchor. The fence must have `scopes` (built with `Fence.of`);
what crosses is its levels, not its paths.

| Arrangement | This machine | Target |
| --- | --- | --- |
| Supervised | The agent process is walled in by Landlock before it runs, with the mirror granted at the workdir's level. Where `online=False`, a proxy served by the anchor process is its only way out, passing the fence's hosts; binds are limited to a kernel-chosen port and the fence's `listen` ports, on loopback. The supervisor, its link and the mirror are outside the wall. | Every command the agent runs is sent with `{local, user, system, online, tmp}`, `tmp` being the agent's scratch directory here. The serving half draws the fence again (`abroad.drawn`) around its exported directories, its own `$HOME` and its own minimum, and runs the command under its own `hmz internal fence` with its scratch at that same path: made `0700` there if missing and left afterwards, used where it is a directory of the serving user's own (not a link), and otherwise replaced by one made for the one command. A command that names the path, as Claude Code's shell commands name the file they write their working directory to, finds it. Where `online=False`, the command reaches no host. |
| Native | nothing | The CLI is run under `hmz internal fence` on the target with the levels, the hosts its model is at, the state it writes under its home (sent as `~/…`), the turn's credential directory, read access to its own install tree, and its `listen` ports. |
| Afar | refused | refused |

- A CLI's own sandbox is not used under an anchor: it would wrap a command here that runs on
  the target. Codex is sent `sandboxPolicy: {"type": "externalSandbox", "networkAccess":
  "enabled" | "restricted"}` (by the fence's `online`) where the fence writes nothing the rung
  forbids: nothing at all for `read-only`, nothing of the home or system for
  `workspace-write`; Cursor's `workspace-write` runs without `cursorsandbox` where
  the fence writes nothing of the home or the system.
- Whatever a driver grants its CLI past the wall (a port it serves on, a sign-in outside its
  home, generated settings) is granted on both machines.
- The target reports what it can hold at the handshake: `fence.fs` is Landlock ABI >= 1;
  `fence.net` is Landlock ABI >= 4 (Linux 6.7), a loadable seccomp user-notification filter,
  and `pidfd_getfd` permitted with Yama `ptrace_scope` < 2. A target of a build before fences
  reports nothing and is treated as unable.

| Where | Error | Message |
| --- | --- | --- |
| agent construction | `Unfenced` | `<Agent>: a fence drawn path by path cannot be held on another machine` |
| agent construction | `Unfenced` | `<Agent>: a fence cannot hold a harness that runs on another machine` |
| agent construction | `Unfenced` | `<Agent>: an agent whose own connections are sent to the target cannot have its network cut here` |
| agent construction, supervised | `Unfenced` | `<Agent> cannot be held to its permission: it is supervised on this machine, which has no Landlock[ ABI 4 and seccomp to cut the network]` |
| first turn, supervised | `Unfenced` | `<id>: <target> cannot fence the commands the agent runs there: it needs Landlock (Linux 5.13 or later, not refused by a container's seccomp profile)[, at ABI 4 (Linux 6.7) with seccomp, to cut the network]; grant the agent everything, or run it where it can be fenced` |
| anchor start, supervised | `PermissionError` | `this machine cannot fence the agent: it needs Landlock[ ABI 4 and seccomp]` |
| native turn | `PermissionError` | `the target cannot fence the CLI: it needs Landlock[ ABI 4 and seccomp]` |
| a fenced command on the target | `PermissionError` | `this machine cannot fence a command: it needs Landlock[ ABI 4 and seccomp]` |

Under a flow, `Unfenced` becomes `HarnessSandboxed`. Docker's default seccomp profile permits
Landlock but not the seccomp listener or `pidfd_getfd`, so a container under it holds a fence
with `online=True` and refuses one with `online=False`; run such a container with a profile
that allows them, or `--security-opt seccomp=unconfined`.

<small>Defined in [`src/hmz/coganchor/anchor.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/anchor.py) (`_Walls`, `_fenced`), [`src/hmz/coganchor/fence/abroad.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/fence/abroad.py), [`src/hmz/coganchor/serve/fencing.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/serve/fencing.py), [`src/hmz/coganchor/agents/base.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/base.py) (`_abroad`, `_reached`, `_walled`).</small>

## Serving a target {#serving-a-target}

```text
hmz internal anchor serve --export VIRTUAL[:REAL] [--export ...]
                          (--stdio | --listen [HOST:]PORT | --peer TICKET@HOST:PORT)
                          [--token TOKEN] [--log-level LEVEL]
```

| Mode | Serves | Started by |
| --- | --- | --- |
| `--stdio` | one session on stdin/stdout; fds 0 and 1 are pointed at `/dev/null` for the rest of the process | humanize, for `local`, `ssh://` and `docker://` targets |
| `--listen [HOST:]PORT` | every TCP connection, one thread each, until interrupted; prints `hmz internal anchor serve listening HOST PORT` on stderr | a person, for `tcp://` targets |
| `--peer TICKET@HOST:PORT` | one session met at a broker | humanize, for a harness on a third machine |

- `--export VIRTUAL[:REAL]` is required and repeatable. `VIRTUAL` must be absolute; `REAL`
  defaults to `VIRTUAL`, with `~` expanded. A path outside every export is refused with
  `EACCES`, `path is outside every export`. Virtual prefixes inside command arguments are
  rewritten to real paths. Malformed: `hmz: malformed export '<spec>'; expected
  VIRTUAL[:REAL]`, exit 2.
- A bare `--listen PORT` listens on `127.0.0.1`. Any host other than `127.0.0.1`, `::1` or
  `localhost` without `--token` is refused: `hmz: cannot listen on a non-loopback address
  without --token`, exit 2. A malformed address: `hmz: malformed listen address '<spec>';
  expected [HOST:]PORT`, exit 2. A bind failure exits 1.
- `--token` defaults to `$HUMANIZE_TOKEN`. With a token, a session whose handshake does not
  present it is refused with `invalid token`.
- For `ssh://` and `docker://` targets the token is unused; ssh and the docker socket
  authenticate the session.

::: danger A listening serving half is a shell on its machine
An export bounds which paths a request may name; it does not confine what the commands it
runs can do. Listen on a non-loopback address only with a secret `--token`.
:::

<small>Defined in [`src/hmz/cli/anchor.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/cli/anchor.py), [`src/hmz/coganchor/serve/`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/serve), [`specs/coganchor/serve.md`](https://github.com/humanfia/humanize/blob/main/specs/coganchor/serve.md).</small>

## Where the account lives {#where-the-account-lives}

| Arrangement | Credentials, CLI state, model-provider connection | Provider variables | Provider credential files |
| --- | --- | --- | --- |
| Supervised | this machine | set on the agent here; listed in `private`, so commands on the target do not get them | answered here as `redirects`; never cross |
| Afar | the harness machine | not sent: the harness process's environment is the harness machine's | redirected to this machine's paths, which the harness machine does not have |
| Native | the target, for each turn | sent as the turn's environment; hushed variables removed with `env -u` | written to a private directory on the target and removed after the turn, where they can [cross](#native-the-target-s-own-cli) |

## Python API {#from-python}

```python
from hmz.coganchor import AnchorConfig, check, connect, drive
from hmz.coganchor.anchor import NotInstalled
```

| Call | Returns | Raises |
| --- | --- | --- |
| `check(config=None) -> dict` | the handshake reply (`version`, `hostname`, `platform`, `python`, `pid`, `exports`, `fence`) plus `target`, `workspace` and `entries` (entries in the workspace). Runs nothing on the target. | `ValueError` (target), `OSError` (unreachable, no workspace) |
| `connect(command, config=None) -> int` | the agent's exit status, after everything it wrote has been pushed. Calls `drive` when `native`; spawns the afar line when the harness is elsewhere. | `ValueError`, `FileNotFoundError`, `OSError` |
| `drive(command, config=None) -> int` | the CLI's exit status, or `128 + signal` | `ValueError` (`no agent given`, target), `NotInstalled` (a `FileNotFoundError`), `OSError`, `PermissionError` (fence) |
| `AnchorConfig.command(argv, *, swaps=(), private=(), chdir="") -> list[str]` | the argv that runs `argv` under this anchor in its own process | `ValueError`, `ConnectionError` |
| `AnchorConfig.capabilities -> frozenset[str]` | `{"anchor:native-cli"}`, `{"anchor:supervised"}` or `{"anchor:supervised", "anchor:afar"}` | |
| `AnchorConfig.mount() -> (Target, str, str)` | the parsed target, the workspace's absolute path here, and the export spelling | `ValueError` |

`config=None` is `AnchorConfig()`: this directory on a `local` target.

## Requirements {#requirements}

| Machine | Requirement |
| --- | --- |
| The harness machine, supervised or afar | Linux on x86-64 or aarch64, Python >= 3.12, ptrace and seccomp permitted. |
| This machine, when the harness is elsewhere or the arrangement is native | none of the above; only what runs the three streams |
| A target | a POSIX `/bin/sh` and Python >= 3.12; no root, compiler, kernel module or installed package |
| A target of a fenced session | Linux with Landlock (ABI >= 1); ABI >= 4 (Linux 6.7), seccomp user notification and `pidfd_getfd` where the network is cut |
| A native target | the CLI installed and on the login's `PATH` |
| A harness machine elsewhere | an `ssh://` or `docker://` machine meeting the first row, with the CLI installed |
| A third-machine harness | both machines able to reach this machine's broker port over IPv4 |

## Failure behaviour {#what-is-not-guaranteed}

- **Serving is not a sandbox.** Exports bound the paths a request may name, not what commands
  do; a symlink out of an export is followed. Only a [fence](#a-fence-on-both-machines)
  confines commands.
- **Mirrored directories carry this machine's permissions** and the time the mirror made them.
- **Only file contents are pushed.** A mode change through an open descriptor is not replayed;
  ownership, device nodes and extended attributes never leave the mirror.
- **An unanswered request is abandoned here, not there.** It may still take effect on the
  target after the agent was told it failed.
- **Losing the connection does not stop the agent.** Work that needs the target fails,
  mirrored files still read, and the agent exits with its own status.
- **The mirror is authoritative.** What the target lacks is deleted from the mirror, including
  a file written here and never pushed; the deletion is logged.
- **A command's output may not reach the agent in a container.** The supervisor borrows each
  command's descriptors with `pidfd_getfd`, which docker's default seccomp profile refuses
  without `CAP_SYS_PTRACE`. A pipe or tty is opened again through `/proc` instead; a socket
  cannot be, and is logged as `could not borrow fd <n> from pid <pid>`. humanize starts a
  standalone harness's container with `--cap-add SYS_PTRACE`; one started otherwise needs it.
- **A path is read when its syscall stops.** A descriptor replaced by another thread in between
  resolves as it was.
- **Native setup commands are bounded.** Each short command a native turn runs to set itself
  up has 120 s; past that it is killed and the turn fails with `TimeoutError: the target did
  not answer '<cmd>' in 120s`.

## Limits

- Files cross whole, in both directions.
- One writer: nothing else may edit the target's workspace during a session.
- `sudo` below a supervised agent does not work here; commands run on the target, where it is
  unaffected.
- Renaming or linking between the workspace and a path kept here fails.
- A 32-bit process below the agent is not intercepted, and runs against the mirror with nothing
  replayed.
- Host names are resolved here and dialled from the target; split-horizon DNS can disagree.
- A relayed session pays this machine's bandwidth and latency for every byte.

## Security properties

| Property | Holds |
| --- | --- |
| A provider's credential files leave this machine | only under `native`, into a `0700` directory on the target, removed after each turn |
| A provider's variables reach commands on the target | never under supervised (`private`); under `native`, the CLI's environment is the turn's |
| A credential appears in an argv | never; projected files cross on stdin |
| A listening serving half without a token | loopback only |
| A broker port | open on every interface for the life of the process that booked a third-machine harness; pairing requires a 128-bit ticket known to exactly two machines |
| A mirror overwrites a directory it did not create | never without `force` |

## Environment variables

Every variable humanize reads is listed in [Environment variables](/reference/environment).

| Variable | Read by | Effect |
| --- | --- | --- |
| `HUMANIZE_TARGET` | `hmz internal anchor` | default `--target` |
| `HUMANIZE_HARNESS` | `hmz internal anchor` | default `--harness` |
| `HUMANIZE_SHADOW` | `hmz internal anchor` | default `--shadow`; set by humanize for a harness elsewhere |
| `HUMANIZE_TOKEN` | `hmz internal anchor`, `… serve` | default `--token`; passed to a spawned serving half |
| `HUMANIZE_LOG` | `hmz internal anchor`, `… serve`, `… rendezvous` | default `--log-level` (`warning`; `info` for `rendezvous`); a value that is not a level is ignored with a warning |
| `HUMANIZE_RENDEZVOUS` | `hmz internal anchor`, the in-process broker | default `--broker`; the address advertised to both halves |
| `HUMANIZE_RENDEZVOUS_PORT` | the in-process broker | the port it listens on; `0` or unset for any |
| `HUMANIZE_SSH_REUSE` | every `ssh` humanize runs | `off`, `0`, `no`, `false` (any case, trimmed) or empty disables connection sharing |
| `HUMANIZE_SHADOWS` | the mirror guard | where mirror records are kept, instead of `~/.cache/humanize/shadows` |
| `XDG_RUNTIME_DIR` | every `ssh` humanize runs | where `humanize-ssh-<uid>/` control sockets are made |
| `HUMANIZE`, `HUMANIZE_TARGET`, `HUMANIZE_WORKSPACE` | set for the agent | see [Variables the agent is given](#variables-the-agent-is-given) |
