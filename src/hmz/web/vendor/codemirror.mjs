// What the page's editors are made of: CodeMirror 6, one copy of each of its packages, and
// the two things only this page knows -- which language a file is in, and how the editor wears
// the page's own colours. Bundled by build.mjs into ../static/vendor/codemirror.js, the only
// place the page imports any of it from.

import { HighlightStyle, LanguageDescription, LanguageSupport, StreamLanguage, syntaxHighlighting } from '@codemirror/language';
import { EditorView } from '@codemirror/view';
import { tags as t } from '@lezer/highlight';

import { cpp } from '@codemirror/lang-cpp';
import { css } from '@codemirror/lang-css';
import { go } from '@codemirror/lang-go';
import { html } from '@codemirror/lang-html';
import { java } from '@codemirror/lang-java';
import { javascript } from '@codemirror/lang-javascript';
import { json } from '@codemirror/lang-json';
import { markdown } from '@codemirror/lang-markdown';
import { php } from '@codemirror/lang-php';
import { python } from '@codemirror/lang-python';
import { rust } from '@codemirror/lang-rust';
import { sql } from '@codemirror/lang-sql';
import { xml } from '@codemirror/lang-xml';
import { yaml } from '@codemirror/lang-yaml';
import { csharp, kotlin, scala } from '@codemirror/legacy-modes/mode/clike';
import { cmake } from '@codemirror/legacy-modes/mode/cmake';
import { diff } from '@codemirror/legacy-modes/mode/diff';
import { dockerFile } from '@codemirror/legacy-modes/mode/dockerfile';
import { lua } from '@codemirror/legacy-modes/mode/lua';
import { nginx } from '@codemirror/legacy-modes/mode/nginx';
import { perl } from '@codemirror/legacy-modes/mode/perl';
import { powerShell } from '@codemirror/legacy-modes/mode/powershell';
import { properties } from '@codemirror/legacy-modes/mode/properties';
import { protobuf } from '@codemirror/legacy-modes/mode/protobuf';
import { ruby } from '@codemirror/legacy-modes/mode/ruby';
import { shell } from '@codemirror/legacy-modes/mode/shell';
import { swift } from '@codemirror/legacy-modes/mode/swift';
import { toml } from '@codemirror/legacy-modes/mode/toml';

export { basicSetup, minimalSetup } from 'codemirror';
export {
  Annotation,
  ChangeSet,
  Compartment,
  EditorSelection,
  EditorState,
  Facet,
  Prec,
  RangeSetBuilder,
  StateEffect,
  StateField,
  Text,
  Transaction,
} from '@codemirror/state';
export {
  Decoration,
  EditorView,
  ViewPlugin,
  WidgetType,
  drawSelection,
  highlightActiveLine,
  highlightActiveLineGutter,
  highlightSpecialChars,
  keymap,
  lineNumbers,
  placeholder,
  rectangularSelection,
  showPanel,
} from '@codemirror/view';
export {
  defaultKeymap,
  history,
  historyKeymap,
  indentLess,
  indentMore,
  indentWithTab,
  redo,
  toggleComment,
  undo,
} from '@codemirror/commands';
export {
  HighlightStyle,
  LanguageSupport,
  StreamLanguage,
  bracketMatching,
  foldGutter,
  foldKeymap,
  indentOnInput,
  indentUnit,
  syntaxHighlighting,
} from '@codemirror/language';
export {
  SearchQuery,
  closeSearchPanel,
  findNext,
  findPrevious,
  getSearchQuery,
  gotoLine,
  highlightSelectionMatches,
  openSearchPanel,
  replaceAll,
  search,
  searchKeymap,
  searchPanelOpen,
  setSearchQuery,
} from '@codemirror/search';
export { autocompletion, closeBrackets, closeBracketsKeymap, completionKeymap } from '@codemirror/autocomplete';
export { lintGutter, linter, setDiagnostics } from '@codemirror/lint';
export { MergeView, getChunks, goToNextChunk, goToPreviousChunk, unifiedMergeView } from '@codemirror/merge';
export { tags } from '@lezer/highlight';

/** A legacy CodeMirror 5 mode, as a language the editor highlights. */
const legacy = (parser) => () => new LanguageSupport(StreamLanguage.define(parser));

