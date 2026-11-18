// What a question asked of a person works out without a page: the fields a JSON schema asks for,
// in the order a person reads them -- what must be said first, what has a suggestion folded
// away -- what each is worded as, whether a value fits, in plain words beside the field it is
// of, how much is left to say, an answer said back in one line, and the one-line summary each
// block of context is folded behind.

/** How many values a choice offers before it is a list to search rather than buttons. */
export const FEW = 5

/** A schema's node with its `$ref` followed, one `allOf` of one unwrapped, and `null` let go. */
export function resolved(node, root = node) {
  let at = node || {}
  let nullable = false
  for (let hops = 0; hops < 32; hops++) {
    if (at.$ref) {
      const { $ref, ...rest } = at
      at = { ...refOf($ref, root), ...rest }
      continue
    }
    if (Array.isArray(at.allOf) && at.allOf.length === 1) {
      const { allOf, ...rest } = at
      at = { ...allOf[0], ...rest }
      continue
    }
    const branches = at.anyOf || at.oneOf
    if (Array.isArray(branches)) {
      const real = branches.filter((one) => one.type !== 'null')
      if (real.length < branches.length) nullable = true
      if (real.length === 1) {
        const { anyOf, oneOf, ...rest } = at
        at = { ...real[0], ...rest }
        continue
      }
      // A union of constants is one choice among them.
      if (real.length > 1 && real.every((one) => 'const' in one || (one.enum && one.enum.length === 1))) {
        const { anyOf, oneOf, ...rest } = at
        at = { ...rest, enum: real.map((one) => ('const' in one ? one.const : one.enum[0])) }
        continue
      }
    }
    if (Array.isArray(at.type) && at.type.includes('null')) {
      nullable = true
      const types = at.type.filter((one) => one !== 'null')
      at = { ...at, type: types.length === 1 ? types[0] : types }
    }
    break
  }
  return { node: at, nullable }
}

function refOf(ref, root) {
  if (!ref.startsWith('#/')) return {}
  let at = root
  for (const part of ref.slice(2).split('/')) at = at ? at[part.replace(/~1/g, '/').replace(/~0/g, '~')] : undefined
  return at || {}
}

/** The values a choice offers, or null where the node is no choice. */
export function choicesOf(node) {
  if (Array.isArray(node.enum)) return node.enum
  if ('const' in node) return [node.const]
  return null
}

/**
 * What kind of field a node is asked as: `choice`, `boolean`, `integer`, `number`, `string`,
 * `object`, `array`, or `json` for whatever has no field of its own.
 */
export function kindOf(node) {
  if (choicesOf(node)) return 'choice'
  const type = Array.isArray(node.type) ? (node.type.length === 1 ? node.type[0] : '') : node.type
  if (type === 'boolean' || type === 'integer' || type === 'number' || type === 'string') return type
  if (type === 'object' && node.properties) return 'object'
  if (type === 'array' && node.items && !Array.isArray(node.items)) return 'array'
  if (!type && node.properties) return 'object'
  return 'json'
}

/** The widget a field asks to be drawn as (`json_schema_extra={"hmz:widget": ...}`), or ''. */
export function widgetOf(node) {
  const said = node['hmz:widget'] || (node['json_schema_extra'] || {})['hmz:widget']
  return ['markdown', 'code', 'secret'].includes(said) ? said : ''
}

