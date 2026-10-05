// The visual grammar every flow diagram on the site is drawn in, and nothing else is.
//
// One mark per idea, the same mark in every diagram, each of them drawn from here. A scene in
// `theme/flows.ts` names what happens -- a role, a turn, a pass -- and never how it looks; how
// it looks is decided once, in this file and `grammar.css`.
//
//   who            a lane head: a disc for an agent (colour by what the role is), a person for
//                  you, a prompt in a square for a program with no model in it
//   a turn         a capsule for an agent, a speech bubble for you, a square box for a program
//   a new session  a spark on the capsule's left edge, which bursts as the turn starts
//   a held session a thread along the lane from the turn before, thicker for every turn it
//                  has held, since that is what its context does
//   what it does   a glyph in the capsule: works, reads, plans
//   a pass         a curve from one turn's end to the next one's start, a comet along it: solid
//                  and round when words are handed on, dotted and square when files are
//   a workspace    a plate under the lanes that work in it, named
//   lanes at once  plates fanned out in depth
//   a subflow      a capsule drawn twice, one inside the other, with the flow it calls
//   a split        copies of the line, a level down
//   a loop         a dashed arc under the lanes, back to where the next round starts
//   the budget     the bar along the bottom, filling only while a model is working
//   the finish     a post at the right, with every way the run ends; the one this run reaches
//                  lights: done, gives up, budget, or you

import type { Does, Outcome, RoleKind } from '../../flows'

/** The words the legend and the captions use for each kind of role. */
export const ROLE_SAID: Record<RoleKind, string> = {
  maker: 'an agent that does the work',
  partner: 'a second agent, taking turns with the first',
  checker: 'an agent that reads and judges',
  steward: 'an agent that plans or cleans, not builds',
  human: 'you',
  program: 'humanize or your script: no model',
}

export const SESSION_SAID = {
  new: 'a session opened for this turn',
  held: 'another turn of the session it already had',
  none: 'no turn of a model',
} as const

export const OUTCOME_SAID: Record<Outcome, string> = {
  done: 'the flow’s own finish',
  fail: 'the flow gives up',
  budget: 'the budget runs out',
  you: 'you end it',
}

/** Glyphs, drawn in a 16-unit box centred on the origin, stroked in the current colour. The
 *  few that are filled say so with a trailing `*` in their key. */
export const GLYPH: Record<string, string> = {
  work: 'M-5 5 L-4.3 1.8 L3.2 -5.7 L5.7 -3.2 L-1.8 4.3 Z M1.4 -3.9 L3.9 -1.4',
  read: 'M-7 0 Q0 -7 7 0 Q0 7 -7 0 Z M-2 0 A2 2 0 1 0 2 0 A2 2 0 1 0 -2 0',
  plan: 'M-6 5 Q-6 -1 0 0 Q6 1 6 -5 M-6 5 m-1.6 0 a1.6 1.6 0 1 0 3.2 0 a1.6 1.6 0 1 0 -3.2 0 M6 -5 m-1.6 0 a1.6 1.6 0 1 0 3.2 0 a1.6 1.6 0 1 0 -3.2 0',
  ask: 'M-2.6 -2.6 Q-2.6 -5.6 0.2 -5.6 Q3 -5.6 3 -3 Q3 -1.2 0.2 -0.2 V1.8 M0.2 4.4 V4.9',
  run: 'M-6 -4 L-2 0 L-6 4 M0 5 H6',
  agent: 'M0 -6.5 Q0.9 -0.9 6.5 0 Q0.9 0.9 0 6.5 Q-0.9 0.9 -6.5 0 Q-0.9 -0.9 0 -6.5 Z',
  human: 'M-2.8 -3.4 A2.8 2.8 0 1 0 2.8 -3.4 A2.8 2.8 0 1 0 -2.8 -3.4 M-5.6 6 Q-5.6 0.8 0 0.8 Q5.6 0.8 5.6 6',
  program: 'M-5 -3.5 L-1.5 0 L-5 3.5 M0.5 4 H5.5',
  folder: 'M-7 -4.5 H-2 L0 -2.5 H7 V5 H-7 Z',
  calls: 'M-6 -6 H6 V6 H-6 Z M-2.5 -2.5 H2.5 V2.5 H-2.5 Z',
  loop: 'M5.4 -1.6 A5.6 5.6 0 1 0 5.6 2.4 M5.6 -6 V-1.6 H1.2',
  done: 'M-5 0.4 L-1.6 3.8 L5.2 -3.8',
  fail: 'M-4.2 -4.2 L4.2 4.2 M4.2 -4.2 L-4.2 4.2',
  budget:
    'M-4.5 -6 H4.5 M-4.5 6 H4.5 M-3.6 -6 Q-3.6 -1.2 0 0 Q3.6 1.2 3.6 6 M3.6 -6 Q3.6 -1.2 0 0 Q-3.6 1.2 -3.6 6',
  you: 'M-4 -4 H4 V4 H-4 Z',
  split: 'M0 -6 V-1 M0 -1 L-5 5 M0 -1 L5 5',
}

/** The glyph a lane head carries. */
export const HEAD_GLYPH: Record<RoleKind, string> = {
  maker: 'agent',
  partner: 'agent',
  checker: 'agent',
  steward: 'agent',
  human: 'human',
  program: 'program',
}

/** What a turn does when a scene does not say. */
export const doesOf = (kind: RoleKind, does?: Does): Does =>
  does ?? (kind === 'human' ? 'ask' : kind === 'program' ? 'run' : 'work')

/** The smallest any word of a scene is set, in the units of its world: at the camera's zoom of
 *  1 it is drawn at 11.5px, and no word is ever drawn smaller than 11px on screen. */
export const WORDS = 11.5

/** How much of a scene's words to show where the camera draws the world at `scale` screen
 *  pixels to the unit: all of them while they can be read, fading as they near 11px, and
 *  none below it. The words of one thing -- a head's name and its note, a turn's lines --
 *  come and go together, by the smallest of them, `WORDS`. A wide shot on a narrow screen is the marks alone, and the words come back
 *  as the camera closes in; the line under the picture says what is happening either way. */
export const legible = (scale: number) => Math.min(1, Math.max(0, (scale * WORDS - 11) / (WORDS - 11)))

/** Sizes, in the units of the world a scene is laid out in. */
export const SIZE = {
  /** From one lane's centre to the next one's. */
  lane: 66,
  /** A turn's height. */
  turn: 36,
  /** The left of the first beat: the lane heads live to the left of it. */
  x0: 176,
  /** Where a lane head's disc sits. */
  head: 26,
  /** A beat's width, unless a scene says otherwise. */
  beat: 160,
  /** How far into its beat a turn starts: the rest of the beat before it is where passes run. */
  gap: 0.22,
  /** Above the first lane. */
  top: 34,
  /** The band under the lanes the loop runs in. */
  arc: 44,
  /** The band under that the budget runs in. */
  meter: 40,
  /** How far apart plates fan out in depth. */
  stack: 260,
}
