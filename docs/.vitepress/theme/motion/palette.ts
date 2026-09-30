// The site's colours, resolved for a canvas. SVG and CSS take `var(--hmz-lane-1)` as it is and
// follow the theme by themselves; a canvas needs the colour itself, and needs it again when the
// reader switches between light and dark. `palette` is that: one object, kept current, cheap to
// read every frame.
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
  }

  onMounted(() => {
    read()
    watch = new MutationObserver(read)
    watch.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
  })
  onUnmounted(() => watch?.disconnect())

  return palette
}
