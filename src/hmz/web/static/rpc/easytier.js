// Where the EasyTier entry of a P2P daemon is written: Local's settings, which `hmz web` opens
// an `easytier:` route with (Section 3.13.6 and Section 4.8.7 of protocol/web.md), and, in the
// desktop application, the app's own entries too, which its pipes open the route with (Section
// 3.12.6 of protocol/desktop.md). Neither hands a secret back.

/**
 * @typedef {{name: string, nodes: string[], secret?: string}} Entry
 * @param {(method: string, params?: object) => Promise<any>} local Asks Local a method.
 * @param {{invoke: (command: string, args?: object) => Promise<any>}} [app] What Tauri gives the page.
 */
export function easytier(local, app = /** @type {any} */ (globalThis).__TAURI_INTERNALS__) {
  /** Asks the app, a refusal of its a sentence as a daemon's is. */
  const invoke = (command, args) =>
    app.invoke(command, args).catch((why) => {
      throw why instanceof Error ? why : new Error(String(why))
    })
  return {
    /** The entries the route of each is opened with here, `secret` whether one is written. */
    list: async () => (app ? invoke('easytier_list') : (await local('easytier.list')).networks || []),
    /** Writes an entry, keeping the secret written where it gives none. @param {Entry} entry */
    async set(entry) {
      await local('easytier.set', entry)
      if (app) await invoke('easytier_set', entry)
    },
    /** Forgets the entry of a name. @param {string} name */
    async remove(name) {
      await local('easytier.remove', { name })
      if (app) await invoke('easytier_remove', { name })
    },
  }
}
