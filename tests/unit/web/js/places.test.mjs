import assert from 'node:assert/strict'
import { after, test } from 'node:test'

import { daemon, provider, until } from './helpers.mjs'
import { page } from './page.mjs'

const { body, el, press, key } = page()

/** What the daemon lists: one workspace, until a test says otherwise. */
const ONE = { here: '', workspaces: [{ name: 'app', path: '/w/app' }] }
let listed = ONE
/** The runtimes the daemon has saved, until a test says otherwise. */
let runtimes = []
const served = daemon({
  methods: {
    'workspaces.list': () => listed,
    'runtimes.list': () => ({ runtimes }),
    'paths.list': ({ at }) => ({ at: at || '~', whole: at || '/home/me', up: '', entries: [], more: 0 }),
    'paths.complete': () => ({ paths: [] }),
  },
})
const api = await import('../../../../src/hmz/web/static/api.js')
api.providers.splice(0, api.providers.length, provider(served))
const { chain, dismiss, opened } = await import('../../../../src/hmz/web/static/layers.js')
const { firstOf, firstWorkspace, folderOf, goneSaid, lostSaid, missing, unplaced, workspacePicker, workspaces } = await import('../../../../src/hmz/web/static/places.js')

after(async () => (await api.client('local')).close())

/** The folder picker in the page, its menu's `Open folder…` picked. */
async function opening(offers) {
  const made = workspacePicker('/w/app', () => {}, offers)
  body.append(made.node)
  const button = made.node.querySelector('[data-hmz=workspace-picker]')
  const form = made.node.querySelector('form')
  await until(() => button.textContent === 'app')
  button.box = { left: 1168, top: 8, width: 112, height: 28 }
  button.click()
  made.menuLeft = made.node.querySelector('[role=menu]').style.left
  made.node.querySelectorAll('[role=menuitem]').find((one) => one.textContent === 'Open folder…').click()
  return { ...made, button, form, field: form.querySelector('input') }
}

test('the form a folder is opened by takes the place of the menu it was picked from', async () => {
  const made = await opening()
  assert.equal(made.form.hidden, false)
  assert.equal(made.node.querySelector('[role=menu]'), null)
  assert.equal(chain().length, 1)
  assert.equal(made.button.getAttribute('aria-expanded'), 'true')
  assert.equal(document.activeElement, made.field)
  // The button pressed again shuts it, and opens no menu behind it.
  made.button.click()
  assert.equal(made.form.hidden, true)
  assert.equal(made.node.querySelector('[role=menu]'), null)
  assert.equal(made.button.getAttribute('aria-expanded'), 'false')
  assert.equal(chain().length, 0)
  // Shut, the button opens its menu again.
  made.button.click()
  assert.ok(made.node.querySelector('[role=menu]'))
  dismiss('route')
  made.leave()
  made.node.remove()
})

test('the form closes as a menu does, from wherever in it the focus is, and keeps what is typed while the window is left', async () => {
  const made = await opening()
  made.field.value = '~/work'
  for (const why of ['blur', 'resize']) dismiss(why)
  assert.equal(made.form.hidden, false)
  made.form.querySelector('[type=submit]').focus()
  key('Escape')
  assert.equal(made.form.hidden, true)
  assert.equal(document.activeElement, made.button)
  made.leave()
  made.node.remove()
  for (const closes of [() => press(body), () => dismiss('route'), () => dismiss('dialog'), () => opened({ node: el('div'), anchor: el('button'), close() {} })]) {
    const next = await opening()
    closes()
    assert.equal(next.form.hidden, true)
    assert.equal(next.button.getAttribute('aria-expanded'), 'false')
    dismiss('route')
    next.leave()
    next.node.remove()
  }
})

/** Has the daemon list other workspaces, and waits until whoever watches them was told. */
async function lists(answer) {
  listed = answer
  api.refresh('workspaces.list')
  let seen
  const stop = api.poll('workspaces.list', {}, null, (data) => (seen = data))
  await until(() => JSON.stringify(seen) === JSON.stringify(answer))
  stop()
}

