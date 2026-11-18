// Ai-chan's conversations as the drawer says and makes them, nothing drawn: the scope a new one
// defaults to from what the page shows (Section 14.3.4 of protocol/core.md), what `aichan.create`
// is sent from the form, how each conversation is said in the list, and what a line typed to her
// does: answer what she waits on, or say it into her turn.

/** The scopes a conversation is made with, as the form offers them. */
export const SCOPES = [
  ['daemon', 'Daemon'],
  ['workspace', 'Workspace'],
  ['epic', 'Epic'],
]

/** The presets a conversation is made with, the first the default. */
export const PRESETS = ['read-only', 'danger-full-access']

/**
 * The scope a new conversation defaults to from where the page is: the epic it shows, else the
 * workspace it shows, else the daemon. An epic's workspace is not in its address: `workspace`
 * is "" for an epic, to be read from the epic.
 *
 * @param {string[]} parts The parts of the address's path, after the daemon it names.
 * @param {URLSearchParams} query Its query.
 * @returns {{scope: string, workspace: string, epic: string}}
 */
export function scopeOf(parts, query) {
  if (parts[0] === 'epics' && parts[1] && !(parts[1] === 'import' && parts.length === 2)) return { scope: 'epic', workspace: '', epic: parts[1] }
  const workspace = query.get('workspace') || ''
  if (workspace) return { scope: 'workspace', workspace, epic: '' }
  return { scope: 'daemon', workspace: '', epic: '' }
}

/**
 * What `aichan.create` is sent from the form: what the scope does not take left out, a nous ""
 * left to the `ai_chan` setting, and a title "" left to the task's first line.
 *
 * @param {{scope: string, workspace: string, epic: string, nous: string, preset: string, network: boolean, title: string, task: string}} form
 */
export function created({ scope, workspace, epic, nous, preset, network, title, task }) {
  const said = { scope, preset, network, task: task.trim() }
  if (scope !== 'daemon') said.workspace = workspace
  if (scope === 'epic') said.epic = epic.trim()
  if (nous.trim()) said.nous = nous.trim()
  if (title.trim()) said.title = title.trim()
  return said
}

/**
 * Why the form cannot make a conversation yet, or "" where it can: the daemon refuses the rest,
 * but a nous neither picked nor set is asked for here (Section 14.3.2 of protocol/core.md).
 *
 * @param {object} form As `created` takes it.
 * @param {string} setting The `ai_chan` setting.
 */
export function missing({ scope, workspace, epic, nous, task }, setting) {
  if (scope !== 'daemon' && !workspace) return 'Pick the workspace she works in.'
  if (scope === 'epic' && !epic.trim()) return 'Name the epic she works on.'
  if (!nous.trim() && !setting) return 'Pick her nous: Settings name none for Ai-chan.'
  if (!task.trim()) return 'Tell Ai-chan something to start with.'
  return ''
}

/** How a conversation stands, in a word: her turn open, between turns, folded away, or failed. */
export function stateSaid(state) {
  return { running: 'Answering', waiting: 'Waiting', folded: 'Folded away', failed: 'Failed' }[state] || state
}

/**
 * How the conversation drawn stands, off what its host says and recorded: `failed`, with what
 * the harness said, where its chat ended so (Section 8.5.3 of protocol/core.md), else her turn
 * open, between turns, or folded away.
 *
 * @param {{connected: boolean, turn: string, records: object[]}} held Whether her host holds it,
 *   the turn it says, and the records of its run.
 * @returns {{state: string, why: string}}
 */
export function stateOf({ connected, turn, records }) {
  const ended = records.findLast((one) => one.type === 'ended')
  if (ended && ended.how === 'failed') return { state: 'failed', why: ended.why || 'Her chat failed.' }
  return { state: connected ? (turn === 'running' ? 'running' : 'waiting') : 'folded', why: '' }
}

/** The last part of a path, as a list names a workspace. */
function last(path) {
  return String(path || '').split('/').filter(Boolean).pop() || path || ''
}

/** What a conversation reaches, in a few words: the daemon, a workspace, or an epic of one. */
export function scopeSaid({ scope, workspace, epic }) {
  if (scope === 'epic') return `Epic ${epic} · ${last(workspace)}`
  if (scope === 'workspace') return `Workspace ${last(workspace)}`
  return 'Daemon'
}

/** What a conversation may do, in a few words: its preset, and whether it reaches the network. */
export function permissionSaid({ preset, network }) {
  return `${preset} · network ${network ? 'on' : 'off'}`
}

/**
 * Ai-chan's session among what her host recorded: the first conversation it opened that is not
 * a person's, or "" before she has opened one.
 */
export function sessionOf(records) {
  const opened = records.find((one) => one.type === 'opened' && !one.person)
  return opened ? opened.key : ''
}

/**
 * What a line typed to her does: answers what she waits on -- her wait between turns, or a
 * question of hers mid-turn -- where she waits on one this page may answer, else is said into
 * her turn.
 *
 * @param {{question: string, owner?: string}[]} pending What the host says waits on a person.
 * @param {string} me Who this page is to the host.
 * @param {string} text The line.
 * @returns {['answer', {question: string, text: string}] | ['say', {text: string}]}
 */
export function told(pending, me, text) {
  const one = (pending || []).find((each) => !each.owner || each.owner === me)
  return one ? ['answer', { question: one.question, text }] : ['say', { text }]
}