/**
 * Every language the editor knows: its name, the file extensions it is found by, the whole
 * names of files with no telling extension, and how its support is made.
 */
const LANGUAGES = [
  { name: 'javascript', ext: ['js', 'mjs', 'cjs'], make: () => javascript() },
  { name: 'jsx', ext: ['jsx'], make: () => javascript({ jsx: true }) },
  { name: 'typescript', ext: ['ts', 'mts', 'cts'], make: () => javascript({ typescript: true }) },
  { name: 'tsx', ext: ['tsx'], make: () => javascript({ jsx: true, typescript: true }) },
  { name: 'python', ext: ['py', 'pyi', 'pyw'], file: [/^(SConstruct|SConscript|BUCK|BUILD(\.bazel)?|WORKSPACE)$/], make: () => python() },
  { name: 'rust', ext: ['rs'], make: () => rust() },
  { name: 'json', ext: ['json', 'jsonc', 'json5', 'jsonl', 'ndjson', 'ipynb'], file: [/^\.(babelrc|eslintrc|prettierrc)$/], make: () => json() },
  { name: 'markdown', ext: ['md', 'markdown', 'mdx', 'mkd'], make: () => markdown({ codeLanguages: fenced }) },
  { name: 'html', ext: ['html', 'htm', 'xhtml', 'vue', 'svelte'], make: () => html() },
  { name: 'css', ext: ['css', 'scss', 'less'], make: () => css() },
  { name: 'yaml', ext: ['yaml', 'yml'], file: [/^\.clang-format$/], make: () => yaml() },
  { name: 'cpp', ext: ['c', 'h', 'cc', 'cpp', 'cxx', 'c++', 'hh', 'hpp', 'hxx', 'h++', 'ino', 'cu', 'cuh', 'mm'], make: () => cpp() },
  { name: 'go', ext: ['go'], make: () => go() },
  { name: 'java', ext: ['java'], make: () => java() },
  { name: 'sql', ext: ['sql'], make: () => sql() },
  { name: 'xml', ext: ['xml', 'svg', 'xsd', 'xsl', 'xslt', 'plist', 'csproj', 'fsproj', 'props', 'targets'], make: () => xml() },
  { name: 'php', ext: ['php', 'phtml'], make: () => php() },
  {
    name: 'shell',
    ext: ['sh', 'bash', 'zsh', 'ksh', 'fish', 'command'],
    file: [/^\.?(bash_profile|bash_logout|bash_aliases|bashrc|zshrc|zshenv|zprofile|zlogin|profile|envrc)$/, /^(PKGBUILD|APKBUILD)$/],
    make: legacy(shell),
  },
  // CodeMirror has no make mode; a shell's comments, strings and `$(...)` are most of one.
  { name: 'makefile', ext: ['mk', 'mak'], file: [/^(gnu)?makefile$/i], make: legacy(shell) },
  { name: 'toml', ext: ['toml'], file: [/^(Pipfile|Cargo\.lock|poetry\.lock|uv\.lock)$/], make: legacy(toml) },
  { name: 'dockerfile', ext: ['dockerfile', 'containerfile'], file: [/^(docker|container)file(\..*)?$/i], make: legacy(dockerFile) },
  { name: 'ruby', ext: ['rb', 'rake', 'gemspec', 'ru'], file: [/^(gemfile|rakefile|brewfile|vagrantfile|podfile|fastfile)$/i], make: legacy(ruby) },
  {
    name: 'properties',
    ext: ['ini', 'cfg', 'conf', 'properties', 'env', 'editorconfig', 'gitconfig', 'npmrc'],
    file: [/^\.(env(\..*)?|editorconfig|gitconfig|gitmodules|npmrc|flake8|pylintrc)$/, /^(setup\.cfg|tox\.ini)$/],
    make: legacy(properties),
  },
  { name: 'diff', ext: ['diff', 'patch', 'rej'], make: legacy(diff) },
  { name: 'cmake', ext: ['cmake'], file: [/^cmakelists\.txt$/i], make: legacy(cmake) },
  { name: 'kotlin', ext: ['kt', 'kts'], make: legacy(kotlin) },
  { name: 'scala', ext: ['scala', 'sc', 'sbt'], make: legacy(scala) },
  { name: 'csharp', ext: ['cs', 'csx'], make: legacy(csharp) },
  { name: 'swift', ext: ['swift'], make: legacy(swift) },
  { name: 'lua', ext: ['lua'], make: legacy(lua) },
  { name: 'perl', ext: ['pl', 'pm', 't'], make: legacy(perl) },
  { name: 'powershell', ext: ['ps1', 'psm1', 'psd1'], make: legacy(powerShell) },
  { name: 'protobuf', ext: ['proto'], make: legacy(protobuf) },
  { name: 'nginx', ext: [], file: [/^nginx\.conf$/], make: legacy(nginx) },
];

