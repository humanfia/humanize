// What a page does to the run going: answers what it asks, says a line to it, writes its board,
// and holds the roles a person fills -- each one request to the runs, refused with their reason.
// And what it asks beside the run, which never reaches the run at all.

import { post } from './api.js'
import { acting, confirming, fill, h, problem } from './dom.js'
import { ask } from './held.js'
import { line } from './transcript.js'

/** The questions the run is waiting on a person for, each answerable here. */
export function questions(pending, me, clients) {
  return pending.map((one) => {
    const named = Object.fromEntries((clients || []).map((client) => [client.client, client.name || client.client]))
    const theirs = one.owner && one.owner !== me
    const holder = h('div', { class: 'question', 'data-hmz': 'question' }, h('div', { class: 'kicker' }, `${one.role || 'the flow'} asks`), h('div', { class: 'body' }, one.text))
    if (theirs) {
      holder.append(h('p', { class: 'dim' }, `Waiting for ${named[one.owner] || one.owner} to answer: that frontend holds ${one.role}.`))
      return holder
    }
    const options = (one.options || []).map((option, index) =>
      acting(option, () => ask('answer', { question: one.question, text: String(index + 1) }), { kind: 'btn small', busy: 'Answering…' }),
    )
    const typed = h('input', { type: 'text', placeholder: 'Or say an answer', 'aria-label': 'Answer' })
    const form = h('form', { class: 'row' }, typed, h('button', { class: 'btn small primary', type: 'submit' }, 'Answer'))
    form.addEventListener('submit', async (event) => {
      event.preventDefault()
      if (!typed.value.trim()) return
      form.querySelector('.error')?.remove()
      try {
        await ask('answer', { question: one.question, text: typed.value })
        typed.value = ''
      } catch (error) {
        form.append(problem(error))
      }
    })
    if (options.length) holder.append(h('div', { class: 'row' }, options))
    holder.append(form)
    return holder
  })
}

/** Says a line to the run: into one session's turn, to a role, or to the next turn to start. */
export function saying(roles, sessions, working, outworlders) {
  const to = h(
    'select',
    { 'aria-label': 'Say it to' },
    h('option', { value: '' }, 'the next turn'),
    roles.map((role) => h('option', { value: role }, role)),
    sessions.map((key) => h('option', { value: key }, `${key}${working.includes(key) ? ' (working)' : ''}`)),
    outworlders.map((role) => h('option', { value: `outworlder:${role}` }, `${role} (a person)`)),
  )
  const text = h('textarea', { rows: '2', placeholder: 'Say something to the run', 'aria-label': 'What to say' })
  const send = h('button', { class: 'btn primary', type: 'submit' }, 'Say it')
  const form = h('form', { class: 'form', 'data-hmz': 'say' }, text, h('div', { class: 'row' }, h('span', { class: 'kicker' }, 'to'), to, send))
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    if (!text.value.trim()) return
    send.disabled = true
    form.querySelector('.error')?.remove()
    try {
      await ask('say', { text: text.value, to: to.value })
      text.value = ''
    } catch (error) {
      form.append(problem(error))
    } finally {
      send.disabled = false
    }
  })
  text.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) form.requestSubmit()
  })
  return form
}