/** A row of `workspaces.list`. */
const row = (name, there) => ({ name, path: `/w/${name}`, ...(there === undefined ? {} : { there }) })

test('the workspace offered first is never one whose directory is gone', () => {
  // Where `hmz web` started, while it is there; a daemon that says nothing of `there` means it is.
  assert.equal(firstOf({ here: '/w/here', workspaces: [row('here'), row('app')] }), '/w/here')
  assert.equal(firstOf({ here: '/w/here', workspaces: [row('app')] }), '/w/here')
  // Gone, it is passed over for the first listed that is there.
  assert.equal(firstOf({ here: '/w/here', workspaces: [row('here', false), row('old', false), row('app', true), row('next', true)] }), '/w/app')
  assert.equal(firstOf({ here: '', workspaces: [row('old', false), row('app')] }), '/w/app')
  // None there, or none at all: the user's home.
  assert.equal(firstOf({ here: '/w/here', workspaces: [row('here', false), row('old', false)] }), '~')
  assert.equal(firstOf({ here: '', workspaces: [] }), '~')
})

test('a directory is missing only where the daemon listed it and said it is not there', () => {
  const answer = { workspaces: [row('app', true), row('old', false), row('plain')] }
  assert.equal(missing('/w/old', answer), true)
  for (const path of ['/w/app', '/w/plain', '/w/unlisted', '', null]) assert.equal(missing(path, answer), false)
  assert.equal(missing('/w/old', null), false)
})

test('a start refused for a directory that is gone is said as the form says it', () => {
  const gone = new api.Refused('There is no directory /w/old.', 404)
  assert.equal(unplaced(gone, '/w/old').message, 'The folder old is no longer on this machine. Pick another folder.')
  assert.equal(unplaced(gone, '/w/old').message, goneSaid('/w/old'))
  // A chat carried on there has no other to pick.
  assert.equal(unplaced(gone, '/w/old', lostSaid).message, 'The folder old is no longer on this machine.')
  // Any other refusal keeps its own words.
  for (const other of [new api.Refused('No such flow.', 404), new api.Refused('There is no directory /w/old.', 400), new Error('Unreachable.')]) assert.equal(unplaced(other, '/w/old'), other)
})

test('the first workspace is read again, so that one gone since is not offered', async () => {
  try {
    listed = { here: '', workspaces: [row('old', false), row('app', true)] }
    await workspaces(true)
    assert.equal(await firstWorkspace(), '/w/app')
    listed = { here: '', workspaces: [row('old', false), row('app', false)] }
    await workspaces(true)
    assert.equal(await firstWorkspace(), '~')
  } finally {
    listed = ONE
    await workspaces(true)
  }
})

test('the menu lists the folders that are there, and the one chosen though it is gone, said to be missing', async () => {
  await lists({ here: '', workspaces: [row('app', true), row('old', false), row('lost', false)] })
  const made = workspacePicker('/w/old', () => {}, { plain: true })
  body.append(made.node)
  const button = made.node.querySelector('[data-hmz=workspace-picker]')
  try {
    await until(() => made.gone())
    assert.equal(button.textContent, 'old (missing)')
    assert.equal(button.getAttribute('aria-invalid'), 'true')
    assert.ok(button.classList.contains('gone'))
    assert.equal(button.dataset.tip, 'This folder is no longer on this machine: /w/old')
    button.click()
    const rows = made.node.querySelectorAll('[role=menuitem]')
    assert.deepEqual(rows.map((one) => one.textContent), ['app', 'oldMissing', 'Open folder…'])
    assert.ok('missing' in rows[1].dataset)
    dismiss('route')
    // Another picked, the one that is gone is offered no more.
    rows[0].click()
    assert.equal(made.gone(), false)
    assert.equal(button.textContent, 'app')
    assert.equal(button.getAttribute('aria-invalid'), null)
    button.click()
    assert.deepEqual(made.node.querySelectorAll('[role=menuitem]').map((one) => one.textContent), ['app', 'Open folder…'])
    dismiss('route')
  } finally {
    made.leave()
    made.node.remove()
    await lists(ONE)
  }
})

