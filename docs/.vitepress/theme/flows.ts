// Every flow in the catalogue, and the scene each one's diagram plays, in one place.
//
// Three things are written down here: how the catalogue is sorted (KINDS), what a flow *is* --
// its name, the roles `-a` fills, what ends it, what `--resume` carries -- which <HmzFlows>
// draws as the catalogue on /flows/ and the sidebar lists, and what a run of it *looks like*,
// as a scene <HmzFlow> plays on each flow's page. Keeping all three here means the catalogue,
// the sidebar and the diagrams cannot disagree.
//
// Everything is read off the flows themselves: `src/hmz/flows/builtin/` for `chat` and the six
// loops beside it, and for the rest the repository each is released from, as the official
// flowverse (https://github.com/humanfia/flowverse) lists it. The visual grammar every scene is
// drawn in is `components/flow/grammar.ts`, and `/flows/` shows it as a legend.
//
// This file is imported by `config.mts` as well as by the theme, so it imports nothing.

/* ------------------------------------------------------------------------------------------
   How the catalogue is sorted: by how the agents in a flow work together.
   ------------------------------------------------------------------------------------------ */

export type Kind = 'talk' | 'solo' | 'relay' | 'tidy' | 'checked' | 'lanes' | 'split'

export interface KindInfo {
  id: Kind
  /** The heading, on /flows/ and in the sidebar. */
  said: string
  /** One line: the pattern every flow under it shares. */
  how: string
}

export const KINDS: KindInfo[] = [
  { id: 'talk', said: 'Talk', how: 'You and one agent, turn for turn.' },
  { id: 'solo', said: 'One agent, looping', how: 'One agent takes round after round on the same task.' },
  { id: 'relay', said: 'A relay', how: 'Two agents hand the same tree back and forth.' },
  {
    id: 'tidy',
    said: 'A loop with a cleaner',
    how: 'A loop, and a cleaner that distills the tree into one commit every few turns.',
  },
  {
    id: 'checked',
    said: 'Maker and checker',
    how: 'One agent makes, and a fresh one, which never saw it made, judges it.',
  },
  { id: 'lanes', said: 'Lanes at once', how: 'Several workspaces, each with agents of its own, at the same time.' },
  { id: 'split', said: 'Divide and conquer', how: 'The task splits into parts, and each part runs the same line.' },
]

/* ------------------------------------------------------------------------------------------
   What a reader may be trying to get done, which is what the chooser on /flows/ asks.
   ------------------------------------------------------------------------------------------ */

export type Job = 'talk' | 'grind' | 'review' | 'pair' | 'plan' | 'parallel' | 'lean' | 'write'

export interface JobInfo {
  id: Job
  /** The chip. */
  said: string
  /** The advice shown once it is picked. Inline `code` is written with backticks. */
  hint: string
}

export const JOBS: JobInfo[] = [
  {
    id: 'talk',
    said: 'talk to an agent',
    hint: '`chat` is what `hmz` opens on in a new project: type, and the agent answers. No loop, and no budget needed.',
  },
  {
    id: 'grind',
    said: 'leave one agent on a task',
    hint: 'Start with `ralph_loop`: a fresh session every round runs for days without drowning in its own context. `stateful_ralph` and `continue_loop` keep one session, so the agent remembers what it tried. `goal` lets the model decide when it is done.',
  },
  {
    id: 'review',
    said: 'have the work reviewed',
    hint: '`rlar` puts a fresh reviewer after every round, and stops when the reviewer says the task is done. `humanize1` agrees on a plan first, then builds it under review.',
  },
  {
    id: 'pair',
    said: 'put two models on one task',
    hint: '`flame_chase` hands the tree back and forth between two agents. `rlar` makes the second one a reviewer instead.',
  },
  {
    id: 'plan',
    said: 'plan before building',
    hint: '`humanize1` is three flows, run one after another: an idea, a plan both sides agreed on, and a build under review.',
  },
  {
    id: 'parallel',
    said: 'chase several leads at once',
    hint: 'Seven agents in three lanes. In `parallel_flame_chase` one lane writes your tree and two work on copies; in `parallel_flame_chase:git_pr` every lane has a clone and main moves only for a measured improvement.',
  },
  {
    id: 'lean',
    said: 'prove a Lean theorem',
    hint: '`recursive_lean_prover` splits the theorem into lemmas and proves each one in a worktree of its own.',
  },
  {
    id: 'write',
    said: 'write a new flow',
    hint: '`aot` writes a flow from a description, and lands it only after it loads, runs on fakes and passes a review.',
  },
]

/* ------------------------------------------------------------------------------------------
   The flows.
   ------------------------------------------------------------------------------------------ */

export interface Flow {
  /** The name the catalogue lists it under. For every flow but `humanize1` it is also what
   *  `-f` and `$` take; `humanize1` holds three flows, each run as `humanize1:<phase>`. */
  name: string
  /** The flows a module of several holds, each run as `<name>:<phase>`. */
  phases?: string[]
  /** The page under /flows/. Every flow has one of its own. */
  link: string
  /** The roles `-a` fills, as it names them. */
  roles: string
  /** One line: what it does. */
  said: string
  /** What ends it, besides the run's budget. */
  ends: string
  /** What a run picked up with `--resume` carries in, or "" for one that always starts afresh. */
  keeps: string
  jobs: Job[]
  kind: Kind
  /** The scene its card draws, by its key in SCENES. */
  scene: string
}

