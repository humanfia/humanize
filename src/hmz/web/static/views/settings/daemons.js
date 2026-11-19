// The daemons the page can show, as this browser keeps them: Local, this machine's own, which is
// always there, and every remote daemon kept beside it -- each with its kind and how far reaching
// it has got. A new one is of a kind: Code, a pairing code claimed at once; SSH › SSH Config, a
// Host of the ssh config picked; SSH › Custom, written a part at a time as a runtime's SSH host
// is, or filled from the ssh config; or P2P › EasyTier, a secret, the shared nodes its network
// meets on and a pairing code claimed over it. One is reached again, changed, or taken away, asked first. Each daemon that is up
// makes a pairing code for another device, and lists the devices paired with it.

import { call, daemons, forget, hello, kindOf as kindNamed, known, onState, pair, providers, reconnect, stateOf } from '../../api.js'
import { confirming } from '../../confirm.js'
import { acting, ago, fill, h, icon, iconButton, problem } from '../../dom.js'
import { pathPicker } from '../../paths.js'
import { easytier } from '../../rpc/easytier.js'
import { parsePairing } from '../../rpc/index.js'
import { copy } from '../../ui.js'

/** How far reaching each state has got, by a glyph, so nothing is said by colour alone. */
const STATES = {
  up: '●',
  connecting: '◐',
  installing: '◐',
  failed: '✕',
  idle: '○',
}

/** The kinds a daemon is of, as the page names them. */
const KINDS = { code: 'Code', ssh: 'SSH', p2p: 'P2P' }

/** How a daemon is reached: its kind, and the mode's name under it. */
const MODES = { code: ['code', 'Code'], config: ['ssh', 'SSH Config'], stored: ['ssh', 'Custom'], easytier: ['p2p', 'EasyTier'] }

/** A route of each kind but Code, as the page's pipe providers are asked whether they open it. */
const OPENED = { ssh: 'stdio:ssh://host', p2p: 'easytier:name' }

/** The fewest bytes, in UTF-8, a P2P daemon's secret may be. */
const SECRET = 16

/** The EasyTier entries a P2P daemon's route is opened with: Local's, and the desktop application's. */
const networks = easytier((method, params) => call(method, params, { on: 'local' }))

/** A shared EasyTier node, as one is typed: a protocol, a host and a port. */
const NODE = /^(tcp|udp|ws|wss|quic|wg):\/\/\S+:(\d{1,5})$/

