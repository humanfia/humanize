// What the sidebar's list says, apart from how it is drawn: its workspaces in their order, how a
// chat stands as a chat app says it, and the words a chat and a flow's epic each go by. Nothing
// here touches the page, so it is read the same by the sidebar and by its tests.

/**
 * Every workspace offered, each with its rows as they were listed, newest first: those with one
 * a host is going with first, then by their latest, newest first.
 *
 * @param {{path: string}[]} workspaces The workspaces the daemon keeps.
 * @param {{workspace: string, held?: boolean, began?: string}[]} runs The rows listed, newest first.
 * @returns {{path: string, runs: object[]}[]}
 */
export function grouped(workspaces, runs) {
  const groups = new Map()
  for (const one of workspaces || []) groups.set(one.path, { path: one.path, runs: [] })
  for (const run of runs || []) {
    if (!groups.has(run.workspace)) groups.set(run.workspace, { path: run.workspace, runs: [] })
    groups.get(run.workspace).runs.push(run)
  }
  return [...groups.values()].sort((a, b) => rank(b) - rank(a))
}

/** Where a workspace stands among the others: one going before any that is not, then its latest. */
function rank(group) {
  const live = group.runs.some((one) => one.held) ? 1e13 : 0
  const last = group.runs.length ? Date.parse(group.runs[0].began) || 0 : 0
  return live + last
}

/**
 * How a chat's row stands, from its mark: `working` while its agent answers, `asking` while it
 * waits on its person, `failed` where it failed, and '' once it only rests.
 *
 * @param {string} how The chat's mark.
 * @returns {'working' | 'asking' | 'failed' | ''}
 */
export function chatState(how) {
  if (how === 'running') return 'working'
  if (how === 'asking') return 'asking'
  return ['failed', 'refused', 'crashed'].includes(how) ? 'failed' : ''
}

/** A chat's state in words, for whoever cannot see its spinner or its dot. */
export const CHAT_SAID = { working: 'Working', asking: 'Needs you', failed: 'Failed' }

/**
 * What a row says when pointed at: all of what was asked, then, for a chat, how it stands and
 * when it began, and for a flow's epic its flow as well.
 *
 * @param {{task: string}} run The row.
 * @param {{chat: boolean, state?: string, how?: string, flow?: string, began: string}} of A chat's state, or an epic's mark and its flow's name, and when it began in words.
 */
export function rowTitle(run, { chat, state = '', how = '', flow = '', began }) {
  const said = chat ? [CHAT_SAID[state], began] : [flow, how, began]
  return `${run.task}\n${said.filter(Boolean).join(' · ')}`
}

/**
 * The words a row's menu goes by: a chat's never name an epic, a flow or a task.
 *
 * @param {boolean} chat Whether the row is a chat.
 */
export function wording(chat) {
  return chat
    ? { like: 'New chat like it', task: 'Copy first message', tasked: 'Message copied', name: 'Copy ID', named: 'ID copied' }
    : { like: 'New epic like it', task: 'Copy task', tasked: 'Task copied', name: 'Copy name', named: 'Name copied' }
}
