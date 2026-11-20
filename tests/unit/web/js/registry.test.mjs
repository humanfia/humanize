import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

import { claim, local, parsePairing, reach, registry, RpcError, WRITES } from '../../../../src/hmz/web/static/rpc/index.js'
import { toBase64url } from '../../../../src/hmz/web/static/rpc/pipe.js'
import { daemon, fakeIndexedDB, provider } from './helpers.mjs'

const ID = 'a'.repeat(52)

/** A pairing code as a daemon makes one. */
const code = (fields = {}) =>
  `hmz-pair:${toBase64url(new TextEncoder().encode(JSON.stringify({ v: 1, id: ID, routes: ['tcp://box:7700'], token: 't'.repeat(43), expires: 2e9, ...fields })))}`

test('Local is unix: in hmz web, stdio:local on macOS and stdio:wsl on Windows in the desktop', () => {
  assert.deepEqual(local('web'), { name: 'local', id: '', routes: ['unix:'] })
  assert.deepEqual(local('macos'), { name: 'local', id: '', routes: ['stdio:local'] })
  assert.deepEqual(local('windows'), { name: 'local', id: '', routes: ['stdio:wsl'] })
  // Node is no web view of the desktop application.
  assert.deepEqual(local(), local('web'))
})

test('the registry adds, lists, updates, renames and removes remote daemons', async () => {
  const store = registry(fakeIndexedDB())
  assert.deepEqual(await store.list(), [])
  await store.add({ name: 'box', id: ID, routes: ['tcp://box:1'] })
  await store.add({ name: 'alpha', id: '', routes: ['stdio:ssh://alpha'] })
  assert.deepEqual(await store.list(), [
    { name: 'alpha', id: '', routes: ['stdio:ssh://alpha'] },
    { name: 'box', id: ID, routes: ['tcp://box:1'] },
  ])
  await assert.rejects(store.add({ name: 'box', id: '', routes: [] }), /There is already a daemon box\./)
  await store.update('alpha', { id: ID, routes: ['stdio:ssh://alpha', 'tcp://alpha:1'] })
  await store.update('alpha', { name: 'beta' })
  await assert.rejects(store.update('beta', { name: 'box' }), /There is already a daemon box\./)
  await assert.rejects(store.update('nobody', { id: '' }), /There is no daemon nobody\./)
  assert.deepEqual(await store.list(), [
    { name: 'beta', id: ID, routes: ['stdio:ssh://alpha', 'tcp://alpha:1'] },
    { name: 'box', id: ID, routes: ['tcp://box:1'] },
  ])
  await store.remove('box')
  assert.deepEqual((await store.list()).map((one) => one.name), ['beta'])
})

test('a remote daemon is not named local, nor anything not a name, and its routes are routes', async () => {
  const store = registry(fakeIndexedDB())
  for (const name of ['local', '-x', 'a b', ''])
    await assert.rejects(store.add({ name, id: '', routes: [] }))
  await assert.rejects(store.add({ name: 'ok', id: '', routes: ['nowhere'] }), /nowhere is not a route\./)
  await assert.rejects(store.update('ok', { name: 'local' }))
})