/** A field's name as a person reads it: its title where it is not merely its name title-cased. */
export function labelOf(name, node = {}) {
  const plain = String(name).replace(/[_-]+/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').trim().toLowerCase()
  const sentence = plain.charAt(0).toUpperCase() + plain.slice(1)
  const title = String(node.title || '').trim()
  if (!title) return sentence
  return title.toLowerCase() === plain ? sentence : title
}

/** A flow's param as its row names it: the title the flow gave it, else its key, as `-p` takes it. */
export function paramLabel(name, node = {}) {
  return String(node.title || '').trim() || String(name)
}

/** Whether a string field is likely to want more than one line. */
export function multiline(name, node, value = '') {
  if (widgetOf(node) === 'markdown' || widgetOf(node) === 'code') return true
  if (node.format === 'textarea' || node.contentMediaType) return true
  if (typeof node.maxLength === 'number' && node.maxLength > 160) return true
  if (typeof value === 'string' && (value.length > 60 || value.includes('\n'))) return true
  return /(^|_)(notes?|comments?|description|body|text|message|feedback|reason|explanation|summary|details?|prompt|why|plan)$/i.test(String(name))
}

/**
 * The fields an object node asks for, in reading order: what must be said, then what may be
 * left out, then what has a suggestion -- which a form folds away under "More options".
 *
 * @returns {{name: string, raw: object, node: object, nullable: boolean, required: boolean, suggested: boolean, value: any, folded: boolean}[]}
 */
export function fieldsOf(node, root = node) {
  const required = new Set(node.required || [])
  const all = Object.entries(node.properties || {}).map(([name, raw]) => {
    // A field is named by the title written on it, never by the one its type is defined under.
    const { node: { title, ...typed }, nullable } = resolved(raw, root)
    const field = 'title' in raw ? { ...typed, title: raw.title } : typed
    const suggested = 'default' in raw || 'default' in field
    const value = 'default' in raw ? raw.default : field.default
    return { name, raw, node: field, nullable, required: required.has(name), suggested, value, folded: !required.has(name) && suggested }
  })
  const rank = (one) => (one.required ? 0 : one.folded ? 2 : 1)
  return all.map((one, at) => ({ one, at })).sort((a, b) => rank(a.one) - rank(b.one) || a.at - b.at).map(({ one }) => one)
}

/** The words of a yes/no field's two buttons, from what it is about. */
export function yesNo(name, node = {}) {
  const about = String(node.description || '').trim().replace(/[.!?]+$/, '')
  const label = labelOf(name, node)
  // A short sentence saying what yes does reads best as the yes: "Yes, write tests".
  const said = about && about.length <= 48 && !/\?$/.test(node.description || '') ? about : label
  const lower = said.charAt(0).toLowerCase() + said.slice(1)
  if (lower.split(/\s+/).length > 7) return { yes: 'Yes', no: 'No' }
  return { yes: `Yes, ${lower}`, no: 'No' }
}

/** Whether a value is nothing said yet. */
export function blank(value) {
  return value === undefined || value === null || value === '' || (Array.isArray(value) && !value.length)
}

/** Whether an object's fields are read as a form first shows them: each blank, off, or still its suggestion, nested objects field by field. */
export function untouched(fields, value, root) {
  return fields.every((field) => {
    const one = value[field.name]
    if (blank(one) || one === false || (field.suggested && same(one, field.value))) return true
    return kindOf(field.node) === 'object' && typeof one === 'object' && !Array.isArray(one) && untouched(fieldsOf(field.node, root), one, root)
  })
}

/** A path, as the key a form finds its field by. */
export function pathKey(path) {
  return (path || []).map(String).join('/')
}

const FORMATS = {
  email: [/^[^\s@]+@[^\s@]+\.[^\s@]+$/, 'an email address, like name@example.com'],
  uri: [/^[a-z][a-z0-9+.-]*:\S+$/i, 'a full address, like https://example.com'],
  url: [/^[a-z][a-z0-9+.-]*:\S+$/i, 'a full address, like https://example.com'],
  date: [/^\d{4}-\d{2}-\d{2}$/, 'a date, like 2026-01-31'],
  'date-time': [/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/, 'a date and time'],
  time: [/^\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$/, 'a time, like 14:30'],
  uuid: [/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i, 'a UUID'],
}

/** A value said back in a message: a short string quoted, anything else as JSON. */
function quoted(value) {
  return typeof value === 'string' ? `“${value}”` : JSON.stringify(value)
}

/**
 * What does not fit in a value, as `[{path, message}]` in plain words, each of the field it is
 * of: what is missing, a choice not offered, a number out of bounds, text too long or not of
 * its format. Empty where it all fits. The host checks it again, and has the last word.
 */
export function problems(node, value, root = node, path = []) {
  const { node: at, nullable } = resolved(node, root)
  const said = []
  const wrong = (message) => said.push({ path, message })
  if (value === undefined || value === null) {
    if (value === null && !nullable && kindOf(at) !== 'json') wrong('This needs an answer.')
    return said
  }
  const kind = kindOf(at)
  if (kind === 'choice') {
    const offered = choicesOf(at)
    if (!offered.some((one) => same(one, value))) wrong(`Pick one of ${offered.map(quoted).join(', ')}.`)
    return said
  }
  if (kind === 'boolean' && typeof value !== 'boolean') wrong('Pick yes or no.')
  if (kind === 'integer' || kind === 'number') {
    if (typeof value !== 'number' || Number.isNaN(value)) wrong('This needs a number.')
    else if (kind === 'integer' && !Number.isInteger(value)) wrong('This needs a whole number.')
    else if (typeof at.minimum === 'number' && value < at.minimum) wrong(`At least ${at.minimum}.`)
    else if (typeof at.maximum === 'number' && value > at.maximum) wrong(`At most ${at.maximum}.`)
    else if (typeof at.exclusiveMinimum === 'number' && value <= at.exclusiveMinimum) wrong(`More than ${at.exclusiveMinimum}.`)
    else if (typeof at.exclusiveMaximum === 'number' && value >= at.exclusiveMaximum) wrong(`Less than ${at.exclusiveMaximum}.`)
    else if (typeof at.multipleOf === 'number' && Math.abs(value / at.multipleOf - Math.round(value / at.multipleOf)) > 1e-9) wrong(`A multiple of ${at.multipleOf}.`)
  }
  if (kind === 'string') {
    if (typeof value !== 'string') wrong('This needs text.')
    else {
      const length = [...value].length
      if (typeof at.minLength === 'number' && length < at.minLength) wrong(at.minLength === 1 ? 'This needs an answer.' : `At least ${at.minLength} characters.`)
      else if (typeof at.maxLength === 'number' && length > at.maxLength) wrong(`At most ${at.maxLength} characters (${length} now).`)
      else if (at.pattern && !safePattern(at.pattern).test(value)) wrong(`This is not in the form asked for (${at.pattern}).`)
      else if (FORMATS[at.format] && !FORMATS[at.format][0].test(value)) wrong(`This needs ${FORMATS[at.format][1]}.`)
    }
  }
  if (kind === 'array') {
    if (!Array.isArray(value)) wrong('This needs a list.')
    else {
      if (typeof at.minItems === 'number' && value.length < at.minItems) wrong(`At least ${at.minItems} ${at.minItems === 1 ? 'item' : 'items'}.`)
      else if (typeof at.maxItems === 'number' && value.length > at.maxItems) wrong(`At most ${at.maxItems} ${at.maxItems === 1 ? 'item' : 'items'}.`)
      else if (at.uniqueItems && new Set(value.map((one) => JSON.stringify(one))).size < value.length) wrong('Each item only once.')
      value.forEach((one, index) => said.push(...problems(at.items, one, root, [...path, index])))
    }
  }
  if (kind === 'object') {
    if (typeof value !== 'object' || Array.isArray(value)) wrong('This needs an object.')
    else
      for (const field of fieldsOf(at, root)) {
        const one = value[field.name]
        if (field.required && (one === undefined || (one === '' && kindOf(field.node) !== 'json'))) said.push({ path: [...path, field.name], message: 'This needs an answer.' })
        else said.push(...problems(field.raw, one, root, [...path, field.name]))
      }
  }
  return said
}

function safePattern(pattern) {
  try {
    return new RegExp(pattern, 'u')
  } catch {
    return /(?:)/
  }
}

function same(a, b) {
  return a === b || JSON.stringify(a) === JSON.stringify(b)
}

/** How many required fields are still blank, nested objects counted field by field. */
export function requiredLeft(node, value, root = node) {
  const { node: at } = resolved(node, root)
  if (kindOf(at) !== 'object') return 0
  let left = 0
  const said = value && typeof value === 'object' && !Array.isArray(value) ? value : {}
  for (const field of fieldsOf(at, root)) {
    const one = said[field.name]
    if (kindOf(field.node) === 'object') left += field.required || !blank(one) ? requiredLeft(field.node, one, root) : 0
    else if (field.required && blank(one) && !(field.nullable && one === null)) left++
  }
  return left
}

/** The words on a form's send button: what is left to say, or that it can go. */
export function sendLabel(left, ready = 'Send answer') {
  return left ? `${left} required left` : ready
}

/**
 * An answer said back in one line: each value of an object in the order asked, choices as they
 * are, text quoted and cut short -- "approve · ‘LGTM’".
 */
/** Whether a field holds a secret: never kept in a draft, never written back but as `***`. */
export function secretOf(node = {}) {
  return widgetOf(node) === 'secret' || node.format === 'password'
}

/** What of a form's value a draft may keep: every field but those holding a secret. */
export function draftable(value, node = null, root = node) {
  if (!node || !value || typeof value !== 'object' || Array.isArray(value)) return value
  const kept = { ...value }
  for (const field of fieldsOf(resolved(node, root).node, root)) {
    if (secretOf(field.raw) || secretOf(field.node)) delete kept[field.name]
    else if (field.name in kept) kept[field.name] = draftable(kept[field.name], field.node, root)
  }
  return kept
}

export function summaryOf(value, node = null, root = node, most = 90) {
  const parts = []
  const add = (one, field) => {
    if (blank(one)) return
    if (field && (secretOf(field.raw || {}) || secretOf(field.node))) {
      parts.push(`${labelOf(field.name, field.node).toLowerCase()}: ***`)
      return
    }
    if (typeof one === 'boolean') parts.push(field ? `${labelOf(field.name, field.node).toLowerCase()}: ${one ? 'yes' : 'no'}` : one ? 'yes' : 'no')
    else if (typeof one === 'string') parts.push(field && kindOf(field.node) === 'choice' ? one : `‘${oneLine(one, 40)}’`)
    else if (typeof one === 'number') parts.push(field ? `${labelOf(field.name, field.node).toLowerCase()}: ${one}` : String(one))
    else if (Array.isArray(one)) parts.push(one.every((each) => typeof each !== 'object') ? one.join(', ') : `${one.length} items`)
    else parts.push(oneLine(JSON.stringify(one), 40))
  }
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const fields = node ? fieldsOf(resolved(node, root).node, root) : Object.keys(value).map((name) => ({ name, node: {} }))
    const named = new Set(fields.map((one) => one.name))
    for (const field of fields) add(value[field.name], field)
    for (const [name, one] of Object.entries(value)) if (!named.has(name)) add(one, { name, node: {} })
  } else add(value, null)
  return oneLine(parts.join(' · ') || '(nothing)', most)
}

