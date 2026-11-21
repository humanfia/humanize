import assert from 'node:assert/strict'
import { after, test } from 'node:test'

import { daemon, provider, until } from './helpers.mjs'
import { page } from './page.mjs'

const { body, el, key } = page()
// What a menu beside another reads of how it is drawn.
globalThis.getComputedStyle = () => ({ paddingTop: '6px', borderTopWidth: '1px' })

/** Twelve models by two routes each, as a harness that routes lists them: more than ten rows, two of every name. */
const ROUTED = ['azure_ai', 'vertex_ai'].flatMap((route) => [1, 2, 3, 4, 5, 6].map((n) => ({ name: `${route}/claude-opus-${n}`, efforts: n === 1 ? ['low', 'high'] : [] })))
/** The harnesses the daemon lists, as `flows.backends` answers them. */
const MANY = { litellm: { accounts: [{ name: '', asked: true, models: ROUTED }] }, claude: { accounts: [{ name: '', asked: true, models: [{ name: 'claude-haiku-4-5', efforts: [] }] }] } }
let clis = MANY
/** What `runs.usage` answers, and what holds each answer back until a test lets it go. */
let usage = { days: [{ money: '$1.20', tokens: '9.0k' }], whole: { runs: 2, money: '$8.40', tokens: '120.4k' } }
let held = null
const served = daemon({
  methods: {
    'flows.backends': () => ({ clis }),
    'runs.usage': async () => {
      const answer = usage
      if (held) await held
      return answer
    },
  },
})
const api = await import('../../../../src/hmz/web/static/api.js')
api.providers.splice(0, api.providers.length, provider(served))
const { readBackends } = await import('../../../../src/hmz/web/static/pickers.js')
const { modelChip } = await import('../../../../src/hmz/web/static/chips/model.js')
const { usageChip } = await import('../../../../src/hmz/web/static/chips/usage.js')
const { chain, dismiss } = await import('../../../../src/hmz/web/static/layers.js')
const { menu: menuOf, submenu } = await import('../../../../src/hmz/web/static/shell.js')

after(async () => (await api.client('local')).close())

/** A chip in the row under a box, as a form holds it. */
function under(node) {
  const row = el('div', { class: 'composer-under' }, node)
  body.append(row)
  return row
}

/** The rows of a level that scroll: those that name a model. */
const nousOf = (menu) => menu.querySelector('.nous-list').querySelectorAll('[role=menuitem]')

/** The rows a menu opens on, a level each: what each picks and what is picked at it. */
const levelsOf = (menu) => menu.querySelectorAll('.choice.step').map((one) => [one.querySelector('.choice-label').textContent, one.querySelector('.choice-about').textContent])

/** The rows of the level that picks a harness, and those that name a virtual nous. */
const harnessesOf = (menu) => menu.querySelectorAll('[role=menuitem]').filter((one) => one.dataset.cli)
const virtualOf = (menu) => menu.querySelectorAll('[role=menuitem]').filter((one) => one.dataset.hmz === 'pick-virtual')

/** Goes into a level of a menu from its row. */
const into = (menu, level) => menu.querySelector(`[data-hmz=step-${level}]`).click()

/** A key pressed on a thing, as the thing's own listeners hear it. */
function pressed(on, name, target = on, more = {}) {
  const event = Object.assign(new Event('keydown', { cancelable: true }), { key: name, ...more })
  Object.defineProperty(event, 'target', { value: target })
  on.dispatchEvent(event)
  return event
}

