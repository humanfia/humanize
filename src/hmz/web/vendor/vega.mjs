// How the page draws a chart a flow hands it: a Vega-Lite (or Vega) spec, drawn by vega-embed
// in the page's own colours. Expressions in the spec are interpreted, never compiled into code,
// so the page's policy (no `eval`) holds; nothing is fetched, so a chart carries its data; and
// there is no actions menu, so it is a picture, not a tool. Bundled by build.mjs into
// ../static/vendor/vega.js.

import vegaEmbed from 'vega-embed';
import { loader as vegaLoader } from 'vega';

/**
 * A loader that reaches nothing: a chart's data is in its spec, a picture in it is a `data:`
 * image, and it links nowhere.
 */
function sealed() {
  const loader = vegaLoader();
  loader.load = async (uri) => {
    throw new Error(`a chart reads no address: ${uri}`);
  };
  loader.sanitize = async (uri, options) => {
    if (options?.context !== 'href' && /^data:image\//i.test(String(uri))) return { href: String(uri) };
    throw new Error(`a chart reads no address: ${uri}`);
  };
  return loader;
}

/** The page's colour `--name` as `el` sees it, or `fallback` where it has none. */
function token(style, name, fallback) {
  const value = style?.getPropertyValue(`--${name}`).trim();
  return value ? value : fallback;
}

const FALLBACK = {
  light: { ink: '#141a1f', ink2: '#435058', ink3: '#5d6a72', line: 'rgba(20, 26, 31, 0.12)', lineStrong: 'rgba(20, 26, 31, 0.28)' },
  dark: { ink: '#e6eff1', ink2: '#b3c3c8', ink3: '#82939a', line: 'rgba(230, 239, 241, 0.12)', lineStrong: 'rgba(230, 239, 241, 0.3)' },
};
const LANES = ['#1fb3c7', '#ec6fa3', '#8b72d6', '#d9a440', '#4a8fd8', '#7f8d95'];
const SANS = "Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";

/** A Vega config that wears the page's colours and type, for its light or dark theme. */
function configFor(el, theme) {
  const base = FALLBACK[theme === 'dark' ? 'dark' : 'light'];
  const style = typeof getComputedStyle === 'function' ? getComputedStyle(el) : null;
  const ink = token(style, 'ink', base.ink);
  const ink2 = token(style, 'ink-2', base.ink2);
  const ink3 = token(style, 'ink-3', base.ink3);
  const line = token(style, 'line', base.line);
  const lineStrong = token(style, 'line-strong', base.lineStrong);
  const font = token(style, 'sans', SANS);
  const lanes = LANES.map((fallback, i) => token(style, `lane-${i + 1}`, fallback));
  const axis = {
    domainColor: lineStrong,
    gridColor: line,
    tickColor: lineStrong,
    labelColor: ink2,
    titleColor: ink,
    labelFont: font,
    titleFont: font,
  };
  const legend = { labelColor: ink2, titleColor: ink, labelFont: font, titleFont: font };
  return {
    background: 'transparent',
    font,
    view: { stroke: line },
    axis,
    legend,
    header: { labelColor: ink2, titleColor: ink, labelFont: font, titleFont: font },
    title: { color: ink, subtitleColor: ink3, font, subtitleFont: font },
    mark: { color: lanes[0] },
    text: { color: ink },
    range: { category: lanes },
  };
}

/**
 * Draws `spec` into `el`, in the page's `theme` ('light' or 'dark'), its colours read from the
 * page as it is now: a page that changes theme draws its charts again. Resolves to vega-embed's
 * result, whose `finalize()` lets the chart go.
 */
export async function embed(el, spec, { theme = 'light' } = {}) {
  if (spec === null || typeof spec !== 'object' || Array.isArray(spec)) {
    throw new TypeError('a chart is a Vega or Vega-Lite spec, an object');
  }
  // A spec's own embedding options could ask for a menu, a loader, or files to read: it gets none.
  const own = structuredClone(spec);
  if (own.usermeta && typeof own.usermeta === 'object') delete own.usermeta.embedOptions;
  return vegaEmbed(el, own, {
    ast: true,
    actions: false,
    renderer: 'svg',
    loader: sealed(),
    config: configFor(el, theme),
  });
}
