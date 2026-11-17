import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  ACK_EVERY,
  binary,
  closedRefusal,
  CREDIT,
  debounced,
  Flow,
  fromBase64,
  goneRefusal,
  INPUT_MOST,
  joined,
  missed,
  mix,
  pairedRefusal,
  RACED,
  palette,
  parseColor,
  shellName,
  Tail,
  tabTitle,
  toBase64,
  Typing,
  unseen,
  utf8,
} from '../../../../src/hmz/web/static/views/envs/terminal_flow.js'

const bytesOf = (text) => new TextEncoder().encode(text)
const textOf = (bytes) => new TextDecoder().decode(bytes)

/** Timers a test runs by hand. */
function clock() {
  const waiting = new Map()
  let next = 1
  return {
    later: (fn, ms) => (waiting.set(next, { fn, ms }), next++),
    cancel: (handle) => waiting.delete(handle),
    run() {
      const due = [...waiting.values()]
      waiting.clear()
      for (const one of due) one.fn()
    },
    get size() {
      return waiting.size
    },
  }
}

test('base64 carries every byte value, and arrays larger than one apply can take', () => {
  const every = Uint8Array.from({ length: 256 }, (_, at) => at)
  assert.deepEqual([...fromBase64(toBase64(every))], [...every])
  const big = Uint8Array.from({ length: 300000 }, (_, at) => (at * 7) & 0xff)
  assert.deepEqual(fromBase64(toBase64(big)), big)
  assert.equal(toBase64(new Uint8Array(0)), '')
  assert.deepEqual(fromBase64(''), new Uint8Array(0))
  assert.deepEqual(fromBase64(undefined), new Uint8Array(0))
  assert.equal(toBase64(utf8('héllo ✓')), Buffer.from('héllo ✓').toString('base64'))
})

test('typed text is sent as UTF-8; xterm binary as one byte per char', () => {
  assert.deepEqual([...utf8('é')], [0xc3, 0xa9])
  assert.deepEqual([...utf8('🙂')], [0xf0, 0x9f, 0x99, 0x82])
  assert.deepEqual([...binary('\x1b[M \xff\x80')], [0x1b, 0x5b, 0x4d, 0x20, 0xff, 0x80])
  assert.deepEqual([...joined([Uint8Array.of(1), new Uint8Array(0), Uint8Array.of(2, 3)])], [1, 2, 3])
})

test('drawn output is acknowledged every 64 KiB, only once xterm has drawn it', () => {
  const acks = []
  const time = clock()
  const flow = new Flow({ ack: (n) => acks.push(n), later: time.later, cancel: time.cancel })
  flow.got(ACK_EVERY)
  assert.equal(flow.unacked, ACK_EVERY)
  assert.deepEqual(acks, [], 'received is not drawn')
  flow.wrote(ACK_EVERY - 1)
  assert.deepEqual(acks, [])
  flow.wrote(1)
  assert.deepEqual(acks, [ACK_EVERY])
  assert.equal(flow.unacked, 0)
})

test('what is drawn short of 64 KiB is acknowledged once drawing idles', () => {
  const acks = []
  const time = clock()
  const flow = new Flow({ ack: (n) => acks.push(n), later: time.later, cancel: time.cancel })
  flow.got(100)
  flow.got(50)
  flow.wrote(100)
  assert.equal(time.size, 0, 'not idle while 50 bytes are still being drawn')
  flow.wrote(50)
  assert.equal(time.size, 1)
  flow.got(10) // more came: not idle after all
  assert.equal(time.size, 0)
  flow.wrote(10)
  time.run()
  assert.deepEqual(acks, [160])
  assert.equal(flow.unacked, 0)
})

test('a renderer that never draws holds the credit, so the host stops at 1 MiB', () => {
  const acks = []
  const time = clock()
  const flow = new Flow({ ack: (n) => acks.push(n), later: time.later, cancel: time.cancel })
  for (let sent = 0; sent < CREDIT; sent += 64 * 1024) flow.got(64 * 1024)
  time.run()
  assert.deepEqual(acks, [])
  assert.equal(flow.unacked, CREDIT)
  // Drawn at last, in pieces as a slow renderer would: acknowledged 64 KiB at a time.
  for (let drawn = 0; drawn < CREDIT; drawn += 16 * 1024) flow.wrote(16 * 1024)
  assert.equal(acks.length, CREDIT / ACK_EVERY)
  assert.ok(acks.every((n) => n === ACK_EVERY))
  assert.equal(flow.unacked, 0)
})

