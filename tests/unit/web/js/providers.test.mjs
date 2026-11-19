import assert from 'node:assert/strict'
import { test } from 'node:test'

import { bridge, connect, NotPinned, tauri, webrtc } from '../../../../src/hmz/web/static/rpc/index.js'
import { fingerprint, publicKeyInfo, signed } from '../../../../src/hmz/web/static/rpc/webrtc.js'
import { toBase32, toBase64, toBase64url } from '../../../../src/hmz/web/static/rpc/pipe.js'
import { daemon, duplex, sleep, until } from './helpers.mjs'

/** A WebSocket the test drives: what the page sends is in `sent`, `onsent` told each. */
class FakeSocket {
  static made = []
  constructor(url) {
    this.url = url
    this.sent = []
    this.readyState = 0
    this.closedWith = null
    FakeSocket.made.push(this)
    setTimeout(() => {
      this.readyState = 1
      this.onopen?.()
    })
  }
  send(data) {
    this.sent.push(data)
    this.onsent?.(data)
  }
  close(code = 1000, reason = '') {
    if (this.readyState === 3) return
    this.readyState = 3
    this.closedWith = code
    setTimeout(() => this.onclose?.({ code, reason }))
  }
  /** The server sends `data`. */
  says(data) {
    this.onmessage?.({ data })
  }
}

const noState = () => {}

test('the bridge reaches unix: over /rpc, and is up once the WebSocket opens', async () => {
  FakeSocket.made = []
  const provider = bridge({ base: 'ws://127.0.0.1:9', WebSocket: FakeSocket })
  assert.ok(provider.opens('unix:') && provider.opens('stdio:ssh://box') && provider.opens('wss://box') && provider.opens('easytier:net') && provider.opens('relay:ws://r'))
  assert.ok(!provider.opens('webrtc:ws://r') && !provider.opens('stdio:local') && !provider.opens('unix:/tmp/s'))
  const pipe = await provider.open('unix:', '', { state: noState, signal: new AbortController().signal })
  const socket = FakeSocket.made[0]
  assert.equal(socket.url, 'ws://127.0.0.1:9/rpc')
  assert.equal(socket.binaryType, 'arraybuffer')
  const got = []
  pipe.listen((bytes) => got.push(...bytes), () => {})
  socket.says(Uint8Array.of(1, 2, 3).buffer)
  pipe.send(Uint8Array.of(9))
  assert.deepEqual(got, [1, 2, 3])
  assert.deepEqual([...socket.sent[0]], [9])
  // Text from the server ends the pipe.
  let why = null
  pipe.listen(() => {}, (said) => (why = said))
  socket.says('{"state":"up"}')
  assert.equal(why, 'The server sent text.')
})

test('the bridge dials other routes, telling their state until up', async () => {
  FakeSocket.made = []
  const provider = bridge({ base: 'ws://127.0.0.1:9', WebSocket: FakeSocket })
  const states = []
  const opening = provider.open('stdio:ssh://me@box?jump=gate', 'x'.repeat(52), {
    state: (state, detail) => states.push([state, detail]),
    signal: new AbortController().signal,
  })
  await sleep(1)
  const socket = FakeSocket.made[0]
  assert.equal(socket.url, `ws://127.0.0.1:9/dial?route=stdio%3Assh%3A%2F%2Fme%40box%3Fjump%3Dgate&id=${'x'.repeat(52)}`)
  socket.says('{"state":"connecting","detail":"ssh me@box"}')
  socket.says('{"state":"installing","detail":"uv tool install hmz"}')
  socket.says('{"state":"up","detail":""}')
  const pipe = await opening
  assert.deepEqual(states, [
    ['connecting', 'ssh me@box'],
    ['installing', 'uv tool install hmz'],
  ])
  const got = []
  pipe.listen((bytes) => got.push(...bytes), () => {})
  socket.says(Uint8Array.of(7).buffer)
  assert.deepEqual(got, [7])
})

