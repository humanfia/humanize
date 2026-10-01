---
pageClass: hmz-feature
---

# Machines

Reference for where an agent's turns and a flow's environments land: the machine settings of
`hmz.coganchor.machines`, the environments a flow run is given with `-e`, the environment
providers saved under humanize's home, docker endpoints, resources, capabilities and mirrors.
How a turn reaches a machine once it is chosen (the anchor, the harness, the fence across
machines) is [Remote execution](/reference/remote-execution).

## Terms

| Term | Definition |
| --- | --- |
| **Machine setting** | A frozen `MachineConfig`: `AgentConfig.machine`. Describes a machine without starting one. |
| **Machine** | A `MachineBase` made by `MachineConfig.create()`: brought up by `start()`, taken down by `stop()`. |
| **Anchor** | The [`AnchorConfig`](/reference/remote-execution#anchorconfig) `start()` returns; every turn of the agent runs under it. |
| **Environment** | A working directory on a machine that a flow role is given: a `LocalEnv`, or a role filled with `-e`. |
| **Environment provider** | An ssh host or a docker daemon saved under a name in `$HUMANIZE_HOME/env-providers/`, so that `-e` can name it. |
| **Endpoint** | The docker daemon a container is run on, spelled as `docker --host`/`--context` spell one. |
| **Mirror** | The directory on the harness machine a supervised agent works in, reproducing the target's workspace. |
| **Capability** | A word a machine setting, a machine or an anchor answers to (`remote`, `isolated`, …), or an environment mixin a driver serves. |

## Agent machine settings

`AgentConfig.machine` is one of:

| Value | Turns land | Brought up | Taken down | `agent.anchor` |
| --- | --- | --- | --- | --- |
| `None` (default) | on this machine, as ordinary processes | — | — | `None` |
| `AnchoredConfig(anchor=…)` | at the anchor's target | never; the machine is already running | never | the anchor as written |
| `DockerConfig(…)` | in a new container of the image | on the agent's first turn | when the agent is garbage-collected, or at interpreter exit | a `docker://` anchor, supervised, with a private mirror |

Lifecycle rules, common to every setting:

- `agent.anchor` calls `create()` and `start()` the first time it is read, which is the first
  turn. Constructing an agent starts nothing.
- One machine per agent; every session of that agent shares it. Two agents built from one
  config get one machine each.
- `stop()` is registered with `weakref.finalize` on the agent: it runs when the agent is
  collected, or at exit.
- The workspace is never removed.

<small>Defined in [`src/hmz/coganchor/machines/base.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/machines/base.py), [`src/hmz/coganchor/agents/base.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/agents/base.py) (`AgentBase.anchor`), [`specs/coganchor/machines.md`](https://github.com/humanfia/humanize/blob/main/specs/coganchor/machines.md).</small>

### `AnchoredConfig`

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `anchor` | `AnchorConfig` | required | The target, the workspace as the target names it, and every other anchor setting. |

- `create()` returns an `Anchored`, whose `start()` returns `anchor` unchanged and whose
  `stop()` does nothing.
- `capabilities` is `{"remote"}` plus `anchor.capabilities`.
- `hmz.coganchor.agents.anchored(target)` returns `AnchoredConfig(anchor=AnchorConfig(target=target))`,
  or `None` for `""`.

### `DockerConfig`

A container of `image`, holding the workspace bind-mounted at its own path, running as the
workspace's owner.

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `image` | `str` | `"python:3.12"` | The image. Needs `/bin/sh` and Python >= 3.12; no sshd. |
| `workspace` | `str \| None` | `None` (the current directory) | The project directory as the daemon's host names it. Mounted, not copied. |
| `endpoint` | `str` | `"local"` | The daemon. See [Endpoints](#endpoints). |
| `name` | `str \| None` | `None` (`humanize-<random>`) | The container's name, matching `[a-zA-Z0-9][a-zA-Z0-9_.-]+`. |
| `cpus` | `float \| None` | `None` (no limit) | `--cpus`. |
| `memory` | `int \| None` | `None` (no limit) | `--memory`, in bytes. |
| `shm_size` | `int \| None` | `None` (docker's) | `--shm-size`, in bytes. |
| `gpus` | `tuple[str, ...] \| "all"` | `()` (none) | GPU ids as `nvidia-smi` lists them, or `"all"`. |
| `runtime` | `str \| None` | `None` (daemon default) | `--runtime`. |
| `network` | `str \| None` | `None` (daemon default) | `--network`. |
| `run_args` | `tuple[str, ...]` | `()` | Extra `docker run` arguments, placed before humanize's resource and GPU flags. |
| `env` | `Mapping[str, str]` | `{}` | Variables set in the container. Copied at construction. |
| `labels` | `Mapping[str, str]` | `{}` | Extra labels. `humanize`, `humanize.cpus`, `humanize.memory`, `humanize.gpus` are dropped from it. |

Validation, in `__post_init__` (`ValueError`):

| Input | Message |
| --- | --- |
| an endpoint that does not parse | `unsupported docker endpoint 'weird'; expected local, unix:///PATH, tcp://HOST:PORT[?tls=DIR], ssh://[USER@]HOST[:PORT][?KEYWORD=VALUE&...] or context:NAME` |
| a name docker does not take | `unsupported container name '-bad'` |
| `cpus`, `memory` or `shm_size` not above 0 | `cpus must be more than nothing, not 0` |
| `gpus` a string other than `"all"` | `gpus must be ids or 'all', not 'some'` |
| an empty GPU id, or one containing `,` | `unsupported gpus ('0,1',); expected their ids` |
| a variable or label name empty or containing `=` | `unsupported name 'A=B'; expected one without '='` |

`start()`:

1. Requires `docker` on `PATH`: `FileNotFoundError: no docker command here`.
2. Resolves the workspace. On a daemon that is [here](#endpoints), `os.path.abspath` of it,
   which must be a directory (`FileNotFoundError: no directory to give the container`). On any
   other daemon, it must be absolute (`ValueError: a workspace on <endpoint> is a path on that
   machine, so it has to be an absolute one, not '<path>'`).
3. Makes a private temporary directory `humanize-<random>` here: the container's default name,
   the home of its mirror (`<dir>/shadow`) and of its cidfile (`<dir>/container`).
4. Runs, against the endpoint:

   ```text
   docker run --detach
     --cidfile <dir>/container
     --name <name>
     --label <key>=<value> ...              caller's labels, then humanize=<uid>,
                                            humanize.cpus, humanize.memory, humanize.gpus
     --user <uid>:<gid>
     --workdir <workspace>
     --env HOME=/tmp --env <env>...  [--env NVIDIA_VISIBLE_DEVICES=void]
     --mount type=bind,source=<workspace>,target=<workspace>
     <run_args>...
     [--cpus N] [--memory BYTES] [--shm-size BYTES] [--runtime R] [--network N]
     [--device nvidia.com/gpu=<id>]... | [--gpus all | --gpus "device=<ids>"]
     <image>
     /bin/sh -c '<first Python >= 3.12>' humanize -c 'import time; time.sleep(2**31)'
   ```

5. Reaches the container as `docker://<name>[@<endpoint>]` with the mirror at `<dir>/shadow`,
   and [observes](#capabilities) it. Any failure removes what was started and re-raises.

| Flag | Rule |
| --- | --- |
| `--user` | This user's `uid:gid` on a daemon here; `0:0` when that daemon reports `name=rootless` in its security options. On any other daemon, the owner of the workspace there, read by `docker run --rm --label humanize=<uid> --network none --mount <workspace> <image> python -c <stat>`; a missing directory raises `FileNotFoundError: no directory to give the container on <endpoint>`. |
| `HOME=/tmp` | Always, before the caller's `env`. |
| `NVIDIA_VISIBLE_DEVICES=void` | Set unless GPUs are handed out with `--gpus`. With no GPUs, the container sees none even under an NVIDIA default runtime. |
| `--mount` | Written as a CSV row; a missing source is refused by docker rather than created. |
| GPUs | `--device nvidia.com/gpu=<id>` for each id when the daemon's `DiscoveredDevices` lists every requested one as a CDI device; otherwise `--gpus all` or `--gpus "device=<ids>"`, which needs the NVIDIA container toolkit. |
| idle process | Keeps the container up in the interpreter the serving half uses, found as the [serving half finds one](/reference/remote-execution#bootstrapping-the-serving-half). An image with no usable Python stops at once; `start()` fails. |

| `start()` error | Message |
| --- | --- |
| `docker run` failed | `RuntimeError: could not start a container of <image> on <endpoint>: <stderr>` |
| the container is not Linux | `RuntimeError: the machine at docker://<name> cannot serve linux: it says it is <platform>` |
| the container cannot serve the workspace | `OSError` from the workspace check |

`stop()` runs `docker rm --force <id from the cidfile>` (never a container it did not create)
and removes the temporary directory.

<small>Defined in [`src/hmz/coganchor/machines/docker.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/machines/docker.py), [`src/hmz/coganchor/machines/anchored.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/machines/anchored.py).</small>

## Endpoints {#endpoints}

A docker endpoint names one daemon. `hmz.coganchor.transport.Endpoint.parse` reads:

| Spelling | Daemon | `here` |
| --- | --- | --- |
| `local` or `""` | docker's default, as `DOCKER_HOST`, `DOCKER_CONTEXT` and the current context leave it | yes, unless `DOCKER_HOST` names a non-`unix://` host |
| `unix:///PATH` | the daemon on that socket | yes |
| `tcp://HOST:PORT` | a daemon listening on TCP, plain | no |
| `tcp://HOST:PORT?tls=DIR` | the same, TLS-verified with `DIR/ca.pem`, `DIR/cert.pem`, `DIR/key.pem`; `DIR` absolute | no |
| `ssh://[USER@]HOST[:PORT][?KEYWORD=VALUE&...]` | the daemon on that host, over docker's own ssh transport | no |
| `context:NAME` | the daemon a docker context names | no |

`Endpoint.docker(*argv)` is the only place an endpoint becomes a command line:

- `local`: `docker ARGV`.
- Any other: `env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u
  DOCKER_CERT_PATH docker (--host HOST | --context NAME) [--tlsverify --tlscacert DIR/ca.pem
  --tlscert DIR/cert.pem --tlskey DIR/key.pem] ARGV`.
- `ssh://` with options: `PATH` is prefixed with `$HUMANIZE_HOME/docker-ssh/<16 hex>/`, which
  holds an `ssh` script (mode `0700`) that runs the real `ssh` with the options first. The
  digest is of the rendered flags.

A daemon that is `here` sees this machine's files: the workspace is checked locally and the
container runs as this user. Any other daemon's workspace is a path on its host.

<small>Defined in [`src/hmz/coganchor/transport.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/transport.py) (`Endpoint`, `_ssh_shim`).</small>

## Flow environments {#where-a-flow-s-agents-work}

A flow never sets `AgentConfig.machine`. It declares environment roles, and each session is
opened in one (`await agent.spawn(env=repo)`); the environment decides where that session's
turns land. A `LocalEnv` role is filled by the runtime with the workspace the run started in;
every other role is filled by `-e`.

### `-e` grammar

```text
-e ROLE=BACKEND[@PROVIDER][/WORKDIR][,ROLE=...]
```

| Part | Rule |
| --- | --- |
| `ROLE` | A Python identifier; each role at most once per run. |
| `BACKEND` | `local`, `ssh` or `docker`. |
| `PROVIDER` | `local`: none. `ssh`: a saved ssh [environment provider](#environment-providers), else `[user@]host[:port]` or an alias of the ssh config. `docker`: a saved docker provider, or `local` for docker's default here. May contain `@` (`user@host`). |
| `WORKDIR` | From the first `/` after the provider: an absolute path, or `~/…` under the login's home (ssh), or this user's home (docker on a daemon here). Omitted: the saved provider's `workdir`, which then must be set. |

Items are separated by a comma followed by `KEY=`; a `-e` may be repeated.

| Input | `EnvSpecError` (exit 2) |
| --- | --- |
| not the shape above, or no workdir and none saved | `-e 'repo=ssh@nohost': expected <role>=<backend>[@<provider>]/<workdir>` |
| role not an identifier | `-e '9r=local@/tmp': the role '9r' is not an identifier` |
| unknown backend | `-e 'repo=bogus@x/y': 'bogus' is not a backend; one of local, ssh, docker` |
| `ssh` without a host | `-e 'repo=ssh/y': ssh needs a host, as in ssh@host/workdir` |
| `docker` without a provider | `-e 'repo=docker/y': docker needs a host, as in docker@local/workdir` |
| `local` with a provider | `-e 'repo=local@h/y': local takes no host, as in local@/workdir` |
| a role given twice | `-e: the role 'repo' is given twice` |
| an empty item | `-e '<value>': an item is empty` |

### Resolution

| `-e` | Machine | Session's anchor (harness here) |
| --- | --- | --- |
| `local@/srv/project` | this machine | none: `machine=None` |
| `ssh@HOST/srv/project` | `HOST` over ssh | `AnchorConfig(target="ssh://HOST", workspace="/srv/project")` |
| `ssh@HOST/~/project` | the same | `workspace` is `~` resolved to the login's home once the host has been reached; before that, `remote_path="~/project"` |
| `ssh@NAME/…`, `NAME` a saved ssh provider | the provider's host | `target=` `NAME`'s [target](#an-ssh-host), e.g. `ssh://me@10.0.0.2:2222?IdentityFile=~/.ssh/gpu&ProxyJump=me@bastion` |
| `docker@NAME/…` | a new container on `NAME`'s daemon | `target="docker://humanize-NAME-ROLE-<8 hex>[@<endpoint>]"`, `workspace` the workdir, `shadow` under `$HUMANIZE_HOME/envs/mirrors/<container>/` |
| `docker@local/…` | a new container on docker's default here | the same, with provider `local` |

Where the harness goes for such a session (supervised here, native on the machine, or on a
third machine) is decided by the run's `-H`: see
[Remote execution › Where the harness runs](/reference/remote-execution#where-the-harness-runs).
A `local` environment's work always has its harness here unless `-H standalone:…`.

| Opening refusal | `EnvUnavailable` message |
| --- | --- |
| `local` workdir not a directory | `there is no directory <path> on this machine` |
| ssh destination not a destination | `'<provider>' is not an ssh host, as [user@]host[:port]` |
| a saved ssh provider that cannot be read | `the ssh host '<name>' cannot be read; fix or remove it: <dir>` |
| an unknown docker provider | `docker host '<name>' not found: add one, or use the default docker@local` |
| a saved docker provider that cannot be read | `the docker host '<name>' cannot be read; fix or remove it: <dir>` |
| `~/…` on a docker daemon elsewhere | `<workdir> is on a remote docker host, so it must be an absolute path` |
| a `~` workdir that climbs out of home | `<workdir> climbs out of the home directory it is under` |
| a workdir neither absolute nor under `~` | `<workdir> is neither absolute nor under ~` |

<small>Defined in [`src/hmz/runtime/flowing/specs.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/specs.py) (`parse_envs`), [`src/hmz/runtime/flowing/environments.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/environments.py) (`open_env`), [`src/hmz/runtime/flowing/environing.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/environing.py) (`tidy_workdir`).</small>

### Environment drivers

Every environment is a `MachineEnvDriver` over a machine object; everything derived from it
shares that machine and its connection.

| Backend | Machine | Reached by | Probe |
| --- | --- | --- | --- |
| `local` | `LocalMachine` | processes here | CPUs (`sched_getaffinity`), memory, GPUs by `nvidia-smi`, `git` on `PATH` |
| `ssh` | `SSHMachine` | the [serving half](/reference/remote-execution#bootstrapping-the-serving-half), bootstrapped over `ssh`, exporting `/` as `/` | one command (60 s) printing `home`, `state` (`${HUMANIZE_HOME:-$HOME/.humanize}`), CPUs, memory, `CUDA_VISIBLE_DEVICES`, `nvidia-smi` GPUs and whether `git` is on `PATH` |
| `docker` | `DockerMachine` | the serving half over `docker exec -i` | the ssh probe, run in the container, after the container is started |

- Nothing connects until the run probes its environments, which it does before any agent
  starts (and for a standalone harness machine too).
- Every command runs in its own process group with stdin closed; a timeout, cancellation or
  closing the driver kills the group.
- Derived environments live under humanize's home on that machine:

  ```text
  <state>/envs/<name>-<digest>/          one per workdir things are derived from
      clones/<id>-<digest>/              a temporary copy (reflink where possible)
      scratch/<id>-<digest>/             a scratch directory
      worktrees/<ref>-<random>/          a worktree added with no dir of its own
  ```

  `<digest>` is 12 hex digits of BLAKE2b over the absolute path or id. A docker environment's
  derived directories are inside its container and go with it.

| Error | Meaning |
| --- | --- |
| `EnvUnavailable` | the machine or workdir is not there |
| `EnvConnectionError` | the machine could not be reached, or the connection broke |
| `EnvFileNotFound`, `EnvPermissionDenied` | a path is missing or refused |
| `EnvCommandTimeout` | `<command> ran past its timeout of <n>s in <workdir>, and was killed` |
| `EnvError` | anything else; `<command> was killed: its environment was closed` after close |

<small>Defined in [`src/hmz/runtime/flowing/environing.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/environing.py), [`environing_local.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/environing_local.py), [`environing_ssh.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/environing_ssh.py).</small>

### Docker environments {#docker-environments}

`-e ROLE=docker@PROVIDER/WORKDIR` gives the role one container of its own, started when the run
reaches its environments and removed when the run closes it.

| Aspect | Rule |
| --- | --- |
| Name | `humanize-<provider>-<role>-<8 hex>` |
| Image | the role's `_image` (`ImageEnvMixin`), else the provider's `image`, else `python:3.12-slim` |
| Workdir | a directory of the daemon's host, bind-mounted at its own path; what is written there outlives the container |
| Limits | exactly the role's `_cpu_count`, `_memory` and `_gpu_count` as hard limits; nothing the role does not declare is limited; no GPU unless `GPUEnvMixin` is declared |
| Runtime and arguments | the provider's `runtime` and `run_args`; for the container of a `-H standalone:docker@…` harness, `--cap-add SYS_PTRACE` before them |
| Labels | `humanize.provider`, `humanize.role`, `humanize.host` (this host's name), `humanize.pid` (this process), plus `humanize=<uid>`, `humanize.cpus`, `humanize.memory`, `humanize.gpus` |
| Agents | anchored to the container over `docker exec`; supervised here in a mirror under `$HUMANIZE_HOME/envs/mirrors/<container>/<12 hex>`, or native in the container per `-H` |
| Derived environments | inside the same container |

Allocation, done while holding an exclusive `flock` on
`$HUMANIZE_HOME/env-providers/docker/.<provider>.lock` until the container is up and labelled:

1. `docker info` and `docker ps`/`inspect` of containers labelled `humanize.provider=<provider>`
   (60 s per question).
2. Containers labelled with this user's uid and this host whose `humanize.pid` no longer exists
   are removed (`docker rm --force`), with their mirrors.
3. What the provider may hand out is its saved `cpus`, `memory`, `gpus` (each `0`/empty meaning
   the daemon's own `NCPU`, `MemTotal` and CDI-listed NVIDIA GPUs), `gpu_memory` and
   `max_containers`; what running containers hold is subtracted, read off their labels.
4. For a role asking for a GPU, the daemon's host is asked which GPUs answer: `nvidia-smi
   --query-gpu=index,uuid` in a container of the role's image (`--network none`, 60 s each; an
   answer is kept 300 s per daemon) -- one container per CDI-listed GPU, given `--device
   nvidia.com/gpu=<name>` and `NVIDIA_VISIBLE_DEVICES=void`, all at once; or, where the daemon
   lists none, one given `--gpus all`. Only GPUs that answer are handed out: one the driver is
   bound to, and the CDI specs list, but that has failed since is never handed out; a container
   seeing more than the one GPU it was given is no answer. A GPU is handed out by the CDI name
   it answered under -- `nvidia-smi` renumbers the GPUs after one that fails, the specs do not
   -- or by its UUID where the daemon lists none. A provider's `gpus` may name either. A
   container labelled with a GPU's UUID holds it as surely as one labelled with its name. A GPU
   whose container does not answer in time, while another does, does not answer, and its
   container is removed. Where nothing could be asked -- no `nvidia-smi` put in the container,
   no GPU runtime, no answer in time -- every GPU listed is handed out.
5. GPUs are the first ids no running container holds.
6. Anything short raises `ResourceUnmet`, every shortage joined by `; `:

```text
docker@gpubox runs 4 of the 4 containers it may (one held by humanize-gpubox-box-1a2b3c4d, pid 4242 on gpubox; …)
docker@gpubox has 2 of 16 CPUs free, and 'box' asks for 4 (8 CPUs held by …)
docker@gpubox has 8 GiB of 64 GiB of memory free, and 'box' asks for 16 GiB (…)
docker@gpubox has 0 of 2 GPUs free, and 'box' asks for 1 (GPU 0 held by humanize-gpubox-box-1a2b3c4d, pid 4242 on gpubox; GPU 1 held by …)
docker@gpubox has 0 of 0 GPUs free, and 'box' asks for 1 (its daemon lists no GPU by name: say which in the provider's gpus)
docker@gpubox has 0 of 0 GPUs free, and 'box' asks for 1 (no GPU of its host answers)
docker@gpubox has 1 of 1 GPUs free, and 'box' asks for 2 (1 of the 2 GPUs it lists are usable: 1 is bound but does not answer)
docker@gpubox's GPUs have 24 GiB each, and 'box' asks for 40 GiB
```

| Start failure | Error |
| --- | --- |
| no `docker` here | `EnvUnavailable: docker@<p>: docker was not found on this machine` |
| daemon not answering | `EnvConnectionError: could not connect to docker@<p>: …` |
| container would not start | `EnvUnavailable: docker@<p>: could not start a container of <image> on <endpoint>: …` |
| workdir missing on the daemon's host | `EnvUnavailable: docker@<p> has no <path> to run a container: …` |

A run killed outright leaves its container; the next run on that provider from the same user
and host removes it. To remove humanize containers by hand:

```sh
docker rm -f $(docker ps -q --filter label=humanize=$(id -u))
```

The `humanize` label is the uid on the machine that started the container; on a daemon shared
by several machines the same uid can belong to different users.

<small>Defined in [`src/hmz/runtime/flowing/environing_docker.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/environing_docker.py), [`src/hmz/runtime/flowing/environments.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/environments.py) (`_docker_env`), [`specs/runtime/flowing.md`](https://github.com/humanfia/humanize/blob/main/specs/runtime/flowing.md) (Docker environments).</small>

## Environment providers {#environment-providers}

A saved machine an environment may be put on. Managed from Python with
`Hmz().environments` (`hmz.runtime.doing.environments.Environments`) and in the TUI on the
Environments page of `/settings`.

| Aspect | Rule |
| --- | --- |
| Location | `$HUMANIZE_HOME/env-providers/<backend>/<name>/provider.json`, `<backend>` `ssh` or `docker` |
| Name | `[A-Za-z0-9][A-Za-z0-9._-]*` |
| Modes | every directory humanize creates on the way `0700`; `provider.json` `0600`, written to a temporary file and renamed |
| Format | JSON object: `backend`, `name`, then every field of the provider (tuples as arrays) |
| Reading | a directory whose file is missing, unparseable or invalid is skipped by `all()`; `-e` naming it is refused as unreadable |

```json
{
  "backend": "ssh",
  "name": "gpu",
  "host": "10.0.0.2",
  "user": "me",
  "port": 2222,
  "identity_file": "~/.ssh/gpu",
  "proxy_jump": "me@bastion",
  "options": {"ServerAliveInterval": "15"},
  "alias": "",
  "config": "",
  "workdir": "~/project",
  "made": "typed"
}
```

### An ssh host {#an-ssh-host}

`hmz.coganchor.machines.store.SSHProvider`:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `name` | `str` | required | The provider's name. |
| `host` | `str` | `""` | The machine. With `alias`, sent as `HostName`. |
| `user` | `str` | `""` | The login. |
| `port` | `int` | `0` (config's or 22) | 0–65535. |
| `identity_file` | `str` | `""` | Sent as `IdentityFile`. Never read by humanize. |
| `proxy_jump` | `str` | `""` | Sent as `ProxyJump`. |
| `options` | `Mapping[str, str]` | `{}` | Every other ssh option, sent as `-o KEY=VALUE`. |
| `alias` | `str` | `""` | The `Host` of an ssh config it was imported from; the destination. |
| `config` | `str` | `""` | The ssh config file, sent as `-F`, where it is not `~/.ssh/config`. |
| `workdir` | `str` | `""` | Default workdir for `-e ROLE=ssh@NAME`: absolute, `~` or `~/…`. |
| `made` | `str` | `"typed"` | `typed` or `imported`. |

`target()` is `ssh://[user@]<alias or host>[:port][?F=…&HostName=…&IdentityFile=…&ProxyJump=…&<options>]`.
These options come before humanize's own `ssh` options, and `ssh` keeps the first value it
is given, so they override both humanize's and the user's config. An imported provider keeps
the alias rather than what it resolved to.

Two providers at one host with different options use different ssh master connections.

### A docker daemon {#a-docker-daemon}

`hmz.coganchor.machines.store.DockerProvider`:

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `name` | `str` | required | The provider's name. |
| `endpoint` | `str` | `"local"` | `local`, `unix:///PATH`, `tcp://HOST:PORT`, `ssh://[USER@]HOST[:PORT]` (no options), `ssh:<name>` (a saved ssh provider, with all its options), or `context:<name>`. |
| `tls_dir` | `str` | `""` | For `tcp://` only: directory of `ca.pem`, `cert.pem`, `key.pem`. |
| `image` | `str` | `""` | Default image; no whitespace. |
| `runtime` | `str` | `""` | Container runtime, e.g. `nvidia`. |
| `run_args` | `tuple[str, ...]` | `()` | Extra `docker run` arguments; no newlines. |
| `cpus` | `float` | `0.0` | CPUs it may hand out; `0` for the daemon's `NCPU`. |
| `memory` | `int` | `0` | Bytes it may hand out; `0` for the daemon's `MemTotal`. |
| `gpus` | `tuple[str, ...]` | `()` | GPU ids it may hand out; empty for the daemon's CDI-listed NVIDIA GPUs. |
| `gpu_memory` | `int` | `0` | Bytes per GPU; `0` for unsaid. |
| `max_containers` | `int` | `0` | Containers at once; `0` for no limit. |
| `workdir` | `str` | `""` | Default workdir for `-e ROLE=docker@NAME`. |
| `made` | `str` | `"typed"` | Always `typed`. |

`daemon()` returns the [`Endpoint`](#endpoints): `tls_dir` becomes `?tls=<absolute dir>`, and
`ssh:<name>` becomes `ssh://[user@]host[:port]` carrying every option of that ssh provider.

### Validation

`store.new(backend, name, **fields)` builds and checks one without writing it; `add` refuses
an existing name; `write` replaces. Every refusal is a `ValueError`:

| Input | Message |
| --- | --- |
| backend not `ssh` or `docker` | `'bogus' is not an environment backend: ssh, docker` |
| bad name | `invalid environment provider name '-x': must start with a letter or digit and contain only letters, digits, dots, dashes, and underscores` |
| unknown field | `x: unknown ssh host setting 'bogus'` |
| wrong type | `x: port cannot be '22'` |
| ssh with neither host nor alias | `x: an ssh host requires a hostname or an alias` |
| bad host, alias or user | `x: invalid ssh host '-h'` |
| port out of range | `x: invalid port 70000` |
| bad jump host | `x: invalid jump host '<value>'` |
| an option with its own field (`HostName`, `User`, `Port`, `IdentityFile`, `ProxyJump`) | `x: User must be set with user, not as an option` |
| option `F` or a malformed keyword | `x: invalid ssh option 'F'` |
| an empty option value | `x: option ServerAliveInterval cannot be empty` |
| a value with a newline or `"` | `<what> '<value>' cannot contain newlines or quotes` |
| a relative workdir | `the workdir 'rel' must be absolute or under ~/` |
| bad docker endpoint | `'weird' is not a docker endpoint: local, unix:///PATH, tcp://HOST:PORT, ssh://[USER@]HOST[:PORT], ssh:<ssh host> or context:<docker context>` |
| `tls_dir` without `tcp://` | `x: TLS certificates require a tcp:// endpoint` |
| image with whitespace | `x: invalid image 'a b'` |
| bad runtime | `x: invalid runtime '<value>'` |
| bad or repeated GPU id | `x: invalid GPU id '<id>'`, `x: duplicate GPU specified` |
| negative amount | `x: CPUs cannot be negative: -1.0` (also `memory`, `GPU memory`, `containers`) |
| `add` over an existing one | `ssh host 'gpu' already exists` |
| `ssh:<name>` naming no ssh provider (at `daemon()`) | `ssh:nobody: ssh host 'nobody' not found` |
| a `config` or `tls_dir` under a `~user` with no home (at `write`) | `the config file '<value>': home directory not found` |

### Importing from an ssh config

- `hosts(config=None)` lists every `Host` of the config (default `~/.ssh/config`), following
  `Include` up to depth 16, skipping patterns (`*`, `?`, `!`), and resolves each with
  `ssh -G` (10 s each) into `SSHHost(alias, host, user, port, identity_files, proxy_jump)`.
- `import_ssh(config=None, names=None, *, update=False)` writes one provider per host, named
  after its `Host` with characters outside `[A-Za-z0-9._-]` replaced by `-`, holding
  `alias` (and `config` where not the default). An existing provider is left alone unless
  `update=True`, which rewrites an imported one and keeps its `workdir`; a typed one is never
  overwritten. With `names`, a host the config lacks raises `ssh config has no host <names>`,
  and a host that cannot be imported raises `<alias> cannot be imported: <why>`.

### Checking one

`check(provider, seconds=30)` never raises; it returns `Checked`:

| Field | ssh host | docker daemon |
| --- | --- | --- |
| `reached` | the probe exited 0 and named a home | `docker info` answered with a `ServerVersion` and no `ServerErrors` |
| `said` | why not: the last stderr line, `it did not answer within <n>s`, or the validation error | the same |
| `home` | the login's home | — |
| `cpus`, `memory` | from the probe | `NCPU`, `MemTotal` |
| `gpus` | `("0", …)` by count | CDI-listed GPU ids |
| `gpu_memory` | smallest GPU's memory | — |
| `runtimes` | — | runtimes, the default first |
| `version` | — | the daemon's version |
| `short` | — | `it is to hand out N CPUs and has M`, `it is to hand out N bytes and has M`, `it has no GPU <ids>`, `it has no runtime <r>` |

The ssh check runs the environment probe down the same `ssh` a run uses, in a new session with
no terminal and `SSH_ASKPASS_REQUIRE=never`, so a host that wants a password fails instead of
waiting.

<small>Defined in [`src/hmz/coganchor/machines/store.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/machines/store.py), [`src/hmz/coganchor/machines/sshconfig.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/machines/sshconfig.py), [`src/hmz/runtime/doing/environments.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/doing/environments.py).</small>

## Resources

A flow role declares what its environment's machine must have with mixins from `hmz.flows`:

| Mixin | Attribute | Default when declared | Local and ssh | Docker |
| --- | --- | --- | --- | --- |
| `CPUEnvMixin` | `_cpu_count` | `1` | minimum logical CPUs | `--cpus`, and allocated from the provider |
| `MemoryEnvMixin` | `_memory` | `0` | minimum bytes | `--memory`, and allocated |
| `GPUEnvMixin` | `_gpu_count`, `_gpu_memory` | `1`, `0` | minimum GPUs (as `CUDA_VISIBLE_DEVICES` narrows them) and minimum memory of the smallest | that many GPUs handed out; memory checked against the provider's `gpu_memory` |
| `ImageEnvMixin` | `_image` | `""` | ignored | the container's image |

A local or ssh machine smaller than declared is refused before the run starts:

```text
ResourceUnmet: <flow>: 'box' needs 4 CPUs, and the environment given has 2
```

(also `bytes of memory`, `GPUs`, `bytes of memory per GPU`). A docker environment is sized
to the declaration instead, and refused only when the provider cannot hand it out.

## Capabilities {#capabilities}

### Machine and anchor words

Each setting answers `capabilities` without starting anything.

| Word | Meaning | Said by |
| --- | --- | --- |
| `remote` | Work lands through an anchor, not as ordinary processes here. A `local:` target counts. | `AnchoredConfig`, `DockerConfig` |
| `isolated` | The tools a command finds are the image's. | `DockerConfig` |
| `managed` | Started for the agent and taken down with it. | `DockerConfig` |
| `linux`, `darwin` | The platform. | `DockerConfig` promises `linux`; any machine after `observe()` |
| `anchor:supervised` | The agent runs under a supervisor; files and commands are answered from the target. | the anchor |
| `anchor:native-cli` | The target's own CLI runs there. | the anchor, `native=True` |
| `anchor:afar` | Supervised, with the harness on another machine; always with `anchor:supervised`. | the anchor, harness elsewhere |

| Setting | `capabilities` |
| --- | --- |
| `AnchoredConfig(anchor=AnchorConfig(target="ssh://x"))` | `{"remote", "anchor:supervised"}` |
| `AnchoredConfig(anchor=AnchorConfig(target="ssh://x", native=True))` | `{"remote", "anchor:native-cli"}` |
| `DockerConfig()` | `{"remote", "isolated", "managed", "linux", "anchor:supervised"}` |

`MachineBase.capabilities` is the setting's words plus what `observe(anchor)` saw.
`observe` performs the [`check`](/reference/remote-execution#from-python) handshake and
workspace listing, adds the platform the handshake reports, and raises:

- `OSError` if the machine cannot be reached or lacks the workspace;
- `RuntimeError: the machine at <target> cannot serve <words>: it says it is <platform>` if a
  platform the setting promised is not the one reported.

### Environment capabilities

An environment driver serves every environment mixin (`ENV_CAPABILITIES`) except where the
machine lacks what one needs:

| Mixin | Served when |
| --- | --- |
| `GitEnvMixin`, `GitWorktreeEnvMixin` | the machine's probe found `git` on `PATH`: this process's `PATH` for `local`, the login's for `ssh`, the image's for `docker`. Unknown before the probe counts as served. |
| `BashEnvMixin` | the same probe found `bash` on `PATH` |
| `RewindableEnvMixin` | declared through `GitEnvMixin`, which implements it |
| every other | always |

A role declaring a mixin its environment does not serve is refused before anything runs:

```text
CapabilityMissing: <flow>: 'repo' needs GitEnvMixin, which ssh@gpu-box/srv/project does not support: GitEnvMixin needs git on the machine's PATH, and it has none
```

<small>Defined in [`src/hmz/coganchor/places.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/places.py), [`src/hmz/coganchor/machines/base.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/coganchor/machines/base.py) (`observe`), [`src/hmz/runtime/flowing/environing.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/environing.py) (`MachineEnvDriver.capabilities`), [`src/hmz/runtime/flowing/engine.py`](https://github.com/humanfia/humanize/blob/main/src/hmz/runtime/flowing/engine.py) (`_serves_env`, `_meets`).</small>

## Mirrors

A supervised agent works in a mirror of the target's workspace on the harness machine. Where
it is:

| Case | Mirror |
| --- | --- |
| `AnchoredConfig` with `shadow` unset, harness here | the workspace's own absolute path on this machine |
| `-e ssh@…` session, harness here | the same: the workdir's path on this machine |
| `DockerConfig` machine | `<tmp>/humanize-<random>/shadow`, removed with the container |
| `-e docker@…` session, harness here | `$HUMANIZE_HOME/envs/mirrors/<container>/<12 hex of the workdir>`, removed with the container |
| harness on another machine, `shadow` unset | `$HOME/.cache/humanize-mirrors/<16 hex>` there (`/tmp/humanize-mirrors/<16 hex>` in a container), kept between turns |

A mirror path that already holds unrelated files, or was last used for another target, is
refused unless `force` is set (see
[Remote execution › The mirror](/reference/remote-execution#the-mirror)). For an ssh
environment this means the workdir's path must be free on this machine, or a previous mirror
of the same host.

## `Mapped` and `Ran`

`Mapped(anchor)` reaches an anchor's workspace from this process, over the same connection a
turn uses. Nothing connects until a member is used; it is a context manager, and iterating it
lists the workspace.

| Member | Behaviour |
| --- | --- |
| `workspace` | the workspace as the machine names it |
| `read_text(path, encoding="utf-8")`, `read_bytes(path)` | a file's contents |
| `write_text(path, said, encoding="utf-8", mode=None)`, `write_bytes(path, said, mode=None)` | replace a file; `mode=None` keeps its permissions |
| `listdir(path="")` | names in a directory |
| `exists(path)` | whether it exists; `OSError` when the machine cannot be reached |
| `mkdir(path, *, parents=True)`, `remove(path)` | make a directory; remove a file |
| `run(argv, *, cwd="", env=None) -> Ran` | run a command there and wait; `argv` a list or one shell-split string; `env` is added to the machine's environment |
| `close()` | release the connection; idempotent |

Paths are absolute as the machine names them, or relative to the workspace.

`Ran` has `argv: tuple[str, ...]`, `status: int`, `output: str` (both streams, in arrival
order) and `ok` (`status == 0`). A signal-killed command reads `128 + signal`; one whose end
was never reported reads `1`.

## `allocations`

```python
allocations(endpoint="local", labels=None, *, seconds=None) -> list[Allocation]
```

Every running container labelled `humanize` on one daemon, whoever started it, optionally
narrowed to those carrying every label in `labels`. `Allocation` has `name`, `cpus`
(`float | None`), `memory` (`int | None`), `gpus` (`tuple[str, ...] | "all"`) and `labels`,
read off the `humanize.cpus`, `humanize.memory` and `humanize.gpus` labels; a malformed
label reads as `None`. A daemon that cannot be asked raises `OSError: could not ask <endpoint>
what it runs: …`; `seconds` bounds each question (`OSError` `ETIMEDOUT` past it).

`info(endpoint="local", seconds=None)` returns `docker info` as a dict, and
`gpus_listed(devices, kind="")` the GPU ids a daemon's `DiscoveredDevices` name.
`gpus_usable(endpoint, image, devices, *, seconds=None)` returns the GPUs of the daemon's
host that answer, as `(name, uuid)` pairs -- `name` the CDI name, or `nvidia-smi`'s index
where the daemon lists none; `()` where none answers -- or `None` where nothing could be
asked; one answer per daemon is kept for `USABLE_FOR` (300 s).

## Writing a machine of your own {#writing-a-machine-of-your-own}

| Type | Contract |
| --- | --- |
| `MachineConfig` | Frozen, keyword-only dataclass. `capabilities` returns only words above (default empty). `create()` returns a new, unstarted machine per call. |
| `MachineBase.start() -> AnchorConfig` | Leaves the machine ready for turns and returns the anchor that reaches it. On failure, takes down whatever it created before re-raising. Should call `observe(anchor)` to confirm a promised platform. |
| `MachineBase.stop()` | Called once for a machine that was started, never for one that was not. Leaves the workspace. Default: nothing. |
| `MachineBase.observe(anchor)` | Provided; see [Capabilities](#capabilities). |

```python
from dataclasses import dataclass

from hmz.coganchor import AnchorConfig
from hmz.coganchor.machines import MachineBase, MachineConfig


@dataclass(frozen=True, kw_only=True)
class PodmanConfig(MachineConfig):
    image: str = "python:3.12"

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"remote", "isolated", "managed", "linux"}) | AnchorConfig().capabilities

    def create(self) -> "Podman":
        return Podman(self)


class Podman(MachineBase):
    def start(self) -> AnchorConfig:
        anchor = ...  # bring it up
        try:
            self.observe(anchor)
        except BaseException:
            self.stop()
            raise
        return anchor

    def stop(self) -> None:
        ...  # take down what start() brought up
```

<small>Contract: [`specs/coganchor/machines.md`](https://github.com/humanfia/humanize/blob/main/specs/coganchor/machines.md).</small>

## Environment variables

Every variable humanize reads is listed in [Environment variables](/reference/environment).

| Variable | Effect |
| --- | --- |
| `HUMANIZE_HOME` | Root of `env-providers/`, `envs/` (mirrors, derived directories here), `docker-ssh/` and `harness/`; default `~/.humanize`. On an ssh host, `${HUMANIZE_HOME:-$HOME/.humanize}` there is where derived directories go. |
| `DOCKER_HOST`, `DOCKER_CONTEXT` | Used by the `local` endpoint; `DOCKER_HOST` decides whether `local` counts as here. Removed from every `docker` sent to any other endpoint, with `DOCKER_TLS`, `DOCKER_TLS_VERIFY`, `DOCKER_CERT_PATH`. |
| `DOCKER_CONFIG` | Where docker reads `context:NAME` contexts (docker's own). |
| `CUDA_VISIBLE_DEVICES` | Narrows the GPUs counted on a local or ssh machine, as CUDA does. |
| `HUMANIZE_SSH_REUSE` | `off`, `0`, `no`, `false` (any case, trimmed) or empty disables ssh connection sharing. |
| `SSH_ASKPASS_REQUIRE` | Set to `never` for `check()` of an ssh provider. |

## API summary

```python
from hmz.coganchor.machines import (
    MachineConfig, MachineBase, AnchoredConfig, Anchored, DockerConfig, Docker,
    Allocation, allocations, info, gpus_listed, Mapped, Ran,
)
from hmz.coganchor.machines.store import (
    SSHProvider, DockerProvider, new, add, write, find, providers, remove, where, under,
    imports, daemon_of,
)
from hmz.coganchor.transport import Endpoint
from hmz.coganchor.agents import anchored
from hmz.sdk import Hmz  # Hmz().environments
```

| `Hmz().environments.` | |
| --- | --- |
| `all(backend="")` | every provider, by backend then name |
| `find(backend, name)` | one, or `None` |
| `where(backend, name)` | its directory |
| `new(backend, name, **fields)` | build and check, unwritten |
| `add(provider)` | write a new one |
| `write(provider)` | write, replacing |
| `remove(backend, name) -> bool` | delete its directory |
| `hosts(config=None)` | ssh config hosts, resolved |
| `import_ssh(config=None, names=None, *, update=False)` | import ssh config hosts |
| `resolve(provider) -> SSHHost` | what `ssh -G` makes of a provider |
| `check(provider, seconds=30) -> Checked` | ask it what it has |
