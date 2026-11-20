// The daemons the page can show, as this browser keeps them: Local, this machine's own, which is
// always there, and every remote daemon kept beside it -- each with its kind and how far reaching
// it has got. A new one is of a kind: Code, a pairing code claimed at once; SSH › SSH Config, a
// Host of the ssh config picked; SSH › Custom, written a part at a time as a runtime's SSH host
// is, or filled from the ssh config; or P2P › EasyTier, a secret, the shared nodes its network
// meets on and a pairing code claimed over it. Beside the form, what the kind chosen is and what
// the other machine needs for it. One is reached again, changed, or taken away, asked first.
// Under each daemon's line is what is its own: once it is up, a pairing code made for another
// device and the devices paired with it; and, for a remote one, the STUN and TURN servers its
// `webrtc:` routes are opened with (Section 3.13.20 and 3.13.21 of protocol/web.md).

import { call, daemons, forget, hello, kindOf as kindNamed, known, onState, pair, providers, reconnect, stateOf } from '../../api.js'
import { confirming } from '../../confirm.js'
import { acting, ago, fill, h, icon, iconButton, problem } from '../../dom.js'
import { locale, pieces, t } from '../../i18n.js'
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

/** How far reaching has got, as the page says it. */
const SAID = { up: t('up'), connecting: t('connecting'), installing: t('installing'), failed: t('failed'), idle: t('idle@@link') }

/** The kinds a daemon is of, as the page names them. */
const KINDS = { code: t('Code@@pairing'), ssh: 'SSH', p2p: 'P2P' }

/** How a daemon is reached: its kind, and the mode's name under it. */
const MODES = { code: ['code', t('Code@@pairing')], config: ['ssh', t('SSH Config')], stored: ['ssh', t('Custom')], easytier: ['p2p', 'EasyTier'] }

/**
 * What each kind is and what the other machine needs for it, said beside the form: what it is
 * called, then a paragraph each.
 */
const ABOUT = {
  code: () => [
    t('Pair with a code'),
    pieces('The other machine makes a one-time pairing code: run {command} there, or press Pair a device on a page that already reaches it. Paste the code here within 10 minutes; it works once.', {
      command: h('code', { class: 'mono' }, 'hmz daemon pair'),
    }),
    t('Its daemon has to listen somewhere this one can reach: a port, a relay or WebRTC.'),
  ],
  ssh: () => [
    t('Reach over SSH'),
    t('Reaches a machine the way ssh does, with your own keys and SSH config. Nothing has to run there first: hmz is started over the connection, and installed where it is missing. You are never asked for a password.'),
  ],
  p2p: () => [
    t('Peer to peer'),
    t('Both machines join one private EasyTier network, so they reach each other behind NAT, with no open port and no ssh. Give both the same secret and at least one node in common, and the first time that machine’s pairing code.'),
  ],
}

/** What a mode under a kind is, said under what its kind is. */
const MODE_ABOUT = {
  config: () => t('SSH Config: pick a Host of ~/.ssh/config. It is resolved through your config every time, so editing the config edits the daemon.'),
  stored: () => t('Custom: write the host a part at a time, or import one from your SSH config. This page keeps what you write, and the config is not read again.'),
}

/** What the STUN and TURN servers of a daemon are for, and how they are written. */
const ICE_ABOUT = () =>
  t('Only used where this daemon is reached over a webrtc: route. STUN finds a direct path between the two; TURN relays where there is none. One a line: the URL, then a TURN server’s username and credential. Empty suits a simple network.')

/** A STUN or TURN server's URL, as one is typed. */
const ICE = /^(stun|stuns|turn|turns):\S+$/

/** What stands for a credential kept: it is never shown again. */
const MASKED = '••••'

/** A route of each kind but Code, as the page's pipe providers are asked whether they open it. */
const OPENED = { ssh: 'stdio:ssh://host', p2p: 'easytier:name' }