export const FLOWS: Flow[] = [
  {
    name: 'chat',
    link: '/flows/chat',
    roles: 'assistant',
    said: 'One agent, one conversation: every line you type back is its next turn.',
    ends: 'you send nothing back, so under hmz exec after one turn',
    keeps: '',
    jobs: ['talk'],
    kind: 'talk',
    scene: 'chat',
  },
  {
    name: 'ralph_loop',
    link: '/flows/ralph-loop',
    roles: 'agent',
    said: 'The task again every round, in a fresh session, so only the repository carries over.',
    ends: '3 rounds in a row that answer nothing',
    keeps: 'the round count',
    jobs: ['grind'],
    kind: 'solo',
    scene: 'ralph_loop',
  },
  {
    name: 'stateful_ralph',
    link: '/flows/stateful-ralph',
    roles: 'agent',
    said: 'The task again every round, in one session that remembers every round before.',
    ends: '3 rounds in a row that answer nothing',
    keeps: 'the round count, not the session',
    jobs: ['grind'],
    kind: 'solo',
    scene: 'stateful_ralph',
  },
  {
    name: 'continue_loop',
    link: '/flows/continue-loop',
    roles: 'agent',
    said: 'The task once, then “continue” to the same session, round after round.',
    ends: '3 failed turns in a row',
    keeps: 'the round count, not the session',
    jobs: ['grind'],
    kind: 'solo',
    scene: 'continue_loop',
  },
  {
    name: 'goal',
    link: '/flows/goal',
    roles: 'worker',
    said: 'The task set as the agent’s own /goal: the model keeps going until it says the goal is met.',
    ends: 'the model says the goal is met',
    keeps: '',
    jobs: ['grind'],
    kind: 'solo',
    scene: 'goal',
  },
  {
    name: 'flame_chase',
    link: '/flows/flame-chase',
    roles: 'first_chaser · second_chaser',
    said: 'Two agents take turns on the same task, each in a fresh session, passing only the tree.',
    ends: '3 failed turns in a row',
    keeps: 'whose turn is next, and the round count',
    jobs: ['pair'],
    kind: 'relay',
    scene: 'flame_chase',
  },
  {
    name: 'agent_cleanup:ralph_loop',
    link: '/flows/ralph-loop-agent-cleanup',
    roles: 'agent · cleaner',
    said: 'ralph_loop, plus a cleaner that distills the tree into one commit every few turns.',
    ends: '3 turns in a row that come to nothing',
    keeps: 'the turn count and the epochs',
    jobs: ['grind'],
    kind: 'tidy',
    scene: 'ralph_loop_agent_cleanup',
  },
  {
    name: 'agent_cleanup:flame_chase',
    link: '/flows/flame-chase-agent-cleanup',
    roles: 'first_chaser · second_chaser · cleaner',
    said: 'flame_chase, with the same cleaner working between the two chasers.',
    ends: '3 turns in a row that come to nothing',
    keeps: 'the turn count and the epochs',
    jobs: ['pair'],
    kind: 'tidy',
    scene: 'flame_chase_agent_cleanup',
  },
  {
    name: 'rlar',
    link: '/flows/rlar',
    roles: 'actor · reviewer',
    said: 'An actor works in one session; a fresh reviewer reads the work and writes its next prompt.',
    ends: 'the reviewer says the task is done',
    keeps: 'the last review, and the round count',
    jobs: ['review', 'pair'],
    kind: 'checked',
    scene: 'rlar',
  },
  {
    name: 'humanize1',
    phases: ['gen-idea', 'gen-plan', 'rlcr'],
    link: '/flows/humanize1',
    roles: 'drafter · planner, analyst · builder, reviewer',
    said: 'PolyArch/humanize as three flows: an idea, a plan both sides agreed on, and a build under review.',
    ends: 'each phase on its own; rlcr when the reviewer finds nothing left, or after max rounds',
    keeps: 'rlcr only: its loop and round',
    jobs: ['review', 'plan'],
    kind: 'checked',
    scene: 'humanize1-rlcr',
  },
  {
    name: 'aot',
    link: '/flows/aot',
    roles: 'writer · critic',
    said: 'Writes a flow from your description, and lands it once it loads, runs on fakes and passes a critic.',
    ends: 'the flow lands, or the repairs run out',
    keeps: '',
    jobs: ['write'],
    kind: 'checked',
    scene: 'aot',
  },
  {
    name: 'parallel_flame_chase',
    link: '/flows/parallel-flame-chase',
    roles: 'coordinator · six lane actors',
    said: 'A coordinator plans three lanes once; lane 1 writes your tree, lanes 2 and 3 work on copies.',
    ends: 'nothing but the budget, or you',
    keeps: 'the plan, the copies, the reports, whose turn each lane is on',
    jobs: ['parallel'],
    kind: 'lanes',
    scene: 'parallel_flame_chase',
  },
  {
    name: 'parallel_flame_chase:git_pr',
    link: '/flows/parallel-flame-chase-git-pr',
    roles: 'orchestrator · six lane actors',
    said: 'Three lanes, each with a clone and pull requests; main moves only for a measured improvement.',
    ends: 'nothing but the budget, or you',
    keeps: 'the central repository, the receipts, the reports',
    jobs: ['parallel'],
    kind: 'lanes',
    scene: 'parallel_flame_chase_git_pr',
  },
  {
    name: 'recursive_lean_prover',
    link: '/flows/recursive-lean-prover',
    roles: 'worker · reviewer',
    said: 'A Lean theorem, split into lemmas that are each planned, proved and formalized in a worktree of their own.',
    ends: 'the root theorem is proved, or refused',
    keeps: 'the lemmas proved so far, their branches and the wiki',
    jobs: ['lean'],
    kind: 'split',
    scene: 'recursive_lean_prover',
  },
]