test('a daemon keeps its own STUN and TURN servers, and only ones that are', async () => {
  const store = registry(fakeIndexedDB())
  const turn = { urls: ['turn:turn.example:3478', 'turns:turn.example:5349'], username: 'ann', credential: 'secret' }
  await store.add({ name: 'box', id: ID, routes: ['webrtc:wss://relay.example/r'], ice: [{ urls: 'stun:stun.example' }] })
  await store.add({ name: 'plain', id: ID, routes: ['tcp://plain:1'], ice: [] })
  assert.deepEqual(await store.list(), [
    { name: 'box', id: ID, routes: ['webrtc:wss://relay.example/r'], ice: [{ urls: 'stun:stun.example' }] },
    // One with none keeps no list.
    { name: 'plain', id: ID, routes: ['tcp://plain:1'] },
  ])
  await store.update('plain', { ice: [turn] })
  // Whatever else changes, they stay; given none, they go.
  await store.update('box', { routes: ['tcp://box:1'] })
  await store.update('box', { name: 'crate' })
  assert.deepEqual((await store.list()).map((one) => one.ice), [[{ urls: 'stun:stun.example' }], [turn]])
  await store.update('crate', { ice: [] })
  assert.deepEqual((await store.list())[0], { name: 'crate', id: ID, routes: ['tcp://box:1'] })

  for (const [bad, why] of [
    ['stun:stun.example', /are a list/],
    [[{}], /needs its URL/],
    [[{ urls: [] }], /needs its URL/],
    [[null], /needs its URL/],
    [[{ urls: 'https://stun.example' }], /https:\/\/stun\.example is not a STUN or TURN server\./],
    [[{ urls: ['stun:ok.example', 'nope'] }], /nope is not a STUN or TURN server\./],
    [[{ urls: 'turn:turn.example', username: 7 }], /username is text/],
    [[{ urls: 'turn:turn.example', credential: {} }], /credential is text/],
  ]) {
    await assert.rejects(store.add({ name: 'other', id: '', routes: [], ice: bad }), why)
    await assert.rejects(store.update('crate', { ice: bad }), why)
  }
  assert.deepEqual((await store.list()).map((one) => one.name), ['crate', 'plain'])
})

/** A base as version 1 of the page left it: the daemons, and one list of servers for them all. */
function versionOne(indexedDB, daemons, keys) {
  return new Promise((resolve) => {
    const asked = indexedDB.open('hmz-daemons', 1)
    asked.onupgradeneeded = () => {
      asked.result.createObjectStore('daemons', { keyPath: 'name' })
      asked.result.createObjectStore('keys')
      for (const one of daemons) asked.transaction.objectStore('daemons').put(one)
      for (const [key, value] of Object.entries(keys)) asked.transaction.objectStore('keys').put(value, key)
    }
    asked.onsuccess = () => resolve(asked.result)
  })
}

test('the servers version 1 kept for every daemon move onto each daemon with a webrtc route', async () => {
  const servers = [{ urls: 'stun:stun.example' }, { urls: 'turn:turn.example', username: 'ann', credential: 'secret' }]
  const cert = { expires: Date.now() + 1e9 }
  const indexedDB = fakeIndexedDB()
  const base = await versionOne(
    indexedDB,
    [
      { name: 'relayed', id: ID, routes: ['tcp://relayed:1', 'webrtc:wss://relay.example/r'] },
      { name: 'ssh', id: '', routes: ['stdio:ssh://ssh'] },
      { name: 'paired', id: ID, routes: ['tcp://paired:1'] },
    ],
    { ice: servers, certificate: cert },
  )
  const store = registry(indexedDB)
  assert.deepEqual(await store.list(), [
    { name: 'paired', id: ID, routes: ['tcp://paired:1'] },
    { name: 'relayed', id: ID, routes: ['tcp://relayed:1', 'webrtc:wss://relay.example/r'], ice: servers },
    { name: 'ssh', id: '', routes: ['stdio:ssh://ssh'] },
  ])
  // The one list is gone; the certificate beside it is the one kept.
  assert.deepEqual([...base.stores.get('keys').data.keys()], ['certificate'])
  assert.equal(base.version, 2)
  assert.deepEqual(await store.certificate(async () => assert.fail('made anew')), cert)

  // Opened again, nothing is moved a second time; and a base that kept no list keeps none.
  await store.update('relayed', { ice: [] })
  assert.equal((await registry(indexedDB).list())[1].ice, undefined)
  const none = fakeIndexedDB()
  await versionOne(none, [{ name: 'relayed', id: ID, routes: ['webrtc:wss://relay.example/r'] }], {})
  assert.deepEqual(await registry(none).list(), [{ name: 'relayed', id: ID, routes: ['webrtc:wss://relay.example/r'] }])
  const empty = fakeIndexedDB()
  await versionOne(empty, [{ name: 'relayed', id: ID, routes: ['webrtc:wss://relay.example/r'] }], { ice: [] })
  assert.deepEqual(await registry(empty).list(), [{ name: 'relayed', id: ID, routes: ['webrtc:wss://relay.example/r'] }])
  assert.deepEqual([...(await versionOne(empty, [], {})).stores.get('keys').data.keys()], [])
})