test('the threshold never strands output: the sum acknowledged is the sum drawn', () => {
  const acks = []
  const time = clock()
  const flow = new Flow({ ack: (n) => acks.push(n), later: time.later, cancel: time.cancel })
  let total = 0
  for (let at = 0; at < 500; at++) {
    const n = 1 + ((at * 7919) % 9000)
    total += n
    flow.got(n)
    flow.wrote(n)
  }
  time.run()
  assert.equal(acks.reduce((a, b) => a + b, 0), total)
  assert.ok(acks.slice(0, -1).every((n) => n >= ACK_EVERY))
})

test('flush acknowledges now; reset forgets; stop acknowledges nothing more', () => {
  const acks = []
  const time = clock()
  const flow = new Flow({ ack: (n) => acks.push(n), later: time.later, cancel: time.cancel })
  flow.got(10)
  flow.wrote(10)
  flow.flush()
  assert.deepEqual(acks, [10])
  assert.equal(time.size, 0)
  flow.flush()
  assert.deepEqual(acks, [10], 'nothing to acknowledge')
  flow.got(5)
  flow.reset()
  assert.equal(flow.unacked, 0)
  flow.got(5)
  flow.wrote(5)
  flow.stop()
  time.run()
  flow.flush()
  assert.deepEqual(acks, [10])
})

/** A Typing whose frames and calls the test runs by hand. */
function typer({ fail = () => false } = {}) {
  const frames = []
  const sent = []
  const failed = []
  const out = []
  const typing = new Typing({
    frame: (fn) => frames.push(fn),
    send: (bytes) =>
      new Promise((done, refuse) => {
        sent.push(textOf(bytes))
        out.push(() => (fail(bytes) ? refuse(new Error('There is no terminal t1.')) : done({})))
      }),
    failed: (error) => failed.push(error.message),
  })
  const frame = () => frames.splice(0).forEach((fn) => fn())
  const answer = async () => {
    while (out.length) {
      out.shift()()
      await new Promise((done) => setTimeout(done, 0))
    }
  }
  return { typing, frames, sent, failed, frame, answer }
}

test('what is typed in one frame goes as one call', async () => {
  const { typing, frames, sent, frame, answer } = typer()
  typing.push(utf8('l'))
  typing.push(utf8('s'))
  typing.push(utf8('\r'))
  assert.equal(frames.length, 1, 'one frame asked for')
  assert.deepEqual(sent, [])
  frame()
  assert.deepEqual(sent, ['ls\r'])
  await answer()
  await typing.idle
})

test('typing waits for the call out, then sends what came meanwhile, in order', async () => {
  const { typing, sent, frame, answer, frames } = typer()
  typing.push(utf8('a'))
  frame()
  typing.push(utf8('b'))
  typing.push(utf8('c'))
  assert.equal(frames.length, 0, 'no frame while a call is out')
  assert.deepEqual(sent, ['a'])
  await answer()
  assert.deepEqual(sent, ['a', 'bc'])
  await answer()
  await typing.idle
  typing.push(utf8('d'))
  frame()
  await answer()
  assert.deepEqual(sent, ['a', 'bc', 'd'])
})

test('a refused call is told, and what follows still goes', async () => {
  const { typing, sent, failed, frame, answer } = typer({ fail: (bytes) => textOf(bytes) === 'x' })
  typing.push(utf8('x'))
  frame()
  typing.push(utf8('y'))
  await answer()
  await answer()
  assert.deepEqual(sent, ['x', 'y'])
  assert.deepEqual(failed, ['There is no terminal t1.'])
})

test('a paste larger than one call carries goes in pieces, in order, whole', async () => {
  const { typing, sent, frame, answer } = typer()
  const text = 'abcdefghij'.repeat((INPUT_MOST * 2.5) / 10)
  typing.push(utf8(text))
  frame()
  await answer()
  await answer()
  await answer()
  assert.equal(sent.length, 3)
  assert.ok(sent.every((one) => one.length <= INPUT_MOST))
  assert.equal(sent.join(''), text)
})

