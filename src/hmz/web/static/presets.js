// The themes humanize comes with, a light one and a dark one of each pair: its own, Humanize
// Green, and twelve more, each named for a mood and the colour it is most. Each is said in a few
// colours, its ground, its ink and its five accents, and the rest of what a theme sets is worked
// out of them as style.css works out its own: the planes from the paper, the greys from the ink,
// the lines from the ink seen through.

/** What a pair's accents stand for in the page's tokens. */
const ROLES = { accent: ['cyan', 'lane-1'], accentInk: ['cyan-ink', 'link'], highlight: ['pink', 'lane-2'], highlightInk: ['pink-ink'], brand: ['green'], tertiary: ['lavender', 'lane-3'], gold: ['gold', 'lane-4'] }

/**
 * Every pair, by the key its themes' ids start with. A pair's light and dark are each its
 * ground (`paper`, `side`, `ink`) and its accents: the colour it is most where the page is live
 * or followed, the one beside it where something is picked out, the mark, a third and the gold.
 */
export const PAIRS = [
  { key: 'humanize', name: 'Humanize Green' },
  {
    key: 'temperate-gold',
    name: 'Temperate Gold',
    light: { paper: '#fbf7ec', side: '#f1e8d2', ink: '#2b2115', accent: '#c9a24a', accentInk: '#7a5a14', highlight: '#b9826a', highlightInk: '#8a4f35', brand: '#d4a23c', tertiary: '#7d8fb3', gold: '#e0b04a' },
    dark: { paper: '#17130c', side: '#100d08', ink: '#f3ead6', accent: '#e3bf6a', accentInk: '#f0d38f', highlight: '#d9a58a', highlightInk: '#ebbfa6', brand: '#e3b04f', tertiary: '#a9b8d8', gold: '#f2c862' },
  },
  {
    key: 'concordant-scarlet',
    name: 'Concordant Scarlet',
    light: { paper: '#fcf5ef', side: '#f5e6dc', ink: '#2a1414', accent: '#c8322b', accentInk: '#9e1f1a', highlight: '#d9a24a', highlightInk: '#7f5a12', brand: '#d6463d', tertiary: '#8c7fb8', gold: '#d9a440' },
    dark: { paper: '#1a0f0f', side: '#120a0a', ink: '#f6e9e4', accent: '#f0645a', accentInk: '#ff8f86', highlight: '#f0c46a', highlightInk: '#f5d38c', brand: '#e04b42', tertiary: '#b5a8e0', gold: '#f2c862' },
  },
  {
    key: 'restrained-crimson',
    name: 'Restrained Crimson',
    light: { paper: '#faf3ec', side: '#f1e2d4', ink: '#2a1612', accent: '#a62c22', accentInk: '#8a2219', highlight: '#a8641e', highlightInk: '#8a5418', brand: '#b8322a', tertiary: '#6f7fa8', gold: '#d1a03c' },
    dark: { paper: '#190f0d', side: '#110a08', ink: '#f5e6dc', accent: '#e05a4c', accentInk: '#f08a7e', highlight: '#f0b06a', highlightInk: '#f5c48e', brand: '#d9473a', tertiary: '#a6b4dc', gold: '#f2c862' },
  },
  {
    key: 'critical-teal',
    name: 'Critical Teal',
    light: { paper: '#f2f7f6', side: '#e2ecea', ink: '#12171e', accent: '#2e8f95', accentInk: '#1d6a70', highlight: '#4d6aa8', highlightInk: '#34508a', brand: '#3aa7a0', tertiary: '#8b72d6', gold: '#c9a24a' },
    dark: { paper: '#0f1518', side: '#0a0f11', ink: '#e4f0ee', accent: '#6fd3c9', accentInk: '#9ae4dc', highlight: '#8fb0f0', highlightInk: '#b0c8f5', brand: '#4fc2b8', tertiary: '#b9a6f5', gold: '#e6c46a' },
  },
  {
    key: 'desirous-indigo',
    name: 'Desirous Indigo',
    light: { paper: '#f6f3f5', side: '#ebe5ea', ink: '#1c1826', accent: '#3d4a8c', accentInk: '#2f3a78', highlight: '#b07a8a', highlightInk: '#87505f', brand: '#383d76', tertiary: '#9a8fb8', gold: '#d4a440' },
    dark: { paper: '#14121c', side: '#0e0c14', ink: '#ece6f0', accent: '#8f9cf0', accentInk: '#b0baf7', highlight: '#e0a8b8', highlightInk: '#edc0cc', brand: '#7f8de6', tertiary: '#c5b8e8', gold: '#f0c862' },
  },
  {
    key: 'peaceful-lilac',
    name: 'Peaceful Lilac',
    light: { paper: '#f7f2f7', side: '#ece2ee', ink: '#22182a', accent: '#8d5c9d', accentInk: '#6e3f7e', highlight: '#d98fb0', highlightInk: '#a3466f', brand: '#9e7eaf', tertiary: '#5d7fb0', gold: '#c9a24a' },
    dark: { paper: '#151019', side: '#0e0a11', ink: '#efe6f2', accent: '#c5a3e0', accentInk: '#d7bdf0', highlight: '#f0a8c8', highlightInk: '#f5c0d8', brand: '#bb92d6', tertiary: '#9cb8f0', gold: '#f2c862' },
  },
  {
    key: 'hateful-silver',
    name: 'Hateful Silver',
    light: { paper: '#f5f5f7', side: '#e8e7ec', ink: '#1d1820', accent: '#5a6a8c', accentInk: '#3f4d6e', highlight: '#b8423e', highlightInk: '#9a2e2a', brand: '#c9a24a', tertiary: '#8c87a8', gold: '#d9a440' },
    dark: { paper: '#121115', side: '#0c0b0e', ink: '#ecebf0', accent: '#a9b8dc', accentInk: '#c2cdea', highlight: '#f07a6e', highlightInk: '#f59a90', brand: '#e0b960', tertiary: '#b8b3d4', gold: '#f2c862' },
  },
  {
    key: 'devoted-pink',
    name: 'Devoted Pink',
    light: { paper: '#fdf6f5', side: '#f7e6e6', ink: '#2a1520', accent: '#e07a98', accentInk: '#b0406a', highlight: '#3fb8cf', highlightInk: '#0f7385', brand: '#d4566e', tertiary: '#a993c6', gold: '#d9a84a' },
    dark: { paper: '#1a1016', side: '#120b0f', ink: '#f7e8ee', accent: '#ff94b8', accentInk: '#ffb0c9', highlight: '#6fd6ea', highlightInk: '#95e3f0', brand: '#e0566e', tertiary: '#c9b4e6', gold: '#f2c862' },
  },
  {
    key: 'self-negating-plum',
    name: 'Self-Negating Plum',
    light: { paper: '#f6f2f5', side: '#ebe3ea', ink: '#1e1622', accent: '#6b3a63', accentInk: '#5a2d53', highlight: '#2f7fae', highlightInk: '#24688f', brand: '#673550', tertiary: '#8c7fb8', gold: '#c9a24a' },
    dark: { paper: '#141017', side: '#0d0a10', ink: '#efe6f0', accent: '#c48ab8', accentInk: '#d8a8cf', highlight: '#7fc4ea', highlightInk: '#a2d4f0', brand: '#b0608f', tertiary: '#b5a8e0', gold: '#f2c862' },
  },
  {
    key: 'dominant-azure',
    name: 'Dominant Azure',
    light: { paper: '#f3f7fb', side: '#e3ecf6', ink: '#141c2e', accent: '#3a7fc0', accentInk: '#24609c', highlight: '#8a7fc0', highlightInk: '#5c519a', brand: '#5497ce', tertiary: '#3fa8b9', gold: '#d9a440' },
    dark: { paper: '#0e1420', side: '#090e17', ink: '#e6eef8', accent: '#7fb8f0', accentInk: '#a6cff5', highlight: '#b8b0f0', highlightInk: '#ccc6f5', brand: '#70b0e8', tertiary: '#70d6f7', gold: '#f2c862' },
  },
  {
    key: 'surviving-jade',
    name: 'Surviving Jade',
    light: { paper: '#f5f3ee', side: '#e9e5dc', ink: '#1b1518', accent: '#2f8a74', accentInk: '#1f6656', highlight: '#b8923e', highlightInk: '#7d5d14', brand: '#3a9a80', tertiary: '#8f6a4a', gold: '#d1a03c' },
    dark: { paper: '#141213', side: '#0d0c0c', ink: '#f0e9de', accent: '#6fd0b0', accentInk: '#95dec6', highlight: '#e6c070', highlightInk: '#f0d28f', brand: '#4fc09c', tertiary: '#c4a688', gold: '#f2c862' },
  },
  {
    key: 'lamenting-orchid',
    name: 'Lamenting Orchid',
    light: { paper: '#fdf5f8', side: '#f8e6ee', ink: '#2a1724', accent: '#c95f98', accentInk: '#a3437a', highlight: '#5aa8c8', highlightInk: '#246985', brand: '#e08ab4', tertiary: '#a993cf', gold: '#d9b04a' },
    dark: { paper: '#1a1018', side: '#120b10', ink: '#f8e9f1', accent: '#f0a0c8', accentInk: '#f5bcd8', highlight: '#9ad8f0', highlightInk: '#b8e4f5', brand: '#e88ec0', tertiary: '#c9b4ec', gold: '#f2c862' },
  },
]

