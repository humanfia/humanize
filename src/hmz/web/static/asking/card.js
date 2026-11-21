// A question a run waits on a person for, as a card: what it asks as the headline, what it shows
// beside it under that, and the answer last -- the form its schema asks for, or the options it
// offers and a line to type. A draft outlives a reload; what is answered folds into one line
// saying what was answered; what goes unanswered says why it went; and what another frontend
// holds is shown to be read, waiting for it. A flow that ships a face of its own is answered
// through it, the plain form a button away.

import { fill, h, problem } from '../dom.js'
import { ask, shownTo } from '../held.js'
import { t } from '../i18n.js'
import { blocks } from './blocks.js'
import { schemaForm } from './form.js'
import { keepDraft, oneLine, pruneDrafts, readDraft, refusalErrors, sendLabel, summaryOf, withdrawnWhy, draftable } from './logic.js'

/** Each card drawn, by its node, with what settles it. */
const settlers = new WeakMap()

/** The tokens of the page's look a face is drawn in. */
const TOKENS = ['paper', 'surface', 'raised', 'side', 'ink', 'ink-2', 'ink-3', 'on-ink', 'line', 'line-strong', 'hover', 'green', 'pink', 'pink-ink', 'cyan', 'cyan-ink', 'lavender', 'gold', 'live', 'link', 'done', 'fail', 'budget', 'primary', 'on-primary', 'field', 'edge', 'control', 'control-ink', 'selected', 'quiet', 'track', 'thumb', 'sans', 'mono']

pruneDrafts()

/** Whether a key pressed there is typed rather than meant as a shortcut. */
function typing(target) {
  if (!(target instanceof Element)) return false
  if (target.isContentEditable || target.closest('textarea, select')) return true
  const input = target.closest('input')
  return Boolean(input) && !['button', 'checkbox', 'radio', 'submit', 'reset'].includes(input.type)
}

/**
 * One question's card.
 *
 * @param {string|{workspace: string, slot: string}} where The host the question is of.
 * @param {object} one The question, as `pending` lists it.
 * @param {string} me This frontend.
 * @param {object[]} [clients] The frontends attached, to name the one holding it.
 * @returns {HTMLElement}
 */
