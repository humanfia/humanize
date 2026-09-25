---
pageClass: hmz-feature
---

# Capability map

Nineteen capability groups in five systems, grouped by the problem each solves rather than by
the code that solves it — a route to the right page rather than a contract. A group may combine
several implementations, a feature may serve more than one group, and availability still
depends on the backend, account, operating system, and shape of the run.

Choose an area, then follow **Learn** for the design, **Use** for the task, and **Reference**
for the interface and its limits.

<HmzMap />

## A. Flow system

The weaver's half: work expressed as async Python that declares what it drives, then composed,
scheduled, and recovered, with nothing a role did not declare within reach.

### A1. Expression and declaration

- A flow is an `async` function; its next step is whatever its body decides at runtime.
- It declares its agents and environments as typed roles, and its settings as a pydantic
  model; a role's type is `Agent` or `Env` with the capability mixins it asks for.
- What a flow is handed is a view of each real agent or machine, granted exactly what its role
  declared; anything else raises `CapabilityNotGranted`, whatever the harness could do.
- Each harness has a protocol of its own (`ClaudeCodeAgent`, `CodexAgent`, …) naming everything
  it serves, for a role that needs that harness and all of it.

| Harness | What it serves beyond `Agent` |
| --- | --- |
| `claude` | goal, loop, steering, permission requests, subagent start/stop, asking the user |
| `codex` | goal, steering, permission requests, subagent start/stop, asking the user |
| `cursor-agent` | subagent start/stop |
| `kimi` | goal, steering, permission requests, asking the user |
| `zcode` | goal, permission requests, asking the user |
| `grok` | nothing beyond `Agent` |
| `pi` | steering, asking the user |
| `dsh` | goal |
| `opencode`, `mimo`, `qwen`, `agy`, an ACP CLI | nothing beyond `Agent` |

