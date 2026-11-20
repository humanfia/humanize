// An agent as `-a` spells it, and what picking one offers a step at a time -- its CLI, the account
// it runs as, a model that account runs and an effort that model takes -- with what a chip says of
// the one picked. Kept apart from the page, as plain functions of what they are given, so that the
// selects of a form and the menu of a chip offer the same, and are tested alone.

import { effortName, harnessName, modelName, modelRoute } from '../names.js'

/** An agent as `-a` spells it, taken apart: `cli[@account]/model[:effort]`. */
export function parted(spec) {
  const said = /^([^@/]+)(?:@([^/]*))?\/(.*)$/.exec(spec || '')
  if (!said) return { cli: '', account: '', model: '', effort: '' }
  const [, cli, account = '', rest] = said
  const colon = rest.lastIndexOf(':')
  return colon < 0 ? { cli, account, model: rest, effort: '' } : { cli, account, model: rest.slice(0, colon), effort: rest.slice(colon + 1) }
}

/** An agent put back together as `-a` spells it. */
export function spelled({ cli, account, model, effort }) {
  if (!cli || !model) return ''
  return `${cli}${account ? `@${account}` : ''}/${model}${effort && effort !== 'auto' ? `:${effort}` : ''}`
}

/**
 * What picking an agent offers now, settling what is chosen on what can be: a CLI there is, an
 * account of it, the first model listed where none is chosen, an effort the model takes.
 *
 * @param {{cli: string, account: string, model: string, effort: string}} chosen What is picked,
 *   changed to what can be.
 * @param {Record<string, {accounts: {name: string, asked?: boolean, models: {name: string, efforts: string[]}[]}[]}>} clis
 *   The CLIs here, as `flows.backends` answers them.
 * @param {string[]} names The CLIs that could be picked.
 * @param {{waiting?: (key: string) => boolean, why?: (key: string) => string | undefined}} [asked]
 *   Whether a CLI is being asked for its models as an account, `cli@account`, and why asking failed.
 * @returns What each step offers, as `{value, label}`; whether the models are being asked for and
 *   why they could not be; whether none can be listed, so one is typed; and whether the CLI is
 *   yet to be asked.
 */
export function offering(chosen, clis, names, { waiting = () => false, why = () => undefined } = {}) {
  if (!chosen.cli || (!names.includes(chosen.cli) && !clis[chosen.cli])) chosen.cli = names[0] || chosen.cli
  const accounts = clis[chosen.cli] ? clis[chosen.cli].accounts : []
  if (!accounts.some((one) => one.name === chosen.account)) chosen.account = ''
  const held = accounts.find((one) => one.name === chosen.account)
  const models = held ? held.models : []
  const key = `${chosen.cli}@${chosen.account}`
  const asking = waiting(key)
  const failed = why(key)
  if (!chosen.model && models.length) chosen.model = models[0].name
  const found = models.find((one) => one.name === chosen.model)
  const efforts = found ? found.efforts : []
  if (chosen.effort && !efforts.includes(chosen.effort)) chosen.effort = ''
  return {
    clis: [
      ...names.map((one) => ({ value: one, label: harnessName(one) })),
      ...(chosen.cli && !names.includes(chosen.cli) ? [{ value: chosen.cli, label: `${harnessName(chosen.cli)} (not installed)` }] : []),
      ...(!names.length && !chosen.cli ? [{ value: '', label: 'None installed' }] : []),
    ],
    accounts: accounts.length ? accounts.map((one) => ({ value: one.name, label: one.name || 'Local' })) : [{ value: '', label: 'Local' }],
    models: models.map((one) => ({ value: one.name, label: modelName(one.name) })),
    /** Whether the model chosen is one nobody listed. */
    unlisted: Boolean(chosen.model) && !found,
    efforts,
    asking,
    failed,
    // Typed where nothing could be listed: once asked and told nothing, or refused.
    typed: !models.length && !asking && Boolean(failed || (held && held.asked)),
    // A CLI nobody has asked as this account yet is asked, as the terminal interface asks.
    unasked: Boolean(chosen.cli && held && !held.asked && !held.models.length && !asking && !failed),
  }
}

/**
 * What a chip says of an agent, a part at a time: its harness, its model and its effort, each by
 * its name (names.js), `Default` where no effort is set; nothing of one that names no model.
 */
export function nousSaid(spec) {
  const { cli, model, effort } = parted(spec)
  return model ? { harness: harnessName(cli), model: modelName(model), effort: effortName(effort) } : { harness: '', model: '', effort: '' }
}

