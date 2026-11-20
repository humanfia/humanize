// What a page does to the run going: answers what it asks, says a line to it, writes its board,
// and holds the roles a person fills -- each one request to the runs, refused with their reason.
// And what it asks of one conversation's side copy, beside the run, which never reaches the run.

import { call } from './api.js'
import { confirming } from './confirm.js'
import { acting, fill, h, headline, icon, problem } from './dom.js'
import { ask } from './held.js'
import { t } from './i18n.js'
import { chipSelect, composer } from './composer.js'
import { choice, menu, section, submenu } from './shell.js'
import { line } from './transcript.js'
import { questionCard } from './asking/card.js'

/**
 * Sends a form once at a time, once it is ready to: its button says it is busy and takes no
 * second press until the reply, and a refusal is said under it.
 */
function sending(form, busy, act, ready = () => true) {
  const button = form.querySelector('button[type=submit]')
  const label = button.textContent
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    if (button.disabled || !ready()) return
    form.querySelector('.error')?.remove()
    button.disabled = true
    button.textContent = busy
    try {
      await act()
    } catch (error) {
      form.append(problem(error))
    } finally {
      button.disabled = false
      button.textContent = label
    }
  })
}

/**
 * One question the run is waiting on a person for, answerable here unless another holds it: its
 * card, as `asking/card.js` draws it -- the whole form its schema asks for, or the options it
 * offers and a line to type.
 */
export function question(workspace, one, me, clients) {
  return questionCard(workspace, one, me, clients)
}

