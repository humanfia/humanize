// Every flow in the catalogue, and the shape of each one, in one place.
//
// Two things are written down here: what a flow *is* -- its name, the roles `-a` fills, what
// ends it, what `--resume` carries -- which <HmzFlows> draws as the catalogue on /flows/, and
// what a run of it *looks like*, as a script of turns <HmzFlowShape> plays on each flow's page.
// Keeping both here means the catalogue and the diagrams cannot disagree.
//
// Everything is read off the flows themselves: `src/hmz/flows/builtin/chat` for `chat`, and
// https://github.com/humanfia/flowverse for the rest. A session marked `new` is one the flow
// opened for that turn; `held` is the same session taking another turn. That distinction is
// most of what separates these flows from each other, so it is what the diagram draws largest.

/** What a reader may be trying to get done, which is what the chooser on /flows/ asks. */
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
    hint: 'Seven agents in three lanes. In `parallel_flame_chase` one lane writes your tree and two work on copies; in `parallel_flame_chase_git_pr` every lane has a clone and main moves only for a measured improvement.',
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

/** The small drawing that stands for a flow in the catalogue. */
export type Family =
  | 'talk'
  | 'fresh'
  | 'held'
  | 'nudge'
  | 'goal'
  | 'pair'
  | 'review'
  | 'phases'
  | 'lanes'

export interface Flow {
  /** The name the catalogue lists it under. For every flow but `humanize1` it is also what
   *  `-f` and `$` take; `humanize1` holds three flows, each run as `humanize1:<phase>`. */
  name: string
  /** The flows a module of several holds, each run as `<name>:<phase>`. */
  phases?: string[]
  /** The page under /flows/. */
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
  family: Family
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
    family: 'talk',
  },
  {
    name: 'ralph_loop',
    link: '/flows/ralph-loop',
    roles: 'agent',
    said: 'The task again every round, in a fresh session, so only the repository carries over.',
    ends: '3 rounds in a row that answer nothing',
    keeps: 'the round count',
    jobs: ['grind'],
    family: 'fresh',
  },
  {
    name: 'stateful_ralph',
    link: '/flows/stateful-ralph',
    roles: 'agent',
    said: 'The task again every round, in one session that remembers every round before.',
    ends: '3 rounds in a row that answer nothing',
    keeps: 'the round count, not the session',
    jobs: ['grind'],
    family: 'held',
  },
  {
    name: 'continue_loop',
    link: '/flows/continue-loop',
    roles: 'agent',
    said: 'The task once, then “continue” to the same session, round after round.',
    ends: '3 failed turns in a row',
    keeps: 'the round count, not the session',
    jobs: ['grind'],
    family: 'nudge',
  },
  {
    name: 'goal',
    link: '/flows/goal',
    roles: 'worker',
    said: 'The task set as the agent’s own /goal: the model keeps going until it says the goal is met.',
    ends: 'the model says the goal is met',
    keeps: '',
    jobs: ['grind'],
    family: 'goal',
  },
  {
    name: 'flame_chase',
    link: '/flows/flame-chase',
    roles: 'first_chaser · second_chaser',
    said: 'Two agents take turns on the same task, each in a fresh session, passing only the tree.',
    ends: '3 failed turns in a row',
    keeps: 'whose turn is next, and the round count',
    jobs: ['pair'],
    family: 'pair',
  },
  {
    name: 'rlar',
    link: '/flows/rlar',
    roles: 'actor · reviewer',
    said: 'An actor works in one session; a fresh reviewer reads the work and writes its next prompt.',
    ends: 'the reviewer says the task is done',
    keeps: 'the last review, and the round count',
    jobs: ['review', 'pair'],
    family: 'review',
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
    family: 'phases',
  },
  {
    name: 'ralph_loop_agent_cleanup',
    link: '/flows/agent-cleanup',
    roles: 'agent · cleaner',
    said: 'ralph_loop, plus a cleaner that distills the tree into one commit every few turns.',
    ends: '3 turns in a row that come to nothing',
    keeps: 'the turn count and the epochs',
    jobs: ['grind'],
    family: 'fresh',
  },
  {
    name: 'flame_chase_agent_cleanup',
    link: '/flows/agent-cleanup',
    roles: 'first_chaser · second_chaser · cleaner',
    said: 'flame_chase, with the same cleaner working between the two chasers.',
    ends: '3 turns in a row that come to nothing',
    keeps: 'the turn count and the epochs',
    jobs: ['pair'],
    family: 'pair',
  },
  {
    name: 'parallel_flame_chase',
    link: '/flows/parallel-flame-chase',
    roles: 'coordinator · six lane actors',
    said: 'A coordinator plans three lanes once; lane 1 writes your tree, lanes 2 and 3 work on copies.',
    ends: 'nothing but the budget, or you',
    keeps: 'the plan, the copies, the reports, whose turn each lane is on',
    jobs: ['parallel'],
    family: 'lanes',
  },
  {
    name: 'parallel_flame_chase_git_pr',
    link: '/flows/parallel-flame-chase-git-pr',
    roles: 'orchestrator · six lane actors',
    said: 'Three lanes, each with a clone and pull requests; main moves only for a measured improvement.',
    ends: 'nothing but the budget, or you',
    keeps: 'the central repository, the receipts, the reports',
    jobs: ['parallel'],
    family: 'lanes',
  },
  {
    name: 'recursive_lean_prover',
    link: '/flows/recursive-lean-prover',
    roles: 'worker · reviewer',
    said: 'A Lean theorem, split into lemmas that are each planned, proved and formalized in a worktree of their own.',
    ends: 'the root theorem is proved, or refused',
    keeps: 'the lemmas proved so far, their branches and the wiki',
    jobs: ['lean'],
    family: 'phases',
  },
  {
    name: 'aot',
    link: '/flows/aot',
    roles: 'writer · critic',
    said: 'Writes a flow from your description, and lands it once it loads, runs on fakes and passes a critic.',
    ends: 'the flow lands, or the repairs run out',
    keeps: '',
    jobs: ['write'],
    family: 'review',
  },
]

