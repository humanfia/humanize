// An agent as `-a` spells it, and what picking one offers a step at a time -- its CLI, the account
// it runs as, a model that account runs and an effort that model takes -- with what a chip says of
// the one picked. Kept apart from the page, as plain functions of what they are given, so that the
// selects of a form and the menu of a chip offer the same, and are tested alone.

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
      ...names.map((one) => ({ value: one, label: one })),
      ...(chosen.cli && !names.includes(chosen.cli) ? [{ value: chosen.cli, label: `${chosen.cli} (not installed)` }] : []),
      ...(!names.length && !chosen.cli ? [{ value: '', label: 'None installed' }] : []),
    ],
    accounts: accounts.length ? accounts.map((one) => ({ value: one.name, label: one.name || 'Local' })) : [{ value: '', label: 'Local' }],
    models: models.map((one) => ({ value: one.name, label: one.name })),
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
 * A model's name as a person reads it: `claude-opus-4-1` is `Opus 4.1`, a date after it left out;
 * any other name is said as it is.
 */
export function modelName(model) {
  const now = /^claude-([a-z]+)-(\d{1,2})(?:-(\d{1,2}))?(?:-\d{8})?$/.exec(model)
  const once = /^claude-(\d{1,2})(?:-(\d{1,2}))?-([a-z]+)(?:-\d{8})?$/.exec(model)
  const [family, major, minor] = now ? [now[1], now[2], now[3]] : once ? [once[3], once[1], once[2]] : []
  if (!family) return model
  return `${family[0].toUpperCase()}${family.slice(1)} ${major}${minor ? `.${minor}` : ''}`
}

/** An effort as a person reads it: none, or `auto` as an epic writes none down, is the model's own. */
export function effortName(effort) {
  return effort && effort !== 'auto' ? `${effort[0].toUpperCase()}${effort.slice(1)}` : 'Default'
}

/** What a chip says of an agent, as a chat app's says it: its model, then its effort where one is set. */
export function agentLabel(spec) {
  const { model, effort } = parted(spec)
  if (!model) return ''
  return effort && effort !== 'auto' ? `${modelName(model)} ${effortName(effort)}` : modelName(model)
}
