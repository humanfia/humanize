// What the Humanize page says, in one place: the ablation, the agents and the features. The
// components lay it out; nothing here is drawn.

export const REPO = 'https://github.com/humanfia/humanize'

// The rest of humanfia.ai: the flows' catalogue and the blog are the organisation's site, which
// this one is served under (at /humanize/) and is not built with.
export const HUMANFIA = 'https://humanfia.ai'

/** The Humanize ablation in the KDA² post (2026-09-27): four base models, three levels of
 *  scaffolding, 50 problems each. */
export const ABLATION = [
  {
    key: 'putnam',
    label: 'PutnamBench',
    rows: [
      { label: 'GPT-5.6-sol', api: 3, cli: 46, flow: 50 },
      { label: 'Kimi-K3', api: 1, cli: 4, flow: 47 },
      { label: 'GLM-5.3', api: 0, cli: 2, flow: 25 },
      { label: 'DeepSeek V4 Pro', api: 0, cli: 4, flow: 13 },
    ],
  },
  {
    key: 'physics',
    label: 'Physics Cup',
    rows: [
      { label: 'GPT-5.6-sol', api: 31, cli: 41, flow: 44 },
      { label: 'Kimi-K3', api: 35, cli: 37, flow: 42 },
      { label: 'GLM-5.3', api: 24, cli: 34, flow: 40 },
      { label: 'DeepSeek V4 Pro', api: 32, cli: 35, flow: 39 },
    ],
  },
] as const

export const LEVELS = [
  { key: 'api', label: 'Model API' },
  { key: 'cli', label: 'Coding CLI' },
  { key: 'flow', label: 'Humanize flow' },
] as const

/** The coding agents Humanize runs, by product name. */
export const AGENTS = [
  'Claude Code',
  'Codex',
  'Cursor Agent',
  'Antigravity CLI',
  'Grok Build',
  'Kimi Code',
  'Qwen Code',
  'opencode',
  'mimocode',
  'MiniMax Code',
  'pi',
  'Oh My Pi',
  'DeepSeek Harness',
]

/** What a user gets, one card each, each linked to the page that shows it: a path in these
 *  docs, or the flows' catalogue on humanfia.ai. */
export const FEATURES = [
  {
    title: 'The agents you already have',
    body: 'Claude Code, Codex and eleven more, under your own logins and subscriptions. Mix them in one run.',
    href: '/features/backends',
  },
  {
    title: 'A proven loop for every task',
    body: 'Pick a flow that suits the work, or write your own in a few lines of Python.',
    href: `${HUMANFIA}/flows/`,
  },
  {
    title: 'Watch and steer as it works',
    body: 'Every turn shows live. Talk to a running agent, or answer when a flow asks you.',
    href: '/user/steering',
  },
  {
    title: 'A budget on every run',
    body: 'Cap time, tokens or dollars. A run stops when it is spent, never after.',
    href: '/features/allowances',
  },
  {
    title: 'Close the laptop, keep the run',
    body: 'Runs keep going in the background, on this machine or on your servers, and pick up where they stopped.',
    href: '/user/leaving',
  },
  {
    title: 'See everything it did',
    body: 'Every agent, command and cost on one timeline you can replay, export and share.',
    href: '/user/tracing',
  },
]
