// What the page says of a daemon it cannot reach, wherever it says it: one sentence for what
// went wrong -- which daemon, how it stands and why -- and one for what to do next. Nothing here
// touches the page, so it is read the same by the page and by its tests.

/** What a daemon is called on the page. */
export function called(name) {
  return name === 'local' ? 'Local' : name
}

/**
 * Why a daemon cannot be reached, and what to do about it.
 *
 * @param {string} name The daemon, `local` for Local.
 * @param {string} state How it stands: `idle`, `connecting`, `installing` or `failed`.
 * @param {string} detail What reaching it said last, if anything.
 * @param {{kind?: string, desktop?: boolean}} [options] A remote daemon's kind, `SSH`, `P2P` or
 *   `Paired`; and whether the page is the desktop app's, which reaches Local without `hmz web`.
 * @returns {{why: string, next: string}}
 */
export function unreached(name, state, detail, { kind = '', desktop = false } = {}) {
  const why = `${called(name)} is unavailable, ${state}${detail ? `: ${detail.replace(/\.$/, '')}.` : '.'}`
  return { why, next: nextStep(name, kind, desktop) }
}

/** What to do about a daemon that cannot be reached, by where it is reached from. */
function nextStep(name, kind, desktop) {
  if (name === 'local')
    return desktop
      ? 'Check that hmz is installed where your login shell finds it, then press Connect.'
      : 'Check that hmz web is still running, then press Connect. If it stopped, start it again and open the address it prints.'
  if (kind === 'SSH') return 'Check that ssh reaches its host from a terminal here without asking for anything, then press Connect.'
  if (kind === 'P2P') return 'Check that both machines name the same secret and a node they both reach, and that this machine is paired with it, then press Connect.'
  return 'Check that its machine is on and its daemon is listening, then press Connect.'
}
