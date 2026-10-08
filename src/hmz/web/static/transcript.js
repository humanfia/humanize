// What a run said, as the terminal interface's transcript says it: an agent's words on a
// bullet, your lines on the prompt's chevron, a tool on a bullet of its own, a turn closed by
// how long it worked -- read off the records of a run going, or off the trace of one that is
// written down.

import { h, lasting } from './dom.js'

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
  return h(
    'div',
    { class: ['said', kind], 'data-hmz': 'said' },
    h('span', { class: 'g', 'aria-hidden': 'true' }, GLYPHS[kind] || '·'),
    h('div', { class: 'body' }, who ? h('div', { class: 'who' }, who) : null, shown),
  )
}

/**
 * What a run going says, a record at a time: on one session's transcript, or every one's
 * where `key` is "". Kept between records, so that a transcript of thousands of lines is
 * drawn once and then added to, rather than drawn again for every word.
 *
 * @returns {(record: object) => Node[]} What one more record adds to the transcript.
 */
export function sayer(key) {
  const began = new Map()
  return (record) => {
    const mine = !key || record.key === key || record.session === key
    switch (record.type) {
      case 'said':
        return mine ? [line('you', record.text, { who: record.by ? `${record.by} said` : '' })] : []
      case 'asked':
        return !key || (record.role && key.startsWith(`${record.role}/`)) ? [line('asks', record.text, { who: `${record.role || 'the flow'} asks` })] : []
      case 'notice':
      case 'printed':
        return key ? [] : [line('notice', record.text)]
      case 'refused':
        return key ? [] : [line('failed', `hmz: ${record.because || record.text || 'refused'}`)]
      case 'ended':
        if (key) return []
        return [line(record.how === 'done' ? 'ends' : 'failed', record.how === 'done' ? '— the flow is done —' : `hmz: ${record.why || record.how}`)]
      case 'event':
        return mine ? said(record, key ? '' : record.session || record.agent, began) : []
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

/** What one session of a run written down said and did, read off its trace. */
export function saidTraced(session) {
  const lines = []
  for (const action of session.actions) {
    const args = action.args || {}
    switch (action.category) {
      case 'turn':
        lines.push(h('div', { class: 'said turn' }, h('span', { class: 'g' }, '❯'), h('div', { class: 'body' }, args.prompt ? String(args.prompt) : action.name)))
        break
      case 'message':
        lines.push(line('text', args.text ?? action.name))
        break
      case 'tool': {
        const said = [action.name]
        if (args.input !== undefined) said.push(`\n${typeof args.input === 'string' ? args.input : JSON.stringify(args.input, null, 2)}`)
        if (args.output !== undefined || args.result !== undefined) {
          const out = args.output ?? args.result
          said.push(`\n⎿ ${typeof out === 'string' ? out : JSON.stringify(out, null, 2)}`)
        }
        if (args.error) said.push(`\n✕ ${args.error}`)
        lines.push(line('tool', said.join(''), { folded: true }))
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
