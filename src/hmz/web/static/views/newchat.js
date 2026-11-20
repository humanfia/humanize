// A new chat, as a chat app opens a new session: a plain heading in the bar, the chats that wait
// on their person listed in the middle, and the box the first message is typed into docked at
// the foot of the page, which Enter sends to start it. Under the box, at its left, where the
// chat runs, on one chip, `Environment` -- the daemon, the folder, and whether in a worktree of
// it -- and at its right how -- the model that answers it, starting from the chat agent that
// workspace remembers, and what it may touch (Sections 3.8.18 and 3.8.21 to 3.8.23 of
// protocol/web.md). A new epic of a flow is a form of its own
// (views/new.js), which the sidebar opens beside this one.

import { call, daemon, given, hash, poll } from '../api.js'
import { NO_WORKTREE, chatRow, inRepository, pathOf } from '../chats.js'
import { covered, focusing, go, stays } from '../app.js'
import { environmentChip } from '../chips/environment.js'
import { modelChip } from '../chips/model.js'
import { composer } from '../composer.js'
import { NO_FOLDER, dismissing, nextSteps, stepKey } from '../desk.js'
import { fill, h, headline, iconButton, problem } from '../dom.js'
import { t } from '../i18n.js'
import { markOf, waitsOn } from '../epic.js'
import { permissionChip } from '../chips/permission.js'
import { usageChip } from '../chips/usage.js'
import { chatAsk } from '../held.js'
import { readBackends } from '../pickers.js'
import { firstWorkspace, folderFiles, goneNote, goneSaid, missing, unplaced, workspacePicker, workspaces } from '../places.js'
import { bar, choice, keep, kept } from '../shell.js'

