// The Humanfia H and the wordmark, as numbers. public/logo.svg, logo-dark.svg, logo-mark.svg and
// favicon.svg draw the same shapes from the same coordinates, and so do scripts/icons.py and og.py;
// this is the copy the page animates, so it is kept as primitives rather than one outline.
//
// The grid is 96 x 108 and every edge lands on a whole unit. Four pieces, the way a constructivist
// letter is built -- a few flat planes and one circle, hard edges, one diagonal:
//
//   the left stem     full height, 24 wide
//   the crossbar      a parallelogram rising one in three (18.4 degrees) from the left stem's
//                     inner edge to the right edge of the mark, 21 deep
//   the right stem    24 wide, standing under the crossbar, its top cut on the crossbar's own line
//                     so the H closes without anything above it
//   the circle        as wide as a stem, centred over the right stem and tangent to the cap line;
//                     the gap under it is parallel to the cut
//
// Without the circle the diagonal still finishes the letter: it rises to the corner and points at
// the empty space, which is a composition rather than an absence. With it, the space is answered.

export const MARK = { width: 96, height: 108 }

/** The rise of the diagonal per unit across: one in three, 18.4 degrees. */
export const SLOPE = 1 / 3
export const ANGLE = Math.atan(SLOPE)

/** The whole H as one outline (the circle is separate, and optional). */
export const MARK_PATH = 'M0 0H24V50L96 26V108H72V55L24 71V108H0Z'

/** The H as the pieces it is built from, for the hero, which assembles it. Points are clockwise
 *  from the top left. The crossbar and the right stem overlap where they meet, so either can move
 *  without a seam opening. */
export const PIECES = {
  stem: [[0, 0], [24, 0], [24, 108], [0, 108]],
  bar: [[24, 50], [96, 26], [96, 47], [24, 71]],
  post: [[72, 34], [96, 26], [96, 108], [72, 108]],
} satisfies Record<string, [number, number][]>

/** The circle's home: the slot over the right stem. */
export const DOT = { cx: 84, cy: 12, r: 12 }

// ---------------------------------------------------------------------------------- wordmark

/**
 * "humanfia" in the same language as the mark: stems and bars on a grid, square shoulders, no
 * curves except the one circle. Units are the mark's own, so the wordmark puts the H and the
 * letters side by side at one scale: ascenders reach the cap line at 0, the x-height is at 32,
 * the baseline is the mark's foot at 108, and a stroke is 16 (two thirds of the mark's stem, so
 * the H stays the heaviest thing in the lockup).
 *
 * The i has no dot of its own. Its dot is the H's circle at the same size, and it sits tangent to
 * the cap line over the i exactly as it does over the right stem -- so the hop between the two is
 * a level arc, and either resting place is a finished wordmark.
 */
const LETTERS: { x: number; d: string }[] = [
  { x: 0, d: 'M0 0H16V32H56V108H40V48H16V108H0Z' }, // h
  { x: 68, d: 'M0 32H16V92H40V32H56V108H0Z' }, // u
  { x: 136, d: 'M0 32H88V108H72V48H52V108H36V48H16V108H0Z' }, // m
  { x: 236, d: 'M0 32H56V108H0V64H40V48H0ZM16 80V92H40V80Z' }, // a
  { x: 304, d: 'M0 32H56V108H40V48H16V108H0Z' }, // n
  { x: 372, d: 'M8 0H40V16H24V32H40V48H24V108H8V48H0V32H8Z' }, // f
  { x: 424, d: 'M0 32H16V108H0Z' }, // i, dotless
  { x: 452, d: 'M0 32H56V108H0V64H40V48H0ZM16 80V92H40V80Z' }, // a
]

/** Where the letters start, right of the mark. */
export const WORD_X = 136

/** The letters as one path, already placed after the mark. */
export const WORD_PATH = LETTERS.map(({ x, d }) =>
  d.replace(/([MHL])(-?[\d.]+)/g, (_, cmd: string, n: string) => `${cmd}${+n + WORD_X + x}`),
).join('')

/** The i's dot, in wordmark units: centred on the i's stem, tangent to the cap line. */
export const I_DOT = { cx: WORD_X + 424 + 8, cy: DOT.cy, r: DOT.r }

/** The whole lockup: mark, gap, letters. */
export const WORDMARK = { width: WORD_X + 508, height: MARK.height }