export function draw(holder) {
  const listing = h('section', { class: 'panel', 'data-hmz': 'daemons' }, h('p', { class: 'loading', role: 'status' }, 'Reading the daemons…'))
  const writing = h('section', { class: 'panel', 'data-hmz': 'write-daemon' })
  const pairing = h('section', { class: 'panel', 'data-hmz': 'pairing' })
  const ice = h('section', { class: 'panel', 'data-hmz': 'ice-servers' })
  fill(holder, listing, writing, pairing, ice)
  let entries = []
  let editing = null
  let gone = false
  const states = new Map()
  // Where Local is: this machine, or the WSL distribution hmz runs in there.
  const where = h('td', { class: 'mono dim' }, 'this machine')
  hello('local').then((said) => fill(where, said.wsl ? `${said.wsl} (WSL)` : said.machine || 'this machine'), () => {})

  /** Reads the daemons again, and draws them. */
  async function read() {
    const mine = await known()
    if (gone) return
    entries = mine
    drawListing()
    drawPairing()
  }

  // A daemon's state, drawn again where it changes; the daemons up offer pairing.
  const unwatch = onState((name, now) => {
    if (gone) return
    if (states.has(name)) fill(states.get(name), shownState(now))
    drawPairing()
  })

  function drawListing() {
    states.clear()
    const rows = entries.map((one) => {
      const local = one.name === 'local'
      states.set(one.name, h('td', {}, shownState(stateOf(one.name))))
      return h(
        'tr',
        { 'data-hmz': 'daemon', 'data-name': one.name },
        h('td', {}, h('b', {}, local ? 'Local' : one.name)),
        h('td', { 'data-hmz': 'daemon-via' }, local ? '' : kindOf(one)),
        local ? where : h('td', { class: 'mono' }, reached(one)),
        states.get(one.name),
        h(
          'td',
          {},
          local
            ? acting('Connect', () => reconnect('local'), { kind: 'btn small quiet', busy: 'Connecting…' })
            : h(
                'div',
                { class: 'row' },
                acting('Connect', () => reconnect(one.name), { kind: 'btn small quiet', busy: 'Connecting…' }),
                h('button', { class: 'btn small quiet', type: 'button', onclick: () => edit(one) }, 'Edit'),
                confirming({
                  label: 'Remove',
                  ask: `Remove ${one.name}?`,
                  yes: 'Remove',
                  small: true,
                  act: async () => {
                    // How to reach it is all that goes: its machine keeps everything as it is.
                    await daemons.remove(one.name)
                    forget(one.name)
                    if (editing && editing.name === one.name) (editing = null), drawWriting()
                    await read()
                  },
                }),
              ),
        ),
      )
    })
    fill(
      listing,
      h('h2', {}, 'Daemons'),
      h('div', { class: 'table-wrap' }, h('table', { class: 'daemons-table' }, h('thead', {}, h('tr', {}, h('th', {}, 'Name'), h('th', {}, 'Kind'), h('th', {}, 'Address'), h('th', {}, 'State'), h('th', {}, ''))), h('tbody', {}, rows))),
    )
  }

  function edit(one) {
    editing = one
    drawWriting()
    writing.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  function drawWriting() {
    const was = editing || { name: '', id: '', routes: [] }
    const mode = editing ? modeOf(editing) : 'code'
    const fields = parsed(was.routes[0] || '')
    let made = () => ({})
    let hosts = null
    // The hosts of Local's ssh config, read once a mode asks for them.
    const offered = () => (hosts ||= call('runtimes.hosts', {}, { on: 'local' }).then((said) => said.hosts || []))
    const name = text('daemon-name', was.name, 'gpu-box', { required: true })
    const kinds = h('div', { class: 'segmented', role: 'group', 'aria-label': 'Kind', 'data-hmz': 'daemon-kind' })
    const modes = h('div', { class: 'segmented', role: 'group', 'aria-label': 'Mode', 'data-hmz': 'daemon-mode' })
    const body = h('div', { class: 'grid' })
    // Every route of a paired daemon, or those after the one its kind writes, in the order tried.
    const more = routeList(mode === 'code' ? was.routes : was.routes.slice(1), 'daemon-routes')
    const routes = h('div', { class: 'grid' })
    const pressed = (label, on, act) => h('button', { type: 'button', 'aria-pressed': String(on), onclick: act }, label)
    // SSH and P2P only where a pipe provider here opens their routes.
    const opens = (kind) => !OPENED[kind] || providers.some((one) => one.opens(OPENED[kind]))
    const pick = (chosen) => {
      const kind = MODES[chosen][0]
      fill(
        kinds,
        Object.entries(KINDS)
          .filter(([key]) => opens(key) && (!editing || key === kind))
          .map(([key, label]) => pressed(label, key === kind, () => key !== kind && pick({ code: 'code', ssh: 'config', p2p: 'easytier' }[key]))),
      )
      fill(
        modes,
        kind === 'code'
          ? []
          : Object.entries(MODES)
              .filter(([, [of]]) => of === kind)
              .map(([key, [, label]]) => pressed(label, key === chosen, () => pick(key))),
      )
      made = { code: drawCode, config: drawConfig, stored: drawStored, easytier: drawEasyTier }[chosen]()
      fill(routes, editing ? part(chosen === 'code' ? 'Routes' : 'More routes', 'daemon-routes', more.node, true) : null)
    }

    /** Code: a pairing code, claimed at once over its routes; kept only once claimed. */
    function drawCode() {
      if (editing) {
        fill(body)
        return () => ({ routes: more.read() })
      }
      const code = h('input', { type: 'password', id: 'daemon-code', autocomplete: 'off', spellcheck: 'false', placeholder: 'hmz-pair:…' })
      fill(body, part('Pairing code', 'daemon-code', code, true))
      return () => ({ code: code.value.trim() })
    }

    /** SSH › SSH Config: a host of the ssh config, picked, and reached as ssh resolves it. */
    function drawConfig() {
      const taken = new Set(entries.flatMap((one) => one.routes))
      const own = mode === 'config' ? [fields.host] : []
      const options = (list, first) => [h('option', { value: '' }, first), list.map((one) => h('option', { value: one, selected: one === fields.host && mode === 'config' }, one))]
      const alias = h('select', { id: 'daemon-alias' }, options(own, 'Reading SSH config…'))
      const said = h('div')
      offered().then(
        (found) => {
          // Those not added yet, and an edited daemon's own.
          const list = [...own, ...found.map((one) => one.alias).filter((one) => !own.includes(one) && !taken.has(sshRoute({ host: one })))]
          fill(alias, options(list, list.length ? 'Pick a host' : 'Every host is added already'))
        },
        (error) => (fill(alias, options(own, '')), fill(said, problem(error))),
      )
      alias.addEventListener('change', () => {
        if (alias.value && !name.value.trim()) name.value = alias.value.replace(/[^A-Za-z0-9._-]/g, '-').replace(/^[._-]+/, '')
      })
      fill(body, part('Host', 'daemon-alias', h('div', {}, alias, said)))
      return () => {
        if (!alias.value) throw new Error('Pick a host of your SSH config.')
        return { route: sshRoute({ host: alias.value }) }
      }
    }

    /** SSH › Custom: a part at a time, or filled from what the ssh config says of a host. */
    function drawStored() {
      const stored = mode === 'stored' ? fields : {}
      const host = text('daemon-host', stored.host, 'box.example')
      const user = text('daemon-user', stored.user, 'me')
      const port = h('input', { type: 'number', id: 'daemon-port', min: '1', max: '65535', step: '1', value: stored.port ? String(stored.port) : '', placeholder: '22' })
      const key = pathPicker({ value: stored.identity || '', files: true, label: 'Identity file', id: 'daemon-identity', placeholder: '~/.ssh/id_ed25519', from: 'local' })
      const jump = text('daemon-jump', stored.jump, 'user@jump')
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
        if (!name.value.trim()) name.value = one.alias.replace(/[^A-Za-z0-9._-]/g, '-').replace(/^[._-]+/, '')
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
        if (!host.value.trim()) throw new Error('Say the host.')
        return { route: sshRoute({ host: host.value.trim(), user: user.value.trim(), port: port.value, identity: key.value(), jump: jump.value.trim(), options: options.read() }) }
      }
    }

    /** P2P › EasyTier: the secret, never shown again, and the shared nodes its network meets on. */
    function drawEasyTier() {
      const keeps = mode === 'easytier'
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
      // The nodes the entry of its name meets on, as what opens its route keeps it.
      if (keeps) {
        networks.list().then(
          (kept) => {
            const entry = kept.find((one) => one.name === fields.name)
            for (const url of entry ? entry.nodes : []) {
              if (!boxes().some((box) => box.value === url)) node(own, url)
              tick(url)
            }
          },
          () => {},
        )
      }
      call('easytier.nodes', {}, { on: 'local' }).then(
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
      // A new one is claimed by its pairing code: an untrusted route is held to the id it gives.
      const code = editing ? null : h('input', { type: 'password', id: 'daemon-code', autocomplete: 'off', spellcheck: 'false', placeholder: 'hmz-pair:…' })
      fill(
        body,
        part('Secret', 'daemon-secret', secret),
        code ? part('Pairing code', 'daemon-code', code, true) : null,
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
        const nodes = [...new Set(boxes().filter((box) => box.checked).map((box) => box.value))]
        if (!nodes.length) throw new Error('An EasyTier daemon needs at least one node.')
        // Refused before the entry is written, where it is no pairing code.
        if (code) parsePairing(code.value)
        return { easytier: { ...(value ? { secret: value } : {}), nodes }, ...(code ? { code: code.value.trim() } : {}) }
      }
    }

    /** Writes what the form holds: a daemon claimed, or kept as its routes say. */
    async function save() {
      const said = made()
      const called = name.value.trim()
      if (said.easytier) {
        // A secret written is never read back: one renamed is written anew under its name.
        if (editing && editing.name !== called && !said.easytier.secret) throw new Error('Say the secret again to rename a P2P daemon.')
        // The entry of that name is what its route opens with: Local's through `hmz web`
        // (Section 4.8.7 of protocol/web.md), the app's in the desktop application (Section
        // 3.12.6 of protocol/desktop.md); the page is never handed the secret again.
        await networks.set({ name: called, ...said.easytier })
        said.route = `easytier:${called}`
      }
      if (said.code !== undefined) {
        await pair(called, said.code, said.route)
      } else {
        const routes = said.route ? [said.route, ...more.read().filter((one) => one !== said.route)] : said.routes
        if (!routes.length) throw new Error('A daemon needs at least one route.')
        if (editing) {
          await daemons.update(editing.name, { name: called, routes })
          // Reached afresh, by its new name or routes.
          forget(editing.name)
          if (said.easytier && editing.name !== called) await networks.remove(editing.name).catch(() => {})
        } else {
          await daemons.add({ name: called, id: '', routes })
        }
      }
      editing = null
      drawWriting()
      await read()
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
        routes,
        h(
          'div',
          { class: 'row' },
          acting(editing ? 'Save' : 'Add', save, { kind: 'btn primary', busy: 'Saving…' }),
          editing ? h('button', { class: 'btn quiet', type: 'button', onclick: () => ((editing = null), drawWriting()) }, 'New daemon') : null,
        ),
      ),
    )
    pick(mode)
  }

  /** For each daemon up: a pairing code for another device, and the devices paired with it. */
  function drawPairing() {
    const up = entries.filter((one) => stateOf(one.name).state === 'up')
    if (!up.length) {
      // Drawn afresh once one is up again.
      pairing.dataset.drawn = ''
      return fill(pairing)
    }
    if (pairing.dataset.drawn === up.map((one) => one.name).join('\n')) return
    pairing.dataset.drawn = up.map((one) => one.name).join('\n')
    fill(
      pairing,
      h('h2', {}, 'Devices'),
      up.map((one) => {
        const on = one.name
        const code = h('div', { 'aria-live': 'polite', 'data-hmz': 'pairing-code' })
        const devices = h('div', { 'data-hmz': 'devices' })
        const list = () =>
          call('devices.list', {}, { on }).then(
            (answer) =>
              fill(
                devices,
                answer.devices.length
                  ? h(
                      'ul',
                      { class: 'list-rows' },
                      answer.devices.map((device) =>
                        h(
                          'li',
                          { class: 'row', 'data-hmz': 'device', 'data-name': device.name },
                          h('b', {}, device.name),
                          h('span', { class: 'dim' }, device.live ? `${device.live} live` : device.seen ? `seen ${ago(device.seen)}` : 'never seen'),
                          device.name === 'local'
                            ? null
                            : confirming({ label: 'Revoke', ask: `Revoke ${device.name}?`, yes: 'Revoke', small: true, act: async () => (await call('devices.revoke', { name: device.name }, { on }), list()) }),
                        ),
                      ),
                    )
                  : h('p', { class: 'dim' }, 'No device paired.'),
              ),
            (error) => fill(devices, problem(error)),
          )
        list()
        return h(
          'div',
          { class: 'form', 'data-hmz': 'daemon-devices', 'data-name': on },
          h('h3', {}, on === 'local' ? 'Local' : on),
          h(
            'div',
            { class: 'row' },
            acting(
              'Pair a device',
              async () => {
                const made = await call('pair.create', {}, { on })
                fill(
                  code,
                  h('code', { class: 'mono pairing-code' }, made.code),
                  h('span', { class: 'dim' }, ` Expires ${new Date(made.expires * 1000).toLocaleTimeString()}`),
                  iconButton('copy', 'Copy code', { class: 'small', onclick: () => copy(made.code, 'Code copied') }),
                )
              },
              { kind: 'btn small', busy: 'Making…' },
            ),
          ),
          code,
          devices,
        )
      }),
    )
  }

  /** The STUN and TURN servers WebRTC uses, as this browser keeps them. */
  function drawIce(servers) {
    const shown = servers.map((one) => [].concat(one.urls).join(' ') + (one.username ? ` ${one.username}${one.credential ? ' ••••' : ''}` : '')).join('\n')
    const lines = h('textarea', { id: 'ice-servers', rows: '3', spellcheck: 'false', placeholder: 'stun:stun.example:3478\nturn:turn.example:3478 user password' }, shown)
    fill(
      ice,
      h('h2', {}, 'WebRTC servers'),
      h(
        'div',
        { class: 'form' },
        part('STUN and TURN', 'ice-servers', lines, true),
        h(
          'div',
          { class: 'row' },
          acting(
            'Save',
            async () => {
              const written = lines.value
                .split('\n')
                .map((line) => line.trim().split(/\s+/))
                .filter((words) => words[0])
                .map(([urls, username, credential]) => {
                  // A credential left as it was shown is the one kept.
                  const was = servers.find((one) => [].concat(one.urls).join(' ') === urls)
                  const kept = credential === '••••' ? was?.credential : credential
                  return { urls, ...(username ? { username } : {}), ...(kept ? { credential: kept } : {}) }
                })
              await daemons.setIceServers(written)
              drawIce(written)
            },
            { kind: 'btn small', busy: 'Saving…', done: 'Saved' },
          ),
        ),
      ),
    )
  }

  read()
    .catch((error) => fill(listing, h('h2', {}, 'Daemons'), problem(error)))
    .then(() => {
      if (holder.contains(writing)) drawWriting()
    })
  daemons.iceServers().then(drawIce, (error) => fill(ice, problem(error)))
  return () => {
    gone = true
    unwatch()
  }
}

