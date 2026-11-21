// Every page of the documentation, in the order a sidebar lists it: four sections, each a tab at the
// head of the sidebar (theme/humanfia/SectionNav.vue). A new page is one line here.
import type { DefaultTheme } from 'vitepress'

export const SIDEBAR: DefaultTheme.Sidebar = {
  '/tutorials/': [
    { text: "Tutorials", link: '/tutorials/' },
    {
      text: 'Using Humanize',
      collapsed: false,
      items: [
        { text: 'Finish your first task in Humanize Desktop', link: '/tutorials/first-task-desktop' },
        { text: 'Finish your first task in the terminal', link: '/tutorials/first-task-terminal' },
        { text: 'Use Humanize from a browser and your phone', link: '/tutorials/browser-and-phone' },
        { text: 'Leave a long task running overnight', link: '/tutorials/overnight-run' },
        { text: 'Run two coding agents with a fallback', link: '/tutorials/two-agents-with-fallback' },
        { text: 'Run the work on a server or in a container', link: '/tutorials/work-on-a-server' },
        { text: 'Run a flow every night in CI', link: '/tutorials/nightly-in-ci' },
        { text: 'Read back, export and share a run', link: '/tutorials/read-back-a-run' },
      ],
    },
    {
      text: 'Building flows',
      collapsed: false,
      items: [
        { text: 'Write your first flow', link: '/tutorials/first-flow' },
        { text: 'Build an actor–reviewer loop under test', link: '/tutorials/review-loop' },
        { text: 'Build a flow that asks you', link: '/tutorials/ask-the-person' },
        { text: 'Fan out agents across git worktrees', link: '/tutorials/parallel-worktrees' },
        { text: 'Publish a flow to a flowverse', link: '/tutorials/publish-a-flow' },
        { text: 'Drive Humanize from Python', link: '/tutorials/drive-from-python' },
      ],
    },
  ],
  '/user/': [
    { text: "User Guide", link: '/user/' },
    {
      text: 'Get set up',
      collapsed: false,
      items: [
        { text: 'Install and update', link: '/user/install' },
        { text: 'Concepts', link: '/user/concepts' },
        { text: 'Humanize Desktop', link: '/user/desktop' },
        { text: 'The browser page', link: '/user/web' },
        { text: 'The terminal interface', link: '/user/terminal' },
        { text: 'The command line', link: '/user/command-line' },
        { text: 'Security', link: '/user/security' },
      ],
    },
    {
      text: 'Chat',
      collapsed: false,
      items: [
        { text: 'Chat with an agent', link: '/user/chat' },
        { text: 'Commands, skills and files in a chat', link: '/user/chat-input' },
        { text: 'Organise chats', link: '/user/manage-chats' },
        { text: 'Continue sessions from other CLIs', link: '/user/harness-sessions' },
        { text: 'Ask a side question', link: '/user/side-questions' },
        { text: 'Ai-chan', link: '/user/ai-chan' },
      ],
    },
    {
      text: 'Run flows',
      collapsed: false,
      items: [
        { text: 'Find and install flows', link: '/user/flows' },
        { text: 'Start an epic', link: '/user/epics' },
        { text: 'Budgets', link: '/user/budgets' },
        { text: 'Watch a run', link: '/user/watch-a-run' },
        { text: 'Talk to a running flow', link: '/user/steering' },
        { text: 'Answer a flow\'s questions', link: '/user/questions' },
        { text: 'Stop a run', link: '/user/stopping' },
        { text: 'Leave it running and come back', link: '/user/leaving' },
        { text: 'Resume a run', link: '/user/resuming' },
        { text: 'Notifications', link: '/user/notifications' },
      ],
    },
    {
      text: 'Agents and models',
      collapsed: false,
      items: [
        { text: 'Coding agents', link: '/user/agents' },
        { text: 'Accounts', link: '/user/accounts' },
        { text: 'Nous: models, retries and fallback', link: '/user/nous' },
        { text: 'Effort and swarm mode', link: '/user/efforts' },
        { text: 'Gateways, LiteLLM and custom CLIs', link: '/user/gateways' },
        { text: 'Permissions', link: '/user/permissions' },
        { text: 'Skills', link: '/user/skills' },
        { text: 'Cost and usage', link: '/user/usage' },
      ],
    },
    {
      text: 'Where the work runs',
      collapsed: false,
      items: [
        { text: 'Environments', link: '/user/environments' },
        { text: 'Files, changes and terminal', link: '/user/environment-panels' },
        { text: 'Snapshots and rewind', link: '/user/snapshots' },
        { text: 'Runtimes: servers, containers and clusters', link: '/user/runtimes' },
        { text: 'The sandbox', link: '/user/sandbox' },
      ],
    },
    {
      text: 'Machines and devices',
      collapsed: false,
      items: [
        { text: 'The daemon', link: '/user/daemon' },
        { text: 'Connect to other machines', link: '/user/daemons' },
        { text: 'Relays and WebRTC', link: '/user/relay' },
      ],
    },
    {
      text: 'After a run',
      collapsed: false,
      items: [
        { text: 'History and search', link: '/user/history' },
        { text: 'Trace a run with Exomyth', link: '/user/tracing' },
        { text: 'Export and import a run', link: '/user/export' },
        { text: 'Back up to git', link: '/user/backups' },
      ],
    },
    {
      text: 'Make it yours',
      collapsed: false,
      items: [
        { text: 'Settings', link: '/user/settings' },
        { text: 'Themes and language', link: '/user/themes' },
      ],
    },
    {
      text: 'Help',
      collapsed: false,
      items: [
        { text: 'Troubleshooting', link: '/user/troubleshooting' },
        { text: 'Report a problem', link: '/user/reporting' },
      ],
    },
  ],
  '/builder/': [
    { text: "Builder Guide", link: '/builder/' },
    {
      text: 'A flow',
      collapsed: false,
      items: [
        { text: 'Anatomy of a flow', link: '/builder/flow' },
        { text: 'Agent roles', link: '/builder/agents' },
        { text: 'Sessions and turns', link: '/builder/turns' },
        { text: 'Loops', link: '/builder/loops' },
        { text: 'Params', link: '/builder/params' },
        { text: 'Context, errors and cleanup', link: '/builder/context' },
        { text: 'Budgets in a flow', link: '/builder/budgets' },
      ],
    },
    {
      text: 'What you can ask an agent',
      collapsed: false,
      items: [
        { text: 'Goals', link: '/builder/goals' },
        { text: 'Typed answers', link: '/builder/shapes' },
        { text: 'Hooks', link: '/builder/hooks' },
        { text: 'Tools the agent can call', link: '/builder/tools' },
        { text: 'Skills and permissions', link: '/builder/skills' },
      ],
    },
    {
      text: 'People',
      collapsed: false,
      items: [
        { text: 'The person as an agent', link: '/builder/outworlder' },
        { text: 'Faces', link: '/builder/faces' },
      ],
    },
    {
      text: 'Composing',
      collapsed: false,
      items: [
        { text: 'Concurrent turns', link: '/builder/async' },
        { text: 'Call another flow', link: '/builder/calling-flows' },
        { text: 'Branch a conversation', link: '/builder/branching' },
        { text: 'Resumable flows', link: '/builder/resumable' },
      ],
    },
    {
      text: 'Environments',
      collapsed: false,
      items: [
        { text: 'Environment roles', link: '/builder/environments' },
        { text: 'Worktrees, clones and scratch', link: '/builder/worktrees' },
        { text: 'Machines and moving sessions', link: '/builder/machines' },
      ],
    },
    {
      text: 'Ship it',
      collapsed: false,
      items: [
        { text: 'Test a flow', link: '/builder/testing' },
        { text: 'Publish and version a flow', link: '/builder/publishing' },
        { text: 'The Python SDK', link: '/builder/sdk' },
      ],
    },
  ],
  '/reference/': [
    { text: "Reference", link: '/reference/' },
    {
      text: 'Interfaces',
      collapsed: false,
      items: [
        { text: 'CLI', link: '/reference/cli' },
        { text: 'Terminal commands and keys', link: '/reference/tui' },
        { text: 'Page addresses and shortcuts', link: '/reference/web' },
        { text: 'Desktop app', link: '/reference/desktop' },
      ],
    },
    {
      text: 'Python',
      collapsed: false,
      items: [
        { text: 'Flow API', link: '/reference/flows' },
        { text: 'SDK', link: '/reference/sdk' },
        { text: 'Agents and harnesses', link: '/reference/agents' },
        { text: 'Environments and runtimes', link: '/reference/environments' },
      ],
    },
    {
      text: 'System',
      collapsed: false,
      items: [
        { text: 'Daemon and wire', link: '/reference/daemon' },
        { text: 'Events and records', link: '/reference/events' },
        { text: 'Trace formats', link: '/reference/tracing' },
        { text: 'settings.yaml', link: '/reference/settings' },
        { text: 'Environment variables', link: '/reference/environment' },
        { text: 'Files on disk', link: '/reference/files' },
      ],
    },
  ],
}
