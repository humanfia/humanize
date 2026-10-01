// How the check that every word can be read (`.vitepress/legible.mjs`) gets hold of a scene.
//
// Played on a clock, a scene is wherever the clock has got it to when the check looks, and a
// busy machine looks later: the same check would pass on one run and fail on the next. So the
// check does not play a scene. It holds it still at one moment of its timeline after another
// and measures each, the same moments every run. Every scene lists itself here for that, and
// only in a browser driven by automation: a reader's browser never has `window.__hmzScenes`.

export interface Probe {
  /** The scene's outermost element: `.hmz-stage` or `.hmz-flow-player`. */
  root: () => Element | null
  /** Seconds in one pass of its timeline. */
  duration: () => number
  /** The moments, in seconds, where it comes to rest for a reader: where a chapter ends, a
   *  step lands, or the scene holds still. A word too small there is too small, however
   *  briefly it is drawn. */
  settled: () => number[]
  /** Pause it `t` seconds into a pass, drawn as it is there. Resolves once the page shows it. */
  seek: (t: number) => Promise<void>
}

declare global {
  interface Window {
    __hmzScenes?: Probe[]
  }
}

/** List a scene for the check, if a check is driving this browser. Returns how to unlist it. */
export function probe(scene: Probe): () => void {
  if (typeof window === 'undefined' || !navigator.webdriver) return () => {}
  const all = (window.__hmzScenes ??= [])
  all.push(scene)
  return () => {
    const at = all.indexOf(scene)
    if (at >= 0) all.splice(at, 1)
  }
}
