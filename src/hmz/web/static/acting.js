// What a page does to the run going: answers what it asks, says a line to it, writes its board,
// and holds the roles a person fills -- each one request to the runs, refused with their reason.
// And what it asks beside the run, which never reaches the run at all.

import { get, post } from './api.js'
import { acting, confirming, fill, h, problem } from './dom.js'
import { ask } from './held.js'
import { chipSelect, composer } from './composer.js'
import { line } from './transcript.js'

/** One question the run is waiting on a person for, answerable here unless another holds it. */
export function question(workspace, one, me, clients) {
  const named = Object.fromEntries((clients || []).map((client) => [client.client, client.name || client.client]))
  const holder = h('div', { class: 'question', 'data-hmz': 'question' }, h('div', { class: 'kicker' }, `${one.role || 'the flow'} asks`), h('div', { class: 'body' }, one.text))
  if (one.owner && one.owner !== me) {
    holder.append(h('p', { class: 'dim' }, `Waiting for ${named[one.owner] || one.owner} to answer: that frontend holds ${one.role}.`))
    return holder
  }
  const options = (one.options || []).map((option, index) =>
    acting(option, () => ask(workspace, 'answer', { question: one.question, text: String(index + 1) }), { kind: 'btn small', busy: 'Answering…' }),
  )
  const typed = h('input', { type: 'text', placeholder: 'Answer', 'aria-label': 'Answer' })
  const form = h('form', { class: 'row' }, typed, h('button', { class: 'btn small primary', type: 'submit' }, 'Answer'))
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    if (!typed.value.trim()) return
    form.querySelector('.error')?.remove()
    try {
      await ask(workspace, 'answer', { question: one.question, text: typed.value })
      typed.value = ''
    } catch (error) {
      form.append(problem(error))
    }
  })
  if (options.length) holder.append(h('div', { class: 'row' }, options))
  holder.append(form)
  return holder
}

/**
 * Says a line to the run: into one session's turn, to a role, or to the next turn to start --
 * or, given a session, into that session alone. Made once for a page, as `asides` is, and told
 * who there is to say it to as that changes, so that a line being typed outlives every drawing
 * of the page around it. Given what the session is asked, a line typed while it is asked
 * something answers it, as a reply in a conversation does; and a session's line may be said
 * on another view of the run than the session's own.
 */
export function saying(workspace, session = '', { asked = () => null, to: into = session } = {}) {
  const to = h('select', { 'aria-label': 'Say it to' })
  const box = composer({
    placeholder: session ? `Message ${session.replace(/^outworlder:/, '')}` : 'Message the epic',
    label: 'What to say',
    submit: (text) => {
      const one = asked()
      return one ? ask(workspace, 'answer', { question: one.question, text }) : ask(workspace, 'say', { text, to: into || to.value })
    },
    tools: session ? [] : [chipSelect('To', to)],
  })
  box.node.dataset.hmz = 'say'
  return {
    node: box.node,
    /** Offers the roles, sessions and people there are to say a line to, keeping the one picked. */
    offers(roles, sessions, working, outworlders) {
      const picked = to.value
      fill(
        to,
        h('option', { value: '' }, 'Next turn'),
        roles.map((role) => h('option', { value: role }, role)),
        sessions.map((key) => h('option', { value: key }, `${key}${working.includes(key) ? ' (working)' : ''}`)),
        outworlders.map((role) => h('option', { value: `outworlder:${role}` }, `${role} (person)`)),
      )
      if ([...to.options].some((option) => option.value === picked)) to.value = picked
    },
  }
}

/** The run's board: a handful of named lines the run and you both write and neither waits on. */
export function board(workspace, items) {
  const lines = h('div', { class: 'board', 'data-hmz': 'board' })
  for (const one of items) {
    const value = h('div', {}, one.value, one.about ? h('div', { class: 'dim' }, one.about) : null, h('div', { class: 'dim mono' }, [one.by, one.whose].filter(Boolean).join(' · ')))
    const edit = h('button', { class: 'btn quiet small', type: 'button' }, 'Edit')
    edit.addEventListener('click', () => {
      const field = h('input', { type: 'text', value: one.value, 'aria-label': `New value of ${one.key}` })
      const form = h('form', { class: 'row' }, field, h('button', { class: 'btn small primary', type: 'submit' }, 'Save'))
      form.addEventListener('submit', async (event) => {
        event.preventDefault()
        try {
          await ask(workspace, 'board', { key: one.key, value: field.value })
        } catch (error) {
          form.append(problem(error))
        }
      })
      fill(value, form)
      field.focus()
    })
    lines.append(
      h(
        'div',
        { class: 'line' },
        h('b', {}, one.key),
        value,
        // A line the flow owns is the flow's to change, as the terminal interface refuses it.
        one.whose === 'flow'
          ? h('span', { class: 'node-tag', title: 'Only the flow changes this line' }, 'Flow')
          : h(
              'span',
              { class: 'row' },
              edit,
              confirming({ label: 'Remove', ask: '', yes: 'Remove', no: 'Cancel', small: true, act: () => ask(workspace, 'board', { key: one.key, value: '' }) }),
            ),
      ),
    )
  }
  const key = h('input', { type: 'text', placeholder: 'Key', 'aria-label': 'Key', size: '12' })
  const value = h('input', { type: 'text', placeholder: 'Value', 'aria-label': 'Value' })
  const adding = h('form', { class: 'row' }, key, value, h('button', { class: 'btn small', type: 'submit' }, 'Add'))
  adding.addEventListener('submit', async (event) => {
    event.preventDefault()
    if (!key.value.trim() || !value.value.trim()) return
    adding.querySelector('.error')?.remove()
    try {
      await ask(workspace, 'board', { key: key.value.trim(), value: value.value })
      key.value = value.value = ''
    } catch (error) {
      adding.append(problem(error))
    }
  })
  return [items.length ? lines : h('p', { class: 'dim' }, 'Nothing is on the board yet.'), adding]
}

