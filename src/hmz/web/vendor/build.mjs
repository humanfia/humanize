// Builds the page's third-party code into ../static/vendor: one minified ES module each for the
// editor (codemirror.mjs), the terminal (xterm.mjs), Markdown (markdown.mjs) and charts
// (vega.mjs), and xterm's stylesheet. Each file opens
// with the licences of every package bundled into it. The same lockfile builds the same bytes,
// which CI checks: run `pnpm install --frozen-lockfile && pnpm build` here and commit the result.

import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const here = dirname(fileURLToPath(import.meta.url));
const out = resolve(here, '../static/vendor');

/** Where the package a bundled file came from lives: the nearest folder with a package.json naming it. */
function packageOf(file) {
  for (let dir = dirname(resolve(here, file)); dir.startsWith(here) && dir !== here; dir = dirname(dir)) {
    const manifest = join(dir, 'package.json');
    if (existsSync(manifest)) {
      const { name, version } = JSON.parse(readFileSync(manifest, 'utf8'));
      if (name) return { dir, name, version };
    }
  }
  return null;
}

/** A package's licence text, as its author wrote it. */
function licenceOf(dir, name) {
  const file = readdirSync(dir).find((entry) => /^(licen[cs]e|copying)(\.(md|txt))?$/i.test(entry));
  if (file === undefined) throw new Error(`${name} ships no licence file`);
  return readFileSync(join(dir, file), 'utf8');
}

/** A comment naming every package in `files` and the licence each is under, identical ones once. */
function notice(files) {
  const packages = new Map();
  for (const file of files) {
    const found = packageOf(file);
    // Only this folder's own entry points are nobody's package; anything installed must say
    // whose it is, or the bundle would carry it without its licence.
    if (found === null && file.split(/[\\/]/).includes('node_modules')) throw new Error(`${file} is in no package`);
    if (found !== null) packages.set(`${found.name}@${found.version}`, found);
  }
  const byText = new Map();
  for (const key of [...packages.keys()].sort()) {
    const { dir, name } = packages.get(key);
    const text = licenceOf(dir, name)
      .replaceAll('*/', '* /')
      .split(/\r?\n/)
      .map((line) => line.trimEnd())
      .join('\n')
      .trim();
    byText.set(text, [...(byText.get(text) ?? []), key]);
  }
  const parts = [...byText].map(([text, keys]) => `${keys.join(', ')}:\n\n${text}`);
  return `/*! Third-party code, bundled by src/hmz/web/vendor/build.mjs. Its licences follow.\n\n${parts.join('\n\n---\n\n')}\n*/\n`;
}

// The few places where a package would compile code from a string at run time, which the page's
// policy refuses (no `eval`): each is rewritten to do the same without. A patch that no longer
// finds its text fails the build, so that an upgrade cannot quietly bring the compiling back.
const PATCHES = [
  {
    // vega's runtime compiles expressions unless given an interpreter; vega.mjs always gives
    // vega-interpreter's, so its compiler goes and, with it, every `Function(`.
    file: /[\\/]vega-runtime[\\/]build[\\/]vega-runtime\.js$/,
    find: 'this.expr = expr || expressionCodegen,',
    put: 'this.expr = expr,',
  },
  {
    // d3-dsv builds a row's object with `new Function`; a closure makes the same object.
    file: /[\\/]d3-dsv[\\/]dist[\\/]d3-dsv\.mjs$/,
    find: `function objectConverter(columns) {
  return new Function("d", "return {" + columns.map(function(name, i) {
    return JSON.stringify(name) + ": d[" + i + "] || \\"\\"";
  }).join(",") + "}");
}`,
    put: `function objectConverter(columns) {
  return function(d) {
    return Object.fromEntries(columns.map(function(name, i) { return [name, d[i] || ""]; }));
  };
}`,
  },
];

const applied = new Set();

const patched = {
  name: 'patched',
  setup(build) {
    for (const patch of PATCHES) {
      const { file, find, put } = patch;
      build.onLoad({ filter: file }, ({ path }) => {
        const text = readFileSync(path, 'utf8');
        if (!text.includes(find)) throw new Error(`${path} no longer reads as patched: ${find.split('\n')[0]}`);
        applied.add(patch);
        return { contents: text.replace(find, put), loader: 'js' };
      });
    }
  },
};

async function bundle(entry, name, options = {}) {
  const result = await build({
    entryPoints: [join(here, entry)],
    absWorkingDir: here,
    bundle: true,
    format: 'esm',
    platform: 'browser',
    target: ['es2022', 'chrome111', 'firefox113', 'safari16.4'],
    minify: true,
    legalComments: 'none',
    charset: 'utf8',
    metafile: true,
    write: false,
    logLevel: 'warning',
    plugins: [patched],
    ...options,
  });
  const [file] = result.outputFiles;
  const inputs = Object.keys(result.metafile.inputs).map((input) => relative(here, resolve(here, input)));
  const text = notice(inputs) + (file.text.endsWith('\n') ? file.text : `${file.text}\n`);
  writeFileSync(join(out, name), text);
  console.log(`${name}: ${(Buffer.byteLength(text) / 1024).toFixed(0)} KiB`);
}

// Built afresh, so that a file no longer built is no longer served, and CI sees it go.
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
await bundle('codemirror.mjs', 'codemirror.js');
await bundle('xterm.mjs', 'xterm.js');
await bundle('markdown.mjs', 'markdown.js');
await bundle('vega.mjs', 'vega.js');
// Every patch is to vega.js's packages: one that found no file to apply to was moved past.
for (const { file } of PATCHES.filter((patch) => !applied.has(patch))) throw new Error(`no file matched ${file}`);
await bundle('node_modules/@xterm/xterm/css/xterm.css', 'xterm_css.css', { format: undefined, target: ['chrome111', 'firefox113', 'safari16.4'] });