test('now sends without waiting for a frame; stop sends nothing more', async () => {
  const { typing, sent, answer } = typer()
  typing.push(utf8('q'))
  typing.now()
  assert.deepEqual(sent, ['q'])
  await answer()
  typing.stop()
  typing.push(utf8('r'))
  typing.now()
  assert.deepEqual(sent, ['q'])
  await typing.idle
})

test('a resize debounced is sent once, with the last size', () => {
  const time = clock()
  const seen = []
  const resize = debounced((size) => seen.push(size), 80, time.later, time.cancel)
  resize({ cols: 80 })
  resize({ cols: 90 })
  resize({ cols: 100 })
  assert.equal(time.size, 1)
  time.run()
  assert.deepEqual(seen, [{ cols: 100 }])
  resize({ cols: 1 })
  resize.cancel()
  time.run()
  assert.deepEqual(seen, [{ cols: 100 }])
})

test('a tail keeps the last bytes drawn', () => {
  const tail = new Tail(8)
  tail.push(bytesOf('hello '))
  tail.push(bytesOf('world'))
  assert.equal(textOf(tail.bytes), 'lo world')
  tail.push(bytesOf('0123456789'))
  assert.equal(textOf(tail.bytes), '23456789')
  tail.set(bytesOf('ab'))
  assert.equal(textOf(tail.bytes), 'ab')
})

test('attached again, a terminal draws only what it missed', () => {
  const replay = bytesOf('$ ls\r\nfile\r\n$ echo hi\r\nhi\r\n$ ')
  assert.equal(textOf(missed(bytesOf('file\r\n$ '), replay)), 'echo hi\r\nhi\r\n$ ')
  assert.equal(missed(bytesOf('hi\r\n$ '), replay).length, 0, 'nothing missed')
  assert.equal(missed(bytesOf('gone from scrollback'), replay), null, 'drawn anew')
  assert.equal(missed(new Uint8Array(0), replay), null)
  // A tail found more than once cannot say where it was left: the terminal is drawn anew.
  assert.equal(missed(bytesOf('$ '), bytesOf('$ ls\r\nfile\r\n$ ')), null)
  // Bytes above 0x7f compare as bytes.
  const raw = Uint8Array.of(0xe2, 0x9c, 0x93, 0x0a, 0xff, 0x00, 0x41)
  assert.deepEqual([...missed(Uint8Array.of(0x9c, 0x93), raw)], [0x0a, 0xff, 0x00, 0x41])
})

test('output that raced the attach is drawn once: what the replay holds is not drawn again', () => {
  const replay = bytesOf('$ make\r\nbuilding')
  assert.equal(textOf(unseen(replay, bytesOf('building'))), '', 'held whole')
  assert.equal(textOf(unseen(replay, bytesOf('building... done\r\n'))), '... done\r\n', 'overlaps its end')
  assert.equal(textOf(unseen(replay, bytesOf('\r\nnext'))), '\r\nnext', 'none of it held')
  assert.equal(textOf(unseen(replay, bytesOf('g'))), 'g', 'a byte alone is taken for chance')
  assert.equal(textOf(unseen(new Uint8Array(0), bytesOf('abc'))), 'abc')
  assert.equal(unseen(replay, new Uint8Array(0)).length, 0)
  // Held far back in the scrollback, it is new output that only looks the same.
  const far = joined([bytesOf('user@host:~$ '), new Uint8Array(RACED + 10).fill(0x78)])
  assert.equal(textOf(unseen(far, bytesOf('user@host:~$ '))), 'user@host:~$ ')
})

test('looking for raced output is quick however large the replay and the output', () => {
  const replay = new Uint8Array(256 * 1024).fill(0x61)
  const next = new Uint8Array(1024 * 1024).fill(0x61)
  next[next.length - 1] = 0x62
  const started = Date.now()
  const rest = unseen(replay, next)
  assert.ok(Date.now() - started < 2000, `${Date.now() - started} ms`)
  assert.ok(rest.length < next.length)
  const tail = new Uint8Array(4096).fill(0x61)
  assert.equal(missed(tail, replay), null, 'found more than once')
})

