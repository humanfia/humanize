// What the Environments view draws, worked out with no page to draw on: which environments
// there are, grouped by the role that holds them and each derived one under the one it came
// from; which panels each has, by what it can really do; which panel it opens on, by what the
// flow said it uses; and how it, and what was done in it, is said in a line.

import { t } from '../../i18n.js'

/**
 * The panels an environment can have, each with the capabilities any one of which gives it, in
 * the order they are shown.
 */
export const PANELS = [
  { key: 'files', label: t('Files'), caps: ['files'] },
  { key: 'terminal', label: t('Terminal'), caps: ['shell'] },
  { key: 'changes', label: t('Changes'), caps: ['git', 'git_worktree'] },
]

/** The panels an environment has: those one of whose capabilities it really has. */
export function panelsOf(env) {
  const caps = new Set((env && env.caps) || [])
  return PANELS.filter((one) => one.caps.some((cap) => caps.has(cap)))
}

/**
 * The panel an environment opens on: the first it has whose capability the flow also declared,
 * else Files where it has Files, else the first it has, else none.
 */
export function defaultTab(env) {
  const panels = panelsOf(env)
  const declared = new Set((env && env.declared) || [])
  const used = panels.find((one) => one.caps.some((cap) => declared.has(cap)))
  if (used) return used.key
  if (panels.some((one) => one.key === 'files')) return 'files'
  return panels.length ? panels[0].key : ''
}

/** The panel asked for, where the environment has it, else the one it opens on. */
export function tabOf(env, asked) {
  return panelsOf(env).some((one) => one.key === asked) ? asked : defaultTab(env)
}

/**
 * The environments as a tree: one group per role, in the order the roles first come, each the
 * environments of that role at the top -- those derived from none here -- and each with those
 * derived from it under it. A derived environment is in its root's group, whatever its own role.
 *
 * @param {object[]} envs As the `envs` snapshot lists them.
 * @returns {{role: string, nodes: {env: object, depth: number, children: object[]}[]}[]}
 */
export function treeOf(envs) {
  const list = Array.isArray(envs) ? envs : []
  const ids = new Set(list.map((one) => one.id))
  const under = new Map()
  for (const env of list) {
    // One whose parent is not listed, or is itself, stands at the top.
    const parent = env.parent && env.parent !== env.id && ids.has(env.parent) ? env.parent : null
    if (!under.has(parent)) under.set(parent, [])
    under.get(parent).push(env)
  }
  const seen = new Set()
  const node = (env, depth) => {
    seen.add(env.id)
    // A parent loop is cut where it would come round again.
    const children = (under.get(env.id) || []).filter((one) => !seen.has(one.id)).map((one) => node(one, depth + 1))
    return { env, depth, children }
  }
  const groups = []
  const byRole = new Map()
  for (const env of under.get(null) || []) {
    const role = env.role || ''
    if (!byRole.has(role)) {
      const group = { role, nodes: [] }
      byRole.set(role, group)
      groups.push(group)
    }
    byRole.get(role).nodes.push(node(env, 0))
  }
  // What is left was only ever in a loop of parents: shown at the top of its own role.
  for (const env of list) {
    if (seen.has(env.id)) continue
    const role = env.role || ''
    if (!byRole.has(role)) {
      const group = { role, nodes: [] }
      byRole.set(role, group)
      groups.push(group)
    }
    byRole.get(role).nodes.push(node(env, 0))
  }
  return groups
}

/** The tree in the order it is drawn, each environment with how deep it is. */
export function flatten(groups) {
  const rows = []
  const walk = (node) => {
    rows.push({ env: node.env, depth: node.depth })
    for (const one of node.children) walk(one)
  }
  for (const group of groups) for (const node of group.nodes) walk(node)
  return rows
}

/** Whether an environment can be worked in: there, and not closed. */
export function usable(env) {
  return Boolean(env && env.available !== false && env.open !== false)
}

/**
 * Why an environment cannot be worked in, in a word: `closed` where it has closed, which the host
 * also tells as out of reach; `unavailable` where it is open and cannot be reached; else nothing.
 */
export function offOf(env) {
  if (usable(env)) return ''
  return env && env.open === false ? 'closed' : 'unavailable'
}

/**
 * Which environment is shown: the one asked for where it is listed; else the first usable one
 * at the top of the latest run; else the first usable; else the first.
 */
export function pick(envs, asked) {
  const list = Array.isArray(envs) ? envs : []
  if (asked) {
    const named = list.find((one) => one.id === asked)
    if (named) return named
  }
  const latest = Math.max(0, ...list.map((one) => Number(one.run) || 0))
  return (
    list.find((one) => usable(one) && !one.parent && (Number(one.run) || 0) === latest) ||
    list.find(usable) ||
    list[0] ||
    null
  )
}

/** An environment's name in the tree: its chain where it says one, else its role. */
export function nameOf(env) {
  if (!env) return ''
  const chain = String(env.chain || '')
  return chain || env.role || env.id
}

/** A size given in bytes, or already in words. */
function sized(value) {
  if (typeof value === 'string') return value
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return ''
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  let at = 0
  let left = value
  while (left >= 1024 && at < units.length - 1) {
    left /= 1024
    at++
  }
  return `${Number.isInteger(left) ? left : left.toFixed(1)} ${units[at]}`
}

/** What an environment runs on, in words: CPUs, memory and GPUs, each where it is known. */
export function factsOf(env) {
  const facts = (env && env.facts) || {}
  const said = []
  if (facts.cpu) said.push(t('{n} CPUs', { n: facts.cpu }))
  const memory = sized(facts.memory)
  if (memory) said.push(t('{size} memory', { size: memory }))
  if (facts.gpu_count) {
    const each = sized(facts.gpu_memory)
    said.push(`${t('{n} GPUs', { n: facts.gpu_count })}${each ? ` · ${each}` : ''}`)
  }
  return said
}

/** What a frontend did in an environment, as its `env_used` record says it, in one line. */
export function usedLine(record, envs) {
  const env = (Array.isArray(envs) ? envs : []).find((one) => one.id === record.env)
  const where = env ? env.role || nameOf(env) : record.env
  return [record.by || t('someone'), record.what, record.path, where ? t('in {name}', { name: where }) : ''].filter(Boolean).join(' ')
}

/** The methods that name a terminal rather than an environment, which are not told `env`. */
export const TERMINAL_ONLY = new Set(['env.term.input', 'env.term.resize', 'env.term.ack', 'env.term.close'])

/** A call's params, as the frame makes them: the environment told, but to a terminal's own methods. */
export function paramsOf(method, params, env) {
  const made = { ...(params || {}) }
  if (TERMINAL_ONLY.has(method)) delete made.env
  else made.env = env
  return made
}

/** How wide a list may be dragged, in pixels: `least` at least, and `most` where that is more. */
export function clampWidth(width, most, least = 160) {
  return Math.round(Math.min(Math.max(least, Number(most) || 0), Math.max(least, Number(width) || 0)))
}

/** Whether a key asks for the menu of what the keys are on: the menu key, or Shift+F10. */
export function menuKey(event) {
  return event.key === 'ContextMenu' || (event.key === 'F10' && event.shiftKey)
}
