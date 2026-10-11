// The theme, set before the page is drawn so it never flashes the other one: the one chosen
// here, kept in this browser, or the system's where none was chosen. And whether the page is
// the macOS app's window, which says so in its user agent: there the page draws its top row
// around the window's traffic lights.
(() => {
  const chosen = localStorage.getItem('hmz-theme')
  const dark = chosen ? chosen === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
  if (/\bhumanize-desktop\//.test(navigator.userAgent)) document.documentElement.dataset.shell = 'macos'
})()