/* ------------------------------------------------------------------------------------------
   The shapes. A script of turns, played left to right by <HmzFlowShape>.
   ------------------------------------------------------------------------------------------ */

/** What a step is drawn as. */
export type Tone = 'work' | 'read' | 'plan' | 'ask' | 'stop'

/** What one turn hands to another, and which turn it hands it to. */
export interface Carry {
  said: string
  to: string
}

export interface Step {
  /** Referred to by a carry, and by the loop. */
  id: string
  /** Which lane it is on. */
  lane: string
  /** When it happens. Two steps at the same column happen at once. */
  col: number
  /** How many columns it takes, for a turn that is longer than the others. Default 1. */
  span?: number
  label: string
  /** Whether the flow opened a session for this turn, held the one it had, or took no turn. */
  session?: 'new' | 'held' | 'none'
  tone?: Tone
  /** Turns of the model inside one turn of the flow -- what a goal is. */
  inside?: number
  carry?: Carry[]
}

export interface Lane {
  id: string
  name: string
  note: string
  /** Which of the six lane colours it takes, where two lanes are two halves of one thing.
   *  Left out, a lane takes the colour of its own place in the list. */
  tone?: number
}

export interface Shape {
  /** The flow it is of, as `-f` takes it. */
  of: string
  lanes: Lane[]
  steps: Step[]
  /** The arc back: what a round ends on, what it starts again at, and why. */
  loop?: { from: string; to: string; said: string }
  /** The bar under the diagram, where the run's budget is what stops it. */
  meter?: { kind: 'budget'; said: string }
  /** One line under the whole thing. */
  caption: string
}

const A = (said: string, to: string): Carry[] => [{ said, to }]

