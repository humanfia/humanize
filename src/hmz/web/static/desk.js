// What the page says around the box a chat is typed into, apart from how it is drawn: what the
// box's Add menu offers and what picking one types, which chats a new chat's page lists as
// waiting on their person, what a chat's Usage chip says, how a chat stands in a line over its
// box, when its box's button stops its turn, and which pane each button of a chat's bar is of. Nothing here touches the page, so it
// is read the same by the views and by their tests (Sections 3.6.6.15 to 3.6.6.21 and 3.8.21
// to 3.8.24 of protocol/web.md).

import { t } from './i18n.js'

/**
 * What the Add menu of a chat's box offers, in its order: each a prefix the box reads a line by
 * (Section 8.9 of protocol/core.md), under a name that says what it is for.
 */
export const ADDS = [
  { key: 'files', label: t('Add files'), sigil: '@', glyph: 'file' },
  { key: 'commands', label: t('Slash commands'), sigil: '/', glyph: 'menu' },
  { key: 'skills', label: t('Skills and flows'), sigil: '$', glyph: 'flows' },
  { key: 'shell', label: t('Run a shell command'), sigil: '!', glyph: 'chevron' },
]

/** Why `Add files` cannot be picked on a form whose folder is none: there is nothing to list. */
export const NO_FOLDER = t('Pick a folder first')

/**
 * Whether the focus is still to be given: a form that reads what it offers before its box is
 * typed into gives the box the focus once that is read, which may be long after it was asked
 * for. It is, where the focus is on what held it as the reading began, or on nothing in
 * particular -- gone with what held it, or left on the page as a whole. Moved since to something
 * else, by a key or the pointer or a dialog closing, it is where its person put it, and stays.
 *
 * @param {object|null} held What held the focus as the reading began.
 * @param {object|null} now What holds it now.
 * @param {object[]} loose What holds it where nothing in particular does: the body, the view.
 * @returns {boolean}
 */
export function unmoved(held, now, loose) {
  return !now || now === held || loose.includes(now)
}

/**
 * What a box holds once a prefix was picked from its Add menu, and where its caret then is: `@`
 * goes in where the caret is, as a word of its own; `/`, `$` and `!` name a whole line, so they
 * go at its start, before whatever was typed -- and not twice.
 *
 * @param {string} text What the box holds.
 * @param {number} caret Where its caret is.
 * @param {string} sigil The prefix picked.
 * @returns {{text: string, caret: number}}
 */
export function added(text, caret, sigil) {
  if (sigil === '@') {
    const at = Math.max(0, Math.min(caret, text.length))
    const gap = at > 0 && !/\s/.test(text[at - 1]) ? ' ' : ''
    return { text: `${text.slice(0, at)}${gap}@${text.slice(at)}`, caret: at + gap.length + 1 }
  }
  const lead = text.length - text.trimStart().length
  if (text[lead] === sigil) return { text, caret: lead + 1 }
  return { text: `${text.slice(0, lead)}${sigil}${text.slice(lead)}`, caret: lead + 1 }
}

/**
 * What the Add menu of a box offers: all of it under a chat, whose host says what each prefix
 * completes; before a chat or an epic there is, only what the page completes by itself -- the
 * files of the folder picked.
 *
 * @param {true | string[]} which Every one, or the keys of those the box offers.
 */
export function addsOf(which) {
  return which === true ? ADDS : ADDS.filter((one) => which.includes(one.key))
}

/**
 * What a chat waiting on its person is kept dismissed by: the chat, and what it waits on -- the
 * questions its host lists or, once it has folded away and lists none, those this browser holds
 * it owing (`waits`), so that it stays dismissed until it asks something else.
 *
 * @param {{name: string, asking?: string[]}} run The chat's row.
 * @param {string[]} [waits] What the page holds it waiting on, where its row lists nothing.
 */
export function stepKey(run, waits = []) {
  const asked = run.asking && run.asking.length ? run.asking : waits
  return `${run.name} ${asked.join(',')}`
}

