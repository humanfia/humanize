---
title: Environments and runtimes
description: Look up how to spell an environment for -e, every field of a saved runtime, the target spellings, and the environment mixins a flow can declare.
---

# Environments and runtimes

An environment is a working directory on a machine. Use this page to look up environment specs, saved runtime fields, target spellings, and flow mixins. For guides, see [Environments](/user/environments), [Runtimes](/user/runtimes), and [Environment roles](/builder/environments).

## Environment spec

Pass one spec per environment role to `hmz exec -e`. Repeat the flag or separate specs with commas.

```text
ROLE=BACKEND[@PROVIDER][/WORKDIR]
```

![The parts of an environment spec: role, backend, optional provider, optional workdir](/diagrams/reference-environments-1.svg)

| Part | Rule |
| --- | --- |
| `ROLE` | A Python identifier. The name of a role in the flow's `EnvCollection`. Once per run. |
| `BACKEND` | One of `local`, `ssh`, `docker`, `swarm`, `apple-container`, `slurm`. |
| `@PROVIDER` | The name of a saved runtime of that backend. For `ssh` only, a host that is not saved, in brackets: `[USER@]HOST[:PORT]`. Left off, it is this machine. `local` takes none. `ssh` always needs one. |
| `/WORKDIR` | Starts at the first `/` after the provider. Absolute, or `/~/...` for a directory under the home. May be left off only for a runtime saved with a `workdir`. |

Pass the same spec without `ROLE=` to `hmz chat -e`, to `env` in `chat.start` and `chat.move`, and to each value of the `envs` map when an epic starts.

```sh
hmz exec -f FLOW -e repo=ssh@build-box/home/alex/shop "add a discount code to checkout"
hmz exec -f FLOW -e repo=ssh@build-box -e scratch=local/tmp/scratch "add a discount code to checkout"
hmz exec -f FLOW -e repo=docker/srv/shop,far=ssh@[alex@far.host:2222]/srv/shop "add a discount code to checkout"
hmz chat -e ssh@build-box/~/shop "what does checkout do?"
```

| Spec | Where the role works |
| --- | --- |
| `local/srv/shop` | `/srv/shop` on this machine. |
| `local/~/shop` | `shop` under your home on this machine. |
| `ssh@build-box/home/alex/shop` | That directory on the ssh host saved as `build-box`. |
| `ssh@build-box/~/shop` | `shop` under the login's home on that host. |
| `ssh@build-box` | The workdir `build-box` was saved with. |
| `ssh@[alex@far.host:2222]/srv/shop` | A host that is not saved. |
| `docker/srv/shop` | A container on docker's default here, with `/srv/shop` of this machine mounted. |
| `docker@box/srv/shop` | A container on the docker runtime saved as `box`. |
| `swarm/srv/shop` | A service on the swarm this machine manages. |
| `swarm@cluster/srv/shop` | A service on the swarm saved as `cluster`. |
| `apple-container/Users/alex/shop` | An Apple container on this Mac. |
| `apple-container@mac/Users/alex/shop` | One out of what the runtime saved as `mac` may hand out. |
| `slurm/lustre/alex/shop` | A job on the cluster this machine submits to, with the cluster's defaults. |
| `slurm@hpc/lustre/alex/shop` | A job asked for as the runtime saved as `hpc` says. |

Invalid specs stop `hmz exec` with exit status 2 and a message that says what is wrong. Deprecated spellings fail the same way, with the current spelling in the message: `local@/x`, `docker@local/x`, and an unsaved ssh host written without brackets.

A `LocalEnv` role uses the directory where the run started and takes no `-e`. A role declared `NotRequired` may be left without one.

## Backends

| Backend | What a role gets | Created | Removed |
| --- | --- | --- | --- |
| `local` | A directory on the machine the daemon runs on. The directory must exist. | — | — |
| `ssh` | A directory on a host reached with the system `ssh`. | — | — |
| `docker` | A container of its own on a docker daemon. The workdir is a directory of the daemon's host, mounted at the same path. | When the run opens its environments | When the run closes it |
| `swarm` | A service of one task on a docker swarm, placed by the swarm's scheduler. The workdir must exist at the same path on every node. | When the run opens its environments | When the run closes it |
| `apple-container` | A container of Apple's `container` tool on this Mac: a small Linux virtual machine. No GPUs. | When the run opens its environments | When the run closes it |
| `slurm` | A job of one task on one node, submitted with `sbatch`. The workdir must be on a filesystem shared by this machine and every node. | When the run opens its environments | Cancelled with `scancel` when the run closes it |

