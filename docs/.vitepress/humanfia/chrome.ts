// The chrome of humanfia.ai: the nav's links, the social link and the footer's lines.
//
// This site is one path of humanfia.ai (/humanize/), built here and served beside the
// organisation's own build. A reader is meant to see one site, so the bar across the top and
// the footer are the organisation's, not this project's: the same links in the same order,
// the same wordmark, the same faces and colours (theme/humanfia/). What the links are is the
// organisation's to say, so it is read from the file its build publishes, /chrome.json, every
// time this site is built. `chrome.json` beside this file is the copy used when that cannot be
// fetched -- offline, or a build with no network -- and is what the fetched one is checked
// against for shape.
import { readFileSync } from 'node:fs'

export interface Chrome {
  /** Where the organisation's site is; every link below starts with it. */
  origin: string
  nav: ({ text: string; link: string } | { text: string; items: { text: string; link: string }[] })[]
  socialLinks: { icon: string; link: string }[]
  footer: { message: string; copyright: string }
}

const SNAPSHOT: Chrome = JSON.parse(readFileSync(new URL('./chrome.json', import.meta.url), 'utf8'))

const looksRight = (chrome: Chrome) =>
  typeof chrome?.origin === 'string' &&
  Array.isArray(chrome.nav) &&
  chrome.nav.length > 0 &&
  chrome.nav.every((entry) => typeof entry.text === 'string' && ('link' in entry || Array.isArray(entry.items))) &&
  Array.isArray(chrome.socialLinks) &&
  typeof chrome.footer?.message === 'string'

/** The organisation's chrome as it is published now, or the copy kept here. */
export async function loadChrome(): Promise<Chrome> {
  try {
    const answer = await fetch(`${SNAPSHOT.origin}/chrome.json`, { signal: AbortSignal.timeout(8000) })
    if (answer.ok) {
      const chrome = (await answer.json()) as Chrome
      if (looksRight(chrome)) return chrome
    }
  } catch {
    // No network, or no answer in time: the copy is at most as old as the last change here.
  }
  return SNAPSHOT
}

/**
 * The chrome as this build's theme takes it.
 *
 * A link into this site (`<origin>/humanize/...`) becomes a path of this site, so the router
 * follows it. Every other link is another build on the same origin: it keeps its full URL, and
 * is marked to load in this tab without the arrow the theme puts on a link that leaves.
 *
 * `origin` is where the organisation's site is for this build -- humanfia.ai, or a local copy
 * of it when the two builds are being looked at side by side.
 */
export function chromeFor(chrome: Chrome, base: string, origin = chrome.origin) {
  const here = `${chrome.origin}${base}`
  const moved = (link: string) => (link.startsWith(chrome.origin) ? origin + link.slice(chrome.origin.length) : link)
  const link = (item: { text: string; link: string }) =>
    item.link.startsWith(here)
      ? { text: item.text, link: `/${item.link.slice(here.length)}` }
      : { text: item.text, link: moved(item.link), target: '_self', rel: 'noopener', noIcon: true }
  return {
    home: `${origin}/`,
    nav: chrome.nav.map((entry) =>
      'items' in entry
        ? // The menu this site's own entry is in is the one that is lit on every page here.
          entry.items.some((item) => item.link.startsWith(here))
          ? { text: entry.text, items: entry.items.map(link), activeMatch: '.' }
          : { text: entry.text, items: entry.items.map(link) }
        : link(entry),
    ),
    socialLinks: chrome.socialLinks,
    footer: {
      message: chrome.footer.message.replaceAll(`href="${chrome.origin}`, `href="${origin}`),
      copyright: chrome.footer.copyright,
    },
  }
}
