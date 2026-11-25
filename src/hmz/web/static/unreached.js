// What the page says of a daemon it cannot reach: one sentence for what went wrong -- which
// daemon, how it stands and why -- said wherever the failure is (Section 3.4.4.9 of
// protocol/web.md), and, apart from it, what to do next, said only on the sidebar's card that
// offers Connect and Manage. Nothing here touches the page, so it is read the same by the page and
// by its tests.

import { t } from './i18n.js'

/** How a daemon is reached, as a failure to reach it says it. */
const STATES = { idle: t('idle@@link'), connecting: t('connecting'), asking: t('asking@@link'), installing: t('installing'), up: t('up'), failed: t('failed') }

/** What a daemon is called on the page. */
export function called(name) {
  return name === 'local' ? t('Local') : name
}

/**
 * Why a daemon cannot be reached, in one sentence.
 *
 * @param {string} name The daemon, `local` for Local.
 * @param {string} now How it stands: `idle`, `connecting`, `installing`, `failed` and so on.
 * @param {string} detail What reaching it said last, if anything.
 */
export function unreached(name, now, detail) {
  const state = Object.hasOwn(STATES, now) ? STATES[now] : now
  const daemon = called(name)
  return detail ? t('{name} is unavailable, {state}: {detail}', { name: daemon, state, detail }) : t('{name} is unavailable, {state}.', { name: daemon, state })
}

/**
 * What to do about a daemon that cannot be reached, by where it is reached from.
 *
 * @param {string} name The daemon, `local` for Local.
 * @param {{kind?: string, desktop?: boolean}} [options] A remote daemon's kind, as `kindOf` names
 *   it; and whether the page is the desktop app's, which reaches Local without `hmz web`.
 */
export function nextStep(name, { kind = '', desktop = false } = {}) {
  if (name === 'local')
    return desktop
      ? t('Check that hmz is installed where your login shell finds it, then press Connect.')
      : t('Check that hmz web is still running, then press Connect. If it stopped, start it again and open the address it prints.')
  if (kind === 'SSH') return t('Check that ssh reaches its host from a terminal here without asking for anything, then press Connect.')
  if (kind === 'EasyTier') return t('Check that both machines name the same network secret and a node they both reach, then press Connect.')
  return t('Check that its machine is on and its daemon is listening, then press Connect.')
}