/** The run's board: a handful of named lines the run and you both write and neither waits on. */
export function board(items) {
  const lines = h('div', { class: 'board', 'data-hmz': 'board' })
  for (const one of items) {
    const value = h('div', {}, one.value, one.about ? h('div', { class: 'dim' }, one.about) : null, h('div', { class: 'dim mono' }, [one.by, one.whose].filter(Boolean).join(' · ')))
    const edit = h('button', { class: 'btn quiet small', type: 'button' }, 'Edit')
    edit.addEventListener('click', () => {
      const field = h('input', { type: 'text', value: one.value, 'aria-label': `New value of ${one.key}` })
      const form = h('form', { class: 'row' }, field, h('button', { class: 'btn small primary', type: 'submit' }, 'Write'))
      form.addEventListener('submit', async (event) => {
        event.preventDefault()
        try {
          await ask('board', { key: one.key, value: field.value })
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
        h(
          'span',
          { class: 'row' },
          edit,
          confirming({ label: 'Remove', ask: '', yes: 'Remove', no: 'Keep', small: true, act: () => ask('board', { key: one.key, value: '' }) }),
        ),
      ),
    )
  }
  const key = h('input', { type: 'text', placeholder: 'name', 'aria-label': 'Name of the new line', size: '12' })
  const value = h('input', { type: 'text', placeholder: 'what it says', 'aria-label': 'What the new line says' })
  const adding = h('form', { class: 'row' }, key, value, h('button', { class: 'btn small', type: 'submit' }, 'Add'))
  adding.addEventListener('submit', async (event) => {
    event.preventDefault()
    if (!key.value.trim() || !value.value.trim()) return
    adding.querySelector('.error')?.remove()
    try {
      await ask('board', { key: key.value.trim(), value: value.value })
      key.value = value.value = ''
    } catch (error) {
      adding.append(problem(error))
    }
  })
  return [items.length ? lines : h('p', { class: 'dim' }, 'Nothing is on the board yet.'), adding]
}

/** The roles a person fills: who holds each, and whether anybody is there for it. */
export function outworlders(roles, { claims, away, me, clients }) {
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
      h('span', { class: 'dim' }, holder ? (holding ? 'you answer it' : `${named[holder] || holder} answers it`) : 'anybody answers it'),
      holding
        ? acting('Let go', () => ask('release', { role }), { kind: 'btn small quiet' })
        : acting(holder ? 'Take it' : 'Answer it here', () => ask('claim', { role, take: Boolean(holder) }), { kind: 'btn small' }),
      acting(absent ? 'I am here' : 'Away', () => ask('afk', { on: !absent, role }), { kind: 'btn small quiet' }),
    )
  })
  const all = acting(everybody ? 'I am back' : 'Away from all of them', () => ask('afk', { on: !everybody }), { kind: 'btn small quiet' })
  return [rows, h('p', { class: 'dim' }, 'Away, a question a person is asked is answered at once with nothing, and the run carries on.'), all]
}

/**
 * Side questions about the run, asked beside it rather than of it, as `/btw` asks them in the
 * terminal interface: of the btw agent, which may ask any one conversation in turn, or of one
 * conversation's read-only side copy. Every question after the first goes on in the same side
 * conversation until they are closed. Made once for a page, and moved from one drawing of it
 * to the next, so that what was asked and what is being typed outlive a redraw.
 */
export function asides() {
  const to = h('select', { 'aria-label': 'Ask it of' }, h('option', { value: '' }, 'the btw agent'))
  const text = h('textarea', { rows: '2', placeholder: 'Ask something about the run', 'aria-label': 'Side question' })
  const send = h('button', { class: 'btn', type: 'submit' }, 'Ask')
  const leave = h('button', { class: 'btn quiet small', type: 'button', hidden: true }, 'Close them')
  const log = h('div', { class: 'transcript', 'data-hmz': 'btw-log', role: 'log', 'aria-live': 'polite' })
  const form = h('form', { class: 'form', 'data-hmz': 'btw' }, log, text, h('div', { class: 'row' }, h('span', { class: 'kicker' }, 'of'), to, send, leave))
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    const question = text.value.trim()
    if (!question || send.disabled) return
    send.disabled = true
    send.textContent = 'Asking…'
    log.append(line('you', question, { who: `btw · ${to.value || 'btw agent'}` }))
    try {
      const answered = await post('/api/btw', { question, to: to.value })
      for (const one of answered.asked) log.append(line('begins', `asked ${one.to}: ${one.question}`))
      log.append(line('btw', answered.answer))
      text.value = ''
      leave.hidden = false
    } catch (error) {
      log.append(problem(error))
    } finally {
      send.disabled = false
      send.textContent = 'Ask'
      log.scrollTop = log.scrollHeight
    }
  })
  text.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) form.requestSubmit()
  })
  leave.addEventListener('click', async () => {
    try {
      await post('/api/btw/leave', {})
      log.append(line('ends', 'btw: closed'))
      leave.hidden = true
    } catch (error) {
      log.append(problem(error))
    }
  })
  return {
    node: form,
    /** Offers the conversations there are to ask, keeping the one picked. */
    sessions(keys) {
      const picked = to.value
      fill(to, h('option', { value: '' }, 'the btw agent'), keys.map((key) => h('option', { value: key }, key)))
      to.value = keys.includes(picked) ? picked : ''
    },
  }
}
