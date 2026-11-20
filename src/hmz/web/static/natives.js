// What a line typed in a chat is, read as Section 8.9 of protocol/core.md reads it, and what the
// box under a chat offers to complete it with: the chat's catalogue (`chat.commands`, Section
// 4.21.3 of protocol/daemon.md) -- its harness's native entries, the names hmz keeps and the
// flows on offer -- each tagged with where it comes from. Kept apart from the page, as plain
// functions of what they are given, so that they are read the same everywhere and tested alone.

import { t } from './i18n.js'

/** The `/` names every frontend keeps for hmz in a chat (Section 8.9.7 of protocol/core.md). */
export const RESERVED = ['btw', 'chat', 'clear', 'epics', 'exit', 'flow', 'prefer', 'quit', 'resume', 'settings']

/** The sigils a chat's native input starts with. */
const SIGILS = '/$!@'

/**
 * The order the sources of a catalogue are offered in, and what each is called over its group,
 * in plain words: what hmz keeps goes by the product's name, and what the chat's CLI has by
 * what it is -- its commands, or by its sigil, its skills and what it can mention.
 */
export const SOURCES = [
  ['native', t('Commands')],
  ['hmz', 'Humanize'],
  ['flow', t('Flows')],
]

/** What the CLI's own entries are called under a sigil that is not for its commands. */
const NATIVE = { $: t('Skills'), '@': t('Mentions') }

/**
 * The word a completion would replace: the name being typed after a sigil, where the caret is.
 * `/` and `$` name something only at the start of a line, as the chat reads them; `@` names a
 * path anywhere a word starts; `/flow <name>` names a flow in its second word.
 *
 * @param {string} text What the box holds.
 * @param {number} caret Where the caret is in it.
 * @returns {{sigil: string, word: string, from: number, to: number} | null} The sigil (`flow` for
 *   the name after `/flow`), what is typed after it, and the span the completion replaces.
 */
export function typing(text, caret) {
  const before = text.slice(0, caret)
  const start = before.search(/\S*$/)
  const word = before.slice(start)
  const lead = text.length - text.trimStart().length
  const flowed = /^\s*\/flow\s+(\S*)$/.exec(before)
  if (flowed) return { sigil: 'flow', word: flowed[1], from: caret - flowed[1].length, to: caret }
  if (!word || !SIGILS.includes(word[0])) return null
  const sigil = word[0]
  if ((sigil === '/' || sigil === '$') && start !== lead) return null
  if (sigil === '!') return null
  return { sigil, word: word.slice(1), from: start, to: caret }
}

/** The tag an entry is drawn with: where it comes from, and for a native one, what it is. */
export function tagOf(entry) {
  if (entry.source === 'flow') return 'flow'
  if (entry.source === 'hmz') return 'hmz'
  return entry.sigil === '$' ? 'skill' : 'command'
}

/** Whether `$<name>` names both a native skill and a flow here, so the preference decides it. */
export function both(entries, name) {
  return entries.some((one) => one.source === 'native' && one.sigil === '$' && one.name === name) && entries.some((one) => one.source === 'flow' && one.name === name)
}

/**
 * What a `$` name that is both a skill and a flow does, and how the other is had: the chat's
 * preference picks one, and `/flow <name>` always names the flow (Section 8.9.11).
 */
export function bothHint(name, prefer) {
  return prefer === 'flow'
    ? t('${name} starts the flow here; pick Use the skill in the chat\'s menu for the skill', { name })
    : t('${name} uses the skill here; /flow {name} starts the flow', { name })
}

/** What a chat's preference does, and where it comes from, as the chat's menu says it. */
export function preferSaid(prefer, from) {
  return `${prefer === 'flow' ? t('Starts the flow') : t('Uses the skill')} · ${from === 'chat' ? t('set for this chat') : t('from settings')}`
}

/**
 * What to offer for the word typed: the catalogue's entries it could become, those it starts
 * first, grouped by where they come from.
 *
 * @param {{sigil: string, name: string, about: string, how: string, source: string}[]} entries The catalogue.
 * @param {{sigil: string, word: string}} typed What `typing` read.
 * @param {string} prefer The chat's preference.
 * @returns {{source: string, label: string, items: {insert: string, name: string, about: string, tag: string, hint: string, refused: boolean}[]}[]}
 */
export function completions(entries, typed, prefer) {
  if (!typed) return []
  const sigil = typed.sigil === 'flow' ? '$' : typed.sigil
  const word = typed.word.toLowerCase()
  const fit = entries.filter((one) => one.sigil === sigil && (typed.sigil !== 'flow' || one.source === 'flow'))
  // `@` names a path, which its entry has no name for: the entry is offered, as it is, only
  // before a path is begun.
  if (sigil === '@') return word ? [] : grouped(fit.map((one) => item(one, '@', entries, prefer)), sigil)
  const starts = fit.filter((one) => one.name.toLowerCase().startsWith(word))
  const within = fit.filter((one) => !one.name.toLowerCase().startsWith(word) && one.name.toLowerCase().includes(word))
  const lead = typed.sigil === 'flow' ? '' : sigil
  return grouped([...starts, ...within].map((one) => item(one, `${lead}${one.name} `, entries, prefer)), sigil)
}

