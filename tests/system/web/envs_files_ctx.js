// The stand-in `ctx` the Files panel is mounted on in test_web_envs_files.py: an environment of
// a few files held in memory, answering the `env.*` files methods, every call kept.
(async () => {
  const enc = (text) => new TextEncoder().encode(text)
  const b64 = (bytes) => btoa(String.fromCharCode(...bytes))
  const files = new Map()
  let made = 0
  const put = (path, text) => files.set(path, { bytes: enc(text), mtime: 1000 + ++made, etag: `e${made}` })
  put('/w/main.py', 'def greet(name):\n    return f"hi {name}"\n\nprint(greet("you"))\n')
  put('/w/src/util.py', 'import os\n\n\ndef here():\n    return os.getcwd()\n')
  put('/w/src/app.js', 'export const answer = 42\n')
  put('/w/README.md', '# Project\n')
  put('/w/blob.bin', 'a\u0000b')
  const dirs = new Set(['/w', '/w/src'])
  const calls = []
  const refuse = (why) => { throw new Error(why) }
  const entries = (dir) => {
    const out = []
    for (const one of dirs) if (one !== dir && one.startsWith(dir + '/') && !one.slice(dir.length + 1).includes('/')) out.push({ name: one.slice(dir.length + 1), kind: 'dir', size: 0, mtime: 0 })
    for (const [path, file] of files) if (path.startsWith(dir + '/') && !path.slice(dir.length + 1).includes('/')) out.push({ name: path.slice(dir.length + 1), kind: 'file', size: file.bytes.length, mtime: file.mtime })
    return out
  }
  const abs = (path) => (path.startsWith('/') ? path : `/w/${path}`)
  const methods = {
    'env.list': ({ path }) => ({ path: abs(path), entries: entries(abs(path)) }),
    'env.stat': ({ path }) => {
      const file = files.get(abs(path)) || refuse(`No such file: ${path}`)
      return { path: abs(path), name: path.split('/').pop(), kind: 'file', size: file.bytes.length, mtime: file.mtime }
    },
    'env.read': ({ path, offset = 0, length = 1048576 }) => {
      const file = files.get(abs(path)) || refuse(`No such file: ${path}`)
      const part = file.bytes.subarray(offset, offset + length)
      return { data: b64(part), size: file.bytes.length, mtime: file.mtime, etag: file.etag, eof: offset + part.length >= file.bytes.length }
    },
    'env.write': ({ path, data, if_match }) => {
      const file = files.get(abs(path))
      if (if_match === '' && file) refuse(`${path} exists already.`)
      if (if_match && (!file || file.etag !== if_match)) refuse(`${path} changed since you read it.`)
      files.set(abs(path), { bytes: Uint8Array.from(atob(data), (c) => c.charCodeAt(0)), mtime: 1000 + ++made, etag: `e${made}` })
      const now = files.get(abs(path))
      return { etag: now.etag, size: now.bytes.length, mtime: now.mtime }
    },
    'env.mkdir': ({ path }) => (dirs.add(abs(path)), {}),
    'env.rename': ({ path, to }) => {
      files.set(abs(to), files.get(abs(path)))
      files.delete(abs(path))
      return {}
    },
    'env.remove': ({ path }) => (files.delete(abs(path)), {}),
    'env.find': () => ({ paths: [...files.keys()].map((one) => one.slice(3)), truncated: false }),
    'env.search': ({ query }) => {
      const matches = []
      for (const [path, file] of files) {
        new TextDecoder().decode(file.bytes).split('\n').forEach((text, i) => {
          const at = text.indexOf(query)
          if (at >= 0) matches.push({ path: path.slice(3), line: i + 1, column: at + 1, text })
        })
      }
      return { matches, truncated: false }
    },
  }
  const kept = new Map()
  const ctx = {
    env: { id: '1:root', role: 'coder', workdir: '/w', open: true, available: true, caps: ['files'], declared: ['files'] },
    call: async (method, params) => {
      calls.push([method, params])
      await new Promise((done) => setTimeout(done, 5))
      return methods[method](params)
    },
    on: () => () => {},
    keep: (key, value) => (value === undefined ? kept.get(key) : kept.set(key, value)),
    open: () => {},
    confirm: async () => true,
    theme: () => ({ dark: false, tokens: {} }),
  }
  window.fake = { files, calls, put, text: (path) => new TextDecoder().decode(files.get(path).bytes) }
  const host = document.createElement('div')
  host.dataset.hmz = 'files-host'
  Object.assign(host.style, { position: 'fixed', inset: '0', zIndex: '50', background: 'var(--paper)' })
  document.body.append(host)
  const { mount } = await import('/views/envs/files.js')
  window.panel = await mount(host, ctx)
})()
