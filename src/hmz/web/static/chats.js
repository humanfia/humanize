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

/** Where a chat or an epic is on the page: `/chats/<id>`, or `/epics/<name>`. */
export function pathOf(run) {
  return `/${run.kind === 'chat' ? 'chats' : 'epics'}/${encodeURIComponent(run.name)}`
}

/** The most characters a chat's title holds (Section 4.25.7.2 of protocol/daemon.md). */
export const TITLE_MOST = 240

/**
 * A title as typed, as `chat.rename` records one: its runs of white space single spaces, none
 * at either end, cut at the most a title holds -- '' for one of white space alone, which is no
 * title.
 */
export function titled(typed) {
  return String(typed || '').replace(/\s+/g, ' ').trim().slice(0, TITLE_MOST)
}

/** Where a chat's assistant works, where that is not its workspace -- its worktree -- else ''. */
export function worksIn(chat) {
  return chat.workdir && chat.workdir !== chat.workspace ? chat.workdir : ''
}

/** What deleting a chat does, as it is said before it is done (Section 8.10.4 of protocol/core.md). */
export const DELETING = 'This permanently removes the chat’s record and the sessions kept with it, and cannot be undone. A worktree it worked in is left on disk.'

/** Why a new chat cannot be started in a worktree, by what is known of its folder. */
export const NO_WORKTREE = { none: 'A worktree needs a folder', plain: 'This folder is not a git repository' }

/**
 * Whether a folder is in a git repository, as far as the daemon's listing of directories tells:
 * `true` where it or a directory over it holds `.git` -- a directory, or the file a worktree
 * keeps in its place, which is refused as no directory -- `false` where each is refused as not
 * there, and `null` where that cannot be told: a folder not read, or a `.git` refused otherwise.
 *
 * @param {(at: string) => Promise<{whole: string}>} list Lists a directory, as `paths.list` does.
 * @param {string} folder The folder.
 */
export async function inRepository(list, folder) {
  let whole = ''
  try {
    whole = (await list(folder)).whole
  } catch {
    return null
  }
  if (!whole.startsWith('/')) return null
  // The folder and every directory over it, the root last.
  const over = []
  for (let at = whole.replace(/\/+$/, ''); ; at = at.slice(0, at.lastIndexOf('/'))) {
    over.push(at)
    if (!at) break
  }
  const held = await Promise.all(
    over.map((at) =>
      list(`${at}/.git`).then(
        () => true,
        (error) => (/not a directory/i.test(error.message) ? true : /no such file/i.test(error.message) ? false : null),
      ),
    ),
  )
  return held.includes(true) ? true : held.includes(null) ? null : false
}
