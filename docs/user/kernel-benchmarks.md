# Run kernel benchmarks on KCoral

An agent can edit a kernel in its usual workspace while its evaluator runs on
a KCoral GPU worker. Choose `local` or `kcoral` at the evaluator command;
the coding agent and flow stay the same.

The [flowverse kernel benchmark example](https://github.com/humanfia/flowverse/tree/main/examples/kernel-benchmark)
provides a runner, a multi-file Triton smoke task, and the full execution
contract. It works with existing flows such as `ralph_loop` and `flame_chase`.

## Connect a service

Install the [KCoral client](https://github.com/cmu-catalyst/kcoral) on the machine
where the agent runs shell commands. Its `kcoral run shell --help` command must
work. The client machine does not need CUDA or PyTorch.

The GPU machine needs the KCoral server environment and the evaluator's
dependencies. Start the service there, or use an existing server or Router:

```sh
kcoral server --device gpu --gpus 0 --workers-per-gpu 1 \
  --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
```

For a different machine, use a reachable service URL or an SSH tunnel.
`127.0.0.1` refers to the machine or container running the client. KCoral runs
uploaded code, so keep the service on a trusted network. Check the health
response's GPU target and versions, then run a smoke evaluation: health alone
does not prove that a worker can execute your task.

## Select the benchmark backend

In a flowverse checkout, run the supplied example:

```sh
python tools/kernel_benchmark.py --backend kcoral \
  --url http://127.0.0.1:8000 \
  --bundle examples/kernel-benchmark/experiment \
  --fetch results --out /tmp/kernel-trial-001 -- python evaluate.py
```

The bundle holds the candidate, evaluator and inputs. The evaluator runs from
inside that directory on either backend. KCoral snapshots it for each request;
`--fetch results` saves the report at
`/tmp/kernel-trial-001/experiment/results/report.json`. Use a new `--out` per
trial. To use your local GPU, change to `--backend local` and omit `--url`.

For your own task, give an existing flow the runner's absolute path and the
exact evaluator command:

```sh
hmz exec -f /ABS/flowverse/flows/ralph_loop \
  -a agent=codex/gpt-5.6-sol:high -b duration=30m \
  'Optimize experiment/kernel.py. Keep the evaluator and correctness checks
   unchanged. Run every trial with:
   python /ABS/flowverse/tools/kernel_benchmark.py --backend kcoral
     --url http://127.0.0.1:8000 --bundle experiment -- python evaluate.py
   A nonzero exit is a failed trial. Keep the measured JSON and tested source.'
```

`HMZ_BENCHMARK_BACKEND` and `KCORAL_URL` can set defaults. Explicit arguments
are useful for a run held by an existing daemon, whose environment may predate
your terminal's exports. They also make a recorded official evaluator command
unambiguous. A flow such as `parallel_flame_chase_git_pr` can record this command
with `pfc evaluate`; the task still supplies its score format and validation.

The runner preserves ordinary evaluator failure and output. There is no
fallback to a local GPU when the service fails. `--timeout` bounds each remote
request subject to the server's cap, independently of the flow budget.
Interrupting the client may leave the remote request running until that
deadline. Fetch artifacts explicitly; the next request has a fresh workspace.
Keep credentials, virtual environments and unrelated files outside the bundle.

Correctness and timing remain the evaluator's job. Measure kernel latency on
the GPU after validation; an HTTP round trip also includes upload, compilation
and queueing. Neither exit zero nor a completed KCoral request alone proves a
kernel correct.

## Who starts the server

**The user or service manager owns the server; humanize connects to its URL.**
This supports a GPU service shared by several flows and agents on CPU-only
machines. KCoral controls workers, GPU leases, request isolation and deadlines;
humanize controls agent sessions and the flow budget.

Automatically starting a server for every flow would require choosing GPUs,
ports and CUDA environments, and deciding what happens to the server when a
run detaches, resumes or ends. Humanize cannot infer whether a URL belongs to
one run or to other users. It therefore does not restart or shut down the
service. Automatic startup can be handled by a service manager. A future
humanize-managed option should be explicit, track the process it owns, and
only clean up that process.

KCoral is also not an agent environment backend. Humanize's environments keep
files and processes across agent turns; KCoral executes stateless requests.
Use a local, SSH or container workspace for the agent and connect the
evaluator command to KCoral.