test('a folder chosen that goes while the picker stands is said to be gone, and to be back', async () => {
  const told = []
  /** What `workspaces` answers of the folder as the picker says it went or came back, as a form reads it then. */
  const read = []
  // Read a moment before it goes: an answer the forms would still take for fresh.
  await workspaces(true)
  const made = workspacePicker('/w/app', () => {}, { went: (gone) => (told.push(gone), read.push(workspaces().then((answer) => missing('/w/app', answer)))) })
  body.append(made.node)
  const button = made.node.querySelector('[data-hmz=workspace-picker]')
  try {
    await until(() => button.textContent === 'app')
    assert.equal(made.gone(), false)
    await lists({ here: '', workspaces: [row('app', false)] })
    await until(() => made.gone())
    assert.equal(button.textContent, 'app (missing)')
    await lists({ here: '', workspaces: [row('app', true)] })
    await until(() => !made.gone())
    assert.equal(button.textContent, 'app')
    assert.ok(!button.classList.contains('gone'))
    assert.deepEqual(told, [true, false])
    // Whoever is told reads the answer that said so, never one from before it.
    assert.deepEqual(await Promise.all(read), [true, false])
    // Left, it hears no more of the directories.
    made.leave()
    await lists({ here: '', workspaces: [row('app', false)] })
    await new Promise((resolve) => setTimeout(resolve, 30))
    assert.equal(made.gone(), false)
  } finally {
    made.leave()
    made.node.remove()
    await lists(ONE)
  }
})

test('a picker opened on no folder names the first that is there', async () => {
  await lists({ here: '/w/here', workspaces: [row('here', false), row('app', true)] })
  const made = workspacePicker('', () => {})
  try {
    await until(() => made.value() === '/w/app')
    assert.equal(made.gone(), false)
  } finally {
    made.leave()
    await lists(ONE)
  }
})

test('Folder is a chip of its own: the folders, opening one by its path, and no folder', async () => {
  await lists({ here: '', workspaces: [row('app', true), row('lib', true)] })
  const { folderChip } = await import('../../../../src/hmz/web/static/chips/environment.js')
  const picked = []
  const place = workspacePicker('/w/app', (path) => picked.push(path), { none: true, hosted: true })
  const made = folderChip(place)
  body.append(made.node)
  const button = made.node.querySelector('[data-hmz=folder]')
  const items = () => made.node.querySelector('[role=menu]').querySelectorAll('[role=menuitem]').map((one) => one.textContent)
  const choose = (said) => made.node.querySelectorAll('[role=menuitem]').find((one) => one.textContent === said).click()
  try {
    // No button of the folders' own: the chip is the one control.
    assert.equal(made.node.querySelector('[data-hmz=workspace-picker]'), null)
    // Named from the first, before the folders are read; then read, as the menu lists them.
    assert.equal(button.textContent, 'app')
    await until(() => place.rows(() => {}).flat(Infinity).some((one) => one && one.dataset.folder === '/w/lib'))
    assert.equal(button.getAttribute('aria-label'), 'Folder: app')
    assert.equal(button.dataset.tip, '/w/app')
    button.box = { left: 20, top: 800, width: 120, height: 24 }
    button.click()
    const menu = made.node.querySelector('[role=menu]')
    // Folders alone: no daemon, and nothing of where the chat works.
    assert.deepEqual(menu.querySelectorAll('.popover-head'), [])
    assert.deepEqual(menu.querySelectorAll('[data-daemon]'), [])
    assert.deepEqual(items(), ['No folder', 'app', 'lib', 'Open folder…'])
    // The keys are on the folder picked.
    assert.equal(document.activeElement.dataset.folder, '/w/app')
    // Another folder picked: the chip names it, and whoever keeps the form is told.
    choose('lib')
    assert.deepEqual(picked, ['/w/lib'])
    assert.equal(button.textContent, 'lib')
    assert.equal(made.node.querySelector('[role=menu]'), null)
    // No folder is a folder picked too.
    button.click()
    choose('No folder')
    assert.deepEqual(picked, ['/w/lib', null])
    assert.equal(button.textContent, 'No folder')
    assert.equal(button.getAttribute('aria-label'), 'Folder: No folder')
    // The form a folder is opened by takes the menu's place, by the chip, which shuts it.
    button.click()
    choose('Open folder…')
    const form = made.node.querySelector('form')
    assert.equal(form.hidden, false)
    assert.equal(made.node.querySelector('[role=menu]'), null)
    assert.equal(button.getAttribute('aria-expanded'), 'true')
    button.click()
    assert.equal(form.hidden, true)
    assert.equal(made.node.querySelector('[role=menu]'), null)
  } finally {
    dismiss('route')
    place.leave()
    made.node.remove()
    await lists(ONE)
  }
})

