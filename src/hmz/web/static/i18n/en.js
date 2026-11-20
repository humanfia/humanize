// The English catalog: only the texts that differ by number, each `{ one, other }`, since every
// other text is its own English. One fragment per area (i18n/en/<area>.js), so that areas are
// written side by side without one file between them; `core` is first.

import core from './en/core.js'
import sidebar from './en/sidebar.js'
import chat from './en/chat.js'
import ask from './en/ask.js'
import settings from './en/settings.js'
import envs from './en/envs.js'
import themes from './en/themes.js'

export default { ...core, ...sidebar, ...chat, ...ask, ...settings, ...envs, ...themes }