/** Text on one line, cut at `most` characters. */
export function oneLine(text, most = 90) {
  const said = String(text ?? '').replace(/\s+/g, ' ').trim()
  return said.length > most ? `${said.slice(0, most - 1)}…` : said
}

/** Why a question went away without being answered here, as a person says it. */
export function withdrawnWhy(why, role = '') {
  if (why === 'away') return `${role || 'The person'} went away`
  if (why === 'over') return 'the run ended'
  return why ? String(why) : 'it is no longer asked'
}

// ------------------------------------------------------------------ context blocks

/** The files of a unified diff, each with its lines and how many it adds and removes. */
export function patchFiles(patch) {
  const files = []
  let at = null
  const start = (name) => {
    at = { name, lines: [], added: 0, removed: 0 }
    files.push(at)
  }
  for (const text of String(patch || '').replace(/\r\n/g, '\n').split('\n')) {
    if (text.startsWith('diff --git ')) {
      const named = /^diff --git a\/(.+?) b\/(.+)$/.exec(text)
      start(named ? named[2] : text.slice(11))
      at.lines.push({ kind: 'meta', text })
      continue
    }
    if (text.startsWith('+++ ')) {
      const name = text.slice(4).replace(/^b\//, '').replace(/\t.*$/, '')
      if (!at || at.lines.some((one) => one.kind === 'hunk')) start(name)
      else if (name !== '/dev/null') at.name = name
      at.lines.push({ kind: 'meta', text })
      continue
    }
    if (text.startsWith('--- ')) {
      // A file named only by its `---`, as a patch of several without `diff --git` names them.
      if (!at || at.lines.some((one) => one.kind === 'hunk')) start(text.slice(4).replace(/^a\//, '').replace(/\t.*$/, ''))
      at.lines.push({ kind: 'meta', text })
      continue
    }
    if (!at) start('')
    if (text.startsWith('@@')) at.lines.push({ kind: 'hunk', text })
    else if (text.startsWith('+')) {
      at.added++
      at.lines.push({ kind: 'add', text })
    } else if (text.startsWith('-')) {
      at.removed++
      at.lines.push({ kind: 'del', text })
    } else if (text.startsWith('\\')) at.lines.push({ kind: 'meta', text })
    else if (/^(index |new file|deleted file|old mode|new mode|similarity|rename |copy )/.test(text)) at.lines.push({ kind: 'meta', text })
    else if (text || at.lines.length) at.lines.push({ kind: 'same', text })
  }
  for (const one of files) while (one.lines.length && one.lines.at(-1).kind === 'same' && !one.lines.at(-1).text) one.lines.pop()
  return files.filter((one) => one.lines.length)
}

/** How much a diff changes: lines added and removed, and in how many files. */
export function diffStats(patch) {
  const files = patchFiles(patch)
  return { added: files.reduce((n, one) => n + one.added, 0), removed: files.reduce((n, one) => n + one.removed, 0), files: files.length }
}

/** The rows a chart is drawn from, as a table: `spec.data.values`, or none. */
export function chartRows(spec) {
  const values = spec && spec.data && Array.isArray(spec.data.values) ? spec.data.values : []
  const columns = []
  for (const row of values) if (row && typeof row === 'object') for (const key of Object.keys(row)) if (!columns.includes(key)) columns.push(key)
  return { columns, rows: values.map((row) => columns.map((key) => (row && typeof row === 'object' ? row[key] : row))) }
}

const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`

/** What a block holds, in one line, as it is folded behind. */
export function blockSummary(block) {
  switch (block.kind) {
    case 'markdown':
      return oneLine(String(block.text || '').replace(/^\s*([-*+]|\d+\.)\s+/gm, '').replace(/[#>*_`]+/g, ''), 80)
    case 'code': {
      const lines = String(block.text || '').split('\n').length
      return [block.language, plural(lines, 'line')].filter(Boolean).join(' · ')
    }
    case 'diff': {
      const { added, removed, files } = diffStats(block.patch)
      return `+${added} −${removed} in ${plural(files, 'file')}`
    }
    case 'table':
      return `table · ${plural((block.rows || []).length, 'row')}`
    case 'image':
      return ['image', block.alt].filter(Boolean).join(' · ')
    case 'json': {
      const value = block.value
      if (Array.isArray(value)) return `json · ${plural(value.length, 'item')}`
      if (value && typeof value === 'object') return `json · ${plural(Object.keys(value).length, 'key')}`
      return `json · ${oneLine(JSON.stringify(value), 60)}`
    }
    case 'chart': {
      const spec = block.spec || {}
      const mark = typeof spec.mark === 'string' ? spec.mark : (spec.mark && spec.mark.type) || ''
      const rows = chartRows(spec).rows.length
      return ['chart', mark, rows ? plural(rows, 'point') : ''].filter(Boolean).join(' · ')
    }
    default:
      return String(block.kind || 'block')
  }
}

