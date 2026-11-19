// A chat and an epic as the page's lists and views read them, apart from how they are drawn. A
// chat is no epic: it is listed and read by `chat.*`, by its id, and an epic by `runs.*`, by its
// name (Section 3.5.20 of protocol/web.md). Each is read here into one shape of row, marked by
// its `kind`, so that the sidebar, Search and the view of a conversation draw the two alike
// where they are alike. An epic an earlier hmz recorded for a chat is an epic like any other, of
// the flow `chat`, and only read. Nothing here touches the page, so it is read the same by the
// views and by their tests.

/**
 * A chat as `chat.list` rows it, as a row of the page's lists: named by its id, told by its
 * title, of the kind `chat`, going while a host or another process holds it, with its turn as
 * its state says it. What it waits on is what its host says it does (`hosts.running`), where
 * one holds it: its reply between turns among them, which the row leaves out.
 *
 * @param {object} chat The row.
 * @param {{chat?: string, asking?: string[]}[]} [running] What each host runs.
 */
export function chatRow(chat, running = []) {
  const held = chat.state !== 'resting' && chat.state !== 'failed'
  const open = chat.state === 'turn' || chat.state === 'asking'
  const host = chat.slot ? running.find((one) => one.chat === chat.id) : null
  return {
    ...chat,
    name: chat.id,
    kind: 'chat',
    flow: '',
    task: chat.title,
    // When it was last heard of, by which a chat resting is sorted.
    ended: held ? '' : chat.updated,
    how: held ? 'running' : chat.state === 'failed' ? 'failed' : 'stopped',
    turn: chat.slot ? (open ? 'running' : 'done') : '',
    held: Boolean(chat.slot),
    asking: host ? host.asking || [] : chat.asking || [],
    agents: chat.agent ? [{ name: 'assistant', role: 'assistant', runs: chat.agent }] : [],
    resumable: false,
  }
}

/**
 * A chat as `chat.get` answers it, as the view of a conversation reads an epic: its row, its
 * first message as its task, and carried on by saying something in it while it rests.
 */
export function chatDetail(chat) {
  return {
    ...chatRow(chat),
    task: chat.task,
    agents: chat.agents,
    sessions: chat.sessions,
    picks_up: chat.state === 'resting',
    foreign: '',
    used: [],
    calls: [],
    params: {},
    budget: null,
    picked_up: '',
  }
}

/**
 * An epic as `runs.list` and `runs.get` answer it. One an earlier hmz recorded for a chat is of
 * no flow there: it is an epic of the flow `chat` here, and is only read.
 */
export function epicRow(row) {
  if (row.kind !== 'chat') return row
  return { ...row, kind: 'flow', flow: 'chat', resumable: false, ...('picks_up' in row ? { picks_up: false } : {}) }
}

/**
 * A session a harness had of its own, as `chat.harness.list` rows it, as a row of the sidebar's
 * list: of the kind `harness`, named by its harness and its id, told by the first line said in
 * it or, where its log gave none, by its id; never going, and only read.
 */
export function harnessRow(one) {
  return {
    ...one,
    name: `harness:${one.harness}:${one.id}`,
    kind: 'harness',
    flow: '',
    task: one.title || one.id,
    ended: one.updated,
    how: 'stopped',
    held: false,
  }
}

/** Where a chat, an epic or a harness session is on the page: `/chats/<id>`, `/epics/<name>`, or `/harness/<harness>/<id>` with its workspace. */
export function pathOf(run) {
  if (run.kind === 'harness') return `/harness/${encodeURIComponent(run.harness)}/${encodeURIComponent(run.id)}?workspace=${encodeURIComponent(run.workspace)}`
  return `/${run.kind === 'chat' ? 'chats' : 'epics'}/${encodeURIComponent(run.name)}`
}
