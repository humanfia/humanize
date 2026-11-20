// The language the page is written in, set before the page is drawn so that nothing is drawn in
// another: the one chosen in this browser (Settings > App > Language), or, where none was, the
// first the browser asks for that the page has -- Traditional Chinese for `zh-Hant`, Taiwan,
// Hong Kong and Macao, Simplified Chinese for any other Chinese, English for everything else.
// It is said on the document itself, `<html lang>`, which is where i18n.js reads it; and the
// browser's own tag of that language is kept beside it, so that a date is written as that
// region writes it.
(() => {
  const HAS = ['en', 'zh-Hans', 'zh-Hant']
  /** The language of the page a tag of the browser's asks for, or none. */
  const spoken = (tag) => {
    const said = String(tag || '').toLowerCase()
    if (said === 'en' || said.startsWith('en-')) return 'en'
    if (said !== 'zh' && !said.startsWith('zh-')) return ''
    return /-(hant|tw|hk|mo)\b/.test(said) && !/-hans\b/.test(said) ? 'zh-Hant' : 'zh-Hans'
  }
  /**
   * What the page is written in: `chosen`, the choice kept or `''` under System; `language`,
   * one of the three; `locale`, the tag dates are written by.
   */
  window.hmzLanguage = () => {
    let chosen = ''
    try {
      chosen = localStorage.getItem('hmz-language') || ''
    } catch {
      // A browser that keeps nothing follows the system.
    }
    if (!HAS.includes(chosen)) chosen = ''
    const asked = [...(navigator.languages || []), navigator.language].filter(Boolean)
    // The first tag the page has a language for decides: one in a language it has not is passed over.
    const language = chosen || asked.map(spoken).find(Boolean) || 'en'
    const locale = asked.find((tag) => spoken(tag) === language) || language
    document.documentElement.lang = language
    document.documentElement.dataset.locale = locale
    return { chosen, language, locale }
  }
  window.hmzLanguage()
})()