/* ------------------------------------------------------------------------------------------
   The scenes. What one run of a flow looks like, played left to right by <HmzFlow>.

   A scene is read off the flow, never invented for the picture: every role is one the flow
   drives, every turn one it takes, and `session` says whether the flow opened a session for
   that turn (`new`), sent another turn to one it already had (`held`), or took no turn of a
   model at all (`none`: you, or a program). That distinction is most of what separates these
   flows from each other, so it is what the grammar draws most plainly.
   ------------------------------------------------------------------------------------------ */

/** What a role is, which is what colour and shape it is drawn in. A `maker` does the work and
 *  a `partner` is a second one taking turns with it; a `checker` reads and judges; a `steward`
 *  shapes the work -- plans the lanes, cleans the tree -- without doing or judging it. `human`
 *  is you, and `program` is humanize or your script: a step with no model in it. */
export type RoleKind = 'maker' | 'partner' | 'checker' | 'steward' | 'human' | 'program'

/** What a turn does, drawn as the glyph in its box. */
export type Does = 'work' | 'read' | 'plan' | 'ask' | 'run'

/** What ends a run: the flow's own success, the flow giving up, the budget, or you. */
export type Outcome = 'done' | 'fail' | 'budget' | 'you'

export interface Env {
  id: string
  /** Where the roles on it work, as the plate under them says it. */
  name: string
  /** Which layer of a `depth: 'lanes'` scene it is: plates with an index here are the lanes
   *  that run at once, and the camera fans them out in depth while they do. */
  stack?: number
}

export interface Role {
  id: string
  name: string
  note: string
  kind: RoleKind
  /** The workspace it works in, by id in `envs`. */
  env?: string
}

export interface Pass {
  /** A turn's id, or `end` for the finish. */
  to: string
  said: string
  /** How it gets there: as words in the next turn's prompt, or as files left in the tree. */
  via: 'text' | 'tree'
}

export interface Turn {
  id: string
  role: string
  /** When it starts, in beats. Two turns at the same beat happen at once. */
  at: number
  /** How many beats it takes. Default 1. */
  span?: number
  label: string
  session: 'new' | 'held' | 'none'
  /** Default: `work` for an agent, `ask` for you, `run` for a program. */
  does?: Does
  /** Turns of the model inside this one turn of the flow -- what a goal is. */
  inside?: number
  /** The flow this turn runs as a subflow. */
  calls?: string
  pass?: Pass[]
}

export interface Scene {
  /** The flow it is of, as `-f` takes it. */
  of: string
  roles: Role[]
  envs?: Env[]
  turns: Turn[]
  /** The arc back: what a round ends on, what it starts again at, and why. */
  loop?: { from: string; to: string; said: string }
  /** Every way a run of it ends. The first is the one this diagram plays to. */
  ends: { is: Outcome; said: string }[]
  /** Whether a budget stops it. Every flow but `chat` has one. Default true. */
  budget?: boolean
  /** Three-dimensional staging, where depth says something flat cannot: lanes that run at
   *  once fan out as layers, and a part that splits sends copies of itself down a level. */
  depth?: 'lanes'
  split?: { at: string; into: number; said: string }
  /** How wide a beat is drawn, for a scene with many of them. Default 150. */
  beat?: number
  /** One line under the whole thing. */
  caption: string
}

const tree = (said: string, to: string): Pass[] => [{ to, said, via: 'tree' }]
const text = (said: string, to: string): Pass[] => [{ to, said, via: 'text' }]
const BUDGET = { is: 'budget' as const, said: 'the budget runs out' }

