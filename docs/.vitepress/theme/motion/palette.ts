// The site's colours, resolved for a canvas. SVG and CSS take `var(--hmz-lane-1)` as it is and
// follow the theme by themselves; a canvas needs the colour itself, and needs it again when the
// reader switches between light and dark. `palette` is that: one object, kept current, cheap to
// read every frame. Every field is a token from `style.css`; none is a colour of its own.
import { onMounted, onUnmounted } from 'vue'

export interface Palette {
  lane: string[]
  accent: string
  accent2: string
  warm: string
  ink: string
  dim: string
  danger: string
  dark: boolean
  /** A stage's hairline, its card fill and its graph paper. */
  line: string
  card: string
  grid: string
  /** How a run ends. */
  done: string
  fail: string
  budget: string
  /** The constructivist red: the one thing on the screen to look at. */
  red: string
  /** What a role in a flow is. */
  role: { maker: string; partner: string; checker: string; steward: string; program: string }
}

export function usePalette(): Palette {
  const palette: Palette = {
    lane: ['#4a90d9', '#14b8a6', '#a855f7', '#e0803a', '#d94a6a', '#8b93a7'],
    accent: '#14b8a6',
    accent2: '#a855f7',
    warm: '#e0803a',
    ink: '#13233a',
    dim: '#5d6f86',
    danger: '#d94a6a',
    dark: false,
    line: 'rgba(42, 110, 166, 0.2)',
    card: 'rgba(255, 255, 255, 0.86)',
    grid: 'rgba(42, 110, 166, 0.07)',
    done: '#16a34a',
    fail: '#dc2626',
    budget: '#ca8a04',
    red: '#d6331f',
    role: { maker: '#2f7fe0', partner: '#0891b2', checker: '#7c3aed', steward: '#db2777', program: '#64748b' },
  }
  let watch: MutationObserver | undefined

  function read() {
    const css = getComputedStyle(document.documentElement)
    const get = (name: string) => css.getPropertyValue(name).trim()
    palette.lane = [1, 2, 3, 4, 5, 6].map((i) => get(`--hmz-lane-${i}`))
    palette.accent = get('--hmz-accent')
    palette.accent2 = get('--hmz-accent-2')
    palette.warm = get('--hmz-warm')
    palette.ink = get('--hmz-stage-ink')
    palette.dim = get('--hmz-stage-dim')
    palette.danger = get('--vp-c-danger-1') || palette.lane[4]
    palette.dark = document.documentElement.classList.contains('dark')
    palette.line = get('--hmz-stage-line')
    palette.card = get('--hmz-stage-card')
    palette.grid = get('--hmz-stage-grid-major')
    palette.done = get('--hmz-done')
    palette.fail = get('--hmz-fail')
    palette.budget = get('--hmz-budget')
    palette.red = get('--hmz-red')
    palette.role = {
      maker: get('--hmz-role-maker'),
      partner: get('--hmz-role-partner'),
      checker: get('--hmz-role-checker'),
      steward: get('--hmz-role-steward'),
      program: get('--hmz-role-program'),
    }
  }

  onMounted(() => {
    read()
    watch = new MutationObserver(read)
    watch.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
  })
  onUnmounted(() => watch?.disconnect())

  return palette
}

/**
 * A colour at an opacity, for a canvas: `withAlpha(palette.red, 0.3)`. Takes the forms the
 * tokens are written in -- `#rgb`, `#rrggbb`, `#rrggbbaa`, `rgb()` and `rgba()` -- and
 * multiplies an alpha the colour already has. Anything else comes back as it is.
 */
export function withAlpha(color: string, alpha: number): string {
  const c = color.trim()
  const a = Math.max(0, Math.min(1, alpha))
  const hex = /^#([0-9a-f]{3,8})$/i.exec(c)
  if (hex) {
    let h = hex[1]
    if (h.length === 3 || h.length === 4) h = [...h].map((d) => d + d).join('')
    if (h.length !== 6 && h.length !== 8) return c
    const n = (i: number) => parseInt(h.slice(i, i + 2), 16)
    const own = h.length === 8 ? n(6) / 255 : 1
    return `rgba(${n(0)}, ${n(2)}, ${n(4)}, ${round(own * a)})`
  }
  const rgb = /^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)(?:[\s,/]+([\d.]+%?))?\s*\)$/i.exec(c)
  if (rgb) {
    const own = rgb[4] === undefined ? 1 : rgb[4].endsWith('%') ? parseFloat(rgb[4]) / 100 : parseFloat(rgb[4])
    return `rgba(${rgb[1]}, ${rgb[2]}, ${rgb[3]}, ${round(own * a)})`
  }
  return c
}

const round = (n: number) => Math.round(n * 1000) / 1000
