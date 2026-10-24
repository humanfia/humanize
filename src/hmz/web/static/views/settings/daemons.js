// The daemons the page can show: Local, this machine's own, which is always there, and every
// SSH host written down beside it -- each with how far reaching it has got. A new one is written
// a part at a time, as a runtime's SSH host is, or brought in from the hosts an SSH config names;
// one is reached again, changed, or taken away, asked first.

import { get, post } from '../../api.js'
import { acting, confirming, empty, fill, h, icon, iconButton, problem } from '../../dom.js'
import { pathPicker } from '../../paths.js'

/** How far reaching each state has got, by a glyph, so nothing is said by colour alone. */
const STATES = {
  up: '●',
  connecting: '◐',
  installing: '◐',
  failed: '✕',
  idle: '○',
}

export function draw(holder) {
  const listing = h('section', { class: 'panel', 'data-hmz': 'daemons' }, h('p', { class: 'loading', role: 'status' }, 'Reading the daemons…'))
  const writing = h('section', { class: 'panel', 'data-hmz': 'write-daemon' })
  const importing = h('section', { class: 'panel', 'data-hmz': 'import-daemons' })
  fill(holder, listing, writing, importing)
  let daemons = []
  let editing = null
  let again = null
  let reading = 0
  let gone = false
  const states = new Map()
  // Where Local is: this machine, or the WSL distribution hmz runs in there.
  const where = h('td', { class: 'mono dim' }, 'this machine')
  get('/d/local/api/held').then((held) => held.wsl && fill(where, `${held.wsl} (WSL)`), () => {})

  /**
   * Reads the daemons again, and draws them; while one is still being reached, again soon. The
   * same daemons as before have only their states drawn again, so a question asked on a row, or
   * a refusal said there, stays.
   */
  async function read() {
    clearTimeout(again)
    const mine = ++reading
    const answer = await get('/api/daemons')
    if (gone || mine !== reading) return
    const was = daemons.map((one) => one.name).join('\n')
    daemons = (answer.daemons || []).filter((one) => one.name !== 'local')
    if (was && was === daemons.map((one) => one.name).join('\n')) for (const one of daemons) fill(states.get(one.name), shownState(stateOf(one)))
    else drawListing()
    if (daemons.some((one) => ['connecting', 'installing'].includes(stateOf(one).state))) again = setTimeout(() => read().catch(() => {}), 2000)
  }

  function drawListing() {
    const local = h(
      'tr',
      { 'data-hmz': 'daemon', 'data-name': 'local' },
      h('td', {}, h('b', {}, 'Local')),
      where,
      h('td', {}, shownState({ state: 'up' })),
      h('td', {}),
    )
    states.clear()
    const rows = daemons.map((one) =>
      h(
        'tr',
        { 'data-hmz': 'daemon', 'data-name': one.name },
        h('td', {}, h('b', {}, one.name)),
        h('td', { class: 'mono' }, reached(one)),
        (states.set(one.name, h('td', {}, shownState(stateOf(one)))), states.get(one.name)),
        h(
          'td',
          {},
          h(
            'div',
            { class: 'row' },
            acting(
              'Connect',
              async () => {
                await post(`/api/daemons/${encodeURIComponent(one.name)}/connect`)
                await read()
              },
              { kind: 'btn small quiet', busy: 'Connecting…' },
            ),
            h('button', { class: 'btn small quiet', type: 'button', onclick: () => edit(one) }, 'Edit'),
            confirming({
              label: 'Remove',
              ask: `Remove ${one.name}?`,
              yes: 'Remove',
              small: true,
              act: async () => {
                await post('/api/daemons/remove', { name: one.name })
                if (editing && editing.name === one.name) (editing = null), drawWriting()
                await read()
              },
            }),
          ),
        ),
      ),
    )
    fill(
      listing,
      h('h2', {}, 'Daemons'),
      h('div', { class: 'table-wrap' }, h('table', { class: 'daemons-table' }, h('thead', {}, h('tr', {}, h('th', {}, 'Name'), h('th', {}, 'Address'), h('th', {}, 'State'), h('th', {}, ''))), h('tbody', {}, local, rows))),
    )
  }

  function edit(one) {
    editing = one
    drawWriting()
    writing.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function drawWriting() {
    const was = editing || {}
    const text = (id, value, placeholder, extra = {}) => h('input', { type: 'text', id, value: value || '', placeholder, autocomplete: 'off', spellcheck: 'false', ...extra })
    const name = text('daemon-name', was.name, 'gpu-box', { required: true, disabled: Boolean(editing) })
    const host = text('daemon-host', was.host || was.alias, 'box.example')
    const user = text('daemon-user', was.user, 'me')
    const port = h('input', { type: 'number', id: 'daemon-port', min: '1', max: '65535', step: '1', value: was.port ? String(was.port) : '', placeholder: '22' })
    const key = pathPicker({ value: was.identity_file || '', files: true, label: 'Identity file', id: 'daemon-identity', placeholder: '~/.ssh/id_ed25519' })
    const jump = text('daemon-jump', was.proxy_jump, 'user@jump')
    const options = pairs(was.options || [], 'daemon-options')
    const part = (label, id, input, wide = false) => h('div', { class: ['field', wide && 'wide'] }, h('label', { for: id }, label), input)
    fill(
      writing,
      h('h2', {}, editing ? `Edit ${editing.name}` : 'New daemon'),
      h(
        'form',
        { class: 'form', onsubmit: (event) => event.preventDefault() },
        h(
          'div',
          { class: 'grid' },
          part('Name', 'daemon-name', name),
          part('Host', 'daemon-host', host),
          part('User', 'daemon-user', user),
          part('Port', 'daemon-port', port),
          part('Identity file', 'daemon-identity', key.node),
          part('Proxy jump', 'daemon-jump', jump),
          part('SSH options', 'daemon-options', options.node, true),
        ),
        h(
          'div',
          { class: 'row' },
          acting(
            editing ? 'Save' : 'Add',
            async () => {
              const fields = {
                host: host.value.trim(),
                user: user.value.trim(),
                identity_file: key.value(),
                proxy_jump: jump.value.trim(),
                options: options.read(),
              }
              if (port.value !== '') fields.port = Number(port.value)
              // What an edited daemon was brought in from its ssh config by, kept as it was.
              if (editing) for (const kept of ['alias', 'config']) if (editing[kept]) fields[kept] = editing[kept]
              const called = name.value.trim()
              await post('/api/daemons', { name: called, fields, replace: Boolean(editing) })
              // Renamed: the daemon under its old name goes.
              if (editing && editing.name !== called) await post('/api/daemons/remove', { name: editing.name })
              editing = null
              drawWriting()
              await read()
            },
            { kind: 'btn primary', busy: 'Saving…' },
          ),
          editing ? h('button', { class: 'btn quiet', type: 'button', onclick: () => ((editing = null), drawWriting()) }, 'New daemon') : null,
        ),
      ),
    )
  }

  function drawImporting() {
    const reading = acting(
      'Read SSH config',
      async () => {
        const hosts = ((await get('/api/daemons/hosts')).hosts || []).map((one) => (typeof one === 'string' ? { alias: one } : one))
        const boxes = hosts.map((one) => ({ one, box: h('input', { type: 'checkbox', 'data-alias': one.alias }) }))
        fill(
          importing,
          h('h2', {}, 'SSH config'),
          hosts.length
            ? [
                h(
                  'div',
                  { class: 'form' },
                  boxes.map(({ one, box }) => h('label', { class: 'check' }, box, h('b', { class: 'mono' }, one.alias), one.host ? h('span', { class: 'dim' }, reached(one)) : null)),
                ),
                h(
                  'p',
                  { class: 'row' },
                  acting(
                    'Import',
                    async () => {
                      const aliases = boxes.filter(({ box }) => box.checked).map(({ one }) => one.alias)
                      if (!aliases.length) return
                      await post('/api/daemons/import', { aliases })
                      await read()
                      drawImporting()
                    },
                    { kind: 'btn primary', busy: 'Importing…' },
                  ),
                ),
              ]
            : h('p', { class: 'dim' }, 'Every host it names is added already.'),
        )
      },
      { kind: 'btn', busy: 'Reading…' },
    )
    fill(importing, h('h2', {}, 'SSH config'), h('p', { class: 'dim' }, 'Import hosts from your SSH config as daemons.'), reading)
  }

  read()
    .catch((error) => {
      if (error.status === 404) return fill(holder, empty('Unavailable', 'This Humanize does not keep daemons.'))
      fill(listing, h('h2', {}, 'Daemons'), problem(error))
    })
    .then(() => {
      if (holder.contains(writing)) drawWriting(), drawImporting()
    })
  return () => {
    gone = true
    clearTimeout(again)
  }
}

/** A daemon's state, as the list says it: `state` an object, or a word beside `detail`. */
function stateOf(one) {
  if (one.state && typeof one.state === 'object') return one.state
  return { state: one.state || 'idle', detail: one.detail || '', version: one.version || '' }
}

function shownState({ state, detail = '', version = '' }) {
  return h(
    'div',
    { class: ['daemon-state', `daemon-${state}`], 'data-hmz': 'daemon-state' },
    h('span', { class: 'glyph', 'aria-hidden': 'true' }, STATES[state] || '·'),
    h('span', {}, state),
    version ? h('span', { class: 'dim' }, ` ${version}`) : null,
    detail ? h('div', { class: 'dim daemon-detail' }, detail) : null,
  )
}

/** Where a daemon is reached, as somebody would write it. */
function reached(one) {
  return `${one.user ? `${one.user}@` : ''}${one.host || one.alias || one.name}${one.port && one.port !== 22 ? `:${one.port}` : ''}`
}

/** SSH options, a name and its value a row, in order and any name more than once: one more added, any taken away. */
function pairs(values, id) {
  const rows = h('div', { class: 'list-rows', id, 'data-hmz': 'pair-editor' })
  const add = h('button', { class: 'btn small quiet', type: 'button' }, icon('plus'), 'Add')
  const row = (key, value) => {
    const line = h(
      'div',
      { class: 'list-row' },
      h('input', { type: 'text', value: key, placeholder: 'Name', 'aria-label': 'Option', class: 'pair-key' }),
      h('input', { type: 'text', value, placeholder: 'Value', 'aria-label': 'Value', class: 'pair-value' }),
      iconButton('close', 'Remove', { class: 'small', onclick: () => line.remove() }),
    )
    rows.append(line)
  }
  for (const [key, value] of values) row(key, String(value))
  add.addEventListener('click', () => {
    row('', '')
    rows.lastElementChild.querySelector('input').focus()
  })
  return {
    node: h('div', { class: 'list-editor' }, rows, add),
    read: () => [...rows.children].map((line) => [line.querySelector('.pair-key').value.trim(), line.querySelector('.pair-value').value.trim()]).filter(([key]) => key),
  }
}
