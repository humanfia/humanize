// Draws where `hmz web` stands, as the app tells it: a splash while it starts, then -- where it
// does not -- what to do about it. Once it runs, the app takes the window to its page instead.

// What @tauri-apps/api's `invoke` calls, with no bundle of it put into every page, `hmz web`'s too.
const invoke = (command) => window.__TAURI_INTERNALS__.invoke(command)

const STATES = {
  missing: {
    title: 'Install humanize',
    lead: 'This app opens the humanize installed on this Mac. Install it in a terminal, then retry.',
    line: 'uv tool install hmz',
    action: 'Retry',
  },
  outdated: {
    title: 'Update humanize',
    lead: 'This app needs a newer humanize. Update it in a terminal, then retry.',
    line: 'uv tool upgrade hmz',
    action: 'Retry',
  },
  failed: { title: 'Failed', lead: 'hmz web exited before it started.', action: 'Retry' },
  stopped: { title: 'Stopped', lead: 'hmz web exited.', action: 'Restart' },
}

const $ = (id) => document.getElementById(id)
const main = document.querySelector('main')

function draw({ state, detail }) {
  const shown = STATES[state]
  main.dataset.state = shown ? state : 'starting'
  if (!shown) return
  $('title').textContent = shown.title
  $('lead').textContent = shown.lead
  $('line').textContent = shown.line ?? ''
  $('detail').textContent = detail ?? ''
  $('retry').textContent = shown.action
  $('retry').focus()
}

async function settle() {
  draw({ state: 'starting' })
  draw(await invoke('status'))
}

$('retry').addEventListener('click', async () => {
  draw({ state: 'starting' })
  await invoke('retry')
  await settle()
})

$('copy').addEventListener('click', async () => {
  const copy = $('copy')
  try {
    await navigator.clipboard.writeText($('line').textContent)
    copy.textContent = 'Copied'
  } catch {
    // Selected instead, for Cmd+C.
    getSelection().selectAllChildren($('line'))
  }
  setTimeout(() => (copy.textContent = 'Copy'), 1500)
})

settle()
