// Ai-chan's conversations as the drawer says and makes them, nothing drawn: the scope a new one
// defaults to from what the page shows (Section 14.3.4 of protocol/core.md), the presets and the
// scopes its chip offers, what `aichan.create` is sent, how each conversation stands in the list -- its face, the line under its
// title, whether it is pinned or unread in this browser, and where it stands among the others --
// and what a line typed to her does: answer what she waits on, or say it into her turn.

import { t } from './i18n.js'

/** The scopes a conversation is made with, widest first, each as its chip names it. */
export const SCOPES = [
  ['daemon', t('Daemon')],
  ['workspace', t('Workspace')],
  ['epic', t('Epic')],
]

/**
 * The presets a conversation is made with, the first the default: each as a chat's permission
 * is named on its chip, with the one line that says what it lets her do.
 */
export const PRESETS = [
  { value: 'read-only', label: t('Read only'), about: t('Reads, and changes nothing') },
  { value: 'danger-full-access', label: t('Full access'), about: t('Changes what her scope reaches') },
]

/** What a scope is called on the chip, or the scope itself where it is none of them. */
export function scopeSaid(scope) {
  const found = SCOPES.find(([value]) => value === scope)
  return found ? found[1] : scope
}

/**
 * The scopes as the chip's menu offers them: each with what it reaches, whether it is the one
 * picked, and why it cannot be -- a workspace's with no folder to hold her to, an epic's while
 * the page shows no epic -- or '' where it can.
 *
 * @param {{scope: string, workspace: string, epic: string}} picked The scope picked, and the
 *   workspace and the epic the page shows.
 */
export function scopesOf({ scope, workspace, epic }) {
  const folder = workspace.replace(/\/+$/, '').split('/').pop() || workspace
  const said = {
    daemon: { about: t('Every workspace and epic here'), why: '' },
    workspace: { about: folder, why: workspace ? '' : t('No folder to hold her to') },
    epic: { about: epic, why: epic ? '' : t('Open an epic to hold her to it') },
  }
  return SCOPES.map(([value, label]) => ({ value, label, ...said[value], chosen: value === scope }))
}

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
 * What `aichan.create` is sent as the first line is said: what the scope does not take left
 * out, the nous and the preset picked, and the line as its task. Its title is the daemon's to
 * give, from that line.
 *
 * @param {{scope: string, workspace: string, epic: string, nous: string, preset: string, task: string}} picked
 */
export function created({ scope, workspace, epic, nous, preset, task }) {
  const said = { scope, nous: nous.trim(), preset, task: task.trim() }
  if (scope !== 'daemon') said.workspace = workspace
  if (scope === 'epic') said.epic = epic.trim()
  return said
}

/**
 * Why a conversation cannot be made yet, or "" where it can: the daemon refuses the rest, but
 * a nous not picked is asked for here (Section 14.3.2 of protocol/core.md).
 *
 * @param {{nous: string, task: string}} picked As `created` takes it.
 */
export function missing({ nous, task }) {
  if (!nous.trim()) return t('Pick a nous for Ai-chan.')
  if (!task.trim()) return t('Tell Ai-chan something to start with.')
  return ''
}

/** How much of the first line said a conversation is titled by (Section 4.22.2.1 of protocol/daemon.md). */
export const TITLED = 80

/** How many faces she has: `ai-chan/face-01.webp` to `face-16.webp` among the page's files. */
export const FACES = 16

/**
 * The face a conversation is drawn with, 1 to 16: its own for as long as it lasts, the same in
 * every browser, and scattered so that conversations made one after another seldom share one.
 *
 * @param {number} id The conversation's `id`.
 */
export function faceOf(id) {
  return (Math.imul(Number(id) || 0, 2654435761) >>> 28) % FACES + 1
}

/** The file of a conversation's face, among the page's. */
export function faceUrl(id) {
  return `/ai-chan/face-${String(faceOf(id)).padStart(2, '0')}.webp`
}

/** What a conversation is called: its title, or its number where it has none. */
export function titleOf(row) {
  return row.title || `Ai-chan #${row.id}`
}

/**
 * The one line under a conversation's title: that she is typing while her turn is open, else
 * the start of what was last said in it.
 *
 * @param {{state: string, latest?: string}} row As `aichan.list` answers it.
 */
export function previewOf(row) {
  return row.state === 'running' ? t('typing…') : row.latest || ''
}

/**
 * What this browser keeps of a daemon's conversations: which are pinned, which marked unread,
 * which were seen to have failed, and up to when each was read.
 *
 * @typedef {{pinned: number[], unread: number[], failed: number[], seen: Record<string, string>}} Marks
 */

/** What is kept of one daemon's, out of what is kept of every daemon's: nothing, where that is unreadable. */
export function marksOf(all, daemon) {
  const mine = all && typeof all === 'object' && all[daemon] && typeof all[daemon] === 'object' ? all[daemon] : {}
  const ids = (said) => (Array.isArray(said) ? said.filter(Number.isInteger) : [])
  return { pinned: ids(mine.pinned), unread: ids(mine.unread), failed: ids(mine.failed), seen: mine.seen && typeof mine.seen === 'object' ? { ...mine.seen } : {} }
}