test('a nous is picked a level at a time: the menu opens on a row a level, never on a list of every nous', async () => {
  await readBackends('/w')
  const made = modelChip('assistant', 'litellm/vertex_ai/claude-opus-3')
  const row = under(made.node)
  const button = made.node.querySelector('[data-hmz=pick-model]')
  try {
    // The chip says who routes the model picked, as its row does.
    assert.equal(button.textContent, 'LiteLLM Opus 3 (vertex_ai) Default')
    assert.equal(button.getAttribute('aria-label'), 'Nous: LiteLLM Opus 3 (vertex_ai) Default')
    button.click()
    const menu = made.node.querySelector('[role=menu]')
    // One account and no effort this model takes: neither has a row.
    assert.deepEqual(levelsOf(menu), [['Harness', 'LiteLLM'], ['Model', 'Opus 3 (vertex_ai)']])
    assert.equal(menu.querySelector('.nous-list'), null)
    // A harness is picked from the harnesses alone, and its model next.
    into(menu, 'harness')
    assert.equal(menu.querySelector('.steps').dataset.step, 'harness')
    assert.deepEqual(harnessesOf(menu).map((one) => [one.textContent, one.classList.contains('chosen')]), [['LiteLLM', true], ['Claude Code', false]])
    assert.equal(document.activeElement.textContent, 'LiteLLM')
    harnessesOf(menu)[1].click()
    assert.equal(menu.querySelector('.steps').dataset.step, 'model')
    assert.deepEqual(nousOf(menu).map((one) => one.textContent), ['Haiku 4.5'])
    assert.equal(made.value(), 'claude/claude-haiku-4-5')
    // The way back is over the level, said as the level, and the left arrow takes it.
    const back = menu.querySelector('[data-hmz=step-back]')
    assert.equal(back.textContent, 'Model')
    assert.equal(back.getAttribute('aria-label'), 'Back from Model')
    pressed(menu.querySelector('.steps'), 'ArrowLeft', nousOf(menu)[0])
    assert.equal(menu.querySelector('.steps').dataset.step, '')
    assert.equal(document.activeElement, menu.querySelector('[data-hmz=step-model]'))
    assert.deepEqual(levelsOf(menu), [['Harness', 'Claude Code'], ['Model', 'Haiku 4.5']])
    // The harness left is picked again from what was last picked of it.
    into(menu, 'harness')
    harnessesOf(menu)[0].click()
    assert.equal(made.value(), 'litellm/vertex_ai/claude-opus-3')
    // A model that takes efforts has a level of them, and picking one closes the menu.
    nousOf(menu).find((one) => one.textContent === 'Opus 1 (azure_ai)').click()
    assert.equal(made.node.querySelector('[role=menu]'), null)
    assert.equal(made.value(), 'litellm/azure_ai/claude-opus-1')
    button.click()
    const again = made.node.querySelector('[role=menu]')
    assert.deepEqual(levelsOf(again), [['Harness', 'LiteLLM'], ['Model', 'Opus 1 (azure_ai)'], ['Effort', 'Default']])
    into(again, 'effort')
    assert.deepEqual(again.querySelectorAll('[role=menuitem]').filter((one) => 'value' in one.dataset).map((one) => one.textContent), ['Default', 'Low', 'High'])
    again.querySelectorAll('[role=menuitem]').filter((one) => 'value' in one.dataset)[2].click()
    assert.equal(made.value(), 'litellm/azure_ai/claude-opus-1:high')
    assert.equal(button.textContent, 'LiteLLM Opus 1 (azure_ai) High')
  } finally {
    dismiss('route')
    made.leave()
    row.remove()
  }
})

