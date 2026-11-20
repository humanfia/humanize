// The theme, set before the page is drawn so it never flashes another: the light of the one
// chosen here where the system is light, its dark where it is dark, and Humanize's own where
// none was chosen. A theme is one Humanize comes with or one made in this browser, each of its
// two sides kept with the colours it changes; its pictures, kept apart, follow in themes.js,
// which paints with what is here. And whether the page is Humanize Desktop's window, which says
// so in its user agent, and on which system: there the page draws its top row around the
// window's own buttons, the traffic lights on macOS or the caption buttons on Windows.
(() => {
  const read = (name) => {
    try {
      return localStorage.getItem(name)
    } catch {
      return null
    }
  }
  /** Paints the side given, or the side of the theme chosen that the system asks for, and says which it painted. */
  window.hmzPaint = (shown) => {
    // The sides made here, and those of the theme chosen where Humanize comes with it, as
    // themes.js keeps them for this.
    let made = []
    try {
      made = [...JSON.parse(read('hmz-themes') || '[]'), ...JSON.parse(read('hmz-painted') || '[]')]
    } catch {
      // Unreadable is as good as none: Humanize's own are left.
    }
    const base = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    const pair = read('hmz-pair') || 'humanize'
    const theme = shown || made.find((one) => one.pair === pair && one.base === base) || { id: base, base, colors: {} }
    const root = document.documentElement
    for (const name of [...root.style]) if (name.startsWith('--')) root.style.removeProperty(name)
    root.dataset.theme = theme.base
    for (const [name, value] of Object.entries(theme.colors || {})) root.style.setProperty(`--${name}`, value)
    return theme
  }
  window.hmzPaint()
  const agent = navigator.userAgent
  if (/\bhumanize-desktop\//.test(agent)) document.documentElement.dataset.shell = /\bWindows NT\b/.test(agent) ? 'windows' : 'macos'
})()
