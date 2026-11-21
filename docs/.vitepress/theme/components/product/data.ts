// What the Humanize page lists, in one place: the agents and the features. The components lay
// it out.

export const REPO = 'https://github.com/humanfia/humanize'

// The rest of humanfia.ai: the flows' catalogue and the blog are the organisation's site, which
// this one is served under (at /humanize/) and is not built with.
export const HUMANFIA = 'https://humanfia.ai'

/** The coding agents Humanize runs, by the name each vendor gives its product: the harnesses of
 *  `src/hmz/coganchor/agents`, as `HARNESSES` (src/hmz/web/static/names.js) names them, but
 *  LiteLLM, which is a bare model and no agent. */
export const AGENTS = [
  'Claude Code',
  'Codex',
  'Cursor CLI',
  'Antigravity',
  'Grok Build',
  'Kimi Code',
  'Qwen Code',
  'OpenCode',
  'MiMo Code',
  'MiniMax Code',
  'Pi',
  'Oh My Pi',
  'DeepSeek Harness',
]

/** What Humanize does, one card each, each linked to the page of the User Guide about it. */
export const FEATURES = [
  {
    title: 'Runs the agents you have',
    body: 'Use Claude Code, Codex and eleven more with your own accounts. Combine several in one flow.',
    href: '/user/agents',
  },
  {
    title: 'Flows are loops in Python',
    body: 'Install a flow from a flowverse, or write your own in a few lines.',
    href: '/user/flows',
  },
  {
    title: 'Watch and steer a run',
    body: 'Watch every turn live. Message a running agent, and answer when a flow asks a question.',
    href: '/user/steering',
  },
  {
    title: 'A budget on every run',
    body: 'Cap cost, time or output tokens. The run stops at the limit.',
    href: '/user/budgets',
  },
  {
    title: 'Leave it running',
    body: 'Close the window and the run continues on your machine or a server. Reconnect or resume it later.',
    href: '/user/leaving',
  },
  {
    title: 'Read back what happened',
    body: 'Inspect every turn, tool call and cost on one timeline. Export or share it.',
    href: '/user/tracing',
  },
]