test('the bridge fails a route with what was said last, or the reason it closed with', async () => {
  FakeSocket.made = []
  const provider = bridge({ base: 'ws://127.0.0.1:9', WebSocket: FakeSocket })
  const failing = provider.open('tcp://box:1', 'x', { state: noState, signal: new AbortController().signal })
  await sleep(1)
  FakeSocket.made[0].says('{"state":"failed","detail":"Connection refused."}')
  FakeSocket.made[0].close(1011)
  await assert.rejects(failing, /Connection refused\./)

  const local = provider.open('unix:', '', { state: noState, signal: new AbortController().signal })
  FakeSocket.made[1].onopen = null
  FakeSocket.made[1].close(1011, 'The daemon cannot be reached: no socket')
  await assert.rejects(local, /The daemon cannot be reached: no socket/)

  const abort = new AbortController()
  const given = provider.open('tcp://box:1', 'x', { state: noState, signal: abort.signal })
  abort.abort()
  await assert.rejects(given, /Given up/)
  assert.equal(FakeSocket.made[2].readyState, 3)
})

/** Tauri's internals as a page sees them, with an app that opens pipes to `served`. */
function fakeTauri(served) {
  const callbacks = new Map()
  const listeners = new Map()
  const app = new Map()
  const invoked = []
  let next = 0
  const emit = (event, payload) => listeners.get(event)?.({ event, id: 1, payload })
  return {
    invoked,
    emit,
    internals: {
      transformCallback: (fn) => {
        callbacks.set(++next, fn)
        return next
      },
      async invoke(command, args) {
        invoked.push([command, args])
        await sleep(1)
        if (command === 'plugin:event|listen') {
          listeners.set(args.event, callbacks.get(args.handler))
          return args.handler
        }
        if (command === 'pipe_open') {
          const pipe = `p${app.size + 1}`
          const [mine, theirs] = duplex()
          served.serve(theirs)
          app.set(pipe, mine)
          mine.listen(
            (bytes) => emit('pipe_data', { pipe, data: toBase64(bytes) }),
            (why) => emit('pipe_closed', { pipe, why }),
          )
          // The app tells the state before it answers, as it may.
          emit('pipe_state', { pipe, state: 'connecting', detail: 'dialing' })
          setTimeout(() => emit('pipe_state', { pipe, state: 'up', detail: '' }), 5)
          return { pipe }
        }
        if (command === 'pipe_send') return app.get(args.pipe).send(Uint8Array.from(atob(args.data), (c) => c.charCodeAt(0)))
        if (command === 'pipe_close') return app.get(args.pipe).close('closed by the page')
        throw new Error(`no command ${command}`)
      },
    },
  }
}

test('the desktop app pipes carry a session through pipe_open, pipe_send and its events', async () => {
  const served = daemon()
  const fake = fakeTauri(served)
  const provider = tauri(fake.internals)
  assert.ok(provider.opens('stdio:local') && provider.opens('stdio:wsl:Ubuntu') && provider.opens('tcp://h:1') && !provider.opens('unix:') && !provider.opens('webrtc:ws://r'))
  const states = []
  const client = connect({ name: 'local', id: '', routes: ['stdio:local'] }, [provider], { client: { name: '', kind: 'desktop' } })
  client.watch((state) => states.push(state.state))
  assert.deepEqual(await client.call('echo', { big: 'x'.repeat(100000) }), { big: 'x'.repeat(100000) })
  assert.deepEqual(states.slice(0, 2), ['connecting', 'up'])
  assert.deepEqual(fake.invoked.filter(([command]) => command === 'pipe_open'), [['pipe_open', { route: 'stdio:local', id: '' }]])
  assert.deepEqual(
    fake.invoked.filter(([command]) => command === 'plugin:event|listen').map(([, args]) => args.event),
    ['pipe_state', 'pipe_data', 'pipe_closed'],
  )
  client.close()
  await until(() => fake.invoked.some(([command]) => command === 'pipe_close'))
})