/** The word a block's kind is named by on its fold. */
export function kindWord(kind) {
  return { markdown: 'Note', code: 'Code', diff: 'Diff', table: 'Table', image: 'Image', json: 'Data', chart: 'Chart' }[kind] || 'Context'
}

/** Whether a block is long enough to fold behind its summary until it is asked for. */
export function isLong(block) {
  switch (block.kind) {
    case 'markdown':
      return String(block.text || '').length > 700 || String(block.text || '').split('\n').length > 14
    case 'code':
      return String(block.text || '').split('\n').length > 14
    case 'diff':
      return patchFiles(block.patch).reduce((n, one) => n + one.lines.length, 0) > 24
    case 'table':
      return (block.rows || []).length > 8
    case 'json':
      return JSON.stringify(block.value ?? null).length > 400
    default:
      return false
  }
}

/** Whether each block of a question's context is open as it is first drawn: the first, and every short one. */
export function opened(context) {
  return (context || []).map((block, at) => at === 0 || !isLong(block))
}

/** An image block's address, where its type is an image's. */
export function imageSource(block) {
  const mime = String(block.mime || '')
  if (!/^image\/[a-z0-9.+-]+$/i.test(mime)) return ''
  return `data:${mime};base64,${String(block.data || '').replace(/\s+/g, '')}`
}