/**
 * The chats a new chat's page lists as waiting on their person, newest first as they were
 * listed: every chat marked `asking` that was not dismissed since it last asked.
 *
 * @param {object[]} runs The chats listed, as rows (`chatRow`).
 * @param {(run: object) => boolean} chat Whether a row is a chat.
 * @param {(run: object) => string} mark How a row is marked.
 * @param {Iterable<string>} dismissed The keys (`stepKey`) dismissed in this browser.
 * @param {(run: object) => string[]} [waits] What a row is held waiting on where it lists nothing.
 */
export function nextSteps(runs, chat, mark, dismissed = [], waits = () => []) {
  const gone = new Set(dismissed)
  return (runs || []).filter((run) => chat(run) && mark(run) === 'asking' && !gone.has(stepKey(run, waits(run))))
}

/** The keys dismissed, with one more: only the latest `kept` are kept. */
export function dismissing(dismissed, key, kept = 200) {
  return [...[...dismissed].filter((one) => one !== key), key].slice(-kept)
}

/**
 * What a chip under a box is called by whoever cannot see it: what it picks, then what is picked
 * -- `Environment: Local` -- or what it picks alone while nothing is.
 */
export function chipNamed(what, value = '') {
  return value ? t('{what}: {value}', { what, value }) : what
}

/**
 * What a pane's button says where pointed at: its name, or why it cannot be opened -- the
 * environment the chat works in keeps no such panel. Whether a host holds the chat is never
 * why: its environment is brought up as a pane of it is opened.
 *
 * @param {string} key The pane, by its key in `PANES`.
 * @param {boolean} has Whether the chat's environment keeps that pane, as far as is known.
 */
export function paneSaid(key, has) {
  const pane = PANES.find((one) => one.key === key)
  if (!pane) return ''
  return has ? pane.label : UNOPENED[key]
}

/** A count of tokens short enough for a narrow column, as the runs' own figures cut one short. */
export function thousands(count) {
  if (count < 1e3) return String(Math.round(count))
  return count < 1e6 ? `${(count / 1e3).toFixed(1)}k` : `${(count / 1e6).toFixed(2)}M`
}

/** The kinds of token a backend counts, as a person reads each. */
const KINDS = {
  input: t('Input'),
  output: t('Output'),
  cache_read: t('Cache read'),
  cache_write: t('Cache write'),
  reasoning: t('Reasoning'),
}

/** A kind of token as a person reads it: `cache_read` is `Cache read`; one the page has no word for, as it is spelled. */
const kindName = (kind) => KINDS[kind] || `${kind[0].toUpperCase()}${kind.slice(1)}`.replaceAll('_', ' ')

/**
 * The rows of a chat's Usage popup: what it has spent, the tokens it has gone through and how
 * long it has run, and while it runs each kind of token with its share of them all; what the
 * chat written down spent once it has folded away; none while nothing was spent.
 *
 * @param {{tally?: string[], lasting?: string, reckoning?: {kind: string, tokens: number, whole: boolean}[]} | null} figures
 *   A chat going's figures, as its host says them.
 * @param {{money?: string, tokens?: string, worked?: string} | null} spent What a chat written down spent.
 * @returns {{label: string, value: string, share?: number}[]} A row with a `share`, 0 to 1, is a kind of token.
 */
export function usageRows(figures, spent) {
  const [tokens = '', money = ''] = (figures && figures.tally) || []
  if (tokens) {
    const priced = money.split(' · ')[0]
    const kinds = figures.reckoning || []
    const all = kinds.reduce((sum, one) => sum + one.tokens, 0)
    // A figure short of what some agent spends without counting is a floor, marked as the tally marks it.
    const floor = (whole) => (whole ? '' : '+')
    return [
      { label: t('Spent'), value: priced.startsWith('$') ? priced : '—' },
      { label: t('Tokens'), value: all ? `${thousands(all)}${floor(kinds.every((one) => one.whole))}` : tokens.replace(/ tokens$/, '') },
      { label: t('Time'), value: figures.lasting || '—' },
      ...kinds.map((one) => ({ label: kindName(one.kind), value: `${thousands(one.tokens)}${floor(one.whole)}`, share: all ? one.tokens / all : 0 })),
    ]
  }
  const paid = spent && spent.money && spent.money !== '$0.00'
  const wrote = spent && spent.tokens && spent.tokens !== '0'
  if (!paid && !wrote) return []
  return [
    { label: t('Spent'), value: spent.money || '—' },
    { label: t('Output tokens'), value: spent.tokens || '—' },
    { label: t('Time working'), value: spent.worked || '—' },
  ]
}