/** The fewest bytes, in UTF-8, a P2P daemon's secret may be. */
const SECRET = 16

/** The EasyTier entries a P2P daemon's route is opened with: Local's, and the desktop application's. */
const networks = easytier((method, params) => call(method, params, { on: 'local' }))

/** A shared EasyTier node, as one is typed: a protocol, a host and a port. */
const NODE = /^(tcp|udp|ws|wss|quic|wg):\/\/\S+:(\d{1,5})$/

export function draw(holder) {
  const listing = h('section', { class: 'panel', 'data-hmz': 'daemons' }, h('p', { class: 'loading', role: 'status' }, t('Reading the daemons…')))
  const writing = h('section', { class: 'panel', 'data-hmz': 'write-daemon' })
  fill(holder, listing, writing)
  let entries = []
  /** What stands under each daemon's line, by its name, kept for as long as its entry is as it was. */
  let under = new Map()
  let editing = null
  let gone = false
  const states = new Map()
  const connects = new Map()
  // Where Local is: this machine, or the WSL distribution hmz runs in there.
  const where = h('td', { class: 'mono dim' }, t('this machine'))
  hello('local').then((said) => fill(where, said.wsl ? `${said.wsl} (WSL)` : said.machine || t('this machine')), () => {})

  /** Reads the daemons again, and draws them. */
  async function read() {
    const mine = await known()
    if (gone) return
    entries = mine
    drawListing()
  }

  // A daemon's state, drawn again where it changes; one that is up offers pairing.
  const unwatch = onState((name, now) => {
    if (gone) return
    if (states.has(name)) fill(states.get(name), shownState(now))
    // A daemon that is reached offers no Connect.
    if (connects.has(name)) connects.get(name).hidden = now.state === 'up'
    if (under.has(name)) drawDevices(under.get(name))
  })

  /** The Connect of one daemon's line, drawn only while the daemon is not reached. */
  function connect(name) {
    const button = acting(t('Connect'), () => reconnect(name), { kind: 'btn small quiet', busy: t('Connecting…') })
    button.hidden = stateOf(name).state === 'up'
    connects.set(name, button)
    return button
  }

  function drawListing() {
    states.clear()
    connects.clear()
    const kept = new Map()
    const rows = entries.map((one) => {
      const local = one.name === 'local'
      states.set(one.name, h('td', {}, shownState(stateOf(one.name))))
      // What is under its line stays as it is drawn while its entry does: a code just made, a list half typed.
      const own = under.get(one.name)?.key === keyOf(one) ? under.get(one.name) : drawOwn(one)
      kept.set(one.name, own)
      drawDevices(own)
      const line = h(
        'tr',
        { 'data-hmz': 'daemon', 'data-name': one.name },
        h('td', {}, h('b', {}, local ? t('Local') : one.name)),
        h('td', { 'data-hmz': 'daemon-via' }, local ? '' : kindOf(one)),
        local ? where : h('td', { class: 'mono' }, reached(one)),
        states.get(one.name),
        h(
          'td',
          {},
          local
            ? connect('local')
            : h(
                'div',
                { class: 'row' },
                connect(one.name),
                h('button', { class: 'btn small quiet', type: 'button', onclick: () => edit(one) }, t('Edit')),
                confirming({
                  label: t('Remove'),
                  ask: t('Remove {name}?', { name: one.name }),
                  yes: t('Remove'),
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
      return [line, h('tr', { class: 'daemon-own', 'data-hmz': 'daemon-own', 'data-name': one.name }, h('td', { colspan: '5' }, own.node))]
    })
    under = kept
    fill(
      listing,
      h('h2', {}, t('Daemons')),
      h(
        'p',
        { class: 'dim', 'data-hmz': 'daemons-about' },
        t('Every machine this page reaches. Under each are its devices: the browsers and machines paired with it, which may reach it. Pair a device makes a one-time code to enter under New daemon › Code on the other device.'),
      ),
      entries.length > 1 ? null : h('p', { class: 'dim', 'data-hmz': 'daemons-none' }, t('Only Local so far. Add another machine under New daemon.')),
      h('div', { class: 'table-wrap' }, h('table', { class: 'daemons-table' }, h('thead', {}, h('tr', {}, h('th', {}, t('Name')), h('th', {}, t('Kind')), h('th', {}, t('Address')), h('th', {}, t('State')), h('th', {}, ''))), h('tbody', {}, rows))),
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
    const kinds = h('div', { class: 'segmented', role: 'group', 'aria-label': t('Kind'), 'data-hmz': 'daemon-kind' })
    const modes = h('div', { class: 'segmented', role: 'group', 'aria-label': t('Mode'), 'data-hmz': 'daemon-mode' })
    const body = h('div', { class: 'grid' })
    const about = h('aside', { class: 'daemon-about', 'data-hmz': 'daemon-about', 'aria-live': 'polite' })
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
      fill(
        routes,
        editing ? part(chosen === 'code' ? t('Routes') : t('More routes'), 'daemon-routes', more.node, true, t('Tried in this order, each as tcp://host:port, relay:wss://…, webrtc:wss://… or another route.')) : null,
      )
      // One paired already has no code to paste: what is said is what is left to change.
      const [title, ...said] = editing && kind === 'code' ? [t('Paired with a code'), t('Paired with a one-time code that machine made, and held to that machine’s id since. What is left to change is what this page calls it and the routes it is reached by.')] : ABOUT[kind]()
      fill(about, h('h3', {}, title), said.map((one) => h('p', {}, one)), MODE_ABOUT[chosen] ? h('p', {}, MODE_ABOUT[chosen]()) : null)
    }

    /** Code: a pairing code, claimed at once over its routes; kept only once claimed. */
    function drawCode() {
      if (editing) {
        fill(body)
        return () => ({ routes: more.read() })
      }
      const code = h('input', { type: 'password', id: 'daemon-code', autocomplete: 'off', spellcheck: 'false', placeholder: 'hmz-pair:…' })
      // Its servers are asked before it is claimed: a code whose routes are WebRTC's may need them to be.
      const servers = iceBox('daemon-ice', [])
      const advanced = h('details', { class: 'fold field wide', 'data-hmz': 'daemon-advanced' }, h('summary', {}, t('Advanced')), part(t('STUN and TURN'), 'daemon-ice', servers, true, ICE_ABOUT()))
      // Opened by a code that is reached over WebRTC, which is where they matter.
      code.addEventListener('input', () => {
        try {
          if (parsePairing(code.value).routes.some((route) => route.startsWith('webrtc:'))) advanced.open = true
        } catch {
          // Not a code yet.
        }
      })
      fill(body, part(t('Pairing code'), 'daemon-code', code, true, CODE_ABOUT()), advanced)
      return () => ({ code: code.value.trim(), ice: readIce(servers.value) })
    }

    /** SSH › SSH Config: a host of the ssh config, picked, and reached as ssh resolves it. */
    function drawConfig() {
      const taken = new Set(entries.flatMap((one) => one.routes))
      const own = mode === 'config' ? [fields.host] : []
      const options = (list, first) => [h('option', { value: '' }, first), list.map((one) => h('option', { value: one, selected: one === fields.host && mode === 'config' }, one))]
      const alias = h('select', { id: 'daemon-alias' }, options(own, t('Reading SSH config…')))
      const said = h('div')
      offered().then(
        (found) => {
          // Those not added yet, and an edited daemon's own.
          const list = [...own, ...found.map((one) => one.alias).filter((one) => !own.includes(one) && !taken.has(sshRoute({ host: one })))]
          fill(alias, options(list, list.length ? t('Pick a host') : t('Every host is added already')))
        },
        (error) => (fill(alias, options(own, '')), fill(said, problem(error))),
      )
      alias.addEventListener('change', () => {
        if (alias.value && !name.value.trim()) name.value = alias.value.replace(/[^A-Za-z0-9._-]/g, '-').replace(/^[._-]+/, '')
      })
      fill(body, part(t('Host'), 'daemon-alias', h('div', {}, alias, said), false, t('Hosts come from ~/.ssh/config.')))
      return () => {
        if (!alias.value) throw new Error(t('Pick a host of your SSH config.'))
        return { route: sshRoute({ host: alias.value }) }
      }
    }

    /** SSH › Custom: a part at a time, or filled from what the ssh config says of a host. */
    function drawStored() {
      const stored = mode === 'stored' ? fields : {}
      const host = text('daemon-host', stored.host, 'box.example')
      const user = text('daemon-user', stored.user, 'me')
      const port = h('input', { type: 'number', id: 'daemon-port', min: '1', max: '65535', step: '1', value: stored.port ? String(stored.port) : '', placeholder: '22' })
      const key = pathPicker({ value: stored.identity || '', files: true, label: t('Identity file'), id: 'daemon-identity', placeholder: '~/.ssh/id_ed25519', from: 'local' })
      const jump = text('daemon-jump', stored.jump, 'user@jump')
      const options = pairs(stored.options || [], 'daemon-options')
      const from = h('select', { id: 'daemon-import' }, h('option', { value: '' }, t('Reading SSH config…')))
      const said = h('div')
      let list = []
      offered().then(
        (found) => {
          list = found
          fill(from, h('option', { value: '' }, list.length ? t('Pick a host') : t('No host to import')), list.map((one) => h('option', { value: one.alias }, one.alias)))
        },
        (error) => (fill(from, h('option', { value: '' }, '')), fill(said, problem(error))),
      )
      const importing = h('button', { class: 'btn quiet', type: 'button', 'data-hmz': 'daemon-import' }, t('Import'))
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
        part(t('Import from SSH config'), 'daemon-import', h('div', {}, h('div', { class: 'row' }, from, importing), said), true, t('Hosts come from ~/.ssh/config.')),
        part(t('Host'), 'daemon-host', host),
        part(t('User'), 'daemon-user', user),
        part(t('Port'), 'daemon-port', port),
        part(t('Identity file'), 'daemon-identity', key.node),
        part(t('Proxy jump'), 'daemon-jump', jump),
        part(t('SSH options'), 'daemon-options', options.node, true),
      )
      return () => {
        if (!host.value.trim()) throw new Error(t('Say the host.'))
        return { route: sshRoute({ host: host.value.trim(), user: user.value.trim(), port: port.value, identity: key.value(), jump: jump.value.trim(), options: options.read() }) }
      }
    }

    /** P2P › EasyTier: the secret, never shown again, and the shared nodes its network meets on. */
    function drawEasyTier() {
      const keeps = mode === 'easytier'
      const secret = h('input', { type: 'password', id: 'daemon-secret', autocomplete: 'new-password', placeholder: keeps ? t('Left empty, kept as it is') : t('At least 16 bytes') })
      const community = h('div', { class: 'list-rows', 'data-hmz': 'daemon-community' })
      const own = h('div', { class: 'list-rows', 'data-hmz': 'daemon-own-nodes' })
      const said = h('div', { class: 'loading', role: 'status' }, t('Reading the community nodes…'))
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
              h('span', { class: ['daemon-state', one.up ? 'daemon-up' : 'daemon-failed'] }, h('span', { class: 'glyph', 'aria-hidden': 'true' }, one.up ? '●' : '✕'), one.up ? t('up') : t('down')),
              one.name ? h('span', { class: 'dim' }, one.name) : null,
              one.uptime === undefined || one.uptime === '' ? null : h('span', { class: 'dim' }, t('{uptime} up in 24h', { uptime: typeof one.uptime === 'number' ? `${one.uptime}%` : one.uptime })),
            )
            if (there?.checked) tick(one.url)
          }
        },
        (error) => fill(said, problem(error), h('span', { class: 'dim' }, t('Add the nodes by their URL instead.'))),
      )
      const add = () => {
        const url = typed.value.trim()
        fill(wrong)
        const port = Number((NODE.exec(url) || [])[2])
        if (!(port >= 1 && port <= 65535)) return fill(wrong, problem(t('Say a node as tcp://host:port, or udp, ws, wss, quic or wg.')))
        if (!boxes().some((box) => box.value === url)) node(own, url)
        tick(url)
        typed.value = ''
      }
      typed.addEventListener('keydown', (event) => event.key === 'Enter' && (event.preventDefault(), add()))
      // A new one is claimed by its pairing code: an untrusted route is held to the id it gives.
      const code = editing ? null : h('input', { type: 'password', id: 'daemon-code', autocomplete: 'off', spellcheck: 'false', placeholder: 'hmz-pair:…' })
      fill(
        body,
        part(t('Secret'), 'daemon-secret', secret, false, t('The secret the other machine’s EasyTier entry holds.')),
        code ? part(t('Pairing code'), 'daemon-code', code, true, CODE_ABOUT()) : null,
        part(
          t('Nodes'),
          'daemon-node',
          h('div', { class: 'list-editor', 'data-hmz': 'daemon-nodes' }, said, community, own, h('div', { class: 'list-row' }, typed, h('button', { class: 'btn small quiet', type: 'button', onclick: add }, icon('plus'), t('Add node'))), wrong),
          true,
          t('Where the two machines meet: tick at least one the other machine uses too.'),
        ),
      )
      return () => {
        const value = secret.value
        if (value ? new TextEncoder().encode(value).length < SECRET : !keeps) throw new Error(t('A secret must be at least 16 bytes.'))
        const nodes = [...new Set(boxes().filter((box) => box.checked).map((box) => box.value))]
        if (!nodes.length) throw new Error(t('An EasyTier daemon needs at least one node.'))
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
        if (editing && editing.name !== called && !said.easytier.secret) throw new Error(t('Say the secret again to rename a P2P daemon.'))
        // The entry of that name is what its route opens with: Local's through `hmz web`
        // (Section 4.8.7 of protocol/web.md), the app's in the desktop application (Section
        // 3.12.6 of protocol/desktop.md); the page is never handed the secret again.
        await networks.set({ name: called, ...said.easytier })
        said.route = `easytier:${called}`
      }
      if (said.code !== undefined) {
        await pair(called, said.code, said.route, said.ice)
      } else {
        const routes = said.route ? [said.route, ...more.read().filter((one) => one !== said.route)] : said.routes
        if (!routes.length) throw new Error(t('A daemon needs at least one route.'))
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
      h('h2', {}, editing ? t('Edit {name}', { name: editing.name }) : t('New daemon')),
      h(
        'div',
        { class: 'daemon-write' },
        h(
          'form',
          { class: 'form', onsubmit: (event) => event.preventDefault() },
          h('div', { class: 'row' }, kinds, modes),
          h('div', { class: 'grid' }, part(t('Name'), 'daemon-name', name, false, t('What this page calls it: letters, digits, ., _ and -.'))),
          body,
          routes,
          h(
            'div',
            { class: 'row' },
            acting(editing ? t('Save') : t('Add'), save, { kind: 'btn primary', busy: t('Saving…') }),
            editing ? h('button', { class: 'btn quiet', type: 'button', onclick: () => ((editing = null), drawWriting()) }, t('New daemon')) : null,
          ),
        ),
        about,
      ),
    )
    pick(mode)
  }

  /**
   * What is a daemon's own, to stand under its line: its devices, and for a remote one its STUN
   * and TURN servers, folded away unless a route of it is WebRTC's.
   */
  function drawOwn(one) {
    const devices = h('div', { class: 'form', 'data-hmz': 'daemon-devices', 'data-name': one.name })
    const own = { name: one.name, key: keyOf(one), devices, up: null, node: h('div', { class: 'daemon-own-body' }, devices) }
    if (one.name === 'local') return own
    const id = `daemon-ice-${one.name}`
    const servers = iceBox(id, one.ice || [])
    own.node.append(
      h(
        'details',
        { class: 'fold', 'data-hmz': 'daemon-ice', 'data-name': one.name, open: one.routes.some((route) => route.startsWith('webrtc:')) },
        h('summary', {}, t('WebRTC servers')),
        h(
          'div',
          { class: 'form' },
          part(t('STUN and TURN'), id, servers, true, ICE_ABOUT()),
          h(
            'div',
            { class: 'row' },
            acting(
              t('Save'),
              async () => {
                const written = readIce(servers.value, one.ice || [])
                await daemons.update(one.name, { ice: written })
                // Kept as they are drawn, a credential masked from here on.
                one.ice = written
                own.key = keyOf(one)
                servers.value = shownIce(written)
                // Reached afresh with them, where it was being reached.
                if (stateOf(one.name).state !== 'idle') await reconnect(one.name)
              },
              { kind: 'btn small', busy: t('Saving…'), done: t('Saved') },
            ),
          ),
        ),
      ),
    )
    return own
  }

  /** A daemon's devices: once it is up, a pairing code for another device, and the devices paired with it. */
  function drawDevices(own) {
    const on = own.name
    const up = stateOf(on).state === 'up'
    if (own.up === up) return
    own.up = up
    const heading = h('h3', {}, t('Devices'))
    if (!up) return fill(own.devices, heading, h('p', { class: 'dim', 'data-hmz': 'devices-none' }, t('Not reached. Connect to it to pair a device and to see the devices paired with it.')))
    const code = h('div', { 'aria-live': 'polite', 'data-hmz': 'pairing-code' })
    // A line is held for them while they are read, so that what is under it moves the least.
    const devices = h('div', { 'data-hmz': 'devices' }, h('p', { class: 'loading', role: 'status' }, t('Reading the devices…')))
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
                      h('span', { class: 'dim' }, device.live ? t('{n} live@@links', { n: device.live }) : device.seen ? t('seen {when}', { when: ago(device.seen) }) : t('never seen')),
                      device.name === 'local'
                        ? null
                        : confirming({
                            label: t('Revoke'),
                            ask: t('Revoke {name}?', { name: device.name }),
                            yes: t('Revoke'),
                            small: true,
                            act: async () => (await call('devices.revoke', { name: device.name }, { on }), list()),
                          }),
                    ),
                  ),
                )
              : h('p', { class: 'dim' }, t('No device paired yet. Pair a device makes a code to enter on the other device.')),
          ),
        (error) => fill(devices, problem(error)),
      )
    list()
    fill(
      own.devices,
      heading,
      h(
        'div',
        { class: 'row' },
        acting(
          t('Pair a device'),
          async () => {
            const made = await call('pair.create', {}, { on })
            fill(
              code,
              h('code', { class: 'mono pairing-code' }, made.code),
              h('span', { class: 'dim' }, t('Expires {time}', { time: new Date(made.expires * 1000).toLocaleTimeString(locale()) })),
              iconButton('copy', t('Copy code'), { class: 'small', onclick: () => copy(made.code, t('Code copied')) }),
            )
          },
          { kind: 'btn small', busy: t('Making…') },
        ),
      ),
      code,
      devices,
    )
  }

  read()
    .catch((error) => fill(listing, h('h2', {}, t('Daemons')), problem(error)))
    .then(() => {
      if (holder.contains(writing)) drawWriting()
    })
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
    h('span', {}, SAID[state] || state),
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