/** The roles a person fills: who holds each, and whether anybody is there for it. */
export function outworlders(workspace, roles, { claims, away, me, clients }) {
  const named = Object.fromEntries((clients || []).map((client) => [client.client, client.name || client.client]))
  const everybody = Boolean(away && away.all)
  const rows = roles.map((role) => {
    const holder = claims[role]
    const absent = away && away.of && role in away.of ? away.of[role] : everybody
    const holding = holder === me
    return h(
      'div',
      { class: 'row', 'data-hmz': 'outworlder' },
      h('b', { class: 'mono' }, role),
      h('span', { class: 'dim' }, holder ? (holding ? 'You' : named[holder] || holder) : 'Anyone'),
      holding
        ? acting('Release', () => ask(workspace, 'release', { role }), { kind: 'btn small quiet' })
        : acting(holder ? 'Take over' : 'Claim', () => ask(workspace, 'claim', { role, take: Boolean(holder) }), { kind: 'btn small' }),
      acting(absent ? 'Back' : 'Away', () => ask(workspace, 'afk', { on: !absent, role }), { kind: 'btn small quiet' }),
    )
  })
  const all = acting(everybody ? 'Back for all' : 'Away for all', () => ask(workspace, 'afk', { on: !everybody }), { kind: 'btn small quiet' })
  return [rows, h('p', { class: 'dim' }, 'Away, a question a person is asked is answered at once with nothing, and the epic carries on.'), all]
}

/**
 * Side questions about the run, asked beside it rather than of it, as `/btw` asks them in the
 * terminal interface: of the btw agent, which may ask any one conversation in turn, or of one
 * conversation's read-only side copy. Every question after the first goes on in the same side
 * conversation until they are closed. The server holds them, and what was said in them, so a
 * page opened again reads them back; made once for a page and moved from one drawing of it to
 * the next, so that what is being typed outlives a redraw.
 */
export function asides(workspace, epic = '') {
  const to = h('select', { 'aria-label': 'Ask it of' }, h('option', { value: '' }, 'btw agent'))
  const leave = h('button', { class: 'btn quiet small', type: 'button', hidden: true }, 'Close')
  const log = h('div', { class: 'thread aside-log', 'data-hmz': 'btw-log', role: 'log', 'aria-live': 'polite' })
  const asked = (question, of) => log.append(line('you', question, { who: `btw · ${of || 'btw agent'}` }))
  const answered = (said) => {
    for (const one of said.asked) log.append(line('begins', `asked ${one.to}: ${one.question}`))
    log.append(line('btw', said.answer))
  }
  const box = composer({
    placeholder: 'Ask about the epic',
    label: 'Side question',
    tools: [chipSelect('Ask', to), leave],
    submit: async (question) => {
      asked(question.trim(), to.value)
      try {
        answered(await post('/api/btw', { question: question.trim(), to: to.value, workspace, epic }))
        leave.hidden = false
      } finally {
        log.scrollTop = log.scrollHeight
      }
    },
  })
  box.node.dataset.hmz = 'btw'
  get(`/api/btw?workspace=${encodeURIComponent(workspace)}`).then(({ open, said }) => {
    for (const one of said) {
      asked(one.question, one.to)
      answered(one)
    }
    leave.hidden = !open.length
  }, () => {})
  leave.addEventListener('click', async () => {
    try {
      await post('/api/btw/leave', { workspace })
      log.append(line('ends', 'btw: closed'))
      leave.hidden = true
    } catch (error) {
      log.append(problem(error))
    }
  })
  return {
    node: h('div', { class: 'aside' }, log, box.node),
    /** Offers the conversations there are to ask, keeping the one picked. */
    sessions(keys) {
      const picked = to.value
      fill(to, h('option', { value: '' }, 'btw agent'), keys.map((key) => h('option', { value: key }, key)))
      to.value = keys.includes(picked) ? picked : ''
    },
  }
}
