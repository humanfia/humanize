---
pageClass: hmz-feature
---

# recursive_lean_prover

Prove a theorem in Lean by splitting it up. Each lemma is planned, proved in prose, split into
child lemmas where it needs to be, and formalized in a git worktree of its own. Every lemma
your comparator and a fresh reviewer accept is written to a Markdown wiki as it lands.

<Badge type="warning" text="worker: claude · codex · kimi · zcode" />
<Badge type="info" text="meant for codex in both roles" />

::: code-group

```text [at the prompt]
❯ $recursive_lean_prover prove the theorem stated in PROBLEM.md, in Submission.lean
```

```sh [hmz exec]
hmz exec -f recursive_lean_prover \
    -a worker=codex/gpt-5.6-sol:max -a reviewer=codex/gpt-5.6-sol:max \
    -p lean_target=Submission.lean -p 'comparator_command=bash tools/check-with-comparator.sh' \
    -b duration=72h "$(cat PROBLEM.md)"
```

:::

<HmzFlowShape flow="recursive_lean_prover" />

## Before you run it

- **A clean Lean git repository**, with `.humanize/` in its `.gitignore`. Run the flow at its
  root.
- **A comparator**: a script that checks a candidate and exits zero, printing
  `comparator_success`, only when every check has passed. It gets `HUMANIZE_NODE_ID`,
  `HUMANIZE_NODE_STATEMENT`, `HUMANIZE_LEAN_FILES`, `HUMANIZE_RUN_DIR` and `HUMANIZE_WIKI_DIR`
  in its environment:

```sh
#!/usr/bin/env bash
set -euo pipefail
lake env lean Submission.lean
./tools/project-comparator "$HUMANIZE_NODE_ID"
printf '%s\n' 'Your solution is okay!'
```

- **A task file** stating the exact theorem, the Lean file that may be edited, anything that
  must not be read or changed, and any rules for accepting a proof.

## How each lemma goes

1. **One plan**, written once by [`humanize1:gen-plan`](/flows/humanize1#gen-plan) and never
   rewritten.
2. **A proof in prose**, revised from the reviewer's first invalid step until it holds.
3. **A split**, where the lemma needs one: child lemmas with exact Lean statements and the
   order they depend on each other in. Each child goes through these same steps.
4. **Lean, in a worktree of its own**: [`humanize1:rlcr`](/flows/humanize1#rlcr) builds the
   formal proof on a named branch.
5. **Acceptance**: your comparator passes, then a fresh reviewer runs it again. The lemma goes
   into the wiki, and whatever was waiting on it can start.

Lemmas whose dependencies are proved run at the same time, up to `max_parallel_children`. The
run prints its directory as it starts; watch the graph of lemmas grow in the `DAG.md` there.

## Roles and params

| Role | |
| --- | --- |
| `worker` | Writes every plan, proof and Lean formalization. Must be `claude`, `codex`, `kimi` or `zcode`: `rlcr`'s guards work through its permission requests. |
| `reviewer` | Checks every proof and candidate, and reruns the comparator itself. |

Every turn is a fresh session. Both roles may write across your home directory and use the web.

Every param has a default:

| Param | Default | |
| --- | --- | --- |
| `lean_target` | blank | The `.lean` file the worker edits. Blank lets it work that out. |
| `comparator_command` | `bash tools/check-with-comparator.sh` | The comparator, run without a shell. May use `{node_id}`, `{node_dir}`, `{run_dir}`, `{wiki_dir}`, `{lean_target}` and `{lean_files}`. |
| `comparator_success` | `Your solution is okay!` | What a passing comparator prints. |
| `comparator_timeout` | `21600` | Seconds each comparator run may take. |
| `max_depth` | `2` | How deep lemmas may be split, 0 to 6. The theorem itself is depth 0. |
| `max_children` | `4` | Most child lemmas one lemma may split into, 2 to 12. |
| `max_nodes` | `24` | Most lemmas in the whole run; at least 3 when `max_depth` is not 0. |
| `max_parallel_children` | `24` | Most lemmas worked on at once. |
| `natural_proof_attempts` | `3` | Prose revisions per batch. Another batch follows while the proof still fails. |
| `decomposition_attempts` | `2` | Tries at a valid split. |
| `rlcr_rounds` | `20` | Rounds of `rlcr` per lemma. |
| `plan_turn_timeout` | `3600` | Seconds one planning turn may take; `0` for no limit. |
| `plan_total_timeout` | `14400` | Seconds one lemma's planning may take; `0` for no limit. |
| `stop_on_child_failure` | `true` | Hold a lemma back when a child it needs fails. |
| `artifact_dir` | `.humanize/recursive-lean-prover` | Plans, proofs, the graph of lemmas and logs. Must be under `.humanize/`. |
| `wiki_dir` | `.humanize/math-wiki` | The wiki of accepted lemmas. Must be under `.humanize/`. |
| `node_attempts` | `2` | Accepted for compatibility; it changes nothing. |
| `plan_attempts` | `1` | Fixed at `1`: each lemma gets exactly one plan. |

## What ends it

- **The theorem is proved**, or refused, with the reason, which the next run starts from.
- **The [budget](/features/allowances).**
- **A refused account, or a model the backend will not run.** A turn that fails in a way a
  retry may fix is simply tried again.

## Picking it up

Run the same line with `--resume`, in the same repository. It reuses the run, the lemmas
already accepted, their worktrees and branches, the wiki, and the latest prose proof that was
turned down. See [Picking a run up](/user/resuming).

## See also

- [humanize1](/flows/humanize1): the phases it is built from
- [A flow that calls a flow](/weaver/calling-flows): how one flow runs another
