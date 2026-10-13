// What a run said, as the terminal interface's transcript says it: an agent's words on a
// bullet, your lines on the prompt's chevron, a tool on a bullet of its own, a turn closed by
// how long it worked -- read off the records of a run going, or off the trace of one that is
// written down.

import { h, lasting } from './dom.js'
import { copy, menuOn } from './ui.js'

/** How much of a long line is shown before the rest is folded away. */
const SHORT = 600

/** What each kind of thing a turn says is drawn with. */
const GLYPHS = {
  text: '●',
  result: '●',
  reasoning: '∴',
  tool: '⏺',
  failed: '✕',
  begins: '·',
  ends: '✻',
  asks: '?',
  notice: '●',
  subagent: '◆',
  'subagent-ends': '◇',
  you: '❯',
  btw: '●',
  turn: '❯',
}

/** One line of a transcript. */
export function line(kind, body, { who = '', folded = false } = {}) {
  const text = String(body ?? '')
  const shown =
    folded || text.length > SHORT
      ? h('details', { class: 'said-more' }, h('summary', {}, text.slice(0, 140).replace(/\s+/g, ' ') + (text.length > 140 ? '…' : '')), h('div', {}, text))
      : text
  const said = h(
    'div',
    { class: ['said', kind], 'data-hmz': 'said' },
    h('span', { class: 'g', 'aria-hidden': 'true' }, GLYPHS[kind] || '·'),
    h('div', { class: 'body' }, who ? h('div', { class: 'who' }, who) : null, shown),
  )
  // A line copied whole, or the whole thread: what selecting it would take a drag to get.
  return menuOn(said, () => [
    { label: 'Copy', glyph: 'copy', act: () => copy(text, 'Copied') },
    { label: 'Copy thread', glyph: 'copy', act: () => copy(threadOf(said), 'Thread copied') },
  ])
}

/** A thread as text: each line, whose it is where it says, one after another. */
function threadOf(one) {
  const thread = one.closest('.thread')
  if (!thread) return one.innerText
  return [...thread.querySelectorAll(':scope > .said')].map((line) => line.querySelector('.body').innerText.trim()).join('\n\n')
}

/**
 * What a run going says, a record at a time, as one of the terminal interface's transcripts
 * says it: one session's, `<agent>/<n>`; one agent's, every session of it, `agent:<agent>`; one
 * person's, what is asked of them and what they answer, `person:<role>`, by the role they
 * answer. Kept between records, so that a transcript of thousands of lines is drawn once and
 * then added to, rather than drawn again for every word.
 *
 * A chat's is read as a conversation: its session's thread opens on the task and goes on with
 * every answer the person gave as a line of theirs, and what to say next is never drawn as
 * asked, since it is only the reply said back.
 *
 * @returns {(record: object) => Node[]} What one more record adds to the transcript.
 */
export function sayer(key, { chat = false } = {}) {
  const began = new Map()
  const [kind, whom] = key.startsWith('agent:') ? ['agent', key.slice(6)] : key.startsWith('person:') ? ['person', key.slice(7)] : ['session', '']
  const of = (record) => String(record.session || record.key || record.agent || '')
  const whose = (record) => (kind === 'agent' ? of(record).split('/')[0] === whom : kind === 'person' ? false : of(record) === key)
  return (record) => {
    const mine = whose(record)
    switch (record.type) {
      case 'said': {
        const toPerson = kind === 'person' && (record.to === `outworlder:${whom}` || record.role === whom || record.by === whom)
        return mine || toPerson ? [line('you', record.text, { who: record.by ? `${record.by} said` : '' })] : []
      }
      case 'asked':
        if (chat && record.mode === 'listen' && kind !== 'person') return []
        // A question asked while a turn is open is that session's, where it says whose it is.
        return (
          kind === 'person'
            ? record.role === whom
            : record.key
              ? whose(record)
              : chat
                ? kind === 'session'
                : record.role && (kind === 'agent' ? record.role === whom : key.startsWith(`${record.role}/`))
        )
          ? [line('asks', record.text, { who: `${record.role || 'the flow'} asks` })]
          : []
      case 'answered':
        return chat && kind !== 'person' && record.text ? [line('you', record.text, { who: record.by ? `${record.by} said` : '' })] : []
      case 'started':
        return chat && kind !== 'person' && record.task ? [line('you', record.task)] : []
      case 'event':
        return mine ? said(record, kind === 'agent' ? record.session || record.agent : '', began) : []
      default:
        return []
    }
  }
}

function said(record, who, began) {
  const whose = record.session || record.agent
  switch (record.kind) {
    case 'begins':
      began.set(whose, record.at)
      return [line('begins', `${whose} is working`)]
    case 'ends': {
      const since = began.get(whose)
      return [line('ends', `Worked for ${since ? lasting(record.at - since) : '?'} · ${whose}`)]
    }
    // A turn's last word is the answer it ends on, which its words have said already: drawn
    // as the terminal interface draws it, once.
    case 'text':
    case 'asks':
    case 'notice':
      return [line(record.kind, record.text, { who })]
    case 'reasoning':
      return [line('reasoning', record.text, { who, folded: true })]
    case 'tool':
      return [line('tool', record.text, { who, folded: record.text.length > 140 })]
    case 'failed':
      return [line('failed', `hmz: ${record.text}`, { who })]
    case 'subagent':
    case 'subagent-ends': {
      const [named, ...about] = record.text.split(' ')
      const doing = record.kind === 'subagent' ? 'started' : 'done'
      return [line(record.kind, `${named}${about.length ? ` (${about.join(' ')})` : ''} ${doing}`, { who })]
    }
    default:
      return []
  }
}

/**
 * What sessions of a run written down said and did, read off its trace: one session's, or
 * several in the order they did it, each line saying whose it is.
 */
export function saidTraced(...sessions) {
  const lines = []
  const many = sessions.length > 1
  const actions = sessions.flatMap((one) => one.actions.map((action) => ({ ...action, whose: one.label || one.key }))).sort((a, b) => a.start - b.start)
  for (const action of actions) {
    const args = action.args || {}
    const who = many ? action.whose : ''
    switch (action.category) {
      case 'turn':
        lines.push(h('div', { class: 'said turn' }, h('span', { class: 'g' }, '❯'), h('div', { class: 'body' }, many ? h('div', { class: 'who' }, action.whose) : null, args.prompt ? String(args.prompt) : action.name)))
        break
      case 'message':
        lines.push(line('text', args.text ?? action.name, { who }))
        break
      case 'tool': {
        const said = [action.name]
        if (args.input !== undefined) said.push(`\n${typeof args.input === 'string' ? args.input : JSON.stringify(args.input, null, 2)}`)
        if (args.output !== undefined || args.result !== undefined) {
          const out = args.output ?? args.result
          said.push(`\n⎿ ${typeof out === 'string' ? out : JSON.stringify(out, null, 2)}`)
        }
        if (args.error) said.push(`\n✕ ${args.error}`)
        lines.push(line('tool', said.join(''), { who, folded: true }))
        break
      }
      case 'llm':
        lines.push(line('reasoning', [action.name, args.model, args.thinking].filter(Boolean).join(' · '), { folded: Boolean(args.thinking) }))
        break
      default:
        lines.push(line('notice', action.name))
        break
    }
  }
  return lines
}