test('a route the desktop app refuses to open leaves the daemon failed with the sentence the app said', async () => {
  // A command of Tauri that answers `Err(String)` rejects with the bare string, not with an Error.
  const internals = {
    transformCallback: () => 1,
    invoke: async (command, args) => {
      if (command === 'pipe_open') throw `${args.route} cannot be reached from here.`
      return 1
    },
  }
  const client = connect({ name: 'box', id: '', routes: ['stdio:wsl'] }, [tauri(internals)], { client: { name: '', kind: 'desktop' } })
  try {
    await assert.rejects(client.call('echo', {}), { code: 503, message: 'stdio:wsl cannot be reached from here.' })
    assert.deepEqual(client.state, { state: 'failed', detail: 'stdio:wsl cannot be reached from here.' })
  } finally {
    client.close()
  }
})

/** A DER element. */
function tlv(tag, ...parts) {
  const body = parts.flatMap((part) => [...part])
  const length = body.length < 128 ? [body.length] : body.length < 256 ? [0x81, body.length] : [0x82, body.length >> 8, body.length & 255]
  return Uint8Array.from([tag, ...length, ...body])
}

/** A certificate shaped as X.509 around `spki`, enough for the page to find its key. */
function certificate(spki) {
  const seq = (...parts) => tlv(0x30, ...parts)
  const tbs = seq(tlv(0xa0, tlv(2, [2])), tlv(2, [1, 2, 3]), seq(tlv(6, [1])), seq(), seq(), seq(), spki)
  return seq(tbs, seq(tlv(6, [1])), tlv(3, [0]))
}

/** A real certificate of the daemon, made by `cryptography`, and its daemon id. */
const REAL =
  'MIIBIDCByKADAgECAhBZ83PHM2EJQa5A7AisdWHlMAoGCCqGSM49BAMCMBIxEDAOBgNVBAMMB2hteiBib3gwIBcNMjYwMTAxMDAwMDAwWhgPOTk5OTEyMzEyMzU5NTlaMBIxEDAOBgNVBAMMB2hteiBib3gwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNCAARdtldmyy4bBf4xXKAtb0tpu2xOz18a+Lvr1ei+CWm3kOuAmolD9vw146CoORILupANSOZBzGUE/F8wrsBUBts/MAoGCCqGSM49BAMCA0cAMEQCIAfDPoeR5TqmqhHh2UVxJdfCSlpqSH8ZaKOVRFm6q3IIAiBczn8PFbKVJmGI/obyXkJhsgbxeKoYJ/GytFn10rat2A=='
const REAL_ID = 'awqxgmnelz63pkjgkqzhbbiichyjtnnlv5rqlim4vxr3aeeanlba'

test('the daemon id of a real certificate is the base32 SHA-256 of its SubjectPublicKeyInfo', async () => {
  const der = Uint8Array.from(atob(REAL), (c) => c.charCodeAt(0))
  const spki = publicKeyInfo(der)
  assert.equal(toBase32(new Uint8Array(await crypto.subtle.digest('SHA-256', spki))), REAL_ID)
  assert.equal(REAL_ID.length, 52)
})

/** A `sha-256` value: 32 bytes of `byte` in hexadecimal. */
const hex = (byte) => Array(32).fill(byte).join(':')
const AA = hex('AA')
const DD = hex('DD')
const OFFER = `v=0\r\no=- 1 2 IN IP4 0.0.0.0\r\na=fingerprint:sha-256 ${AA}\r\nm=application 9 UDP/DTLS/SCTP webrtc-datachannel\r\n`
const ANSWER = `v=0\r\no=- 3 4 IN IP4 0.0.0.0\r\na=fingerprint:sha-256 ${DD}\r\n`

/** A daemon's key, its certificate and id, and a signer of the fingerprints given. */
async function daemonKey() {
  const keys = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify'])
  const spki = new Uint8Array(await crypto.subtle.exportKey('spki', keys.publicKey))
  const id = toBase32(new Uint8Array(await crypto.subtle.digest('SHA-256', spki)))
  const sign = async (offer, answer) =>
    new Uint8Array(await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, keys.privateKey, new TextEncoder().encode(`hmz-webrtc/1\n${offer}\n${answer}`)))
  return { id, der: certificate(spki), sign }
}

