// The git repositories epics are backed up to: each with when an epic goes to it unasked -- as
// a session closes, every so many minutes, once the epic ends, or never, by hand only -- and
// which of them a new epic goes to unless it is told otherwise; and `Download`, which brings an
// epic they hold here. A URL is shown with nothing signed into it, and one left as shown is kept
// as written.

import { confirming } from '../../confirm.js'
import { acting, empty, fill, h, problem } from '../../dom.js'
import { pieces, t } from '../../i18n.js'
import { toast } from '../../ui.js'

/** Each policy, as it is ticked. */
const POLICIES = [
  ['session', t('On session close')],
  ['interval', t('Every N minutes')],
  ['end', t('On epic end')],
]

/** When a target is backed up to, as the list says it: each time whole on its line. */
function whenSaid(one) {
  const said = POLICIES.filter(([key]) => one.policies.includes(key)).map(([key, label]) => (key === 'interval' ? t('Every {n} minutes', { n: one.every }) : label))
  return (said.length ? said : [t('Manual')]).flatMap((each, at) => [at ? ' · ' : null, h('span', { style: { whiteSpace: 'nowrap' } }, each)])
}

export function draw(holder, query, parts, scope) {
  const listing = h('section', { class: 'panel', 'data-hmz': 'backups' }, h('p', { class: 'loading', role: 'status' }, t('Reading the backups…')))
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
    data = (await scope.call('settings.set', { backup: { targets, defaults } })).backup
    drawListing()
  }

  function drawListing() {
    const rows = data.targets.map((one) =>
      h(
        'tr',
        { 'data-hmz': 'backup-target', 'data-name': one.name },
        h('td', {}, h('b', {}, one.name)),
        h('td', { class: 'mono' }, one.url, h('div', { class: 'dim' }, one.branch)),
        h('td', { 'data-label': t('When') }, whenSaid(one)),
        h(
          'td',
          {},
          h(
            'div',
            { class: 'row' },
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
              t('Default'),
            ),
            h('button', { class: 'btn small quiet', type: 'button', onclick: () => edit(one) }, t('Edit')),
            confirming({ label: t('Remove'), ask: t('Remove {name}?', { name: one.name }), yes: t('Remove'), small: true, act: async () => {
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
        h('h2', {}, t('Targets')),
        h(
          'span',
          { class: 'row' },
          // What the targets hold, brought here onto the daemon picked.
          data.targets.length ? h('a', { class: 'btn small quiet', href: scope.name === 'local' ? '#/download' : `#/@${encodeURIComponent(scope.name)}/download`, 'data-hmz': 'download' }, t('Download')) : null,
          scope.batch(() => [['settings.set', { backup: data }]]),
        ),
      ),
      rows.length
        ? h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, t('Name')), h('th', {}, t('Repository')), h('th', {}, t('When')), h('th', {}, ''))), h('tbody', {}, rows)))
        : empty(
            t('No backup target yet.'),
            t(' Add a git repository, and chats and epics are backed up to it.'),
            h('button', { class: 'btn primary', type: 'button', 'data-hmz': 'backup-add', onclick: () => edit(null) }, t('Add target')),
          ),
    )
  }

  function edit(one) {
    editing = one
    drawWriting()
    writing.scrollIntoView({ behavior: 'smooth', block: 'start' })
    // A new one starts at its name; one edited keeps its name, and is read first.
    if (!one) writing.querySelector('#backup-name').focus({ preventScroll: true })
  }

  function drawWriting() {
    const was = editing || { name: '', url: '', branch: 'main', policies: [], every: 30 }
    // A target keeps its name: the epics started with it name it.
    const name = h('input', { type: 'text', id: 'backup-name', value: was.name, placeholder: 'lab', required: true, disabled: Boolean(editing), autocomplete: 'off', spellcheck: 'false' })
    const url = h('input', { type: 'text', id: 'backup-url', value: was.url, placeholder: 'git@github.com:you/epics.git', required: true, autocomplete: 'off', spellcheck: 'false' })
    const branch = h('input', { type: 'text', id: 'backup-branch', value: was.branch, placeholder: 'main', autocomplete: 'off', spellcheck: 'false' })
    const every = h('input', { type: 'number', min: '1', step: '1', value: String(was.every), 'aria-label': t('Minutes'), 'data-hmz': 'backup-every' })
    const ticks = Object.fromEntries(POLICIES.map(([key]) => [key, h('input', { type: 'checkbox', 'data-policy': key, checked: was.policies.includes(key) })]))
    const form = h(
      'form',
      { class: 'form' },
      h('div', { class: 'row' }, h('div', { class: 'field' }, h('label', { for: 'backup-name' }, t('Name')), name), h('div', { class: 'field' }, h('label', { for: 'backup-branch' }, t('Branch')), branch)),
      h('div', { class: 'field' }, h('label', { for: 'backup-url' }, t('Repository')), url, h('span', { class: 'hint' }, t('Pushed to with your own git, as it signs in.'))),
      h(
        'div',
        { class: 'field', 'data-hmz': 'backup-policies' },
        h('span', { class: 'label' }, t('When')),
        h('label', { class: 'check' }, ticks.session, t('On session close')),
        // The words around the number, in the order the language puts them, each as it stands alone.
        h('label', { class: 'check' }, ticks.interval, pieces('Every {n} minutes', { n: every }).map((bit) => (typeof bit === 'string' ? bit.trim() : bit))),
        h('label', { class: 'check' }, ticks.end, t('On epic end')),
        h('span', { class: 'hint' }, t('None ticked: only by hand.')),
      ),
      h(
        'div',
        { class: 'row' },
        acting(
          t('Save'),
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
          { kind: 'btn primary', busy: t('Saving…') },
        ),
        editing ? h('button', { class: 'btn quiet', type: 'button', onclick: () => ((editing = null), drawWriting()) }, t('New target')) : null,
      ),
    )
    form.addEventListener('submit', (event) => event.preventDefault())
    fill(writing, h('h2', {}, editing ? t('Edit {name}', { name: editing.name }) : t('New target')), form)
  }

  scope.call('settings.get')
    .then(shown)
    .catch((error) => fill(listing, problem(error)))
}