// ------------------------------------------------------------------ drafts

/** Where a question's draft is kept in this browser. */
export function draftKey(question) {
  return `hmz-ask-draft:${question}`
}

/** A draft kept, or undefined where none is or this browser keeps nothing. */
export function readDraft(question, storage = globalThis.localStorage) {
  try {
    const said = storage && storage.getItem(draftKey(question))
    return said ? JSON.parse(said).value : undefined
  } catch {
    return undefined
  }
}

/** Keeps a draft, or forgets it given undefined. */
export function keepDraft(question, value, storage = globalThis.localStorage) {
  try {
    if (!storage) return
    if (value === undefined) storage.removeItem(draftKey(question))
    else storage.setItem(draftKey(question), JSON.stringify({ value, at: Date.now() }))
  } catch {
    // A browser that keeps nothing forgets the draft: the form works the same.
  }
}

/** Forgets drafts older than `days`, so that questions long gone leave nothing behind. */
export function pruneDrafts(days = 14, storage = globalThis.localStorage, now = Date.now()) {
  try {
    if (!storage) return
    for (let at = storage.length - 1; at >= 0; at--) {
      const key = storage.key(at)
      if (!key || !key.startsWith('hmz-ask-draft:')) continue
      let old = true
      try {
        old = now - JSON.parse(storage.getItem(key)).at > days * 86400000
      } catch {
        // What cannot be read is forgotten.
      }
      if (old) storage.removeItem(key)
    }
  } catch {
    // Nothing kept, nothing to forget.
  }
}

/** The errors of a refusal of `epic.answer`, as `[{path, message}]`, or none. */
export function refusalErrors(error) {
  // The page's own refusal keeps what came with it as `said`; the RPC client's, as `data`.
  const data = error && (error.said || error.data)
  const errors = data && Array.isArray(data.errors) ? data.errors : []
  return errors.filter((one) => one && typeof one.message === 'string').map((one) => ({ path: Array.isArray(one.path) ? one.path : [], message: one.message }))
}