export function mount(root, { query }) {
  // Where the chat works: the workspace the address names, or none -- a directory of its own made
  // as it starts, offered the agent remembered where `hmz web` started.
  let scratch = query.get('scratch') === '1'
  let workspace = scratch ? '' : query.get('workspace') || ''
  const place = workspacePicker(scratch ? null : workspace, (path) => {
    scratch = path === null
    workspace = path || ''
    load('')
    // Gone since, or back: the form says so, or reads what the folder remembers again.
  }, { none: true, hosted: true, went: (lost) => !scratch && lost !== gone && load('') })
  const permission = permissionChip({ up: true })
  // Whether the chat works in a new git worktree of its folder, as a chat app's session may:
  // a row of Environment's menu that is ticked, not on offer with no folder, nor in one known
  // to be no git repository.
  let inWorktree = false
  /** Why a worktree is not on offer, or '' where it is. */
  let unoffered = ''
  /** The row as the menu open now draws it, if any. */
  let worktree = null
  function worktreeRow() {
    // Ticked, the menu stays: it says so on the row.
    const row = choice({
      label: t('Worktree'),
      chosen: inWorktree,
      glyph: 'fork',
      act: () => {
        if (unoffered) return
        inWorktree = !inWorktree
        redrawn(true)
      },
      close: () => {},
    })
    row.setAttribute('role', 'menuitemcheckbox')
    row.setAttribute('aria-checked', String(inWorktree))
    row.dataset.hmz = 'new-worktree'
    // Said, not switched off: a row that cannot be reached says nothing of why.
    if (unoffered) {
      row.setAttribute('aria-disabled', 'true')
      row.dataset.tip = unoffered
    }
    return (worktree = row)
  }
  /** Draws the row again where a menu shows it, keeping the keys on it. */
  function redrawn(held = document.activeElement === worktree) {
    const was = worktree
    if (!was || !was.isConnected) return
    was.replaceWith(worktreeRow())
    if (held) worktree.focus()
  }
  /** Says whether a worktree is on offer, and why not where it is not. */
  const offered = (why) => {
    unoffered = why
    if (why) inWorktree = false
    redrawn()
  }
  offered(scratch ? NO_WORKTREE.none : '')
  // Before a chat there is no catalogue to complete from: `@` names a file of the folder.
  // A chat of no folder works in a directory made as it starts, which holds nothing to name yet.
  const files = folderFiles(() => (scratch ? '' : workspace))
  // What the folder has used, where a chat begun says what it has (Section 3.8.22 of protocol/web.md).
  const usage = usageChip({ hmz: 'new-usage', tip: 'What this folder has used', workspace: () => (scratch ? '' : workspace || '') })
  const box = composer({
    placeholder: 'Message',
    label: 'First message',
    busy: 'Starting…',
    submit: (task) => start(task),
    complete: files.complete,
    // So Add offers the files alone: what `/`, `$` and `!` start is the chat's host's to say.
    desk: { add: ['files'], able: () => (scratch || !workspace ? NO_FOLDER : ''), left: [environmentChip('/new/chat', { place, rows: worktreeRow }).node], right: [permission.node, usage.node] },
  })
  box.node.dataset.hmz = 'start'
  const steps = h('section', { class: 'next-steps', 'aria-label': 'Next steps', 'data-hmz': 'next-steps', hidden: true })
  fill(
    root,
    h('div', { class: 'view view-new view-desk', 'data-hmz': 'new-chat' }, bar({ title: 'New chat' }), h('div', { class: 'desk-body' }, steps), h('div', { class: 'dock desk-dock' }, box.node)),
  )

  // The chats of this daemon that wait on their person, each opened by its row, and dismissed
  // from the list in this browser until it asks again.
  let chats = []
  /** What each host runs, which says what a chat going waits on. */
  let running = []
  const DISMISSED = 'hmz-next-dismissed'
  const dismissed = () => {
    try {
      return JSON.parse(kept(DISMISSED, '[]')) || []
    } catch {
      return []
    }
  }
  // What a chat waits on: what its host lists, or what this browser holds it owing once it lists none.
  const waits = (run) => waitsOn(run.name, run.asking || [])
  const keyOf = (run) => `${daemon()} ${stepKey(run, waits(run))}`
  function drawSteps() {
    const waiting = nextSteps(
      chats.map((one) => chatRow(one, running)),
      () => true,
      (run) => markOf(run.how, { chat: true, turn: run.turn, asked: run.asking || [], epic: run.name }),
      dismissed().filter((one) => one.startsWith(`${daemon()} `)).map((one) => one.slice(daemon().length + 1)),
      waits,
    )
    steps.hidden = !waiting.length
    // The list alone, as a chat app draws it: what it is is said to whoever cannot see it.
    fill(
      steps,
      h(
        'ul',
        {},
        waiting.map((run) =>
          h(
            'li',
            { class: 'next-step', 'data-hmz': 'next-step', 'data-epic': run.name },
            h('a', { href: hash(pathOf(run)), title: run.task }, h('span', { class: 'dot waiting', role: 'img', 'aria-label': 'Waiting' }), h('span', { class: 'next-title' }, headline(run.task)), h('span', { class: 'next-state' }, 'Asked a question')),
            iconButton('close', 'Dismiss', {
              'data-hmz': 'next-dismiss',
              onclick: () => {
                keep(DISMISSED, JSON.stringify(dismissing(dismissed(), keyOf(run))))
                drawSteps()
              },
            }),
          ),
        ),
      ),
    )
  }
  // As many as `chat.list` answers at once: a chat waits while a host holds it, or was left lately.
  const unlisted = poll('chat.list', { limit: 200 }, 4000, (answer) => {
    if (!answer) return
    chats = answer.chats || []
    drawSteps()
  })
  const unheld = poll('hosts.running', {}, 4000, (answer) => {
    if (!answer) return
    running = answer.running
    drawSteps()
  })
  // Looked at in its own view, a chat waits on nobody any more.
  window.addEventListener('hmz:seen', drawSteps)

  /** The chip the assistant's agent is picked from, as drawn last, if any. */
  let picker = null
  /** Which workspace was read last: one read after another was picked draws nothing. */
  let loading = ''
  /** Whether the directory of the folder picked is gone: nothing is read of it, and nothing started in it. */
  let gone = false

  /** Reads the CLIs here and the chat agent a workspace remembers, and sets the agent up from it. */
  async function load(agent) {
    const mine = (loading = scratch ? 'none' : workspace || 'here')
    // Asked for now: what takes the focus while this is read keeps it.
    const focus = focusing()
    fill(box.said)
    files.clear()
    picker?.node.classList.add('stale')
    try {
      // Never one that went: the first that is there, which the control then names.
      if (!workspace) {
        workspace = await firstWorkspace()
        if (!scratch) place.set(workspace)
      }
      // One the address named, or picked and gone since, stays picked and is said to be gone,
      // rather than swapped for a folder nobody asked for. Unread, the daemon says so itself.
      gone = !scratch && missing(workspace, await workspaces().catch(() => null))
      if (mine !== loading) return
      if (gone) {
        offered(NO_WORKTREE.none)
        fill(box.said, goneNote(workspace))
        return
      }
      offered(scratch ? NO_WORKTREE.none : '')
      // Told apart from what the agent is read by: a folder no repository is found over offers none.
      if (!scratch)
        inRepository((at) => call('paths.list', { at }), workspace).then((found) => {
          if (mine === loading && found === false) offered(NO_WORKTREE.plain)
        })
      // The address of a dialog opened over it is the dialog's own.
      if (!covered()) stays({ workspace: scratch ? '' : workspace, scratch: scratch ? '1' : '' })
      const [, settings] = await Promise.all([readBackends(workspace), call('settings.get', { workspace }).catch(() => null)])
      if (mine !== loading) return
      draw(agent || (settings && settings.chat) || (picker ? picker.value() : ''), focus)
    } catch (error) {
      if (mine !== loading) return
      fill(box.said, problem(error))
    } finally {
      if (mine === loading) picker?.node.classList.remove('stale')
    }
  }
  load(query.get('agent') || '')

  function draw(kept, focus) {
    const was = picker
    was?.leave()
    picker = modelChip('assistant', kept)
    // Under the box, at its right, before what it may touch.
    if (was) was.node.replaceWith(picker.node)
    else box.tray.prepend(picker.node)
    // Typed into next -- but not from under a dialog opened over it, out of what is typed there,
    // nor out of Ai-chan's drawer beside it, nor out of what took the focus while this was read.
    focus(box.text)
  }

  async function start(task) {
    if (gone) throw new Error(goneSaid(workspace))
    const agent = picker ? picker.value() : ''
    if (!agent) {
      picker?.open()
      throw new Error('Pick a nous for the chat.')
    }
    // A new chat's own host, beside every epic here; the agent is remembered for the next.
    const started = await chatAsk(workspace, 'start', { agent, task, permission: permission.value(), worktree: inWorktree && !unoffered, remember: !scratch, scratch }).catch((error) => {
      throw unplaced(error, workspace)
    })
    go(`/live?${new URLSearchParams(given({ workspace: started.workspace, slot: started.slot }))}`)
  }

  // Back from making an account, the picker offers it.
  const back = () => {
    if (!location.hash.startsWith(hash('/settings'))) readBackends(workspace).catch(() => {})
  }
  window.addEventListener('hashchange', back)
  return () => {
    // Left, what is still being read draws nothing.
    loading = null
    unlisted()
    unheld()
    window.removeEventListener('hmz:seen', drawSteps)
    window.removeEventListener('hashchange', back)
    place.leave()
    picker?.leave()
  }
}
