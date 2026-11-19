// What the page says around the box a chat is typed into, apart from how it is drawn: what the
// box's Add menu offers and what picking one types, which chats a new chat's page lists as
// waiting on their person, what a chat's Usage chip says, how a chat stands in a line over its
// box, and which pane each button of a chat's bar is of. Nothing here touches the page, so it
// is read the same by the views and by their tests (Sections 3.6.6.15 to 3.6.6.21 and 3.8.21
// to 3.8.24 of protocol/web.md).

/**
 * What the Add menu of a chat's box offers, in its order: each a prefix the box reads a line by
 * (Section 8.9 of protocol/core.md), under a name that says what it is for.
 */
export const ADDS = [
  { key: 'files', label: 'Add files', sigil: '@', glyph: 'file' },
  { key: 'commands', label: 'Slash commands', sigil: '/', glyph: 'menu' },
  { key: 'skills', label: 'Skills and flows', sigil: '$', glyph: 'flows' },
  { key: 'shell', label: 'Run a shell command', sigil: '!', glyph: 'chevron' },
]

/** Why `Add files` cannot be picked on a form whose folder is none: there is nothing to list. */
export const NO_FOLDER = 'Pick a folder first'

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
 * @param {object[]} runs The rows `runs.list` answered.
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
 * -- `Environment: Local`, `Usage: $0.42` -- or what it picks alone while nothing is.
 */
export function chipNamed(what, value = '') {
  return value ? `${what}: ${value}` : what
}

/**
 * What a pane's button says where pointed at: its name, or why it cannot be opened -- no host
 * holds the chat, so it has no environment now, or the environment it has keeps no such panel.
 *
 * @param {string} key The pane, by its key in `PANES`.
 * @param {boolean} has Whether the chat has that pane now.
 * @param {boolean} held Whether a host holds the chat.
 */
export function paneSaid(key, has, held) {
  const pane = PANES.find((one) => one.key === key)
  if (!pane) return ''
  if (has) return pane.label
  return held ? `No ${pane.label.toLowerCase()} in this environment` : `${pane.label} opens once the chat goes on`
}

/**
 * What a chat's Usage chip says beside its ring: what it has spent where that is priced, else
 * the tokens it has written, else nothing -- and then the ring stands alone.
 *
 * @param {{tally?: string[]} | null} figures A chat going's figures, as its host says them.
 * @param {{money?: string, tokens?: string} | null} spent What a chat written down spent.
 */
export function usageSaid(figures, spent) {
  const [tokens = '', money = ''] = (figures && figures.tally) || []
  const priced = money.split(' · ')[0]
  if (priced.startsWith('$')) return priced
  if (tokens) return tokens.split(' · ')[0]
  if (spent && spent.money && spent.money !== '$0.00') return spent.money
  if (spent && spent.tokens && spent.tokens !== '0') return `${spent.tokens} tokens`
  return ''
}

/**
 * How a chat stands, said in a line over its box only while there is something to say: who is
 * answering while a turn is open, that it waits on its person, or that it failed.
 *
 * @param {string} state The chat's mark (`markOf`).
 * @param {string} model The model answering it, as a person reads it, or ''.
 */
export function standing(state, model = '') {
  if (state === 'running') return `${model || 'The assistant'} is responding`
  if (state === 'asking') return 'Waiting for you'
  return ['failed', 'refused', 'crashed'].includes(state) ? 'The chat failed' : ''
}

/**
 * The panes a chat's bar opens beside it, in the bar's order: the chat's details, and the three
 * panels of the environment it works in, each opened on its own tab.
 */
export const PANES = [
  { key: 'details', label: 'Details', tab: 'epic', env: '' },
  { key: 'terminal', label: 'Terminal', tab: 'env', env: 'terminal' },
  { key: 'changes', label: 'Changes', tab: 'env', env: 'changes' },
  { key: 'files', label: 'Files', tab: 'env', env: 'files' },
]

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