test('Folder says on its chip that the folder picked is gone', async () => {
  await lists({ here: '', workspaces: [row('app', true), row('old', false)] })
  const { folderChip } = await import('../../../../src/hmz/web/static/chips/environment.js')
  const place = workspacePicker('/w/old', () => {}, { none: true, hosted: true })
  const made = folderChip(place)
  body.append(made.node)
  const button = made.node.querySelector('[data-hmz=folder]')
  try {
    await until(() => place.gone())
    assert.equal(button.textContent, 'old (missing)')
    assert.equal(button.getAttribute('aria-invalid'), 'true')
    assert.ok(button.classList.contains('gone'))
    assert.equal(button.dataset.tip, 'This folder is no longer on this machine: /w/old')
    button.click()
    assert.ok('missing' in made.node.querySelectorAll('[role=menuitem]').find((one) => one.textContent === 'oldMissing').dataset)
    dismiss('route')
    place.set('/w/app')
    assert.equal(button.textContent, 'app')
    assert.equal(button.getAttribute('aria-invalid'), null)
    assert.ok(!button.classList.contains('gone'))
  } finally {
    dismiss('route')
    place.leave()
    made.node.remove()
    await lists(ONE)
  }
})

test('Daemon is which hmz serves the page, on a chip that names no folder and no environment', async () => {
  const { daemonChip } = await import('../../../../src/hmz/web/static/chips/environment.js')
  const made = daemonChip('/new')
  body.append(made.node)
  const button = made.node.querySelector('[data-hmz=daemon]')
  try {
    assert.equal(made.node.querySelector('[data-hmz=environment]'), null)
    assert.equal(button.textContent, 'Local')
    assert.equal(button.getAttribute('aria-label'), 'Daemon: Local')
    button.box = { left: 300, top: 100, width: 80, height: 24 }
    button.click()
    const menu = made.node.querySelector('[role=menu]')
    assert.equal(menu.querySelector('[data-hmz=daemon-about]').textContent, 'Which hmz serves this page: a machine running hmz that you are connected to.')
    assert.deepEqual(menu.querySelectorAll('[role=menuitem]').map((one) => one.textContent), ['Local', 'Add daemon…'])
    assert.ok(parseFloat(menu.style.top) >= 124)
  } finally {
    dismiss('route')
    made.node.remove()
  }
})

