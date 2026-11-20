// How the page looks: every theme Humanize comes with and every one made here, each a light
// and a dark chosen as one -- the system says which of the two is shown -- and one made here
// opened to be changed: its name, each of its two sides' colours and a picture behind any of
// the large planes, shown on the page as it is changed and kept at once, and written out as a
// `.hmztheme` file. A theme of the user's own is made of the one in use, or read in from a file.

import { hash } from '../../api.js'
import { confirming } from '../../confirm.js'
import { fill, h, iconButton, problem } from '../../dom.js'
import { t } from '../../i18n.js'
import { menuOn, toast } from '../../ui.js'
import * as look from '../../themes.js'

/** The names of the themes Humanize comes with, as the page's language says them. */
const NAMES = {
  'Humanize Green': t('Humanize Green'),
  'Temperate Gold': t('Temperate Gold'),
  'Concordant Scarlet': t('Concordant Scarlet'),
  'Restrained Crimson': t('Restrained Crimson'),
  'Critical Teal': t('Critical Teal'),
  'Desirous Indigo': t('Desirous Indigo'),
  'Peaceful Lilac': t('Peaceful Lilac'),
  'Hateful Silver': t('Hateful Silver'),
  'Devoted Pink': t('Devoted Pink'),
  'Self-Negating Plum': t('Self-Negating Plum'),
  'Dominant Azure': t('Dominant Azure'),
  'Surviving Jade': t('Surviving Jade'),
  'Lamenting Orchid': t('Lamenting Orchid'),
}

/** What a theme is called: one made here as the user named it. */
const called = (one) => (one.mine ? one.name : NAMES[one.name] || one.name)

export function draw(holder, query, parts) {
  if (parts[2]) return editor(holder, parts[2])
  list(holder)
}

function list(holder) {
  const file = h('input', { type: 'file', accept: '.hmztheme,application/json', hidden: true, 'data-hmz': 'theme-file' })
  file.addEventListener('change', async () => {
    const [chosen] = file.files
    file.value = ''
    if (!chosen) return
    try {
      const [one] = await look.imported(await chosen.text())
      toast(t('Imported {name}', { name: one.name }))
      redraw()
    } catch (error) {
      toast(error.message)
    }
  })
  // A theme of the user's own, of both sides of the one in use, opened on the side now shown.
  const fresh = async () => {
    const [one] = await look.create(look.sides(look.chosen()), t('New theme'))
    location.hash = hash(`/settings/themes/${look.shown(one.pair).id}`)
  }
  const use = (key) => {
    look.choose(key)
    redraw()
  }
  const row = (one) => {
    const on = look.chosen() === one.key
    const name = called(one)
    const edit = one.mine ? hash(`/settings/themes/${look.shown(one.key).id}`) : null
    const node = h(
      'div',
      { class: ['theme-row', on && 'chosen'], 'data-hmz': 'theme', 'data-key': one.key },
      h('div', { class: 'theme-sides' }, look.sides(one.key).map(swatch)),
      h('div', { class: 'theme-name' }, h('b', {}, name), on ? h('span', { class: 'dim' }, t('In use')) : null),
      h(
        'div',
        { class: 'row' },
        h('button', { class: 'btn small', type: 'button', disabled: on, onclick: () => use(one.key) }, t('Use')),
        edit ? h('a', { class: 'btn quiet small', href: edit }, t('Edit')) : null,
        edit ? confirming({ label: t('Delete'), ask: t('Delete {name}?', { name }), yes: t('Delete'), small: true, act: () => look.remove(one.key).then(redraw) }) : null,
      ),
    )
    return menuOn(node, () => [{ head: name }, { label: t('Use'), glyph: 'check', act: () => use(one.key) }, edit ? { label: t('Edit'), glyph: 'new', href: edit } : null])
  }
  const redraw = () => {
    const all = look.themes()
    const mine = all.filter((one) => one.mine)
    fill(
      holder,
      h('section', { class: 'panel', 'data-hmz': 'presets' }, h('header', {}, h('h2', {}, t('Presets'))), h('div', { class: 'theme-list' }, all.filter((one) => !one.mine).map(row))),
      h(
        'section',
        { class: 'panel', 'data-hmz': 'custom' },
        h(
          'header',
          {},
          h('h2', {}, t('Custom')),
          h(
            'div',
            { class: 'row' },
            h('button', { class: 'btn small', type: 'button', onclick: fresh }, t('New')),
            h('button', { class: 'btn quiet small', type: 'button', onclick: () => file.click() }, t('Import')),
            file,
          ),
        ),
        mine.length ? h('div', { class: 'theme-list' }, mine.map(row)) : h('p', { class: 'dim' }, t('No custom themes yet.')),
      ),
    )
  }
  redraw()
}

