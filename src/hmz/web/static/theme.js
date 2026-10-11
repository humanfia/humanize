// The theme, set before the page is drawn so it never flashes another: the one chosen here, or
// under Auto, where none was chosen, the one picked for the system's light or the one for its
// dark. A theme is Light or Dark, humanize's own, or one made in this browser on either of them,
// kept with the colours it changes of it; its pictures, kept apart, follow in themes.js, which
// paints with what is here. And whether the page is the macOS app's window, which says so in its
// user agent: there the page draws its top row around the window's traffic lights.
(() => {
  const read = (name) => {
    try {
      return localStorage.getItem(name)
    } catch {
      return null
    }
  }
  /** Paints the theme given, or the one chosen, and says which it painted. */
  window.hmzPaint = (shown) => {
    let made = []
    try {
      made = JSON.parse(read('hmz-themes') || '[]')
    } catch {
      // Unreadable is as good as none: humanize's own are left.
    }
    const dark = matchMedia('(prefers-color-scheme: dark)').matches
    const chosen = read('hmz-theme') || 'auto'
    const id = chosen === 'auto' ? read(dark ? 'hmz-theme-dark' : 'hmz-theme-light') || (dark ? 'dark' : 'light') : chosen
    const own = (one) => ({ id: one, base: one, colors: {} })
    const theme = shown || made.find((one) => one.id === id) || own(id === 'light' || id === 'dark' ? id : dark ? 'dark' : 'light')
    const root = document.documentElement
    for (const name of [...root.style]) if (name.startsWith('--')) root.style.removeProperty(name)
    root.dataset.theme = theme.base
    for (const [name, value] of Object.entries(theme.colors || {})) root.style.setProperty(`--${name}`, value)
    return theme
  }
  window.hmzPaint()
  if (/\bhumanize-desktop\//.test(navigator.userAgent)) document.documentElement.dataset.shell = 'macos'
})()