function shownState({ state, detail = '' }) {
  return h(
    'div',
    { class: ['daemon-state', `daemon-${state}`], 'data-hmz': 'daemon-state' },
    h('span', { class: 'glyph', 'aria-hidden': 'true' }, STATES[state] || '·'),
    h('span', {}, state),
    detail ? h('div', { class: 'dim daemon-detail' }, detail) : null,
  )
}

/**
 * A `stdio:ssh` route's parts (Section 3.3 of protocol/wire.md), percent-decoded; for any other
 * route, an EasyTier one's name.
 */
function parsed(route) {
  if (route.startsWith('easytier:')) return { name: route.slice('easytier:'.length) }
  const found = /^stdio:ssh:\/\/(?:([^@/?]*)@)?(\[[^\]]*\]|[^:/?]*)(?::([0-9]*))?(?:\?(.*))?$/.exec(route)
  if (!found) return {}
  const decoded = (text) => {
    try {
      return decodeURIComponent(text)
    } catch {
      return text
    }
  }
  const said = { user: decoded(found[1] || ''), host: decoded(found[2] || ''), port: found[3] || '', identity: '', jump: '', options: [] }
  for (const param of (found[4] || '').split('&').filter(Boolean)) {
    const [key, ...rest] = param.split('=')
    const value = decoded(rest.join('='))
    if (key === 'identity') said.identity = value
    else if (key === 'jump') said.jump = value
    else if (key === 'option') {
      const [option, ...more] = value.split('=')
      said.options.push([option, more.join('=')])
    }
  }
  return said
}

