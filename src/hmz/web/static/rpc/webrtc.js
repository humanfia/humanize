// The browser's own pipe provider for `webrtc:<url>` routes (Section 4.7 of protocol/wire.md): a
// WebRTC connection offered with the browser's persistent DTLS certificate and signalled through
// the relay at `<url>` (Section 5.5), whose data channel `hmz` carries the bytes. Before any frame,
// the daemon's answer is checked: its certificate must have the daemon id pinned, and its
// signature over both DTLS fingerprints must verify under that certificate's key.

import { t } from '../i18n.js'
import { NotPinned } from './client.js'
import { Pipe, fromBase64, onAbort, toBase32 } from './pipe.js'
import { routeKind } from './routes.js'

/** The most bytes of the carrier one data channel message carries (Section 4.7.3). */
const CHUNK = 16384

/** How many bytes may wait in the data channel before sending waits for it to drain. */
const BUFFERED = 1048576

/**
 * @param {{certificate: () => Promise<RTCCertificate>, RTCPeerConnection?: typeof RTCPeerConnection,
 *   WebSocket?: typeof WebSocket, subtle?: SubtleCrypto}} options `certificate` the browser's DTLS
 *   certificate (`registry`'s). A route is opened with the STUN and TURN servers of the daemon it
 *   reaches, as `open` is given them, and with none where it is given none.
 * @returns {import('./client.js').Provider}
 */
export function webrtc({
  certificate,
  RTCPeerConnection: Connection = globalThis.RTCPeerConnection,
  WebSocket: Socket = globalThis.WebSocket,
  subtle = globalThis.crypto.subtle,
}) {
  return {
    opens: (route) => routeKind(route) === 'webrtc',
    async open(route, id, { state, signal, iceServers = [] }) {
      const cert = await certificate()
      return new Promise((resolve, reject) => {
        const relay = new Socket(route.slice('webrtc:'.length))
        const peer = new Connection({ certificates: [cert], iceServers })
        const channel = peer.createDataChannel('hmz', { ordered: true })
        channel.binaryType = 'arraybuffer'
        /** @type {Pipe | null} */
        let pipe = null
        let offered = ''
        let answered = false
        /** @type {RTCIceCandidateInit[]} Candidates come before the answer was taken. */
        const waiting = []
        const signalled = (data) => relay.readyState === 1 && relay.send(JSON.stringify({ t: 'signal', data }))
        const fail = (error) => {
          stop()
          relay.close()
          peer.close()
          if (pipe) pipe.end(error.message)
          else reject(error)
        }
        const stop = onAbort(signal, () => fail(new Error(t('Given up.'))))

        relay.onopen = () => relay.send(JSON.stringify({ t: 'join', id, kind: 'webrtc' }))
        relay.onclose = () => {
          if (!pipe) fail(new Error(t('{route} closed.', { route })))
        }
        relay.onmessage = async (event) => {
          let message
          try {
            message = JSON.parse(event.data)
          } catch {
            return
          }
          try {
            if (message.t === 'error') fail(new Error(message.why))
            else if (message.t === 'joined') {
              state('connecting', t('Joined the relay.'))
              const offer = await peer.createOffer()
              await peer.setLocalDescription(offer)
              offered = peer.localDescription?.sdp ?? offer.sdp ?? ''
              signalled({ type: 'offer', sdp: offered })
            } else if (message.t === 'signal' && message.data?.type === 'answer') {
              const { sdp, cert: der, sig } = message.data
              if (!(await signed(subtle, id, fromBase64(der), fromBase64(sig), offered, sdp))) throw new NotPinned()
              await peer.setRemoteDescription({ type: 'answer', sdp })
              answered = true
              for (const candidate of waiting.splice(0)) await peer.addIceCandidate(candidate)
            } else if (message.t === 'signal' && message.data?.type === 'candidate') {
              const { candidate, sdpMid, sdpMLineIndex } = message.data
              if (answered) await peer.addIceCandidate({ candidate, sdpMid, sdpMLineIndex })
              else waiting.push({ candidate, sdpMid, sdpMLineIndex })
            }
          } catch (error) {
            fail(error)
          }
        }
        peer.onconnectionstatechange = () => {
          if (peer.connectionState === 'failed') fail(new Error(t('{route} could not connect.', { route })))
        }
        peer.onicecandidate = (event) => {
          const candidate = event.candidate
          if (candidate?.candidate) signalled({ type: 'candidate', candidate: candidate.candidate, sdpMid: candidate.sdpMid, sdpMLineIndex: candidate.sdpMLineIndex })
        }

        /** @type {Uint8Array[]} */
        const queue = []
        const drain = () => {
          while (queue.length && channel.bufferedAmount <= BUFFERED) channel.send(queue.shift())
        }
        channel.bufferedAmountLowThreshold = BUFFERED / 2
        channel.onbufferedamountlow = drain
        channel.onopen = () => {
          stop()
          relay.onclose = null
          relay.close()
          pipe = new Pipe(
            (bytes) => {
              for (let at = 0; at < bytes.length; at += CHUNK) queue.push(bytes.slice(at, at + CHUNK))
              drain()
            },
            () => peer.close(),
          )
          resolve(pipe)
        }
        channel.onmessage = (event) => {
          if (typeof event.data === 'string') fail(new Error(t('The daemon sent text.')))
          else pipe?.feed(new Uint8Array(event.data))
        }
        channel.onclose = () => fail(new Error(t('{route} closed.', { route })))
      })
    },
  }
}