export const SHAPES: Record<string, Shape> = {
  chat: {
    of: 'chat',
    lanes: [
      { id: 'agent', name: 'the assistant', note: 'one session throughout' },
      { id: 'you', name: 'you', note: 'the one who ends it', tone: 6 },
    ],
    steps: [
      {
        id: 'y0',
        lane: 'you',
        col: 0,
        label: 'what you typed first',
        session: 'none',
        tone: 'ask',
        carry: A('the turn', 'a0'),
      },
      {
        id: 'a0',
        lane: 'agent',
        col: 1,
        label: 'a turn',
        session: 'new',
        carry: A('its answer', 'y1'),
      },
      {
        id: 'y1',
        lane: 'you',
        col: 2,
        label: 'what you type back',
        session: 'none',
        tone: 'ask',
        carry: A('the next turn', 'a1'),
      },
      {
        id: 'a1',
        lane: 'agent',
        col: 3,
        label: '…the same session',
        session: 'held',
        carry: A('its answer', 'y2'),
      },
      { id: 'y2', lane: 'you', col: 4, label: 'nothing sent back', session: 'none', tone: 'stop' },
    ],
    loop: { from: 'a1', to: 'y1', said: 'for as long as you answer' },
    caption:
      'Each answer comes to you, and what you type back is the next turn. Send nothing back — or run it under hmz exec, where nobody is at the prompt — and the run ends.',
  },

  ralph_loop: {
    of: 'ralph_loop',
    lanes: [{ id: 'agent', name: 'the agent', note: 'a new session a round' }],
    steps: [
      { id: 'r1', lane: 'agent', col: 0, label: 'the task, and the repository', session: 'new' },
      { id: 'r2', lane: 'agent', col: 1, label: 'the task, and the repository', session: 'new' },
      { id: 'r3', lane: 'agent', col: 2, label: 'the task, and the repository', session: 'new' },
      { id: 'r4', lane: 'agent', col: 3, label: 'the task, and the repository', session: 'new' },
    ],
    loop: { from: 'r4', to: 'r1', said: 'nothing carries but the repository' },
    meter: { kind: 'budget', said: 'what the turns spend, against the run’s budget' },
    caption:
      'Every round starts from the task and from whatever the round before it left in the working directory.',
  },

  stateful_ralph: {
    of: 'stateful_ralph',
    lanes: [{ id: 'agent', name: 'the agent', note: 'one session, longer' }],
    steps: [
      { id: 's1', lane: 'agent', col: 0, label: 'the task', session: 'new' },
      { id: 's2', lane: 'agent', col: 1, label: 'the task, again', session: 'held' },
      { id: 's3', lane: 'agent', col: 2, label: 'the task, again', session: 'held' },
      { id: 's4', lane: 'agent', col: 3, label: 'the task, again', session: 'held' },
    ],
    loop: { from: 's4', to: 's2', said: 'the same conversation, one round longer' },
    meter: { kind: 'budget', said: 'what the turns spend, against the run’s budget' },
    caption:
      'One session is one conversation, so the context window grows with every round — the other limit a long run of this reaches.',
  },

  continue_loop: {
    of: 'continue_loop',
    lanes: [{ id: 'agent', name: 'the agent', note: 'one session, nudged' }],
    steps: [
      { id: 'c1', lane: 'agent', col: 0, label: 'the task', session: 'new' },
      { id: 'c2', lane: 'agent', col: 1, label: '“continue”', session: 'held' },
      { id: 'c3', lane: 'agent', col: 2, label: '“continue”', session: 'held' },
      { id: 'c4', lane: 'agent', col: 3, label: '“continue”', session: 'held' },
    ],
    loop: { from: 'c4', to: 'c2', said: 'until the run’s budget is spent' },
    meter: { kind: 'budget', said: 'what the turns spend, against the run’s budget' },
    caption:
      'Until a turn answers, the task is sent again rather than “continue”: the word means something only to a session that heard the task.',
  },

  goal: {
    of: 'goal',
    lanes: [{ id: 'agent', name: 'the worker', note: 'one session, under a goal' }],
    steps: [
      {
        id: 'g1',
        lane: 'agent',
        col: 0,
        span: 3,
        label: '/goal <task>',
        session: 'new',
        inside: 6,
        carry: A('the goal, met', 'g2'),
      },
      { id: 'g2', lane: 'agent', col: 3, label: 'the model says it is done', session: 'none', tone: 'stop' },
    ],
    meter: { kind: 'budget', said: 'every turn the goal took, against the run’s budget' },
    caption:
      'The ticks inside the box are turns the backend started itself: a turn that would have ended starts another, until the model says the goal is met.',
  },

  flame_chase: {
    of: 'flame_chase',
    lanes: [
      { id: 'one', name: 'first_chaser', note: 'a fresh session a turn' },
      { id: 'two', name: 'second_chaser', note: 'a fresh session a turn' },
    ],
    steps: [
      {
        id: 'f1',
        lane: 'one',
        col: 0,
        label: 'the task, and the repository',
        session: 'new',
        carry: A('what it left in the tree', 'f2'),
      },
      {
        id: 'f2',
        lane: 'two',
        col: 1,
        label: 'the task, and the repository',
        session: 'new',
        carry: A('what it left in the tree', 'f3'),
      },
      {
        id: 'f3',
        lane: 'one',
        col: 2,
        label: 'the task, and the repository',
        session: 'new',
        carry: A('what it left in the tree', 'f4'),
      },
      { id: 'f4', lane: 'two', col: 3, label: 'the task, and the repository', session: 'new' },
    ],
    loop: { from: 'f4', to: 'f1', said: 'a round is a turn each' },
    meter: { kind: 'budget', said: 'the run’s budget, which the two spend between them' },
    caption:
      'Neither is told what the other said. What passes between them is the working directory.',
  },

  rlar: {
    of: 'rlar',
    lanes: [
      { id: 'actor', name: 'the actor', note: 'one session, remembers' },
      { id: 'reviewer', name: 'the reviewer', note: 'fresh every round' },
    ],
    steps: [
      {
        id: 'a1',
        lane: 'actor',
        col: 0,
        label: 'the task',
        session: 'new',
        carry: A('a round of work, in the tree', 'v1'),
      },
      {
        id: 'v1',
        lane: 'reviewer',
        col: 1,
        label: 'reads the repository',
        session: 'new',
        tone: 'read',
        carry: A('its notes, word for word', 'a2'),
      },
      {
        id: 'a2',
        lane: 'actor',
        col: 2,
        label: 'the review, as its prompt',
        session: 'held',
        carry: A('a round of work, in the tree', 'v2'),
      },
      {
        id: 'v2',
        lane: 'reviewer',
        col: 3,
        label: 'reads the repository',
        session: 'new',
        tone: 'read',
        carry: A('done: true', 'over'),
      },
      { id: 'over', lane: 'reviewer', col: 4, label: 'the run is over', session: 'none', tone: 'stop' },
    ],
    loop: { from: 'v2', to: 'a2', said: 'while the review says there is something left' },
    caption:
      'Every review answers two things: whether the task is done, and what the actor hears next.',
  },

  'humanize1-gen-idea': {
    of: 'humanize1:gen-idea',
    lanes: [{ id: 'drafter', name: 'the drafter', note: 'one session' }],
    steps: [
      {
        id: 'i1',
        lane: 'drafter',
        col: 0,
        span: 2,
        label: 'explores the idea in n directions',
        session: 'new',
        tone: 'plan',
        carry: A('the draft, written to a file', 'i2'),
      },
      { id: 'i2', lane: 'drafter', col: 2, label: '.humanize/ideas/…', session: 'none', tone: 'stop' },
    ],
    caption: 'One turn, one file. Running it again writes another draft.',
  },

  'humanize1-gen-plan': {
    of: 'humanize1:gen-plan',
    lanes: [
      { id: 'planner', name: 'the planner', note: 'one session throughout' },
      { id: 'analyst', name: 'the analyst', note: 'fresh, each reading' },
    ],
    steps: [
      {
        id: 'n0',
        lane: 'analyst',
        col: 0,
        label: 'checks the draft',
        session: 'new',
        tone: 'read',
        carry: A('the risks', 'p1'),
      },
      {
        id: 'p1',
        lane: 'planner',
        col: 1,
        label: 'writes the plan',
        session: 'new',
        tone: 'plan',
        carry: A('the plan as it stands', 'n1'),
      },
      {
        id: 'n1',
        lane: 'analyst',
        col: 2,
        label: 'reviews the plan',
        session: 'new',
        tone: 'read',
        carry: A('what it disagrees with', 'p2'),
      },
      {
        id: 'p2',
        lane: 'planner',
        col: 3,
        label: 'revises it',
        session: 'held',
        tone: 'plan',
        carry: A('the plan, agreed', 'p3'),
      },
      { id: 'p3', lane: 'planner', col: 4, label: 'docs/plan.md', session: 'none', tone: 'stop' },
    ],
    loop: { from: 'p2', to: 'n1', said: 'up to three rounds, until the two agree' },
    caption:
      'The side that writes remembers and the side that reads does not — the rule all of humanize1 is built on.',
  },

  'humanize1-rlcr': {
    of: 'humanize1:rlcr',
    lanes: [
      { id: 'builder', name: 'the builder', note: 'one session, the loop' },
      { id: 'reviewer', name: 'the reviewer', note: 'fresh, each round' },
      { id: 'you', name: 'you', note: 'asked only when you are there', tone: 6 },
    ],
    steps: [
      {
        id: 'q',
        lane: 'you',
        col: 0,
        label: 'have you read the plan?',
        session: 'none',
        tone: 'ask',
        carry: A('answered, or skipped when you are away', 'b1'),
      },
      {
        id: 'b1',
        lane: 'builder',
        col: 1,
        label: 'builds the plan',
        session: 'new',
        carry: A('believes it is done — the gates run', 'v1'),
      },
      {
        id: 'v1',
        lane: 'reviewer',
        col: 2,
        label: 'reviews what landed',
        session: 'new',
        tone: 'read',
        carry: A('[P0-9] findings, as the next prompt', 'b2'),
      },
      { id: 'b2', lane: 'builder', col: 3, label: '…the same session', session: 'held' },
    ],
    loop: { from: 'b2', to: 'v1', said: 'a round ends when the builder believes it is done' },
    caption:
      'The builder works until it believes the whole plan is done; the round’s checks run, and what the reviewer finds is what the builder hears next.',
  },

  ralph_loop_agent_cleanup: {
    of: 'ralph_loop_agent_cleanup',
    lanes: [
      { id: 'agent', name: 'the agent', note: 'a fresh session a turn' },
      { id: 'cleaner', name: 'the cleaner', note: 'a fresh session an epoch', tone: 4 },
    ],
    steps: [
      { id: 't1', lane: 'agent', col: 0, label: 'a turn', session: 'new' },
      { id: 't2', lane: 'agent', col: 1, label: 'a turn', session: 'new' },
      {
        id: 't3',
        lane: 'agent',
        col: 2,
        label: 'a turn',
        session: 'new',
        carry: A('the tree, three turns on', 'e1'),
      },
      {
        id: 'e1',
        lane: 'cleaner',
        col: 3,
        span: 2,
        label: 'distills it into one commit',
        session: 'new',
        tone: 'plan',
      },
    ],
    loop: { from: 'e1', to: 't1', said: 'every cleanup_turns turns, an epoch' },
    meter: { kind: 'budget', said: 'what the turns spend, against the run’s budget' },
    caption:
      'Between turns, the cleaner keeps the work under work_paths, deletes what strayed, writes NEXT.md, and the history becomes one commit.',
  },

  flame_chase_agent_cleanup: {
    of: 'flame_chase_agent_cleanup',
    lanes: [
      { id: 'one', name: 'first_chaser', note: 'a fresh session a turn' },
      { id: 'two', name: 'second_chaser', note: 'a fresh session a turn' },
      { id: 'cleaner', name: 'the cleaner', note: 'a fresh session an epoch', tone: 4 },
    ],
    steps: [
      { id: 'f1', lane: 'one', col: 0, label: 'turn 1', session: 'new' },
      { id: 'f2', lane: 'two', col: 1, label: 'turn 2', session: 'new' },
      { id: 'f3', lane: 'one', col: 2, label: 'turn 3', session: 'new' },
      {
        id: 'e1',
        lane: 'cleaner',
        col: 3,
        label: 'one commit',
        session: 'new',
        tone: 'plan',
      },
      { id: 'f4', lane: 'two', col: 4, label: 'turn 4', session: 'new' },
      { id: 'f5', lane: 'one', col: 5, label: 'turn 5', session: 'new' },
      { id: 'f6', lane: 'two', col: 6, label: 'turn 6', session: 'new' },
      {
        id: 'e2',
        lane: 'cleaner',
        col: 7,
        label: 'one commit',
        session: 'new',
        tone: 'plan',
      },
    ],
    loop: { from: 'e2', to: 'f1', said: 'the chasers alternate across epochs' },
    meter: { kind: 'budget', said: 'what the turns spend, against the run’s budget' },
    caption:
      'The chasers keep alternating across epochs, so after an odd number of turns the second chaser opens the next stretch.',
  },

  parallel_flame_chase: {
    of: 'parallel_flame_chase',
    lanes: [
      { id: 'co', name: 'coordinator', note: 'plans once, then gone', tone: 6 },
      { id: 'l1a', name: 'lane 1 · a', note: 'your tree, sole writer', tone: 1 },
      { id: 'l1b', name: 'lane 1 · b', note: 'your tree, sole writer', tone: 1 },
      { id: 'l2a', name: 'lane 2 · a', note: 'a private copy', tone: 2 },
      { id: 'l2b', name: 'lane 2 · b', note: 'a private copy', tone: 2 },
      { id: 'l3a', name: 'lane 3 · a', note: 'a private copy', tone: 3 },
      { id: 'l3b', name: 'lane 3 · b', note: 'a private copy', tone: 3 },
    ],
    steps: [
      {
        id: 'c0',
        lane: 'co',
        col: 0,
        label: 'plans the three lanes',
        session: 'new',
        tone: 'plan',
        carry: [
          { said: 'lane 1', to: 'x1' },
          { said: 'lane 2', to: 'y1' },
          { said: 'lane 3', to: 'z1' },
        ],
      },
      { id: 'x1', lane: 'l1a', col: 1, label: 'a turn', session: 'new' },
      { id: 'x2', lane: 'l1b', col: 2, label: 'a turn', session: 'new' },
      { id: 'x3', lane: 'l1a', col: 3, label: 'a turn', session: 'new' },
      { id: 'y1', lane: 'l2a', col: 1, label: 'a turn', session: 'new' },
      { id: 'y2', lane: 'l2b', col: 2, label: 'a turn', session: 'new' },
      {
        id: 'y3',
        lane: 'l2a',
        col: 3,
        label: 'a turn',
        session: 'new',
        carry: A('a report and an artifact', 'x3'),
      },
      { id: 'z1', lane: 'l3a', col: 1, label: 'a turn', session: 'new' },
      { id: 'z2', lane: 'l3b', col: 2, label: 'a turn', session: 'new' },
      { id: 'z3', lane: 'l3b', col: 3, label: 'a turn', session: 'new' },
    ],
    loop: { from: 'z3', to: 'x1', said: 'each lane alternates a and b, for as long as the run goes' },
    caption:
      'Three lanes at once, and only lane 1 writes your tree. What lanes 2 and 3 find reaches it as a report and an artifact, never as a write.',
  },

  parallel_flame_chase_git_pr: {
    of: 'parallel_flame_chase_git_pr',
    lanes: [
      { id: 'co', name: 'orchestrator', note: 'plans once', tone: 6 },
      { id: 'l1a', name: 'lane 1 · a', note: 'a clone of its own', tone: 1 },
      { id: 'l1b', name: 'lane 1 · b', note: 'a clone of its own', tone: 1 },
      { id: 'l2a', name: 'lane 2 · a', note: 'a clone of its own', tone: 2 },
      { id: 'l2b', name: 'lane 2 · b', note: 'a clone of its own', tone: 2 },
      { id: 'l3a', name: 'lane 3 · a', note: 'a clone of its own', tone: 3 },
      { id: 'l3b', name: 'lane 3 · b', note: 'a clone of its own', tone: 3 },
    ],
    steps: [
      {
        id: 'c0',
        lane: 'co',
        col: 0,
        label: 'plans the three lanes',
        session: 'new',
        tone: 'plan',
        carry: [
          { said: 'lane 1', to: 'x1' },
          { said: 'lane 2', to: 'y1' },
          { said: 'lane 3', to: 'z1' },
        ],
      },
      { id: 'x1', lane: 'l1a', col: 1, label: 'a turn', session: 'new' },
      { id: 'x2', lane: 'l1b', col: 2, label: 'a turn', session: 'new' },
      { id: 'y1', lane: 'l2a', col: 1, label: 'a turn', session: 'new' },
      {
        id: 'y2',
        lane: 'l2b',
        col: 2,
        label: 'pfc evaluate · a ready PR',
        session: 'new',
        tone: 'read',
        carry: A('a receipt that improves main — merged', 'x3'),
      },
      { id: 'z1', lane: 'l3a', col: 1, label: 'a turn', session: 'new' },
      { id: 'z2', lane: 'l3b', col: 2, label: 'a turn', session: 'new' },
      { id: 'x3', lane: 'l1a', col: 3, label: 'a turn, on the new main', session: 'new' },
      { id: 'y3', lane: 'l2a', col: 3, label: 'a turn', session: 'new' },
      { id: 'z3', lane: 'l3a', col: 3, label: 'a turn', session: 'new' },
    ],
    loop: { from: 'z3', to: 'x1', said: 'each lane alternates a and b; main moves only for a measured improvement' },
    caption:
      'No reviewer: a pull request reaches main when its receipt shows an improvement, and the repository refuses any main that is not the tree that was measured.',
  },

  recursive_lean_prover: {
    of: 'recursive_lean_prover',
    lanes: [
      { id: 'worker', name: 'the worker', note: 'a fresh session a turn' },
      { id: 'reviewer', name: 'the reviewer', note: 'a fresh session a turn' },
      { id: 'check', name: 'the comparator', note: 'your script, no model', tone: 6 },
    ],
    steps: [
      {
        id: 'p',
        lane: 'worker',
        col: 0,
        label: 'one plan',
        session: 'new',
        tone: 'plan',
      },
      {
        id: 'n',
        lane: 'worker',
        col: 1,
        label: 'a proof in prose',
        session: 'new',
        carry: A('the proof', 'r'),
      },
      {
        id: 'r',
        lane: 'reviewer',
        col: 2,
        label: 'checks every step',
        session: 'new',
        tone: 'read',
        carry: A('valid — formalize it', 'f'),
      },
      {
        id: 'f',
        lane: 'worker',
        col: 3,
        label: 'Lean, in a worktree',
        session: 'new',
        carry: A('the candidate', 'c'),
      },
      {
        id: 'c',
        lane: 'check',
        col: 4,
        label: 'comparator passes',
        session: 'none',
        tone: 'read',
        carry: A('the same candidate', 'a'),
      },
      {
        id: 'a',
        lane: 'reviewer',
        col: 5,
        label: 'reruns it: accepted',
        session: 'new',
        tone: 'read',
      },
    ],
    loop: { from: 'a', to: 'p', said: 'the next lemma whose dependencies are proved' },
    meter: { kind: 'budget', said: 'every turn of every lemma, against the run’s budget' },
    caption:
      'One lemma of the proof: the Lean is written by humanize1:rlcr, and an accepted lemma goes into the wiki. A lemma that needs splitting gets child lemmas that run this same line, many at once.',
  },

  aot: {
    of: 'aot',
    lanes: [
      { id: 'writer', name: 'the writer', note: 'one session throughout' },
      { id: 'gates', name: 'the gates', note: 'humanize, no model', tone: 6 },
      { id: 'critic', name: 'the critic', note: 'fresh, reads only' },
    ],
    steps: [
      {
        id: 'w1',
        lane: 'writer',
        col: 0,
        label: 'drafts a spec',
        session: 'new',
        tone: 'plan',
      },
      {
        id: 'w2',
        lane: 'writer',
        col: 1,
        label: 'drafts the flow',
        session: 'held',
        carry: A('the draft', 'g'),
      },
      {
        id: 'g',
        lane: 'gates',
        col: 2,
        label: 'loads it, runs it on fakes',
        session: 'none',
        tone: 'read',
        carry: A('passed', 'c'),
      },
      {
        id: 'c',
        lane: 'critic',
        col: 3,
        label: 'reads it fresh',
        session: 'new',
        tone: 'read',
        carry: A('approved', 'land'),
      },
      { id: 'land', lane: 'gates', col: 4, label: 'lands the flow', session: 'none', tone: 'stop' },
    ],
    loop: { from: 'c', to: 'w2', said: 'a refusal goes back word for word, up to repairs rounds' },
    caption:
      'A draft lands only once the engine has loaded it, it has ended on its own in three fake worlds, and a critic that never saw it written approves it.',
  },
}