test('a long level of models is found by typing: its rows alone scroll, none read alike, and nothing found says so', async () => {
  await readBackends('/w')
  const made = modelChip('assistant', 'litellm/vertex_ai/claude-opus-3')
  const row = under(made.node)
  const button = made.node.querySelector('[data-hmz=pick-model]')
  try {
    button.click()
    const menu = made.node.querySelector('[role=menu]')
    into(menu, 'model')
    const find = menu.querySelector('[data-hmz=pick-model-find]')
    const list = menu.querySelector('.nous-list')
    const rows = () => list.querySelectorAll('[role=menuitem]')
    const shown = () => rows().filter((one) => !one.hidden).map((one) => one.textContent)
    // The field and what is under the rows are no part of what scrolls.
    assert.ok(find && !list.contains(find))
    assert.ok(!list.contains(menu.querySelector('[data-hmz=pick-model-typed]')))
    assert.ok(!list.contains(menu.querySelector('[data-hmz=pick-refresh]')))
    // The models of the harness chosen alone, no two read alike.
    assert.equal(rows().length, 12)
    assert.equal(new Set(shown()).size, 12)
    // It opens on the model chosen, and what is typed there goes to the field.
    assert.equal(document.activeElement.textContent, 'Opus 3 (vertex_ai)')
    pressed(list, 'o', document.activeElement)
    assert.equal(document.activeElement, find)
    // A key that does something else on a row is the row's still.
    rows()[0].focus()
    for (const [name, more] of [[' ', {}], ['Enter', {}], ['ArrowDown', {}], ['k', { metaKey: true }]]) pressed(list, name, rows()[0], more)
    assert.equal(document.activeElement, rows()[0])
    // Up from the first row is the field, from any other the row over it.
    pressed(list, 'ArrowUp', rows()[1])
    assert.equal(document.activeElement, rows()[0])
    pressed(list, 'ArrowUp', rows()[0])
    assert.equal(document.activeElement, find)
    // Found by a row's name and by what `-a` spells.
    const typed = (text) => {
      find.value = text
      find.dispatchEvent(new Event('input'))
    }
    typed('opus 2')
    assert.deepEqual(shown(), ['Opus 2 (azure_ai)', 'Opus 2 (vertex_ai)'])
    assert.equal(list.querySelector('.ask-none').hidden, true)
    typed('litellm/azure_ai/claude-opus-6')
    assert.deepEqual(shown(), ['Opus 6 (azure_ai)'])
    typed('zzzzqq')
    assert.deepEqual(shown(), [])
    assert.equal(list.querySelector('.ask-none').hidden, false)
    assert.equal(list.querySelector('.ask-none').textContent, 'No model matches')
    // Closed and opened again, nothing is looked for still.
    dismiss('route')
    button.click()
    const again = made.node.querySelector('[role=menu]')
    into(again, 'model')
    assert.equal(again.querySelector('[data-hmz=pick-model-find]').value, '')
    assert.equal(nousOf(again).filter((one) => !one.hidden).length, 12)
    // Found and picked, it is the nous of the chip.
    nousOf(again).find((one) => one.textContent === 'Opus 2 (azure_ai)').click()
    assert.equal(made.value(), 'litellm/azure_ai/claude-opus-2')
    assert.equal(button.textContent, 'LiteLLM Opus 2 (azure_ai) Default')
  } finally {
    dismiss('route')
    made.leave()
    row.remove()
  }
})

test('a level with one choice has no row, and a short level of models no field to find one by', async () => {
  clis = { claude: MANY.claude }
  await readBackends('/w')
  const made = modelChip('assistant', 'claude/claude-haiku-4-5')
  const row = under(made.node)
  try {
    made.node.querySelector('[data-hmz=pick-model]').click()
    const menu = made.node.querySelector('[role=menu]')
    assert.deepEqual(levelsOf(menu), [['Model', 'Haiku 4.5']])
    into(menu, 'model')
    assert.equal(menu.querySelector('[data-hmz=pick-model-find]'), null)
    assert.deepEqual(nousOf(menu).map((one) => one.textContent), ['Haiku 4.5'])
  } finally {
    dismiss('route')
    made.leave()
    row.remove()
    clis = MANY
    await readBackends('/w')
  }
})