/** A `sha-256` value (Section 4.7.12): 32 bytes in hexadecimal, a colon between each. */
const SHA256 = /^[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){31}$/

/**
 * The `sha-256` fingerprint of an SDP, as written there (Section 4.7.12 and 4.7.13): the one
 * distinct value its `a=fingerprint:sha-256` lines say, which they may repeat.
 *
 * @param {string} sdp
 */
export function fingerprint(sdp) {
  const lines = [...sdp.matchAll(/^a=fingerprint:(\S+)[ \t]+(\S+)[ \t]*\r?$/gm)]
  const values = new Set(lines.filter(([, name]) => name.toLowerCase() === 'sha-256').map(([, , value]) => value))
  if (values.size !== 1) throw new Error(t('A description must say exactly one sha-256 fingerprint.'))
  const [value] = values
  if (!SHA256.test(value)) throw new Error(t('{value} is not a sha-256 fingerprint.', { value }))
  return value
}

/**
 * Whether a daemon's answer is the pinned daemon's (Section 4.7.5 and 4.7.6): `der` has the
 * daemon id `id`, and `sig` is its key's over `hmz-webrtc/1`, the offer's fingerprint and the
 * answer's, each on a line.
 *
 * @param {SubtleCrypto} subtle
 * @param {string} id
 * @param {Uint8Array} der The daemon's certificate.
 * @param {Uint8Array} sig The 64 bytes of `r` and `s`.
 * @param {string} offer
 * @param {string} answer
 */
export async function signed(subtle, id, der, sig, offer, answer) {
  const spki = publicKeyInfo(der)
  if (toBase32(new Uint8Array(await subtle.digest('SHA-256', spki))) !== id) return false
  const key = await subtle.importKey('spki', spki, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify'])
  const text = new TextEncoder().encode(`hmz-webrtc/1\n${fingerprint(offer)}\n${fingerprint(answer)}`)
  return subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, key, sig, text)
}

/**
 * The DER of a certificate's `SubjectPublicKeyInfo`: the seventh field of its `tbsCertificate`,
 * counting the version, which is tagged [0], where it is there.
 *
 * @param {Uint8Array} der
 */
export function publicKeyInfo(der) {
  /** The element at `at`: where its content starts and where it ends. */
  const element = (at) => {
    let length = der[at + 1]
    let start = at + 2
    if (length & 0x80) {
      const count = length & 0x7f
      length = 0
      for (let i = 0; i < count; i++) length = length * 256 + der[start + i]
      start += count
    }
    if (start + length > der.length) throw new Error(t('That certificate is not DER.'))
    return { tag: der[at], start, end: start + length }
  }
  const certificate = element(0)
  const tbs = element(certificate.start)
  let at = tbs.start
  if (element(at).tag === 0xa0) at = element(at).end
  for (let skipped = 0; skipped < 5; skipped++) at = element(at).end
  const spki = element(at)
  if (spki.tag !== 0x30) throw new Error(t('That certificate is not DER.'))
  return der.slice(at, spki.end)
}
