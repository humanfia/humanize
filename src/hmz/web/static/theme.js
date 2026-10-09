// The theme, set before the page is drawn so it never flashes the other one: the one chosen
// here, kept in this browser, or the system's where none was chosen.
(() => {
  const chosen = localStorage.getItem('hmz-theme')
  const dark = chosen ? chosen === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches
  document.documentElement.dataset.theme = dark ? 'dark' : 'light'
})()
