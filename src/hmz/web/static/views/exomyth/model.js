// Exomyth's data: an epic's timeline, as `GET /api/runs/<name>/timeline` lays it out, read into
// what the views draw from once, as it arrives -- its strings looked up, its columns typed, each
// track's spans indexed by depth -- and read again while the epic goes.
//
// The model every view of Exomyth is handed (the Timeline here, the Flame in flame.js):
//
//   {
//     version, layout, epic, origin, live,  // as the document says them
//     end,                                  // µs: the last moment anything did (summary.end)
//     strings: string[],                    // the document's string table
//     summary,                              // as the document says it
//     processes: [{
//       id, kind ('flow' | 'session' | 'os'), parent (id or -1), pid, start, end,
//       name, key, agent, role, backend, model, label, record,  // text, looked up
//       tracks: number[],                   // track ids, in lane order
//       children: number[],                 // process ids hanging from it, in id order
//       level,                              // how deep it hangs: 0 for a root
//       spans,                              // how many spans its tracks hold
//     }],
//     order: number[],                      // process ids, each after its parent (depth first)
//     tracks: [{
//       id, process, name (text), first (the span id of its first), count, depths,
//       start, dur, end: Float64Array,      // µs; end = start + dur
//       depth: Int32Array,
//       cat, name_, model: Int32Array,      // string indices (name_ is the span's name)
//       in, out: Float64Array,              // tokens
//       rows: Int32Array[],                 // per depth: indices of its spans, by start -- and,
//                                           // since spans of one depth never overlap, by end
//     }],
//     categories: string[],                 // the categories it holds, in a fixed order
//   }
//
// A span is named by its id (`track.first + index`); `locate(model, id)` finds it again.

/** The timeline's version this page draws. */
export const VERSION = 1

/** Categories in the order they are listed and coloured. */
export const CATEGORIES = ['flow', 'session', 'turn', 'llm', 'tool', 'message', 'event', 'process']

/** Reads a timeline document into the model; throws on a version this page does not know. */
export function load(doc) {
  if (doc.version !== VERSION) throw new Error(`This page draws timelines of version ${VERSION}, not ${doc.version}.`)
  const strings = doc.strings
  const said = (index) => strings[index] || ''
  const tracks = doc.tracks.map((one, id) => {
    const columns = one.spans
    const start = Float64Array.from(columns.start)
    const dur = Float64Array.from(columns.dur)
    const end = new Float64Array(one.count)
    for (let i = 0; i < one.count; i++) end[i] = start[i] + dur[i]
    const depth = Int32Array.from(columns.depth)
    // Each depth's spans, by start: counted first, then laid in place.
    const counts = new Int32Array(Math.max(1, one.depths))
    for (let i = 0; i < one.count; i++) counts[depth[i]]++
    const rows = Array.from(counts, (count) => new Int32Array(count))
    const filled = new Int32Array(counts.length)
    for (let i = 0; i < one.count; i++) rows[depth[i]][filled[depth[i]]++] = i
    return {
      id,
      process: one.process,
      name: said(one.name),
      first: one.first,
      count: one.count,
      depths: Math.max(1, one.depths),
      start,
      dur,
      end,
      depth,
      cat: Int32Array.from(columns.cat),
      name_: Int32Array.from(columns.name),
      model: Int32Array.from(columns.model),
      in: Float64Array.from(columns.in),
      out: Float64Array.from(columns.out),
      rows,
    }
  })
  const processes = doc.processes.map((one) => ({
    id: one.id,
    kind: one.kind,
    parent: one.parent,
    pid: one.pid,
    start: one.start,
    end: one.end,
    name: said(one.name),
    key: said(one.key),
    agent: said(one.agent),
    role: said(one.role),
    backend: said(one.backend),
    model: said(one.model),
    label: said(one.label),
    record: said(one.record),
    tracks: one.tracks,
    children: [],
    level: 0,
    spans: one.tracks.reduce((sum, track) => sum + tracks[track].count, 0),
  }))
  const roots = []
  for (const one of processes) (one.parent >= 0 && processes[one.parent] ? processes[one.parent].children : roots).push(one.id)
  const order = []
  const walk = (id, level) => {
    processes[id].level = level
    order.push(id)
    for (const child of processes[id].children) walk(child, level + 1)
  }
  for (const id of roots) walk(id, 0)
  const present = new Set(tracks.flatMap((track) => Array.from(new Set(track.cat), said)))
  return {
    version: doc.version,
    layout: doc.layout,
    epic: doc.epic,
    origin: doc.origin,
    live: doc.live,
    end: Math.max(1, doc.summary.end),
    strings,
    summary: doc.summary,
    processes,
    order,
    tracks,
    categories: [...CATEGORIES.filter((one) => present.has(one)), ...[...present].filter((one) => one && !CATEGORIES.includes(one)).sort()],
  }
}

