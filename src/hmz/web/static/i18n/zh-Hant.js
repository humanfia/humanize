// The Traditional Chinese, in Taiwan’s words catalog: what each English text of the page is in it. One fragment per
// area (i18n/zh-Hant/<area>.js), so that areas are written side by side without one file between
// them; `core` is first, and holds every text two areas share.

import core from './zh-Hant/core.js'
import sidebar from './zh-Hant/sidebar.js'
import chat from './zh-Hant/chat.js'
import ask from './zh-Hant/ask.js'
import settings from './zh-Hant/settings.js'
import envs from './zh-Hant/envs.js'
import themes from './zh-Hant/themes.js'

export default { ...core, ...sidebar, ...chat, ...ask, ...settings, ...envs, ...themes }