/** A field: what it is called, what is written in it, and under it, where given, what it is for. */
function part(label, id, input, wide = false, hint = '') {
  return h('div', { class: ['field', wide && 'wide'] }, h('label', { for: id }, label), input, hint ? h('div', { class: 'hint' }, hint) : null)
}

/** What a pairing code is, said under where one is pasted. */
const CODE_ABOUT = () => t('Starts with hmz-pair: and is made on the other machine.')

/** What tells a daemon's entry from another of its name: its routes and its STUN and TURN servers. */
function keyOf(one) {
  return JSON.stringify([one.routes, one.ice || []])
}

/** Where a daemon's STUN and TURN servers are written, a line each. */
function iceBox(id, servers) {
  return h('textarea', { id, rows: '3', spellcheck: 'false', 'data-hmz': 'ice-lines', placeholder: 'stun:stun.example:3478\nturn:turn.example:3478 user password' }, shownIce(servers))
}

/** STUN and TURN servers as they are written, a line each: the URLs, then the username, a credential masked. */
function shownIce(servers) {
  return servers.map((one) => [].concat(one.urls).join(',') + (one.username ? ` ${one.username}${one.credential ? ` ${MASKED}` : ''}` : '')).join('\n')
}

/**
 * The STUN and TURN servers written, a line each: the URL, or several with commas between, then
 * the username and the credential. A credential left as it was shown is the one `was` kept: of
 * the server of that username written with these URLs, or with one of them where they were
 * edited, or else on this line -- and where there is none, it is asked for again, never dropped.
 */
