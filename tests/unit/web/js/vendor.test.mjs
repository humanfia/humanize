// The editor's bundle, as far as it reads without a page: which language a file is opened in,
// and a theme drawn from the page's colours. The terminal's bundle needs a window to load, and
// is tried in a browser by tests/system/web/test_web_vendor.py.

import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  EditorState,
  EditorView,
  MergeView,
  basicSetup,
  gotoLine,
  languageFor,
  languageName,
  languageNames,
  openSearchPanel,
  themeFor,
  unifiedMergeView,
} from '../../../../src/hmz/web/static/vendor/codemirror.js'

test('the contract the panels import is there', () => {
  for (const name of [EditorState, EditorView, MergeView, basicSetup, gotoLine, openSearchPanel, unifiedMergeView]) {
    assert.ok(name)
  }
})

test('a file is opened in the language its name says', () => {
  const by = {
    'a.py': 'python',
    'src/x/a.pyi': 'python',
    'a.js': 'javascript',
    'a.mjs': 'javascript',
    'a.jsx': 'jsx',
    'a.ts': 'typescript',
    'a.tsx': 'tsx',
    'Cargo.toml': 'toml',
    'uv.lock': 'toml',
    'lib.rs': 'rust',
    'package.json': 'json',
    'README.md': 'markdown',
    'index.HTML': 'html',
    'style.css': 'css',
    'ci.yml': 'yaml',
    'a.c': 'cpp',
    'a.h': 'cpp',
    'a.hpp': 'cpp',
    'a.cc': 'cpp',
    'main.go': 'go',
    'A.java': 'java',
    'q.sql': 'sql',
    'a.xml': 'xml',
    'i.php': 'php',
    'run.sh': 'shell',
    'x.zsh': 'shell',
    '.bashrc': 'shell',
    '/home/me/.zshrc': 'shell',
    Dockerfile: 'dockerfile',
    'Dockerfile.dev': 'dockerfile',
    'a.rb': 'ruby',
    Gemfile: 'ruby',
    Makefile: 'makefile',
    'setup.cfg': 'properties',
    '.env': 'properties',
    'a.ini': 'properties',
    'fix.patch': 'diff',
    'a.diff': 'diff',
    'CMakeLists.txt': 'cmake',
  }
  for (const [file, name] of Object.entries(by)) {
    assert.equal(languageName(file), name, file)
    const support = languageFor(file)
    assert.ok(support?.language, file)
    assert.ok(languageNames.includes(name), name)
  }
})

test('a file in no language it knows is plain text', () => {
  for (const file of ['notes', 'a.txt', 'a.bin', '', 'dir/', '.hidden', 'a.']) {
    assert.equal(languageName(file), null, file)
    assert.equal(languageFor(file), null, file)
  }
})

test('the same language is made once, however many files are opened in it', () => {
  assert.equal(languageFor('a.py'), languageFor('b/c.py'))
})

test('an editor takes a language and a theme from tokens given either way, or none', () => {
  for (const options of [
    { dark: false, tokens: { paper: '#f4f8f9', ink: '#141a1f', mono: 'monospace' } },
    { dark: true, tokens: { '--paper': '#0f1418', '--pink-ink': '#ffa8cf' } },
    { dark: true, tokens: new Map([['--ink', '#e6eff1']]) },
    {},
    undefined,
  ]) {
    const state = EditorState.create({
      doc: 'def f():\n    return 1\n',
      extensions: [basicSetup, languageFor('a.py'), themeFor(options)],
    })
    assert.equal(state.doc.lines, 3)
  }
})