/** The three parts as one line, as a chip is read out: `Claude Code Fable 5.2 Medium`. */
export function agentLabel(spec) {
  const { harness, model, effort } = nousSaid(spec)
  return model ? `${harness} ${model} ${effort}` : ''
}

/** A nous as a menu's row names it: its harness, then its model -- `Codex - GPT-6.2 Sol`. */
export function nousLabel(cli, model) {
  return `${harnessName(cli)} - ${modelName(model)}`
}

/**
 * The models of one harness as its rows name them, no two alike: where two ids come to one name
 * -- one model by two routes, `azure_ai/claude-opus-4-5` and `vertex_ai/claude-opus-4-5` -- each
 * says after it who routes it, `Opus 4.5 (azure_ai)`, or its id whole where that tells none apart.
 *
 * @param {string[]} models The ids one harness lists, each once.
 * @returns {string[]} A name for each, in their order.
 */
export function modelsNamed(models) {
  const tally = (keys) => keys.reduce((seen, key) => seen.set(key, (seen.get(key) || 0) + 1), new Map())
  const plain = models.map(modelName)
  const alike = tally(plain)
  const routed = tally(models.map((model, at) => `${plain[at]}\n${modelRoute(model)}`))
  return models.map((model, at) => {
    if (alike.get(plain[at]) < 2) return plain[at]
    const route = modelRoute(model)
    return `${plain[at]} (${route && routed.get(`${plain[at]}\n${route}`) === 1 ? route : model})`
  })
}

/**
 * A nous as a list of them names it whole: its row's name, the account it runs as and the effort
 * it sets, where it names either -- `Claude Code - Fable 5.2 · High`; a name that spells no
 * agent, as written.
 */
export function nousNamed(spec) {
  const { cli, account, model, effort } = parted(spec)
  if (!model) return spec || ''
  return [nousLabel(cli, model), account && `@${account}`, effort && effort !== 'auto' && effortName(effort)].filter(Boolean).join(' · ')
}

/**
 * Every nous the harnesses here are known to run, a group a harness in the order they are named:
 * its models as the account it runs as -- the account chosen for the harness chosen, else its own
 * sign-in, or the first account that lists any where that lists none -- and, where none is
 * listed, why: it is being asked, asking failed, nobody asked it yet, or it listed none.
 *
 * @param {{cli: string, account: string, model: string}} chosen What is picked.
 * @param {Parameters<typeof offering>[1]} clis The CLIs here, as `flows.backends` answers them.
 * @param {string[]} names The CLIs that could be picked.
 * @param {Parameters<typeof offering>[3]} [asked]
 * @returns {{cli: string, name: string, account: string, state: 'listed'|'asking'|'failed'|'unasked'|'empty', why: string,
 *   rows: {cli: string, account: string, model: string, named: string, label: string, spec: string, chosen: boolean, unlisted: boolean}[]}[]}
 *   `named` is the model as its row names it (`modelsNamed`), and `label` the row whole.
 */
export function nousOffered(chosen, clis, names, { waiting = () => false, why = () => undefined } = {}) {
  return [...names, ...(chosen.cli && !names.includes(chosen.cli) ? [chosen.cli] : [])].map((cli) => {
    const accounts = clis[cli] ? clis[cli].accounts : []
    const mine = cli === chosen.cli
    const held = mine ? accounts.find((one) => one.name === chosen.account) : accounts.find((one) => !one.name && one.models.length) || accounts.find((one) => one.models.length) || accounts.find((one) => !one.name)
    const account = held ? held.name : ''
    const key = `${cli}@${account}`
    const listed = held ? held.models.map((one) => one.name) : []
    // A model nobody listed is kept as a row of its harness, as `-a` takes one: not said unlisted
    // while its harness is still being asked.
    const typed = mine && chosen.model && !listed.includes(chosen.model)
    const models = typed ? [...listed, chosen.model] : listed
    const named = modelsNamed(models)
    const rows = models.map((model, at) => ({
      cli,
      account,
      model,
      named: named[at],
      label: `${harnessName(cli)} - ${named[at]}`,
      spec: spelled({ cli, account, model, effort: '' }),
      chosen: mine && model === chosen.model,
      unlisted: Boolean(typed) && at === listed.length && !waiting(key),
    }))
    const state = rows.length ? 'listed' : waiting(key) ? 'asking' : why(key) ? 'failed' : held && !held.asked ? 'unasked' : 'empty'
    return { cli, name: harnessName(cli), account, state, why: (state === 'failed' && why(key)) || '', rows }
  })
}
