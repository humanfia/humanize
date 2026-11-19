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

test('the DTLS certificate is made once and kept until it expires; the ICE servers are kept', async () => {
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
  assert.deepEqual(await store.iceServers(), [])
  await store.setIceServers([{ urls: 'stun:stun.example' }])
  assert.deepEqual(await store.iceServers(), [{ urls: 'stun:stun.example' }])
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