test('a database another tab holds on an earlier version is said, not waited for, and is let go of for a later one', async () => {
  const real = fakeIndexedDB()
  /** The requests to open it, held until `answer` lets one through; the bases opened, and how many were closed. */
  const requests = []
  const bases = []
  let closed = 0
  const held = {
    open(name, version) {
      const asked = /** @type {any} */ ({})
      asked.answer = () =>
        new Promise((done) => {
          const inner = real.open(name, version)
          inner.onupgradeneeded = (event) => {
            asked.result = inner.result
            asked.transaction = inner.transaction
            asked.onupgradeneeded?.(event)
          }
          inner.onsuccess = () => {
            const base = inner.result
            asked.result = { transaction: (...given) => base.transaction(...given), close: () => closed++, onversionchange: null }
            bases.push(asked.result)
            asked.onsuccess?.()
            done()
          }
        })
      requests.push(asked)
      return asked
    },
  }
  const store = registry(held)
  // Blocked: whoever asked is told why, at once.
  const first = store.list()
  requests[0].onblocked()
  await assert.rejects(first, /Another tab of this page is open on an earlier version: close or reload it\./)
  // The next use asks again; the request given up on, opened once the other tab went, is closed.
  const second = store.list()
  assert.equal(requests.length, 2)
  await requests[0].answer()
  assert.equal(closed, 1)
  await requests[1].answer()
  assert.deepEqual(await second, [])
  await store.add({ name: 'box', id: ID, routes: ['tcp://box:1'] })
  assert.equal(requests.length, 2)
  // A later version asks for it from another tab: it is let go of, and opened again by the next use.
  bases[1].onversionchange()
  assert.equal(closed, 2)
  const third = store.list()
  assert.equal(requests.length, 3)
  await requests[2].answer()
  assert.deepEqual((await third).map((one) => one.name), ['box'])
})

test('the DTLS certificate is made once and kept until it expires', async () => {
  const store = registry(fakeIndexedDB())
  let made = 0
  const make = async () => ({ made: ++made, expires: made === 1 ? Date.now() - 1 : Date.now() + 1e9 })
  assert.equal((await store.certificate(make)).made, 1)
  // The first expired: a new one is made, then kept.
  assert.equal((await store.certificate(make)).made, 2)
  assert.equal((await store.certificate(make)).made, 2)
  // Asked by many at once, one is made.
  const fresh = registry(fakeIndexedDB())
  let count = 0
  const once = async () => ({ made: ++count, expires: Date.now() + 1e9 })
  const all = await Promise.all([fresh.certificate(once), fresh.certificate(once), fresh.certificate(once)])
  assert.deepEqual(all.map((one) => one.made), [1, 1, 1])
})

test('a pairing code is read; anything else is not', () => {
  assert.deepEqual(parsePairing(code()), { v: 1, id: ID, routes: ['tcp://box:7700'], token: 't'.repeat(43), expires: 2e9 })
  for (const bad of ['', 'hmz-pair:', 'hmz-pair:!!!', code({ v: 2 }), code({ extra: 1 }), code({ id: 'short' }), code({ routes: ['nowhere'] }), code().replace('hmz-pair:', 'hmz:')])
    assert.throws(() => parsePairing(bad), /That is not a pairing code\./, bad)
})