test('the virtual nous are offered first, each by its name, and one picked is what the chip says and gives', async () => {
  await readBackends('/w')
  let told = 0
  const made = modelChip('assistant', 'careful', () => told++, { virtual: () => ['careful', 'fast'] })
  const row = under(made.node)
  const button = made.node.querySelector('[data-hmz=pick-model]')
  try {
    assert.equal(made.value(), 'careful')
    assert.equal(button.textContent, 'careful')
    assert.equal(button.getAttribute('aria-label'), 'Nous: careful')
    button.click()
    const menu = made.node.querySelector('[role=menu]')
    assert.deepEqual(menu.querySelectorAll('.popover-head').map((one) => one.textContent), ['Virtual', 'Concrete'])
    assert.deepEqual(virtualOf(menu).map((one) => [one.textContent, one.classList.contains('chosen')]), [['careful', true], ['fast', false]])
    // It opens on the one chosen, over the levels of a concrete one.
    assert.equal(document.activeElement.textContent, 'careful')
    virtualOf(menu)[1].click()
    assert.equal(made.value(), 'fast')
    assert.equal(told, 1)
    // A concrete one picked instead is no longer the virtual one.
    button.click()
    const again = made.node.querySelector('[role=menu]')
    into(again, 'model')
    nousOf(again).find((one) => one.textContent === 'Opus 5 (azure_ai)').click()
    assert.equal(made.value(), 'litellm/azure_ai/claude-opus-5')
    assert.equal(told, 2)
  } finally {
    dismiss('route')
    made.leave()
    row.remove()
  }
})

test('a chip drawn as a field holds what it was given as it is written until another is picked', async () => {
  await readBackends('/w')
  // A harness that is not installed here, and an effort nobody lists: kept, not settled away.
  const made = modelChip('node', 'codex/gpt-9:high', () => {}, { up: false, align: 'start', field: true, virtual: () => [] })
  const row = el('div', { class: 'row' }, made.node)
  body.append(row)
  const button = made.node.querySelector('[data-hmz=pick-model]')
  try {
    assert.ok(button.classList.contains('as-field'))
    assert.equal(made.value(), 'codex/gpt-9:high')
    button.click()
    const menu = made.node.querySelector('[role=menu]')
    into(menu, 'harness')
    harnessesOf(menu).find((one) => one.textContent === 'Claude Code').click()
    assert.equal(made.value(), 'claude/claude-haiku-4-5')
  } finally {
    dismiss('route')
    made.leave()
    row.remove()
  }
})

test('a menu opened from a choice of a chip`s menu ends no lower than that menu, off the chips and the box', async () => {
  const button = el('button', { class: 'chip-btn', type: 'button' })
  const holder = el('span', {}, button)
  const row = under(holder)
  menuOf(button, () => [submenu({ label: 'Effort', items: () => [el('button', { role: 'menuitem' })] })], { align: 'end', up: true, label: 'Chip' })
  try {
    button.box = { left: 800, top: 768, width: 200, height: 24 }
    button.click()
    const menu = holder.querySelector('[role=menu]')
    menu.box = { left: 680, top: 420, width: 320, height: 342 }
    const effort = menu.querySelectorAll('.choice-sub').find((one) => one.textContent.startsWith('Effort'))
    const opener = effort.querySelector('[aria-haspopup=menu]')
    // The choice is near the menu's foot, and what it opens is taller than what is left under it.
    opener.box = { left: 686, top: 690, width: 308, height: 28 }
    const drawn = globalThis.document.createElement
    globalThis.document.createElement = (tag) => {
      const one = drawn(tag)
      if (tag === 'div') one.box = { left: 0, top: 0, width: 180, height: 154 }
      return one
    }
    try {
      opener.click()
    } finally {
      globalThis.document.createElement = drawn
    }
    const sub = effort.querySelector('.sub')
    assert.equal(sub.dataset.side, 'right')
    // Its foot at the menu's own, 762, not at the window's: 852 would lie on the chip at 768.
    assert.equal(sub.style.top, `${762 - 154}px`)
  } finally {
    dismiss('route')
    row.remove()
  }
})