/**
 * The rows of what a workspace has used lately, out of what `runs.usage` answers for 7 days:
 * today, the last of its days, and the whole of them.
 *
 * @param {{days?: object[], whole?: object}} data
 * @returns {{label: string, value: string, about: string, sub?: string}[]} `about`, the output
 *   tokens beside the money; `sub`, under the whole of them, over how many chats and epics.
 */
export function usedLately(data) {
  const row = (label, one = {}) => ({ label, value: one.money || '$0.00', about: t('{tokens} output tokens', { tokens: one.tokens || '0' }) })
  const whole = (data && data.whole) || {}
  const runs = whole.runs || 0
  return [
    // A day of the daemon's is a UTC day, as the Usage page of Settings says of its own.
    row(t('Today (UTC)'), ((data && data.days) || []).at(-1)),
    // Said of none as well, so that the popup is as tall whatever the answer.
    { ...row(t('Last 7 days'), whole), sub: !runs ? t('No chats or epics yet') : t('Over {n} chats and epics', { n: runs }) },
  ]
}

/**
 * What is said of how a chat stands in a line over its box: that it failed, and nothing else.
 * That a turn is open its button says, which stops it, and that it waits on its person the
 * conversation says, which ends on what was answered.
 *
 * @param {string} state The chat's mark (`markOf`).
 */
export function standing(state) {
  return ['failed', 'refused', 'crashed'].includes(state) ? t('The chat failed') : ''
}

/**
 * Whether the button of a chat's box stops rather than sends: while its host says a turn is
 * open, answering or asking mid-turn, and never between turns (Section 3.6.6.21 of
 * protocol/web.md).
 *
 * @param {string} [turn] The turn its host says: `running` or `done`.
 */
export function stoppable(turn = '') {
  return turn === 'running'
}

/**
 * The panes a chat's bar opens beside it, in the bar's order: the chat's details, and the three
 * panels of the environment it works in, each opened on its own tab.
 */
export const PANES = [
  { key: 'details', label: t('Details'), tab: 'epic', env: '' },
  { key: 'terminal', label: t('Terminal'), tab: 'env', env: 'terminal' },
  { key: 'changes', label: t('Changes'), tab: 'env', env: 'changes' },
  { key: 'files', label: t('Files'), tab: 'env', env: 'files' },
]

/**
 * Why a pane cannot be opened, by its key in `PANES`: the environment the chat has keeps no such
 * panel. `Details` is the chat's own, and always opens.
 */
const UNOPENED = {
  details: '',
  terminal: t('No terminal in this environment'),
  changes: t('No changes in this environment'),
  files: t('No files in this environment'),
}

/**
 * Which pane is open beside a chat, by its key in `PANES`: none while its panel is shut, or
 * while the panel shows what no button of the bar is of.
 *
 * @param {{open: boolean, tab: string, env: string}} now Whether the panel is open, the tab of
 *   it shown, and the panel of the environment shown in it.
 */
export function paneOf({ open, tab, env }) {
  if (!open) return ''
  const pane = PANES.find((one) => one.tab === tab && (one.tab !== 'env' || one.env === env))
  return pane ? pane.key : ''
}

/**
 * What pressing a pane's button does: shut the panel where that pane is the one open, else
 * open it on that pane.
 *
 * @returns {{open: boolean, tab: string, env: string}} How the panel then stands.
 */
export function toggled(now, key) {
  const pane = PANES.find((one) => one.key === key)
  if (!pane) return now
  if (paneOf(now) === key) return { ...now, open: false }
  return { open: true, tab: pane.tab, env: pane.env || now.env }
}