**Learn:** [A flow is Python](/features/flows) · **Use:**
[Writing a flow](/weaver/writing-a-flow) · **Reference:**
[Flows](/reference/flows#asking-for-an-agent-that-can-do-something)

### A2. Requirements and testing

- A run is checked against what the flow declares before any agent starts: every required
  role filled, each harness serving the role's mixins, each machine meeting its resources, the
  params valid, a budget given.
- A called flow is checked the same way at the call, before it runs, with a refusal of its
  own for each thing missing — a role, a capability, a permission, a resource, a harness.
- An in-memory fake kit — scripted agents, a dictionary of files for an environment, a
  stand-in person — runs a flow through the real engine with no model turn and no machine.

**Learn:** [A flow is Python](/features/flows) · **Use:**
[Testing flows](/weaver/testing-flows) · **Reference:**
[Flows](/reference/flows#testing-a-flow)

### A3. Composition and reload

- A flow may load another by ref — beside it, in the same flowverse, or at a git URL pinned to
  a commit — and call it with agents and environments it holds, narrowed to what the callee
  declares.
- A callee's budget is the tighter of its own and what remains of its caller's; what it
  spends rolls up to every flow above it; what it raises reaches the caller unwrapped.
- Remote skill repositories are fetched and cached for the role that names them.
- A flow's module is imported once per run and afresh by the next run once its files change.

**Learn:** [A flow is Python](/features/flows) · **Use:**
[Calling flows](/weaver/calling-flows), [Skills](/user/skills) · **Reference:**
[Flows](/reference/flows#a-flow-that-calls-another-flow)

### A4. Scheduling, state, and resumption

- Flows declare agent roles, capabilities, the environments they work in, and what each agent
  is allowed — a `Permission` over its workdir, the user's home, the machine and the network —
  rather than backend implementations. Whoever runs the flow names a CLI, an account, a model
  and an effort per role, and a machine and directory per environment role.
- Independent sessions may run concurrently; turns sharing one session remain sequential.
- A resumable flow keeps an explicit state mapping in the run's journal and resumes by running
  current flow code again; its calls pick up where they are called again with the same task,
  agents, environments and params.
- Nothing restores a backend conversation; repositories and explicit flow state carry the work
  forward.

**Learn:** [Many turns at once](/features/concurrency),
[Picked up where it stopped](/features/resuming) · **Use:**
[Async flows](/weaver/async-flows), [Picking a run up](/user/resuming) · **Reference:**
[Flows](/reference/flows#a-flow-that-can-be-picked-up)

## B. Agent control plane

Drive different coding agents through one orchestration model while preserving their real
capabilities, identities, conversations, and ways of collaborating with a person.

### B1. Backend unification

- Agent and session contracts normalize turns, events, answers, and lifecycle operations.
- App servers, streaming command-line adapters, and Agent Client Protocol (ACP) servers keep
  their own transport semantics behind that contract.
- A capability matrix says what each backend can do, so a flow can reject an incompatible one.
- Models are usually discovered for the account that will run them — from the endpoint that
  account points its backend at where it names one, and from the backend itself where it does
  not; a backend that can do neither starts from a small advisory catalogue.
- Shaped answers are reconstructed into the same typed result where a backend supports them.

**Learn:** [Many backends, one agent](/features/backends),
[Answers in a shape](/features/shapes) · **Use:** [Providers](/user/providers),
[Efforts](/user/efforts) · **Reference:**
[Agents](/reference/agents#what-each-backend-can-do)

### B2. Turn and session control

- Per-turn controls, lifecycle hooks, and typed failures give flows explicit decision points.
- Steering delivers an acknowledged instruction into a supported turn that is already running.
- A per-turn budget of output tokens or wall-clock seconds is held to off the live meter, and
  cuts the running turn off where its cut-off setting says.
- A run's budget of duration, cost and output tokens — required of every `hmz exec` but
  `chat` — is held to at every turn of every backend; a called flow runs under the tighter of
  its own and what remains of its caller's, and a spent budget stays spent.
- The same interrupt primitive ends a turn by hand, reaching whichever process is holding it.
- Goals continue across controlled turns, while forking creates a separate conversation
  branch, into another environment where the harness can.
- Side questions through /btw read a frozen conversation snapshot without changing the main
  session.
- Agent questions and the outworlder — the person outside the run, driven as an agent — share
  one answer path; away, it answers with defaults rather than blocking the run.

**Learn:** [A line typed mid-turn](/features/steering),
[A turn can be cut off](/features/budgets),
[Every run has a budget](/features/allowances),
[It decides when it is done](/features/goals), [The moments of a turn](/features/hooks),
[You, as one of the agents](/features/human) · **Use:** [Questions](/user/questions),
[Side questions (/btw)](/user/btw), [Human agent](/weaver/human-agent),
[Being away](/user/afk) · **Reference:**
[Agents](/reference/agents#turns), [Flows](/reference/flows#the-person-at-the-prompt)

### B3. Skills and hooks

- Each session receives the skills its role declares, found in the flow's own `skills/` or
  fetched, and an agent derived with fewer carries fewer. Which skills exist at all is the flow
  author's; nobody running the flow adjusts one.
- Backends expose the native skills already installed where their own CLI reads them, as a
  reading: humanize never rewrites, overrides or disables one.
- Hooks put the flow's own code on the moments of a turn — a prompt, a tool, a permission, a
  question, a turn ending — one method per moment, and only on a role declared for the moments
  some harnesses alone reach.

**Learn:** [The moments of a turn](/features/hooks) · **Use:**
[Skills](/user/skills), [Hooks](/weaver/hooks),
[The agent asking the flow](/weaver/tools) · **Reference:**
[Agents](/reference/agents#the-skills-an-agent-carries),
[Flows](/reference/flows#the-skills-a-flow-brings)

### B4. Failure recovery

- Backends distinguish failures worth another attempt from explicitly unrecoverable ones;
  configured policy then retries, walks accounts, and finally walks places.
- Retries and waits are policy for a place, not an automatic response to every failure.
- An account chain stays inside one backend and may continue the same backend conversation.
- Cross-backend fallback opens a new session carrying compatible agent settings and the pending
  turn, but not the earlier conversation.
- Recovery stops on loops, missing destinations, unsupported capabilities, and failures another
  attempt cannot fix.

**Learn:** [Two accounts of one CLI](/features/accounts) · **Use:**
[Falling back](/user/fallback) · **Reference:**
[Account recovery](/reference/agents#when-an-account-goes-down),
[Cross-backend recovery](/reference/agents#when-the-place-has-nowhere-left-to-run)

### B5. Accounts and credentials

- Where a CLI has a native login, capture lets it create and refresh credentials in its own
  format; other backends take their configured credential inputs.
- Credential paths and environment variables are redirected for the account taking a turn,
  without changing the agent's own command.
- Ambient credential variables are removed so the shell cannot silently select another account.
- Compatible vendor credentials can be reused across CLI backends under each backend's
  spelling.
- Concurrent accounts keep private files, and stored account state updates atomically.
- The machine's own login may start an account chain, but humanize does not own or copy it.

**Learn:** [Two accounts of one CLI](/features/accounts) · **Use:**
[Providers](/user/providers) · **Reference:** [Providers](/reference/providers)

## C. Execution fabric

Let a local coding agent operate another machine while keeping process behavior, workspace
movement, transport, and machine ownership explicit.

### C1. Transparent remote execution

- The agent stays local while a supervisor decides selected system calls and replays them on
  the target one at a time.
- Program launches, descendants, network access, paths, and executables follow explicit routes.
- Control files and backend state that should stay local are kept there.
- Remote results preserve target errors, exit status, and common signals; rarer or repeated
  signals have documented limits.
- The anchor is routing and transport, not a sandbox or an authorization boundary.

**Learn:** [The anchor](/features/anchor) · **Use:**
[Remote execution](/user/remote-execution), [Security](/user/security) · **Reference:**
[Remote execution](/reference/remote-execution)

### C2. Shadow workspace and consistent writes

- A sparse local shadow presents the target workspace before every file has crossed the wire.
- Missing files and virtual exports are materialized when the agent actually reaches them.
- Writes stream to the target and become visible atomically when the complete file arrives.

**Learn:** [The anchor](/features/anchor) · **Use:**
[Remote execution](/user/remote-execution) · **Reference:**
[What the agent observes](/reference/remote-execution#what-the-agent-observes)

### C3. Portable transport runtime

- A compact target runtime — sent rather than installed — carries process, file, environment,
  and working-directory operations.
- One multiplexed connection can keep independent requests and streamed results in flight.
- Targets may use different transports while preserving the same remote-execution semantics.
- Local and target environments are composed deliberately rather than replacing each other.
- Each remote command uses the target-resolved counterpart of the tracee's current working
  directory.

**Learn:** [The anchor](/features/anchor) · **Use:**
[Remote execution](/user/remote-execution) · **Reference:**
[Targets](/reference/remote-execution#targets)

### C4. Machine lifecycle

- An agent may receive a dedicated container whose lifetime follows it, or a run may share one
  container when the participants need the same environment.
- Existing remote targets remain externally owned; managed targets are closed by the scope that
  created them.
- Where a flow's work lands is an environment role, declared separately from which backend
  performs the turn: the directory the run was started in, or one `-e` points at on this
  machine or an ssh host.

**Learn:** [The anchor](/features/anchor) · **Use:** [Containers](/user/containers) ·
**Reference:** [Machines](/reference/machines)

## D. Run continuity and observability

Keep long work reachable, leave a readable record after failure, reconstruct its timeline, and
separate local traces from optional outbound reporting.

### D1. Detached operation

- One workspace daemon owns the interface pseudoterminal (PTY) and survives terminal or SSH
  loss; terminals attach as readers.
- A new terminal receives a redraw of the live screen rather than a promised full transcript.
- Slow readers have independent buffers and cannot stall the run or other attached terminals.
- Detaching, cooperative stopping, and forced stopping remain distinct operations.
- Detachment does not survive host or daemon loss; persisted state supports a later run rather
  than resurrecting the old process.

**Learn:** [The terminal can leave](/features/daemon) · **Use:**
[Unattended runs](/user/unattended), [Stopping](/user/stopping) · **Reference:**
[Daemon](/reference/daemon)

### D2. Persistent state and layered logs

- Each run's epic record gains complete journal entries as events happen.
- A resumable run's journal records every flow call, its state writes, its sessions and its
  temporary directories; a state write is flushed as it is made.
- Called flows keep their own state against their own call without overwriting their caller.
- These records are workflow state, not the backend conversation or a terminal transcript.

**Learn:** [Picked up where it stopped](/features/resuming),
[The terminal can leave](/features/daemon) · **Use:**
[Picking a run up](/user/resuming), [History](/user/history) · **Reference:**
[Resumable flows](/reference/flows#a-flow-that-can-be-picked-up),
[Epic records](/reference/tracing#epics)

### D3. Trace reconstruction

- Backend session logs and profiled processes are combined onto one timeline without copying
  their source records.
- Process clocks are calibrated so agent events and operating-system activity can be compared.
- Epic records bound collection to the sessions opened by the run being inspected.
- Subagent relationships become explicit topology rather than anonymous extra sessions.
- Dense lane packing and lazy attachments keep large traces navigable without dropping detail.

**Learn:** [One timeline](/features/tracing) · **Use:** [Tracing](/user/tracing) ·
**Reference:** [Tracing](/reference/tracing)

### D4. Telemetry privacy

- Consent may be unanswered, enabled, or disabled; an unanswered machine sends nothing.
- Data suppliers run only while a report is assembled, and provide names, counts, and
  configuration rather than prompts, transcripts, tool output, or file content.
- Final filters strip command lines, credentials, external paths, frame context, and logging
  breadcrumbs before a report is sent.
- Run journals, session logs, profiles, and traces are local artifacts; creating or opening one
  does not opt into outbound reporting.

**Learn:** [One timeline](/features/tracing) · **Use:** [Reporting](/user/reporting),
[Tracing](/user/tracing) · **Reference:** [SDK](/reference/sdk),
[Tracing](/reference/tracing)

## E. Product surfaces

Discover, own, configure, and start the same flows through interfaces suited to interactive,
scripted, embedded, or detached work.

### E1. Discovery, forking, and configuration

- Fetched, project, and user flows sit in an explicit catalogue: qualified names
  select a source directly, unqualified names prefer the nearest local version.
- Forking stages a complete copy and refuses to overwrite an existing local flow.
- A flow's `FlowParams` model drives `-p`, setup fields, validation, defaults, and grouped
  presentation.
- Remembered roles, environments, params and budget are revalidated against what the flow
  declares now.

**Learn:** [One system, four ways in](/features/surfaces) · **Use:**
[Flowverses](/weaver/flowverses), [Flow params](/weaver/flow-settings) · **Reference:**
[Flows](/reference/flows#flowverses)

### E2. Unified entry points

- The SDK, command line, and terminal interface share workspace stores, flow loading,
  validation, and the runner where their work overlaps.
- The daemon holds the terminal interface without interpreting flows or becoming another
  engine.
- Each surface keeps its purpose: composable SDK, scriptable command line, conversational
  interface, and detached terminal continuity.
- Every user-facing run is written as an epic record, whatever surface started it.
- Shared semantics do not imply identical interaction or backend capability on every surface.

**Learn:** [One system, four ways in](/features/surfaces) · **Use:**
[Run a flow](/#run-a-flow), [Monitor](/user/monitor) · **Reference:**
[SDK](/reference/sdk), [CLI](/reference/cli), [TUI](/reference/tui),
[Daemon](/reference/daemon)
