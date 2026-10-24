// Which notifications may appear, of every daemon at once: an epic done, failed or stopped, a
// question to you, a chat turn over -- and whether they are shown by the system as well as on
// the page. This app's own, kept on this machine, never a daemon's. A browser shows them only
// once you allow it, from a click here; Humanize Desktop needs nothing more.

import { get, post } from '../../api.js'
import { empty, fill, h, problem } from '../../dom.js'
import { inApp } from '../../shell.js'

/** Every kind, by its word in the settings, and what the page calls it. */
const KINDS = [
  ['done', 'Done'],
  ['failed', 'Failed'],
  ['stopped', 'Stopped'],
  ['asked', 'Questions'],
  ['listening', 'Chat turns'],
]

/** What the browser says of showing notifications, as the page says it. */
const PERMISSIONS = { granted: 'Allowed', denied: 'Blocked', default: 'Not asked' }

export function draw(holder) {
  const shown = (settings) => {
    const kinds = { ...Object.fromEntries(KINDS.map(([kind]) => [kind, true])), ...(settings.kinds || {}) }
    let system = settings.system !== false
    const said = h('span', { class: 'hint', 'aria-live': 'polite', 'data-hmz': 'notifications-said' })
    const save = async () => {
      said.replaceChildren()
      try {
        await post('/api/notifications/settings', { kinds, system })
        said.textContent = 'Saved'
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
    const drawAllowing = () => {
      if (inApp) return fill(allowing)
      if (!('Notification' in window)) return fill(allowing, h('span', { class: 'dim' }, 'Unsupported'))
      const now = Notification.permission
      fill(
        allowing,
        h('span', { class: 'dim', 'data-hmz': 'permission-state' }, PERMISSIONS[now] || now),
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
              'Allow',
            ),
      )
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
            h('span', { class: 'label' }, 'Kinds'),
            h(
              'div',
              { class: 'notification-kinds' },
              KINDS.map(([kind, label]) => toggle(label, kinds[kind], (on) => (kinds[kind] = on), `notify-${kind}`)),
            ),
            h('span', { class: 'hint' }, 'Of every daemon, as they happen.'),
          ),
          h(
            'div',
            { class: 'field' },
            h('span', { class: 'label' }, 'System'),
            toggle('On', system, (on) => (system = on), 'notify-system'),
            allowing,
            h('span', { class: 'hint' }, inApp ? 'Shown by macOS while the window is away.' : 'Shown by the browser while the page is away.'),
          ),
          said,
        ),
      ),
    )
  }
  get('/api/notifications/settings')
    .then(shown)
    .catch((error) => fill(holder, error.status === 404 ? empty('Unavailable', 'This Humanize does not keep notifications.') : problem(error)))
}