test('the Usage chip opens a popup that is read, drawn again as the chat spends, and left by Tab as by Escape', async () => {
  let rows = [{ label: 'Spent', value: '$0.10' }]
  let folder = '/w/app'
  const made = usageChip({ hmz: 'chat-usage', tip: 'What this chat has used', chat: () => rows, workspace: () => folder })
  const row = under(made.node)
  const button = made.node.querySelector('[data-hmz=chat-usage]')
  try {
    // What is read, not chosen from: a dialog, to whoever cannot see it.
    assert.equal(button.getAttribute('aria-haspopup'), 'dialog')
    assert.equal(button.getAttribute('aria-expanded'), 'false')
    // The ring alone: no figure stands beside it, however much the chat has spent.
    made.read()
    assert.equal(button.textContent, '')
    assert.equal(button.querySelector('.chip-value'), null)
    assert.equal(button.getAttribute('aria-label'), 'Usage')
    button.click()
    const pop = made.node.querySelector('[role=dialog]')
    assert.equal(pop.getAttribute('aria-label'), 'Usage')
    assert.equal(button.getAttribute('aria-expanded'), 'true')
    assert.equal(pop.querySelector('.usage-lately').textContent, 'Reading…')
    const lately = pop.querySelector('.usage-lately')
    await until(() => lately.querySelector('dl'))
    assert.deepEqual(lately.querySelectorAll('dt').map((one) => one.textContent), ['Today (UTC)', 'Last 7 days'])
    assert.deepEqual(lately.querySelectorAll('.usage-about').map((one) => one.textContent), ['9.0k output tokens', '120.4k output tokens'])
    assert.equal(lately.querySelector('.usage-sub').textContent, 'Over 2 chats and epics')
    // The link is to the Usage page on the folder read.
    const link = pop.querySelector('a')
    assert.equal(link.textContent, 'Usage settings')
    assert.equal(link.getAttribute('href'), '#/settings/usage?workspace=%2Fw%2Fapp')
    assert.equal(link.getAttribute('role'), null)
    // Open, it is drawn again with what the chat has spent since.
    const mine = () => pop.querySelector('.usage-mine').querySelectorAll('.usage-value').map((one) => one.textContent)
    assert.deepEqual(mine(), ['$0.10'])
    rows = [{ label: 'Spent', value: '$0.25' }]
    made.read()
    assert.deepEqual(mine(), ['$0.25'])
    assert.equal(button.textContent, '')
    // Tab past its last stop closes it, and the chip has the focus, from where Tab goes on.
    assert.equal(document.activeElement, link)
    const tab = pressed(pop, 'Tab', link)
    assert.equal(tab.defaultPrevented, true)
    assert.equal(made.node.querySelector('[role=dialog]'), null)
    assert.equal(button.getAttribute('aria-expanded'), 'false')
    assert.equal(document.activeElement, button)
    assert.equal(chain().length, 0)
    // Escape closes it the same.
    button.click()
    key('Escape')
    assert.equal(made.node.querySelector('[role=dialog]'), null)
    assert.equal(document.activeElement, button)
  } finally {
    dismiss('route')
    row.remove()
  }
})

