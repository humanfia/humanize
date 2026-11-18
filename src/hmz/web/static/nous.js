// A nous and its graphs as the Nous page says and writes them, nothing drawn: a graph's nodes in
// order from its start, each said in a line; the graph the form holds put as `nous.set` takes
// it; and every nous written in an order in which each names only nous already written.

/** Whether a nous is concrete, `HARNESS[@ACCOUNT]/MODEL[:EFFORT]`, rather than a name. */
export function concrete(name) {
  return String(name || '').includes('/')
}

/** A concrete nous with an effort put on in place of an `:auto` it ends in, none for '' or `auto`. */
export function withEffort(spec, effort) {
  return effort && effort !== 'auto' ? `${spec.replace(/:auto$/, '')}:${effort}` : spec
}

/** A graph's nodes, each once, in order from its start along its edges; those not reached last. */
export function ordered(graph) {
  if (!graph || !graph.nodes) return []
  const byId = new Map(graph.nodes.map((one) => [one.id, one]))
  const seen = new Set()
  const out = []
  const walk = (id) => {
    const one = byId.get(id)
    if (!one || seen.has(id)) return
    seen.add(id)
    out.push(one)
    for (const to of Object.values(one.on || {})) walk(to)
  }
  walk(graph.start)
  for (const one of graph.nodes) if (!seen.has(one.id)) out.push(one)
  return out
}

/** One node as a line says it: its nous, or its strategy and its nous with their weights. */
export function nodeSaid(one) {
  if (one.use) return one.use
  const among = (one.among || []).map(({ nous, weight }) => (weight > 1 ? `${nous} ×${weight}` : nous)).join(', ')
  return `${one.balance}: ${among}${one.spread ? `, ${one.spread} at most` : ''}`
}

/** One node's edges as a line says them: `fault → node`, `*` last. */
export function edgesSaid(one) {
  const edges = Object.entries(one.on || {})
  edges.sort(([a], [b]) => (a === '*') - (b === '*'))
  return edges.map(([fault, to]) => `${fault} → ${to}`).join(', ')
}

/** A graph as the list says it: a line per node in order from the start, or none. */
export function graphSaid(graph) {
  return ordered(graph).map((one) => ({ id: one.id, start: one.id === graph.start, text: nodeSaid(one), edges: edgesSaid(one) }))
}

/**
 * A graph as the form holds it: its start, and each node with its kind and its edges as rows,
 * so that a row half written is kept until it is finished.
 */
export function held(graph) {
  if (!graph) return { start: '', nodes: [] }
  return {
    start: graph.start,
    nodes: graph.nodes.map((one) => ({
      id: one.id,
      kind: one.balance ? 'balance' : 'use',
      use: one.use || '',
      balance: one.balance || '',
      among: (one.among || []).map(({ nous, weight }) => ({ nous, weight })),
      spread: one.spread || 0,
      on: Object.entries(one.on || {}).map(([fault, to]) => ({ fault, to })),
    })),
  }
}

/** A graph the form holds, as `nous.set` takes it, or null where it has no node. */
export function written(form) {
  if (!form || !form.nodes.length) return null
  return {
    start: form.start || form.nodes[0].id,
    nodes: form.nodes.map((one) => {
      const on = Object.fromEntries(one.on.filter((edge) => edge.fault && edge.to).map((edge) => [edge.fault, edge.to]))
      if (one.kind === 'use') return { id: one.id, use: one.use.trim(), on }
      const among = one.among.filter((member) => member.nous.trim()).map((member) => ({ nous: member.nous.trim(), weight: Number(member.weight) || 1 }))
      return { id: one.id, balance: one.balance, among, spread: Number(one.spread) || 0, on }
    }),
  }
}

/** A node id no node of the form has: `n1`, `n2`, … */
export function freshId(form) {
  const ids = new Set(form.nodes.map((one) => one.id))
  let n = form.nodes.length + 1
  while (ids.has(`n${n}`)) n++
  return `n${n}`
}

/** Gives a node of the form another id, its start and every edge to it following. */
export function renamed(form, was, id) {
  for (const one of form.nodes) {
    if (one.id === was) one.id = id
    for (const edge of one.on) if (edge.to === was) edge.to = id
  }
  if (form.start === was) form.start = id
}

/** Takes a node out of the form, with every edge to it; the start moves to the first left. */
export function removed(form, id) {
  form.nodes = form.nodes.filter((one) => one.id !== id)
  for (const one of form.nodes) one.on = one.on.filter((edge) => edge.to !== id)
  if (form.start === id) form.start = form.nodes.length ? form.nodes[0].id : ''
}

/** Every virtual nous a nous names, in its graph and its `then`. */
export function named(one) {
  const names = new Set()
  for (const graph of [one.graph, one.then]) {
    for (const node of (graph && graph.nodes) || []) {
      for (const name of [node.use, ...(node.among || []).map((member) => member.nous)]) if (name && !concrete(name)) names.add(name)
    }
  }
  return names
}

/**
 * Every nous as `nous.set` calls, each after every virtual nous it names, so that each call
 * names only nous the daemon it goes to already has.
 */
export function batched(every) {
  const left = [...every]
  const done = new Set()
  const out = []
  while (left.length) {
    const ready = left.findIndex((one) => [...named(one)].every((name) => done.has(name) || !left.some((other) => other.name === name)))
    // Nous that name each other round are refused wherever they go; they go as they are.
    const [one] = left.splice(ready < 0 ? 0 : ready, 1)
    done.add(one.name)
    out.push(['nous.set', { name: one.name, tries: one.tries, policy: one.policy, timeout: one.timeout, graph: one.graph, then: one.then }])
  }
  return out
}
