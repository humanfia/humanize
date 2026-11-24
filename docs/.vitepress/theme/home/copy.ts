// Every word of the home page, but its title and description, which are the frontmatter of
// docs/index.md.
//
// The page says one thing: Humanize is infrastructure. A flow is a program somebody else writes;
// what is here schedules the many different nous it asks for, in the environments it names,
// under one budget, for as long as one large task takes. So nothing here calls Humanize a flow,
// and nothing here sells a loop, a pane of sessions or a row of worktrees.
//
// `pnpm check:words` (.vitepress/words.mjs) holds this file, and those two lines, to the page's
// rules: the banner is the repository's description word for word, and the page's title ends
// with it; a tab or a button is one word; and no string is empty.
//
// What is not prose is not here, and the check does not see it: the names the page prints as
// they are. They are the install command; the platforms, macOS, Windows and Linux; the
// documentation's sections, Tutorials, User Guide, Builder Guide and Reference, which are the
// site's own navigation; and the links out, Flows and GitHub.

export const BANNER = 'The agent flow system for token maxxing.'

export const WORDS = {
  download: 'Download',
  docs: 'Docs',
  copy: 'Copy',
  copied: 'Copied',
  /** The stage's one control: it stops what moves on the page, and starts it again. */
  pause: 'Pause',
  play: 'Play',
  /** Beside Windows, while it is offered the command: where on Windows the command runs. */
  wsl: 'WSL',
  /** The stage's row of tabs, as a screen reader names it. */
  tabs: 'Product views',
}

/** The drawing of the scale: where Humanize is going, as five figures, each beside what it counts, and
 *  what the drawing is for a reader who cannot see it. */
export const SCALE = {
  flow: '1 flow',
  agents: '1M agents',
  envs: '1M envs',
  month: '1 month',
  task: '1 task',
  alt: 'A diagram shows one flow fanning out to a field of agents of different kinds, each in an environment of its own, all of them converging on one task along a rule that marks one month.',
}

/** What the infrastructure does, under the drawing: the claim, and the four parts that carry it.
 *  Each part is a label, a line that says it, a sentence of what is there today, and the page
 *  of the documentation that has the rest. */
export const INFRA = {
  kicker: 'Infrastructure',
  head: 'A flow is a program. Humanize is what it runs on.',
  lead: 'A flow says what to ask and of whom. Humanize schedules the many different nous it asks for, gives each a place to work, holds the whole run to one budget and keeps the record.',
  more: 'Read',
}

export const PILLARS = [
  {
    label: 'Nous',
    head: 'Many different minds on one schedule',
    text: 'A nous is a harness, an account, a model and an effort. Any mix of them fills the roles of one run, and a turn that fails is retried or carried to the next nous in a graph you draw.',
    href: '/user/nous',
  },
  {
    label: 'Environments',
    head: 'A place of its own for every agent',
    text: 'Work happens in environments on runtimes: this machine, an SSH host, Docker, a swarm, Apple containers or a Slurm cluster, each with caps on its CPUs, memory and GPUs.',
    href: '/user/runtimes',
  },
  {
    label: 'Budgets',
    head: 'One budget over the whole run',
    text: 'Time, cost and tokens are capped for the run and more tightly for any part of it. What is spent counts against every cap above it, and a run that stops can be resumed.',
    href: '/user/budgets',
  },
  {
    label: 'Tracing',
    head: 'One timeline for all of it',
    text: 'Exomyth draws every flow call, session, turn, model call and tool call of a run on one timeline, and sums them in a flame graph and a table.',
    href: '/user/tracing',
  },
] as const

/** The stage's scenes, in the order they play: the tab's word, what the picture shows (which is
 *  also the name of the link on it), and the page of the documentation it opens. `key` names
 *  the reels: `/shots/home-<key>.svg`. */
export const SCENES = [
  {
    key: 'run',
    tab: 'Run',
    alt: 'Humanize Desktop shows a running flow as a graph with an actor agent and a reviewer agent passing work back and forth.',
    href: '/user/epics',
  },
  {
    key: 'steer',
    tab: 'Steer',
    alt: 'Humanize Desktop shows a live agent thread where the user sends a message and the working agent takes it up.',
    href: '/user/steering',
  },
  {
    key: 'budget',
    tab: 'Budget',
    alt: 'Humanize Desktop shows a run filling up its cost and token caps before stopping at the limit.',
    href: '/user/budgets',
  },
  {
    key: 'ask',
    tab: 'Ask',
    alt: 'Humanize Desktop shows a flow pausing to ask the user a question and continuing after a button is clicked.',
    href: '/user/questions',
  },
  {
    key: 'replay',
    tab: 'Replay',
    alt: 'Humanize Desktop shows a completed run as a log of turns and tool calls with their costs.',
    href: '/user/tracing',
  },
  {
    key: 'terminal',
    tab: 'Terminal',
    alt: 'The Humanize terminal interface runs the flow inside a console window with the agents at work.',
    href: '/user/terminal',
  },
] as const