test('Environment is where a chat works: this computer, a new worktree, or a runtime and the directory there', async () => {
  const { envSaid, environmentChip } = await import('../../../../src/hmz/web/static/chips/environment.js')
  runtimes = [
    { backend: 'ssh', name: 'gpu-box', workdir: '~/proj' },
    { backend: 'docker', name: 'boxes', workdir: '' },
  ]
  let env = { backend: 'local', provider: '', workdir: '', worktree: false }
  let unoffered = ''
  const picked = []
  const made = environmentChip({
    now: () => env,
    home: () => '/w/app',
    pick: (to) => {
      picked.push(to)
      env = { worktree: false, ...to }
    },
    worktree: () => unoffered,
    folders: false,
  })
  body.append(made.node)
  const button = made.node.querySelector('[data-hmz=environment]')
  const rows = () => made.node.querySelector('[role=menu]').querySelectorAll('[role=menuitemradio], [role=menuitem]')
  const row = (key) => rows().find((one) => one.dataset.env === key)
  try {
    // It says where, never which daemon.
    assert.equal(button.textContent, 'This computer')
    assert.equal(button.getAttribute('aria-label'), 'Environment: This computer')
    assert.equal(button.dataset.env, 'local')
    await until(() => served.calls.some((one) => one.method === 'runtimes.list'))
    await new Promise((done) => setTimeout(done, 20))
    button.box = { left: 20, top: 800, width: 120, height: 24 }
    button.click()
    const menu = made.node.querySelector('[role=menu]')
    assert.equal(menu.querySelector('[data-hmz=environment-about]').textContent, 'Where this chat’s commands run and its files live.')
    assert.deepEqual(menu.querySelectorAll('[data-daemon]'), [])
    assert.deepEqual(menu.querySelectorAll('.popover-head').map((one) => one.textContent), ['Runtimes'])
    assert.deepEqual(rows().map((one) => one.querySelector('.choice-label').textContent), ['This computer', 'New worktree', 'gpu-box', 'boxes', 'Add runtime…'])
    assert.equal(row('local').getAttribute('aria-checked'), 'true')
    assert.equal(row('ssh@gpu-box').querySelector('.choice-about').textContent, 'SSH host · ~/proj')
    // A new worktree is one of the places, picked as any is.
    row('worktree').click()
    assert.equal(made.node.querySelector('[role=menu]'), null)
    await until(() => button.textContent === 'New worktree')
    assert.equal(picked.at(-1).worktree, true)
    // Not on offer, it says why and picks nothing.
    unoffered = 'This folder is not a git repository'
    env = { backend: 'local', provider: '', workdir: '', worktree: false }
    made.again()
    button.click()
    assert.equal(row('worktree').getAttribute('aria-disabled'), 'true')
    assert.equal(row('worktree').dataset.tip, 'This folder is not a git repository')
    row('worktree').click()
    assert.equal(picked.length, 1)
    // A runtime saved with a directory is picked at once, and the chip names both.
    row('ssh@gpu-box').click()
    await until(() => button.textContent === 'gpu-box · proj')
    assert.deepEqual(picked.at(-1), { backend: 'ssh', provider: 'gpu-box', workdir: '~/proj' })
    assert.equal(button.getAttribute('aria-label'), 'Environment: gpu-box, proj')
    assert.equal(button.dataset.env, 'ssh')
    // There, a directory is chosen as a folder is here: in a form, written or browsed for.
    button.click()
    const choose = rows().find((one) => one.dataset.hmz === 'env-dir-choose')
    assert.equal(choose.querySelector('.choice-about').textContent, '~/proj')
    choose.click()
    const form = made.node.querySelector('[data-hmz=env-dir-form]')
    assert.equal(form.hidden, false)
    assert.equal(form.querySelector('.label').textContent, 'Directory on gpu-box')
    const field = form.querySelector('input')
    assert.equal(field.value, '~/proj')
    // Browsed for on that machine: the listing names the runtime.
    form.querySelector('[data-hmz=path-browse]').click()
    await until(() => served.calls.some((one) => one.method === 'paths.list' && one.params.env === 'ssh@gpu-box'))
    field.value = '/srv/other'
    const sent = new Event('submit')
    sent.preventDefault = () => {}
    form.dispatchEvent(sent)
    await until(() => form.hidden)
    assert.deepEqual(picked.at(-1), { backend: 'ssh', provider: 'gpu-box', workdir: '/srv/other' })
    assert.equal(button.textContent, 'gpu-box · other')
    // A runtime saved with none asks for one before anything is picked.
    const before = picked.length
    button.click()
    row('docker@boxes').click()
    assert.equal(form.hidden, false)
    assert.equal(form.querySelector('.label').textContent, 'Directory on boxes')
    assert.equal(picked.length, before)
    button.click()
    assert.equal(form.hidden, true)
    // Said as the daemon spells it: this computer elsewhere than the folder names the directory.
    assert.deepEqual(envSaid({ backend: 'local', provider: '', workdir: '/w/else' }, '/w/app'), { glyph: 'computer', name: 'This computer', dir: 'else', tip: '/w/else' })
    assert.equal(envSaid({ backend: 'local', provider: '', workdir: '/w/app/' }, '/w/app').dir, '')
  } finally {
    dismiss('route')
    made.node.remove()
    runtimes = []
  }
})

