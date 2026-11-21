// What a run said, as the terminal interface's transcript says it: an agent's words on a
// bullet, your lines on the prompt's chevron, a tool on a bullet of its own, a turn closed by
// how long it worked -- read off the records of a run going, or off the trace of one that is
// written down.

import { blocks } from './asking/blocks.js'
import { fieldsOf, kindOf, resolved, summaryOf } from './asking/logic.js'
import { h, lasting } from './dom.js'
import { t } from './i18n.js'
import { modelName } from './names.js'
import { refusedSaid, shellOf, shellParts } from './natives.js'
import { copy, menuOf, menuOn } from './ui.js'

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
  refused: '✕',
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
    { label: t('Copy'), glyph: 'copy', act: () => copy(text, t('Copied')) },
    { label: t('Copy thread'), glyph: 'copy', act: () => copy(threadOf(said), t('Thread copied')) },
  ])
}

/**
 * A `!` command run in a chat and what it printed, drawn as a shell draws them: the command on
 * its prompt, its output under it, what it complained of set apart, and how it exited where it
 * failed.
 */
export function shellLine(ran) {
  const parts = shellParts(ran)
  const text = parts.map((one) => one.text).join('\n')
  const said = h(
    'div',
    { class: 'said shell', 'data-hmz': 'said-shell' },
    h('span', { class: 'g', 'aria-hidden': 'true' }, '!'),
    h('div', { class: 'body' }, parts.map((one) => h('pre', { class: `shell-${one.part}` }, one.text))),
  )
  return menuOn(said, () => [
    { label: t('Copy'), glyph: 'copy', act: () => copy(text, t('Copied')) },
    { label: t('Copy output'), glyph: 'copy', act: () => copy([ran.out, ran.err].filter(Boolean).join('\n'), t('Copied')) },
  ])
}

/**
 * Gives the keys a way to a thread's lines, which nothing else gives the focus: the thread is
 * one stop of Tab, the arrows go from it to its newest line and then from line to line, and on a
 * line Alt and Enter open its menu, as the menu key does where a keyboard has one. A thread the
 * pointer pressed is scrolled by the arrows still.
 *
 * @param {HTMLElement} thread What holds the lines.
 * @returns {HTMLElement} The thread.
 */