/** What a fenced block in Markdown is highlighted as: the language its info string names. */
const fenced = LANGUAGES.map((lang) =>
  LanguageDescription.of({
    name: lang.name,
    alias: lang.ext,
    extensions: lang.ext,
    load: async () => made(lang),
  }),
);

/** Each language's support, made the first time a file in it is opened. */
const supports = new Map();

function made(lang) {
  let support = supports.get(lang.name);
  if (support === undefined) {
    support = lang.make();
    supports.set(lang.name, support);
  }
  return support;
}

/** The language a file is in, by its whole name and then by its extension, or undefined. */
function find(filename) {
  const base = String(filename ?? '').split(/[\\/]/).pop() ?? '';
  const byName = LANGUAGES.find((lang) => (lang.file ?? []).some((re) => re.test(base)));
  if (byName !== undefined) return byName;
  const dot = base.lastIndexOf('.');
  // A name that only starts with a dot, `.bashrc`, is matched whole above, and its "extension"
  // is the name itself.
  const ext = (dot >= 0 ? base.slice(dot + 1) : '').toLowerCase();
  return ext === '' ? undefined : LANGUAGES.find((lang) => lang.ext.includes(ext));
}

/** The name of the language a file is in, for a status bar, or null for plain text. */
export function languageName(filename) {
  return find(filename)?.name ?? null;
}

/** The highlighting, indentation and folding for a file of this name, or null for plain text. */
export function languageFor(filename) {
  const lang = find(filename);
  return lang === undefined ? null : made(lang);
}

/** Every language name `languageFor` can return support for. */
export const languageNames = LANGUAGES.map((lang) => lang.name);

/** The syntax colours where the page sets none: one set for light paper, one for dark. */
const PALETTE = {
  light: {
    keyword: '#b83a72',
    string: '#2a9468',
    number: '#80590c',
    comment: '#5d6a72',
    function: '#0b7080',
    type: '#6a52b8',
    property: '#2f6fb5',
    meta: '#435058',
    invalid: '#cf3552',
  },
  dark: {
    keyword: '#ff94c2',
    string: '#5fdca3',
    number: '#f2c862',
    comment: '#82939a',
    function: '#7fe4f1',
    type: '#b9a6f5',
    property: '#86b8f2',
    meta: '#b3c3c8',
    invalid: '#ff6f88',
  },
};

/**
 * How the editor wears the page's colours.
 *
 * `tokens` holds the page's CSS custom properties, keyed with or without their leading `--`
 * (`{paper: '#f4f8f9'}` or `{'--paper': '#f4f8f9'}`), as an object or a Map; any the page does
 * not give is read from the page itself as `var(--name)`, so a theme set on the root later still
 * reaches the editor.
 */
