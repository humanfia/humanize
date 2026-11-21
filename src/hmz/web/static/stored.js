// A store of values by key in this browser's IndexedDB, for what the page keeps for itself alone
// and never in any daemon's settings: where each daemon's notices are taken up and what it wants
// told of them.

/**
 * One IndexedDB database of one store of values by key.
 *
 * @param {string} name The database.
 * @param {IDBFactory} [indexedDB]
 * @returns {{get: (key: string) => Promise<any>, put: (key: string, value: any) => Promise<void>, drop: (key: string) => Promise<void>}}
 */
export function stored(name, indexedDB = globalThis.indexedDB) {
  /** @type {Promise<IDBDatabase> | null} */
  let base = null
  const kept = (mode, act) => {
    base ||= new Promise((resolve, reject) => {
      const asked = indexedDB.open(name, 1)
      asked.onupgradeneeded = () => asked.result.createObjectStore('kept')
      asked.onsuccess = () => resolve(asked.result)
      asked.onerror = () => reject(asked.error)
    })
    return base.then(
      (db) =>
        new Promise((resolve, reject) => {
          const doing = db.transaction('kept', mode)
          const request = act(doing.objectStore('kept'))
          doing.oncomplete = () => resolve(request.result)
          doing.onabort = () => reject(doing.error)
        }),
    )
  }
  return {
    get: (key) => kept('readonly', (store) => store.get(key)),
    put: (key, value) => kept('readwrite', (store) => store.put(value, key)).then(() => undefined),
    drop: (key) => kept('readwrite', (store) => store.delete(key)).then(() => undefined),
  }
}