test('a description says exactly one sha-256 value, of 32 bytes, read as written', () => {
  const lower = hex('ab')
  // Spaces or a tab after the name, read in any case, repeated, beside other algorithms.
  assert.equal(fingerprint(`a=fingerprint:SHA-256\t${lower}\r\nm=x\r\na=fingerprint:sha-256  ${lower} \r\na=fingerprint:sha-1 00:11\r\n`), lower)
  for (const sdp of ['v=0\r\n', `a=fingerprint:sha-1 ${AA}\r\n`, `a=fingerprint:sha-256 ${AA}\r\na=fingerprint:sha-256 ${DD}\r\n`, `a=fingerprint:sha-256 ${AA}\r\na=fingerprint:sha-256 ${AA.toLowerCase()}\r\n`])
    assert.throws(() => fingerprint(sdp), { message: 'A description must say exactly one sha-256 fingerprint.' })
  for (const value of ['AA:BB:CC', `${AA}:AA`, AA.replace('AA', 'GG'), AA.replaceAll(':', '')])
    assert.throws(() => fingerprint(`a=fingerprint:sha-256 ${value}\r\n`), { message: `${value} is not a sha-256 fingerprint.` })
})

test('an answer is the pinned daemon\'s only where its id and its signature over both fingerprints hold', async () => {
  assert.equal(fingerprint(OFFER), AA)
  const { id, der, sign } = await daemonKey()
  const sig = await sign(AA, DD)
  assert.equal(sig.length, 64)
  assert.ok(await signed(crypto.subtle, id, der, sig, OFFER, ANSWER))
  assert.ok(!(await signed(crypto.subtle, 'b'.repeat(52), der, sig, OFFER, ANSWER)))
  assert.ok(!(await signed(crypto.subtle, id, der, await sign(hex('00'), DD), OFFER, ANSWER)))
  assert.ok(!(await signed(crypto.subtle, id, der, sig, OFFER, ANSWER.replace('DD:', '11:'))))
})

/** RTCPeerConnection as far as the provider uses it; its data channel opens once answered. */
class FakeConnection {
  static last = null
  constructor(config) {
    this.config = config
    this.added = []
    this.closed = false
    FakeConnection.last = this
  }
  createDataChannel(label, options) {
    this.channel = { label, options, sent: [], bufferedAmount: 0, send: (bytes) => this.channel.sent.push(bytes) }
    return this.channel
  }
  async createOffer() {
    return { type: 'offer', sdp: OFFER }
  }
  async setLocalDescription(description) {
    this.localDescription = description
    setTimeout(() => this.onicecandidate?.({ candidate: { candidate: 'candidate:1 1 udp 1 10.0.0.1 9 typ host', sdpMid: '0', sdpMLineIndex: 0 } }))
  }
  async setRemoteDescription(description) {
    this.remoteDescription = description
    setTimeout(() => this.channel.onopen?.())
  }
  async addIceCandidate(candidate) {
    this.added.push(candidate)
  }
  close() {
    this.closed = true
  }
}

/** A relay that joins at once and answers the offer as `answer` makes it. */
function relayAnswering(answer) {
  return class extends FakeSocket {
    constructor(url) {
      super(url)
      this.onsent = async (text) => {
        const message = JSON.parse(text)
        if (message.t === 'join') this.says(JSON.stringify({ t: 'joined' }))
        if (message.t === 'signal' && message.data.type === 'offer') {
          // A candidate may come before the answer.
          this.says(JSON.stringify({ t: 'signal', data: { type: 'candidate', candidate: 'candidate:2', sdpMid: '0', sdpMLineIndex: 0 } }))
          this.says(JSON.stringify({ t: 'signal', data: await answer(message.data.sdp) }))
        }
      }
    }
  }
}