export function walked(thread) {
  let tabbed = false
  thread.tabIndex = 0
  thread.addEventListener('focus', () => (tabbed = thread.matches(':focus-visible')))
  thread.addEventListener('pointerdown', () => (tabbed = false))
  thread.addEventListener('keydown', (event) => {
    const lines = [...thread.querySelectorAll(':scope > .said')]
    const on = lines.indexOf(event.target)
    if (event.key === 'Enter' && event.altKey && on >= 0) {
      if (menuOf(event.target)) event.preventDefault()
      return
    }
    const step = { ArrowUp: -1, ArrowDown: 1 }[event.key]
    if (!step || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
    const to = on < 0 ? event.target === thread && tabbed && lines.at(-1) : lines[on + step]
    if (!to) return
    event.preventDefault()
    to.tabIndex = -1
    to.focus()
  })
  return thread
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
 * asked, since it is only the reply said back. Anything else said in asking it -- that a turn
 * could not be taken, or that the conversation could not be carried on -- is the flow's own
 * word in the conversation, and is drawn there, as the terminal interface draws it. A `!`
 * command the chat ran is drawn as a shell draws it, and a line it refused with why. A turn of
 * its assistant's is closed by how long it worked and names no session: nothing is drawn as it
 * begins.
 *
 * Given `folded`, every tool is one line to open, as Ai-chan's are drawn.
 *
 * @returns {(record: object) => Node[]} What one more record adds to the transcript.
 */
export function sayer(key, { chat = false, folded = false } = {}) {
  const began = new Map()
  const [kind, whom] = key.startsWith('agent:') ? ['agent', key.slice(6)] : key.startsWith('person:') ? ['person', key.slice(7)] : ['session', '']
  const of = (record) => String(record.session || record.key || record.agent || '')
  const whose = (record) => (kind === 'agent' ? of(record).split('/')[0] === whom : kind === 'person' ? false : of(record) === key)
  // The answer the last turn ended on, which a chat says back to ask what next.
  let answer = ''
  // What each question asked for, so that its answer is said back as its fields.
  const schemas = new Map()
  // What an agent here last stopped to ask and the line that says it: the flow putting that to
  // its person is that question, said once.
  let stopped = null
  return (record) => {
    const mine = whose(record)
    switch (record.type) {
      case 'said': {
        const toPerson = kind === 'person' && (record.to === `outworlder:${whom}` || record.role === whom || record.by === whom)
        return mine || toPerson ? [line('you', record.text, { who: record.by ? t('{who} said', { who: record.by }) : '' })] : []
      }
      case 'asked':
        if (chat && record.mode === 'listen' && kind !== 'person') {
          const text = String(record.text || '').trim()
          return text && text !== answer.trim() && kind === 'session' ? [line('notice', text)] : []
        }
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
          ? asking(record)
          : []
      case 'answered':
        if (kind === 'person' && record.role === whom) return [line('you', answeredText(record, schemas), { who: record.by ? t('{who} answered', { who: record.by }) : t('answered') })]
        return chat && kind !== 'person' && record.text ? [line('you', record.text, { who: record.by ? t('{who} said', { who: record.by }) : '' })] : []
      // What a flow showed a person with nothing asked, in their thread.
      case 'shown':
        return (kind === 'person' && record.role === whom) || (kind === 'session' && (of(record) === key || key === `outworlder:${record.role}`)) ? [shown(record)] : []
      case 'started':
        return chat && kind !== 'person' && record.task ? [line('you', record.task)] : []
      // A chat's own: what its person ran, or said and it would not take.
      case 'shell':
        return chat && kind === 'session' ? [shellLine(shellOf(record))] : []
      case 'refused':
        return chat && kind === 'session' ? [line('refused', refusedSaid(record))] : []
      case 'event': {
        if (!mine) return []
        if (record.kind === 'result') answer = String(record.text || '')
        const lines = said(record, kind === 'agent' ? record.session || record.agent : '', began, { chat, folded })
        if (record.kind === 'asks') stopped = { text: String(record.text || '').trim(), line: lines[0] }
        return lines
      }
      default:
        return []
    }
  }

  /** A question put to a person: a line of its own, or the line its agent asked it on just before. */
  function asking(record) {
    const echoed = stopped && stopped.text === String(record.text || '').trim() ? stopped.line : null
    stopped = null
    const one = asked(record, schemas, echoed)
    return echoed ? [] : [one]
  }
}

/**
 * A question asked, with what it showed beside it and, for a form, how much it asks: on a line
 * of its own, or added to the line that asked it already. The line says which question it is,
 * `data-question`, for what answers it to be put by it.
 */
function asked(record, schemas, one = null) {
  one ||= line('asks', record.text, { who: record.role ? t('{who} asks', { who: record.role }) : t('the flow asks') })
  one.dataset.question = record.question
  const body = one.querySelector('.body')
  const context = blocks(record.context)
  if (context) body.append(context)
  if (record.schema && typeof record.schema === 'object') {
    schemas.set(record.question, record.schema)
    const top = resolved(record.schema).node
    const n = kindOf(top) === 'object' ? fieldsOf(top, record.schema).length : 1
    body.append(h('div', { class: 'ask-form-note dim', 'data-hmz': 'ask-form-note' }, t('form · {n} fields', { n })))
  }
  return one
}

/** An answer, as one line: a form's as its fields, text as it was said. */
function answeredText(record, schemas) {
  const text = String(record.text ?? '')
  const schema = schemas.get(record.question)
  if (!schema) return text
  try {
    return summaryOf(JSON.parse(text), schema, schema, 400)
  } catch {
    return text
  }
}

/** Context a flow showed a person, as blocks under who it was shown to. */
function shown(record) {
  const one = line('notice', '', { who: record.role ? t('shown to {who}', { who: record.role }) : t('shown to you') })
  one.classList.add('shown')
  one.dataset.hmz = 'said-shown'
  const context = blocks(record.context)
  if (context) one.querySelector('.body').append(context)
  return one
}

/**
 * What one thing a turn did adds to the transcript. A turn's start and its end name whose turn
 * it was; given `chat`, a chat's or an Ai-chan conversation's, they name nobody -- there is one
 * assistant, and no session for its person to tell from another: `begins` draws nothing, and
 * `ends` only how long the turn worked.
 */
function said(record, who, began, { chat = false, folded = false } = {}) {
  const whose = record.session || record.agent
  switch (record.kind) {
    case 'begins':
      began.set(whose, record.at)
      return chat ? [] : [line('begins', t('{who} is working', { who: whose }))]
    case 'ends': {
      const since = began.get(whose)
      const time = since ? lasting(record.at - since) : '?'
      return [line('ends', chat ? t('Worked for {time}', { time }) : t('Worked for {time} · {who}', { time, who: whose }))]
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
      return [line('tool', record.text, { who, folded: folded || record.text.length > 140 })]
    case 'failed':
      return [line('failed', `hmz: ${record.text}`, { who })]
    case 'subagent':
    case 'subagent-ends': {
      const [named, ...about] = record.text.split(' ')
      const called = `${named}${about.length ? ` (${about.join(' ')})` : ''}`
      return [line(record.kind, record.kind === 'subagent' ? t('{who} started', { who: called }) : t('{who} done', { who: called }), { who })]
    }
    default:
      return []
  }
}

/**
 * What sessions of a run written down said and did, read off its trace: one session's, or
 * several in the order they did it, each line saying whose it is. What opened a turn is drawn
 * on the prompt's chevron, as the terminal interface draws it; a chat's session, one given
 * with `chat`, has it as its person's line, as the chat drew it while it went.
 */
export function saidTraced(...sessions) {
  return tracedLines(...sessions).map((one) => one.make())
}

/**
 * The same, a line at a time and not yet drawn: each with a `key` that says all it is drawn
 * from, and what makes it. A trace read again is then drawn over the one drawn before by key
 * (`merged` of logs.js): the lines it had stay the nodes they were, and only what is new is made.
 *
 * @returns {{key: string, make: () => Node}[]}
 */
export function tracedLines(...sessions) {
  const lines = []
  const many = sessions.length > 1
  const actions = sessions.flatMap((one) => one.actions.map((action) => ({ action, whose: one.label || one.key, chat: Boolean(one.chat) }))).sort((a, b) => a.action.start - b.action.start)
  for (const { action, whose, chat } of actions) {
    lines.push({ key: JSON.stringify([many ? whose : '', chat, action]), make: () => tracedLine(action, whose, chat, many) })
  }
  return lines
}

/** One line of a trace. */
function tracedLine(action, whose, chat, many) {
  const args = action.args || {}
  const who = many ? whose : ''
  switch (action.category) {
    case 'turn': {
      const prompt = args.prompt ? String(args.prompt) : action.name
      return chat ? line('you', prompt) : h('div', { class: 'said turn' }, h('span', { class: 'g' }, '❯'), h('div', { class: 'body' }, many ? h('div', { class: 'who' }, whose) : null, prompt))
    }
    case 'message':
      return line('text', args.text ?? action.name, { who })
    case 'tool': {
      const said = [action.name]
      if (args.input !== undefined) said.push(`\n${typeof args.input === 'string' ? args.input : JSON.stringify(args.input, null, 2)}`)
      if (args.output !== undefined || args.result !== undefined) {
        const out = args.output ?? args.result
        said.push(`\n⎿ ${typeof out === 'string' ? out : JSON.stringify(out, null, 2)}`)
      }
      if (args.error) said.push(`\n✕ ${args.error}`)
      return line('tool', said.join(''), { who, folded: true })
    }
    case 'llm':
      return line('reasoning', [action.name, modelName(args.model), args.thinking].filter(Boolean).join(' · '), { folded: Boolean(args.thinking) })
    default:
      return line('notice', action.name)
  }
}