Machines reached over `ssh` require Linux or macOS on x86-64 or aarch64, `/bin/sh`, and passwordless login. Containers and Slurm nodes require Linux and `/bin/sh`. You do not need to install anything else on the target.

## Saved runtimes

Save machines under `runtimes.<backend>.<name>` in `settings.yaml` inside the Humanize home. Start each name with a letter or digit, followed by letters, digits, `.`, `_`, or `-`. Omitted fields take their defaults.

```yaml
runtimes:
  ssh:
    build-box:
      host: 10.0.0.2
      user: alex
      workdir: ~/shop
      fallback: [docker:box]
  docker:
    box:
      image: python:3.12
      cpus: 8
      memory: 17179869184
      harness: local
  slurm:
    hpc:
      partition: gpu
      max_wait: 600
```

### Common fields

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `workdir` | string | `""` | Default working directory when the spec omits one. Absolute, or under `~/`. |
| `fallback` | list | `[]` | Runtimes to try in order when this one cannot hold a role, each `<backend>:<name>`. Cannot contain itself or duplicates. A fallback runtime does not follow its own fallback list. `docker:local`, `swarm:local`, `apple-container:local` and `slurm:local` name the default on this machine, unless a runtime is saved as `local`. |
| `harness` | string | `env` | Where the agent's CLI runs: `env` (on the runtime's machine), `local` (on this machine), or `<backend>:<name>` (on another saved runtime). Cannot name itself. |
| `made` | string | `typed` | Origin: `typed`, or `imported` for an ssh host read from an ssh config. |

### `ssh`

Set `host` or `alias`. Configured fields override your ssh config.

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `host` | string | `""` | Host name or address. |
| `user` | string | `""` | Login user. Defaults to the ssh config or local user. |
| `port` | integer | `0` | Port, 0 to 65535. `0` uses the config's port or 22. |
| `identity_file` | string | `""` | Path to the private key. |
| `proxy_jump` | string | `""` | Jump host or hosts. |
| `options` | map | `{}` | Extra ssh options passed as `-o KEYWORD=VALUE`. Cannot include `F`, `HostName`, `User`, `Port`, `IdentityFile`, or `ProxyJump`: use the fields. |
| `alias` | string | `""` | The `Host` entry imported from an ssh config. `ssh` resolves it through that config. |
| `config` | string | `""` | Path to the source ssh config file, if not the default. |