test('webrtc joins the relay, offers, checks the answer, and carries bytes in chunks over the channel', async () => {
  const { id, der, sign } = await daemonKey()
  FakeSocket.made = []
  const cert = { expires: Date.now() + 1e9 }
  const provider = webrtc({
    certificate: async () => cert,
    iceServers: async () => [{ urls: 'stun:stun.example' }],
    RTCPeerConnection: FakeConnection,
    WebSocket: relayAnswering(async (offer) => ({
      type: 'answer',
      sdp: ANSWER,
      cert: toBase64(der),
      sig: toBase64url(await sign(fingerprint(offer), fingerprint(ANSWER))),
    })),
  })
  assert.ok(provider.opens('webrtc:wss://relay.example') && !provider.opens('relay:wss://relay.example'))
  const pipe = await provider.open('webrtc:wss://relay.example/r', id, { state: noState, signal: new AbortController().signal })
  const relay = FakeSocket.made[0]
  const connection = FakeConnection.last
  assert.equal(relay.url, 'wss://relay.example/r')
  const sent = relay.sent.map((text) => JSON.parse(text))
  assert.deepEqual(sent[0], { t: 'join', id, kind: 'webrtc' })
  assert.deepEqual(sent[1], { t: 'signal', data: { type: 'offer', sdp: OFFER } })
  assert.deepEqual(connection.config, { certificates: [cert], iceServers: [{ urls: 'stun:stun.example' }] })
  assert.equal(connection.channel.label, 'hmz')
  assert.deepEqual(connection.channel.options, { ordered: true })
  assert.deepEqual(connection.added, [{ candidate: 'candidate:2', sdpMid: '0', sdpMLineIndex: 0 }])
  assert.equal(relay.readyState, 3)

  pipe.send(new Uint8Array(40000))
  assert.deepEqual(connection.channel.sent.map((chunk) => chunk.length), [16384, 16384, 7232])
  const got = []
  let why = null
  pipe.listen((bytes) => got.push(bytes.length), (said) => (why = said))
  connection.channel.onmessage({ data: new ArrayBuffer(5) })
  assert.deepEqual(got, [5])
  connection.channel.onmessage({ data: 'text' })
  assert.equal(why, 'The daemon sent text.')
  assert.ok(connection.closed)
})

test('webrtc refuses an answer not signed by the daemon pinned, before any frame', async () => {
  const { id, der, sign } = await daemonKey()
  const other = await daemonKey()
  for (const answer of [
    async (offer) => ({ type: 'answer', sdp: ANSWER, cert: toBase64(other.der), sig: toBase64url(await other.sign(fingerprint(offer), DD)) }),
    async () => ({ type: 'answer', sdp: ANSWER, cert: toBase64(der), sig: toBase64url(await sign(hex('00'), DD)) }),
  ]) {
    const provider = webrtc({ certificate: async () => ({}), RTCPeerConnection: FakeConnection, WebSocket: relayAnswering(answer) })
    await assert.rejects(provider.open('webrtc:ws://relay', id, { state: noState, signal: new AbortController().signal }), NotPinned)
    assert.ok(FakeConnection.last.closed)
    assert.equal(FakeConnection.last.remoteDescription, undefined)
  }
})

test('webrtc fails with what the relay says', async () => {
  const Refusing = class extends FakeSocket {
    constructor(url) {
      super(url)
      this.onsent = () => this.says(JSON.stringify({ t: 'error', why: 'No daemon x is here.' }))
    }
  }
  const provider = webrtc({ certificate: async () => ({}), RTCPeerConnection: FakeConnection, WebSocket: Refusing })
  await assert.rejects(provider.open('webrtc:ws://relay', 'x', { state: noState, signal: new AbortController().signal }), /No daemon x is here\./)
})

test('webrtc fails at once with the daemon\'s refusal the relay passes on after joined', async () => {
  const Refused = class extends FakeSocket {
    constructor(url) {
      super(url)
      this.onsent = (text) => {
        const message = JSON.parse(text)
        if (message.t === 'join') this.says(JSON.stringify({ t: 'joined' }))
        if (message.t === 'signal' && message.data.type === 'offer') {
          this.says(JSON.stringify({ t: 'error', why: 'This daemon cannot answer WebRTC.' }))
          this.close()
        }
      }
    }
  }
  const provider = webrtc({ certificate: async () => ({}), RTCPeerConnection: FakeConnection, WebSocket: Refused })
  const started = Date.now()
  await assert.rejects(provider.open('webrtc:ws://relay', 'x', { state: noState, signal: new AbortController().signal }), {
    message: 'This daemon cannot answer WebRTC.',
  })
  assert.ok(Date.now() - started < 1000)
  assert.ok(FakeConnection.last.closed)
})
