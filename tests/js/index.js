// `node --test tests/js`, as CI runs it, loads this directory as one module, not each file in it:
// this loads every test file here. `node --test 'tests/js/*.test.mjs'` runs them one by one.

import { readdirSync } from 'node:fs'

for (const name of readdirSync(import.meta.dirname).filter((one) => one.endsWith('.test.mjs')).sort()) await import(`./${name}`)
