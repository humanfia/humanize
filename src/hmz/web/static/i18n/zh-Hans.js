// The Simplified Chinese catalog: what each English text of the page is in it. One fragment per
// area (i18n/zh-Hans/<area>.js), so that areas are written side by side without one file between
// them; `core` is first, and holds every text two areas share.

import core from './zh-Hans/core.js'
import sidebar from './zh-Hans/sidebar.js'
import chat from './zh-Hans/chat.js'
import ask from './zh-Hans/ask.js'
import settings from './zh-Hans/settings.js'
import envs from './zh-Hans/envs.js'
import themes from './zh-Hans/themes.js'

export default { ...core, ...sidebar, ...chat, ...ask, ...settings, ...envs, ...themes }