/**
 * What is kept once the list was read again: nothing of a conversation that is gone, whose
 * number the next one made may take -- nor of one made since this one was last read, which is
 * another under its number; one never listed here before read up to now, so that only what is
 * said from here on makes it unread; and the one open read, whatever was said in it.
 *
 * @param {Marks} marks
 * @param {{id: number, created?: string, updated?: string}[]} rows As `aichan.list` answers them.
 * @param {number|null} [open] The conversation open in the drawer.
 * @returns {Marks}
 */
export function settled(marks, rows, open = null) {
  // Read up to a time before it was made, it was another's reading: this one is new here.
  const renewed = (row) => Boolean(marks.seen[row.id]) && (row.created || '') > marks.seen[row.id]
  const here = new Set(rows.filter((row) => !renewed(row)).map((one) => one.id))
  const still = (ids) => ids.filter((id) => here.has(id))
  const seen = {}
  for (const row of rows) seen[row.id] = row.id === open || !(row.id in marks.seen) || renewed(row) ? row.updated || '' : marks.seen[row.id]
  return { pinned: still(marks.pinned), unread: still(marks.unread).filter((id) => id !== open), failed: still(marks.failed), seen }
}

/** A mark put on a conversation, or taken off it: `pinned`, `unread` or `failed`. */
export function marked(marks, kind, id, on) {
  const others = marks[kind].filter((one) => one !== id)
  return { ...marks, [kind]: on ? [...others, id] : others }
}

/** A conversation read up to what was last said in it, by opening it or by `Mark as read`. */
export function read(marks, row) {
  return { ...marked(marks, 'unread', row.id, false), seen: { ...marks.seen, [row.id]: row.updated || '' } }
}

/**
 * Whether a conversation is unread here: marked so, or said something since it was last read.
 * The one open in the drawer never is.
 */
export function unreadOf(row, marks, open = null) {
  if (row.id === open) return false
  if (marks.unread.includes(row.id)) return true
  const seen = marks.seen[row.id]
  return seen !== undefined && (row.updated || '') > seen
}

/**
 * The conversations in the order the drawer lists them: the pinned first, then each by when
 * something was last said in it, the latest first, and the newer first of two said in at once.
 */
export function ordered(rows, marks) {
  const pinned = new Set(marks.pinned)
  const when = (row) => row.updated || row.created || ''
  return [...rows].sort((a, b) => pinned.has(b.id) - pinned.has(a.id) || (when(a) < when(b) ? 1 : when(a) > when(b) ? -1 : b.id - a.id))
}

/**
 * What a conversation's menu offers, and the row it is swiped to: pinning it or not, marking it
 * read or unread, and deleting it.
 *
 * @returns {{key: 'pin'|'read'|'delete', label: string, glyph: string, on?: boolean, danger?: boolean}[]}
 */
export function actionsOf(row, marks) {
  const pinned = marks.pinned.includes(row.id)
  const unread = unreadOf(row, marks)
  return [
    { key: 'pin', label: pinned ? t('Unpin') : t('Pin'), glyph: 'pin', on: !pinned },
    { key: 'read', label: unread ? t('Mark as read') : t('Mark as unread'), glyph: 'bell', on: unread },
    { key: 'delete', label: t('Delete'), glyph: 'trash', danger: true },
  ]
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
  if (ended && ended.how === 'failed') return { state: 'failed', why: ended.why || t('Her chat failed.') }
  return { state: connected ? (turn === 'running' ? 'running' : 'waiting') : 'folded', why: '' }
}

/** What ends what she is told ahead of the first line of a conversation (`briefing`, runtime/doing/aichan.py). */
const TOLD = '\n\nThe user says:\n\n'

/**
 * What a conversation carried on did before, as its trace kept it, for the drawer to draw: each
 * turn opened by the line the person said, without what she was told of herself ahead of it,
 * and no line that only names the model she thought with.
 *
 * @param {{category: string, name?: string, args?: object}[]} actions One session's, as `chat.get` answers them.
 */
export function earlierOf(actions) {
  return actions
    .filter((one) => one.category !== 'llm' || (one.args && one.args.thinking))
    .map((one) => {
      const args = one.args || {}
      if (one.category === 'llm') return { ...one, args: { ...args, model: '' } }
      if (one.category !== 'turn') return one
      const prompt = String(args.prompt ?? one.name ?? '')
      const at = prompt.startsWith('You are Ai-chan') ? prompt.indexOf(TOLD) : -1
      return at < 0 ? one : { ...one, args: { ...args, prompt: prompt.slice(at + TOLD.length) } }
    })
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

/**
 * Whether she is typing: her turn is open and she waits on nothing this page may answer. A
 * question of hers mid-turn, with answers offered or none, waits on the person, not on her.
 *
 * @param {boolean} answering Whether her turn is open.
 * @param {{question: string, owner?: string}[]} pending What the host says waits on a person.
 * @param {string} me Who this page is to the host.
 */
export function typingOf(answering, pending, me) {
  return answering && told(pending, me, '')[0] === 'say'
}