function readIce(text, was = []) {
  const urlsOf = (one) => [].concat(one.urls)
  return text
    .split('\n')
    .map((line) => line.trim().split(/\s+/))
    .filter((words) => words[0])
    .map(([urls, username, credential], at) => {
      const each = urls.split(',').filter(Boolean)
      for (const url of each) if (!ICE.test(url)) throw new Error(t('{url} is not a STUN or TURN server: write one as stun:host:port or turn:host:port.', { url }))
      // What was kept for a server of this username, the only ones a mask was shown for -- and a
      // credential kept with no username, which no line shows, stays with the URLs it was under.
      const mine = (one) => one && one.credential && (one.username || '') === (username || '')
      const same = was.find((one) => mine(one) && urlsOf(one).join(',') === urls)
      let kept = credential
      if (credential === MASKED) {
        const from = same ?? was.find((one) => mine(one) && urlsOf(one).some((url) => each.includes(url))) ?? (mine(was[at]) ? was[at] : null)
        if (!from) throw new Error(t('Write the credential of {urls} again: none is kept for it.', { urls }))
        kept = from.credential
      } else if (!username && same) kept = same.credential
      return { urls: each.length === 1 ? each[0] : each, ...(username ? { username } : {}), ...(kept ? { credential: kept } : {}) }
    })
}

