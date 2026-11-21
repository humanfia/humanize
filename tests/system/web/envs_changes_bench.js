// The Changes panel mounted alone on a repository held in the page, for
// tests/system/web/test_web_envs_changes.py: `env.git.*` answered out of files each with a HEAD,
// an index and a worktree side, staged, unstaged, discarded and committed as git would. What the
// panel did is kept on `window.repo`, the panel on `window.panel`.
(async ({caps, conflict, refusal}) => {
  const enc = (text) => text === null ? null : btoa(String.fromCharCode(...new TextEncoder().encode(text)))
  const files = {
    'src/app.py': {head: 'import os\n\n\ndef main():\n    return 1\n', index: null, work: 'import os\nimport sys\n\n\ndef main():\n    return 2\n'},
    'README.md': {head: '# Demo\n', index: '# Demo\n\nMore words.\n', work: null},
    'old.txt': {head: 'gone\n', index: null, work: null, deleted: true},
    'notes/todo.txt': {head: null, index: null, work: 'write tests\n'},
    'logo.png': {head: null, index: null, work: '\u0000PNG', binary: true},
  }
  for (const one of Object.values(files)) {
    if (one.index === null && one.head !== null) one.index = one.head
    if (one.work === null && !one.deleted) one.work = one.index
  }
  const repo = window.repo = {files, commits: [{hash: 'f00dfeed0123456789', parents: [], author: 'Ada', date: new Date(Date.now() - 3 * 3600e3).toISOString(), subject: 'First commit'}],
    calls: [], pending: 0, asked: [], answer: true, opened: [], handlers: {}, snapshots: ['hmz/snap/1', 'hmz/snap/2']}
  const char = (from, to) => from === to ? '.' : from === null ? 'A' : to === null ? 'D' : 'M'
  const status = () => {
    const out = Object.entries(files).map(([path, f]) => {
      if (f.head === null && f.index === null) return {path, index: '?', worktree: '?', state: 'untracked'}
      return {path, index: char(f.head, f.index), worktree: char(f.index, f.work), state: 'changed'}
    }).filter((f) => f.index !== '.' || f.worktree !== '.')
    if (conflict) out.push({path: 'both.c', index: 'U', worktree: 'U', state: 'conflict'})
    return {root: '/work', branch: 'main', head: repo.commits[0].hash, upstream: 'origin/main', ahead: repo.commits.length - 1, behind: 2, files: out}
  }
  const methods = {
    'env.git.status': status,
    'env.git.log': () => ({commits: repo.commits}),
    'env.git.diff': ({path, staged}) => {
      const f = files[path]
      const [a, b] = staged ? [f.head, f.index] : [f.head === null && f.index === null ? null : f.index, f.work]
      return {old: enc(a), new: enc(b), binary: Boolean(f.binary)}
    },
    'env.git.stage': ({paths}) => { for (const p of paths) { const f = files[p]; f.index = f.work; if (f.work === null && f.head === null) delete files[p] } return {} },
    'env.git.unstage': ({paths}) => { for (const p of paths) files[p].index = files[p].head; return {} },
    'env.git.discard': ({paths}) => {
      for (const p of paths) { const f = files[p]; if (f.head === null && f.index === null) delete files[p]; else f.work = f.index }
      return {}
    },
    'env.git.commit': ({message, amend}) => {
      for (const [p, f] of Object.entries(files)) { f.head = f.index; if (f.head === null && f.work === null) delete files[p] }
      const hash = Math.random().toString(16).slice(2).padEnd(12, '0')
      const one = {hash, parents: [], author: 'Ada', date: new Date().toISOString(), subject: message.split('\n')[0]}
      if (amend) repo.commits[0] = one; else repo.commits.unshift(one)
      return {head: hash}
    },
    'env.git.snapshots': () => ({snapshots: repo.snapshots}),
    'env.git.rewind': () => { if (refusal) throw new Error(refusal); return {} },
  }
  const kept = {}
  const ctx = {
    env: {id: '1:workspace', role: 'workspace', caps, declared: ['git']},
    async call(method, params) {
      repo.calls.push([method, params])
      if (repo.closed) throw new Error('That environment has closed.')
      repo.pending += 1
      try {
        await new Promise((r) => setTimeout(r, 5))
        if (!methods[method]) throw new Error(`no ${method}`)
        return structuredClone(methods[method](params))
      } finally {
        repo.pending -= 1
      }
    },
    on(type, fn) { (repo.handlers[type] ||= []).push(fn); return () => {} },
    keep(key, value) { if (value === undefined) return kept[key]; kept[key] = value },
    open(tab, args) { repo.opened.push([tab, args]) },
    async confirm(text) { repo.asked.push(text); return repo.answer },
    theme() { return {dark: false, tokens: {}} },
  }
  document.querySelector('#ch-host')?.remove()
  const host = document.createElement('div')
  host.id = 'ch-host'
  document.body.append(host)
  for (const [k, v] of Object.entries({position: 'fixed', inset: '0', zIndex: '1000'})) host.style[k] = v
  const {mount} = await import('/views/envs/changes.js')
  window.panel = await mount(host, ctx)
})
