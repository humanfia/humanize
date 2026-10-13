// The flows, in the two pages `/flow` opens on in the terminal interface. Installed: a card for
// each flow on offer in a workspace, by where it came from, each installed out of an index with
// its release and any newer one -- and, one opened, what it declares, with starting it, updating
// it, uninstalling it and copying it into the workspace whole. Flowverses: every index flows are
// installed out of, fetched or written into -- not this project's flows or yours, which are no
// index -- and, one opened, every flow it lists, every release of each, installing, switching
// and uninstalling one; with adding, fetching and removing one. Nothing opens until chosen.

import { get, hash, poll, post, refresh } from '../api.js'
import { stays } from '../app.js'
import { acting, confirming, empty, fill, h, icon, permitted, problem } from '../dom.js'
import { workspacePicker } from '../places.js'
import { bar, tabbed } from '../shell.js'
import { copy, menuOn, toast } from '../ui.js'

export function mount(root, { query }) {
  let tab = query.get('tab') === 'verses' ? 'verses' : 'installed'
  let chosen = query.get('flow') || ''
  let verse = query.get('verse') || ''
  // A workspace's flows: its own and yours, and the flowverses installed.
  let workspace = query.get('workspace') || ''
  const place = workspacePicker(workspace, (path) => {
    workspace = path
    chosen = ''
    watch()
  })
  const tabs = h('div', { class: 'flows-tabs' })
  const said = h('div', { class: 'flows-said', 'aria-live': 'polite' })
  const list = h('div', { class: 'gallery', 'data-hmz': 'flows' }, h('p', { class: 'loading', role: 'status' }, 'Reading the flows…'))
  const shown = h('section', { class: 'flow-detail', 'aria-live': 'polite', hidden: true })
  fill(
    root,
    h(
      'div',
      { class: 'view' },
      bar({ title: 'Flows', actions: [place.node] }),
      h('div', { class: 'view-scroll' }, h('div', { class: 'view-pad wide' }, tabs, said, shown, list)),
    ),
  )

  /** Every flowverse, what is installed out of them, and the newer releases there are. */
  let verses = null
  let stop = () => {}
  let stopVerses = () => {}

  const watch = () => {
    stop()
    stopVerses()
    stays({ tab: tab === 'verses' ? 'verses' : '', workspace, flow: tab === 'installed' ? chosen : '', verse: tab === 'verses' ? verse : '' })
    fill(tabs, tabbed([['installed', 'Installed'], ['verses', 'Flowverses']], tab, (key) => {
      tab = key
      watch()
    }))
    stopVerses = poll('/api/flowverses', 30000, (data, error) => {
      if (data) verses = data
      drawUpdates(error)
      if (tab === 'verses') drawVerses(error)
    })
    if (tab === 'installed') {
      stop = poll(`/api/flows?workspace=${encodeURIComponent(workspace)}`, 30000, drawFlows)
      if (chosen) show(chosen)
      else {
        shown.hidden = false
        fill(shown, empty('Pick a flow.', ' What it declares is shown here.'))
      }
    } else {
      stop = () => {}
      // Nothing of a flowverse is shown, nor the form adding one, until its card is chosen.
      if (verse) openVerse(verse)
      else close()
    }
  }

  /** Says what changed, and reads again what it changed. */
  async function change(url, body) {
    const answer = await post(url, body)
    fill(said, h('p', { class: 'note', role: 'status' }, answer.said || 'Done.'))
    refresh('/api/flowverses')
    refresh('/api/flows')
    return answer
  }

  function drawUpdates(error) {
    if (error) return
    const updates = verses ? verses.updates : []
    const banner = said.querySelector('[data-hmz=update-banner]')
    if (banner) banner.remove()
    if (!updates.length) return
    said.prepend(
      h(
        'div',
        { class: 'note', 'data-hmz': 'update-banner' },
        h('b', {}, `${updates.length} update${updates.length === 1 ? '' : 's'}`),
        ' ',
        updates.map((one) => h('span', { class: 'chip' }, `${one.flow} ${one.from} → ${one.to}`)),
      ),
    )
  }

  // ------------------------------------------------------------------ installed

  function drawFlows(data, error) {
    if (!data) {
      fill(list, error ? problem(error) : h('p', { class: 'loading' }, 'Reading the flows…'))
      return
    }
    const installed = Object.fromEntries(((verses && verses.installed) || []).map((one) => [one.flow, one]))
    const updates = Object.fromEntries(((verses && verses.updates) || []).map((one) => [one.flow, one]))
    const whose = {}
    for (const one of data.flows) (whose[one.whose] ||= []).push(one)
    fill(
      list,
      Object.entries(whose).map(([from, flows]) =>
        h(
          'section',
          { class: 'gallery-group' },
          h('h2', { class: 'kicker' }, from),
          h(
            'div',
            { class: 'cards' },
            flows.map((one) => {
              const card = h(
                'button',
                { class: ['card', one.name === chosen && 'chosen'], type: 'button', 'data-flow': one.name, 'aria-pressed': String(one.name === chosen) },
                h('span', { class: 'card-mark', 'aria-hidden': 'true' }, one.name.replace(/^@[^/]+\//, '').slice(0, 1).toUpperCase()),
                h(
                  'span',
                  { class: 'card-name' },
                  one.name,
                  one.name === data.flow ? h('span', { class: 'node-tag' }, 'Default') : null,
                  installed[one.name] ? h('span', { class: 'node-tag' }, installed[one.name].version) : null,
                  updates[one.name] ? h('span', { class: 'node-tag fresh' }, `${updates[one.name].to} out`) : null,
                ),
                one.about ? h('span', { class: 'card-about' }, one.about) : null,
              )
              card.addEventListener('click', () => show(one.name))
              const newEpic = hash(`/new?flow=${encodeURIComponent(one.name)}&workspace=${encodeURIComponent(workspace)}`)
              return menuOn(card, () => [
                { head: one.name },
                { label: 'New epic', glyph: 'new', href: newEpic },
                { label: 'Show', glyph: 'open', act: () => show(one.name) },
                '-',
                updates[one.name] ? { label: `Update to ${updates[one.name].to}`, glyph: 'download', act: () => change('/api/flowverses/install', { flow: one.name, version: updates[one.name].to }).catch((error) => toast(error.message)) } : null,
                one.name.startsWith('@local/') ? null : { label: 'Copy here', glyph: 'copy', act: () => change('/api/flows/fork', { flow: one.name, workspace }).catch((error) => toast(error.message)) },
                { label: 'Copy name', glyph: 'copy', act: () => copy(one.name, 'Name copied') },
              ])
            }),
          ),
        ),
      ),
    )
  }

  async function show(name) {
    chosen = name
    stays({ workspace, flow: name })
    for (const card of list.querySelectorAll('.card')) {
      card.classList.toggle('chosen', card.dataset.flow === name)
      card.setAttribute('aria-pressed', String(card.dataset.flow === name))
    }
    shown.hidden = false
    fill(shown, h('p', { class: 'loading', role: 'status' }, `Reading ${name}…`))
    let flow
    try {
      flow = await get(`/api/flow?name=${encodeURIComponent(name)}&workspace=${encodeURIComponent(workspace)}`)
    } catch (error) {
      if (chosen === name) fill(shown, problem(error))
      return
    }
    // Another flow was chosen while this one was read: what it says is no longer asked for.
    if (chosen !== name) return
    const installed = ((verses && verses.installed) || []).find((one) => one.flow === name)
    const update = ((verses && verses.updates) || []).find((one) => one.flow === name)
    const actions = [h('a', { class: 'btn primary', href: hash(`/new?flow=${encodeURIComponent(flow.name)}&workspace=${encodeURIComponent(workspace)}`) }, icon('new'), 'New epic')]
    if (update) actions.push(acting(`Update to ${update.to}`, () => change('/api/flowverses/install', { flow: name, version: update.to }), { busy: 'Updating…' }))
    if (!name.startsWith('@local/')) actions.push(acting('Copy here', () => change('/api/flows/fork', { flow: name, workspace }), { kind: 'btn quiet', busy: 'Copying…' }))
    if (installed) actions.push(confirming({ label: 'Uninstall', ask: `Uninstall ${name}?`, yes: 'Uninstall', no: 'Cancel', act: () => change('/api/flowverses/uninstall', { flow: name }) }))
    const params = Object.entries(flow.params.properties || {})
    fill(
      shown,
      h('header', {}, h('div', {}, h('div', { class: 'kicker' }, installed ? `${installed.verse} · ${installed.version}` : 'flow'), h('h2', {}, flow.name)), h('div', { class: 'row' }, actions)),
      flow.description ? h('p', { class: 'prose' }, flow.description) : null,
      h(
        'dl',
        { class: 'facts' },
        h('dt', {}, 'ref'),
        h('dd', { class: 'mono' }, flow.ref),
        h('dt', {}, 'resumable'),
        h('dd', {}, flow.resumable ? (flow.resumes ? 'yes, with an epic here to resume' : 'yes') : 'no'),
        h('dt', {}, 'agents'),
        h('dd', {}, flow.agents.length ? flow.agents.map((role) => h('div', {}, h('b', {}, role.name), role.auto ? h('span', { class: 'dim' }, ' (a person, answering here)') : null, role.harness ? [' ', h('span', { class: 'chip' }, role.harness)] : null, role.auto ? null : h('div', { class: 'dim' }, permitted(role.permission)))) : '—'),
        h('dt', {}, 'environments'),
        h('dd', {}, flow.envs.length ? flow.envs.map((role) => h('div', {}, h('b', {}, role.name), role.auto ? h('span', { class: 'dim' }, ' (this directory)') : null)) : '—'),
        h('dt', {}, 'params'),
        h('dd', {}, params.length ? params.map(([key, one]) => h('div', {}, h('b', { class: 'mono' }, key), one.description ? h('span', { class: 'dim' }, ` — ${one.description}`) : null)) : 'none'),
      ),
    )
  }

  // ------------------------------------------------------------------ flowverses

  function drawVerses(error) {
    if (!verses) {
      fill(list, error ? problem(error) : h('p', { class: 'loading' }, 'Reading the flowverses…'))
      return
    }
    fill(
      list,
      h(
        'div',
        { class: 'cards', 'data-hmz': 'verses' },
        verses.verses.map((one) => {
          const card = h(
            'button',
            { class: ['card', one.name === verse && 'chosen'], type: 'button', 'data-verse': one.name, 'aria-pressed': String(one.name === verse) },
            h('span', { class: 'card-mark', 'aria-hidden': 'true' }, one.name.slice(0, 1).toUpperCase()),
            h(
              'span',
              { class: 'card-name' },
              one.name,
              one.fixed ? h('span', { class: 'node-tag' }, 'Built in') : null,
              one.edited ? h('span', { class: 'node-tag' }, 'Edited') : null,
              !one.fetched ? h('span', { class: 'node-tag' }, 'Not fetched') : null,
            ),
            h('span', { class: 'card-about' }, one.url || 'local', one.installed ? ` · ${one.installed} installed` : ''),
          )
          // The one open closes when chosen again.
          card.addEventListener('click', () => (one.name === verse ? close() : openVerse(one.name)))
          return menuOn(card, () => [
            { head: one.url || one.name },
            { label: 'Open', glyph: 'open', act: () => openVerse(one.name) },
            !one.fixed || one.name === 'official' ? { label: 'Fetch', glyph: 'resume', act: () => change('/api/flowverses/fetch', { name: one.name }).catch((error) => toast(error.message)) } : null,
            one.url ? { label: 'Copy URL', glyph: 'copy', act: () => copy(one.url, 'URL copied') } : null,
          ])
        }),
        // Its form, too, closes when chosen again.
        h('button', { class: 'card card-add', type: 'button', 'data-hmz': 'add-verse', 'aria-pressed': String(adding()), onclick: (event) => {
          const was = adding()
          close()
          if (was) return
          event.currentTarget.setAttribute('aria-pressed', 'true')
          shown.hidden = false
          fill(shown, addVerse())
        } }, h('span', { class: 'card-mark', 'aria-hidden': 'true' }, icon('plus')), h('span', { class: 'card-name' }, 'Add flowverse')),
      ),
    )
  }

  /** Whether the form adding a flowverse is what is shown. */
  const adding = () => Boolean(shown.querySelector('[data-hmz=add-verse-form]'))

  /** Marks the card of the flowverse called `name` chosen, and no other: Add flowverse's neither. */
  function choose(name) {
    for (const card of list.querySelectorAll('.card[data-verse], [data-hmz=add-verse]')) {
      card.classList.toggle('chosen', card.dataset.verse === name)
      card.setAttribute('aria-pressed', String(card.dataset.verse === name))
    }
  }

  /** Shows no flowverse, and nothing in its place. */
  function close() {
    verse = ''
    stays({ tab: 'verses', workspace })
    choose('')
    shown.hidden = true
    fill(shown)
  }

  function addVerse() {
    const url = h('input', { type: 'text', placeholder: 'owner/repo or URL', 'aria-label': 'URL', required: true })
    const name = h('input', { type: 'text', placeholder: 'Name (optional)', 'aria-label': 'Name' })
    const form = h('form', { class: 'form', 'data-hmz': 'add-verse-form' }, h('h2', {}, 'Add flowverse'), h('div', { class: 'row' }, h('label', { class: 'field' }, h('span', { class: 'label' }, 'URL'), url), h('label', { class: 'field' }, h('span', { class: 'label' }, 'Name'), name)), h('div', { class: 'row' }, h('button', { class: 'btn primary', type: 'submit' }, 'Add')))
    form.addEventListener('submit', async (event) => {
      event.preventDefault()
      form.querySelector('.error')?.remove()
      const button = form.querySelector('button')
      button.disabled = true
      button.textContent = 'Adding…'
      try {
        const answer = await change('/api/flowverses', { url: url.value.trim(), name: name.value.trim() })
        const added = String(answer.said || '').replace(/^added /, '')
        if (added) openVerse(added)
      } catch (error) {
        form.append(problem(error))
      } finally {
        button.disabled = false
        button.textContent = 'Add'
      }
    })
    return form
  }

  async function openVerse(name) {
    verse = name
    stays({ tab: 'verses', workspace, verse: name })
    choose(name)
    shown.hidden = false
    fill(shown, h('p', { class: 'loading', role: 'status' }, `Reading ${name}…`))
    let index
    try {
      index = await get(`/api/flowverses/${encodeURIComponent(name)}`)
    } catch (error) {
      if (verse === name) fill(shown, problem(error))
      return
    }
    if (verse !== name) return
    const actions = []
    if (!index.fixed || name === 'official') actions.push(acting(index.fetched ? 'Fetch' : 'Fetch now', async () => {
      await change('/api/flowverses/fetch', { name })
      openVerse(name)
    }, { kind: 'btn', busy: 'Fetching…' }))
    if (!index.fixed) actions.push(confirming({ label: 'Remove', ask: `Remove ${name} and every flow installed out of it?`, yes: 'Remove', no: 'Cancel', act: async () => {
      await change('/api/flowverses/remove', { name })
      close()
    } }))
    fill(
      shown,
      h('header', {}, h('div', {}, h('div', { class: 'kicker' }, 'flowverse'), h('h2', {}, name)), h('div', { class: 'row' }, actions)),
      h('p', { class: 'dim mono' }, index.url || 'local'),
      index.edited ? h('p', { class: 'note' }, 'Something is written into it: fetching resets it to what its repository says.') : null,
      index.flows.length
        ? h('div', { class: 'releases', 'data-hmz': 'index' }, index.flows.map((one) => release(name, one)))
        : h('p', { class: 'dim' }, index.fetched ? 'Its index lists no flow.' : 'Fetch it to see what it lists.'),
      index.skipped.length
        ? h('details', {}, h('summary', {}, `${index.skipped.length} skipped`), h('ul', { class: 'tree' }, index.skipped.map((one) => h('li', {}, h('span', { class: 'mono' }, one.at), h('div', { class: 'dim' }, one.why)))))
        : null,
    )
  }

  function release(name, one) {
    const pick = h(
      'select',
      { 'aria-label': `Release of ${one.listed}` },
      one.releases.map((each) => h('option', { value: each.version, selected: each.version === one.installed }, `${each.version}${each.prerelease ? ' (pre)' : ''}${each.version === one.installed ? ' ✓' : ''}`)),
    )
    const newest = one.releases.find((each) => !each.prerelease) || one.releases[0]
    if (!one.installed && newest) pick.value = newest.version
    const go = acting(one.installed ? 'Switch' : 'Install', async () => {
      await change('/api/flowverses/install', { flow: one.flow, version: pick.value })
      openVerse(name)
    }, { kind: 'btn small', busy: 'Installing…' })
    const remove = one.installed ? confirming({ label: 'Uninstall', ask: `Uninstall ${one.flow}?`, yes: 'Uninstall', no: 'Cancel', small: true, act: async () => {
      await change('/api/flowverses/uninstall', { flow: one.flow })
      openVerse(name)
    } }) : null
    const about = (one.releases.find((each) => each.version === (one.installed || (newest && newest.version))) || {}).description
    return h(
      'div',
      { class: 'release', 'data-hmz': 'release', 'data-flow': one.flow },
      h('div', {}, h('b', {}, one.listed), one.installed ? h('span', { class: 'node-tag' }, `${one.installed} installed`) : null, about ? h('div', { class: 'dim' }, about) : null),
      h('div', { class: 'row' }, pick, go, remove),
    )
  }

  watch()
  return () => {
    stop()
    stopVerses()
  }
}