test('Environment picks nothing while a turn is open, and says why', async () => {
  const { environmentChip } = await import('../../../../src/hmz/web/static/chips/environment.js')
  const picked = []
  const refused = []
  let why = 'A turn is open. Move the chat once it is done.'
  const made = environmentChip({
    now: () => ({ backend: 'local', provider: '', workdir: '/w/else' }),
    home: () => '/w/app',
    pick: (to) => {
      picked.push(to)
      throw new Error('The chat stays where it was: no such directory')
    },
    failed: (error) => refused.push(error.message),
    busy: () => why,
  })
  body.append(made.node)
  const button = made.node.querySelector('[data-hmz=environment]')
  const row = (key) => made.node.querySelector('[role=menu]').querySelectorAll('[role=menuitemradio]').find((one) => one.dataset.env === key)
  try {
    // A chat begun elsewhere on this computer names the directory after it.
    assert.equal(button.textContent, 'This computer · else')
    button.click()
    assert.equal(made.node.querySelector('[data-hmz=environment-about]').textContent, why)
    assert.equal(row('local').getAttribute('aria-disabled'), 'true')
    row('local').click()
    assert.deepEqual(picked, [])
    dismiss('route')
    // Between turns it is moved, and what the daemon refuses is the caller's to say.
    why = ''
    button.click()
    assert.equal(row('local').getAttribute('aria-checked'), 'false')
    row('local').click()
    await until(() => refused.length === 1)
    assert.deepEqual(picked, [{ backend: 'local', provider: '', workdir: '/w/app' }])
    assert.deepEqual(refused, ['The chat stays where it was: no such directory'])
  } finally {
    dismiss('route')
    made.node.remove()
  }
})

/** A hosted picker bound to a button of another's, which holds its form beside it. */
function hosting(chosen) {
  const made = workspacePicker(chosen, () => {}, { hosted: true })
  const button = el('button')
  const holder = el('div')
  holder.append(button, made.node)
  body.append(holder)
  const told = []
  made.bind(button, { align: 'start', up: true }, (now) => told.push(now))
  return { ...made, button, holder, told, form: made.node }
}

test('a hosted picker’s form is its host’s button’s: closed, the focus goes back to it, and a press on it only shuts the form', async () => {
  const made = hosting('/w/app')
  const pick = () => [made.rows(() => {})].flat(Infinity).find((one) => one && one.textContent === 'Open folder…').click()
  try {
    pick()
    assert.equal(made.form.hidden, false)
    assert.equal(document.activeElement, made.form.querySelector('input'))
    key('Escape')
    assert.equal(made.form.hidden, true)
    assert.equal(document.activeElement, made.button)
    // A press on the button is a press inside: the form stands until the click, which shuts it
    // before anything else of the button's hears of it.
    pick()
    let heard = 0
    made.button.addEventListener('click', () => heard++)
    press(made.button)
    assert.equal(made.form.hidden, false)
    made.button.click()
    assert.equal(made.form.hidden, true)
    assert.equal(heard, 0)
    assert.equal(chain().length, 0)
    made.button.click()
    assert.equal(heard, 1)
  } finally {
    dismiss('route')
    made.leave()
    made.holder.remove()
  }
})

test('a hosted picker says the folder not read yet as the button does, never as an empty name', async () => {
  const made = hosting('')
  try {
    assert.deepEqual(made.told.map((now) => now.name), ['…'])
    await until(() => made.value() === '/w/app')
    assert.equal(made.told.at(-1).name, 'app')
  } finally {
    made.leave()
    made.holder.remove()
  }
})

test('the folder of an epic or a chat is named by the last part of its path, and No folder of a folderless one', () => {
  assert.equal(folderOf({ workspace: '/w/app' }), 'app')
  assert.equal(folderOf({ workspace: '/w/app', folderless: false }), 'app')
  // Never by the directory made for it.
  assert.equal(folderOf({ workspace: '/tmp/humanize-501/nofolder/tmpab12', folderless: true }), 'No folder')
})
