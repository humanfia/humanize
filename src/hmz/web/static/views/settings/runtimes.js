// The runtimes: an ssh host, a docker daemon, a docker swarm or this Mac's Apple containers,
// written down under a name an `-e` names. Each can be asked what it has, the way a run
// reaching it asks; a new one is written from its backend's own fields, or brought in from
// the hosts an ssh config names.

import { get, post } from '../../api.js'
import { acting, confirming, fill, h, icon, iconButton, problem } from '../../dom.js'
import { pathPicker } from '../../paths.js'

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
            h('button', { class: 'btn small quiet', type: 'button', onclick: () => edit(one) }, 'Edit'),
            confirming({ label: 'Remove', ask: `Remove ${one.name}?`, yes: 'Remove', small: true, act: async () => shown(await post('/api/runtimes/remove', { backend: one.backend, name: one.name })) }),
          ),
        ),
      )
    })
    fill(
      listing,
      h('h2', {}, 'Runtimes'),
      rows.length
        ? h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Backend'), h('th', {}, 'Name'), h('th', {}, 'Address'), h('th', {}, 'Resources'), h('th', {}, ''))), h('tbody', {}, rows)))
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
        const [input, read] = field(key, empty, value, { backend: backend.value, name: name.value.trim(), runtimes: data.runtimes })
        readers[key] = read
        fields.append(h('div', { class: ['field', (Array.isArray(empty) || (empty && typeof empty === 'object')) && 'wide'] }, h('label', { for: `runtime-${key}` }, labelOf(key)), input))
      }
      for (const key of Object.keys(readers)) if (!(key in blank)) delete readers[key]
    }
    backend.addEventListener('change', drawFields)
    const said = h('div', { 'aria-live': 'polite' })
    fill(
      writing,
      h('h2', {}, editing ? `Edit ${editing.name}` : 'New runtime'),
      h(
        'form',
        { class: 'form', onsubmit: (event) => event.preventDefault() },
        h('div', { class: 'row' }, h('div', { class: 'field' }, h('label', { for: 'runtime-backend' }, 'Backend'), backend), h('div', { class: 'field' }, h('label', { for: 'runtime-name' }, 'Name'), name)),
        fields,
        h(
          'div',
          { class: 'row' },
          acting(
            editing ? 'Save' : 'Add',
            async () => {
              const given = {}
              for (const [key, read] of Object.entries(readers)) given[key] = read()
              const answer = await post('/api/runtimes', { backend: backend.value, name: name.value.trim(), fields: given, replace: Boolean(editing) })
              editing = null
              shown(answer)
            },
            { kind: 'btn primary', busy: 'Saving…' },
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
      'Read SSH config',
      async () => {
        const { hosts } = await get('/api/runtimes/hosts')
        const boxes = hosts.map((one) => ({ one, box: h('input', { type: 'checkbox', disabled: one.saved }) }))
        fill(
          importing,
          h('h2', {}, 'SSH config'),
          hosts.length
            ? [
                h(
                  'div',
                  { class: 'form' },
                  boxes.map(({ one, box }) =>
                    h('label', { class: 'check' }, box, h('b', { class: 'mono' }, one.alias), h('span', { class: 'dim' }, `${one.user ? `${one.user}@` : ''}${one.host}${one.port && one.port !== 22 ? `:${one.port}` : ''}${one.saved ? ' · saved' : ''}`)),
                  ),
                ),
                h(
                  'p',
                  { class: 'row' },
                  acting(
                    'Import',
                    async () => {
                      const names = boxes.filter(({ box }) => box.checked).map(({ one }) => one.alias)
                      if (!names.length) return
                      shown(await post('/api/runtimes/import', { names }))
                      drawImporting()
                    },
                    { kind: 'btn primary', busy: 'Importing…' },
                  ),
                ),
              ]
            : h('p', { class: 'dim' }, 'It names no host.'),
        )
      },
      { kind: 'btn', busy: 'Reading…' },
    )
    fill(importing, h('h2', {}, 'SSH config'), h('p', { class: 'dim' }, 'Import hosts from your SSH config as runtimes.'), read)
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

/** What a runtime's field is called on its form: its name, as words. */
function labelOf(key) {
  const named = { identity_file: 'Identity file', proxy_jump: 'Proxy jump', tls_dir: 'TLS directory', run_args: 'Run arguments', gpu_memory: 'GPU memory, GiB', gpus: 'GPUs', cpus: 'CPUs', config: 'SSH config', workdir: 'Workdir', affinity: 'Harness runs on', fallback: 'Falls back to', options: 'SSH options' }
  if (named[key]) return named[key]
  const words = key.replace(/_/g, ' ')
  return `${words.slice(0, 1).toUpperCase()}${words.slice(1)}${key.endsWith('memory') ? ', GiB' : ''}`
}

/** The SSH hosts your config names, read once, for the fields that name one. */
let hosts = null
function sshHosts() {
  hosts ||= get('/api/runtimes/hosts').then((answer) => answer.hosts.map((one) => one.alias), () => [])
  return hosts
}

/**
 * One field of a runtime: what it is picked or written in, and what reads it back as JSON holds
 * it. Each as the terminal interface's form asks it rather than as a string to spell: a file or
 * a directory browsed for, the runtimes to fall back to and where a harness runs picked from
 * what is saved and put in order, options as names and values, and a list a row at a time.
 */
function field(key, empty, value, { backend, name, runtimes }) {
  const id = `runtime-${key}`
  if (key === 'identity_file' || key === 'config' || key === 'tls_dir') {
    const picked = pathPicker({ value: value || '', files: key !== 'tls_dir', label: labelOf(key), id, placeholder: key === 'config' ? '~/.ssh/config' : key === 'tls_dir' ? '~/.docker' : '~/.ssh/id_ed25519' })
    return [picked.node, () => picked.value()]
  }
  if (key === 'fallback') {
    const others = runtimes.filter((one) => one.backend === backend && one.name !== name).map((one) => one.name)
    const listed = listing(value || [], { id, options: () => others, none: 'No other runtime of this backend' })
    return [listed.node, listed.read]
  }
  if (key === 'affinity') {
    const places = ['self', 'local', ...runtimes.filter((one) => one.name !== name || one.backend !== backend).map((one) => `${one.backend}:${one.name}`)]
    const listed = listing(value || [], { id, options: () => places })
    return [listed.node, listed.read]
  }
  if (Array.isArray(empty)) {
    const listed = listing(value || [], { id, placeholder: key === 'gpus' ? '0' : key === 'run_args' ? '--shm-size=8g' : '' })
    return [listed.node, listed.read]
  }
  if (empty && typeof empty === 'object') {
    const pairs = pairing(value || {}, id)
    return [pairs.node, pairs.read]
  }
  if (typeof empty === 'number') {
    const memory = key.endsWith('memory')
    const input = h('input', { id, type: 'number', min: '0', step: memory || !Number.isInteger(empty) || key === 'cpus' ? 'any' : '1', value: value ? String(memory ? value / GIB : value) : '' })
    return [input, () => (input.value === '' ? 0 : memory ? Math.round(Number(input.value) * GIB) : Number(input.value))]
  }
  if (typeof empty === 'boolean') {
    const input = h('input', { id, type: 'checkbox', checked: Boolean(value) })
    return [h('label', { class: 'check' }, input, 'On'), () => input.checked]
  }
  if (key === 'alias' || key === 'proxy_jump' || (key === 'host' && backend === 'ssh')) {
    // A host your SSH config names, picked; any other written.
    const offered = h('datalist', { id: `${id}-hosts` })
    const input = h('input', { id, type: 'text', value: value || '', list: offered.id, autocomplete: 'off', placeholder: key === 'alias' ? 'A host in your SSH config' : key === 'host' ? 'box.example' : 'user@jump' })
    sshHosts().then((names) => fill(offered, names.map((one) => h('option', { value: one }))))
    return [h('div', { class: 'row' }, input, offered), () => input.value.trim()]
  }
  const input = h('input', { id, type: 'text', value: value || '', autocomplete: 'off' })
  return [input, () => input.value.trim()]
}

/**
 * A list a row at a time, in order: each picked from what there is to pick, or written; moved
 * up, down and taken away; and one more added.
 */
function listing(values, { id, options = null, placeholder = '', none = '' }) {
  const rows = h('div', { class: 'list-rows', id, 'data-hmz': 'list-editor' })
  const add = h('button', { class: 'btn small quiet', type: 'button' }, icon('plus'), 'Add')
  const node = h('div', { class: 'list-editor' }, rows, add)
  const row = (value) => {
    const choices = options ? options() : null
    const input = choices
      ? h('select', { 'aria-label': 'Value' }, [...new Set([...choices, value].filter(Boolean))].map((one) => h('option', { value: one, selected: one === value }, one)))
      : h('input', { type: 'text', value, placeholder, 'aria-label': 'Value' })
    const line = h(
      'div',
      { class: 'list-row' },
      input,
      iconButton('down', 'Move down', { class: 'small', onclick: () => line.nextElementSibling && line.nextElementSibling.after(line) }),
      iconButton('close', 'Remove', { class: 'small', onclick: () => line.remove() }),
    )
    rows.append(line)
  }
  for (const one of values) row(String(one))
  add.addEventListener('click', () => {
    const choices = options ? options() : null
    if (choices && !choices.length) return
    row(choices ? choices.find((one) => !read().includes(one)) || choices[0] : '')
    rows.lastElementChild.querySelector('input, select').focus()
  })
  if (options && !options().length && none) add.after(h('span', { class: 'hint' }, none))
  const read = () => [...rows.querySelectorAll('input, select')].map((one) => one.value.trim()).filter(Boolean)
  return { node, read }
}

/** Names and their values, a pair a row: one more added, any taken away. */
function pairing(values, id) {
  const rows = h('div', { class: 'list-rows', id, 'data-hmz': 'pair-editor' })
  const add = h('button', { class: 'btn small quiet', type: 'button' }, icon('plus'), 'Add')
  const row = (key, value) => {
    const line = h(
      'div',
      { class: 'list-row' },
      h('input', { type: 'text', value: key, placeholder: 'Name', 'aria-label': 'Name', class: 'pair-key' }),
      h('input', { type: 'text', value, placeholder: 'Value', 'aria-label': 'Value', class: 'pair-value' }),
      iconButton('close', 'Remove', { class: 'small', onclick: () => line.remove() }),
    )
    rows.append(line)
  }
  for (const [key, value] of Object.entries(values)) row(key, String(value))
  add.addEventListener('click', () => {
    row('', '')
    rows.lastElementChild.querySelector('input').focus()
  })
  return {
    node: h('div', { class: 'list-editor' }, rows, add),
    read: () => Object.fromEntries([...rows.children].map((line) => [line.querySelector('.pair-key').value.trim(), line.querySelector('.pair-value').value.trim()]).filter(([key]) => key)),
  }
}