export function questionCard(where, one, me, clients) {
  const named = Object.fromEntries((clients || []).map((client) => [client.client, client.name || client.client]))
  const promptId = `ask-prompt-${String(one.question).replace(/[^\w-]/g, '_')}`
  const schema = one.schema && typeof one.schema === 'object' ? one.schema : null
  const held = Boolean(one.owner && one.owner !== me)
  const node = h('section', { class: ['question', 'ask-card', 'ask-new', held && 'is-held'], 'data-hmz': 'question', 'data-question': String(one.question), 'aria-labelledby': promptId })
  const kicker = h('div', { class: 'kicker ask-kicker' }, h('span', {}, one.role ? t('{role} asks', { role: one.role }) : t('the flow asks')))
  const prompt = h('div', { class: 'body ask-prompt', id: promptId, 'data-hmz': 'ask-prompt' }, one.text || '')
  // On a card, only the first block is open: the rest wait behind what they hold, one line each.
  const context = blocks(one.context, { open: (one.context || []).map((_, at) => at === 0) })
  const answer = h('div', { class: 'ask-answer' })
  node.append(kicker, prompt, context || '', answer)
  // The highlight a new card arrives with fades on its own: nothing goes on calling.
  setTimeout(() => node.classList.remove('ask-new'), 2400)

  let settled = false
  /** Folds the card into one line: what was answered, or why it went unanswered. */
  function settle(outcome) {
    if (settled) return
    settled = true
    keepDraft(draftOf(where, one), undefined)
    const answered = outcome.answered
    const said = answered ? summaryOfAnswer(answered, schema) : ''
    const mine = answered && (outcome.mine || answered.client === me)
    const words = answered
      ? mine
        ? t('You answered: {said}', { said })
        : t('{who} answered: {said}', { who: answered.by || named[answered.client] || t('Someone'), said })
      : t('Withdrawn: {why}', { why: withdrawnWhy(outcome.withdrawn, one.role) })
    node.classList.remove('ask-new', 'is-held')
    node.classList.add('ask-settled', answered ? 'is-answered' : 'is-withdrawn')
    const dismiss = h('button', { type: 'button', class: 'icon-btn ask-dismiss', 'aria-label': t('Dismiss'), title: t('Dismiss'), 'data-hmz': 'ask-dismiss', onclick: () => node.remove() }, '×')
    fill(
      node,
      h(
        'div',
        { class: 'ask-closed', role: 'status', 'data-hmz': 'ask-closed' },
        h('span', { class: 'ask-closed-mark', 'aria-hidden': 'true' }, answered ? '✓' : '–'),
        h('div', { class: 'ask-closed-text' }, h('div', { class: 'ask-closed-said', 'data-hmz': 'ask-closed-said' }, words), h('div', { class: 'ask-closed-asked dim' }, oneLine(one.text, 100))),
        dismiss,
      ),
    )
  }
  settlers.set(node, settle)

  if (held) {
    // Held by another: read, never filled, while it waits for them.
    answer.append(h('p', { class: 'ask-held', 'data-hmz': 'ask-held', role: 'status' }, h('span', { class: 'ask-wait', 'aria-hidden': 'true' }, '●'), t('Waiting for {who} to answer: that frontend holds {role}.', { who: named[one.owner] || one.owner, role: one.role })))
    if (schema) answer.append(schemaForm(schema, { disabled: true, prefix: 'held' }).node)
    else if ((one.options || []).length) answer.append(h('div', { class: 'ask-options row' }, one.options.map((option) => h('button', { type: 'button', class: 'btn small', disabled: true }, option))))
    return node
  }

  const sending = schema ? schemaAnswer(where, one, schema, settle) : textAnswer(where, one, settle)
  if (one.face && (one.face.hash || typeof one.face === 'string')) faced(where, one, context, answer, sending, settle)
  else answer.append(sending.node)
  node.addEventListener('keydown', (event) => {
    if (settled) return
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault()
      sending.submit()
      return
    }
    // A number picks a choice, where nothing is being typed.
    if (/^[1-9]$/.test(event.key) && !event.metaKey && !event.ctrlKey && !event.altKey && !typing(event.target)) {
      if (sending.pick(Number(event.key), event.target)) event.preventDefault()
    }
  })
  return node
}

/** What a question's draft is kept by: its host and run as well, as each host counts its questions from one. */
function draftOf(where, one) {
  const host = typeof where === 'string' ? where : `${where.workspace}\n${where.slot || ''}`
  return `${host}\n${one.run || ''}\n${one.question}`
}

/**
 * Settles a card drawn by `questionCard`: answered (`{answered, mine}`), withdrawn
 * (`{withdrawn}`), or, given `{leaving: true}`, no longer answerable while what became of it is
 * not yet known.
 */
export function settle(node, outcome) {
  if (outcome.leaving) {
    if (node.classList.contains('ask-settled')) return
    node.classList.add('is-leaving')
    node.inert = true
    return
  }
  node.inert = false
  const settler = settlers.get(node)
  if (settler) settler(outcome)
}

/** What was answered, in one line: a schema's answer as its fields, text as it was said. */
function summaryOfAnswer(answered, schema) {
  if ('value' in answered) return summaryOf(answered.value, schema)
  const text = String(answered.text ?? '')
  if (schema) {
    try {
      return summaryOf(JSON.parse(text), schema)
    } catch {
      // Said as it was.
    }
  }
  return `‘${oneLine(text, 80)}’`
}

/** A draft kept, said quietly: that it was kept, or brought back. */
function draftNote() {
  const note = h('span', { class: 'ask-draft dim', 'data-hmz': 'ask-draft', 'aria-live': 'polite' })
  let timer = 0
  return {
    note,
    say(text) {
      note.textContent = text
      clearTimeout(timer)
      timer = setTimeout(() => (note.textContent = ''), 2500)
    },
  }
}