function rgb(hex) {
  return [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16))
}

/** Two colours mixed, `by` of the way from the first to the second. */
function mix(one, other, by) {
  const [a, b] = [rgb(one), rgb(other)]
  return `#${a.map((n, at) => Math.round(n + (b[at] - n) * by).toString(16).padStart(2, '0')).join('')}`
}

/** How far apart two colours are to the eye, as WCAG measures it: 1 to 21. */
function contrast(one, other) {
  const lit = (hex) => {
    const [r, g, b] = rgb(hex).map((n) => n / 255).map((n) => (n <= 0.03928 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
  }
  const [hi, lo] = [lit(one), lit(other)].sort((a, b) => b - a)
  return (hi + 0.05) / (lo + 0.05)
}

function through(hex, alpha) {
  return `rgba(${rgb(hex).join(', ')}, ${alpha})`
}

/** Every colour a theme of a pair sets, worked out of the few it is said in. */
export function colours(scheme, said) {
  const { paper, side, ink } = said
  const light = scheme === 'light'
  // Text on a fill of any accent: the ink or the paper, whichever the darkest or lightest
  // accent leaves easier to read.
  const fills = [said.accent, said.highlight, said.brand]
  const legible = (text) => Math.min(...fills.map((fill) => contrast(text, fill)))
  const made = {
    paper,
    side,
    ink,
    surface: light ? mix(paper, '#ffffff', 0.5) : mix(paper, ink, 0.06),
    raised: light ? mix(paper, '#ffffff', 0.85) : mix(paper, ink, 0.1),
    'ink-2': mix(ink, paper, light ? 0.3 : 0.25),
    'ink-3': mix(ink, paper, light ? 0.32 : 0.42),
    'on-ink': paper,
    'on-fill': legible(ink) >= legible(paper) ? ink : paper,
    line: through(ink, 0.12),
    'line-strong': through(ink, light ? 0.28 : 0.3),
    hover: through(said.accent, 0.1),
    scrim: light ? through(ink, 0.45) : 'rgba(0, 0, 0, 0.6)',
  }
  for (const [role, tokens] of Object.entries(ROLES)) for (const token of tokens) made[token] = said[role]
  return made
}

/** The two themes of every pair: humanize's own, kept by the ids they always had, then the rest. */
export const OWN = PAIRS.flatMap((pair) =>
  ['light', 'dark'].map((scheme) => ({
    id: pair.key === 'humanize' ? scheme : `${pair.key}-${scheme}`,
    name: pair.name,
    base: scheme,
    pair: pair.key,
    colors: pair[scheme] ? colours(scheme, pair[scheme]) : {},
    images: {},
  })),
)
