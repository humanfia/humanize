// Which notifications may appear, of every daemon at once: an epic done, failed or stopped, a
// question to you, a chat turn over -- and whether the system shows them. This browser's own,
// kept in its storage, never a daemon's. A browser shows them only once you allow it, from a
// click here; Humanize Desktop needs nothing more.

import { fill, h, problem } from '../../dom.js'
import { t } from '../../i18n.js'
import { kept } from '../../notifications.js'
import { inApp, shell } from '../../shell.js'

/** Every kind, by its word in the settings, and what the page calls it. */
const KINDS = [
  ['done', t('Done')],
  ['failed', t('Failed')],
  ['stopped', t('Stopped')],
  ['asked', t('Questions')],
  ['listening', t('Waiting')],
]

/** What the browser says of showing notifications, as the page says it. */
const PERMISSIONS = { granted: t('Allowed'), denied: t('Blocked'), default: t('Not asked') }

/** Who shows them in a browser, by what it says of showing them: none where it has no way to. */
const SHOWN = {
  granted: t('Shown by the browser.'),
  denied: t('Blocked in this browser’s settings for this site: allow them there.'),
  default: t('Shown by the browser, once you allow it.'),
  none: t('This browser shows none.'),
}

export function draw(holder) {
  const shown = (settings) => {
    const kinds = { ...Object.fromEntries(KINDS.map(([kind]) => [kind, true])), ...(settings.kinds || {}) }
    let system = settings.system !== false
    const said = h('span', { class: 'hint', 'aria-live': 'polite', 'data-hmz': 'notifications-said' })
    const save = async () => {
      said.replaceChildren()
      try {
        await kept.prefer({ kinds, system })
        said.textContent = t('Saved')
      } catch (error) {
        said.replaceChildren(problem(error))
      }
    }
    const toggle = (label, checked, changed, hook) => {
      const box = h('input', { type: 'checkbox', checked, 'data-hmz': hook })
      box.addEventListener('change', () => {
        changed(box.checked)
        save()
      })
      return h('label', { class: 'check' }, box, label)
    }
    const allowing = h('div', { class: 'row', 'data-hmz': 'notifications-permission' })
    const shownBy = h('span', { class: 'hint', 'data-hmz': 'notifications-shown-by' }, inApp ? t('Shown by {system}.', { system: shell === 'windows' ? 'Windows' : 'macOS' }) : '')
    const drawAllowing = () => {
      if (inApp) return fill(allowing)
      shownBy.textContent = 'Notification' in window ? SHOWN[Notification.permission] || SHOWN.default : SHOWN.none
      if (!('Notification' in window)) return fill(allowing, h('span', { class: 'dim' }, t('Unsupported')))
      const now = Notification.permission
      // `Allow` goes once it is answered: the focus it held is kept on it, or on what says the answer.
      const held = allowing.contains(document.activeElement)
      fill(
        allowing,
        h('span', { class: 'dim', 'data-hmz': 'permission-state', tabindex: '-1' }, PERMISSIONS[now] || now),
        now === 'granted' || now === 'denied'
          ? null
          : h(
              'button',
              {
                class: 'btn small',
                type: 'button',
                'data-hmz': 'allow-notifications',
                onclick: async () => {
                  try {
                    // A promise where it is one; older Safari answers by calling back instead.
                    await Notification.requestPermission(drawAllowing)
                  } finally {
                    drawAllowing()
                  }
                },
              },
              t('Allow'),
            ),
      )
      if (held && !allowing.contains(document.activeElement)) allowing.querySelector('[data-hmz=allow-notifications], [data-hmz=permission-state]').focus()
    }
    drawAllowing()
    fill(
      holder,
      h(
        'section',
        { class: 'panel notification-settings' },
        h(
          'div',
          { class: 'form' },
          h(
            'div',
            { class: 'field' },
            h('span', { class: 'label' }, t('Kinds')),
            h(
              'div',
              { class: 'notification-kinds' },
              KINDS.map(([kind, label]) => toggle(label, kinds[kind], (on) => (kinds[kind] = on), `notify-${kind}`)),
            ),
            h('span', { class: 'hint' }, t('Of every daemon, as they happen.')),
          ),
          h(
            'div',
            { class: 'field' },
            h('span', { class: 'label' }, t('System@@notifications')),
            toggle(t('On'), system, (on) => (system = on), 'notify-system'),
            allowing,
            shownBy,
          ),
          said,
        ),
      ),
    )
  }
  kept
    .preferences()
    .then(shown)
    .catch((error) => fill(holder, problem(error)))
}