/** The shortcut that sends, as this system says it. */
function sendKeys() {
  return /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? '⌘↵' : 'Ctrl+↵'
}

/** A whole form, sent as one value once it fits. */
function schemaAnswer(where, one, schema, settle) {
  const draft = readDraft(draftOf(where, one))
  const kept = draftNote()
  let timer = 0
  const form = schemaForm(schema, {
    value: draft,
    prefix: `ask-${String(one.question).replace(/[^\w-]/g, '_')}`,
    changed: (value) => {
      progress()
      clearTimeout(timer)
      timer = setTimeout(() => {
        keepDraft(draftOf(where, one), draftable(value, schema))
        kept.say(t('Draft kept'))
      }, 400)
    },
  })
  const button = h('button', { type: 'submit', class: 'btn primary ask-send', 'data-hmz': 'ask-send' })
  const said = h('div', { class: 'ask-said' })
  const node = h(
    'form',
    { class: 'ask-form', 'data-hmz': 'ask-form', novalidate: true },
    form.node,
    said,
    h('div', { class: 'ask-foot' }, button, h('span', { class: 'ask-keys dim', 'aria-hidden': 'true' }, sendKeys()), kept.note),
  )
  function progress() {
    if (button.disabled) return
    const left = form.left()
    button.textContent = sendLabel(left)
    button.classList.toggle('is-left', left > 0)
  }
  progress()
  if (draft !== undefined) kept.say(t('Draft restored'))

  let busy = false
  async function submit() {
    if (busy) return
    fill(said)
    const errors = form.check()
    if (errors.length) {
      form.show(errors)
      form.focusFirst()
      return
    }
    const value = form.read()
    busy = button.disabled = true
    button.textContent = t('Answering…')
    try {
      await ask(where, 'answer', { question: one.question, value })
      clearTimeout(timer)
      settle({ answered: { value }, mine: true })
    } catch (error) {
      const mapped = refusalErrors(error)
      if (mapped.length) {
        form.show(mapped)
        said.append(h('p', { class: 'problem', role: 'alert' }, mapped.length === 1 ? t('One answer needs another look.') : t('{n} answers need another look.', { n: mapped.length })))
        form.focusFirst()
      } else said.append(problem(error))
    } finally {
      busy = button.disabled = false
      progress()
    }
  }
  node.addEventListener('submit', (event) => {
    event.preventDefault()
    submit()
  })
  return { node, submit, pick: (n, target) => form.pick(n, target) }
}

/** A question in words: the options it offers, each picked by its number, and a line to type. */
function textAnswer(where, one, settle) {
  const options = one.options || []
  const answering = async (text, said) => {
    await ask(where, 'answer', { question: one.question, text })
    settle({ answered: { text: said }, mine: true })
  }
  const said = h('div', { class: 'ask-said' })
  const buttons = options.map((option, at) => {
    const button = h('button', { type: 'button', class: 'btn small ask-option', 'data-hmz': 'ask-option' }, at < 9 ? h('kbd', { class: 'ask-key', 'aria-hidden': 'true' }, String(at + 1)) : null, h('span', {}, option))
    button.addEventListener('click', async () => {
      if (button.disabled) return
      fill(said)
      const was = [...button.childNodes]
      for (const each of buttons) each.disabled = true
      fill(button, t('Answering…'))
      try {
        // Sent as itself: a number is taken as a place only where it is no option of its own.
        await answering(option, option)
      } catch (error) {
        said.append(problem(error))
      } finally {
        for (const each of buttons) each.disabled = false
        fill(button, was)
      }
    })
    return button
  })
  const draft = readDraft(draftOf(where, one))
  const typed = h('input', { type: 'text', placeholder: options.length ? t('Or say something else') : t('Your answer'), 'aria-label': t('Answer'), 'data-hmz': 'ask-text', value: typeof draft === 'string' ? draft : '' })
  let timer = 0
  typed.addEventListener('input', () => {
    clearTimeout(timer)
    timer = setTimeout(() => keepDraft(draftOf(where, one), typed.value || undefined), 400)
  })
  const send = h('button', { class: 'btn small primary', type: 'submit' }, t('Answer'))
  const form = h('form', { class: 'row ask-line' }, typed, send)
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    if (send.disabled || !typed.value.trim()) {
      typed.focus()
      return
    }
    fill(said)
    send.disabled = true
    send.textContent = t('Answering…')
    try {
      clearTimeout(timer)
      await answering(typed.value, typed.value)
      typed.value = ''
    } catch (error) {
      said.append(problem(error))
    } finally {
      send.disabled = false
      send.textContent = t('Answer')
    }
  })
  const node = h('div', { class: 'ask-text-answer' }, buttons.length ? h('div', { class: 'row ask-options', role: 'group', 'aria-label': t('Answers offered') }, buttons) : null, form, said)
  return {
    node,
    submit: () => form.requestSubmit(),
    pick(n) {
      const button = buttons[n - 1]
      if (!button || button.disabled) return false
      button.focus()
      button.click()
      return true
    },
  }
}