test('a claimed code keeps the daemon; a refused claim keeps nothing', async () => {
  const claims = []
  const served = daemon({
    methods: {
      'pair.claim': (params) => {
        claims.push(params)
        if (params.token !== 't'.repeat(43)) throw new RpcError(403, 'That pairing code is not valid: ask for a new one.')
        return { daemon_id: ID, device: params.name }
      },
    },
  })
  const store = registry(fakeIndexedDB())
  const entry = await claim(store, { name: 'box', code: code(), device: 'browser' }, [provider(served)])
  assert.deepEqual(entry, { name: 'box', id: ID, routes: ['tcp://box:7700'] })
  assert.deepEqual(claims, [{ token: 't'.repeat(43), name: 'browser' }])
  assert.deepEqual(await store.list(), [entry])
  assert.equal(served.sessions[0].peer.open, false)

  await assert.rejects(claim(store, { name: 'other', code: code({ token: 'x' }), device: 'browser' }, [provider(served)]), /not valid/)
  await assert.rejects(claim(store, { name: 'box', code: code(), device: 'browser' }, [provider(served)]), /already/)
  assert.deepEqual((await store.list()).map((one) => one.name), ['box'])
})

test('a daemon is reached with its own STUN and TURN servers, claimed with them, and kept with them', async () => {
  const served = daemon({ methods: { 'pair.claim': (params) => ({ daemon_id: ID, device: params.name }) } })
  const store = registry(fakeIndexedDB())
  const ice = [{ urls: 'turn:turn.example', username: 'ann', credential: 'secret' }]
  const given = []
  const asked = { name: 'box', code: code({ routes: ['webrtc:wss://relay.example/r'] }), device: 'browser', ice }
  const entry = await claim(store, asked, [provider(served, [], given)])
  // Before it is kept: a code whose one route is WebRTC may need them to be claimed at all.
  assert.deepEqual(given, [ice])
  assert.deepEqual(entry, { name: 'box', id: ID, routes: ['webrtc:wss://relay.example/r'], ice })
  assert.deepEqual(await store.list(), [entry])
  await assert.rejects(claim(store, { ...asked, name: 'bad', ice: [{ urls: 'nope' }] }, [provider(served, [], given)]), /nope is not a STUN or TURN server\./)
  assert.equal(given.length, 1)

  // Each daemon with its own, and one with none with none.
  const other = { name: 'other', id: ID, routes: ['webrtc:wss://relay.example/o'], ice: [{ urls: 'stun:stun.example' }] }
  for (const one of [entry, other, { name: 'plain', id: ID, routes: ['tcp://plain:1'] }]) (await reach(one, [provider(served, [], given)])).peer.close('Done.')
  assert.deepEqual(given.slice(1), [ice, [{ urls: 'stun:stun.example' }], []])
})

test('a P2P daemon is claimed over its easytier route here and kept with the id its code gives', async () => {
  const served = daemon({ methods: { 'pair.claim': (params) => ({ daemon_id: ID, device: params.name }) } })
  const store = registry(fakeIndexedDB())
  const opened = []
  const asked = { name: 'edge', code: code({ routes: ['easytier:home', 'tcp://box:7700'] }), device: 'browser', first: 'easytier:edge' }
  const entry = await claim(store, asked, [provider(served, opened)])
  // The code's own easytier route names that machine's entry, not this one's.
  assert.deepEqual(entry, { name: 'edge', id: ID, routes: ['easytier:edge', 'tcp://box:7700'] })
  assert.equal(opened[0], 'easytier:edge')
  assert.deepEqual(await store.list(), [entry])
  // Pinned, its untrusted route is not refused for want of an id.
  const session = await reach({ ...entry, routes: ['easytier:edge'] }, [provider(served)])
  assert.equal(session.route, 'easytier:edge')
  session.peer.close('Done.')
})

test('the writes are the methods of openrpc.json taking idem', () => {
  const document = JSON.parse(readFileSync(new URL('../../../../protocol/openrpc.json', import.meta.url), 'utf8'))
  const writes = document.methods.filter((method) => method.params.some((param) => param.name === 'idem')).map((method) => method.name)
  assert.deepEqual([...WRITES].sort(), writes.sort())
})
