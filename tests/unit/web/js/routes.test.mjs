import assert from 'node:assert/strict'
import { test } from 'node:test'

import { race, routeKind, trusted } from '../../../../src/hmz/web/static/rpc/index.js'
import { sleep } from './helpers.mjs'

test('each kind of route is read, and what is not a route is not', () => {
  const kinds = {
    'unix:': 'unix',
    'unix:/run/user/1000/hmz/daemon.sock': 'unix',
    'stdio:local': 'stdio:local',
    'stdio:ssh://box': 'stdio:ssh',
    'stdio:ssh://me@box.example:2222?identity=~%2F.ssh%2Fid&jump=gate&option=ConnectTimeout=5': 'stdio:ssh',
    'stdio:wsl': 'stdio:wsl',
    'stdio:wsl:Ubuntu-24.04': 'stdio:wsl',
    'tcp://10.0.0.2:7700': 'tcp',
    'tcp://[::1]:7700': 'tcp',
    'ws://box:7700': 'ws',
    'wss://box.example/hmz': 'ws',
    'easytier:home-net': 'easytier',
    'relay:wss://relay.example/r': 'relay',
    'webrtc:wss://relay.example': 'webrtc',
  }
  for (const [route, kind] of Object.entries(kinds)) assert.equal(routeKind(route), kind, route)
  for (const route of ['', 'unix', 'stdio:ssh:box', 'stdio:ssh://box?port=2', 'tcp://box', 'http://box', 'easytier:-x', 'webrtc:http://x', 'ws://box?q=1'])
    assert.equal(routeKind(route), null, route)
})

test('a port outside 1 to 65535 or an empty host is not a route', () => {
  for (const route of [
    'tcp://h:',
    'tcp://h:0',
    'tcp://h:65536',
    'tcp://h:99999',
    'tcp://:1',
    'ws://',
    'ws://h:/x',
    'ws://h:99999/x',
    'wss://:443/x',
    'stdio:ssh://',
    'stdio:ssh://h:0',
    'stdio:ssh://me@:22',
    'relay:ws://:0',
    'webrtc:wss://h:70000',
  ])
    assert.equal(routeKind(route), null, route)
  for (const [route, kind] of Object.entries({ 'tcp://h:1': 'tcp', 'tcp://h:65535': 'tcp', 'tcp://h:065535': 'tcp', 'ws://h:65535/x': 'ws', 'stdio:ssh://h:22': 'stdio:ssh' }))
    assert.equal(routeKind(route), kind, route)
})

test('unix and stdio carriers are trusted, every other is not', () => {
  assert.ok(trusted('unix:') && trusted('stdio:local') && trusted('stdio:ssh://box') && trusted('stdio:wsl'))
  assert.ok(!trusted('tcp://box:1') && !trusted('wss://box') && !trusted('easytier:x') && !trusted('relay:ws://r') && !trusted('webrtc:ws://r'))
})

test('routes start 250 ms apart, the first to succeed wins and the others are given up', async () => {
  const started = []
  const aborted = []
  const discarded = []
  const t0 = Date.now()
  const won = await race(
    ['slow', 'fast', 'never'],
    (route, signal) => {
      started.push([route, Date.now() - t0])
      signal.addEventListener('abort', () => aborted.push(route))
      if (route === 'fast') return sleep(20).then(() => route)
      return new Promise(() => {})
    },
    (late) => discarded.push(late),
  )
  assert.equal(won, 'fast')
  assert.deepEqual(started.map(([route]) => route), ['slow', 'fast'])
  assert.ok(started[1][1] >= 240, `fast started at ${started[1][1]} ms`)
  assert.deepEqual(aborted, ['slow'])
  await sleep(300)
  assert.equal(started.length, 2)
})

test('a route starts at once where every route before it failed; all failing is the last failure', async () => {
  const started = []
  const t0 = Date.now()
  await assert.rejects(
    race(
      ['a', 'b', 'c'],
      async (route) => {
        started.push([route, Date.now() - t0])
        await sleep(route === 'c' ? 30 : 5)
        throw new Error(`${route} failed`)
      },
      () => {},
    ),
    /c failed/,
  )
  assert.ok(started[1][1] < 100, `b started at ${started[1][1]} ms`)
  assert.ok(started[2][1] < 100, `c started at ${started[2][1]} ms`)
  // The last to fail, not the last in order.
  await assert.rejects(
    race(
      ['a', 'b'],
      async (route) => {
        await sleep(route === 'a' ? 400 : 5)
        throw new Error(`${route} failed`)
      },
      () => {},
    ),
    /a failed/,
  )
})

test('a success after the race was won is closed', async () => {
  const discarded = []
  const won = await race(
    ['a', 'b'],
    async (route) => {
      await sleep(route === 'a' ? 300 : 10)
      return route
    },
    (late) => discarded.push(late),
  )
  assert.equal(won, 'b')
  await sleep(100)
  assert.deepEqual(discarded, ['a'])
})