/** A `stdio:ssh` route of its parts, each percent-encoded. */
function sshRoute({ host, user = '', port = '', identity = '', jump = '', options = [] }) {
  const params = [
    ...(identity ? [`identity=${encodeURIComponent(identity)}`] : []),
    ...(jump ? [`jump=${encodeURIComponent(jump)}`] : []),
    ...options.map(([key, value]) => `option=${encodeURIComponent(`${key}=${value}`)}`),
  ]
  return `stdio:ssh://${user ? `${encodeURIComponent(user)}@` : ''}${host.startsWith('[') ? host : encodeURIComponent(host)}${port ? `:${port}` : ''}${params.length ? `?${params.join('&')}` : ''}`
}

/** The mode a daemon is in, by its first route: EasyTier; a Host of the ssh config alone; ssh written down; or paired. */
function modeOf(one) {
  const first = one.routes[0] || ''
  if (first.startsWith('easytier:')) return 'easytier'
  if (!first.startsWith('stdio:ssh:')) return 'code'
  return /^stdio:ssh:\/\/[^@:?]+$/.test(first) ? 'config' : 'stored'
}

/** A daemon's kind and mode, as the listing says them. */
function kindOf(one) {
  const mode = modeOf(one)
  return mode === 'code' ? kindNamed(one) : `${kindNamed(one)} · ${MODES[mode][1]}`
}

