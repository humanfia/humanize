// A form read off a JSON schema, as a person fills it in: a field for each property, in the order
// they read -- what must be said first, what has a suggestion folded under "More options" --
// each drawn by its type: a few choices as buttons side by side, many as a list to search, a
// yes or no as two worded buttons, numbers, text on one line or several, a list to add to and
// take from, and an object as the fields it holds. Nothing is checked while it is typed: a field
// is checked once it is left, and the whole once it is sent, each problem said in plain words
// beside the field it is of. The same form asks a flow's params on a new epic.

import { h } from '../dom.js'
import { t } from '../i18n.js'
import { blank, choicesOf, FEW, fieldsOf, kindOf, labelOf, multiline, paramLabel, pathKey, problems, requiredLeft, resolved, sentAs, untouched, widgetOf, yesNo } from './logic.js'
import { markdownInto } from './blocks.js'

/** How many fields a form shows before those with a suggestion fold away. */
const FOLDS_PAST = 3

let made = 0

/**
 * A form for a schema.
 *
 * @param {object} schema The JSON schema of the value asked for: an object's, or any other.
 * @param {object} [options]
 * @param {any} [options.value] What it is filled with first: a draft, or what was kept.
 * @param {string} [options.prefix] What its fields' ids start with.
 * @param {boolean} [options.fold] Whether fields with a suggestion fold under "More options".
 * @param {boolean} [options.keyed] Whether a field without a title is named by its key as it is written.
 * @param {(value: any) => void} [options.changed] Told the value whenever a field changes.
 * @param {boolean} [options.disabled] Drawn to be read, not filled.
 */
