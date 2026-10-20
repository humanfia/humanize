// The git repositories epics are backed up to: each with when an epic goes to it unasked -- as
// a session closes, every so many minutes, once the epic ends, or never, by hand only -- and
// which of them a new epic goes to unless it is told otherwise; and `Download`, which brings an
// epic they hold here. A URL is shown with nothing signed into it, and one left as shown is kept
// as written.

import { get, post } from '../../api.js'
import { acting, confirming, fill, h, problem } from '../../dom.js'
import { toast } from '../../ui.js'

/** Each policy, as it is ticked. */
const POLICIES = [
  ['session', 'On session close'],
  ['interval', 'Every N minutes'],
  ['end', 'On epic end'],
]

/** When a target is backed up to, as the list says it. */
function whenSaid(one) {
  const said = POLICIES.filter(([key]) => one.policies.includes(key)).map(([key, label]) => (key === 'interval' ? `Every ${one.every} minutes` : label))
  return said.length ? said.join(' · ') : 'Manual'
}

export function draw(holder, query, parts, scope) {
  const listing = h('section', { class: 'panel', 'data-hmz': 'backups' }, h('p', { class: 'loading', role: 'status' }, 'Reading the backups…'))
  const writing = h('section', { class: 'panel', 'data-hmz': 'write-backup' })
  fill(holder, listing, writing)
  let data = null
  let editing = null

  const shown = (settings) => {
    data = settings.backup
    drawListing()
    drawWriting()
  }

  /** Writes every target down, as they are with one change made, and lists them again. */
  const save = async (targets, defaults) => {
    data = (await post(scope.at('/api/settings'), { backup: { targets, defaults } })).backup
    drawListing()
  }

  function drawListing() {
    const rows = data.targets.map((one) =>
      h(
        'tr',
        { 'data-hmz': 'backup-target', 'data-name': one.name },
        h('td', {}, h('b', {}, one.name)),
        h('td', { class: 'mono' }, one.url, h('div', { class: 'dim' }, one.branch)),
        h('td', {}, whenSaid(one)),
        h(
          'td',
          {},
          h(
            'label',
            { class: 'check' },
            h('input', {
              type: 'checkbox',
              'data-hmz': 'backup-default',
              checked: data.defaults.includes(one.name),
              onchange: (event) => save(data.targets, event.target.checked ? [...data.defaults, one.name] : data.defaults.filter((name) => name !== one.name)).catch((error) => {
                toast(error.message)
                drawListing()
              }),
            }),
            'Default',
          ),
        ),
        h(
          'td',
          {},
          h(
            'div',
            { class: 'row' },
            h('button', { class: 'btn small quiet', type: 'button', onclick: () => edit(one) }, 'Edit'),
            confirming({ label: 'Remove', ask: `Remove ${one.name}?`, yes: 'Remove', small: true, act: async () => {
              await save(data.targets.filter((other) => other.name !== one.name), data.defaults.filter((name) => name !== one.name))
              if (editing && editing.name === one.name) {
                editing = null
                drawWriting()
              }
            } }),
          ),
        ),
      ),
    )
    fill(
      listing,
      h(
        'header',
        {},
        h('h2', {}, 'Targets'),
        h(
          'span',
          { class: 'row' },
          // What the targets hold, brought here onto the daemon picked.
          data.targets.length ? h('a', { class: 'btn quiet', href: scope.name === 'local' ? '#/download' : `#/@${encodeURIComponent(scope.name)}/download`, 'data-hmz': 'download' }, 'Download') : null,
          scope.batch(() => [['/api/settings', { backup: data }]]),
        ),
      ),
      rows.length
        ? h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Name'), h('th', {}, 'Repository'), h('th', {}, 'When'), h('th', {}, ''), h('th', {}, ''))), h('tbody', {}, rows)))
        : h('p', { class: 'dim' }, 'None yet: no epic is backed up.'),
    )
  }

  function edit(one) {
    editing = one
    drawWriting()
    writing.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function drawWriting() {
    const was = editing || { name: '', url: '', branch: 'main', policies: [], every: 30 }
    // A target keeps its name: the epics started with it name it.
    const name = h('input', { type: 'text', id: 'backup-name', value: was.name, placeholder: 'lab', required: true, disabled: Boolean(editing), autocomplete: 'off', spellcheck: 'false' })
    const url = h('input', { type: 'text', id: 'backup-url', value: was.url, placeholder: 'git@github.com:you/epics.git', required: true, autocomplete: 'off', spellcheck: 'false' })
    const branch = h('input', { type: 'text', id: 'backup-branch', value: was.branch, placeholder: 'main', autocomplete: 'off', spellcheck: 'false' })
    const every = h('input', { type: 'number', min: '1', step: '1', value: String(was.every), 'aria-label': 'Minutes', 'data-hmz': 'backup-every' })
    const ticks = Object.fromEntries(POLICIES.map(([key]) => [key, h('input', { type: 'checkbox', 'data-policy': key, checked: was.policies.includes(key) })]))
    const form = h(
      'form',
      { class: 'form' },
      h('div', { class: 'row' }, h('div', { class: 'field' }, h('label', { for: 'backup-name' }, 'Name'), name), h('div', { class: 'field' }, h('label', { for: 'backup-branch' }, 'Branch'), branch)),
      h('div', { class: 'field' }, h('label', { for: 'backup-url' }, 'Repository'), url, h('span', { class: 'hint' }, 'Pushed to with your own git, as it signs in.')),
      h(
        'div',
        { class: 'field', 'data-hmz': 'backup-policies' },
        h('span', { class: 'label' }, 'When'),
        h('label', { class: 'check' }, ticks.session, 'On session close'),
        h('label', { class: 'check' }, ticks.interval, 'Every', every, 'minutes'),
        h('label', { class: 'check' }, ticks.end, 'On epic end'),
        h('span', { class: 'hint' }, 'None ticked: only by hand.'),
      ),
      h(
        'div',
        { class: 'row' },
        acting(
          'Save',
          async () => {
            const made = {
              name: name.value.trim(),
              url: url.value.trim(),
              branch: branch.value.trim() || 'main',
              policies: POLICIES.map(([key]) => key).filter((key) => ticks[key].checked),
              // Only read where it is used: unticked, the minutes stay as they were.
              every: ticks.interval.checked ? Number(every.value) : was.every,
            }
            await save(editing ? data.targets.map((one) => (one.name === editing.name ? made : one)) : [...data.targets, made], data.defaults)
            editing = null
            drawWriting()
          },
          { kind: 'btn primary', busy: 'Saving…' },
        ),
        editing ? h('button', { class: 'btn quiet', type: 'button', onclick: () => ((editing = null), drawWriting()) }, 'New target') : null,
      ),
    )
    form.addEventListener('submit', (event) => event.preventDefault())
    fill(writing, h('h2', {}, editing ? `Edit ${editing.name}` : 'New target'), form)
  }

  get(scope.at('/api/settings'))
    .then(shown)
    .catch((error) => fill(listing, problem(error)))
}
