// What an earlier Humanize kept of themes in this browser, made what this one keeps. It kept
// themes of one side, a light or a dark alone, and a choice of one such theme outright, or of
// one for the system's light and another for its dark; now a theme always has both sides and is
// chosen whole. Nothing is dropped: a theme of one side gets the other, plain, one side chosen
// outright stays the side shown, and two sides picked apart become one theme of the user's own.
// Said without the page, so that it is tested.

/**
 * What to keep in place of what was kept; or null where there is nothing of an earlier Humanize.
 *
 * @param {object} kept What the browser holds: `pair`, the theme chosen as it is kept now;
 *   `theme`, `light` and `dark`, the ids an earlier Humanize chose by; `themes`, the sides made
 *   here. Each null, or `themes` empty, where the browser holds none.
 * @param {object[]} own The sides of the themes Humanize comes with, its own two by the ids
 *   `light` and `dark`.
 * @param {{fresh: (kind: string) => string, name: string}} how A new id of a kind, `p` for a
 *   theme and `t` for a side, and what a theme made of two picked apart is called.
 * @returns {{pair: string|null, mode: string|null, themes: object[], copies: [string, string][]}|null}
 *   The theme chosen, null for Humanize's own; the side an earlier Humanize showed whatever the
 *   system asked for, `light` or `dark`, null where it left none; the sides made here; and the
 *   sides whose pictures are copied, each as the id they are kept under and the id they are
 *   wanted under.
 */
export function migrated({ pair = null, theme = null, light = null, dark = null, themes = [] }, own, { fresh, name }) {
  const lone = (one) => !one.pair || !themes.some((other) => other.pair === one.pair && other.base !== one.base)
  if (theme === null && light === null && dark === null && !themes.some(lone)) return null
  const made = []
  for (const one of themes) {
    if (!lone(one)) made.push(one)
    else {
      const key = one.pair || fresh('p')
      made.push({ ...one, pair: key }, { id: fresh('t'), name: one.name, base: one.base === 'dark' ? 'light' : 'dark', pair: key, colors: {}, images: {} })
    }
  }
  const find = (id) => [...own, ...made].find((one) => one.id === id)
  const copies = []
  let chosen = pair
  // One side chosen outright was shown whatever the system asked for: it still is.
  const mode = theme === null ? null : (find(theme)?.base ?? null)
  if (chosen === null && theme !== null) chosen = find(theme)?.pair ?? null
  else if (chosen === null) {
    const two = [find(light) || find('light'), find(dark) || find('dark')]
    if (two[0].pair === two[1].pair && two[0].base === 'light' && two[1].base === 'dark') chosen = two[0].pair
    else {
      const taken = new Set(made.map((one) => one.name))
      let said = name
      for (let n = 2; taken.has(said); n++) said = `${name} ${n}`
      chosen = fresh('p')
      for (const [at, base] of ['light', 'dark'].entries()) {
        const id = fresh('t')
        made.push({ id, name: said, base, pair: chosen, colors: { ...two[at].colors }, images: structuredClone(two[at].images || {}) })
        if (Object.keys(two[at].images || {}).length) copies.push([two[at].id, id])
      }
    }
  }
  return { pair: chosen === 'humanize' ? null : chosen, mode, themes: made, copies }
}