export function schemaForm(schema, { value, prefix = 'ask', fold = true, changed = () => {}, disabled = false, keyed = false } = {}) {
  const root = schema || {}
  const ctx = { root, prefix: `${prefix}-${++made}`, boxes: new Map(), choices: [], changed: () => changed(read()), disabled, keyed, ids: 0 }
  const top = resolved(root, root).node
  let control
  let fields = []
  if (kindOf(top) === 'object') {
    control = objectControl([], top, value && typeof value === 'object' ? value : {}, ctx, { fold, flat: true })
    fields = control.fields
  } else {
    // A value that is not an object is asked as one field, named by its title.
    const field = { name: top.title || t('answer'), node: top, nullable: false, required: true, suggested: 'default' in top, value: top.default }
    control = fieldControl([], field, value === undefined ? top.default : value, ctx)
    fields = [control.box]
  }
  const node = h('div', { class: 'ask-fields', 'data-hmz': 'ask-fields' }, fields)
  const general = h('p', { class: 'problem ask-general', role: 'alert', hidden: true })
  node.append(general)

  function read() {
    return control.read()
  }

  /** Every problem with what is filled in now: what could not be read, then what does not fit. */
  function check() {
    const value = read()
    const local = [...ctx.boxes.values()].flatMap((box) => (box.local ? box.local().map((message) => ({ path: box.path, message })) : []))
    const bad = new Set(local.map((one) => pathKey(one.path)))
    return [...local, ...problems(root, value, root).filter((one) => !bad.has(pathKey(one.path)))]
  }

  /** The box a problem at `path` is said in: its own, or the nearest one holding it. */
  function boxOf(path) {
    for (let n = path.length; n >= 0; n--) {
      const box = ctx.boxes.get(pathKey(path.slice(0, n)))
      if (box && box.problem) return box
    }
    return null
  }

  /** Says each problem beside its field, and nothing beside the rest; `only` limits it to some. */
  function show(errors, only = null) {
    const said = new Map()
    let elsewhere = []
    for (const one of errors) {
      const box = boxOf(one.path || [])
      if (!box) elsewhere.push(one.message)
      else if (!said.has(box)) said.set(box, one.message)
    }
    for (const box of ctx.boxes.values()) {
      if (!box.problem || (only && !only(box))) continue
      box.say(said.get(box) || '')
    }
    if (!only) {
      general.hidden = !elsewhere.length
      general.textContent = elsewhere.join(' ')
    }
    // A problem folded away is unfolded, so that it is seen.
    for (const box of said.keys()) box.el.closest('details.ask-more')?.setAttribute('open', '')
    return said
  }

  /** Puts the cursor in the first field with a problem, in reading order. */
  function focusFirst() {
    const first = [...ctx.boxes.values()].find((box) => box.problem && !box.problem.hidden)
    if (first) {
      first.el.closest('details.ask-more')?.setAttribute('open', '')
      first.focus()
      first.el.scrollIntoView?.({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
      return true
    }
    if (!general.hidden) general.scrollIntoView?.({ block: 'nearest' })
    return false
  }

  // A field left is checked once something was said in it: one passed by untouched is not told
  // it is missing until the whole is sent, nor told it no longer is.
  node.addEventListener('focusout', (event) => {
    // The innermost field it was in: a field's own are set down before it is.
    const box = [...ctx.boxes.values()].find((one) => one.problem && one.el.contains(event.target))
    if (!box || !box.touched || (event.relatedTarget && box.el.contains(event.relatedTarget))) return
    show(check(), (one) => one === box || box.el.contains(one.el))
  })

  return {
    node,
    fields,
    read,
    check,
    show,
    focusFirst,
    /** How many required fields are still blank. */
    left: () => requiredLeft(root, read(), root),
    /** Picks the `n`th choice of the choice group holding `target`, or of the first; true where one was. */
    pick(n, target = null) {
      const groups = ctx.choices.filter((one) => one.el.isConnected)
      const group = groups.find((one) => target && one.el.contains(target)) || groups[0]
      return group ? group.pick(n) : false
    },
  }
}

/**
 * A flow's params as a new epic asks them: every field in reading order, none folded, and read
 * as what was said, leaving out what was not. What cannot be read is thrown, by its field.
 */
export function paramsForm(schema, kept = {}) {
  const given = schema && Object.keys(schema.properties || {}).length ? schema : { type: 'object', properties: {} }
  const form = schemaForm(given, { value: kept, prefix: 'param', fold: false, keyed: true })
  return {
    fields: form.fields,
    read() {
      // What could not be read at all, in the words it is said in.
      const unread = [t('This is not valid JSON.'), t('This needs a number.'), t('This needs a whole number.')]
      const bad = form.check().find((one) => unread.includes(one.message))
      if (bad) throw new Error(`${paramLabel(bad.path[0] ?? 'value', given.properties[bad.path[0]])}: ${bad.message}`)
      const said = form.read() || {}
      return Object.fromEntries(Object.entries(said).filter(([, one]) => one !== null && one !== '' && one !== undefined))
    },
  }
}

// ------------------------------------------------------------------ fields

function idOf(ctx) {
  return `${ctx.prefix}-${++ctx.ids}`
}

/** One field: its label, whether it is optional or suggested, its control, its hint and its problem. */
function fieldControl(path, field, value, ctx) {
  const id = idOf(ctx)
  const label = ctx.keyed ? paramLabel(field.name, field.node) : labelOf(field.name, field.node)
  // A param named by its title still tells its key, which is what `-p` takes.
  const key = ctx.keyed && label !== field.name ? field.name : undefined
  const hintId = `${id}-hint`
  const problemId = `${id}-problem`
  const kind = kindOf(field.node)
  const description = String(field.node.description || '').trim()
  // A yes or no is worded from its description: said twice it says nothing more.
  const hint = description && !(kind === 'boolean' && yesNo(field.name, field.node).yes.toLowerCase().includes(description.replace(/[.!?]+$/, '').toLowerCase())) ? description : ''
  const describedBy = [hint && hintId, problemId].filter(Boolean).join(' ')
  const inner = controlFor(path, field, value, ctx, { id, label, describedBy })
  const suggested = field.suggested && !blank(field.value) ? h('span', { class: 'ask-tag ask-suggested', 'data-hmz': 'suggested', title: t('Filled in with what the flow suggests') }, t('suggested')) : null
  const optional = !field.required && !field.suggested ? h('span', { class: 'ask-tag' }, t('optional')) : null
  const labelled = inner.group
    ? h('span', { class: 'ask-label', id: `${id}-label`, title: key }, label)
    : h('label', { class: 'ask-label', for: id, id: `${id}-label`, title: key }, label)
  const problem = h('p', { class: 'problem', id: problemId, hidden: true, 'aria-live': 'polite' })
  const box = h(
    'div',
    { class: ['field', 'ask-field', `ask-kind-${kind}`], 'data-hmz': 'ask-field', 'data-path': pathKey(path) },
    h('div', { class: 'ask-label-row' }, labelled, suggested, optional),
    hint ? h('span', { class: 'hint', id: hintId }, hint) : null,
    inner.el,
    problem,
  )
  const entry = {
    el: box,
    path,
    problem,
    touched: false,
    local: inner.local,
    focus: () => inner.focus(),
    say(message) {
      problem.hidden = !message
      problem.textContent = message
      box.classList.toggle('has-problem', Boolean(message))
      for (const one of box.querySelectorAll(`[aria-describedby~="${problemId}"]`)) {
        if (message) one.setAttribute('aria-invalid', 'true')
        else one.removeAttribute('aria-invalid')
      }
    },
  }
  ctx.boxes.set(pathKey(path), entry)
  // What is being changed is no longer told it is wrong: it is checked again once it is left.
  const edited = () => {
    entry.touched = true
    if (!problem.hidden) entry.say('')
    if (suggested) suggested.hidden = !same(inner.read(), field.value)
    ctx.changed()
  }
  box.addEventListener('input', edited)
  box.addEventListener('hmz-change', edited)
  if (suggested) suggested.hidden = !same(inner.read(), field.value)
  return { box, read: inner.read }
}

function same(a, b) {
  return JSON.stringify(a) === JSON.stringify(b)
}

/** Tells the field a control is in that it changed, as typing into a field does. */
function changedIn(el) {
  el.dispatchEvent(new CustomEvent('hmz-change', { bubbles: true }))
}

/** The control a field is filled in with, by its type, read as it is answered. */
function controlFor(path, field, value, ctx, said) {
  const control = controlOf(path, field, value, ctx, said)
  return { ...control, read: () => sentAs(field, control.read()) }
}

function controlOf(path, field, value, ctx, said) {
  const node = field.node
  switch (kindOf(node)) {
    case 'choice': {
      const offered = choicesOf(node)
      return offered.length <= FEW ? buttons(offered.map((one) => ({ value: one, label: String(one) })), value, ctx, said, field) : listed(offered, value, ctx, said)
    }
    case 'boolean': {
      const words = yesNo(field.name, node)
      return buttons([{ value: true, label: words.yes }, { value: false, label: words.no }], value, ctx, said, field)
    }
    case 'integer':
    case 'number':
      return number(node, value, ctx, said, kindOf(node) === 'integer')
    case 'string':
      return text(field, value, ctx, said)
    case 'object':
      return objectControl(path, node, value && typeof value === 'object' ? value : {}, ctx, { said, required: field.required })
    case 'array':
      return list(path, field, Array.isArray(value) ? value : [], ctx, said)
    default:
      return json(value, ctx, said)
  }
}

/** A few choices, side by side as buttons, one of them picked: a radio group, as a keyboard moves through it. */
function buttons(options, value, ctx, { id, label, describedBy }, field) {
  let picked = options.findIndex((one) => same(one.value, value))
  const group = h('div', { class: 'ask-choices', role: 'radiogroup', 'aria-labelledby': `${id}-label`, 'aria-describedby': describedBy, 'data-hmz': 'ask-choices' })
  const first = ctx.choices.length === 0
  const each = options.map((one, at) =>
    h(
      'button',
      {
        type: 'button',
        role: 'radio',
        class: 'ask-choice',
        id: at === 0 ? id : undefined,
        'data-hmz': 'ask-choice',
        'data-value': JSON.stringify(one.value),
        disabled: ctx.disabled,
        onclick: () => choose(at),
      },
      // The first group's choices are picked by number, which each says.
      first && at < 9 ? h('kbd', { class: 'ask-key', 'aria-hidden': 'true' }, String(at + 1)) : null,
      h('span', {}, one.label),
      field.suggested && same(one.value, field.value) ? h('span', { class: 'ask-default', title: t('Suggested') }, '•') : null,
    ),
  )
  group.append(...each)
  function mark() {
    each.forEach((button, at) => {
      button.setAttribute('aria-checked', String(at === picked))
      // One stop in the tab order: the one picked, or the first.
      button.tabIndex = at === (picked < 0 ? 0 : picked) ? 0 : -1
    })
  }
  function choose(at) {
    if (ctx.disabled || at < 0 || at >= options.length) return false
    picked = at
    mark()
    changedIn(group)
    return true
  }
  group.addEventListener('keydown', (event) => {
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key]
    if (!step) return
    event.preventDefault()
    const at = ((picked < 0 ? 0 : picked + step) + options.length) % options.length
    choose(at)
    each[at].focus()
  })
  mark()
  ctx.choices.push({ el: group, pick: (n) => choose(n - 1) && (each[n - 1].focus(), true) })
  return {
    el: group,
    group: true,
    read: () => (picked < 0 ? undefined : options[picked].value),
    focus: () => each[picked < 0 ? 0 : picked].focus(),
  }
}

/** Many choices: a list to pick from, with a box to search it where it is long. */
function listed(offered, value, ctx, { id, describedBy }) {
  const select = h(
    'select',
    { id, 'aria-describedby': describedBy, disabled: ctx.disabled, 'data-hmz': 'ask-select' },
    h('option', { value: '' }, t('Choose…')),
    offered.map((one, at) => h('option', { value: String(at), selected: same(one, value) }, String(one))),
  )
  select.addEventListener('change', () => changedIn(select))
  let el = select
  if (offered.length > 12) {
    const search = h('input', { type: 'search', placeholder: t('Search {n} choices', { n: offered.length }), 'aria-label': t('Search the choices'), 'aria-controls': id, disabled: ctx.disabled, 'data-hmz': 'ask-search' })
    // What is searched narrows the list, and is no answer of its own.
    search.addEventListener('input', (event) => {
      event.stopPropagation()
      const words = search.value.trim().toLowerCase()
      for (const option of select.options) if (option.value) option.hidden = Boolean(words) && !option.textContent.toLowerCase().includes(words)
      const only = [...select.options].filter((option) => option.value && !option.hidden)
      if (only.length === 1 && select.value !== only[0].value) {
        select.value = only[0].value
        changedIn(select)
      }
    })
    el = h('div', { class: 'ask-listed' }, search, select)
  }
  return { el, read: () => (select.value === '' ? undefined : offered[Number(select.value)]), focus: () => select.focus() }
}

function number(node, value, ctx, { id, describedBy }, integer) {
  const input = h('input', {
    id,
    type: 'number',
    inputmode: integer ? 'numeric' : 'decimal',
    step: integer ? '1' : 'any',
    min: node.minimum ?? node.exclusiveMinimum,
    max: node.maximum ?? node.exclusiveMaximum,
    value: typeof value === 'number' ? String(value) : '',
    'aria-describedby': describedBy,
    disabled: ctx.disabled,
    'data-hmz': 'ask-input',
  })
  return {
    el: input,
    read: () => (input.value === '' ? undefined : Number(input.value)),
    focus: () => input.focus(),
    local: () => (input.validity && input.validity.badInput ? [t('This needs a number.')] : []),
  }
}

/** The types of input a string's format is typed into. */
const TYPED = { email: 'email', uri: 'url', url: 'url', date: 'date', time: 'time', 'date-time': 'datetime-local', password: 'password' }

function text(field, value, ctx, { id, describedBy }) {
  const node = field.node
  const widget = widgetOf(node)
  const said = typeof value === 'string' ? value : value === undefined || value === null ? '' : String(value)
  const common = { id, 'aria-describedby': describedBy, disabled: ctx.disabled, maxlength: node.maxLength, 'data-hmz': 'ask-input' }
  if (widget === 'secret' || node.format === 'password') {
    const input = h('input', { ...common, type: 'password', value: said, autocomplete: 'off', spellcheck: 'false' })
    const shown = h('button', { type: 'button', class: 'btn quiet small', 'aria-pressed': 'false', 'aria-controls': id, disabled: ctx.disabled }, t('Show'))
    shown.addEventListener('click', () => {
      const showing = input.type === 'password'
      input.type = showing ? 'text' : 'password'
      shown.textContent = showing ? t('Hide') : t('Show')
      shown.setAttribute('aria-pressed', String(showing))
    })
    return { el: h('div', { class: 'ask-secret row' }, input, shown), read: () => input.value, focus: () => input.focus() }
  }
  if (multiline(field.name, node, said)) {
    const area = h('textarea', { ...common, rows: widget === 'code' ? '6' : '3', class: widget === 'code' ? 'mono' : undefined, spellcheck: widget === 'code' ? 'false' : undefined }, said)
    grows(area)
    const counted = counter(area, node)
    if (widget !== 'markdown') return { el: counted ? h('div', { class: 'ask-text' }, area, counted) : area, read: () => area.value, focus: () => area.focus() }
    // Markdown is written, and seen as it will read, a button apart.
    const preview = h('div', { class: 'ask-preview ask-markdown', hidden: true, 'aria-live': 'polite' })
    const toggle = h('button', { type: 'button', class: 'btn quiet small', 'aria-pressed': 'false', disabled: ctx.disabled }, t('Preview'))
    toggle.addEventListener('click', () => {
      const previewing = preview.hidden
      preview.hidden = !previewing
      area.hidden = previewing
      toggle.textContent = previewing ? t('Write') : t('Preview')
      toggle.setAttribute('aria-pressed', String(previewing))
      if (previewing) markdownInto(preview, area.value || t('_Nothing written yet._'))
      else area.focus()
    })
    return {
      el: h('div', { class: 'ask-text' }, h('div', { class: 'ask-text-tools' }, h('span', { class: 'ask-tag' }, 'Markdown'), toggle), area, preview, counted),
      read: () => area.value,
      focus: () => {
        if (preview.hidden) area.focus()
        else toggle.click()
      },
    }
  }
  const type = TYPED[node.format] || 'text'
  const shown = type === 'datetime-local' ? said.slice(0, 16) : said
  const input = h('input', { ...common, type, value: shown, inputmode: type === 'email' ? 'email' : type === 'url' ? 'url' : undefined, spellcheck: type === 'text' ? undefined : 'false' })
  const counted = counter(input, node)
  return {
    el: counted ? h('div', { class: 'ask-text' }, input, counted) : input,
    read: () => (type === 'datetime-local' && input.value.length === 16 ? `${input.value}:00` : input.value),
    focus: () => input.focus(),
  }
}

/** How much of a bounded text is used, said once it is near the bound. */
function counter(input, node) {
  if (typeof node.maxLength !== 'number') return null
  const said = h('span', { class: 'ask-count', 'aria-live': 'off' })
  const count = () => {
    const n = [...input.value].length
    said.textContent = n >= node.maxLength * 0.7 ? `${n} / ${node.maxLength}` : ''
  }
  input.addEventListener('input', count)
  count()
  return said
}

/** A box of text grows with what is written in it, up to a point. */
function grows(area) {
  const fit = () => {
    if (!area.isConnected) return
    area.style.height = 'auto'
    area.style.height = `${Math.min(area.scrollHeight + 4, 360)}px`
  }
  area.addEventListener('input', fit)
  requestAnimationFrame(fit)
}

/** Fields of an object: its own, in reading order, those with a suggestion folded past a few. */
function objectControl(path, node, value, ctx, { fold = false, flat = false, said = null, required = true } = {}) {
  const fields = fieldsOf(node, ctx.root)
  const folds = fold && fields.length > FOLDS_PAST && fields.some((one) => !one.folded)
  const reads = {}
  const shown = []
  const folded = []
  for (const field of fields) {
    const at = [...path, field.name]
    const one = fieldControl(at, field, field.name in value ? value[field.name] : field.value, ctx)
    reads[field.name] = one.read
    ;(folds && field.folded ? folded : shown).push(one.box)
  }
  // What was changed from a suggestion is not hidden away.
  const moved = folds && fields.some((field) => field.folded && field.name in value && !same(value[field.name], field.value))
  const more = folded.length
    ? h('details', { class: 'ask-more', 'data-hmz': 'ask-more', open: moved || undefined }, h('summary', {}, t('More options ({n})', { n: folded.length })), h('div', { class: 'ask-more-fields' }, folded))
    : null
  const read = () => {
    const out = {}
    for (const [name, fn] of Object.entries(reads)) {
      const one = fn()
      if (one !== undefined) out[name] = one
    }
    return out
  }
  if (flat) return { fields: [...shown, more].filter(Boolean), read }
  const group = h('fieldset', { class: 'ask-group', 'aria-labelledby': `${said.id}-label`, 'aria-describedby': said.describedBy, disabled: ctx.disabled }, shown, more)
  return {
    el: group,
    group: true,
    // An object nobody must give, left as it was first shown, is left out.
    read: () => {
      const out = read()
      return !required && untouched(fields, out, ctx.root) && !Object.keys(value).length ? undefined : out
    },
    focus: () => group.querySelector('input, textarea, select, button')?.focus(),
  }
}

/** A list: its items, each taken out by a button beside it, and one more added below them. */
function list(path, field, value, ctx, said) {
  const { node: items } = resolved(field.node.items || {}, ctx.root)
  const choices = choicesOf(items)
  // A list of few choices is each choice toggled on or off.
  if (choices && choices.length <= 8) return toggles(choices, value, ctx, said)
  const rows = h('div', { class: 'ask-items', 'data-hmz': 'ask-items' })
  const singular = labelOf(field.name, field.node).replace(/ies$/, 'y').replace(/(?<!s)s$/, '').toLowerCase()
  const entries = []
  /** Each item's fields found again by where the item is now. */
  const rekey = () => {
    const moved = []
    for (const [key, box] of [...ctx.boxes]) {
      const n = entries.findIndex((one) => one.row.contains(box.el))
      if (n < 0) continue
      ctx.boxes.delete(key)
      box.path = [...path, n, ...box.path.slice(path.length + 1)]
      moved.push(box)
    }
    for (const box of moved) ctx.boxes.set(pathKey(box.path), box)
  }
  const add = (one, focus = false) => {
    const at = entries.length
    const itemField = { name: `${field.name}-item`, node: items, nullable: false, required: true, suggested: false, value: undefined }
    const id = idOf(ctx)
    const control = controlFor([...path, at], itemField, one, ctx, { id, label: `${singular} ${at + 1}`, describedBy: said.describedBy })
    const remove = h('button', { type: 'button', class: 'icon-btn ask-remove', 'aria-label': t('Remove {what} {n}', { what: singular, n: at + 1 }), title: t('Remove'), disabled: ctx.disabled, 'data-hmz': 'ask-remove' }, '×')
    const named = control.group ? h('span', { class: 'ask-item-n', id: `${id}-label` }, `${at + 1}.`) : h('label', { class: 'ask-item-n', for: id }, `${at + 1}.`)
    const row = h('div', { class: 'ask-item', 'data-hmz': 'ask-item' }, named, control.el, remove)
    const entry = { row, control }
    entries.push(entry)
    remove.addEventListener('click', () => {
      const was = entries.indexOf(entry)
      entries.splice(was, 1)
      row.remove()
      // The fields of what was taken out go with it, and those after it move up a place.
      for (const [key, box] of [...ctx.boxes]) if (row.contains(box.el)) ctx.boxes.delete(key)
      entries.forEach((one, n) => {
        one.row.querySelector('.ask-item-n').textContent = `${n + 1}.`
        one.row.querySelector('.ask-remove').setAttribute('aria-label', t('Remove {what} {n}', { what: singular, n: n + 1 }))
      })
      rekey()
      changedIn(rows)
      // The cursor stays where the item was: on the one after it, or on adding another.
      const next = entries[Math.min(was, entries.length - 1)]
      if (next) next.control.focus()
      else adder.focus()
    })
    rows.append(row)
    if (focus) control.focus()
  }
  for (const one of value) add(one)
  if (!value.length && (field.node.minItems || 0) > 0) add(undefined)
  const adder = h('button', { type: 'button', class: 'btn quiet small ask-add', disabled: ctx.disabled, 'data-hmz': 'ask-add' }, t('+ Add {what}', { what: singular }))
  adder.addEventListener('click', () => {
    add(undefined, true)
    changedIn(rows)
  })
  return {
    el: h('div', { class: 'ask-list', role: 'group', 'aria-labelledby': `${said.id}-label`, 'aria-describedby': said.describedBy }, rows, adder),
    group: true,
    read: () => entries.map((one) => one.control.read()).filter((one) => one !== undefined),
    focus: () => (entries[0] ? entries[0].control.focus() : adder.focus()),
  }
}

function toggles(choices, value, ctx, { id, describedBy }) {
  const picked = new Set(choices.map((one, at) => (value.some((each) => same(each, one)) ? at : -1)).filter((at) => at >= 0))
  const each = choices.map((one, at) =>
    h('button', { type: 'button', class: 'ask-choice', id: at === 0 ? id : undefined, 'aria-pressed': String(picked.has(at)), disabled: ctx.disabled, 'data-hmz': 'ask-toggle', onclick: (event) => {
      if (picked.has(at)) picked.delete(at)
      else picked.add(at)
      event.currentTarget.setAttribute('aria-pressed', String(picked.has(at)))
      changedIn(event.currentTarget)
    } }, String(one)),
  )
  return {
    el: h('div', { class: 'ask-choices ask-many', role: 'group', 'aria-labelledby': `${id}-label`, 'aria-describedby': describedBy }, each),
    group: true,
    read: () => choices.filter((_, at) => picked.has(at)),
    focus: () => each[0].focus(),
  }
}

/** Whatever has no field of its own, written as JSON. */
function json(value, ctx, { id, describedBy }) {
  const area = h('textarea', { id, rows: '4', class: 'mono', spellcheck: 'false', 'aria-describedby': describedBy, disabled: ctx.disabled, 'data-hmz': 'ask-input', placeholder: 'JSON' }, value === undefined ? '' : JSON.stringify(value, null, 2))
  grows(area)
  const parse = () => {
    if (!area.value.trim()) return { value: undefined }
    try {
      return { value: JSON.parse(area.value) }
    } catch {
      return { bad: true }
    }
  }
  return {
    el: area,
    read: () => parse().value,
    focus: () => area.focus(),
    local: () => (parse().bad ? [t('This is not valid JSON.')] : []),
  }
}