test('colours are read as #hex or rgb(), and mixed', () => {
  assert.deepEqual(parseColor('#fff'), [255, 255, 255, 1])
  assert.deepEqual(parseColor('#0b7080'), [11, 112, 128, 1])
  assert.deepEqual(parseColor('#00000080').slice(0, 3), [0, 0, 0])
  assert.deepEqual(parseColor('rgba(20, 26, 31, 0.12)'), [20, 26, 31, 0.12])
  assert.deepEqual(parseColor('rgb(1 2 3 / 50%)'), [1, 2, 3, 0.5])
  assert.equal(parseColor('color-mix(in srgb, red, blue)'), null)
  assert.equal(parseColor(''), null)
  assert.equal(mix('#000000', '#ffffff', 0.5), '#808080')
  assert.equal(mix('nonsense', '#ffffff', 0.5), 'nonsense')
})

const KEYS = ['background', 'foreground', 'cursor', 'cursorAccent', 'selectionBackground', 'black', 'red', 'green', 'yellow', 'blue', 'magenta', 'cyan', 'white', 'brightBlack', 'brightRed', 'brightGreen', 'brightYellow', 'brightBlue', 'brightMagenta', 'brightCyan', 'brightWhite']

const luminance = (hex) => {
  const [r, g, b] = parseColor(hex).slice(0, 3).map((v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const contrast = (a, b) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

test('a palette is every colour xterm takes, as opaque hex, from the tokens', () => {
  const light = palette({
    dark: false,
    tokens: { surface: '#fbfdfd', ink: '#141a1f', fail: '#cf3552', done: '#2a9468', 'cyan-ink': '#0b7080', cyan: '#1fb3c7', 'line-strong': 'rgba(20, 26, 31, 0.28)' },
  })
  for (const key of KEYS) assert.match(light[key], /^#[0-9a-f]{6}$/, key)
  assert.equal(light.background, '#fbfdfd')
  assert.equal(light.foreground, '#141a1f')
  assert.equal(light.red, '#cf3552')
  assert.equal(light.green, '#2a9468')
  assert.equal(light.cyan, '#0b7080', 'the darker ink of a hue on light paper')
  // A see-through token is laid on the paper.
  assert.equal(light.white, '#babdbf')
})

test('the ANSI colours read on their paper, light or dark, with or without tokens', () => {
  for (const dark of [false, true]) {
    for (const tokens of [{}, dark ? { surface: '#172026', ink: '#e6eff1' } : { surface: '#fbfdfd', ink: '#141a1f' }]) {
      const theme = palette({ dark, tokens })
      for (const key of ['red', 'green', 'blue', 'magenta', 'cyan', 'foreground']) {
        assert.ok(contrast(theme[key], theme.background) >= 3, `${dark ? 'dark' : 'light'} ${key}: ${theme[key]} on ${theme.background}`)
      }
      assert.notEqual(theme.red, theme.brightRed)
    }
  }
})

test('a palette ignores tokens it cannot read', () => {
  const theme = palette({ dark: true, tokens: { surface: 'var(--x)', fail: 'color-mix(in srgb, red, blue)' } })
  assert.equal(theme.background, '#172026')
  assert.equal(theme.red, '#ff6f88')
})

test('a tab is called by the name given, the title set, or its shell', () => {
  assert.equal(shellName('/bin/zsh -l'), 'zsh')
  assert.equal(shellName(['/usr/bin/bash', '-l']), 'bash')
  assert.equal(shellName('-bash'), 'bash')
  assert.equal(shellName(null), 'shell')
  assert.equal(tabTitle({ shell: '/bin/zsh -l' }), 'zsh')
  assert.equal(tabTitle({ titled: 'vim notes.md', shell: '/bin/zsh' }), 'vim notes.md')
  assert.equal(tabTitle({ named: 'server', titled: 'vim', shell: '/bin/zsh' }), 'server')
  assert.equal(tabTitle({ titled: 'x'.repeat(100) }).length, 60)
})

test('refusals are told apart by what they say', () => {
  assert.ok(pairedRefusal('Terminals are off for paired devices; turn on envs.paired_terminals.'))
  assert.ok(closedRefusal('That environment has closed.'))
  assert.ok(goneRefusal('There is no terminal t9.'))
  assert.ok(!pairedRefusal('That environment has closed.'))
  assert.ok(!closedRefusal(undefined))
})
