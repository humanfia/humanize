// How the page asks the server anything: one wrapper for reading and writing, which turns a
// refusal into the sentence the server gave, and one store for what is read again and again,
// shared by every view of it.

/** A refusal: the server's own sentence, and the status it came with. */
export class Refused extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

/** Reads one answer, or throws the server's sentence. */
export async function get(url) {
  return answered(await fetch(url, { headers: { Accept: 'application/json' } }))
}

/** Writes, sending JSON, and reads the answer, or throws the server's sentence. */
export async function post(url, body = {}) {
  return answered(
    await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

async function answered(response) {
  const text = await response.text()
  let said = null
  try {
    said = text ? JSON.parse(text) : null
  } catch {
    said = null
  }
  if (response.status === 401) window.dispatchEvent(new CustomEvent('hmz:out'))
  if (!response.ok) {
    throw new Refused((said && said.error) || text || `The server answered ${response.status}.`, response.status)
  }
  return said
}

/** Every address read again and again, with who is reading it. */
const reads = new Map()

/** The shortest a failed read waits before the next, and the longest. */
const SOON = 1600
const LONGEST = 30000

/**
 * Reads an address every so often for as long as something is watching it: once for all of
 * them, at the shortest interval any of them asked for, and not while the page is hidden. A
 * read that fails is tried again later and later, and whoever is watching keeps what it had.
 *
 * @param {string} url What to read.
 * @param {number|null} every How often, in milliseconds, or null for once.
 * @param {(data: any, error: Error|null) => void} told What is told each answer.
 * @returns {() => void} What stops watching.
 */
export function poll(url, every, told) {
  let read = reads.get(url)
  if (!read) {
    read = { url, watchers: new Set(), timer: 0, failures: 0, text: undefined, data: undefined, error: null }
    reads.set(url, read)
  }
  const watcher = { every, told }
  read.watchers.add(watcher)
  if (read.text !== undefined || read.error) told(read.data, read.error)
  if (read.watchers.size === 1 || read.text === undefined) fetchNow(read)
  else schedule(read)
  return () => {
    read.watchers.delete(watcher)
    if (!read.watchers.size) {
      clearTimeout(read.timer)
      reads.delete(url)
    }
  }
}

/** Reads an address again now, for whoever watches it: after a write that changed it. */
export function refresh(url) {
  for (const read of reads.values()) if (read.url === url || read.url.startsWith(`${url}?`)) fetchNow(read)
}

async function fetchNow(read) {
  clearTimeout(read.timer)
  if (document.hidden) return
  try {
    const response = await fetch(read.url, { headers: { Accept: 'application/json' } })
    const text = await response.text()
    if (response.status === 401) window.dispatchEvent(new CustomEvent('hmz:out'))
    if (!response.ok) {
      let said = null
      try {
        said = JSON.parse(text)
      } catch {
        said = null
      }
      throw new Refused((said && said.error) || `The server answered ${response.status}.`, response.status)
    }
    read.failures = 0
    // An answer the same as the last is nothing new: nobody is told it again.
    if (text !== read.text || read.error) {
      read.text = text
      read.data = JSON.parse(text)
      read.error = null
      for (const watcher of read.watchers) watcher.told(read.data, null)
    }
  } catch (error) {
    read.failures += 1
    read.error = error
    for (const watcher of read.watchers) watcher.told(read.data, error)
  }
  schedule(read)
}

function schedule(read) {
  clearTimeout(read.timer)
  if (!reads.has(read.url)) return
  let every = Infinity
  for (const watcher of read.watchers) if (watcher.every) every = Math.min(every, watcher.every)
  if (read.failures) every = Math.min(SOON * 2 ** (read.failures - 1), LONGEST)
  if (every !== Infinity) read.timer = setTimeout(() => fetchNow(read), every)
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) for (const read of reads.values()) fetchNow(read)
})

/** An address with the query given, leaving out what is empty. */
export function address(path, query = {}) {
  const params = new URLSearchParams()
  for (const [name, value] of Object.entries(query)) if (value !== '' && value !== undefined && value !== null) params.set(name, value)
  const said = params.toString()
  return said ? `${path}?${said}` : path
}
