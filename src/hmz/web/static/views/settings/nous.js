// Every nous: a concrete one, `HARNESS[@ACCOUNT]/MODEL[:EFFORT]`, or a virtual one, a name
// standing for a graph of other nous. A concrete nous is never made here: it is found by the
// daemon asking the harnesses installed what they run, as it starts and whenever `Scan` is
// pressed, and every one found is listed under its harness. A virtual nous is made, renamed and
// removed here. Each says how many more goes a failed turn has there, how it waits between them,
// how long it may take at most, and the graph a turn goes to once those are spent (`then`). A
// graph is a start and its nodes: a use node names one nous, a balance node picks among several
// by a strategy, and each node's edges say, by fault class or `*`, which node a turn goes to
// once it fails there.

import { confirming } from '../../confirm.js'
import { nousNamed } from '../../chips/agent.js'
import { modelChip } from '../../chips/model.js'
import { acting, fill, h, iconButton, lasting, problem } from '../../dom.js'
import { pieces, t } from '../../i18n.js'
import { effortName, harnessName, modelName } from '../../names.js'
import { batched, found, freshId, graphSaid, held, removed, renamed, wayName, written } from '../../nous.js'
import { anyCli, parted, readBackends } from '../../pickers.js'

/** How many nous a harness lists before its group opens folded, and how many there are before they are searched. */
const MANY = 12

/** How long after a scan the daemon makes by itself is found going the list is read again, ms. */
const AGAIN = 2000

