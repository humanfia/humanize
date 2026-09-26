---
pageClass: hmz-feature
---

# recursive_lean_prover

A theorem proved in Lean by recursive decomposition: each node is planned, proved in prose,
split into child theorems where it has to be, and formalized in a git worktree of its own —
every accepted theorem written to a Markdown wiki as it lands. It is built out of
[`humanize1`](/flows/humanize1)'s phases, called in the same process.

```sh
hmz exec -f recursive_lean_prover \
    -a worker=codex/gpt-5.6-sol:max -a reviewer=codex/gpt-5.6-sol:max \
    -p lean_target=Submission.lean -p 'comparator_command=bash tools/check-with-comparator.sh' \
    -b duration=72h "$(cat PROBLEM.md)"
```

Run it at the root of a clean Lean git repository that ignores `.humanize/`, with a comparator
wrapper that exits zero and prints `comparator_success` only when every check has passed.

## Two roles

| | |
| --- | --- |
| `worker` | Writes each plan, proof and Lean formalization; declared with `PermissionRequestHookAgentMixin`, since `humanize1:rlcr`'s guards work through its permission requests — so Claude Code, Codex, Kimi Code or ZCode |
| `reviewer` | Checks each proof and each candidate afresh, and reruns the comparator itself |

Both declare `Permission(local=ALL, user=ALL, system=READ, online=ALL)` and carry the flow's
skill, `recursive-lean-proof`. Every turn is a fresh session. There is no `human` role.

## Each node

1. **One scaffold plan**, from `humanize1:gen-plan` in `direct` mode, handed `planner=worker`
   and `analyst=reviewer`, and never regenerated.
2. **A proof in prose**, revised from the reviewer's first invalid step, in batches of
   `natural_proof_attempts`.
3. **A decomposition**, where the node needs one: child theorems with exact Lean statements and
   an acyclic dependency list, each child going through the same steps — up to `max_depth` deep,
   `max_children` apiece, `max_nodes` in all.
4. **Formalization in a worktree of its own**: every ready node gets a named branch and a
   `derive_worktree` checkout under a scratch directory of the workspace, and runs
   `humanize1:rlcr` through the hidden `worktree-rlcr` subflow with that worktree as its
   workspace, for up to `rlcr_rounds` rounds. Up to `max_parallel_children` nodes work at once.
5. **Acceptance**: the comparator, then a fresh reviewer that reruns it. An accepted theorem is
   published to the wiki and unlocks what depends on it.

## What it takes

Every param has a default: `max_depth` `2`, `max_children` `4`, `max_parallel_children` `24`,
`max_nodes` `24`, `natural_proof_attempts` `3`, `decomposition_attempts` `2`, `rlcr_rounds`
`20`, `plan_turn_timeout` `3600` and `plan_total_timeout` `14400` seconds, `comparator_timeout`
`21600` seconds, `lean_target` blank for the worker to infer, `comparator_command`
`bash tools/check-with-comparator.sh`, `comparator_success` `Your solution is okay!`,
`artifact_dir` `.humanize/recursive-lean-prover`, `wiki_dir` `.humanize/math-wiki`, and
`stop_on_child_failure` `true`.

## What ends it

The root theorem proved, or not accepted — said, with why, and kept for the next run — or the
run's [budget](/features/allowances) spent. A refused credential or a model that is not served
stops it too. It can be picked up with `--resume`, in the same repository: the run, its accepted
nodes, their worktrees and branches, the wiki and the latest rejected draft are all reused.

## See also

- [humanize1](/flows/humanize1) — the phases it is built from
- [A flow that calls a flow](/weaver/calling-flows)
- [Worktrees](/weaver/worktrees) — what `derive_worktree` makes