/** Where a daemon is reached, as its routes say, the first first. */
function reached(one) {
  return one.routes.join(', ')
}

/** Routes, one a row, in the order tried: one more added, any taken away or moved up. */
function routeList(values, id) {
  const rows = h('div', { class: 'list-rows', id, 'data-hmz': 'route-editor' })
  const add = h('button', { class: 'btn small quiet', type: 'button' }, icon('plus'), t('Add'))
  const row = (value) => {
    const line = h(
      'div',
      { class: 'list-row' },
      h('input', { type: 'text', value, placeholder: 'tcp://host:port', 'aria-label': t('Route'), class: 'route', spellcheck: 'false' }),
      iconButton('up', t('Move up'), { class: 'small', onclick: () => line.previousElementSibling && line.previousElementSibling.before(line) }),
      iconButton('close', t('Remove'), { class: 'small', onclick: () => line.remove() }),
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
  const add = h('button', { class: 'btn small quiet', type: 'button' }, icon('plus'), t('Add'))
  const row = (key, value) => {
    const line = h(
      'div',
      { class: 'list-row' },
      h('input', { type: 'text', value: key, placeholder: t('Name'), 'aria-label': t('Option'), class: 'pair-key' }),
      h('input', { type: 'text', value, placeholder: t('Value'), 'aria-label': t('Value'), class: 'pair-value' }),
      iconButton('close', t('Remove'), { class: 'small', onclick: () => line.remove() }),
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
