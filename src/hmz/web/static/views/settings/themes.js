// How the page looks: the pair -- or any two themes -- Auto follows the system with, every pair
// humanize comes with and every theme made here -- used, copied, written out as a `.hmztheme`
// file or read in from one -- and one made here opened to be changed: its name, what it is made
// on, each of its colours and a picture behind any of the large planes, shown on the page as it
// is changed and kept at once.

import { confirming, fill, h, iconButton, problem } from '../../dom.js'
import { choice, menu } from '../../shell.js'
import { menuOn, toast } from '../../ui.js'
import * as look from '../../themes.js'

export function draw(holder, query, parts) {
  if (parts[2]) return editor(holder, parts[2])
  list(holder)
}

/** The theme shown now: the one chosen, or the one Auto shows for the system as it is. */
function shown() {
  const id = look.chosen()
  if (id !== 'auto') return look.theme(id) || look.OWN[0]
  return look.theme(look.paired()[matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'])
}

function list(holder) {
  const auto = () => look.chosen() === 'auto'
  // The pair Auto follows the system with, set at once; or its light and its dark apart.
  const pairs = () => {
    const now = look.pairing()
    const select = h(
      'select',
      { 'aria-label': 'Auto pair', 'data-hmz': 'auto-pair' },
      now ? null : h('option', { value: '', selected: true, disabled: true }, 'Custom'),
      look.PAIRS.map((one) => h('option', { value: one.key, selected: now === one.key }, one.name)),
    )
    select.addEventListener('change', () => {
      look.usePair(select.value)
      redraw()
    })
    return select
  }
  const pick = (scheme) => {
    const select = h('select', { 'aria-label': `Auto ${scheme}`, 'data-hmz': `auto-${scheme}` }, look.themes().map((one) => h('option', { value: one.id, selected: look.paired()[scheme] === one.id }, look.label(one))))
    select.addEventListener('change', () => {
      look.pair(scheme, select.value)
      redraw()
    })
    return select
  }
  const file = h('input', { type: 'file', accept: '.hmztheme,application/json', hidden: true, 'data-hmz': 'theme-file' })
  file.addEventListener('change', async () => {
    const [chosen] = file.files
    file.value = ''
    if (!chosen) return
    try {
      const one = await look.imported(await chosen.text())
      toast(`Imported ${one.name}`)
      redraw()
    } catch (error) {
      toast(error.message)
    }
  })
  const fresh = async (from, name) => {
    const one = await look.create(from, name)
    location.hash = `/settings/themes/${one.id}`
  }
  const use = (one) => {
    look.choose(one.id)
    redraw()
  }
  // What can be done to one theme humanize comes with or one made here.
  const offered = (one) => [
    { head: look.label(one) },
    { label: 'Use', glyph: 'check', act: () => use(one) },
    look.OWN.includes(one) ? null : { label: 'Edit', glyph: 'new', href: `#/settings/themes/${one.id}` },
    { label: 'Duplicate', glyph: 'copy', act: () => fresh(one, `${one.name} copy`) },
    { label: 'Export', glyph: 'download', act: () => look.exported(one) },
  ]
  // A button opening a choice of the pair's light or dark, for something done to one of them.
  const either = (label, two, act) => {
    const button = h('button', { class: 'btn quiet small', type: 'button', 'aria-label': label }, label)
    const holding = h('span', { class: 'menu-holder' }, button)
    menu(button, (close) => two.map((one) => choice({ label: one.base === 'dark' ? 'Dark' : 'Light', act: () => act(one), close })), { label, align: 'end' })
    return holding
  }
  const pairRow = (pair) => {
    const two = look.OWN.filter((one) => one.pair === pair.key)
    const on = auto() && look.pairing() === pair.key
    const node = h(
      'div',
      { class: ['theme-row', on && 'chosen'], 'data-hmz': 'pair', 'data-key': pair.key },
      two.map((one) =>
        menuOn(
          h('button', { class: ['theme-swatch-button', look.chosen() === one.id && 'chosen'], type: 'button', title: `Use ${look.label(one)}`, 'aria-label': `Use ${look.label(one)}`, onclick: () => use(one) }, swatch(one)),
          () => offered(one),
        ),
      ),
      h('div', { class: 'theme-name' }, h('b', {}, pair.name), h('span', { class: 'dim' }, pair.heir || 'humanize', on ? ' · In use' : '')),
      h(
        'div',
        { class: 'row' },
        h('button', { class: 'btn small', type: 'button', disabled: on, onclick: () => (look.usePair(pair.key), redraw()) }, 'Use pair'),
        either('Duplicate', two, (one) => fresh(one, `${pair.name} copy`)),
        either('Export', two, (one) => look.exported(one)),
      ),
    )
    return menuOn(node, () => [{ head: pair.name }, { label: 'Use pair', glyph: 'check', act: () => (look.usePair(pair.key), redraw()) }])
  }
  const row = (one) => {
    const on = look.chosen() === one.id
    const node = h(
      'div',
      { class: ['theme-row', on && 'chosen'], 'data-hmz': 'theme', 'data-id': one.id },
      swatch(one),
      h('div', { class: 'theme-name' }, h('b', {}, one.name), h('span', { class: 'dim' }, one.base === 'dark' ? 'Dark' : 'Light', on ? ' · In use' : '')),
      h(
        'div',
        { class: 'row' },
        h('button', { class: 'btn small', type: 'button', disabled: on, onclick: () => use(one) }, 'Use'),
        h('a', { class: 'btn quiet small', href: `#/settings/themes/${one.id}` }, 'Edit'),
        h('button', { class: 'btn quiet small', type: 'button', onclick: () => fresh(one, `${one.name} copy`) }, 'Duplicate'),
        h('button', { class: 'btn quiet small', type: 'button', onclick: () => look.exported(one) }, 'Export'),
        confirming({ label: 'Delete', ask: `Delete ${one.name}?`, yes: 'Delete', small: true, act: () => look.remove(one.id).then(redraw) }),
      ),
    )
    return menuOn(node, () => offered(one))
  }
  const redraw = () => {
    const mine = look.themes().filter((one) => !look.OWN.includes(one))
    fill(
      holder,
      h(
        'section',
        { class: 'panel', 'data-hmz': 'theme-auto' },
        h('header', {}, h('h2', {}, 'Auto')),
        h(
          'div',
          { class: 'form' },
          h('div', { class: 'field' }, h('span', { class: 'label' }, 'Pair'), pairs(), h('span', { class: 'hint' }, 'A light and a dark at once, or each below.')),
          h('div', { class: 'field' }, h('span', { class: 'label' }, 'Light'), pick('light')),
          h('div', { class: 'field' }, h('span', { class: 'label' }, 'Dark'), pick('dark'), h('span', { class: 'hint' }, 'Under Auto, the page follows the system with these.')),
          h('div', { class: 'row' }, h('button', { class: 'btn small', type: 'button', disabled: auto(), onclick: () => (look.choose('auto'), redraw()) }, auto() ? 'In use' : 'Use Auto')),
        ),
      ),
      h('section', { class: 'panel', 'data-hmz': 'pairs' }, h('header', {}, h('h2', {}, 'Presets')), h('div', { class: 'theme-list' }, look.PAIRS.map(pairRow))),
      h(
        'section',
        { class: 'panel', 'data-hmz': 'themes' },
        h(
          'header',
          {},
          h('h2', {}, 'Yours'),
          h('div', { class: 'row' }, h('button', { class: 'btn small', type: 'button', onclick: () => fresh(shown(), 'New theme') }, 'New'), h('button', { class: 'btn quiet small', type: 'button', onclick: () => file.click() }, 'Import'), file),
        ),
        mine.length ? h('div', { class: 'theme-list' }, mine.map(row)) : h('p', { class: 'dim' }, 'None yet: make one, duplicate a preset or import a file.'),
      ),
    )
  }
  redraw()
}

/** A theme drawn small: its page, sidebar, text and accents, in its own colours. */
function swatch(one) {
  const node = h(
    'div',
    { class: 'theme-swatch', 'data-theme': one.base, 'aria-hidden': 'true', style: Object.fromEntries(Object.entries(one.colors).map(([token, value]) => [`--${token}`, value])) },
    h('span', { class: 'theme-swatch-side' }),
    h('span', { class: 'theme-swatch-text' }, 'Aa'),
    h('span', { class: 'theme-swatch-dots' }, h('i', { style: { background: 'var(--cyan)' } }), h('i', { style: { background: 'var(--pink)' } }), h('i', { style: { background: 'var(--green)' } })),
  )
  if (one.images?.page)
    look.picture(one.id, 'page').then((data) => data && node.style.setProperty('background-image', `url("${data}")`), () => {})
  return node
}

/** A colour as the browser draws it: red, green, blue and alpha, each of 255. */
const pixel = document.createElement('canvas').getContext('2d', { willReadFrequently: true })
function rgba(colour) {
  pixel.clearRect(0, 0, 1, 1)
  pixel.fillStyle = '#000'
  pixel.fillStyle = colour
  pixel.fillRect(0, 0, 1, 1)
  return [...pixel.getImageData(0, 0, 1, 1).data]
}

function hex(colour) {
  return `#${rgba(colour).slice(0, 3).map((n) => n.toString(16).padStart(2, '0')).join('')}`
}

function editor(holder, id) {
  const one = look.theme(id)
  if (!one || look.OWN.includes(one)) {
    fill(holder, problem('No such theme'), h('p', { class: 'row' }, h('a', { class: 'btn', href: '#/settings/themes' }, 'Themes')))
    return
  }
  // What the theme's colours are where it sets none: its base's, as a theme on it works them out.
  const probe = h('div', { 'data-theme': one.base, hidden: true })
  const fallback = (token) => getComputedStyle(probe).getPropertyValue(`--${token}`).trim()
  const changed = () => {
    look.save(one)
    look.paint(one)
  }
  const name = h('input', { type: 'text', value: one.name, 'aria-label': 'Name', 'data-hmz': 'theme-name', maxlength: '60' })
  name.addEventListener('input', () => {
    if (!name.value.trim()) return
    one.name = name.value.trim()
    look.save(one)
  })
  const base = h('select', { 'aria-label': 'Base', 'data-hmz': 'theme-base' }, h('option', { value: 'light', selected: one.base === 'light' }, 'Light'), h('option', { value: 'dark', selected: one.base === 'dark' }, 'Dark'))
  base.addEventListener('change', () => {
    one.base = probe.dataset.theme = base.value
    changed()
    colours()
  })
  const tints = h('div', { class: 'theme-colours' })
  const colours = () =>
    fill(
      tints,
      look.COLOURS.map(([group, tokens]) =>
        h('section', { class: 'panel' }, h('header', {}, h('h2', {}, group)), h('div', { class: 'theme-grid' }, tokens.map(([token, label]) => colour(token, label)))),
      ),
    )
  const colour = (token, label) => {
    const text = h('input', { type: 'text', value: one.colors[token] || '', placeholder: fallback(token), spellcheck: 'false', 'aria-label': label, 'data-hmz': `colour-${token}` })
    const pick = h('input', { type: 'color', value: hex(one.colors[token] || fallback(token)), 'aria-label': `${label} picker` })
    const reset = iconButton('close', `Reset ${label}`, { class: 'theme-reset' })
    const set = (value) => {
      if (value) one.colors[token] = value
      else delete one.colors[token]
      reset.hidden = !value
      changed()
    }
    // Picked, a colour keeps how see-through the one it replaces was.
    pick.addEventListener('input', () => {
      const alpha = rgba(text.value || fallback(token))[3]
      const [r, g, b] = rgba(pick.value)
      text.value = alpha === 255 ? pick.value : `rgba(${r}, ${g}, ${b}, ${(alpha / 255).toFixed(2)})`
      text.removeAttribute('aria-invalid')
      set(text.value)
    })
    text.addEventListener('input', () => {
      const value = text.value.trim()
      if (value && !look.isColour(value)) return text.setAttribute('aria-invalid', 'true')
      text.removeAttribute('aria-invalid')
      pick.value = hex(value || fallback(token))
      set(value)
    })
    reset.addEventListener('click', () => {
      text.value = ''
      text.removeAttribute('aria-invalid')
      pick.value = hex(fallback(token))
      set('')
    })
    reset.hidden = !one.colors[token]
    return h('label', { class: 'theme-colour' }, h('span', { class: 'label' }, label), h('span', { class: 'theme-colour-row' }, pick, text, reset))
  }
  const planes = h('div', { class: 'theme-grid' })
  const pictures = async () => {
    const read = await Promise.all(look.AREAS.map(([area]) => (one.images[area] ? look.picture(one.id, area).catch(() => null) : null)))
    fill(planes, look.AREAS.map(([area, label], at) => plane(area, label, read[at])))
  }
  const plane = (area, label, data) => {
    const file = h('input', { type: 'file', accept: 'image/*,.svg', hidden: true, 'data-hmz': `picture-${area}` })
    file.addEventListener('change', async () => {
      const [chosen] = file.files
      file.value = ''
      if (!chosen) return
      try {
        await look.picture(one.id, area, await look.readPicture(chosen))
        one.images[area] = { fit: one.images[area]?.fit || 'cover' }
        changed()
        pictures()
      } catch (error) {
        toast(error.message)
      }
    })
    const fit = h('select', { 'aria-label': `${label} fit`, disabled: !data }, Object.entries(look.FITS).map(([key, said]) => h('option', { value: key, selected: (one.images[area]?.fit || 'cover') === key }, said)))
    fit.addEventListener('change', () => {
      one.images[area] = { fit: fit.value }
      changed()
    })
    const thumb = h('span', { class: ['theme-thumb', !data && 'none'] })
    if (data) thumb.style.setProperty('background-image', `url("${data}")`)
    return h(
      'div',
      { class: 'field', 'data-hmz': `plane-${area}` },
      h('span', { class: 'label' }, label),
      h(
        'div',
        { class: 'row' },
        thumb,
        h('button', { class: 'btn small', type: 'button', onclick: () => file.click() }, data ? 'Replace' : 'Choose'),
        fit,
        data
          ? h('button', { class: 'btn quiet small', type: 'button', onclick: async () => {
              await look.picture(one.id, area, null)
              delete one.images[area]
              changed()
              pictures()
            } }, 'Remove')
          : null,
        file,
      ),
    )
  }
  fill(
    holder,
    probe,
    h(
      'section',
      { class: 'panel', 'data-hmz': 'theme-editor' },
      h(
        'div',
        { class: 'form' },
        h('div', { class: 'field' }, h('span', { class: 'label' }, 'Name'), name),
        h('div', { class: 'field' }, h('span', { class: 'label' }, 'Base'), base, h('span', { class: 'hint' }, 'What any colour left blank is taken from.')),
        h(
          'div',
          { class: 'row' },
          h('a', { class: 'btn', href: '#/settings/themes' }, 'Done'),
          h('button', { class: 'btn quiet', type: 'button', onclick: () => (look.choose(one.id), toast(`Using ${one.name}`)) }, 'Use'),
          h('button', { class: 'btn quiet', type: 'button', onclick: () => look.exported(one) }, 'Export'),
          confirming({ label: 'Delete', ask: `Delete ${one.name}?`, yes: 'Delete', act: () => look.remove(one.id).then(() => (location.hash = '/settings/themes')) }),
        ),
      ),
    ),
    tints,
    h('section', { class: 'panel' }, h('header', {}, h('h2', {}, 'Pictures')), h('p', { class: 'dim' }, 'Behind each large plane: a still picture, a GIF, or an SVG, moving or not.'), planes),
  )
  colours()
  pictures()
  look.paint(one)
  // Left, the page is drawn in the theme chosen again.
  return () => look.paint()
}
