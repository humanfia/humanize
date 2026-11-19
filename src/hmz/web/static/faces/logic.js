// What hosting a face works out without a page: which face and which session a question is
// of, what of it the face is told, what the page's colours are said to it as, how tall its frame
// may grow, and what a submission came to. Kept apart from host.js so that it is tested alone.

/** How long a face has to say it listens for asks, from its frame loading, before the plain form. */
export const PATIENCE_MS = 5000

/** The shortest and the tallest a face's frame is drawn. */
export const HEIGHTS = Object.freeze({ least: 48, most: 4000, first: 168 })

/** How many sessions keep their frame mounted at once; the one used longest ago goes first. */
export const KEPT = 8

/** How many `show` pushes a session keeps, to tell a frame loaded again what it was shown. */
export const SHOWN = 32

/** The tokens of the page's style a face is given, whether or not the browser lists them. */
export const TOKENS = Object.freeze([
  'paper', 'surface', 'raised', 'side', 'ink', 'ink-2', 'ink-3', 'on-ink', 'on-fill',
  'line', 'line-strong', 'hover', 'scrim', 'green', 'pink', 'pink-ink', 'cyan', 'cyan-ink',
  'lavender', 'gold', 'live', 'live-ink', 'live-soft', 'link', 'done', 'fail', 'budget',
  'budget-ink', 'lane-1', 'lane-2', 'lane-3', 'lane-4', 'lane-5', 'lane-6', 'shadow', 'sans',
  'mono', 'control', 'control-ink', 'primary', 'on-primary', 'field', 'edge', 'selected', 'quiet',
  'border-w', 'radius-xs', 'radius-sm', 'radius-md', 'radius-lg', 'control-h', 'control-h-sm',
  'control-h-xs', 'control-h-lg',
])

/** The hash of a question's face, which the wire says as `{hash, title}` and a host as a hash. */
export function hashOf(question) {
  const face = question?.face
  if (typeof face === 'string') return face
  return typeof face?.hash === 'string' ? face.hash : ''
}

/** The title a question's face was given, if it was. */
export function titleOf(question) {
  const face = question?.face
  return face && typeof face === 'object' && typeof face.title === 'string' ? face.title : ''
}

/** The session a question is asked in: its frame is kept across that session's asks. */
export function sessionOf(question) {
  if (question?.session) return String(question.session)
  return `${question?.role || ''}/${question?.key ?? question?.question ?? question?.id ?? ''}`
}

/**
 * What a session's frame is kept by: its host and its epic as well as its name, as every epic
 * of every host names its sessions from one.
 */
export function mountOf(where, run, session) {
  const host = typeof where === 'string' ? `${where}\n` : `${where?.workspace || ''}\n${where?.slot || ''}`
  return `${host}\n${run || ''}\n${session}`
}

/** What a face is told of a question: `{prompt, context, schema, errors}`, as the bridge says. */
export function askOf(question) {
  const list = (value) => (Array.isArray(value) ? value : [])
  return {
    prompt: String(question?.prompt ?? question?.text ?? ''),
    context: list(question?.context),
    schema: question?.schema ?? null,
    errors: list(question?.errors),
  }
}

/** Refusals the bridge passes on: each `{path, message}`, whatever shape they came in. */
export function errorsOf(errors, otherwise = 'The answer was not taken.') {
  const listed = Array.isArray(errors) ? errors : []
  const said = listed
    .filter((one) => one && typeof one === 'object')
    .map((one) => ({
      path: Array.isArray(one.path) ? one.path.filter((part) => typeof part === 'string' || typeof part === 'number') : [],
      message: String(one.message ?? otherwise),
    }))
  return said.length ? said : [{ path: [], message: otherwise }]
}

/**
 * What a face's `hmz.submit` resolves to, given what submitting did: `{ok: true}` for anything
 * but a refusal, and `{ok: false, errors}` for one, whether the submitter resolved with
 * `{ok: false, errors}` or threw an error carrying `data.errors` (a JSON-RPC refusal, as
 * `RpcError` carries it; `said.errors` as api.js's `Refused` does).
 */
export async function outcome(submit, value) {
  try {
    const result = await submit(value)
    if (result && typeof result === 'object' && result.ok === false) return { ok: false, errors: errorsOf(result.errors) }
    return { ok: true }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    return { ok: false, errors: errorsOf(error?.data?.errors ?? error?.said?.errors, message || undefined) }
  }
}

/** A value as the JSON it is sent as, or undefined where it is none. */
export function jsonOf(value) {
  try {
    const text = JSON.stringify(value)
    return text === undefined ? undefined : JSON.parse(text)
  } catch {
    return undefined
  }
}

/** The height a face's frame is drawn at, for one it asked for. */
export function heightOf(asked) {
  const number = Number(asked)
  if (!Number.isFinite(number) || number <= 0) return HEIGHTS.first
  return Math.round(Math.min(HEIGHTS.most, Math.max(HEIGHTS.least, number)))
}

/** Whether a token may be said in a style sheet: a custom property's name and a plain value. */
export function tokenFits(name, value) {
  return /^--[A-Za-z0-9_-]+$/.test(name) && typeof value === 'string' && value.trim() !== '' && !/[<>{};\\]/.test(value)
}

/** Only the tokens that fit, trimmed. */
export function tokensOf(given) {
  const tokens = {}
  for (const [name, value] of Object.entries(given || {})) if (tokenFits(name, String(value).trim())) tokens[name] = String(value).trim()
  return tokens
}

/** The `:root` rule the tokens are set on in a face before it runs. */
export function rootRule(tokens) {
  const lines = Object.entries(tokensOf(tokens)).map(([name, value]) => `${name}:${value};`)
  const scheme = tokens?.['--scheme'] === 'dark' ? 'dark' : tokens?.['--scheme'] === 'light' ? 'light' : ''
  return `:root{${lines.join('')}${scheme ? `color-scheme:${scheme};` : ''}}`
}

/** A token never seen again, for one mount's handshake. */
export function tokenFor(random = globalThis.crypto) {
  const bytes = new Uint8Array(16)
  random.getRandomValues(bytes)
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('')
}

/**
 * A fetch that asks each face once: the HTML of a hash is kept for as long as the page is open,
 * and a fetch that failed is asked again next time.
 */
export function cached(store = new Map()) {
  return (hash, fetchFace) => {
    if (!store.has(hash)) {
      const asked = Promise.resolve()
        .then(() => fetchFace(hash))
        .then((face) => {
          if (!face || typeof face.html !== 'string' || !face.html.trim()) throw new Error(`The view ${hash.slice(0, 8)} is empty.`)
          return { html: face.html, title: typeof face.title === 'string' ? face.title : '' }
        })
      asked.catch(() => store.delete(hash))
      store.set(hash, asked)
    }
    return store.get(hash)
  }
}

/** The sessions to let go of so that at most `most` stay: those used longest ago. */
export function overflow(sessions, most = KEPT) {
  return sessions.length > most ? sessions.slice(0, sessions.length - most) : []
}
