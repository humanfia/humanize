// What the Runtimes page offers, apart from how it is drawn. Nothing here touches the page, so
// it is read the same by the page and by its tests.

/**
 * The runtimes one may fall back to, as its list holds them: `<backend>:<name>`, which is the
 * only shape the daemon takes (Section 7.4.3.2 of core.md), of any backend, and never itself.
 *
 * @param {{backend: string, name: string}[]} runtimes Every runtime saved.
 * @param {string} backend The backend of the runtime written.
 * @param {string} name Its name, '' while it has none yet.
 * @returns {string[]}
 */
export function fallbacks(runtimes, backend, name) {
  return runtimes.filter((one) => one.name !== name || one.backend !== backend).map((one) => `${one.backend}:${one.name}`)
}