/** A side drawn small: its page, sidebar, text and accents, in its own colours. */
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

/** One side of a theme made here, by its id, opened to be changed; the other a press away. */
function editor(holder, id) {
  const one = look.side(id)
  if (!one || look.OWN.includes(one)) {
    fill(holder, problem(t('No such theme')), h('p', { class: 'row' }, h('a', { class: 'btn', href: hash('/settings/themes') }, t('Themes'))))
    return
  }
  // What the side's colours are where it sets none: Humanize's own for that side.
  const probe = h('div', { 'data-theme': one.base, hidden: true })
  const fallback = (token) => getComputedStyle(probe).getPropertyValue(`--${token}`).trim()
  const changed = () => {
    look.save(one)
    look.paint(one)
  }
  const name = h('input', { type: 'text', value: one.name, 'aria-label': t('Name'), 'data-hmz': 'theme-name', maxlength: '60' })
  // A theme's name is both its sides'.
  name.addEventListener('input', () => {
    if (!name.value.trim()) return
    one.name = name.value.trim()
    look.rename(one.pair, one.name)
  })
  const sides = h(
    'div',
    { class: 'segmented', role: 'group', 'aria-label': t('Side'), 'data-hmz': 'theme-side' },
    look.sides(one.pair).map((other) =>
      h('button', { type: 'button', 'aria-pressed': String(other.id === one.id), onclick: () => (location.hash = hash(`/settings/themes/${other.id}`)) }, other.base === 'dark' ? t('Dark') : t('Light')),
    ),
  )
  const colour = (token, label) => {
    const text = h('input', { type: 'text', value: one.colors[token] || '', placeholder: fallback(token), spellcheck: 'false', 'aria-label': label, 'data-hmz': `colour-${token}` })
    const pick = h('input', { type: 'color', value: hex(one.colors[token] || fallback(token)), 'aria-label': t('{name} picker', { name: label }) })
    const reset = iconButton('close', t('Reset {name}', { name: label }), { class: 'theme-reset' })
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
  const tints = h('div', { class: 'theme-colours' })
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
    const fit = h('select', { 'aria-label': t('{name} fit', { name: label }), disabled: !data }, Object.entries(look.FITS).map(([key, said]) => h('option', { value: key, selected: (one.images[area]?.fit || 'cover') === key }, said)))
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
        h('button', { class: 'btn small', type: 'button', onclick: () => file.click() }, data ? t('Replace') : t('Choose')),
        fit,
        data
          ? h('button', { class: 'btn quiet small', type: 'button', onclick: async () => {
              await look.picture(one.id, area, null)
              delete one.images[area]
              changed()
              pictures()
            } }, t('Remove'))
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
        h('div', { class: 'field' }, h('span', { class: 'label' }, t('Name')), name),
        h('div', { class: 'field' }, h('span', { class: 'label' }, t('Side')), sides, h('span', { class: 'hint' }, t('Light is shown where the system is light, Dark where it is dark.'))),
        h(
          'div',
          { class: 'row' },
          h('a', { class: 'btn', href: hash('/settings/themes') }, t('Done@@button')),
          h('button', { class: 'btn quiet', type: 'button', onclick: () => (look.choose(one.pair), look.paint(one), toast(t('Using {name}', { name: one.name }))) }, t('Use')),
          h('button', { class: 'btn quiet', type: 'button', onclick: () => look.exported(one.pair) }, t('Export')),
          confirming({ label: t('Delete'), ask: t('Delete {name}?', { name: one.name }), yes: t('Delete'), act: () => look.remove(one.pair).then(() => (location.hash = hash('/settings/themes'))) }),
        ),
      ),
    ),
    tints,
    h('section', { class: 'panel' }, h('header', {}, h('h2', {}, t('Pictures'))), h('p', { class: 'dim' }, t('Behind each large plane: a still picture, a GIF, or an SVG, moving or not.')), planes),
  )
  // Drawn once the probe is in the page: only there has it colours to be asked.
  fill(
    tints,
    look.COLOURS.map(([group, tokens]) => h('section', { class: 'panel' }, h('header', {}, h('h2', {}, group)), h('div', { class: 'theme-grid' }, tokens.map(([token, label]) => colour(token, label))))),
  )
  pictures()
  look.paint(one)
  // Left, the page is drawn in the theme chosen again.
  return () => look.paint()
}
