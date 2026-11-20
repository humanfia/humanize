// The language this browser's page is written in: the system's, as the browser asks for it, or
// one of the three the page has. This browser's own, kept in its storage, never a daemon's.
// Chosen, it is kept and the page opens again where it was, written in it: lang.js reads the
// choice before anything is drawn.

import { fill, h } from '../../dom.js'
import { LANGUAGES, choose, chosen, t } from '../../i18n.js'

export function draw(holder) {
  const picker = h(
    'select',
    { id: 'language', 'data-hmz': 'language' },
    // A language is called what it calls itself, whatever the page is written in; only `System` is the page's word.
    LANGUAGES.map(([code, name]) => h('option', { value: code, selected: code === chosen(), lang: code || null }, code ? name : t('System'))),
  )
  picker.addEventListener('change', () => {
    choose(picker.value)
    location.reload()
  })
  fill(
    holder,
    h(
      'section',
      { class: 'panel' },
      h(
        'div',
        { class: 'form' },
        h(
          'div',
          { class: 'field' },
          h('label', { class: 'label', for: 'language' }, t('Language')),
          picker,
          h('span', { class: 'hint' }, t('System follows the language this browser asks for. What a daemon, a flow or an agent wrote stays as it was written.')),
        ),
      ),
    ),
  )
}