/** The page's look, as the tokens a face is drawn in. */
function themeTokens() {
  const style = getComputedStyle(document.documentElement)
  const tokens = Object.fromEntries(TOKENS.map((name) => [`--${name}`, style.getPropertyValue(`--${name}`).trim()]))
  return { ...tokens, scheme: document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light' }
}

/**
 * A question answered through the flow's own face, mounted by the page's face host: the plain
 * form a button away, and the plain form alone where the face cannot be shown.
 */
function faced(where, one, context, answer, sending, settle) {
  const plain = h('div', { class: 'ask-plain-form', hidden: true }, sending.node)
  const frame = h('div', { class: 'ask-face', 'data-hmz': 'ask-face', 'aria-busy': 'true' }, h('p', { class: 'loading dim', role: 'status' }, one.face && one.face.title ? t('Opening {name}…', { name: one.face.title }) : t('Opening the flow’s view…')))
  const note = h('p', { class: 'dim ask-face-note', hidden: true })
  let failed = false
  // The face host draws the one switch between the face and the plain form, and says when
  // the plain form is to be shown: chosen, or because the face failed or never answered.
  // The face is handed the context itself: the card's own blocks stand only beside the
  // plain form, so that nothing is drawn twice.
  const showPlain = (yes) => {
    plain.hidden = !yes
    if (context) context.hidden = !yes
  }
  showPlain(false)
  const fallBack = (why) => {
    if (failed) return
    failed = true
    frame.remove()
    note.hidden = false
    note.textContent = why ? t('The flow’s own view could not open ({why}); here is the plain form.', { why }) : t('The flow’s own view could not open; here is the plain form.')
    showPlain(true)
  }
  answer.append(frame, note, plain)
  // What the session was shown before this card was drawn, read now: what comes later is
  // handed to the mounted face as it comes.
  const shown = shownTo(where, one.session)
  import('../faces/host.js')
    .then(async ({ mountFace }) => {
      const mounted = await mountFace(one, {
        fetchFace: (hash) => ask(where, 'face', { hash }),
        submit: async (value) => {
          try {
            await ask(where, 'answer', { question: one.question, value })
            settle({ answered: { value }, mine: true })
            return { ok: true }
          } catch (error) {
            const errors = refusalErrors(error)
            return { ok: false, errors: errors.length ? errors : [{ path: [], message: error.message || String(error) }] }
          }
        },
        theme: themeTokens(),
        plain: (on) => showPlain(on),
        shown,
        where,
      })
      if (!(mounted instanceof Node)) throw new Error(t('no view'))
      if (failed) return
      frame.removeAttribute('aria-busy')
      fill(frame, mounted)
    })
    .catch((error) => fallBack((error && error.message) || String(error || '')))
}