test('an answer to an earlier opening of the Usage popup is dropped, and every folder is read where none is picked', async () => {
  let folder = '/w/app'
  const made = usageChip({ hmz: 'new-usage', tip: 'What this folder has used', workspace: () => folder })
  const row = under(made.node)
  const button = made.node.querySelector('[data-hmz=new-usage]')
  try {
    // Asked, and held back; closed, the folder changed, and asked again.
    let free
    held = new Promise((resolve) => (free = resolve))
    usage = { days: [], whole: { runs: 1, money: '$1.00', tokens: '5' } }
    button.click()
    await until(() => served.calls.some((one) => one.method === 'runs.usage' && one.params.workspace === '/w/app'))
    dismiss('route')
    folder = ''
    held = null
    usage = { days: [], whole: { runs: 0 } }
    button.click()
    const pop = made.node.querySelector('[role=dialog]')
    // No chat's figures on a form, and no folder in the link.
    assert.equal(pop.querySelector('.usage-mine'), null)
    assert.equal(pop.querySelector('.popover-head').textContent, 'Every folder')
    assert.equal(pop.querySelector('a').getAttribute('href'), '#/settings/usage')
    const lately = pop.querySelector('.usage-lately')
    await until(() => lately.querySelector('dl'))
    assert.equal(lately.querySelector('.usage-sub').textContent, 'No chats or epics yet')
    // The first answer comes now, and changes nothing.
    free()
    await new Promise((resolve) => setTimeout(resolve, 30))
    assert.deepEqual(lately.querySelectorAll('.usage-value').map((one) => one.textContent), ['$0.00', '$0.00'])
    assert.equal(served.calls.filter((one) => one.method === 'runs.usage').at(-1).params.workspace, undefined)
  } finally {
    held = null
    dismiss('route')
    row.remove()
  }
})

test('a chip of a flow`s role offers only the harnesses that can fill it, and its menu opens under it, at its start', async () => {
  await readBackends('/w')
  // In the middle of a page, as a new epic keeps it: not in the row under a box.
  const made = modelChip({ name: 'worker', clis: ['claude'] }, '', () => {}, { up: false, align: 'start' })
  const row = el('div', { class: 'setup-row' }, made.node)
  body.append(row)
  const button = made.node.querySelector('[data-hmz=pick-model]')
  try {
    assert.equal(made.node.getAttribute('data-role'), 'worker')
    // Nothing kept: the first model of the first harness that can fill it.
    assert.equal(made.value(), 'claude/claude-haiku-4-5')
    assert.equal(button.textContent, 'Claude Code Haiku 4.5 Default')
    button.box = { left: 300, top: 200, width: 220, height: 24 }
    button.click()
    const menu = made.node.querySelector('[role=menu]')
    // No level of harnesses where one alone can fill it, though the daemon lists another's twelve models.
    assert.deepEqual(levelsOf(menu), [['Model', 'Haiku 4.5']])
    // Under the chip, its left edge on the chip's.
    assert.equal(menu.style.left, '300px')
    assert.ok(parseFloat(menu.style.top) >= 224)
  } finally {
    dismiss('route')
    made.leave()
    row.remove()
  }
})

test('a chip named by a role alone still offers every harness, over the chip', async () => {
  await readBackends('/w')
  const made = modelChip('assistant', 'claude/claude-haiku-4-5')
  const row = under(made.node)
  const button = made.node.querySelector('[data-hmz=pick-model]')
  try {
    button.box = { left: 800, top: 768, width: 200, height: 24 }
    button.click()
    const menu = made.node.querySelector('[role=menu]')
    into(menu, 'harness')
    assert.deepEqual(harnessesOf(menu).map((one) => one.textContent), ['LiteLLM', 'Claude Code'])
    assert.ok(parseFloat(menu.style.top) < 768)
  } finally {
    dismiss('route')
    made.leave()
    row.remove()
  }
})

test('a role no harness installed here can fill says so in its menu', async () => {
  await readBackends('/w')
  const made = modelChip({ name: 'worker', clis: [] }, '', () => {}, { up: false, align: 'start' })
  const row = el('div', { class: 'setup-row' }, made.node)
  body.append(row)
  try {
    assert.equal(made.value(), '')
    made.node.querySelector('[data-hmz=pick-model]').click()
    const menu = made.node.querySelector('[role=menu]')
    assert.equal(menu.querySelector('.nous-list'), null)
    assert.equal(menu.querySelector('[data-hmz=pick-none]').textContent, 'No harness installed here can fill it.')
  } finally {
    dismiss('route')
    made.leave()
    row.remove()
  }
})