function text(id, value, placeholder, extra = {}) {
  return h('input', { type: 'text', id, value: value || '', placeholder, autocomplete: 'off', spellcheck: 'false', ...extra })
}

function part(label, id, input, wide = false) {
  return h('div', { class: ['field', wide && 'wide'] }, h('label', { for: id }, label), input)
}

/** Where a daemon is reached, as its routes say, the first first. */
function reached(one) {
  return one.routes.join(', ')
}

/** Routes, one a row, in the order tried: one more added, any taken away or moved up. */
function routeList(values, id) {
  const rows = h('div', { class: 'list-rows', id, 'data-hmz': 'route-editor' })
  const add = h('button', { class: 'btn small quiet', type: 'button' }, icon('plus'), 'Add')
  const row = (value) => {
    const line = h(
      'div',
      { class: 'list-row' },
      h('input', { type: 'text', value, placeholder: 'tcp://host:port', 'aria-label': 'Route', class: 'route', spellcheck: 'false' }),
      iconButton('up', 'Move up', { class: 'small', onclick: () => line.previousElementSibling && line.previousElementSibling.before(line) }),
      iconButton('close', 'Remove', { class: 'small', onclick: () => line.remove() }),
    )
    rows.append(line)
  }
  for (const value of values) row(value)
  add.addEventListener('click', () => {
    row('')
    rows.lastElementChild.querySelector('input').focus()
  })
  return {
    node: h('div', { class: 'list-editor' }, rows, add),
    read: () => [...rows.querySelectorAll('.route')].map((input) => input.value.trim()).filter(Boolean),
  }
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