/**
 * Says a line to the run: into one session's turn, to an agent, or to the next turn to start --
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
    /** Offers the agents, by name, sessions and people there are to say a line to, keeping the one picked. */
    offers(agents, sessions, working, outworlders) {
      const picked = to.value
      fill(
        to,
        h('option', { value: '' }, 'Next turn'),
        agents.map((name) => h('option', { value: name }, name)),
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
      sending(form, 'Saving…', () => ask(workspace, 'board', { key: one.key, value: field.value }))
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
  sending(
    adding,
    'Adding…',
    async () => {
      await ask(workspace, 'board', { key: key.value.trim(), value: value.value })
      key.value = value.value = ''
    },
    () => key.value.trim() && value.value.trim(),
  )
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

/** What the control that picks an aside's conversation says until one is picked. */
const UNPICKED = 'Pick a conversation'

/** How often an aside answering is read again, in milliseconds. */
const WATCHED = 1000

/**
 * Side questions about the run, asked beside it rather than of it, as `/btw` asks them in the
 * terminal interface: several asides, each a side conversation of its own, picked between on a
 * strip, and a new one opened from it. An aside asks one conversation's read-only side copy,
 * whose agent is that conversation's own, for good: the conversation is picked before its first
 * question, from a menu laid out as the epic is, each agent with the role it fills opening onto
 * its conversations, newest first; typing in it narrows it to the conversations that match.
 * While one answers it says so. The server holds them, and what was said in them, so a page
 * opened again reads them back; made once for a page and moved from one drawing of it to the
 * next, so that what is being typed outlives a redraw.
 */
export function asides(workspace, epic = '', { chat = false } = {}) {
  /** What an aside not yet asked is called: beside a chat, in a chat's words. */
  const unasked = chat ? 'New question' : 'New aside'
  /** The epic's agents: `{name, role, sessions: [{key, about}]}`, as its graph has them. */
  let agents = []
  /** Every aside, in the order opened: the one not yet asked, if any, last. */
  const all = []
  let shown = null
  let watching = null
  /** How many times an aside here has changed, by which a reading begun before is stale. */
  let changed = 0
  let reading = null
  const strip = h('div', { class: 'aside-strip', 'data-hmz': 'btw-asides' })
  const body = h('div', { class: 'aside-body' })
  const fresh = h('button', { class: 'chip-btn', type: 'button', 'data-hmz': 'btw-new' }, icon('plus'), unasked)
  // A chat is named by its id as `chat`, an epic by its name as `epic`.
  const about = epic ? { [chat ? 'chat' : 'epic']: epic } : {}
  const query = { workspace, ...about }

  /** One aside: `to` is null until its first question fixes the conversation it asks. */
  function aside(id, to = null) {
    const one = { id, to, said: [], question: '', posting: false }
    let target = ''
    const named = h('span', { class: 'chip-value' })
    const tab = h('button', { class: 'chip-btn aside-tab', type: 'button', 'data-hmz': 'btw-tab', onclick: () => show(one) }, h('span', { class: 'aside-dot', 'aria-hidden': 'true' }), named)
    const leave = h('button', { class: 'btn quiet small', type: 'button', 'data-hmz': 'btw-close' }, 'Close')
    const log = h('div', { class: 'thread aside-log', 'data-hmz': 'btw-log', role: 'log', 'aria-live': 'polite' })
    const picked = h('span', { class: 'chip-value' }, UNPICKED)
    const picker = h('button', { class: 'chip-btn ask-to', type: 'button', 'aria-label': 'Ask it of', 'data-hmz': 'btw-to' }, h('span', { class: 'chip-label' }, 'Ask'), picked, icon('down'))
    const pick = (key) => {
      target = key
      picked.textContent = key || UNPICKED
      picker.dataset.value = key
    }
    const box = composer({
      placeholder: chat ? 'Ask a side question' : 'Ask about the epic',
      label: 'Side question',
      submit: async (question) => {
        // A chat is one conversation, and is asked about as that: the last it opened, unpicked.
        if (one.to === null && chat) target = agents.flatMap((agent) => agent.sessions).at(-1)?.key || ''
        if (one.to === null && !target) throw new Error(chat ? t('This chat has said nothing to ask about yet.') : 'Pick the conversation to ask first.')
        if (one.to === null) one.to = target
        Object.assign(one, { question: question.trim(), posting: true })
        changed += 1
        tabs()
        watch()
        try {
          one.said = [...one.said, await call('btw.ask', { question: question.trim(), aside: id, to: one.to, workspace, ...about })]
        } finally {
          Object.assign(one, { question: '', posting: false })
          changed += 1
          tabs()
          // Read again: one refused before it opened has its conversation still to pick, and
          // one answering on another page is drawn answering here.
          reread()
        }
      },
    })
    box.node.dataset.hmz = 'btw'
    // The menu opens clear of the box under its button: what is typed there stays in sight.
    menu(picker, (close) => whom(target, close, pick), { by: box.node, label: 'Ask it of' })
    const node = h('div', { class: 'aside-one', 'data-hmz': 'btw-aside' }, h('div', { class: 'aside-head' }, leave), log, h('div', { class: 'aside-to' }, picker), box.node)
    leave.addEventListener('click', async () => {
      leave.disabled = true
      leave.textContent = 'Closing…'
      try {
        await call('btw.leave', { workspace, aside: id })
        forget(one)
      } catch (error) {
        box.said.replaceChildren(problem(error))
        leave.disabled = false
        leave.textContent = 'Close'
      }
    })
    let was = ''
    const draw = () => {
      // Beside a chat no session is named: an aside goes by what it first asked.
      const who = chat ? '' : one.to === null ? unasked : `btw · ${one.to}`
      named.textContent = !chat ? who : one.to === null ? unasked : headline(one.said[0]?.question || one.question || t('Side question'))
      tab.classList.toggle('busy', Boolean(one.question))
      tab.setAttribute('aria-pressed', String(shown === one))
      leave.hidden = one.to === null
      picker.parentElement.hidden = chat || one.to !== null
      if (!one.posting) box.send.disabled = Boolean(one.question)
      const now = JSON.stringify([one.to, one.said, one.question])
      if (now === was) return
      was = now
      fill(
        log,
        one.said.map((said) => [line('you', said.question, { who }), line('btw', said.answer)]),
        one.question
          ? [
              line('you', one.question, { who }),
              h('div', { class: 'aside-working', 'data-hmz': 'btw-working', role: 'status' }, h('span', { class: 'aside-dot', 'aria-hidden': 'true' }), chat ? t('Thinking…') : `${one.to} is thinking…`),
            ]
          : null,
      )
      log.scrollTop = log.scrollHeight
    }
    Object.assign(one, {
      tab,
      node,
      draw,
      /** Whether nothing was picked for it, nor typed in it. */
      untouched: () => one.to === null && !target && !box.text.value,
      /** Lets go of the conversation picked where it is no longer of the epic. */
      offered: () => !chat && target && !agents.some((agent) => agent.sessions.some((session) => session.key === target)) && pick(''),
    })
    return one
  }

  /** The menu of whom an aside asks: each agent, opening its conversations. */
  function whom(target, close, pick) {
    const conversation = (agent, one) => choice({ label: one.key, about: [agent.role, one.about].filter(Boolean).join(' · '), chosen: one.key === target, act: () => pick(one.key), close })
    const newest = (agent) => [...agent.sessions].reverse()
    const laid = () =>
      agents.length
        ? [
            section('Conversations'),
            ...agents.map((agent) =>
              submenu({ label: agent.name, glyph: 'agent', about: [agent.role, `${agent.sessions.length}`].filter(Boolean).join(' · '), hmz: 'btw-agent', items: () => newest(agent).map((one) => conversation(agent, one)) }),
            ),
          ]
        : h('p', { class: 'dim ask-none' }, 'No conversation has opened yet.')
    const list = h('div', { class: 'ask-list' }, laid())
    const narrow = h('input', { class: 'menu-filter', type: 'search', placeholder: 'Find whom to ask', 'aria-label': 'Find whom to ask', 'data-hmz': 'btw-find' })
    narrow.addEventListener('input', () => {
      const wanted = narrow.value.trim().toLowerCase()
      if (!wanted) return fill(list, laid())
      const found = agents.flatMap((agent) => newest(agent).filter((one) => [agent.name, agent.role, one.key, one.about].some((said) => String(said || '').toLowerCase().includes(wanted))).map((one) => conversation(agent, one)))
      fill(list, found.length ? found : h('p', { class: 'dim ask-none' }, 'Nobody matches.'))
    })
    return [narrow, list]
  }

  /** The strip: each aside's tab, and a new one's where every one has been asked. */
  function tabs() {
    const wanted = [...all.map((each) => each.tab), ...(all.some((each) => each.to === null) ? [] : [fresh])]
    // Drawn again only where they changed: what is focused is left where it is.
    if (wanted.length !== strip.children.length || wanted.some((tab, at) => strip.children[at] !== tab)) fill(strip, wanted)
    for (const each of all) each.draw()
  }

  /** Shows one aside. */
  function show(one) {
    shown = one
    tabs()
    if (body.firstChild !== one.node) fill(body, one.node)
  }

  /** The aside not yet asked, opened if there is none. */
  function opened() {
    let one = all.find((each) => each.to === null)
    if (!one) all.push((one = aside(`${Date.now().toString(36)}${Math.random().toString(36).slice(2, 8)}`)))
    return one
  }

  /** Lets go of an aside closed, showing the last one left. */
  function forget(one) {
    all.splice(all.indexOf(one), 1)
    show(shown === one || !all.includes(shown) ? all.at(-1) || opened() : shown)
  }

  /** Reads the asides as the server holds them: what was said, and what is answering now. */
  async function read() {
    const at = changed
    const { asides: held } = await call('btw.list', query)
    // Read before an aside here changed: what it says of it is older than what is shown.
    if (at !== changed) return read()
    for (const kept of held) {
      let one = all.find((each) => each.id === kept.aside)
      if (!one) {
        const unasked = all.findIndex((each) => each.to === null)
        all.splice(unasked < 0 ? all.length : unasked, 0, (one = aside(kept.aside, kept.to)))
      }
      if (!one.posting) Object.assign(one, { to: kept.to, said: kept.said, question: kept.question })
    }
    for (const one of all.filter((each) => each.to !== null && !each.posting && !held.some((kept) => kept.aside === each.id))) {
      // One answered here that the server holds no more was closed: by another page, or an epic
      // starting. One never answered was never opened: its conversation is still to pick.
      if (one.said.length) forget(one)
      else one.to = null
    }
    show(all.includes(shown) ? shown : all.at(-1))
  }

  /** Reads them again, once at a time. */
  function reread() {
    reading ||= read()
      .catch(() => {})
      .finally(() => {
        reading = null
        watch()
      })
  }

  /** Reads them again every second while any one answers, and stops once none does. */
  function watch() {
    if (watching) return
    watching = setInterval(() => {
      if (!all.some((one) => one.question)) {
        clearInterval(watching)
        watching = null
        return
      }
      reread()
    }, WATCHED)
  }

  fresh.addEventListener('click', () => show(opened()))
  show(opened())
  // Opened again on what was asked before, rather than on a new one.
  read().then(() => {
    if (all.length > 1 && shown.untouched()) forget(shown)
    watch()
  }, () => {})
  return {
    node: h('div', { class: 'aside' }, strip, body),
    /** Offers the epic's agents and their conversations to ask, keeping the one picked. */
    sessions(given) {
      agents = given
      for (const one of all) if (one.to === null) one.offered()
    },
  }
}