function item(entry, insert, entries, prefer) {
  return {
    source: entry.source,
    insert,
    name: `${entry.sigil}${entry.name}`,
    about: entry.about || '',
    tag: tagOf(entry),
    hint: entry.sigil === '$' && both(entries, entry.name) ? bothHint(entry.name, prefer) : '',
    refused: entry.how === 'refuse',
  }
}

function grouped(items, sigil) {
  return SOURCES.map(([source, label]) => ({ source, label: (source === 'native' && NATIVE[sigil]) || label, items: items.filter((one) => one.source === source) })).filter((one) => one.items.length)
}

/**
 * What the page does with a line typed in a chat, as Section 8.9 of protocol/core.md reads it:
 * a name hmz keeps is the page's to serve (`reserved`); a `$` line naming a flow the preference
 * gives to it, and `/flow <name>`, start that flow (`flow`); everything else is said to the chat
 * (`say`), whose host serves the rest of the catalogue and refuses what it cannot take.
 *
 * @returns {{kind: 'reserved'|'flow'|'say', name: string, rest: string}}
 */
export function route(line, entries, prefer) {
  const text = line.trim()
  if (!text || !'/$'.includes(text[0])) return { kind: 'say', name: '', rest: '' }
  const name = text.slice(1).split(/\s+/)[0]
  const rest = text.slice(1 + name.length).trim()
  if (text[0] === '/') {
    if (name === 'flow') {
      const flow = rest.split(/\s+/)[0]
      return { kind: 'flow', name: flow, rest: rest.slice(flow.length).trim() }
    }
    return RESERVED.includes(name) ? { kind: 'reserved', name, rest } : { kind: 'say', name: '', rest: '' }
  }
  const flow = entries.some((one) => one.source === 'flow' && one.name === name)
  const skill = entries.some((one) => one.source === 'native' && one.sigil === '$' && one.name === name)
  return flow && (!skill || prefer === 'flow') ? { kind: 'flow', name, rest } : { kind: 'say', name: '', rest: '' }
}

/** A typed path after `@`, split into the directory it is in and the start of its name. */
export function pathParts(word) {
  const cut = word.lastIndexOf('/') + 1
  return { dir: word.slice(0, cut), base: word.slice(cut) }
}

/**
 * What `@` completes a path with, from a directory's listing (`paths.list`): its entries whose
 * names start as typed, a directory going on with `/`, a file ending the word.
 */
export function pathItems(dir, base, listed) {
  return listed
    .filter((one) => one.name.startsWith(base))
    .map((one) => ({ source: 'path', insert: `@${dir}${one.name}${one.dir ? '/' : ' '}`, name: `@${dir}${one.name}${one.dir ? '/' : ''}`, about: '', tag: one.dir ? 'dir' : 'file', hint: '', refused: false }))
}

/**
 * A `!` command run in a chat and what it printed, read off the host's `shell` record (Section
 * 4.9.2.4 of daemon.md), or null for a record that is not one.
 *
 * @returns {{command: string, out: string, err: string, status: number|null} | null}
 */
export function shellOf(record) {
  if (!record || record.type !== 'shell') return null
  return {
    command: String(record.command ?? ''),
    out: String(record.out ?? ''),
    err: String(record.err ?? ''),
    status: typeof record.status === 'number' ? record.status : null,
  }
}

/**
 * The parts a `!` command is drawn in, as a shell shows it: the command on its prompt, what it
 * printed, what it complained of, and how it exited where it failed.
 *
 * @returns {{part: 'input'|'stdout'|'stderr'|'status', text: string}[]}
 */
export function shellParts({ command, out, err, status }) {
  const parts = [{ part: 'input', text: `$ ${command.replace(/^!/, '')}` }]
  if (out.replace(/\n+$/, '')) parts.push({ part: 'stdout', text: out.replace(/\n+$/, '') })
  if (err.replace(/\n+$/, '')) parts.push({ part: 'stderr', text: err.replace(/\n+$/, '') })
  if (status) parts.push({ part: 'status', text: t('exit {status}', { status }) })
  return parts
}

/** A line the chat refused, with why, as the conversation says it. */
export function refusedSaid(record) {
  const because = String(record.because || '').trim()
  return because ? t('{text} -- refused: {why}', { text: record.text, why: because }) : t('{text} -- refused', { text: record.text })
}
