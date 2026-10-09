// The runtimes: an ssh host, a docker daemon, a docker swarm or this Mac's Apple containers,
// written down under a name an `-e` names. Each can be asked what it has, the way a run
// reaching it asks; a new one is written from its backend's own fields, or brought in from
// the hosts an ssh config names.

import { get, post } from '../../api.js'
import { acting, confirming, fill, h, problem } from '../../dom.js'

const GIB = 2 ** 30

export function draw(holder) {
  const listing = h('section', { class: 'panel', 'data-hmz': 'runtimes' })
  const writing = h('section', { class: 'panel', 'data-hmz': 'write-runtime' })
  const importing = h('section', { class: 'panel', 'data-hmz': 'import-runtimes' })
  fill(holder, listing, writing, importing)
  let data = null
  let editing = null
  const checked = {}

  const shown = (answer) => {
    data = answer
    drawListing()
    drawWriting()
  }

  function drawListing() {
    const rows = data.runtimes.map((one) => {
      const key = `${one.backend}:${one.name}`
      return h(
        'tr',
        { 'data-hmz': 'runtime' },
        h('td', { class: 'mono' }, one.backend),
        h('td', {}, h('b', {}, one.name), h('div', { class: 'dim' }, one.made)),
        h('td', { class: 'mono' }, reached(one), one.workdir ? h('div', { class: 'dim' }, one.workdir) : null),
        h('td', {}, checked[key] ? said(checked[key]) : h('span', { class: 'dim' }, 'not asked')),
        h(
          'td',
          {},
          h(
            'div',
            { class: 'row' },
            acting(
              'Check',
              async () => {
                checked[key] = await post('/api/runtimes/check', { backend: one.backend, name: one.name })
                drawListing()
              },
              { kind: 'btn small quiet', busy: 'Asking…' },
            ),
            h('button', { class: 'btn small quiet', type: 'button', onclick: () => edit(one) }, 'Change'),
            confirming({ label: 'Remove', ask: `Remove ${one.name}?`, yes: 'Remove it', small: true, act: async () => shown(await post('/api/runtimes/remove', { backend: one.backend, name: one.name })) }),
          ),
        ),
      )
    })
    fill(
      listing,
      h('h2', {}, 'Runtimes'),
      rows.length
        ? h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Backend'), h('th', {}, 'Name'), h('th', {}, 'Reached at'), h('th', {}, 'Has'), h('th', {}, ''))), h('tbody', {}, rows)))
        : h('p', { class: 'dim' }, 'None yet: every environment is this machine, or spelled out where it is named.'),
    )
  }

  function edit(one) {
    editing = one
    drawWriting()
    writing.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function drawWriting() {
    const backend = h('select', { id: 'runtime-backend', disabled: Boolean(editing) }, Object.keys(data.blanks).map((one) => h('option', { value: one, selected: editing ? editing.backend === one : false }, one)))
    const name = h('input', { type: 'text', id: 'runtime-name', value: editing ? editing.name : '', placeholder: 'gpu-box', required: true, disabled: Boolean(editing), autocomplete: 'off' })
    const fields = h('div', { class: 'grid' })
    const readers = {}
    const drawFields = () => {
      const blank = data.blanks[backend.value]
      fill(fields)
      for (const [key, empty] of Object.entries(blank)) {
        const value = editing ? editing[key] : empty
        const [input, read] = field(key, empty, value)
        readers[key] = read
        fields.append(h('div', { class: 'field' }, h('label', { for: `runtime-${key}` }, key.endsWith('memory') ? `${key}, GiB` : key), input))
      }
      for (const key of Object.keys(readers)) if (!(key in blank)) delete readers[key]
    }
    backend.addEventListener('change', drawFields)
    const said = h('div', { 'aria-live': 'polite' })
    fill(
      writing,
      h('h2', {}, editing ? `Change ${editing.name}` : 'Add a runtime'),
      h(
        'form',
        { class: 'form', onsubmit: (event) => event.preventDefault() },
        h('div', { class: 'row' }, h('div', { class: 'field' }, h('label', { for: 'runtime-backend' }, 'backend'), backend), h('div', { class: 'field' }, h('label', { for: 'runtime-name' }, 'name'), name)),
        fields,
        h(
          'div',
          { class: 'row' },
          acting(
            editing ? 'Write it over' : 'Add it',
            async () => {
              const given = {}
              for (const [key, read] of Object.entries(readers)) given[key] = read()
              const answer = await post('/api/runtimes', { backend: backend.value, name: name.value.trim(), fields: given, replace: Boolean(editing) })
              editing = null
              shown(answer)
            },
            { kind: 'btn primary', busy: 'Writing…' },
          ),
          editing ? h('button', { class: 'btn quiet', type: 'button', onclick: () => ((editing = null), drawWriting()) }, 'Add a new one') : null,
          said,
        ),
      ),
    )
    drawFields()
  }

  function drawImporting() {
    const read = acting(
      'Read the ssh config',
      async () => {
        const { hosts } = await get('/api/runtimes/hosts')
        const boxes = hosts.map((one) => ({ one, box: h('input', { type: 'checkbox', disabled: one.saved }) }))
        fill(
          importing,
          h('h2', {}, 'From your ssh config'),
          hosts.length
            ? [
                h(
                  'div',
                  { class: 'form' },
                  boxes.map(({ one, box }) =>
                    h('label', { class: 'check' }, box, h('b', { class: 'mono' }, one.alias), h('span', { class: 'dim' }, `${one.user ? `${one.user}@` : ''}${one.host}${one.port && one.port !== 22 ? `:${one.port}` : ''}${one.saved ? ' · written down already' : ''}`)),
                  ),
                ),
                h(
                  'p',
                  { class: 'row' },
                  acting(
                    'Bring them in',
                    async () => {
                      const names = boxes.filter(({ box }) => box.checked).map(({ one }) => one.alias)
                      if (!names.length) return
                      shown(await post('/api/runtimes/import', { names }))
                      drawImporting()
                    },
                    { kind: 'btn primary', busy: 'Bringing them in…' },
                  ),
                ),
              ]
            : h('p', { class: 'dim' }, 'It names no host.'),
        )
      },
      { kind: 'btn', busy: 'Reading…' },
    )
    fill(importing, h('h2', {}, 'From your ssh config'), h('p', { class: 'dim' }, 'Each host your ssh config names can be written down as a runtime of its own.'), read)
  }

  get('/api/runtimes')
    .then((answer) => {
      shown(answer)
      drawImporting()
    })
    .catch((error) => fill(listing, problem(error)))
}

/** Where a runtime is reached, as somebody would write it. */
function reached(one) {
  if (one.backend === 'ssh') return `${one.user ? `${one.user}@` : ''}${one.host || one.alias}${one.port ? `:${one.port}` : ''}`
  return one.endpoint || 'this Mac'
}

/** What a runtime said when it was asked what it has. */
function said(answer) {
  if (!answer.reached) return h('span', { class: 'bad' }, answer.said || 'it did not answer')
  const has = [
    answer.cpus ? `${answer.cpus} cpu` : '',
    answer.memory ? `${Math.round(answer.memory / GIB)} GiB` : '',
    answer.gpus.length ? `${answer.usable ? `${answer.usable.length} of ` : ''}${answer.gpus.length} gpu` : '',
    answer.nodes.length ? `${answer.nodes.length} node${answer.nodes.length === 1 ? '' : 's'}` : '',
    answer.version,
  ].filter(Boolean)
  return h('div', {}, h('span', { class: 'ok' }, '✔ '), has.join(' · ') || 'answered', answer.short.length ? h('div', { class: 'bad' }, `short of: ${answer.short.join(', ')}`) : null)
}

/** One field of a runtime: the input it is written in, and what reads it back as JSON holds it. */
function field(key, empty, value) {
  const id = `runtime-${key}`
  if (Array.isArray(empty)) {
    const input = h('textarea', { id, rows: '2', placeholder: 'one per line' }, (value || []).join('\n'))
    return [input, () => input.value.split('\n').map((one) => one.trim()).filter(Boolean)]
  }
  if (empty && typeof empty === 'object') {
    const input = h('textarea', { id, rows: '2', placeholder: 'KEY=VALUE, one per line' }, Object.entries(value || {}).map(([name, set]) => `${name}=${set}`).join('\n'))
    return [input, () => Object.fromEntries(input.value.split('\n').filter((one) => one.includes('=')).map((one) => [one.slice(0, one.indexOf('=')).trim(), one.slice(one.indexOf('=') + 1).trim()]))]
  }
  if (typeof empty === 'number') {
    const memory = key.endsWith('memory')
    const input = h('input', { id, type: 'number', min: '0', step: memory || !Number.isInteger(empty) || key === 'cpus' ? 'any' : '1', value: value ? String(memory ? value / GIB : value) : '' })
    return [input, () => (input.value === '' ? 0 : memory ? Math.round(Number(input.value) * GIB) : Number(input.value))]
  }
  const input = h('input', { id, type: 'text', value: value || '', autocomplete: 'off' })
  return [input, () => input.value.trim()]
}