/** The track and index of a span, by its id, or null for one the model does not have. */
export function locate(model, id) {
  const { tracks } = model
  let low = 0
  let high = tracks.length - 1
  while (low <= high) {
    const mid = (low + high) >> 1
    const track = tracks[mid]
    if (id < track.first) high = mid - 1
    else if (id >= track.first + track.count) low = mid + 1
    else return { track: mid, index: id - track.first }
  }
  return null
}

/** The first position in `row` (indices into `ends`) whose span ends at or after `t`. */
export function firstEnding(row, ends, t) {
  let low = 0
  let high = row.length
  while (low < high) {
    const mid = (low + high) >> 1
    if (ends[row[mid]] < t) low = mid + 1
    else high = mid
  }
  return low
}

/**
 * What a stretch of time holds, category by category: how many spans overlap it, how long of
 * each lies inside it, and the tokens of those spans.
 */
export function within(model, from, to) {
  const by = new Map()
  let count = 0
  let tokensIn = 0
  let tokensOut = 0
  for (const track of model.tracks) {
    for (const row of track.rows) {
      for (let at = firstEnding(row, track.end, from); at < row.length; at++) {
        const i = row[at]
        if (track.start[i] > to) break
        const cat = model.strings[track.cat[i]]
        let one = by.get(cat)
        if (!one) by.set(cat, (one = { count: 0, time: 0, in: 0, out: 0 }))
        one.count++
        one.time += Math.min(to, track.end[i]) - Math.max(from, track.start[i])
        one.in += track.in[i]
        one.out += track.out[i]
        count++
        tokensIn += track.in[i]
        tokensOut += track.out[i]
      }
    }
  }
  return { count, in: tokensIn, out: tokensOut, categories: by }
}

/** A moment, µs from the start, said to the precision a step between moments asks for. */
export function clock(t, step = 1) {
  const sign = t < 0 ? '-' : ''
  t = Math.abs(t)
  if (step >= 60e6) {
    const minutes = Math.round(t / 60e6)
    const hours = Math.floor(minutes / 60)
    return sign + (hours ? `${hours}h${minutes % 60 ? ` ${String(minutes % 60).padStart(2, '0')}m` : ''}` : `${minutes}m`)
  }
  const digits = step >= 1e6 ? 0 : Math.min(6, Math.ceil(-Math.log10(step / 1e6) - 1e-9))
  // Rounded first, so that 59.9996s at a millisecond's step is 1m 00.000s rather than 60.000s.
  const unit = 1e6 / 10 ** digits
  const seconds = (Math.round(t / unit) * unit) / 1e6
  const minutes = Math.floor(seconds / 60)
  let rest = (seconds - minutes * 60).toFixed(digits)
  if (!minutes) return `${sign}${rest}s`
  if (rest.split('.')[0].length < 2) rest = `0${rest}`
  const hours = Math.floor(minutes / 60)
  return `${sign}${hours ? `${hours}h ${String(minutes % 60).padStart(2, '0')}m` : `${minutes}m`} ${rest}s`
}

/** How long, in µs, said shortly. */
export function lasted(us) {
  // Each unit up to where it would round to the next: 999.6µs is 1.00ms, never 1000µs.
  if (us < 999.5) return `${Math.round(us)}µs`
  if (us < 999_500) return `${trim(us / 1e3)}ms`
  if (us < 59_950_000) return `${trim(us / 1e6)}s`
  const seconds = Math.round(us / 1e6)
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ${String(seconds % 60).padStart(2, '0')}s`
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}m`
}

function trim(value) {
  return value >= 100 ? value.toFixed(0) : value >= 10 ? value.toFixed(1) : value.toFixed(2)
}

/** A count said with its thousands grouped. */
export function counted(n) {
  return Math.round(n).toLocaleString('en-US')
}
