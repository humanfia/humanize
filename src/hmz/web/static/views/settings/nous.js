// Every nous: a concrete one, `HARNESS[@ACCOUNT]/MODEL[:EFFORT]`, or a virtual one, a name
// standing for a graph of other nous. Each says how many more goes a failed turn has there, how
// it waits between them, how long it may take at most, and the graph a turn goes to once those
// are spent (`then`). A graph is a start and its nodes: a use node names one nous, a balance
// node picks among several by a strategy, and each node's edges say, by fault class or `*`,
// which node a turn goes to once it fails there.

import { confirming } from '../../confirm.js'
import { acting, fill, h, iconButton, lasting, problem } from '../../dom.js'
import { batched, concrete, freshId, graphSaid, held, removed, renamed, withEffort, written } from '../../nous.js'
import { parted, readBackends } from '../../pickers.js'

export function draw(holder, query, parts, scope) {
  const listing = h('section', { class: 'panel', 'data-hmz': 'nous' }, h('p', { class: 'loading', role: 'status' }, 'Reading the nous…'))
  const writing = h('section', { class: 'panel', 'data-hmz': 'write-nous' })
  const offered = h('datalist', { id: 'nous-offered' })
  fill(holder, offered, listing, writing)
  let data = null
  let backends = null
  let editing = null
  let renaming = null

  const shown = (answer) => {
    data = answer
    const virtual = data.nous.filter((one) => one.virtual).map((one) => one.name)
    fill(offered, [...virtual, ...data.concrete].map((one) => h('option', { value: one })))
    drawListing()
    drawWriting()
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
      ? graphSaid(graph).map((one) =>
          h(
            'div',
            { 'data-hmz': 'nous-node' },
            h('span', { class: 'dim' }, `${one.id}${one.start ? ' (start)' : ''}: `),
            h('span', { class: 'mono' }, worded(one.text)),
            one.edges ? h('span', { class: 'dim' }, ` · ${one.edges}`) : null,
          ),
        )
      : h('span', { class: 'dim' }, none)

  function drawListing() {
    const rows = data.nous.map((one) =>
      h(
        'tr',
        { 'data-hmz': 'nous-row', 'data-name': one.name },
        h('td', {}, h('div', { class: 'mono' }, worded(one.name)), h('span', { class: 'chip', 'data-hmz': 'nous-kind' }, one.virtual ? 'virtual' : 'concrete')),
        h('td', { 'data-label': 'Tried' }, one.tries ? `${one.tries} more ${one.tries === 1 ? 'go' : 'goes'}, ${one.policy}` : h('span', { class: 'dim' }, 'once'), h('div', { class: 'dim' }, one.timeout ? `at most ${lasting(one.timeout)}` : 'no limit')),
        h('td', { 'data-label': 'Graph' }, graphCell(one.graph, '—')),
        h('td', { 'data-label': 'Then' }, graphCell(one.then, 'nowhere')),
        h('td', {}, renaming === one.name ? renameForm(one) : actions(one)),
      ),
    )
    fill(
      listing,
      // Each nous written whole over the one of its name there, or added; none there taken away.
      h('header', {}, h('h2', {}, 'Nous'), scope.batch(() => batched(data.nous))),
      rows.length
        ? h('div', { class: 'table-wrap' }, h('table', {}, h('thead', {}, h('tr', {}, h('th', {}, 'Nous'), h('th', {}, 'Tried'), h('th', {}, 'Graph'), h('th', {}, 'Then'), h('th', {}, ''))), h('tbody', {}, rows)))
        : h('p', { class: 'dim' }, 'No nous written down. A failed turn fails where it ran.'),
    )
    if (rows.length) fit(listing.querySelector('.table-wrap'))
  }

  function actions(one) {
    return h(
      'div',
      { class: 'row' },
      h('button', { class: 'btn small quiet', type: 'button', 'data-hmz': 'nous-edit', onclick: () => edit(one) }, 'Edit'),
      one.virtual ? h('button', { class: 'btn small quiet', type: 'button', 'data-hmz': 'nous-rename', onclick: () => ((renaming = one.name), drawListing()) }, 'Rename') : null,
      confirming({
        label: 'Remove',
        ask: `Remove ${one.name}?`,
        yes: 'Remove',
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
    const to = h('input', { type: 'text', value: one.name, 'aria-label': `New name for ${one.name}`, 'data-hmz': 'nous-rename-to', spellcheck: 'false' })
    return h(
      'div',
      { class: 'row' },
      to,
      acting('Rename', async () => {
        const answer = await scope.call('nous.rename', { name: one.name, to: to.value.trim() })
        if (editing && editing.name === one.name) editing = null
        renaming = null
        shown(answer)
      }, { kind: 'btn small primary', busy: 'Renaming…' }),
      h('button', { class: 'btn small quiet', type: 'button', onclick: () => ((renaming = null), drawListing()) }, 'Cancel'),
    )
  }

  function edit(one) {
    editing = one
    drawWriting()
    writing.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  /** The efforts the model of a concrete nous takes, as the daemon's harnesses list them. */
  function effortsOf(spec) {
    const { cli, account, model } = parted(spec)
    const accounts = (backends && backends.clis[cli] && backends.clis[cli].accounts) || []
    const found = ((accounts.find((one) => one.name === account) || { models: [] }).models || []).find((one) => one.name === model)
    return found ? found.efforts : []
  }

  /** The name of a new nous: a concrete one picked, or typed, with an effort; or a virtual name. */
  function nameField() {
    const kind = h('select', { id: 'nous-kind', 'data-hmz': 'nous-kind-pick' }, h('option', { value: 'concrete' }, 'Concrete'), h('option', { value: 'virtual' }, 'Virtual'))
    const spec = h('select', { id: 'nous-spec', 'data-hmz': 'nous-spec' }, data.concrete.map((one) => h('option', { value: one }, one)), h('option', { value: '…' }, 'Other…'))
    const typed = h('input', { type: 'text', 'aria-label': 'Concrete nous', placeholder: 'HARNESS[@ACCOUNT]/MODEL', 'data-hmz': 'nous-spec-typed', spellcheck: 'false', hidden: data.concrete.length > 0 })
    if (!data.concrete.length) spec.hidden = true
    const effort = h('select', { id: 'nous-effort', 'data-hmz': 'nous-effort' })
    const graphHolder = h('div', {})
    const virtual = h('input', { type: 'text', id: 'nous-name', placeholder: 'A name, as fast or careful', 'data-hmz': 'nous-name', spellcheck: 'false' })
    const picked = () => (spec.hidden || spec.value === '…' ? typed.value.trim() : spec.value)
    const efforts = () => {
      const offered = effortsOf(picked())
      fill(effort, h('option', { value: '' }, 'Default'), offered.map((one) => h('option', { value: one }, one)))
      effort.disabled = !offered.length
    }
    const concreteFields = h('div', { class: 'row' }, h('div', { class: 'field' }, h('label', { for: 'nous-spec' }, 'Nous'), spec, typed), h('div', { class: 'field' }, h('label', { for: 'nous-effort' }, 'Effort'), effort))
    const virtualFields = h('div', { class: 'field' }, h('label', { for: 'nous-name' }, 'Name'), virtual)
    const switched = () => {
      concreteFields.hidden = kind.value !== 'concrete'
      virtualFields.hidden = kind.value !== 'virtual'
      graphHolder.hidden = kind.value !== 'virtual'
    }
    spec.addEventListener('change', () => {
      typed.hidden = spec.value !== '…'
      efforts()
    })
    typed.addEventListener('change', efforts)
    kind.addEventListener('change', switched)
    efforts()
    return {
      node: h('div', { class: 'form' }, h('div', { class: 'field' }, h('label', { for: 'nous-kind' }, 'Kind'), kind), concreteFields, virtualFields),
      graphHolder,
      switched,
      value: () => (kind.value === 'virtual' ? virtual.value.trim() : withEffort(picked(), effort.value)),
    }
  }

  function drawWriting() {
    const was = editing || { name: '', virtual: false, tries: 0, policy: data.default, timeout: 0, graph: null, then: null }
    const name = editing ? null : nameField()
    const graph = graphForm('Graph', 'graph', held(was.graph))
    const then = graphForm('Then', 'then', held(was.then))
    const tries = h('input', { type: 'number', id: 'nous-tries', min: '0', step: '1', value: String(was.tries) })
    const policy = h(
      'select',
      { id: 'nous-policy' },
      data.policies.map((one) => h('option', { value: one.name, selected: one.name === was.policy, title: one.about }, `${one.name} — ${one.about}`)),
    )
    const timeout = h('input', { type: 'number', id: 'nous-timeout', min: '0', step: '1', value: String(was.timeout || 0) })
    const form = h(
      'form',
      { class: 'form' },
      name ? name.node : h('div', { class: 'field' }, h('span', { class: 'label' }, editing.virtual ? 'Virtual nous' : 'Concrete nous'), h('span', { class: 'mono' }, editing.name)),
      h(
        'div',
        { class: 'row' },
        h('div', { class: 'field' }, h('label', { for: 'nous-tries' }, 'Tries'), tries),
        h('div', { class: 'field' }, h('label', { for: 'nous-policy' }, 'Wait'), policy),
        h('div', { class: 'field' }, h('label', { for: 'nous-timeout' }, 'Limit, s'), timeout),
      ),
      name ? fill(name.graphHolder, graph.node) : editing.virtual ? graph.node : null,
      then.node,
      h(
        'div',
        { class: 'row' },
        acting(
          'Save',
          async () => {
            const virtual = name ? !concrete(name.value()) : editing.virtual
            const answer = await scope.call('nous.set', {
              name: name ? name.value() : editing.name,
              tries: Number(tries.value || 0),
              policy: policy.value,
              timeout: Number(timeout.value || 0),
              graph: virtual ? written(graph.form) : null,
              then: written(then.form),
            })
            editing = null
            shown(answer)
          },
          { kind: 'btn primary', busy: 'Saving…' },
        ),
        editing ? h('button', { class: 'btn quiet', type: 'button', onclick: () => ((editing = null), drawWriting()) }, 'New nous') : null,
      ),
    )
    if (name) name.switched()
    form.addEventListener('submit', (event) => event.preventDefault())
    fill(writing, h('h2', {}, editing ? `Edit ${editing.name}` : 'New nous'), form)
  }

  /**
   * A graph's form: its nodes, each a use node or a balance node with its edges, and its start.
   *
   * @param {string} label What the graph is to the nous.
   * @param {string} key Its word in `data-hmz`.
   * @param {ReturnType<typeof held>} form The graph as the form holds it, changed in place.
   */
  function graphForm(label, key, form) {
    const node = h('div', { class: 'field graph-form', 'data-hmz': `nous-${key}` })
    const select = (options, value, props, changed) => {
      const el = h('select', props, options.map(([one, said]) => h('option', { value: one, selected: one === value }, said)))
      el.addEventListener('change', () => changed(el.value))
      return el
    }
    const nousInput = (value, aria, changed) => {
      const el = h('input', { type: 'text', value, list: 'nous-offered', placeholder: 'A nous', 'aria-label': aria, 'data-hmz': 'graph-nous', spellcheck: 'false', autocomplete: 'off' })
      el.addEventListener('input', () => changed(el.value))
      return el
    }
    const redraw = () => {
      const ids = form.nodes.map((one) => one.id)
      const start = select(ids.map((one) => [one, one]), form.start, { 'aria-label': `${label} start`, 'data-hmz': 'graph-start' }, (value) => (form.start = value))
      fill(
        node,
        h('span', { class: 'label' }, label),
        form.nodes.length ? h('div', { class: 'row' }, h('span', { class: 'dim' }, 'Start'), start) : h('span', { class: 'hint' }, label === 'Then' ? 'None: a turn whose tries are spent fails.' : 'No node yet.'),
        form.nodes.map((one) => nodeRow(one, ids)),
        h(
          'div',
          { class: 'row' },
          h('button', { class: 'btn small quiet', type: 'button', 'data-hmz': 'graph-add-use', onclick: () => add('use') }, 'Add use node'),
          h('button', { class: 'btn small quiet', type: 'button', 'data-hmz': 'graph-add-balance', onclick: () => add('balance') }, 'Add balance node'),
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
      const id = h('input', { type: 'text', value: one.id, 'aria-label': 'Node id', 'data-hmz': 'graph-node-id', spellcheck: 'false', size: '6' })
      id.addEventListener('change', () => {
        const to = id.value.trim()
        if (!to || form.nodes.some((other) => other !== one && other.id === to)) {
          id.value = one.id
          return
        }
        renamed(form, one.id, to)
        redraw()
      })
      const kind = select([['use', 'Use'], ['balance', 'Balance']], one.kind, { 'aria-label': `Kind of node ${one.id}`, 'data-hmz': 'graph-node-kind' }, (value) => {
        one.kind = value
        if (value === 'balance') {
          if (!one.balance && data.strategies.length) one.balance = data.strategies[0].name
          if (!one.among.length) one.among.push({ nous: one.use, weight: 1 })
        } else if (!one.use && one.among.length) one.use = one.among[0].nous
        redraw()
      })
      const what =
        one.kind === 'use'
          ? h('div', { class: 'row' }, nousInput(one.use, `Nous of node ${one.id}`, (value) => (one.use = value)))
          : h(
              'div',
              { class: 'form' },
              h(
                'div',
                { class: 'row' },
                select(
                  data.strategies.map((strategy) => [strategy.name, `${strategy.name} — ${strategy.about}`]),
                  one.balance,
                  { 'aria-label': `Strategy of node ${one.id}`, 'data-hmz': 'graph-strategy' },
                  (value) => (one.balance = value),
                ),
                h('label', {}, 'Spread ', number(one.spread, 0, `Spread of node ${one.id}`, 'graph-spread', (value) => (one.spread = value))),
              ),
              one.among.map((member) =>
                h(
                  'div',
                  { class: 'row', 'data-hmz': 'graph-member' },
                  nousInput(member.nous, `Member of node ${one.id}`, (value) => (member.nous = value)),
                  h('label', {}, '× ', number(member.weight, 1, `Weight of ${member.nous || 'member'}`, 'graph-weight', (value) => (member.weight = value))),
                  iconButton('close', 'Remove member', { class: 'small', onclick: () => ((one.among = one.among.filter((other) => other !== member)), redraw()) }),
                ),
              ),
              h('div', {}, h('button', { class: 'btn small quiet', type: 'button', 'data-hmz': 'graph-add-member', onclick: () => (one.among.push({ nous: '', weight: 1 }), redraw()) }, 'Add member')),
            )
      const others = ids.filter((other) => other !== one.id)
      const edges = one.on.map((edge) =>
        h(
          'div',
          { class: 'row', 'data-hmz': 'graph-edge' },
          h('span', { class: 'dim' }, 'On'),
          select(data.faults.map((fault) => [fault, fault === '*' ? '* (any other)' : fault]), edge.fault, { 'aria-label': `Fault of an edge of node ${one.id}`, 'data-hmz': 'graph-edge-fault' }, (value) => (edge.fault = value)),
          h('span', { class: 'dim' }, 'go to'),
          select([['', '—'], ...others.map((other) => [other, other])], edge.to, { 'aria-label': `Node an edge of node ${one.id} goes to`, 'data-hmz': 'graph-edge-to' }, (value) => (edge.to = value)),
          iconButton('close', 'Remove edge', { class: 'small', onclick: () => ((one.on = one.on.filter((other) => other !== edge)), redraw()) }),
        ),
      )
      const unused = data.faults.filter((fault) => !one.on.some((edge) => edge.fault === fault))
      return h(
        'div',
        { class: 'graph-node', 'data-hmz': 'graph-node', 'data-id': one.id },
        h('div', { class: 'row' }, id, kind, iconButton('close', 'Remove node', { class: 'small', 'data-hmz': 'graph-remove-node', onclick: () => (removed(form, one.id), redraw()) })),
        what,
        edges,
        others.length && unused.length
          ? h('div', {}, h('button', { class: 'btn small quiet', type: 'button', 'data-hmz': 'graph-add-edge', onclick: () => (one.on.push({ fault: unused.includes('*') ? '*' : unused[0], to: others[0] }), redraw()) }, 'Add edge'))
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

  Promise.all([scope.call('nous.list'), readBackends(undefined, scope.name).catch(() => null)])
    .then(([answer, read]) => {
      backends = read
      shown(answer)
    })
    .catch((error) => fill(listing, problem(error)))
}
