// The flows, in the two pages `/flow` opens on in the terminal interface. Installed: a card for
// each flow on offer on the daemon, by where it came from, each installed out of an index with
// its release and any newer one -- and, one opened, what it declares, with starting it, updating
// it and uninstalling it. The page is the daemon's and no folder's: it names, picks and depends
// on no workspace, and a workspace an address names is left out of it. Flowverses: a tab for
// every index flows are installed out of, fetched or written into -- not a project's flows or
// yours, which are no index -- the first open with no press, showing every flow it lists, every
// release of each, installing, switching and uninstalling one; with adding, fetching and
// removing one. What a card or a tab opens stands under them, so that none moves. Where there
// is nothing to list, the page says so and offers what gets something there (Section 3.4.6 of
// protocol/web.md).

import { call, given, hash, poll, refresh } from '../api.js'
import { stays } from '../app.js'
import { confirming } from '../confirm.js'
import { acting, empty, fill, h, icon, iconButton, permitted, problem } from '../dom.js'
import { t } from '../i18n.js'
import { harnessName, verseName } from '../names.js'
import { bar, picks, tabbed } from '../shell.js'
import { copy, menuOn, toast } from '../ui.js'

export function mount(root, { query }) {
  let tab = query.get('tab') === 'verses' ? 'verses' : 'installed'
  let chosen = query.get('flow') || ''
  let verse = query.get('verse') || ''
  const tabs = h('div', { class: 'flows-tabs' })
  const said = h('div', { class: 'flows-said', 'aria-live': 'polite' })
  const list = h('div', { class: 'gallery', 'data-hmz': 'flows' }, h('p', { class: 'loading', role: 'status' }, t('Reading the flows…')))
  const shown = h('section', { class: 'flow-detail', 'aria-live': 'polite', hidden: true })
  fill(
    root,
    h(
      'div',
      { class: 'view' },
      bar({ title: t('Flows') }),
      h('div', { class: 'view-scroll' }, h('div', { class: 'view-pad wide' }, tabs, said, list, shown)),
    ),
  )

  /** Every flowverse, what is installed out of them, and the newer releases there are. */
  let verses = null
  let stop = () => {}
  let stopVerses = () => {}

  const watch = () => {
    stop()
    stopVerses()
    stays({ tab: tab === 'verses' ? 'verses' : '', flow: tab === 'installed' ? chosen : '', verse: tab === 'verses' ? verse : '' })
    // Picked by the keys, a tab is drawn again: the focus stays on it.
    const held = tabs.contains(document.activeElement)
    fill(tabs, tabbed([['installed', t('Installed')], ['verses', t('Flowverses')]], tab, (key) => {
      tab = key
      watch()
    }))
    if (held) tabs.querySelector('[aria-selected=true]').focus()
    stopVerses = poll('flowverses.list', {}, 30000, (data, error) => {
      if (data) verses = data
      drawUpdates(error)
      if (tab === 'verses') drawVerses(error)
    })
    if (tab === 'installed') {
      stop = poll('flows.list', {}, 30000, drawFlows)
      if (chosen) show(chosen)
      else open()
    } else {
      stop = () => {}
      // The one the address names, or the first: the tabs, once read, open that one.
      if (verse) openVerse(verse)
      else if (verses) openVerse(verses.verses[0].name)
      else put()
    }
  }

  /** Puts what a card or a tab opened under them, or, of nothing, nothing: where the view is, unmoved. */
  function put(...made) {
    shown.hidden = !made.length
    fill(shown, ...made)
  }

  /**
   * Shows what a card opened, scrolled no further than it takes to be seen, nor so far that the
   * card it was opened from leaves the view.
   */
  function open(...made) {
    put(...made)
    if (!made.length) return
    const scroller = shown.closest('.view-scroll')
    const view = scroller.getBoundingClientRect()
    const box = shown.getBoundingClientRect()
    const card = list.querySelector('.card[aria-pressed=true]')
    const needed = Math.min(box.top - view.top, box.bottom - view.bottom)
    // How far under the view's top its card is, where the card is in the view to be kept there.
    const kept = card ? card.getBoundingClientRect().top - view.top : -1
    scroller.scrollTop += Math.max(0, kept < 0 ? needed : Math.min(needed, kept))
  }

  /** Says what changed -- in the page's words where it has them, else the daemon's -- and reads again what it changed. */
  async function change(method, body, done = '') {
    const answer = await call(method, given(body))
    fill(said, h('p', { class: 'note', role: 'status' }, done || answer.said || t('Done.')))
    refresh('flowverses.list')
    refresh('flows.list')
    return answer
  }

  /** What a card's menu does, said while it goes: then what changed, or a toast of why not. */
  function busy(doing, method, body, done) {
    fill(said, said.querySelector('[data-hmz=update-banner]'), h('p', { class: 'loading', role: 'status', 'data-hmz': 'busy' }, doing))
    change(method, body, done).catch((error) => {
      said.querySelector('[data-hmz=busy]')?.remove()
      toast(error.message)
    })
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
        h('b', {}, t('{n} updates', { n: updates.length })),
        ' ',
        updates.map((one) => h('span', { class: 'chip' }, `${one.flow} ${one.from} → ${one.to}`)),
      ),
    )
  }

  // ------------------------------------------------------------------ installed

  /** Where an epic of the flow is started. */
  const newEpic = (flow) => hash(`/new?flow=${encodeURIComponent(flow)}`)

  /** Opens `Flowverses`, where a flow is installed from. */
  const browse = () => {
    tab = 'verses'
    chosen = ''
    watch()
    tabs.querySelector('[aria-selected=true]')?.focus()
  }

  function drawFlows(data, error) {
    if (!data) {
      fill(list, error ? problem(error) : h('p', { class: 'loading' }, t('Reading the flows…')))
      return
    }
    const installed = Object.fromEntries(((verses && verses.installed) || []).map((one) => [one.flow, one]))
    const updates = Object.fromEntries(((verses && verses.updates) || []).map((one) => [one.flow, one]))
    if (!data.flows.length) {
      fill(
        list,
        empty(
          t('No flows installed yet.'),
          t(' A flow is what an epic runs. Install one from a flowverse.'),
          h('button', { class: 'btn primary', type: 'button', 'data-hmz': 'flows-browse', onclick: browse }, t('Browse Flowverses')),
        ),
      )
      return
    }
    const whose = {}
    for (const one of data.flows) (whose[one.whose] ||= []).push(one)
    fill(
      list,
      Object.entries(whose).map(([from, flows]) =>
        h(
          'section',
          { class: 'gallery-group' },
          h('h2', { class: 'kicker' }, verseName(from)),
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
                  installed[one.name] ? h('span', { class: 'node-tag' }, installed[one.name].version) : null,
                  updates[one.name] ? h('span', { class: 'node-tag fresh' }, t('{version} out', { version: updates[one.name].to })) : null,
                ),
                one.about ? h('span', { class: 'card-about' }, one.about) : null,
              )
              card.addEventListener('click', () => show(one.name))
              return menuOn(card, () => [
                { head: one.name },
                { label: t('New epic'), glyph: 'new', href: newEpic(one.name) },
                { label: t('Show'), glyph: 'open', act: () => show(one.name) },
                '-',
                updates[one.name] ? { label: t('Update to {version}', { version: updates[one.name].to }), glyph: 'download', act: () => busy(t('Updating {name}…', { name: one.name }), 'flowverses.install', { flow: one.name, version: updates[one.name].to }) } : null,
                { label: t('Copy name'), glyph: 'copy', act: () => copy(one.name, t('Name copied')) },
              ])
            }),
          ),
        ),
      ),
    )
  }

  async function show(name) {
    chosen = name
    stays({ flow: name })
    for (const card of list.querySelectorAll('.card')) {
      card.classList.toggle('chosen', card.dataset.flow === name)
      card.setAttribute('aria-pressed', String(card.dataset.flow === name))
    }
    put(h('p', { class: 'loading', role: 'status' }, t('Reading {name}…', { name })))
    let flow
    try {
      flow = await call('flows.get', { name })
    } catch (error) {
      if (chosen === name) open(problem(error))
      return
    }
    // Another flow was chosen while this one was read: what it says is no longer asked for.
    if (chosen !== name) return
    const installed = ((verses && verses.installed) || []).find((one) => one.flow === name)
    const update = ((verses && verses.updates) || []).find((one) => one.flow === name)
    const actions = [h('a', { class: 'btn primary', href: newEpic(flow.name) }, icon('new'), t('New epic'))]
    if (update) actions.push(acting(t('Update to {version}', { version: update.to }), () => change('flowverses.install', { flow: name, version: update.to }), { busy: t('Updating…') }))
    if (installed) actions.push(confirming({ label: t('Uninstall'), ask: t('Uninstall {name}?', { name }), yes: t('Uninstall'), no: t('Cancel'), act: () => change('flowverses.uninstall', { flow: name }) }))
    const params = Object.entries(flow.params.properties || {})
    open(
      h('header', {}, h('div', {}, h('div', { class: 'kicker' }, installed ? `${verseName(installed.verse)} · ${installed.version}` : t('flow')), h('h2', {}, flow.name)), h('div', { class: 'row' }, actions)),
      flow.description ? h('p', { class: 'prose' }, flow.description) : null,
      h(
        'dl',
        { class: 'facts' },
        h('dt', {}, t('ref')),
        h('dd', { class: 'mono' }, flow.ref),
        h('dt', {}, t('resumable')),
        h('dd', {}, flow.resumable ? t('yes') : t('no')),
        h('dt', {}, t('agents')),
        h('dd', {}, flow.agents.length ? flow.agents.map((role) => h('div', {}, h('b', {}, role.name), role.auto ? h('span', { class: 'dim' }, t(' (a person, answering here)')) : null, role.harness ? [' ', h('span', { class: 'chip', title: role.harness }, harnessName(role.harness))] : null, role.auto ? null : h('div', { class: 'dim' }, permitted(role.permission)))) : '—'),
        h('dt', {}, t('environments')),
        h('dd', {}, flow.envs.length ? flow.envs.map((role) => h('div', {}, h('b', {}, role.name), role.auto ? h('span', { class: 'dim' }, t(' (the folder the epic runs in)')) : null)) : '—'),
        h('dt', {}, t('params')),
        h('dd', {}, params.length ? params.map(([key, one]) => h('div', {}, one.title ? h('b', { title: key }, one.title) : h('b', { class: 'mono' }, key), one.description ? h('span', { class: 'dim' }, ` — ${one.description}`) : null)) : t('none')),
      ),
    )
  }

  // ------------------------------------------------------------------ flowverses

  function drawVerses(error) {
    if (!verses) {
      fill(list, error ? problem(error) : h('p', { class: 'loading' }, t('Reading the flowverses…')))
      return
    }
    // A tab says the name alone: where one is fetched from, and what state it is in, is said
    // once, in what it opens.
    const row = tabbed(verses.verses.map((one) => [one.name, verseName(one.name)]), verse, openVerse)
    row.classList.add('verse-tabs')
    row.setAttribute('aria-label', t('Flowverses'))
    row.dataset.hmz = 'verses'
    verses.verses.forEach((one, at) => {
      const tab = row.children[at]
      tab.dataset.verse = one.name
      tab.id = `verse-tab-${at}`
      // A long name is cut short on its tab, and said whole where it is pointed at.
      tab.title = verseName(one.name)
      menuOn(tab, () => [
        { head: one.url || verseName(one.name) },
        { label: t('Open'), glyph: 'open', act: () => openVerse(one.name) },
        !one.fixed || one.name === 'official' ? { label: t('Fetch'), glyph: 'resume', act: () => busy(t('Fetching {name}…', { name: verseName(one.name) }), 'flowverses.fetch', { name: one.name }, fetched(one.name)) } : null,
        one.url ? { label: t('Copy URL'), glyph: 'copy', act: () => copy(one.url, t('URL copied')) } : null,
      ])
    })
    // Its form closes when chosen again, onto the first flowverse.
    const add = iconButton('plus', t('Add flowverse'), { 'data-hmz': 'add-verse', 'aria-pressed': String(adding()), onclick: () => {
      if (adding()) return openVerse(verses.verses[0].name)
      verse = ''
      stays({ tab: 'verses' })
      choose('')
      add.setAttribute('aria-pressed', 'true')
      put(addVerse())
    } })
    fill(list, h('div', { class: 'verse-bar' }, row, add))
    labelled()
    // No press is asked for: the first is open, save where the form adding one is -- and in
    // place of one the address names that is not listed.
    if (!adding() && (!verse || (missed === verse && !listed(verse)))) openVerse(verses.verses[0].name)
  }

  /** Whether a flowverse of a name is among those listed. */
  const listed = (name) => verses.verses.some((one) => one.name === name)
  /** The flowverse asked for last that could not be read. */
  let missed = ''
  /** What is said once a flowverse is fetched, by the name the page gives it. */
  const fetched = (name) => t('Fetched {name}.', { name: verseName(name) })

  /** Says what is under the tabs is the panel of the tab picked, where one is. */
  function labelled() {
    const tab = list.querySelector('[role=tab][data-verse][aria-selected=true]')
    if (tab) {
      shown.setAttribute('role', 'tabpanel')
      shown.setAttribute('aria-labelledby', tab.id)
    } else {
      shown.removeAttribute('role')
      shown.removeAttribute('aria-labelledby')
    }
  }

  /** Whether the form adding a flowverse is what is shown. */
  const adding = () => Boolean(shown.querySelector('[data-hmz=add-verse-form]'))

  /** Marks the tab of the flowverse called `name` picked, and no other: Add flowverse's neither. */
  function choose(name) {
    const row = list.querySelector('[data-hmz=verses]')
    if (row) picks(row, name)
    labelled()
    list.querySelector('[data-hmz=add-verse]')?.setAttribute('aria-pressed', 'false')
  }

  function addVerse() {
    const url = h('input', { type: 'text', placeholder: t('owner/repo or URL'), 'aria-label': t('URL'), required: true })
    const name = h('input', { type: 'text', placeholder: t('Name (optional)'), 'aria-label': t('Name') })
    const form = h('form', { class: 'form', 'data-hmz': 'add-verse-form' }, h('h2', {}, t('Add flowverse')), h('div', { class: 'row' }, h('label', { class: 'field' }, h('span', { class: 'label' }, t('URL')), url), h('label', { class: 'field' }, h('span', { class: 'label' }, t('Name')), name)), h('div', { class: 'row' }, h('button', { class: 'btn primary', type: 'submit' }, t('Add'))))
    form.addEventListener('submit', async (event) => {
      event.preventDefault()
      form.querySelector('.error')?.remove()
      const button = form.querySelector('button')
      button.disabled = true
      button.textContent = t('Adding…')
      try {
        const answer = await change('flowverses.add', { url: url.value.trim(), name: name.value.trim() })
        const added = String(answer.said || '').replace(/^added /, '')
        if (added) openVerse(added)
      } catch (error) {
        form.append(problem(error))
      } finally {
        button.disabled = false
        button.textContent = t('Add')
      }
    })
    return form
  }

  // What a tab opens stands right under the tabs, and is put there unscrolled: it is there on
  // arrival, and a long index must not carry the tabs out of the view.
  async function openVerse(name) {
    verse = name
    missed = ''
    stays({ tab: 'verses', verse: name })
    choose(name)
    put(h('p', { class: 'loading', role: 'status' }, t('Reading {name}…', { name: verseName(name) })))
    let index
    try {
      index = await call('flowverses.get', { name })
    } catch (error) {
      if (verse !== name) return
      // One that is not listed gives way to the first, at once or once they are read.
      if (verses && !listed(name)) return openVerse(verses.verses[0].name)
      missed = name
      put(problem(error))
      return
    }
    if (verse !== name) return
    // Fetching it again is the arrow right after its name: busy itself while it goes, and said
    // so where nothing moves for it, so that the arrow stays under what pressed it.
    const fetching = !index.fixed || name === 'official' ? iconButton('resume', t('Fetch'), { 'data-hmz': 'fetch-verse' }) : null
    const going = h('span', { class: 'sr-only', role: 'status', 'data-hmz': 'fetching-verse' })
    fetching?.addEventListener('click', async () => {
      if (fetching.getAttribute('aria-busy')) return
      fetching.setAttribute('aria-busy', 'true')
      going.textContent = t('Fetching {name}…', { name: verseName(name) })
      try {
        await change('flowverses.fetch', { name }, fetched(name))
        if (verse !== name) return
        // What it opened is drawn again, the arrow with it: the focus it held stays on it.
        const held = document.activeElement === fetching
        await openVerse(name)
        if (held && verse === name) shown.querySelector('[data-hmz=fetch-verse]')?.focus()
      } catch (error) {
        toast(error.message)
      } finally {
        going.textContent = ''
        fetching.removeAttribute('aria-busy')
      }
    })
    const remove = index.fixed ? null : confirming({ label: t('Remove'), ask: t('Remove {name} and every flow installed out of it?', { name }), yes: t('Remove'), no: t('Cancel'), act: async () => {
      await change('flowverses.remove', { name })
      // The first is Humanize's own, which is never removed.
      openVerse(verses.verses[0].name)
    } })
    // Nothing listed: fetched, it lists none, and another flowverse may; else it is yet to be
    // fetched, which the arrow by its name does, pressed from here.
    const adds = () => {
      list.querySelector('[data-hmz=add-verse]')?.click()
      shown.querySelector('[data-hmz=add-verse-form] input')?.focus()
    }
    // The arrow takes the focus, and keeps it once what it fetched is drawn.
    const fetches = () => {
      fetching.focus()
      fetching.click()
    }
    const nothing = () =>
      index.fetched || !fetching
        ? empty(
            t('This flowverse lists no flow.'),
            t(' Add another flowverse to find more.'),
            h('button', { class: 'btn', type: 'button', 'data-hmz': 'verse-add', onclick: adds }, t('Add flowverse')),
          )
        : empty(
            t('Not fetched yet.'),
            t(' Fetch this flowverse to see what it lists.'),
            h('button', { class: 'btn primary', type: 'button', 'data-hmz': 'verse-fetch', onclick: fetches }, t('Fetch')),
          )
    put(
      h('header', {}, h('div', { class: 'verse-head' }, h('h2', { title: verseName(name) }, verseName(name)), fetching, fetching ? going : null), remove ? h('div', { class: 'row' }, remove) : null),
      h('p', { class: 'dim mono' }, index.url || t('local')),
      index.edited ? h('p', { class: 'note' }, t('Something is written into it: fetching resets it to what its repository says.')) : null,
      index.flows.length
        ? h('div', { class: 'releases', 'data-hmz': 'index' }, index.flows.map((one) => release(name, one)))
        : nothing(),
      index.skipped.length
        ? h('details', {}, h('summary', {}, t('{n} skipped', { n: index.skipped.length })), h('ul', { class: 'tree' }, index.skipped.map((one) => h('li', {}, h('span', { class: 'mono' }, one.at), h('div', { class: 'dim' }, one.why)))))
        : null,
    )
  }

  function release(name, one) {
    const pick = h(
      'select',
      { 'aria-label': t('Release of {name}', { name: one.listed }) },
      one.releases.map((each) => h('option', { value: each.version, selected: each.version === one.installed }, `${each.prerelease ? t('{version} (pre)', { version: each.version }) : each.version}${each.version === one.installed ? ' ✓' : ''}`)),
    )
    const newest = one.releases.find((each) => !each.prerelease) || one.releases[0]
    if (!one.installed && newest) pick.value = newest.version
    const go = acting(one.installed ? t('Switch') : t('Install'), async () => {
      await change('flowverses.install', { flow: one.flow, version: pick.value })
      openVerse(name)
    }, { kind: 'btn small', busy: t('Installing…') })
    const remove = one.installed ? confirming({ label: t('Uninstall'), ask: t('Uninstall {name}?', { name: one.flow }), yes: t('Uninstall'), no: t('Cancel'), small: true, act: async () => {
      await change('flowverses.uninstall', { flow: one.flow })
      openVerse(name)
    } }) : null
    const about = (one.releases.find((each) => each.version === (one.installed || (newest && newest.version))) || {}).description
    return h(
      'div',
      { class: 'release', 'data-hmz': 'release', 'data-flow': one.flow },
      h('div', {}, h('b', {}, one.listed), one.installed ? h('span', { class: 'node-tag' }, t('{version} installed', { version: one.installed })) : null, about ? h('div', { class: 'dim' }, about) : null),
      // The release and what installs it end the line, whatever else it offers standing before them.
      h('div', { class: 'row' }, remove, pick, go),
    )
  }

  watch()
  return () => {
    stop()
    stopVerses()
  }
}
