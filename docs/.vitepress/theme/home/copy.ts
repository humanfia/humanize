// Every word of the home page, but its title and description, which are the frontmatter of
// docs/index.md. They were written by gemini-4-argon, slot by slot, from what each stands beside.
// To change one, ask the model again; do not edit it here by hand.
//
// `pnpm check:words` (.vitepress/words.mjs) holds this file, and those two lines, to the page's
// rules: the banner is the repository's description word for word, and the page's title ends
// with it; a tab or a button is one word; and no string has a digit, a number written out, a
// comma or a semicolon in it, which is how it sees a count and two fragments joined.
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

/** The drawing of the loop: its four words, and what it is for a reader who cannot see it. */
export const LOOP = {
  task: 'Task',
  work: 'Work',
  review: 'Review',
  done: 'Done',
  alt: 'An animated diagram shows a task entering a loop where an agent works and a reviewer checks it until it finishes.',
}

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
