// Draws where the app stands, as it tells it: a splash while it starts, how an install of hmz
// goes, and -- where hmz web does not start -- why. Once it runs, the app takes the window to its
// page instead.

// What @tauri-apps/api's `invoke` calls, with no bundle of it put into every page, `hmz web`'s too.
const invoke = (command, args) => window.__TAURI_INTERNALS__.invoke(command, args)

const NO_WSL = 'WSL missing'

const STEPS = { uv: 'Getting uv', python: 'Getting Python', hmz: 'Installing hmz' }

// Each state the app tells, as drawn: its heading, what it says, and which buttons it offers.
const STATES = {
  installing: ({ updating, step, line }) => ({
    title: updating ? 'Updating Humanize CLI' : 'Installing Humanize CLI',
    step: STEPS[step],
    line,
  }),
  waiting: (version) => ({
    title: 'Update waiting',
    lead: `Epics are running in Humanize CLI${version ? ` ${version}` : ''}, which this app cannot open. It updates once they end; updating now may stop them.`,
    buttons: ['update_now', 'docs'],
  }),
  // On Windows, where there is no WSL for humanize to run in, which an install says first.
  'install-failed': ({ updating, said, keep }) => said.startsWith(NO_WSL) ? {
    title: NO_WSL,
    lead: 'humanize runs in WSL. Set up WSL with a Linux distribution, then retry.',
    detail: said.slice(NO_WSL.length).replace(/^:\s*/, ''),
    buttons: ['retry', 'docs'],
  } : ({
    title: updating ? 'Update failed' : 'Install failed',
    lead: keep
      ? 'Check the connection and retry, or continue with the Humanize CLI installed.'
      : 'Check the connection, then retry.',
    detail: said,
    buttons: ['retry', keep && 'keep', 'docs'],
  }),
  missing: () => ({
    title: 'Not found',
    lead: 'This build installs no Humanize CLI. Install hmz, or name one in HUMANIZE_HMZ, then retry.',
    buttons: ['retry', 'docs'],
  }),
  outdated: () => ({
    title: 'Outdated',
    lead: 'This hmz does not take hmz web --attached. Update it, then retry.',
    buttons: ['retry', 'docs'],
  }),
  failed: (said) => ({
    title: 'Failed',
    lead: 'hmz web exited before it started.',
    detail: said,
    buttons: ['retry', 'docs'],
  }),
  stopped: (said) => ({
    title: 'Stopped',
    lead: 'hmz web exited.',
    detail: said,
    buttons: ['retry', 'docs'],
    retry: 'Restart',
  }),
}

const $ = (id) => document.getElementById(id)
const main = document.querySelector('main')
const BUTTONS = ['retry', 'keep', 'update_now', 'docs']

function draw({ state, detail }) {
  const shown = STATES[state]?.(detail)
  main.dataset.state = shown ? state : 'starting'
  if (!shown) return
  $('title').textContent = shown.title
  $('lead').textContent = shown.lead ?? ''
  $('step').textContent = shown.step ?? ''
  $('line').textContent = shown.line ?? ''
  $('detail').textContent = shown.detail ?? ''
  $('retry').textContent = shown.retry ?? 'Retry'
  for (const button of BUTTONS) $(button).hidden = !shown.buttons?.includes(button)
  const first = BUTTONS.find((button) => !$(button).hidden)
  if (first && !main.contains(document.activeElement)) $(first).focus()
}

// Each status as it changes, until hmz web runs. A newer follow takes over from an older one.
let following = 0

async function follow() {
  const mine = ++following
  let after = null
  for (;;) {
    const status = await invoke('status', { after })
    if (mine !== following) return
    draw(status)
    if (status.state === 'running') return
    after = status
  }
}

for (const command of ['retry', 'keep', 'update_now']) {
  $(command).addEventListener('click', async () => {
    draw({ state: 'starting' })
    await invoke(command)
    follow()
  })
}

follow()
