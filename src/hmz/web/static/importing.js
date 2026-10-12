// Reading an epic back in from a `.hmzepic`, exported here or on another machine: picked from
// the disk, or dropped anywhere on the window, and opened once it is in. One already on this
// machine, named by its path -- as the desktop app opens a file -- is `#/epics/import?path=`.

import { refresh, send } from './api.js'
import { h, iconButton, problem } from './dom.js'

/** What an epic's archive is named with, and sent as. */
const SUFFIX = '.hmzepic'
const KIND = 'application/vnd.hmz.epic+gzip'

/** The most the server takes of one, which is told before any of it is sent. */
const LARGEST = 2 * 1024 ** 3

/** What is said of the import going, or of how it failed, until the next or until closed. */
let notice = null

function say(...kids) {
  notice?.remove()
  notice = kids.length ? h('div', { class: 'toast notice', role: 'status', 'data-hmz': 'import-notice' }, kids) : null
  if (notice) document.body.append(notice)
}

/** Says why an import failed, until closed. */
function failed(...why) {
  say(why, iconButton('close', 'Close', { onclick: () => say() }))
}

/** How an import refused is said: the server's sentence, and the epic it names where that is here already. */
export function refusal(error) {
  const name = error.said && error.said.name
  return [problem(error), name ? h('a', { href: `#/epics/${encodeURIComponent(name)}`, 'data-hmz': 'imported-already', onclick: () => say() }, 'Open') : null]
}

/** Sends one archive, saying so as it goes, and opens the epic it was once it is in. */
export async function importFile(file) {
  if (file.size > LARGEST) return failed(problem('That is more than a request here may send.'))
  say(h('span', {}, `Importing ${file.name}…`))
  try {
    const answer = await send('/api/runs/import', file, KIND)
    say()
    refresh('/api/runs')
    location.hash = `/epics/${encodeURIComponent(answer.name)}`
  } catch (error) {
    failed(refusal(error))
  }
}

/** The system's own picker, for one archive: kept, so that it is picked from again as it was. */
const picker = h('input', { type: 'file', accept: SUFFIX, hidden: true, 'data-hmz': 'import-file' })
picker.addEventListener('change', () => {
  const [file] = picker.files
  picker.value = ''
  if (file) importFile(file)
})

/** Asks for an archive to import. */
export function pick() {
  if (!picker.isConnected) document.body.append(picker)
  picker.click()
}

// ------------------------------------------------------------------ dropped on the window

/** How deep into the page a file being dragged is, which is out of it at 0. */
let over = 0

function carriesFiles(event) {
  return Boolean(event.dataTransfer) && [...event.dataTransfer.types].includes('Files')
}

function dropping(on) {
  if (!on) over = 0
  document.body.classList.toggle('dropping', on)
}

addEventListener('dragenter', (event) => {
  if (!carriesFiles(event)) return
  over += 1
  dropping(true)
})
addEventListener('dragleave', (event) => {
  if (carriesFiles(event) && (over -= 1) <= 0) dropping(false)
})
addEventListener('dragover', (event) => {
  if (!carriesFiles(event)) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'copy'
})
addEventListener('drop', (event) => {
  if (!carriesFiles(event)) return
  // Never opened by the browser in place of the page.
  event.preventDefault()
  dropping(false)
  const file = [...event.dataTransfer.files].find((one) => one.name.endsWith(SUFFIX))
  if (file) importFile(file)
  else failed(problem(`Only a ${SUFFIX} file is imported.`))
})