export const SCENES: Record<string, Scene> = {
  chat: {
    of: 'chat',
    budget: false,
    envs: [{ id: 'dir', name: 'the directory you started in' }],
    roles: [
      { id: 'you', name: 'you', note: 'at the prompt', kind: 'human' },
      { id: 'agent', name: 'assistant', note: 'one session throughout', kind: 'maker', env: 'dir' },
    ],
    turns: [
      { id: 'y0', role: 'you', at: 0, label: 'what you typed first', session: 'none', pass: text('the turn', 'a0') },
      { id: 'a0', role: 'agent', at: 1, label: 'answers', session: 'new', pass: text('its answer', 'y1') },
      { id: 'y1', role: 'you', at: 2, label: 'what you type back', session: 'none', pass: text('the next turn', 'a1') },
      { id: 'a1', role: 'agent', at: 3, label: 'answers, remembering', session: 'held', pass: text('its answer', 'y2') },
      { id: 'y2', role: 'you', at: 4, label: 'nothing sent back', session: 'none', pass: text('', 'end') },
    ],
    loop: { from: 'a1', to: 'y1', said: 'for as long as you answer' },
    ends: [{ is: 'you', said: 'you send nothing back' }],
    caption:
      'Each answer comes to you, and what you type back is the next turn of the same session. Send nothing back — or run it under hmz exec, where nobody is at the prompt — and the run ends.',
  },

  ralph_loop: {
    of: 'ralph_loop',
    envs: [{ id: 'repo', name: 'your repository' }],
    roles: [{ id: 'agent', name: 'agent', note: 'a new session a round', kind: 'maker', env: 'repo' }],
    turns: [
      { id: 'r1', role: 'agent', at: 0, label: 'the task', session: 'new', pass: tree('the repository', 'r2') },
      { id: 'r2', role: 'agent', at: 1, label: 'the task', session: 'new', pass: tree('the repository', 'r3') },
      { id: 'r3', role: 'agent', at: 2, label: 'the task', session: 'new', pass: tree('the repository', 'r4') },
      { id: 'r4', role: 'agent', at: 3, label: 'the task', session: 'new' },
    ],
    loop: { from: 'r4', to: 'r1', said: 'nothing carries over but the repository' },
    ends: [BUDGET, { is: 'fail', said: '3 rounds in a row answer nothing' }],
    caption:
      'Every round starts from the task and from whatever the round before it left in the working directory — never from what it said.',
  },

  stateful_ralph: {
    of: 'stateful_ralph',
    envs: [{ id: 'repo', name: 'your repository' }],
    roles: [{ id: 'agent', name: 'agent', note: 'one session, longer', kind: 'maker', env: 'repo' }],
    turns: [
      { id: 's1', role: 'agent', at: 0, label: 'the task', session: 'new' },
      { id: 's2', role: 'agent', at: 1, label: 'the task, again', session: 'held' },
      { id: 's3', role: 'agent', at: 2, label: 'the task, again', session: 'held' },
      { id: 's4', role: 'agent', at: 3, label: 'the task, again', session: 'held' },
    ],
    loop: { from: 's4', to: 's2', said: 'the same conversation, one round longer' },
    ends: [BUDGET, { is: 'fail', said: '3 rounds in a row answer nothing' }],
    caption:
      'One session is one conversation, so its context grows with every round — the thread thickens — and that is the other limit a long run of this reaches.',
  },

  continue_loop: {
    of: 'continue_loop',
    envs: [{ id: 'repo', name: 'your repository' }],
    roles: [{ id: 'agent', name: 'agent', note: 'one session, nudged', kind: 'maker', env: 'repo' }],
    turns: [
      { id: 'c1', role: 'agent', at: 0, label: 'the task', session: 'new' },
      { id: 'c2', role: 'agent', at: 1, label: '“continue”', session: 'held' },
      { id: 'c3', role: 'agent', at: 2, label: '“continue”', session: 'held' },
      { id: 'c4', role: 'agent', at: 3, label: '“continue”', session: 'held' },
    ],
    loop: { from: 'c4', to: 'c2', said: 'until the budget is spent' },
    ends: [BUDGET, { is: 'fail', said: '3 failed turns in a row' }],
    caption:
      'Until a turn answers, the task is sent again rather than “continue”: the word means something only to a session that heard the task.',
  },

  goal: {
    of: 'goal',
    envs: [{ id: 'repo', name: 'your repository' }],
    roles: [{ id: 'agent', name: 'worker', note: 'one session, under a goal', kind: 'maker', env: 'repo' }],
    turns: [
      {
        id: 'g1',
        role: 'agent',
        at: 0,
        span: 4,
        label: '/goal <task>',
        session: 'new',
        inside: 7,
        pass: text('the goal is met', 'end'),
      },
    ],
    ends: [{ is: 'done', said: 'the model says the goal is met' }, BUDGET],
    caption:
      'One turn of the flow. The ticks inside it are turns the backend started itself: a turn that would have ended starts another, until the model says the goal is met.',
  },

  flame_chase: {
    of: 'flame_chase',
    envs: [{ id: 'repo', name: 'your repository, shared' }],
    roles: [
      { id: 'one', name: 'first_chaser', note: 'a new session a turn', kind: 'maker', env: 'repo' },
      { id: 'two', name: 'second_chaser', note: 'a new session a turn', kind: 'partner', env: 'repo' },
    ],
    turns: [
      { id: 'f1', role: 'one', at: 0, label: 'the task', session: 'new', pass: tree('what it left in the tree', 'f2') },
      { id: 'f2', role: 'two', at: 1, label: 'the task', session: 'new', pass: tree('what it left in the tree', 'f3') },
      { id: 'f3', role: 'one', at: 2, label: 'the task', session: 'new', pass: tree('what it left in the tree', 'f4') },
      { id: 'f4', role: 'two', at: 3, label: 'the task', session: 'new' },
    ],
    loop: { from: 'f4', to: 'f1', said: 'a round is a turn each' },
    ends: [BUDGET, { is: 'fail', said: '3 failed turns in a row' }],
    caption:
      'Neither is told what the other said. What passes between them is the working directory — and a failed turn passes to the other chaser too.',
  },

  ralph_loop_agent_cleanup: {
    of: 'agent_cleanup:ralph_loop',
    beat: 146,
    envs: [{ id: 'repo', name: 'your repository — its history rewritten every epoch' }],
    roles: [
      { id: 'agent', name: 'agent', note: 'a new session a turn', kind: 'maker', env: 'repo' },
      { id: 'cleaner', name: 'cleaner', note: 'a new session an epoch', kind: 'steward', env: 'repo' },
      { id: 'epoch', name: 'the epoch', note: 'humanize, no model', kind: 'program', env: 'repo' },
    ],
    turns: [
      { id: 't1', role: 'agent', at: 0, label: 'a turn', session: 'new', pass: tree('the tree', 't2') },
      { id: 't2', role: 'agent', at: 1, label: 'a turn', session: 'new', pass: tree('the tree', 't3') },
      { id: 't3', role: 'agent', at: 2, label: 'a turn', session: 'new', pass: tree('three turns of work', 'e1') },
      {
        id: 'e1',
        role: 'cleaner',
        at: 3,
        label: 'distills it, writes NEXT.md',
        session: 'new',
        does: 'plan',
        pass: tree('the distilled tree', 'm1'),
      },
      {
        id: 'm1',
        role: 'epoch',
        at: 4,
        label: 'measures, checks, one commit',
        session: 'none',
        pass: tree('work_paths and NEXT.md', 't4'),
      },
      { id: 't4', role: 'agent', at: 5, label: 'a turn', session: 'new' },
    ],
    loop: { from: 't4', to: 't2', said: 'an epoch every cleanup_turns turns' },
    ends: [BUDGET, { is: 'fail', said: '3 turns in a row come to nothing' }],
    caption:
      'Every few turns the cleaner keeps the work under work_paths, deletes what strayed and writes NEXT.md; humanize checks the result and the history becomes one commit. An empty or failed turn is taken again.',
  },

  flame_chase_agent_cleanup: {
    of: 'agent_cleanup:flame_chase',
    beat: 146,
    envs: [{ id: 'repo', name: 'your repository — its history rewritten every epoch' }],
    roles: [
      { id: 'one', name: 'first_chaser', note: 'a new session a turn', kind: 'maker', env: 'repo' },
      { id: 'two', name: 'second_chaser', note: 'a new session a turn', kind: 'partner', env: 'repo' },
      { id: 'cleaner', name: 'cleaner', note: 'a new session an epoch', kind: 'steward', env: 'repo' },
      { id: 'epoch', name: 'the epoch', note: 'humanize, no model', kind: 'program', env: 'repo' },
    ],
    turns: [
      { id: 'f1', role: 'one', at: 0, label: 'turn 1', session: 'new', pass: tree('the tree', 'f2') },
      { id: 'f2', role: 'two', at: 1, label: 'turn 2', session: 'new', pass: tree('the tree', 'f3') },
      { id: 'f3', role: 'one', at: 2, label: 'turn 3', session: 'new', pass: tree('three turns of work', 'e1') },
      {
        id: 'e1',
        role: 'cleaner',
        at: 3,
        label: 'distills the tree',
        session: 'new',
        does: 'plan',
        pass: tree('the distilled tree', 'm1'),
      },
      {
        id: 'm1',
        role: 'epoch',
        at: 4,
        label: 'checks, one commit',
        session: 'none',
        pass: tree('work_paths and NEXT.md', 'f4'),
      },
      { id: 'f4', role: 'two', at: 5, label: 'turn 4', session: 'new', pass: tree('the tree', 'f5') },
      { id: 'f5', role: 'one', at: 6, label: 'turn 5', session: 'new' },
    ],
    loop: { from: 'f5', to: 'f2', said: 'the seats keep alternating across epochs' },
    ends: [BUDGET, { is: 'fail', said: '3 turns in a row come to nothing' }],
    caption:
      'The chasers alternate straight across the cleaning, so after three turns the second chaser opens the next stretch. An empty or failed turn is taken again by the same chaser.',
  },

  rlar: {
    of: 'rlar',
    envs: [{ id: 'repo', name: 'your repository' }],
    roles: [
      { id: 'actor', name: 'actor', note: 'one session, remembers', kind: 'maker', env: 'repo' },
      { id: 'reviewer', name: 'reviewer', note: 'a new session a review', kind: 'checker', env: 'repo' },
    ],
    turns: [
      { id: 'a1', role: 'actor', at: 0, label: 'the task', session: 'new', pass: tree('a round of work', 'v1') },
      {
        id: 'v1',
        role: 'reviewer',
        at: 1,
        label: 'reviews the work',
        session: 'new',
        does: 'read',
        pass: text('done: false, and its notes', 'a2'),
      },
      { id: 'a2', role: 'actor', at: 2, label: 'the notes', session: 'held', pass: tree('a round of work', 'v2') },
      {
        id: 'v2',
        role: 'reviewer',
        at: 3,
        label: 'reviews the work',
        session: 'new',
        does: 'read',
        pass: text('done: true', 'end'),
      },
    ],
    loop: { from: 'v2', to: 'a2', said: 'while the review says there is more to do' },
    ends: [
      { is: 'done', said: 'the reviewer says done' },
      { is: 'fail', said: '3 failures in a row' },
      BUDGET,
    ],
    caption:
      'Every review answers two things: whether the task is done, and what the actor hears next.',
  },

  'humanize1-gen-idea': {
    of: 'humanize1:gen-idea',
    envs: [{ id: 'repo', name: 'your repository' }],
    roles: [{ id: 'drafter', name: 'drafter', note: 'one session', kind: 'maker', env: 'repo' }],
    turns: [
      {
        id: 'i1',
        role: 'drafter',
        at: 0,
        span: 3,
        label: 'explores n directions',
        session: 'new',
        does: 'plan',
        inside: 6,
        pass: tree('.hmz/ideas/<slug>.md', 'end'),
      },
    ],
    ends: [{ is: 'done', said: 'the draft is written' }, BUDGET],
    caption:
      'One turn, one file: a main direction and the rest as alternatives. The ticks are the directions, each explored by a read-only helper inside the drafter’s own turn.',
  },

  'humanize1-gen-plan': {
    of: 'humanize1:gen-plan',
    beat: 146,
    envs: [{ id: 'repo', name: 'your repository' }],
    roles: [
      { id: 'planner', name: 'planner', note: 'one session throughout', kind: 'maker', env: 'repo' },
      { id: 'analyst', name: 'analyst', note: 'a new session a reading', kind: 'checker', env: 'repo' },
    ],
    turns: [
      {
        id: 'n0',
        role: 'analyst',
        at: 0,
        label: 'is it about this repo?',
        session: 'new',
        does: 'read',
        pass: text('relevant', 'n1'),
      },
      {
        id: 'n1',
        role: 'analyst',
        at: 1,
        label: 'an analysis of its own',
        session: 'new',
        does: 'read',
        pass: text('the risks', 'p1'),
      },
      { id: 'p1', role: 'planner', at: 2, label: 'writes the plan', session: 'new', does: 'plan', pass: tree('docs/plan.md', 'n2') },
      {
        id: 'n2',
        role: 'analyst',
        at: 3,
        label: 'reviews the plan',
        session: 'new',
        does: 'read',
        pass: text('what it disagrees with', 'p2'),
      },
      { id: 'p2', role: 'planner', at: 4, label: 'revises it', session: 'held', does: 'plan', pass: text('agreed', 'p3') },
      { id: 'p3', role: 'planner', at: 5, label: 'consolidates', session: 'held', does: 'plan', pass: tree('docs/plan.md', 'end') },
    ],
    loop: { from: 'p2', to: 'n2', said: 'up to 3 rounds, until the two agree' },
    ends: [
      { is: 'done', said: 'the plan is written' },
      { is: 'fail', said: 'the draft is not about this repository' },
      BUDGET,
    ],
    caption:
      'The side that writes remembers and the side that reads does not — the rule all of humanize1 is built on.',
  },

  'humanize1-rlcr': {
    of: 'humanize1:rlcr',
    beat: 146,
    envs: [{ id: 'repo', name: 'your git repository' }],
    roles: [
      { id: 'you', name: 'you', note: 'asked only when you are there', kind: 'human' },
      { id: 'builder', name: 'builder', note: 'one session, the loop', kind: 'maker', env: 'repo' },
      { id: 'gates', name: 'the gates', note: 'humanize, no model', kind: 'program', env: 'repo' },
      { id: 'reviewer', name: 'reviewer', note: 'a new session a review', kind: 'checker', env: 'repo' },
    ],
    turns: [
      { id: 'q', role: 'you', at: 0, label: 'a quiz on the plan', session: 'none', pass: text('answered, or skipped', 'b1') },
      { id: 'b1', role: 'builder', at: 1, label: 'builds the plan', session: 'new', pass: tree('believes it is done', 'g1') },
      { id: 'g1', role: 'gates', at: 2, label: '15 stop checks', session: 'none', pass: text('passed', 'v1') },
      {
        id: 'v1',
        role: 'reviewer',
        at: 3,
        label: 'reviews the round',
        session: 'new',
        does: 'read',
        pass: text('[P0-9] findings', 'b2'),
      },
      { id: 'b2', role: 'builder', at: 4, label: 'the findings', session: 'held', pass: tree('believes it is done', 'g2') },
      { id: 'g2', role: 'gates', at: 5, label: '15 stop checks', session: 'none', pass: text('passed', 'v2') },
      {
        id: 'v2',
        role: 'reviewer',
        at: 6,
        label: 'COMPLETE, then a code review',
        session: 'new',
        does: 'read',
        pass: text('clean: a finalize round', 'end'),
      },
    ],
    loop: { from: 'v2', to: 'b2', said: 'a refused check or a finding is the builder’s next prompt' },
    ends: [
      { is: 'done', said: 'complete: nothing left, code review clean' },
      { is: 'fail', said: 'max rounds, or stop' },
      BUDGET,
    ],
    caption:
      'The builder works until it believes the whole plan is done; the round’s checks run, and what the reviewer finds is what the builder hears next, in the same session.',
  },

  aot: {
    of: 'aot',
    beat: 146,
    envs: [
      { id: 'scratch', name: 'a scratch directory' },
      { id: 'fakes', name: 'three fake worlds' },
    ],
    roles: [
      { id: 'writer', name: 'writer', note: 'one session throughout', kind: 'maker', env: 'scratch' },
      { id: 'critic', name: 'critic', note: 'a new session, reads only', kind: 'checker', env: 'scratch' },
      { id: 'gates', name: 'the gates', note: 'humanize, no model', kind: 'program', env: 'fakes' },
    ],
    turns: [
      { id: 'w1', role: 'writer', at: 0, label: 'draws up a spec', session: 'new', does: 'plan' },
      { id: 'w2', role: 'writer', at: 1, label: 'writes the flow', session: 'held', pass: tree('the draft', 'g1') },
      {
        id: 'g1',
        role: 'gates',
        at: 2,
        label: 'loads it, runs it on fakes',
        session: 'none',
        pass: text('it ends in every world', 'c1'),
      },
      {
        id: 'c1',
        role: 'critic',
        at: 3,
        label: 'reads it fresh',
        session: 'new',
        does: 'read',
        pass: text('refused, word for word', 'w3'),
      },
      { id: 'w3', role: 'writer', at: 4, label: 'repairs it', session: 'held', pass: tree('the draft', 'g2') },
      {
        id: 'g2',
        role: 'gates',
        at: 5,
        label: 'loads it, runs it on fakes',
        session: 'none',
        pass: text('it ends in every world', 'c2'),
      },
      {
        id: 'c2',
        role: 'critic',
        at: 6,
        label: 'reads it fresh',
        session: 'new',
        does: 'read',
        pass: text('approved: it lands', 'end'),
      },
    ],
    loop: { from: 'c2', to: 'w3', said: 'a refusal goes back word for word, up to repairs times' },
    ends: [
      { is: 'done', said: 'approved: the flow lands' },
      { is: 'fail', said: 'repairs run out, and you say no' },
      BUDGET,
    ],
    caption:
      'A draft lands only once humanize has loaded it, it has ended on its own in three fake worlds, and a critic that never saw it written approves it.',
  },

  parallel_flame_chase: {
    of: 'parallel_flame_chase',
    depth: 'lanes',
    envs: [
      { id: 'plan', name: 'a planning snapshot' },
      { id: 'l1', name: 'lane 1 · your tree', stack: 0 },
      { id: 'l2', name: 'lane 2 · a private copy', stack: 1 },
      { id: 'l3', name: 'lane 3 · a private copy', stack: 2 },
    ],
    roles: [
      { id: 'co', name: 'coordinator', note: 'plans once, then leaves', kind: 'steward', env: 'plan' },
      { id: 'l1a', name: 'lane_1_actor_a', note: 'the sole writer', kind: 'maker', env: 'l1' },
      { id: 'l1b', name: 'lane_1_actor_b', note: 'the sole writer', kind: 'partner', env: 'l1' },
      { id: 'l2a', name: 'lane_2_actor_a', note: 'on a copy', kind: 'maker', env: 'l2' },
      { id: 'l2b', name: 'lane_2_actor_b', note: 'on a copy', kind: 'partner', env: 'l2' },
      { id: 'l3a', name: 'lane_3_actor_a', note: 'on a copy', kind: 'maker', env: 'l3' },
      { id: 'l3b', name: 'lane_3_actor_b', note: 'on a copy', kind: 'partner', env: 'l3' },
    ],
    turns: [
      {
        id: 'c0',
        role: 'co',
        at: 0,
        label: 'plans three lanes',
        session: 'new',
        does: 'plan',
        pass: [
          { to: 'x1', said: 'lane 1', via: 'text' },
          { to: 'y1', said: 'lane 2', via: 'text' },
          { to: 'z1', said: 'lane 3', via: 'text' },
        ],
      },
      { id: 'x1', role: 'l1a', at: 1, label: 'a turn', session: 'new', pass: tree('the tree', 'x2') },
      { id: 'y1', role: 'l2a', at: 1, label: 'a turn', session: 'new', pass: tree('the copy', 'y2') },
      { id: 'z1', role: 'l3a', at: 1, label: 'a turn', session: 'new', pass: tree('the copy', 'z2') },
      { id: 'x2', role: 'l1b', at: 2, label: 'a turn', session: 'new', pass: tree('the tree', 'x3') },
      {
        id: 'y2',
        role: 'l2b',
        at: 2,
        label: 'a turn',
        session: 'new',
        pass: [
          { to: 'y3', said: 'the copy', via: 'tree' },
          { to: 'x3', said: 'a report and an artifact', via: 'text' },
        ],
      },
      { id: 'z2', role: 'l3b', at: 2, label: 'a turn', session: 'new', pass: tree('the copy', 'z3') },
      { id: 'x3', role: 'l1a', at: 3, label: 'a turn, and the report', session: 'new' },
      { id: 'y3', role: 'l2a', at: 3, label: 'a turn', session: 'new' },
      { id: 'z3', role: 'l3a', at: 3, label: 'a turn', session: 'new' },
    ],
    loop: { from: 'x3', to: 'x1', said: 'each lane alternates a and b, for as long as the run goes' },
    ends: [BUDGET, { is: 'you', said: 'you stop it' }],
    caption:
      'Three lanes at once, and only lane 1 writes your tree. What lanes 2 and 3 find reaches it as a report and an artifact, never as a write.',
  },

  parallel_flame_chase_git_pr: {
    of: 'parallel_flame_chase:git_pr',
    depth: 'lanes',
    beat: 150,
    envs: [
      { id: 'plan', name: 'a planning workspace' },
      { id: 'l1', name: 'lane 1 · a clone', stack: 0 },
      { id: 'l2', name: 'lane 2 · a clone', stack: 1 },
      { id: 'l3', name: 'lane 3 · a clone', stack: 2 },
      { id: 'main', name: 'the central repository' },
    ],
    roles: [
      { id: 'co', name: 'orchestrator', note: 'plans once', kind: 'steward', env: 'plan' },
      { id: 'l1a', name: 'lane_1_actor_a', note: 'in its clone', kind: 'maker', env: 'l1' },
      { id: 'l1b', name: 'lane_1_actor_b', note: 'in its clone', kind: 'partner', env: 'l1' },
      { id: 'l2a', name: 'lane_2_actor_a', note: 'in its clone', kind: 'maker', env: 'l2' },
      { id: 'l2b', name: 'lane_2_actor_b', note: 'in its clone', kind: 'partner', env: 'l2' },
      { id: 'l3a', name: 'lane_3_actor_a', note: 'in its clone', kind: 'maker', env: 'l3' },
      { id: 'l3b', name: 'lane_3_actor_b', note: 'in its clone', kind: 'partner', env: 'l3' },
      { id: 'main', name: 'main', note: 'humanize, no model', kind: 'program', env: 'main' },
    ],
    turns: [
      {
        id: 'c0',
        role: 'co',
        at: 0,
        label: 'plans three lanes',
        session: 'new',
        does: 'plan',
        pass: [
          { to: 'x1', said: 'lane 1', via: 'text' },
          { to: 'y1', said: 'lane 2', via: 'text' },
          { to: 'z1', said: 'lane 3', via: 'text' },
        ],
      },
      { id: 'x1', role: 'l1a', at: 1, label: 'a turn', session: 'new', pass: tree('the clone', 'x2') },
      { id: 'y1', role: 'l2a', at: 1, label: 'a turn', session: 'new', pass: tree('the clone', 'y2') },
      { id: 'z1', role: 'l3a', at: 1, label: 'a turn', session: 'new', pass: tree('the clone', 'z2') },
      { id: 'x2', role: 'l1b', at: 2, label: 'a turn', session: 'new' },
      {
        id: 'y2',
        role: 'l2b',
        at: 2,
        label: 'pfc evaluate, PR ready',
        session: 'new',
        pass: tree('a PR and its receipt', 'm'),
      },
      { id: 'z2', role: 'l3b', at: 2, label: 'a turn', session: 'new' },
      {
        id: 'm',
        role: 'main',
        at: 3,
        label: 'beats main: merged',
        session: 'none',
        pass: [
          { to: 'x3', said: 'pr_merged', via: 'text' },
          { to: 'z3', said: 'pr_merged', via: 'text' },
        ],
      },
      { id: 'x3', role: 'l1a', at: 4, label: 'on the new main', session: 'new' },
      { id: 'z3', role: 'l3a', at: 4, label: 'on the new main', session: 'new' },
    ],
    loop: { from: 'x3', to: 'x1', said: 'each lane alternates a and b; main moves only for a measured improvement' },
    ends: [BUDGET, { is: 'you', said: 'you stop it' }],
    caption:
      'No reviewer: a pull request reaches main when its receipt shows an improvement, and the repository refuses any main that is not the tree that was measured.',
  },

  recursive_lean_prover: {
    of: 'recursive_lean_prover',
    beat: 140,
    envs: [
      { id: 'repo', name: 'your Lean repository' },
      { id: 'wt', name: 'the lemma’s own worktree' },
    ],
    roles: [
      { id: 'worker', name: 'worker', note: 'a new session a turn', kind: 'maker', env: 'repo' },
      { id: 'reviewer', name: 'reviewer', note: 'a new session a turn', kind: 'checker', env: 'repo' },
      { id: 'lean', name: 'worker, as builder', note: 'rlcr, in the worktree', kind: 'maker', env: 'wt' },
      { id: 'check', name: 'comparator', note: 'your script, no model', kind: 'program', env: 'wt' },
    ],
    turns: [
      { id: 'p', role: 'worker', at: 0, label: 'one plan', session: 'new', does: 'plan', calls: 'humanize1:gen-plan' },
      { id: 'n', role: 'worker', at: 1, label: 'a proof in prose', session: 'new', pass: text('the proof', 'r') },
      {
        id: 'r',
        role: 'reviewer',
        at: 2,
        label: 'audits every step',
        session: 'new',
        does: 'read',
        pass: text('valid', 'd'),
      },
      {
        id: 'd',
        role: 'worker',
        at: 3,
        label: 'splits it in lemmas',
        session: 'new',
        does: 'plan',
        pass: text('proved lemmas', 'f'),
      },
      {
        id: 'f',
        role: 'lean',
        at: 6,
        label: 'Lean, on a branch',
        session: 'new',
        calls: 'humanize1:rlcr',
        pass: tree('the candidate', 'c'),
      },
      { id: 'c', role: 'check', at: 7, label: 'comparator passes', session: 'none', pass: tree('the same candidate', 'a') },
      {
        id: 'a',
        role: 'reviewer',
        at: 8,
        label: 'reruns it: accepted',
        session: 'new',
        does: 'read',
        pass: text('into the wiki', 'end'),
      },
    ],
    split: { at: 'd', into: 2, said: 'each lemma runs this same line, at once' },
    ends: [{ is: 'done', said: 'the root theorem is proved' }, BUDGET],
    caption:
      'One lemma of the proof. A lemma that needs splitting sends child lemmas a level down, each running this same line at once; an accepted lemma goes into the wiki and unlocks whatever waited on it.',
  },
}