export function draw(holder, query, parts, scope) {
  const listing = h('section', { class: 'panel', 'data-hmz': 'nous' }, h('p', { class: 'loading', role: 'status' }, t('Reading the nous…')))
  const writing = h('section', { class: 'panel', 'data-hmz': 'write-nous' })
  fill(holder, listing, writing)
  let data = null
  let backends = null
  let editing = null
  let renaming = null
  /** Who a scan asked for here could not ask, once one has ended: null before any. */
  let failed = null
  /** The chips of the form drawn, each left as the form is drawn again. */
  let chips = []
  let reading = 0
  let gone = false

  /** Draws the list of what the daemon answered, and reads it again while a scan of its own is going. */
  const listed = (answer) => {
    data = answer
    drawListing()
    clearTimeout(reading)
    if (data.scanning && !gone) reading = setTimeout(() => read().catch(() => {}), AGAIN)
  }

  const shown = (answer) => {
    listed(answer)
    drawWriting()
  }

  /** Reads the nous and the harnesses again: the form, once drawn, is left as it is written. */
  const read = async () => {
    const [answer, clis] = await Promise.all([scope.call('nous.list'), readBackends(undefined, scope.name).catch(() => backends)])
    if (gone) return
    backends = clis
    if (data) listed(answer)
    else shown(answer)
  }

  /**
   * What is said, in pieces that may each be held whole on a line: its words, and of a nous
   * what is before its `/`, its model, and its effort -- so that one is never broken at a hyphen.
   */
  const worded = (said) =>
    String(said)
      .split(' ')
      .flatMap((word, at) => [at ? ' ' : null, word.split(/(?<=\/)|(?=:)/).map((part, n) => [n ? h('wbr') : null, h('span', { 'data-hmz': 'nous-word' }, part)])])

  /**
   * Holds every such piece of the table drawn whole while the table has room for them all.
   * Where it has not, they break where they must, as they would unheld: the table does not
   * scroll for them.
   */
  function fit(wrap) {
    const words = wrap.querySelectorAll('[data-hmz=nous-word]')
    let wide = -1
    const hold = () => {
      if (wrap.clientWidth === wide) return
      wide = wrap.clientWidth
      for (const word of words) word.style.whiteSpace = 'nowrap'
      if (wrap.scrollWidth > wide) for (const word of words) word.style.whiteSpace = ''
    }
    hold()
    // Again once it is as wide as it was not, a frame on: holding them lays the table out anew.
    new ResizeObserver(() => requestAnimationFrame(hold)).observe(wrap)
  }

  /** A graph as a cell says it: a line per node from the start, or what none means. */
  const graphCell = (graph, none) =>
    graph
      ? graphSaid(graph, nousNamed).map((one) =>
          h(
            'div',
            { 'data-hmz': 'nous-node', title: graphSaid(graph).find((each) => each.id === one.id).text },
            h('span', { class: 'dim' }, one.start ? t('{id} (start): ', { id: one.id }) : `${one.id}: `),
            h('span', {}, worded(one.text)),
            one.edges ? h('span', { class: 'dim' }, ` · ${one.edges}`) : null,
          ),
        )
      : h('span', { class: 'dim' }, none)

  /** How one nous is tried again: said of one nothing is written of as of one tried once. */
  const tried = (one) => [
    one && one.tries ? t('{n} more goes, {policy}', { n: one.tries, policy: wayName('policy', one.policy).name }) : h('span', { class: 'dim' }, t('once')),
    h('div', { class: 'dim' }, one && one.timeout ? t('at most {time}', { time: lasting(one.timeout) }) : t('no limit')),
  ]

  /** A concrete nous as its row names it under its harness: its model, then its account and its effort where it names either. */
  function modelSaid(name) {
    const { account, model, effort } = parted(name)
    return [modelName(model), account && `@${account}`, effort && effort !== 'auto' && effortName(effort)].filter(Boolean).join(' · ')
  }

  /** What is said of the scan: that one is going, who the last would not answer, and what there is. */
  function scanned(groups) {
    const total = groups.reduce((n, group) => n + group.rows.length, 0)
    const count = groups.length ? t('{n} concrete nous of {m} harnesses.', { n: total, m: groups.length }) : t('No harness is installed on this daemon.')
    return h(
      'p',
      { class: 'dim', role: 'status', 'data-hmz': 'nous-scanned' },
      data.scanning ? t('Scanning the harnesses in the background…') : count,
      failed && failed.length
        ? failed.map((one) => h('span', { class: 'bad', 'data-hmz': 'nous-scan-failed' }, ' ', t('{harness} would not answer: {why}', { harness: one.account ? `${harnessName(one.cli)} @${one.account}` : harnessName(one.cli), why: one.why })))
        : null,
    )
  }

  function drawListing() {
    const virtual = data.nous.filter((one) => one.virtual)
    const groups = found(data, backends ? Object.keys(backends.clis) : [])
    const total = groups.reduce((n, group) => n + group.rows.length, 0)
    const rows = virtual.map((one) =>
      h(
        'tr',
        { 'data-hmz': 'nous-row', 'data-name': one.name },
        h('td', {}, h('div', { title: one.name }, worded(one.name))),
        h('td', { 'data-label': t('Tried') }, tried(one)),
        h('td', { 'data-label': t('Graph') }, graphCell(one.graph, '—')),
        h('td', { 'data-label': t('Then') }, graphCell(one.then, t('nowhere'))),
        h('td', {}, renaming === one.name ? renameForm(one) : actions(one)),
      ),
    )
    const scan = acting(
      t('Scan'),
      async () => {
        const answer = await scope.call('nous.scan')
        failed = answer.failed
        backends = await readBackends(undefined, scope.name).catch(() => backends)
        if (!gone) shown(answer)
      },
      { kind: 'btn small', busy: t('Scanning…') },
    )
    scan.firstChild.dataset.hmz = 'nous-scan'
    scan.firstChild.title = t('Ask every harness installed what it runs')
    const none = h('p', { class: 'dim', role: 'status', hidden: true }, t('No nous matches'))
    const folds = groups.map((group) => harnessFold(group))
    const find = h('input', { type: 'search', class: 'nous-find', placeholder: t('Find a nous'), 'aria-label': t('Find a nous'), 'data-hmz': 'nous-find', spellcheck: 'false', autocomplete: 'off' })
    find.addEventListener('input', () => {
      const typed = find.value.trim().toLowerCase()
      let any = false
      for (const fold of folds) {
        let mine = false
        for (const row of fold.querySelectorAll('[data-hmz=concrete-row]')) {
          row.hidden = Boolean(typed) && !`${row.dataset.name} ${row.textContent}`.toLowerCase().includes(typed)
          mine ||= !row.hidden
        }
        fold.hidden = Boolean(typed) && !mine
        // What is looked for is shown where it is found; nothing looked for, each as it stood.
        fold.open = typed ? mine : fold.dataset.open === 'true'
        any ||= !fold.hidden
      }
      none.hidden = any
    })
    fill(
      listing,
      // Each nous written whole over the one of its name there, or added; none there taken away.
      h('header', {}, h('h2', {}, t('Nous')), h('span', { class: 'row' }, scan, h('button', { class: 'btn small primary', type: 'button', 'data-hmz': 'nous-add', onclick: () => edit(null) }, t('New virtual nous')), scope.batch(() => batched(data.nous)))),
      scanned(groups),
      h('h3', { class: 'nous-part' }, t('Virtual')),
      rows.length
        ? h('div', { class: 'table-wrap', 'data-hmz': 'nous-virtual' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, t('Name')), h('th', {}, t('Tried')), h('th', {}, t('Graph')), h('th', {}, t('Then')), h('th', {}, ''))), h('tbody', {}, rows)))
        : h('p', { class: 'hint', 'data-hmz': 'nous-no-virtual' }, t('None yet. A virtual nous is a name for a graph of other nous: a turn that fails there is tried again, on the same model or on another.')),
      h('h3', { class: 'nous-part' }, t('Concrete')),
      h('p', { class: 'hint' }, t('Found by asking each harness what it runs, never made by hand. What is written of one says how a turn that fails there is tried again.')),
      total > MANY ? find : null,
      folds,
      none,
    )
    if (rows.length) fit(listing.querySelector('.table-wrap'))
  }

  /** One harness and every concrete nous of it, folded away where they are many and nothing is written of any. */
  function harnessFold(group) {
    const some = group.rows.some((one) => one.written)
    const open = some || group.rows.length <= MANY
    const asked = backends && backends.clis[group.cli] ? backends.clis[group.cli].accounts.some((one) => one.asked) : true
    return h(
      'details',
      { class: 'fold nous-harness', 'data-hmz': 'nous-harness', 'data-cli': group.cli, 'data-open': String(open), open },
      h('summary', {}, h('b', {}, harnessName(group.cli)), h('span', { class: 'dim' }, group.rows.length ? t('{n} models', { n: group.rows.length }) : asked ? t('No models listed') : t('Not asked yet'))),
      group.rows.length
        ? h(
            'div',
            { class: 'table-wrap' },
            h(
              'table',
              {},
              h('thead', {}, h('tr', {}, h('th', {}, t('Model')), h('th', {}, t('Tried')), h('th', {}, t('Then')), h('th', {}, ''))),
              h(
                'tbody',
                {},
                group.rows.map((one) =>
                  h(
                    'tr',
                    { 'data-hmz': 'concrete-row', 'data-name': one.name },
                    h('td', {}, h('div', { title: one.name }, modelSaid(one.name))),
                    h('td', { 'data-label': t('Tried') }, tried(one.written)),
                    h('td', { 'data-label': t('Then') }, graphCell(one.written && one.written.then, t('nowhere'))),
                    h('td', {}, actions(one.written || { name: one.name, virtual: false, unwritten: true })),
                  ),
                ),
              ),
            ),
          )
        : null,
    )
  }

  function actions(one) {
    return h(
      'div',
      { class: 'row' },
      h('button', { class: 'btn small quiet', type: 'button', 'data-hmz': 'nous-edit', onclick: () => edit(one) }, t('Edit')),
      one.virtual ? h('button', { class: 'btn small quiet', type: 'button', 'data-hmz': 'nous-rename', onclick: () => ((renaming = one.name), drawListing()) }, t('Rename')) : null,
      // A concrete nous stays listed, as its harness runs it: what is written of it is what goes.
      one.unwritten
        ? null
        : confirming({
            label: one.virtual ? t('Remove') : t('Reset'),
            ask: one.virtual ? t('Remove {name}?', { name: one.name }) : t('Forget what is written of {name}?', { name: nousNamed(one.name) }),
            yes: one.virtual ? t('Remove') : t('Reset'),
            small: true,
            act: async () => {
              const answer = await scope.call('nous.clear', { name: one.name })
              if (editing && editing.name === one.name) editing = null
              shown(answer)
            },
          }),
    )
  }

  function renameForm(one) {
    const to = h('input', { type: 'text', value: one.name, 'aria-label': t('New name for {name}', { name: one.name }), 'data-hmz': 'nous-rename-to', spellcheck: 'false' })
    return h(
      'div',
      { class: 'row' },
      to,
      acting(t('Rename'), async () => {
        const answer = await scope.call('nous.rename', { name: one.name, to: to.value.trim() })
        if (editing && editing.name === one.name) editing = null
        renaming = null
        shown(answer)
      }, { kind: 'btn small primary', busy: t('Renaming…') }),
      h('button', { class: 'btn small quiet', type: 'button', onclick: () => ((renaming = null), drawListing()) }, t('Cancel')),
    )
  }

  function edit(one) {
    editing = one
    drawWriting()
    writing.scrollIntoView({ behavior: 'smooth', block: 'start' })
    // A new one starts at its first field; one edited is read first.
    if (!one) writing.querySelector('input:not([disabled]), select:not([disabled])')?.focus({ preventScroll: true })
  }

  /**
   * A select of ways -- of waiting, or of picking -- each by its short name, and the line that
   * explains the one chosen, which stands by the select and follows it.
   */
  function ways(kind, offered, value, props, changed = () => {}) {
    // What is written is kept, though the daemon no longer offers it.
    const all = offered.some((one) => one.name === value) || !value ? offered : [...offered, { name: value }]
    const select = h('select', props, all.map((one) => h('option', { value: one.name, selected: one.name === value }, wayName(kind, one).name)))
    const about = h('p', { class: 'hint way-about', 'data-hmz': `${kind}-about`, 'aria-live': 'polite' })
    const say = () => (about.textContent = wayName(kind, all.find((one) => one.name === select.value) || select.value).about)
    select.addEventListener('change', () => {
      say()
      changed(select.value)
    })
    say()
    return { select, about }
  }

  function drawWriting() {
    for (const one of chips) one.leave()
    chips = []
    const was = editing || { name: '', virtual: true, tries: 0, policy: data.default, timeout: 0, graph: null, then: null }
    // A new nous is a virtual one: a concrete one is found, not made.
    const name = editing ? null : h('input', { type: 'text', id: 'nous-name', placeholder: t('A name, as fast or careful'), 'data-hmz': 'nous-name', spellcheck: 'false' })
    const graph = graphForm(t('Graph'), 'graph', held(was.graph), was.name)
    const then = graphForm(t('Then'), 'then', held(was.then), was.name)
    const tries = h('input', { type: 'number', id: 'nous-tries', min: '0', step: '1', value: String(was.tries || 0) })
    const policy = ways('policy', data.policies, was.policy || data.default, { id: 'nous-policy', 'data-hmz': 'nous-policy' })
    const timeout = h('input', { type: 'number', id: 'nous-timeout', min: '0', step: '1', value: String(was.timeout || 0) })
    const form = h(
      'form',
      { class: 'form' },
      name
        ? h('div', { class: 'field' }, h('label', { for: 'nous-name' }, t('Name')), name)
        : h('div', { class: 'field' }, h('span', { class: 'label' }, editing.virtual ? t('Virtual nous') : t('Concrete nous')), h('span', { title: editing.name }, nousNamed(editing.name))),
      h(
        'div',
        { class: 'field' },
        h(
          'div',
          { class: 'row' },
          h('div', { class: 'field' }, h('label', { for: 'nous-tries' }, t('Tries')), tries),
          h('div', { class: 'field' }, h('label', { for: 'nous-timeout' }, t('Limit, s')), timeout),
          // Last in the row, with what explains the way chosen beside its select, not under another field.
          h('div', { class: 'field way-field' }, h('label', { for: 'nous-policy' }, t('Wait')), h('div', { class: 'row' }, policy.select, policy.about)),
        ),
      ),
      was.virtual ? graph.node : null,
      then.node,
      h(
        'div',
        { class: 'row' },
        acting(
          t('Save'),
          async () => {
            const answer = await scope.call('nous.set', {
              name: name ? name.value.trim() : editing.name,
              tries: Number(tries.value || 0),
              policy: policy.select.value,
              timeout: Number(timeout.value || 0),
              graph: was.virtual ? written(graph.form) : null,
              then: written(then.form),
            })
            editing = null
            shown(answer)
          },
          { kind: 'btn primary', busy: t('Saving…') },
        ),
        editing ? h('button', { class: 'btn quiet', type: 'button', onclick: () => ((editing = null), drawWriting()) }, t('New virtual nous')) : null,
      ),
    )
    form.addEventListener('submit', (event) => event.preventDefault())
    fill(writing, h('h2', {}, editing ? t('Edit {name}', { name: nousNamed(editing.name) }) : t('New virtual nous')), form)
  }

  /**
   * A graph's form: its nodes, each a use node or a balance node with its edges, and its start.
   *
   * @param {string} label What the graph is to the nous.
   * @param {string} key Its word in `data-hmz`.
   * @param {ReturnType<typeof held>} form The graph as the form holds it, changed in place.
   * @param {string} whose The nous it is a graph of, which it does not offer itself.
   */
  function graphForm(label, key, form, whose) {
    const node = h('div', { class: 'field graph-form', 'data-hmz': `nous-${key}` })
    /** The chips of this graph drawn, left as it is drawn again. */
    let mine = []
    const select = (options, value, props, changed) => {
      const el = h('select', props, options.map(([one, said]) => h('option', { value: one, selected: one === value }, said)))
      el.addEventListener('change', () => changed(el.value))
      return el
    }
    /** A nous a node names, picked a level at a time as every nous is: said `aria` to whoever cannot see its node. */
    const nousPick = (value, aria, changed) => {
      const chip = modelChip(anyCli(aria), value, () => changed(chip.value()), {
        up: false,
        align: 'start',
        field: true,
        virtual: () => data.nous.filter((one) => one.virtual && one.name !== whose).map((one) => one.name),
      })
      mine.push(chip)
      chips.push(chip)
      // One that names nothing yet names the first nous there is, as its chip says.
      if (!value) changed(chip.value())
      return h('span', { class: 'nous-field', role: 'group', 'aria-label': aria, 'data-hmz': 'graph-nous' }, chip.node)
    }
    const redraw = () => {
      for (const one of mine) one.leave()
      chips = chips.filter((one) => !mine.includes(one))
      mine = []
      const ids = form.nodes.map((one) => one.id)
      const start = select(ids.map((one) => [one, one]), form.start, { 'aria-label': t('{graph} start', { graph: label }), 'data-hmz': 'graph-start' }, (value) => (form.start = value))
      fill(
        node,
        h('span', { class: 'label' }, label),
        form.nodes.length ? h('div', { class: 'row' }, h('span', { class: 'dim' }, t('Start')), start) : h('span', { class: 'hint' }, key === 'then' ? t('None: a turn whose tries are spent fails.') : t('No node yet.')),
        form.nodes.map((one) => nodeRow(one, ids)),
        h(
          'div',
          { class: 'row' },
          h('button', { class: 'btn small quiet', type: 'button', 'data-hmz': 'graph-add-use', onclick: () => add('use') }, t('Add use node')),
          h('button', { class: 'btn small quiet', type: 'button', 'data-hmz': 'graph-add-balance', onclick: () => add('balance') }, t('Add balance node')),
        ),
      )
    }
    const add = (kind) => {
      const id = freshId(form)
      form.nodes.push({ id, kind, use: '', balance: data.strategies.length ? data.strategies[0].name : '', among: kind === 'balance' ? [{ nous: '', weight: 1 }] : [], spread: 0, on: [] })
      if (!form.start) form.start = id
      redraw()
    }
    const nodeRow = (one, ids) => {
      const id = h('input', { type: 'text', value: one.id, 'aria-label': t('Node id'), 'data-hmz': 'graph-node-id', spellcheck: 'false', size: '6' })
      id.addEventListener('change', () => {
        const to = id.value.trim()
        if (!to || form.nodes.some((other) => other !== one && other.id === to)) {
          id.value = one.id
          return
        }
        renamed(form, one.id, to)
        redraw()
      })
      const kind = select([['use', t('Use')], ['balance', t('Balance')]], one.kind, { 'aria-label': t('Kind of node {id}', { id: one.id }), 'data-hmz': 'graph-node-kind' }, (value) => {
        one.kind = value
        if (value === 'balance') {
          if (!one.balance && data.strategies.length) one.balance = data.strategies[0].name
          if (!one.among.length) one.among.push({ nous: one.use, weight: 1 })
        } else if (!one.use && one.among.length) one.use = one.among[0].nous
        redraw()
      })
      const strategy = one.kind === 'balance' ? ways('strategy', data.strategies, one.balance, { 'aria-label': t('Strategy of node {id}', { id: one.id }), 'data-hmz': 'graph-strategy' }, (value) => (one.balance = value)) : null
      const what =
        one.kind === 'use'
          ? h('div', { class: 'row' }, nousPick(one.use, t('Nous of node {id}', { id: one.id }), (value) => (one.use = value)))
          : h(
              'div',
              { class: 'form' },
              h(
                'div',
                { class: 'field' },
                h('div', { class: 'row' }, strategy.select, h('label', {}, pieces('Spread {count}', { count: number(one.spread, 0, t('Spread of node {id}', { id: one.id }), 'graph-spread', (value) => (one.spread = value)) }))),
                strategy.about,
              ),
              one.among.map((member) =>
                h(
                  'div',
                  { class: 'row', 'data-hmz': 'graph-member' },
                  nousPick(member.nous, t('Member of node {id}', { id: one.id }), (value) => (member.nous = value)),
                  h('label', {}, '× ', number(member.weight, 1, member.nous ? t('Weight of {name}', { name: member.nous }) : t('Weight of member'), 'graph-weight', (value) => (member.weight = value))),
                  iconButton('close', t('Remove member'), { class: 'small', onclick: () => ((one.among = one.among.filter((other) => other !== member)), redraw()) }),
                ),
              ),
              h('div', {}, h('button', { class: 'btn small quiet', type: 'button', 'data-hmz': 'graph-add-member', onclick: () => (one.among.push({ nous: '', weight: 1 }), redraw()) }, t('Add member'))),
            )
      const others = ids.filter((other) => other !== one.id)
      const edges = one.on.map((edge) =>
        h(
          'div',
          { class: 'row', 'data-hmz': 'graph-edge' },
          h('span', { class: 'dim' }, t('On@@fault')),
          select(data.faults.map((fault) => [fault, fault === '*' ? t('* (any other)') : fault]), edge.fault, { 'aria-label': t('Fault of an edge of node {id}', { id: one.id }), 'data-hmz': 'graph-edge-fault' }, (value) => (edge.fault = value)),
          h('span', { class: 'dim' }, t('go to')),
          select([['', '—'], ...others.map((other) => [other, other])], edge.to, { 'aria-label': t('Node an edge of node {id} goes to', { id: one.id }), 'data-hmz': 'graph-edge-to' }, (value) => (edge.to = value)),
          iconButton('close', t('Remove edge'), { class: 'small', onclick: () => ((one.on = one.on.filter((other) => other !== edge)), redraw()) }),
        ),
      )
      const unused = data.faults.filter((fault) => !one.on.some((edge) => edge.fault === fault))
      return h(
        'div',
        { class: 'graph-node', 'data-hmz': 'graph-node', 'data-id': one.id },
        h('div', { class: 'row' }, id, kind, iconButton('close', t('Remove node'), { class: 'small', 'data-hmz': 'graph-remove-node', onclick: () => (removed(form, one.id), redraw()) })),
        what,
        edges,
        others.length && unused.length
          ? h('div', {}, h('button', { class: 'btn small quiet', type: 'button', 'data-hmz': 'graph-add-edge', onclick: () => (one.on.push({ fault: unused.includes('*') ? '*' : unused[0], to: others[0] }), redraw()) }, t('Add edge')))
          : null,
      )
    }
    const number = (value, min, aria, hook, changed) => {
      const el = h('input', { type: 'number', min: String(min), step: '1', value: String(value), 'aria-label': aria, 'data-hmz': hook, class: 'narrow' })
      el.addEventListener('input', () => changed(Number(el.value || min)))
      return el
    }
    redraw()
    return { node, form }
  }

  read().catch((error) => fill(listing, problem(error)))
  return () => {
    gone = true
    clearTimeout(reading)
    for (const one of chips) one.leave()
  }
}