export function themeFor({ dark = false, tokens = {} } = {}) {
  const given = (name) => {
    const value = tokens instanceof Map ? (tokens.get(name) ?? tokens.get(`--${name}`)) : (tokens?.[name] ?? tokens?.[`--${name}`]);
    return typeof value === 'string' && value.trim() !== '' ? value.trim() : null;
  };
  const tok = (name, fallback) => given(name) ?? (fallback === undefined ? `var(--${name})` : `var(--${name}, ${fallback})`);
  const base = PALETTE[dark ? 'dark' : 'light'];
  // Syntax colours are drawn from the page's own where it has one that reads on its paper.
  const syn = {
    keyword: given('pink-ink') ?? base.keyword,
    string: given('done') ?? base.string,
    number: given('budget-ink') ?? base.number,
    comment: given('ink-3') ?? base.comment,
    function: given('cyan-ink') ?? base.function,
    type: dark ? (given('lavender') ?? base.type) : base.type,
    property: dark ? (given('lane-5') ?? base.property) : base.property,
    meta: given('ink-2') ?? base.meta,
    invalid: given('fail') ?? base.invalid,
  };
  const ink = tok('ink', dark ? '#e6eff1' : '#141a1f');
  const ink3 = tok('ink-3', syn.comment);
  const line = tok('line', dark ? 'rgba(230, 239, 241, 0.12)' : 'rgba(20, 26, 31, 0.12)');
  const lineStrong = tok('line-strong', dark ? 'rgba(230, 239, 241, 0.3)' : 'rgba(20, 26, 31, 0.28)');
  const paper = tok('paper', dark ? '#0f1418' : '#f4f8f9');
  const surface = tok('surface', dark ? '#172026' : '#fbfdfd');
  const raised = tok('raised', dark ? '#1d272e' : '#ffffff');
  const cyan = tok('cyan', dark ? '#4fd8ea' : '#1fb3c7');
  const pink = tok('pink', dark ? '#ff94c2' : '#ec6fa3');
  const gold = tok('gold', dark ? '#f2c862' : '#d9a440');
  const done = tok('done', syn.string);
  const fail = tok('fail', syn.invalid);
  const mono = tok('mono', "ui-monospace, Menlo, Monaco, Consolas, 'Liberation Mono', monospace");
  const sans = tok('sans', 'ui-sans-serif, system-ui, sans-serif');
  const mix = (colour, percent) => `color-mix(in srgb, ${colour} ${percent}%, transparent)`;

  const chrome = EditorView.theme(
    {
      '&': { color: ink, backgroundColor: raised, height: '100%' },
      '&.cm-focused': { outline: 'none' },
      '.cm-scroller': { fontFamily: mono, fontSize: '13px', lineHeight: '1.55' },
      '.cm-content': { caretColor: ink },
      '.cm-cursor, .cm-dropCursor': { borderLeftColor: ink, borderLeftWidth: '2px' },
      '&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection':
        { backgroundColor: mix(pink, dark ? 32 : 24) },
      '.cm-activeLine': { backgroundColor: mix(cyan, 7) },
      '.cm-selectionMatch': { backgroundColor: mix(cyan, 18) },
      '.cm-searchMatch': { backgroundColor: mix(gold, 30), outline: `1px solid ${mix(gold, 60)}` },
      '.cm-searchMatch.cm-searchMatch-selected': { backgroundColor: mix(pink, 40) },
      '&.cm-focused .cm-matchingBracket': { backgroundColor: mix(cyan, 22), outline: `1px solid ${mix(cyan, 55)}` },
      '&.cm-focused .cm-nonmatchingBracket': { backgroundColor: mix(fail, 25) },
      '.cm-gutters': { backgroundColor: surface, color: ink3, borderRight: `1px solid ${line}` },
      '.cm-activeLineGutter': { backgroundColor: mix(cyan, 10), color: ink },
      '.cm-lineNumbers .cm-gutterElement': { padding: '0 10px 0 8px' },
      '.cm-foldGutter .cm-gutterElement': { color: ink3 },
      '.cm-foldPlaceholder': { backgroundColor: mix(cyan, 14), border: `1px solid ${line}`, color: ink, padding: '0 4px' },
      '.cm-panels': { backgroundColor: surface, color: ink, fontFamily: sans },
      '.cm-panels.cm-panels-top': { borderBottom: `1px solid ${lineStrong}` },
      '.cm-panels.cm-panels-bottom': { borderTop: `1px solid ${lineStrong}` },
      '.cm-panel input, .cm-panel button, .cm-textfield, .cm-button': {
        fontFamily: sans,
        fontSize: '12px',
        color: ink,
        backgroundColor: raised,
        backgroundImage: 'none',
        border: `1px solid ${lineStrong}`,
        borderRadius: '0',
      },
      '.cm-textfield:focus, .cm-panel input:focus': { outline: `2px solid ${cyan}`, outlineOffset: '-1px' },
      '.cm-button:active': { backgroundColor: mix(pink, 20) },
      '.cm-panel.cm-search label': { fontSize: '12px' },
      '.cm-tooltip': { backgroundColor: raised, color: ink, border: `1px solid ${lineStrong}`, borderRadius: '0' },
      '.cm-tooltip .cm-tooltip-arrow:before': { borderTopColor: lineStrong, borderBottomColor: lineStrong },
      '.cm-tooltip .cm-tooltip-arrow:after': { borderTopColor: raised, borderBottomColor: raised },
      '.cm-tooltip-autocomplete > ul': { fontFamily: mono },
      '.cm-tooltip-autocomplete > ul > li[aria-selected]': { backgroundColor: mix(cyan, 22), color: ink },
      '.cm-completionMatchedText': { textDecoration: 'none', fontWeight: '600', color: syn.function },
      '.cm-diagnostic-error': { borderLeftColor: fail },
      '.cm-diagnostic-warning': { borderLeftColor: gold },
      '.cm-diagnostic-info': { borderLeftColor: cyan },
      // The merge view's changed lines, in the page's green and red.
      '.cm-changedLine, &.cm-merge-b .cm-changedLine, .cm-inlineChangedLine': { backgroundColor: mix(done, 10) },
      '&.cm-merge-a .cm-changedLine, .cm-deletedChunk': { backgroundColor: mix(fail, 10) },
      '&.cm-merge-b .cm-changedText, .cm-insertedLine .cm-changedText': { background: mix(done, 30) },
      '&.cm-merge-a .cm-changedText, .cm-deletedChunk .cm-deletedText': { background: mix(fail, 30) },
      '.cm-changeGutter': { width: '3px', paddingLeft: '1px' },
      '&.cm-merge-b .cm-changedLineGutter, .cm-changedLineGutter': { background: done },
      '&.cm-merge-a .cm-changedLineGutter, .cm-deletedLineGutter': { background: fail },
      '.cm-collapsedLines': { color: ink3, backgroundColor: surface, backgroundImage: 'none', borderBlock: `1px solid ${line}` },
      '.cm-mergeSpacer': { backgroundColor: paper },
    },
    { dark },
  );

  const highlight = HighlightStyle.define(
    [
      { tag: [t.keyword, t.controlKeyword, t.moduleKeyword, t.operatorKeyword, t.definitionKeyword, t.modifier], color: syn.keyword },
      { tag: [t.self, t.null, t.bool, t.atom, t.special(t.variableName)], color: syn.keyword },
      { tag: [t.string, t.special(t.string), t.docString, t.character], color: syn.string },
      { tag: [t.regexp, t.escape], color: syn.number },
      { tag: [t.number, t.integer, t.float, t.unit], color: syn.number },
      { tag: [t.lineComment, t.blockComment, t.comment], color: syn.comment, fontStyle: 'italic' },
      { tag: t.docComment, color: syn.comment, fontStyle: 'italic' },
      { tag: [t.function(t.variableName), t.function(t.propertyName), t.macroName, t.labelName], color: syn.function },
      { tag: [t.definition(t.function(t.variableName))], color: syn.function, fontWeight: '600' },
      { tag: [t.typeName, t.className, t.namespace, t.definition(t.typeName), t.standard(t.typeName)], color: syn.type },
      { tag: [t.propertyName, t.attributeName, t.definition(t.propertyName)], color: syn.property },
      { tag: [t.tagName, t.angleBracket], color: syn.keyword },
      { tag: [t.attributeValue], color: syn.string },
      { tag: [t.constant(t.variableName), t.standard(t.variableName)], color: syn.number },
      { tag: [t.meta, t.annotation, t.processingInstruction, t.documentMeta], color: syn.meta },
      { tag: [t.operator, t.punctuation, t.separator, t.bracket, t.derefOperator], color: syn.meta },
      { tag: t.heading, color: syn.keyword, fontWeight: '700' },
      { tag: t.strong, fontWeight: '700' },
      { tag: t.emphasis, fontStyle: 'italic' },
      { tag: t.strikethrough, textDecoration: 'line-through' },
      { tag: [t.link, t.url], color: syn.function, textDecoration: 'underline' },
      { tag: t.monospace, color: syn.string },
      { tag: t.quote, color: syn.comment },
      { tag: t.list, color: syn.property },
      { tag: t.inserted, color: syn.string },
      { tag: t.deleted, color: syn.invalid },
      { tag: t.changed, color: syn.number },
      { tag: t.invalid, color: syn.invalid, textDecoration: 'underline wavy' },
    ],
    { themeType: dark ? 'dark' : 'light' },
  );

  return [chrome, syntaxHighlighting(highlight)];
}
