// A chat's permission as the page says it, nothing drawn: the three presets a chat's assistant
// can be held to (Section 8.3.9 of protocol/core.md), each with the name and the one line the
// chip's menu gives it, and which of them a chat's chip shows.

/** The permission of a chat nobody gave another. */
export const DEFAULT = 'workspace-write'

/** The permissions a chat is offered, narrowest first, as the daemon names and holds them. */
export const MODES = [
  { value: 'read-only', label: 'Read only', about: 'Reads and runs commands, changes no file' },
  { value: 'workspace-write', label: 'Edit this folder', about: 'Changes files in this folder only' },
  { value: 'danger-full-access', label: 'Full access', about: 'Changes files anywhere on this machine' },
]

/** What the menu says under them: why none of them asks before acting. */
export const NOTE = 'The assistant acts without asking first. What it may touch is what holds it.'

/** The mode a permission names, or the default's for one that names none. */
export function modeOf(permission) {
  return MODES.find((one) => one.value === permission) || MODES.find((one) => one.value === DEFAULT)
}

/** The modes as a menu offers them, the one in force marked. */
export function offered(permission) {
  const now = modeOf(permission).value
  return MODES.map((one) => ({ ...one, chosen: one.value === now }))
}

/**
 * The permission a chat's chip shows: the one picked here for a chat to be carried on with,
 * else what its host says, else what its epic records, else the default. None -- `null` --
 * for a chat whose host says it has none to set, which is an Ai-chan conversation.
 *
 * @param {object} of
 * @param {string|null} [of.picked] What was picked here and not yet taken by a host.
 * @param {{permission?: string|null}|null} [of.host] What `chat.commands` answered, if it has.
 * @param {{permission?: string}|null} [of.epic] The epic as `runs.get` answers it.
 * @returns {string|null}
 */
export function shown({ picked = null, host = null, epic = null } = {}) {
  if (host && host.permission === null) return null
  if (picked) return modeOf(picked).value
  if (host && host.permission) return modeOf(host.permission).value
  return modeOf(epic && epic.permission).value
}