### `docker`

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `endpoint` | string | `local` | Daemon address. See [Docker endpoints](#docker-endpoints). |
| `tls_dir` | string | `""` | Directory containing `ca.pem`, `cert.pem`, and `key.pem` for a `tcp://` endpoint. |
| `image` | string | `""` | Default container image when the flow declares none. Falls back to `python:3.12-slim`. |
| `runtime` | string | `""` | OCI runtime, such as `nvidia`. Empty uses the daemon's default. |
| `run_args` | list | `[]` | Extra arguments for `docker run`. |
| `name_prefix` | string | `""` | Container name prefix before the role and 8 hex digits. Defaults to `humanize-<name>`. Max 54 characters. |
| `cpus` | number | `0` | CPUs available to allocate. `0` means all available. |
| `memory` | integer | `0` | Bytes of memory available to allocate. `0` means all available. |
| `gpus` | list | `[]` | GPU device IDs available to allocate. |
| `gpu_memory` | integer | `0` | Bytes of memory per GPU. `0` leaves it unspecified. |
| `max_containers` | integer | `0` | Maximum concurrent containers. `0` means no limit. |
| `container` | string | `""` | Name or ID of an existing running container. All roles assigned here share it. Humanize does not start, count, or stop it. |
| `exec_user` | string | `""` | Numeric `UID[:GID]` for commands inside the container. |
| `exec_env` | list | `[]` | `NAME=VALUE` environment variables for commands inside the container. |
| `exec_wrapper` | list | `[]` | Command prefix run before every command in the container. |

If you set `container`, do not set `image`, `runtime`, `run_args`, `name_prefix`, `cpus`, `memory`, `gpus`, `gpu_memory`, or `max_containers`.

Run `docker inspect` to view the resource labels on a container Humanize starts. Each is set only when the environment was given that resource. Humanize reads these labels to total the resources a runtime has allocated:

| Label | Value |
| --- | --- |
| `humanize.cpus` | CPUs given to the environment. |
| `humanize.memory` | Memory in bytes. |
| `humanize.gpus` | Device IDs joined by commas, or `all`. |

### `swarm`

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `endpoint` | string | `local` | Swarm manager address, written as a docker endpoint. |
| `tls_dir` | string | `""` | Directory containing `ca.pem`, `cert.pem`, and `key.pem` for a `tcp://` endpoint. |
| `image` | string | `""` | Default task image when the flow declares none. Every node must be able to pull it. |
| `run_args` | list | `[]` | Extra arguments for `docker service create`. |
| `name_prefix` | string | `""` | Service name prefix. Defaults to `humanize-<name>`. Max 54 characters. |
| `cpus` | number | `0` | Total CPUs tasks may reserve. `0` means all node capacity. |
| `memory` | integer | `0` | Total bytes of memory tasks may reserve. `0` means all node capacity. |
| `gpu_resource` | string | `""` | Generic resource name nodes use to advertise GPUs, such as `NVIDIA-GPU`. Empty allocates no GPUs. |
| `constraints` | list | `[]` | Placement constraints, each `<attribute>==<value>` or `<attribute>!=<value>`. |
| `max_tasks` | integer | `0` | Maximum concurrent tasks. `0` means no limit. |
| `nodes` | map | `{}` | Map of node hostnames to a saved ssh runtime name or `[USER@]HOST[:PORT]`. Unlisted nodes connect over ssh at their own address. |

### `apple-container`

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `image` | string | `""` | Default container image when the flow declares none. |
| `run_args` | list | `[]` | Extra arguments for `container run`. |
| `cpus` | number | `0` | Total CPUs across containers. `0` means all Mac CPUs. |
| `memory` | integer | `0` | Total bytes of memory across containers. `0` means all Mac memory. |
| `max_containers` | integer | `0` | Maximum concurrent containers. `0` means no limit. |

### `slurm`

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `partition` | string | `""` | Target partition. Empty uses the cluster default. |
| `account` | string | `""` | Billing account. Empty uses your default. |
| `qos` | string | `""` | Quality of service. Empty uses the default. |
| `time` | string | `""` | Time limit passed to `--time`: minutes, `MM:SS`, `HH:MM:SS`, `D-HH[:MM[:SS]]`, `UNLIMITED`, or `INFINITE`. Empty uses the partition default. |
| `constraint` | string | `""` | Required node features passed to `--constraint`. |
| `via` | string | `srun` | Node connection method: `srun` (one job step per connection) or `tcp` (direct connection to a node port reachable from this machine). |
| `run_args` | list | `[]` | Extra arguments for `sbatch`. |
| `cpus` | number | `0` | Total CPUs across jobs. `0` means cluster capacity. |
| `memory` | integer | `0` | Total bytes of memory across jobs. `0` means cluster capacity. |
| `max_jobs` | integer | `0` | Maximum queued and running jobs. `0` means no limit. |
| `max_wait` | integer | `0` | Seconds a job waits for a node before failing. `0` waits indefinitely. |
| `python` | string | `""` | Accepted and ignored. Nodes do not require Python. If set, must be absolute or under `~/`. |

### Docker endpoints

Set `endpoint` on a `docker` or `swarm` runtime to one of these values:

| Spelling | Daemon |
| --- | --- |
| `local` | Default local `docker` daemon. |
| `unix:///PATH` | Local Unix socket. |
| `tcp://HOST:PORT` | Remote daemon over TCP. Set `tls_dir` for TLS. |
| `ssh://[USER@]HOST[:PORT]` | Daemon on an ssh host. |
| `ssh:<name>` | Daemon on the named ssh runtime. |
| `context:<name>` | Named docker context. |

## Target spellings

A target identifies a destination machine for `hmz internal anchor --target` and `--harness`. See [CLI](/reference/cli).

| Spelling | Machine |
| --- | --- |
| `local` | This machine. |
| `local:DIR` | This machine, using `DIR` as the workspace. |
| `ssh://[USER@]HOST[:PORT][?KEYWORD=VALUE&...]` | Host over ssh. Options pass as `-o KEYWORD=VALUE`; `F` sets the config file. |
| `docker://CONTAINER[?user=UID[:GID]&env=NAME=VALUE&exec=WORD][@ENDPOINT]` | Running container. `ENDPOINT` is `local`, `unix:///PATH`, `tcp://HOST:PORT[?tls=DIR]`, `ssh://[USER@]HOST[:PORT][?KEYWORD=VALUE&...]`, or `context:NAME`. |
| `apple-container://CONTAINER` | Running Apple container on this Mac. |
| `slurm://JOBID[?python=PATH]` | Node of a running Slurm job. `python` is accepted and ignored. |
| `tcp://HOST:PORT` | Running server listening at this address. |
| `peer://TICKET@HOST:PORT` | Running server reached through a rendezvous broker. |

Humanize automatically starts its server on `local`, `ssh`, `docker`, `apple-container`, and `slurm` targets. `tcp` and `peer` targets must already be running.

A `tcp://` or `peer://` session runs over TLS 1.3 with ALPN `hmz-anchor`. On startup, the server generates a self-signed P-256 certificate in memory, requiring no configuration or certificate files. Neither side sends the shared secret (`--token`, `--token-file`, `HUMANIZE_TOKEN`, or the `peer://` ticket). Instead, each side proves possession with an HMAC bound to the server's public key. Sessions to other targets run unwrapped over a pipe. A server or client built before this TLS layer cannot connect to one built with it.

::: warning
An `env` option on a `docker://` target appears in command lines and logs. Do not pass secrets in it.
:::

## Environment mixins

Type each role in a flow as `Env` combined with mixins from `hmz.flows`. Calling a method from an undeclared mixin raises `CapabilityNotGranted`. See [Flow API](/reference/flows) for full signatures.

Base `Env` members:

| Member | Meaning |
| --- | --- |
| `available` | Whether the machine was reached and the workdir existed on last check. |
| `backend` | The backend (`EnvBackendKind`). |
| `provider` | Provider name, or `""` for this machine. |
| `role` | Role name. |
| `workdir` | Working directory for commands. |
| `await env.derive_subdir(subdir=...)` | Returns an environment in a subdirectory on the same machine, creating it if needed. |

### Capability mixins

| Mixin | Adds | The machine needs |
| --- | --- | --- |
| `ShellEnvMixin` | `await env.exec(argv, timeout=0)` returns `(status, stdout, stderr)`. Runs directly without a shell. `timeout=0` disables the timeout. | — |
| `BashEnvMixin` | `exec` also accepts a string to run via `bash -c`. | `bash` |
| `FilesEnvMixin` | `await env.read(path)` returns bytes. `await env.write(path, data)` writes a full file. | — |
| `GitWorktreeEnvMixin` | `await env.derive_worktree(ref=None, dir=None)` returns an environment in a new detached worktree. | `git` |
| `GitEnvMixin` | `await env.snapshot(name=None)`, `await env.rewind(ref)`, `await env.snapshots()`. | `git` |
| `RewindableEnvMixin` | Interface implemented by `GitEnvMixin`. Declare `GitEnvMixin` instead. | — |
| `TemporaryClonedDirEnvMixin` | `await env.derive_temp_clone(id)`, `await env.destroy_temp_clone(id)`: creates and removes a throwaway copy of the workdir. | — |
| `ScratchDirEnvMixin` | `await env.derive_scratch(id)`, `await env.destroy_scratch(id)`: creates and removes an empty directory on the same machine. | — |

If a machine lacks a required tool for a mixin, the run fails before starting with `CapabilityMissing`.

### Resource mixins

Set these class attributes on the role class to request hardware or images.

| Mixin | Attribute | Default | Meaning |
| --- | --- | --- | --- |
| `CPUEnvMixin` | `_cpu_count` | `1` | CPUs. |
| `MemoryEnvMixin` | `_memory` | `0` | Bytes of memory. |
| `GPUEnvMixin` | `_gpu_count` | `1` | GPUs. |
| `GPUEnvMixin` | `_gpu_memory` | `0` | Bytes of memory per GPU. |
| `ImageEnvMixin` | `_image` | `""` | Container image for `docker`, `swarm`, and `apple-container`. Empty uses the runtime's `image`, then `python:3.12-slim`. |

| Backend | How resources apply |
| --- | --- |
| `local`, `ssh` | Verified as minimums before the run starts. |
| `docker` | Enforced as hard container limits (`--cpus`, `--memory`) and allocated GPU IDs. |
| `swarm` | Set as service reservations and limits (`--reserve-cpu`, `--limit-cpu`, `--reserve-memory`, `--limit-memory`, `--generic-resource`). |
| `apple-container` | Sets the VM size. Refuses roles that declare `GPUEnvMixin`. |
| `slurm` | Passed as job requests (`--cpus-per-task`, `--mem`, `--gpus`). |

If a runtime cannot meet these requirements, it moves the role to its `fallback` or fails with `ResourceUnmet`.
