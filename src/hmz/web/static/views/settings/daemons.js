// The daemons the page can show: Local, this machine's own, which is always there, and every
// SSH or P2P daemon written down beside it -- each with its kind and how far reaching it has got.
// A new one is of a kind and a mode: SSH › SSH Config, a Host of the ssh config picked; SSH ›
// hmz-stored, written a part at a time as a runtime's SSH host is, or filled from the ssh config;
// or P2P › EasyTier, a secret and the shared nodes its network meets on. Hosts are brought in
// from the ssh config too; one is reached again, changed, or taken away, asked first.

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

/** The kinds a daemon is of, as the page names them. */
const KINDS = { ssh: 'SSH', p2p: 'P2P' }

/** How a daemon is reached: its kind, and the mode's name under it. */
const MODES = { config: ['ssh', 'SSH Config'], stored: ['ssh', 'hmz-stored'], easytier: ['p2p', 'EasyTier'] }

/** The fewest bytes, in UTF-8, a P2P daemon's secret may be. */
const SECRET = 16

/** A shared EasyTier node, as one is typed: a protocol, a host and a port. */
const NODE = /^(tcp|udp|ws|wss|quic|wg):\/\/\S+:(\d{1,5})$/

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
      h('td', {}),
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
        h('td', { 'data-hmz': 'daemon-via' }, kindOf(one)),
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
      h('div', { class: 'table-wrap' }, h('table', { class: 'daemons-table' }, h('thead', {}, h('tr', {}, h('th', {}, 'Name'), h('th', {}, 'Kind'), h('th', {}, 'Address'), h('th', {}, 'State'), h('th', {}, ''))), h('tbody', {}, local, rows))),
    )
  }

  function edit(one) {
    editing = one
    drawWriting()
    writing.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function drawWriting() {
    const was = editing || {}
    let fields = () => ({})
    let hosts = null
    // The hosts of the ssh config not added yet, read once a mode asks for them.
    const offered = () => (hosts ||= get('/api/daemons/hosts').then((said) => said.hosts || []))
    const name = text('daemon-name', was.name, 'gpu-box', { required: true, disabled: Boolean(editing) })
    const kinds = h('div', { class: 'segmented', role: 'group', 'aria-label': 'Kind', 'data-hmz': 'daemon-kind' })
    const modes = h('div', { class: 'segmented', role: 'group', 'aria-label': 'Mode', 'data-hmz': 'daemon-mode' })
    const body = h('div', { class: 'grid' })
    const pressed = (label, on, act) => h('button', { type: 'button', 'aria-pressed': String(on), onclick: act }, label)
    const pick = (mode) => {
      const kind = MODES[mode][0]
      fill(kinds, Object.entries(KINDS).map(([key, label]) => pressed(label, key === kind, () => key !== kind && pick(key === 'p2p' ? 'easytier' : 'config'))))
      fill(
        modes,
        Object.entries(MODES)
          .filter(([, [of]]) => of === kind)
          .map(([key, [, label]]) => pressed(label, key === mode, () => pick(key))),
      )
      fields = { config: drawConfig, stored: drawStored, easytier: drawEasyTier }[mode]()
    }

    /** SSH › SSH Config: a host of the ssh config, picked, and written under its Host. */
    function drawConfig() {
      // An edited daemon's own Host, which is added already and so never offered.
      const own = modeOf(was) === 'config' ? [{ alias: was.alias, name: was.name }] : []
      const options = (list, first) => [h('option', { value: '' }, first), list.map((one) => h('option', { value: one.alias, selected: one.alias === was.alias }, one.alias))]
      const alias = h('select', { id: 'daemon-alias' }, options(own, 'Reading SSH config…'))
      const said = h('div')
      let list = own
      offered().then(
        (found) => {
          list = [...own, ...found]
          fill(alias, options(list, list.length ? 'Pick a host' : 'Every host is added already'))
        },
        (error) => (fill(alias, options(own, '')), fill(said, problem(error))),
      )
      alias.addEventListener('change', () => {
        const one = list.find((each) => each.alias === alias.value)
        if (one && !name.disabled) name.value = one.name || one.alias
      })
      fill(body, part('Host', 'daemon-alias', h('div', {}, alias, said)))
      return () => {
        if (!alias.value) throw new Error('Pick a host of your SSH config.')
        // The config file it was resolved through, kept while it is the same host.
        return { via: 'ssh', alias: alias.value, ...(was.config && was.alias === alias.value ? { config: was.config } : {}) }
      }
    }

    /** SSH › hmz-stored: a part at a time, or filled from what the ssh config says of a host. */
    function drawStored() {
      const stored = modeOf(was) === 'stored' ? was : {}
      const host = text('daemon-host', stored.host, 'box.example')
      const user = text('daemon-user', stored.user, 'me')
      const port = h('input', { type: 'number', id: 'daemon-port', min: '1', max: '65535', step: '1', value: stored.port ? String(stored.port) : '', placeholder: '22' })
      const key = pathPicker({ value: stored.identity_file || '', files: true, label: 'Identity file', id: 'daemon-identity', placeholder: '~/.ssh/id_ed25519' })
      const jump = text('daemon-jump', stored.proxy_jump, 'user@jump')
      const options = pairs(stored.options || [], 'daemon-options')
      const from = h('select', { id: 'daemon-import' }, h('option', { value: '' }, 'Reading SSH config…'))
      const said = h('div')
      let list = []
      offered().then(
        (found) => {
          list = found
          fill(from, h('option', { value: '' }, list.length ? 'Pick a host' : 'No host to import'), list.map((one) => h('option', { value: one.alias }, one.alias)))
        },
        (error) => (fill(from, h('option', { value: '' }, '')), fill(said, problem(error))),
      )
      const importing = h('button', { class: 'btn quiet', type: 'button', 'data-hmz': 'daemon-import' }, 'Import')
      importing.addEventListener('click', () => {
        const one = list.find((each) => each.alias === from.value)
        if (!one) return
        host.value = one.host || ''
        user.value = one.user || ''
        port.value = one.port ? String(one.port) : ''
        key.node.querySelector('input').value = (one.identity_files || [])[0] || ''
        jump.value = one.proxy_jump || ''
        if (!name.disabled && !name.value.trim()) name.value = one.name || one.alias
      })
      fill(
        body,
        part('Import from SSH config', 'daemon-import', h('div', {}, h('div', { class: 'row' }, from, importing), said), true),
        part('Host', 'daemon-host', host),
        part('User', 'daemon-user', user),
        part('Port', 'daemon-port', port),
        part('Identity file', 'daemon-identity', key.node),
        part('Proxy jump', 'daemon-jump', jump),
        part('SSH options', 'daemon-options', options.node, true),
      )
      return () => {
        const fields = {
          via: 'ssh',
          host: host.value.trim(),
          user: user.value.trim(),
          identity_file: key.value(),
          proxy_jump: jump.value.trim(),
          options: options.read(),
        }
        if (port.value !== '') fields.port = Number(port.value)
        // What an edited daemon was brought in from its ssh config by, kept as it was.
        for (const kept of ['alias', 'config']) if (stored[kept]) fields[kept] = stored[kept]
        return fields
      }
    }

    /** P2P › EasyTier: the secret, never shown again, and the shared nodes its network meets on. */
    function drawEasyTier() {
      const keeps = was.via === 'easytier'
      const secret = h('input', { type: 'password', id: 'daemon-secret', autocomplete: 'new-password', placeholder: keeps ? 'Left empty, kept as it is' : 'At least 16 bytes' })
      const community = h('div', { class: 'list-rows', 'data-hmz': 'daemon-community' })
      const own = h('div', { class: 'list-rows', 'data-hmz': 'daemon-own-nodes' })
      const said = h('div', { class: 'loading', role: 'status' }, 'Reading the community nodes…')
      const typed = text('daemon-node', '', 'tcp://node.example:11010')
      const wrong = h('div')
      const boxes = () => [...community.querySelectorAll('input'), ...own.querySelectorAll('input')]
      const node = (holder, url, ...more) => holder.append(h('label', { class: 'check', 'data-node': url }, h('input', { type: 'checkbox', value: url }), h('span', { class: 'mono' }, url), more))
      const tick = (url) => {
        const box = boxes().find((one) => one.value === url)
        if (box) box.checked = true
      }
      for (const url of keeps ? was.peers || [] : []) node(own, url), tick(url)
      get('/api/daemons/easytier/nodes').then(
        (answer) => {
          said.remove()
          for (const one of answer.nodes || []) {
            // A node it already meets on, typed before, is the community's own.
            const there = boxes().find((box) => box.value === one.url)
            there?.closest('label').remove()
            node(
              community,
              one.url,
              h('span', { class: ['daemon-state', one.up ? 'daemon-up' : 'daemon-failed'] }, h('span', { class: 'glyph', 'aria-hidden': 'true' }, one.up ? '●' : '✕'), one.up ? 'up' : 'down'),
              one.name ? h('span', { class: 'dim' }, one.name) : null,
              one.uptime === undefined || one.uptime === '' ? null : h('span', { class: 'dim' }, `${typeof one.uptime === 'number' ? `${one.uptime}%` : one.uptime} up in 24h`),
            )
            if (there?.checked) tick(one.url)
          }
        },
        (error) => fill(said, problem(error), h('span', { class: 'dim' }, 'Add the nodes by their URL instead.')),
      )
      const add = () => {
        const url = typed.value.trim()
        fill(wrong)
        const port = Number((NODE.exec(url) || [])[2])
        if (!(port >= 1 && port <= 65535)) return fill(wrong, problem('Say a node as tcp://host:port, or udp, ws, wss, quic or wg.'))
        if (!boxes().some((box) => box.value === url)) node(own, url)
        tick(url)
        typed.value = ''
      }
      typed.addEventListener('keydown', (event) => event.key === 'Enter' && (event.preventDefault(), add()))
      fill(
        body,
        part('Secret', 'daemon-secret', secret),
        part(
          'Nodes',
          'daemon-node',
          h('div', { class: 'list-editor', 'data-hmz': 'daemon-nodes' }, said, community, own, h('div', { class: 'list-row' }, typed, h('button', { class: 'btn small quiet', type: 'button', onclick: add }, icon('plus'), 'Add node')), wrong),
          true,
        ),
      )
      return () => {
        const value = secret.value
        if (value ? new TextEncoder().encode(value).length < SECRET : !keeps) throw new Error('A secret must be at least 16 bytes.')
        const peers = [...new Set(boxes().filter((box) => box.checked).map((box) => box.value))]
        if (!peers.length) throw new Error('Pick or add at least one node.')
        return { via: 'easytier', ...(value ? { secret: value } : {}), peers }
      }
    }

    fill(
      writing,
      h('h2', {}, editing ? `Edit ${editing.name}` : 'New daemon'),
      h(
        'form',
        { class: 'form', onsubmit: (event) => event.preventDefault() },
        h('div', { class: 'row' }, kinds, modes),
        h('div', { class: 'grid' }, part('Name', 'daemon-name', name)),
        body,
        h(
          'div',
          { class: 'row' },
          acting(
            editing ? 'Save' : 'Add',
            async () => {
              const written = fields()
              const called = name.value.trim()
              await post('/api/daemons', { name: called, fields: written, replace: Boolean(editing) })
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
    pick(editing ? modeOf(editing) : 'config')
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
                      // A new daemon's form offers the hosts not added yet: those left.
                      if (!editing) drawWriting()
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

/** The mode a daemon is in: EasyTier; a Host of the ssh config alone; or written down here. */
function modeOf(one) {
  if (one.via === 'easytier') return 'easytier'
  return one.alias && !one.host ? 'config' : 'stored'
}

/** A daemon's kind and mode, as the listing says them. */
function kindOf(one) {
  const [kind, label] = MODES[modeOf(one)]
  return `${KINDS[kind]} · ${label}`
}

function text(id, value, placeholder, extra = {}) {
  return h('input', { type: 'text', id, value: value || '', placeholder, autocomplete: 'off', spellcheck: 'false', ...extra })
}

function part(label, id, input, wide = false) {
  return h('div', { class: ['field', wide && 'wide'] }, h('label', { for: id }, label), input)
}

/** Where a daemon is reached, as somebody would write it: a P2P one by the nodes it meets on. */
function reached(one) {
  if (one.via === 'easytier') return (one.peers || []).join(', ')
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
